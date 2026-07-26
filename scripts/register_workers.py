#!/usr/bin/env python3
"""Register CineOS workers in PostgreSQL and monitor their health."""

import json
import logging
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx
import psycopg2
import psycopg2.extras
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("register_workers")

DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "cineos")
DB_USER = os.getenv("POSTGRES_USER", "cineos")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "cineos_secret")

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", "config"))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
HEALTH_CHECK_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))
RE_REGISTER_INTERVAL = int(os.getenv("RE_REGISTER_INTERVAL", "60"))

DOCKER_NETWORK = os.getenv("DOCKER_NETWORK", "cineos-network")

KNOWN_WORKER_SERVICES = {
    "cineos-image-worker": {"type": "gpu", "port": 8000, "task_types": ["image_generation", "super_resolution"]},
    "cineos-voice-worker": {"type": "voice", "port": 8000, "task_types": ["tts_generation"]},
    "cineos-animation-worker": {"type": "animation", "port": 8000, "task_types": ["image_animation", "motion_transfer"]},
    "cineos-render-worker": {"type": "render", "port": 8000, "task_types": ["video_render", "clip_assembly"]},
    "cineos-quality-worker": {"type": "vision", "port": 8000, "task_types": ["quality_review", "consistency_check"]},
    "cineos-supervisor": {"type": "supervisor", "port": 9000, "task_types": ["job_scheduling", "worker_management"]},
}


@dataclass
class WorkerInfo:
    worker_id: str
    name: str
    worker_type: str
    host: str
    port: int
    protocol: str
    endpoint_url: str
    supported_task_types: list[str]
    state: str = "registering"
    enabled: bool = True
    health_check_url: str = ""
    max_concurrent_tasks: int = 1
    priority: int = 5
    gpu_model: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    cpu_cores: Optional[int] = None
    ram_gb: Optional[float] = None


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def load_worker_config() -> dict:
    candidates = [
        Path("config/workers.yaml"),
        Path("/app/config/workers.yaml"),
        CONFIG_DIR / "workers.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
    log.warning("No workers.yaml found, using defaults")
    return {}


def discover_workers() -> list[WorkerInfo]:
    workers: list[WorkerInfo] = []
    config = load_worker_config()

    docker_hosts = _discover_via_docker()

    for container_name, meta in KNOWN_WORKER_SERVICES.items():
        host = docker_hosts.get(container_name)
        if not host:
            host = _resolve_hostname(container_name)

        if not host:
            log.debug("Worker %s not reachable, skipping", container_name)
            continue

        endpoint = f"http://{host}:{meta['port']}"
        health_url = f"{endpoint}/health"

        if not _is_healthy(health_url):
            log.warning("Worker %s at %s is not healthy", container_name, host)
            continue

        worker_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"cineos-{container_name}"))

        worker_info = WorkerInfo(
            worker_id=worker_id,
            name=container_name,
            worker_type=meta["type"],
            host=host,
            port=meta["port"],
            protocol="http",
            endpoint_url=endpoint,
            supported_task_types=meta.get("task_types", []),
            state="idle",
            health_check_url=health_url,
            max_concurrent_tasks=config.get("worker_types", {}).get(meta["type"], {}).get("max_concurrent", 2),
            priority=config.get("worker_types", {}).get(meta["type"], {}).get("priority", 5),
        )

        hardware = _probe_hardware(host, meta["port"])
        if hardware:
            worker_info.gpu_model = hardware.get("gpu_model")
            worker_info.gpu_vram_gb = hardware.get("gpu_vram_gb")
            worker_info.cpu_cores = hardware.get("cpu_cores")
            worker_info.ram_gb = hardware.get("ram_gb")

        workers.append(worker_info)
        log.info("Discovered: %s (%s) at %s", container_name, meta["type"], host)

    return workers


def _discover_via_docker() -> dict[str, str]:
    hosts: dict[str, str] = {}
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "network", "inspect", DOCKER_NETWORK, "--format", "{{range .Containers}}{{.Name}} {{.IPv4Address}}{{println}}{{end}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    name = parts[0].lstrip("/")
                    ip = parts[1].split("/")[0]
                    hosts[name] = ip
    except FileNotFoundError:
        log.debug("Docker CLI not available")
    except Exception as exc:
        log.debug("Docker network inspection failed: %s", exc)
    return hosts


def _resolve_hostname(name: str) -> Optional[str]:
    try:
        ip = socket.gethostbyname(name)
        return ip
    except socket.gaierror:
        return None


