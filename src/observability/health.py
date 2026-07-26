"""Health check system for CineOS services and dependencies."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health report for a single component."""
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = ""

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


# Type alias for health check callables
HealthCheckFn = Callable[[], Coroutine[Any, Any, ComponentHealth]]


class HealthChecker:
    """Aggregates health from all system components.

    Provides /health, /health/ready, /health/live, and /health/detailed
    endpoint handlers for HTTP or integration use.
    """

    def __init__(self) -> None:
        self._checks: Dict[str, HealthCheckFn] = {}
        self._results_cache: Dict[str, ComponentHealth] = {}
        self._cache_ttl: float = 10.0
        self._cache_timestamps: Dict[str, float] = {}
        self._registered_at_startup: bool = False

    # ── Registration ──────────────────────────────────────────────

    def register(self, name: str, check_fn: HealthCheckFn) -> None:
        """Register a health check callback."""
        self._checks[name] = check_fn
        logger.debug("Registered health check: %s", name)

    def register_all_standard(self) -> None:
        """Register all standard CineOS health checks."""
        self.register("postgresql", self._check_postgresql)
        self.register("redis", self._check_redis)
        self.register("n8n", self._check_n8n)
        self.register("workers", self._check_workers)
        self.register("disk_space", self._check_disk_space)
        self.register("memory", self._check_memory)
        self._registered_at_startup = True

    # ── Individual health checks ──────────────────────────────────

    async def _check_postgresql(self) -> ComponentHealth:
        """Check PostgreSQL connectivity."""
        start = time.monotonic()
        try:
            import asyncpg
            dsn = os.environ.get(
                "DATABASE_URL",
                os.environ.get("CINEOS_DATABASE_URL", "postgresql://cineos:cineos@localhost:5432/cineos"),
            )
            conn = await asyncpg.connect(dsn=dsn, timeout=5)
            row = await conn.fetchrow("SELECT 1 AS ok")
            await conn.close()
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="postgresql",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Connection successful",
                details={"server_version": str(getattr(row, "ok", "unknown"))},
            )
        except ImportError:
            return ComponentHealth(
                name="postgresql",
                status=HealthStatus.DEGRADED,
                message="asyncpg not installed",
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="postgresql",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    async def _check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        start = time.monotonic()
        try:
            import aioredis
            redis_url = os.environ.get(
                "REDIS_URL",
                os.environ.get("CINEOS_REDIS_URL", "redis://localhost:6379/0"),
            )
            redis = aioredis.from_url(redis_url, socket_timeout=5)
            await redis.ping()
            await redis.close()
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=round(latency, 2),
                message="Pong received",
            )
        except ImportError:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message="aioredis not installed",
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    async def _check_n8n(self) -> ComponentHealth:
        """Check n8n workflow engine availability."""
        start = time.monotonic()
        try:
            import httpx
            n8n_url = os.environ.get("N8N_URL", "http://localhost:5678")
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{n8n_url}/healthz")
                latency = (time.monotonic() - start) * 1000
                if resp.status_code == 200:
                    return ComponentHealth(
                        name="n8n",
                        status=HealthStatus.HEALTHY,
                        latency_ms=round(latency, 2),
                        message="n8n responding",
                        details={"status_code": resp.status_code},
                    )
                return ComponentHealth(
                    name="n8n",
                    status=HealthStatus.DEGRADED,
                    latency_ms=round(latency, 2),
                    message=f"n8n returned status {resp.status_code}",
                    details={"status_code": resp.status_code},
                )
        except ImportError:
            return ComponentHealth(
                name="n8n",
                status=HealthStatus.DEGRADED,
                message="httpx not installed",
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="n8n",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    async def _check_workers(self) -> ComponentHealth:
        """Check worker pool availability from the database."""
        start = time.monotonic()
        try:
            import asyncpg
            dsn = os.environ.get(
                "DATABASE_URL",
                os.environ.get("CINEOS_DATABASE_URL", "postgresql://cineos:cineos@localhost:5432/cineos"),
            )
            conn = await asyncpg.connect(dsn=dsn, timeout=5)
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE state IN ('idle', 'busy'))::int AS active,
                    COUNT(*) FILTER (WHERE state = 'idle')::int AS idle
                FROM cineos_exec.workers
                WHERE enabled = TRUE
            """)
            await conn.close()
            latency = (time.monotonic() - start) * 1000
            total = row["total"]
            active = row["active"]
            idle = row["idle"]
            status = HealthStatus.HEALTHY
            if total == 0:
                status = HealthStatus.UNHEALTHY
            elif active == 0:
                status = HealthStatus.DEGRADED
            return ComponentHealth(
                name="workers",
                status=status,
                latency_ms=round(latency, 2),
                message=f"{active}/{total} workers active, {idle} idle",
                details={"total": total, "active": active, "idle": idle},
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="workers",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    async def _check_disk_space(self) -> ComponentHealth:
        """Check available disk space."""
        start = time.monotonic()
        try:
            usage = shutil.disk_usage("/")
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            used_pct = ((usage.total - usage.free) / usage.total) * 100
            latency = (time.monotonic() - start) * 1000

            if used_pct > 95:
                status = HealthStatus.UNHEALTHY
            elif used_pct > 85:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return ComponentHealth(
                name="disk_space",
                status=status,
                latency_ms=round(latency, 2),
                message=f"{free_gb:.1f} GB free of {total_gb:.1f} GB ({used_pct:.1f}% used)",
                details={
                    "total_gb": round(total_gb, 2),
                    "free_gb": round(free_gb, 2),
                    "used_percent": round(used_pct, 2),
                },
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    async def _check_memory(self) -> ComponentHealth:
        """Check system memory usage."""
        start = time.monotonic()
        try:
            import psutil
            mem = psutil.virtual_memory()
            latency = (time.monotonic() - start) * 1000

            if mem.percent > 95:
                status = HealthStatus.UNHEALTHY
            elif mem.percent > 85:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return ComponentHealth(
                name="memory",
                status=status,
                latency_ms=round(latency, 2),
                message=f"{mem.percent:.1f}% used ({mem.available / (1024**3):.1f} GB available)",
                details={
                    "total_gb": round(mem.total / (1024 ** 3), 2),
                    "available_gb": round(mem.available / (1024 ** 3), 2),
                    "used_percent": round(mem.percent, 2),
                },
            )
        except ImportError:
            # Fallback: read /proc/meminfo on Linux
            try:
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                mem_info = {}
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        mem_info[key] = int(parts[1]) * 1024  # kB to bytes
                total = mem_info.get("MemTotal", 0)
                available = mem_info.get("MemAvailable", 0)
                used_pct = ((total - available) / total * 100) if total else 0
                latency = (time.monotonic() - start) * 1000

                if used_pct > 95:
                    status = HealthStatus.UNHEALTHY
                elif used_pct > 85:
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.HEALTHY

                return ComponentHealth(
                    name="memory",
                    status=status,
                    latency_ms=round(latency, 2),
                    message=f"{used_pct:.1f}% used ({available / (1024**3):.1f} GB available)",
                    details={
                        "total_gb": round(total / (1024 ** 3), 2),
                        "available_gb": round(available / (1024 ** 3), 2),
                        "used_percent": round(used_pct, 2),
                    },
                )
            except Exception as inner_exc:
                latency = (time.monotonic() - start) * 1000
                return ComponentHealth(
                    name="memory",
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=round(latency, 2),
                    message=str(inner_exc),
                )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return ComponentHealth(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 2),
                message=str(exc),
            )

    # ── Aggregate checks ──────────────────────────────────────────

    async def check_all(self, force: bool = False) -> Dict[str, ComponentHealth]:
        """Run all registered health checks and return results."""
        results: Dict[str, ComponentHealth] = {}
        tasks = []

        for name, check_fn in self._checks.items():
            if not force and name in self._results_cache:
                age = time.monotonic() - self._cache_timestamps.get(name, 0)
                if age < self._cache_ttl:
                    results[name] = self._results_cache[name]
                    continue
            tasks.append((name, check_fn))

        if tasks:
            check_results = await asyncio.gather(
                *(fn() for _, fn in tasks),
                return_exceptions=True,
            )
            for (name, _), result in zip(tasks, check_results):
                if isinstance(result, Exception):
                    results[name] = ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Check raised: {result}",
                    )
                else:
                    results[name] = result
                self._results_cache[name] = results[name]
                self._cache_timestamps[name] = time.monotonic()

        return results

    def _aggregate_status(self, results: Dict[str, ComponentHealth]) -> HealthStatus:
        """Determine overall status from individual component results."""
        if not results:
            return HealthStatus.HEALTHY

        statuses = [h.status for h in results.values()]
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    # ── Endpoint handlers ─────────────────────────────────────────

    async def handle_health(self) -> Dict[str, Any]:
        """Handle /health endpoint — overall system health."""
        results = await self.check_all()
        overall = self._aggregate_status(results)
        return {
            "status": overall.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {name: h.to_dict() for name, h in results.items()},
        }

    async def handle_ready(self) -> Dict[str, Any]:
        """Handle /health/ready endpoint — readiness probe.

        Returns 200 only if all critical dependencies are up.
        """
        results = await self.check_all()
        overall = self._aggregate_status(results)

        critical_components = ["postgresql", "redis", "n8n"]
        critical_healthy = all(
            results[c].status != HealthStatus.UNHEALTHY
            for c in critical_components
            if c in results
        )
        ready = overall != HealthStatus.UNHEALTHY and critical_healthy
        return {
            "ready": ready,
            "status": overall.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def handle_live(self) -> Dict[str, Any]:
        """Handle /health/live endpoint — liveness probe.

        Always returns 200 if the process is running.
        """
        return {
            "alive": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }

    async def handle_detailed(self) -> Dict[str, Any]:
        """Handle /health/detailed endpoint — full component breakdown."""
        results = await self.check_all(force=True)
        overall = self._aggregate_status(results)

        return {
            "status": overall.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks_registered": list(self._checks.keys()),
            "components": {name: h.to_dict() for name, h in results.items()},
        }

    async def handle(self, path: str) -> Dict[str, Any]:
        """Route a health check request by path."""
        if path in ("/health", "/health/"):
            return await self.handle_health()
        if path == "/health/ready":
            return await self.handle_ready()
        if path == "/health/live":
            return await self.handle_live()
        if path == "/health/detailed":
            return await self.handle_detailed()
        return {"error": "Unknown health endpoint", "available": [
            "/health", "/health/ready", "/health/live", "/health/detailed",
        ]}
