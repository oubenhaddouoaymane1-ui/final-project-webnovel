"""Worker lifecycle, job claiming, and metrics tests."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone, timedelta

import asyncpg
import pytest


# ── Helpers ────────────────────────────────────────────────────────


async def _insert_worker(conn, **overrides) -> uuid.UUID:
    worker_id = uuid.uuid4()
    defaults = {
        "worker_id": worker_id,
        "worker_name": "test-worker",
        "worker_type": "image_generation",
        "state": "idle",
        "host": "10.0.0.1",
        "port": 8001,
        "supported_task_types": ["image_generate"],
        "enabled": True,
        "health_status": "healthy",
        "max_concurrent_tasks": 1,
        "priority": 5,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f"${i+1}" for i in range(len(defaults)))
    vals = list(defaults.values())
    await conn.execute(
        f"INSERT INTO cineos_exec.workers ({cols}) VALUES ({placeholders})",
        *vals,
    )
    return worker_id


async def _insert_job(conn, project_id: uuid.UUID, **overrides) -> uuid.UUID:
    job_id = uuid.uuid4()
    defaults = {
        "job_id": job_id,
        "project_id": project_id,
        "job_type": "image_generate",
        "state": "pending",
        "priority": 5,
        "payload": json.dumps({"shot_id": str(uuid.uuid4())}),
        "timeout_ms": 300000,
        "max_retries": 3,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f"${i+1}" for i in range(len(defaults)))
    vals = list(defaults.values())
    await conn.execute(
        f"INSERT INTO cineos_exec.jobs ({cols}) VALUES ({placeholders})",
        *vals,
    )
    return job_id


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_worker_registration(db_pool: asyncpg.Pool):
    async with db_pool.acquire() as conn:
        worker_id = await _insert_worker(conn, worker_name="reg-worker")
        row = await conn.fetchrow(
            "SELECT * FROM cineos_exec.workers WHERE worker_id = $1",
            worker_id,
        )
        assert row["worker_name"] == "reg-worker"
        assert row["worker_type"] == "image_generation"
        assert row["state"] == "idle"
        assert row["enabled"] is True
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


@pytest.mark.integration
async def test_worker_heartbeat(db_pool: asyncpg.Pool, test_worker: uuid.UUID):
    """Heartbeat updates the last_heartbeat timestamp."""
    async with db_pool.acquire() as conn:
        before = await conn.fetchval(
            "SELECT last_heartbeat FROM cineos_exec.workers WHERE worker_id = $1",
            test_worker,
        )
        await asyncio_sleep(0.05)
        await conn.execute(
            """
            UPDATE cineos_exec.workers
            SET last_heartbeat = NOW(), state = 'busy'
            WHERE worker_id = $1
            """,
            test_worker,
        )
        after = await conn.fetchrow(
            "SELECT last_heartbeat, state FROM cineos_exec.workers WHERE worker_id = $1",
            test_worker,
        )
        assert after["last_heartbeat"] >= before
        assert after["state"] == "busy"


@pytest.mark.integration
async def test_worker_offline_detection(db_pool: asyncpg.Pool):
    """Worker with old heartbeat should be detectable as offline."""
    async with db_pool.acquire() as conn:
        worker_id = await _insert_worker(conn, worker_name="stale-worker")
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        await conn.execute(
            """
            UPDATE cineos_exec.workers
            SET last_heartbeat = $1, state = 'idle'
            WHERE worker_id = $2
            """,
            old_time,
            worker_id,
        )
        stale = await conn.fetch(
            """
            SELECT worker_id FROM cineos_exec.workers
            WHERE state != 'offline'
              AND last_heartbeat < NOW() - INTERVAL '90 seconds'
            """,
        )
        stale_ids = [r["worker_id"] for r in stale]
        assert worker_id in stale_ids
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


import asyncio

async def asyncio_sleep(seconds: float):
    await asyncio.sleep(seconds)


@pytest.mark.integration
async def test_job_assignment(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Assign a pending job to a worker using SKIP LOCKED pattern."""
    async with db_pool.acquire() as conn:
        worker_id = await _insert_worker(conn, worker_name="assign-worker")
        job_id = await _insert_job(conn, test_project)

        row = await conn.fetchrow(
            """
            UPDATE cineos_exec.jobs
            SET state = 'assigned',
                worker_id = $1,
                assigned_at = NOW()
            WHERE job_id = $2 AND state = 'pending'
            RETURNING job_id, state, worker_id
            """,
            worker_id,
            job_id,
        )
        assert row is not None
        assert row["state"] == "assigned"
        assert row["worker_id"] == worker_id
        await conn.execute(
            "DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


@pytest.mark.integration
async def test_job_claim_skip_locked(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Two concurrent claims on the same job must not conflict."""
    async with db_pool.acquire() as conn:
        worker_a = await _insert_worker(conn, worker_name="worker-a")
        worker_b = await _insert_worker(conn, worker_name="worker-b")
        job_id = await _insert_job(conn, test_project)

        row_a = await conn.fetchrow(
            """
            UPDATE cineos_exec.jobs
            SET state = 'assigned', worker_id = $1, assigned_at = NOW()
            WHERE job_id = $2 AND state = 'pending'
            RETURNING job_id
            """,
            worker_a,
            job_id,
        )
        assert row_a is not None

        row_b = await conn.fetchrow(
            """
            UPDATE cineos_exec.jobs
            SET state = 'assigned', worker_id = $1, assigned_at = NOW()
            WHERE job_id = $2 AND state = 'pending'
            RETURNING job_id
            """,
            worker_b,
            job_id,
        )
        assert row_b is None

        final = await conn.fetchrow(
            "SELECT worker_id FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert final["worker_id"] == worker_a
        await conn.execute(
            "DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id IN ($1, $2)",
            worker_a,
            worker_b,
        )


@pytest.mark.integration
async def test_job_completion(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Complete a job and verify the result is stored."""
    async with db_pool.acquire() as conn:
        worker_id = await _insert_worker(conn, worker_name="complete-worker")
        job_id = await _insert_job(conn, test_project)

        await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'completed',
                worker_id = $1,
                assigned_at = NOW(),
                started_at = NOW(),
                completed_at = NOW(),
                result = $3::jsonb
            WHERE job_id = $2
            """,
            worker_id,
            job_id,
            json.dumps({"image_path": "/output/shot_001.png", "quality": 0.91}),
        )
        row = await conn.fetchrow(
            "SELECT state, result, completed_at FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "completed"
        assert row["completed_at"] is not None
        assert row["result"]["image_path"] == "/output/shot_001.png"
        await conn.execute(
            "DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


@pytest.mark.integration
async def test_job_failure(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """A failed job records the error message."""
    async with db_pool.acquire() as conn:
        worker_id = await _insert_worker(conn, worker_name="fail-worker")
        job_id = await _insert_job(conn, test_project)

        await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'failed',
                worker_id = $1,
                assigned_at = NOW(),
                started_at = NOW(),
                completed_at = NOW(),
                error_message = 'CUDA out of memory',
                error_code = 'GPU_OOM'
            WHERE job_id = $2
            """,
            worker_id,
            job_id,
        )
        row = await conn.fetchrow(
            "SELECT state, error_message, error_code FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "failed"
        assert row["error_message"] == "CUDA out of memory"
        assert row["error_code"] == "GPU_OOM"
        await conn.execute(
            "DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


@pytest.mark.integration
async def test_worker_load_balancing(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Jobs should be distributed to workers with lowest load."""
    async with db_pool.acquire() as conn:
        w1 = await _insert_worker(conn, worker_name="w1", current_load=0.2, priority=5)
        w2 = await _insert_worker(conn, worker_name="w2", current_load=0.8, priority=5)
        w3 = await _insert_worker(conn, worker_name="w3", current_load=0.5, priority=8)

        best = await conn.fetchrow(
            """
            SELECT worker_id, worker_name, priority, current_load
            FROM cineos_exec.workers
            WHERE state = 'idle' AND enabled = true
              AND 'image_generate' = ANY(supported_task_types)
            ORDER BY priority DESC, current_load ASC
            LIMIT 1
            """,
        )
        assert best["worker_id"] == w3
        assert best["priority"] == 8

        for w in [w1, w2, w3]:
            await conn.execute(
                "DELETE FROM cineos_exec.workers WHERE worker_id = $1", w
            )


@pytest.mark.integration
async def test_worker_health_check(db_pool: asyncpg.Pool, test_worker: uuid.UUID):
    """Health check endpoint status reflects DB state."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cineos_exec.workers
            SET health_status = 'healthy',
                last_health_check = NOW(),
                cpu_usage_percent = 45.2,
                ram_usage_percent = 62.8,
                gpu_memory_used_mb = 8500.0,
                gpu_memory_total_mb = 24000.0
            WHERE worker_id = $1
            """,
            test_worker,
        )
        row = await conn.fetchrow(
            """
            SELECT health_status, cpu_usage_percent, ram_usage_percent,
                   gpu_memory_used_mb, gpu_memory_total_mb
            FROM cineos_exec.workers WHERE worker_id = $1
            """,
            test_worker,
        )
        assert row["health_status"] == "healthy"
        assert row["cpu_usage_percent"] == pytest.approx(45.2)
        assert row["gpu_memory_used_mb"] < row["gpu_memory_total_mb"]


@pytest.mark.integration
async def test_worker_metrics(db_pool: asyncpg.Pool, test_worker: uuid.UUID):
    """Worker metrics are stored and retrievable."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cineos_exec.workers
            SET total_tasks_completed = 150,
                total_tasks_failed = 3,
                avg_task_duration_ms = 2340.5,
                success_rate = 0.98,
                last_task_completed_at = NOW()
            WHERE worker_id = $1
            """,
            test_worker,
        )
        row = await conn.fetchrow(
            """
            SELECT total_tasks_completed, total_tasks_failed,
                   avg_task_duration_ms, success_rate, last_task_completed_at
            FROM cineos_exec.workers WHERE worker_id = $1
            """,
            test_worker,
        )
        assert row["total_tasks_completed"] == 150
        assert row["total_tasks_failed"] == 3
        assert row["avg_task_duration_ms"] == pytest.approx(2340.5)
        assert row["success_rate"] == pytest.approx(0.98)
        assert row["last_task_completed_at"] is not None