def _is_healthy(url: str) -> bool:
    try:
        r = httpx.get(url, timeout=HEALTH_CHECK_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def _probe_hardware(host: str, port: int) -> Optional[dict]:
    try:
        r = httpx.get(f"http://{host}:{port}/metrics", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def register_worker(conn, worker: WorkerInfo):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cineos_exec.workers (
            worker_id, worker_name, worker_type, state, host, port, protocol,
            endpoint_url, supported_task_types, enabled, health_check_url,
            max_concurrent_tasks, priority, gpu_model, gpu_vram_gb, cpu_cores, ram_gb,
            last_heartbeat, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            NOW(), NOW(), NOW()
        )
        ON CONFLICT (worker_id) DO UPDATE SET
            worker_name = EXCLUDED.worker_name,
            state = EXCLUDED.state,
            host = EXCLUDED.host,
            port = EXCLUDED.port,
            endpoint_url = EXCLUDED.endpoint_url,
            supported_task_types = EXCLUDED.supported_task_types,
            enabled = EXCLUDED.enabled,
            health_check_url = EXCLUDED.health_check_url,
            max_concurrent_tasks = EXCLUDED.max_concurrent_tasks,
            priority = EXCLUDED.priority,
            gpu_model = EXCLUDED.gpu_model,
            gpu_vram_gb = EXCLUDED.gpu_vram_gb,
            cpu_cores = EXCLUDED.cpu_cores,
            ram_gb = EXCLUDED.ram_gb,
            last_heartbeat = NOW(),
            updated_at = NOW()
        """,
        (
            uuid.UUID(worker.worker_id),
            worker.name,
            worker.worker_type,
            worker.state,
            worker.host,
            worker.port,
            worker.protocol,
            worker.endpoint_url,
            worker.supported_task_types,
            worker.enabled,
            worker.health_check_url,
            worker.max_concurrent_tasks,
            worker.priority,
            worker.gpu_model,
            worker.gpu_vram_gb,
            worker.cpu_cores,
            worker.ram_gb,
        ),
    )
    conn.commit()
    cur.close()
    log.info("Registered worker: %s (id=%s)", worker.name, worker.worker_id[:8])


def mark_offline(conn, worker_id: str):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE cineos_exec.workers
        SET state = 'offline', updated_at = NOW()
        WHERE worker_id = %s
        """,
        (uuid.UUID(worker_id),),
    )
    conn.commit()
    cur.close()
    log.info("Marked worker %s as offline", worker_id[:8])


def update_heartbeat(conn, worker_id: str, state: str):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE cineos_exec.workers
        SET last_heartbeat = NOW(), state = %s, updated_at = NOW()
        WHERE worker_id = %s
        """,
        (state, uuid.UUID(worker_id)),
    )
    conn.commit()
    cur.close()


def health_monitor_loop(registered_workers: list[WorkerInfo]):
    log.info("Starting health monitor loop (interval=%ds)", HEALTH_CHECK_INTERVAL)

    while True:
        try:
            time.sleep(HEALTH_CHECK_INTERVAL)

            conn = get_connection()

            for worker in list(registered_workers):
                if _is_healthy(worker.health_check_url):
                    new_state = "idle"
                    update_heartbeat(conn, worker.worker_id, new_state)
                else:
                    log.warning("Worker %s is offline, re-registering...", worker.name)
                    mark_offline(conn, worker.worker_id)

                    if _is_healthy(worker.health_check_url):
                        worker.state = "idle"
                        register_worker(conn, worker)
                        log.info("Re-registered: %s", worker.name)
                    else:
                        log.error("Worker %s still unreachable", worker.name)

            conn.close()

        except KeyboardInterrupt:
            log.info("Health monitor shutting down")
            break
        except Exception as exc:
            log.error("Health monitor error: %s", exc)
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(5)


def main():
    log.info("=== CineOS Worker Registration ===")

    workers = discover_workers()

    if not workers:
        log.warning("No workers found. Waiting %d seconds and retrying...", RE_REGISTER_INTERVAL)
        time.sleep(RE_REGISTER_INTERVAL)
        workers = discover_workers()

    if not workers:
        log.error("No workers available. Exiting.")
        sys.exit(1)

    conn = get_connection()
    registered: list[WorkerInfo] = []

    for worker in workers:
        try:
            register_worker(conn, worker)
            registered.append(worker)
        except Exception as exc:
            log.error("Failed to register %s: %s", worker.name, exc)

    conn.close()

    log.info("Registered %d/%d workers", len(registered), len(workers))

    for w in registered:
        log.info("  %-30s  type=%-12s  endpoint=%s", w.name, w.worker_type, w.endpoint_url)

    if "--once" not in sys.argv:
        health_monitor_loop(registered)

    log.info("=== Worker registration complete ===")


if __name__ == "__main__":
    main()
