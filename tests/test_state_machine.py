"""State machine tests — exercise the enforce_state_transition trigger."""
from __future__ import annotations

import uuid

import asyncpg
import pytest


VALID_HAPPY_PATH = [
    "received", "validated", "parsed", "understood", "biblified",
    "characterized", "worldbuilt", "timeline_verified", "planned",
    "prompted", "queued", "generating", "generated", "reviewing",
    "approved", "voiced", "musicked", "animated", "rendering",
    "rendered", "super_resolution", "final_review", "delivered",
    "learned", "completed",
]


async def _transition_to(conn, project_id: uuid.UUID, target_state: str):
    """Transition a project to *target_state* assuming it is at the previous state."""
    await conn.execute(
        """
        UPDATE cineos_core.projects
        SET current_state = $1
        WHERE project_id = $2
        """,
        target_state,
        project_id,
    )


async def _get_state(conn, project_id: uuid.UUID) -> str:
    row = await conn.fetchval(
        "SELECT current_state FROM cineos_core.projects WHERE project_id = $1",
        project_id,
    )
    return row


@pytest.mark.integration
async def test_happy_path_full_lifecycle(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Walk through the entire happy-path lifecycle: received → completed."""
    async with db_pool.acquire() as conn:
        for state in VALID_HAPPY_PATH[1:]:
            await _transition_to(conn, test_project, state)
        assert await _get_state(conn, test_project) == "completed"


@pytest.mark.integration
async def test_pause_and_resume(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Pause mid-lifecycle and resume from paused."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "validated")
        await _transition_to(conn, test_project, "parsed")

        await _transition_to(conn, test_project, "paused")
        assert await _get_state(conn, test_project) == "paused"

        await _transition_to(conn, test_project, "understood")
        assert await _get_state(conn, test_project) == "understood"


@pytest.mark.integration
async def test_retry_on_failure(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Enter failed state, then retrying."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "validated")
        await _transition_to(conn, test_project, "generating")

        await _transition_to(conn, test_project, "failed")
        assert await _get_state(conn, test_project) == "failed"

        await _transition_to(conn, test_project, "retrying")
        assert await _get_state(conn, test_project) == "retrying"

        await _transition_to(conn, test_project, "generating")
        await _transition_to(conn, test_project, "generated")
        assert await _get_state(conn, test_project) == "generated"


@pytest.mark.integration
async def test_cancel_project(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Cancel from a normal state (received) and from failed."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "cancelled")
        assert await _get_state(conn, test_project) == "cancelled"

    # Create a fresh project to test cancel from failed
    pid2 = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.projects
                (project_id, user_id, chat_id, title, current_state)
            VALUES ($1, 999, 888, 'Cancel Test', 'received')
            """,
            pid2,
        )
        await _transition_to(conn, pid2, "validated")
        await _transition_to(conn, pid2, "failed")
        await _transition_to(conn, pid2, "cancelled")
        assert await _get_state(conn, pid2) == "cancelled"
        await conn.execute(
            "DELETE FROM cineos_core.projects WHERE project_id = $1", pid2
        )


INVALID_TRANSITIONS = [
    ("received", "parsed"),
    ("received", "completed"),
    ("received", "generating"),
    ("received", "failed"),
    ("received", "validated"),  # this IS valid, so skip; we want invalid
    ("completed", "received"),
    ("completed", "failed"),
    ("completed", "validated"),
    ("cancelled", "received"),
    ("cancelled", "completed"),
]


@pytest.mark.integration
@pytest.mark.parametrize("from_state,to_state", [
    ("received", "parsed"),
    ("received", "completed"),
    ("received", "generating"),
    ("received", "failed"),
    ("completed", "received"),
    ("completed", "failed"),
    ("completed", "validated"),
    ("cancelled", "received"),
    ("cancelled", "completed"),
    ("cancelled", "generating"),
], ids=[
    "received→parsed",
    "received→completed",
    "received→generating",
    "received→failed",
    "completed→received",
    "completed→failed",
    "completed→validated",
    "cancelled→received",
    "cancelled→completed",
    "cancelled→generating",
])
async def test_invalid_transition_rejected(
    db_pool: asyncpg.Pool, from_state: str, to_state: str
):
    """Each invalid transition must be rejected by the DB trigger."""
    pid = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.projects
                (project_id, user_id, chat_id, title, current_state)
            VALUES ($1, 1, 1, 'SM Test', $2)
            """,
            pid,
            from_state,
        )
        # Try the invalid transition
        with pytest.raises(asyncpg.RaiseError, match="Invalid state transition"):
            await _transition_to(conn, pid, to_state)
        # Verify state unchanged
        assert await _get_state(conn, pid) == from_state
        await conn.execute(
            "DELETE FROM cineos_core.projects WHERE project_id = $1", pid
        )


@pytest.mark.integration
async def test_waiting_state(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Enter waiting from a normal state and exit waiting."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "validated")
        await _transition_to(conn, test_project, "parsed")
        await _transition_to(conn, test_project, "waiting")
        assert await _get_state(conn, test_project) == "waiting"

        await _transition_to(conn, test_project, "understood")
        assert await _get_state(conn, test_project) == "understood"


@pytest.mark.integration
async def test_manual_attention(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Escalate to manual_attention from repairing."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "validated")
        await _transition_to(conn, test_project, "generating")
        await _transition_to(conn, test_project, "generated")
        await _transition_to(conn, test_project, "reviewing")
        await _transition_to(conn, test_project, "repairing")
        await _transition_to(conn, test_project, "manual_attention")
        assert await _get_state(conn, test_project) == "manual_attention"


@pytest.mark.integration
@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
async def test_terminal_states(db_pool: asyncpg.Pool, terminal: str):
    """completed, failed, cancelled are terminal — cannot transition out."""
    pid = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.projects
                (project_id, user_id, chat_id, title, current_state)
            VALUES ($1, 1, 1, 'Terminal Test', $2)
            """,
            pid,
            terminal,
        )
        if terminal == "completed":
            targets = ["received", "validated", "failed", "cancelled"]
        elif terminal == "failed":
            targets = ["received", "validated", "completed"]
        else:
            targets = ["received", "completed", "failed"]

        for target in targets:
            with pytest.raises(asyncpg.RaiseError, match="Invalid state transition"):
                await _transition_to(conn, pid, target)
            assert await _get_state(conn, pid) == terminal

        await conn.execute(
            "DELETE FROM cineos_core.projects WHERE project_id = $1", pid
        )


@pytest.mark.integration
async def test_state_change_timestamp(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """last_state_change_at is updated on every transition."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_state_change_at FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        ts1 = row["last_state_change_at"]

        await _transition_to(conn, test_project, "validated")
        row = await conn.fetchrow(
            "SELECT last_state_change_at FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        ts2 = row["last_state_change_at"]
        assert ts2 >= ts1


@pytest.mark.integration
async def test_previous_state_tracking(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """previous_state is set to the old state after each transition."""
    async with db_pool.acquire() as conn:
        await _transition_to(conn, test_project, "validated")
        row = await conn.fetchrow(
            "SELECT previous_state FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        assert row["previous_state"] == "received"

        await _transition_to(conn, test_project, "parsed")
        row = await conn.fetchrow(
            "SELECT previous_state FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        assert row["previous_state"] == "validated"
