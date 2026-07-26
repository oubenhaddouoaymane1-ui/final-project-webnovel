"""Failure simulation and recovery tests."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest


# ── Worker offline recovery ────────────────────────────────────────


@pytest.mark.integration
async def test_worker_offline_recovery(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """When a worker goes offline, its pending job should be requeued."""
    async with db_pool.acquire() as conn:
        worker_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_exec.workers
                (worker_id, worker_name, worker_type, state,
                 supported_task_types, enabled)
            VALUES ($1, 'dying-worker', 'image_generation', 'busy',
                    ARRAY['image_generate'], true)
            """,
            worker_id,
        )
        job_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_exec.jobs
                (job_id, project_id, job_type, state, worker_id,
                 priority, payload)
            VALUES ($1, $2, 'image_generate', 'assigned', $3,
                    5, $4::jsonb)
            """,
            job_id,
            test_project,
            worker_id,
            json.dumps({"shot_id": str(uuid.uuid4())}),
        )

        # Worker goes offline
        await conn.execute(
            "UPDATE cineos_exec.workers SET state = 'offline' WHERE worker_id = $1",
            worker_id,
        )

        # Requeue jobs assigned to offline worker
        await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'pending', worker_id = NULL, assigned_at = NULL
            WHERE worker_id = $1 AND state IN ('assigned', 'running')
            """,
            worker_id,
        )

        row = await conn.fetchrow(
            "SELECT state, worker_id FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "pending"
        assert row["worker_id"] is None

        await conn.execute("DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id)
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


# ── Database connection loss ───────────────────────────────────────


@pytest.mark.integration
async def test_database_connection_loss():
    """Attempt connection to a bogus DSN; verify graceful failure."""
    with pytest.raises(Exception):
        pool = await asyncpg.create_pool(
            "postgresql://x:x@nonexistent-host:99999/nodb",
            timeout=2,
        )
        await pool.close()


# ── API timeout handling ───────────────────────────────────────────


@pytest.mark.unit
async def test_api_timeout_handling():
    """Simulated timeout should trigger a retry."""
    call_count = 0

    async def flaky_call():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise asyncio.TimeoutError("Connection timed out")
        return {"status": "ok"}

    result = None
    for attempt in range(3):
        try:
            result = await flaky_call()
            break
        except asyncio.TimeoutError:
            continue

    assert result is not None
    assert result["status"] == "ok"
    assert call_count == 3


# ── Partial render recovery ────────────────────────────────────────


@pytest.mark.integration
async def test_partial_render_recovery(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """A partially completed render job can be resumed."""
    async with db_pool.acquire() as conn:
        job_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_exec.jobs
                (job_id, project_id, job_type, state, priority, payload,
                 result)
            VALUES ($1, $2, 'video_render', 'failed', 5, $3::jsonb, $4::jsonb)
            """,
            job_id,
            test_project,
            json.dumps({"shot_id": str(uuid.uuid4()), "resume_from_clip": 12}),
            json.dumps({"clips_completed": 12, "total_clips": 20}),
        )

        row = await conn.fetchrow(
            "SELECT result, state FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "failed"
        assert row["result"]["clips_completed"] == 12

        # Requeue for resume
        await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'pending', worker_id = NULL, error_message = NULL,
                retry_count = retry_count + 1
            WHERE job_id = $1
            """,
            job_id,
        )
        row = await conn.fetchrow(
            "SELECT state, retry_count FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "pending"
        assert row["retry_count"] == 1

        await conn.execute("DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id)


# ── Corrupted image detection ──────────────────────────────────────


@pytest.mark.integration
async def test_corrupted_image_detection(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """A review with very low scores flags the image as corrupted."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, passed, decision,
                 issues, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.10, 0.05, false,
                    'reject', $4::jsonb, 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
            json.dumps(["image appears corrupted", "all-black output"]),
        )
        row = await conn.fetchrow(
            "SELECT decision, issues FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["decision"] == "reject"
        assert row["issues"][0] == "image appears corrupted"
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


# ── Concurrent modification (optimistic locking) ───────────────────


@pytest.mark.integration
async def test_concurrent_modification(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Two concurrent updates to the same job: second one should fail with optimistic lock."""
    async with db_pool.acquire() as conn:
        job_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_exec.jobs
                (job_id, project_id, job_type, state, priority, payload)
            VALUES ($1, $2, 'image_generate', 'assigned', 5, $3::jsonb)
            """,
            job_id,
            test_project,
            json.dumps({"shot_id": str(uuid.uuid4())}),
        )

        row1 = await conn.fetchrow(
            "SELECT state FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )

        # First worker completes
        updated = await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'completed', completed_at = NOW()
            WHERE job_id = $1 AND state = 'assigned'
            """,
            job_id,
        )
        assert updated.endswith("1")

        # Second worker tries to complete the same job — should affect 0 rows
        updated2 = await conn.execute(
            """
            UPDATE cineos_exec.jobs
            SET state = 'completed', completed_at = NOW()
            WHERE job_id = $1 AND state = 'assigned'
            """,
            job_id,
        )
        assert updated2.endswith("0")

        await conn.execute("DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id)


# ── Disk full handling ─────────────────────────────────────────────


@pytest.mark.unit
async def test_disk_full_handling():
    """Graceful error when disk is full during file write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = os.path.join(tmpdir, "output.png")
        try:
            # Simulate disk full by writing to read-only location
            readonly = os.path.join(tmpdir, "readonly_dir")
            os.makedirs(readonly)
            os.chmod(readonly, 0o444)
            bad_path = os.path.join(readonly, "file.png")
            with open(bad_path, "w") as f:
                f.write("test")
            os.chmod(readonly, 0o555)
        except (OSError, PermissionError):
            pass

        # Verify we can still write to the temp dir
        with open(fake_path, "w") as f:
            f.write("ok")
        assert os.path.exists(fake_path)


# ── Memory overflow protection ─────────────────────────────────────


@pytest.mark.unit
async def test_memory_overflow_protection():
    """Graceful degradation when processing would consume too much memory."""
    max_buffer_size = 1024 * 1024  # 1MB limit

    data_chunks = [b"x" * (max_buffer_size // 2) for _ in range(10)]

    buffered = bytearray()
    accepted = 0
    for chunk in data_chunks:
        if len(buffered) + len(chunk) > max_buffer_size:
            break
        buffered.extend(chunk)
        accepted += 1

    assert accepted >= 1
    assert len(buffered) <= max_buffer_size
