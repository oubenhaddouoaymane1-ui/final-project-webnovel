"""Shared fixtures for the CineOS test suite."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import AsyncGenerator

import asyncpg
import httpx
import pytest
import pytest_asyncio

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://cineos:cineos@localhost:5432/cineos",
)
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
API_BASE_URL = os.getenv("TEST_API_BASE_URL", "http://localhost:8000")


# ── Database pool ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Create a connection pool to the test database and tear down after tests."""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("SET search_path TO cineos_core, cineos_memory, cineos_gen, cineos_quality, cineos_exec, cineos_audit, cineos_config, public")
    yield pool
    await pool.close()


# ── Redis ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def redis_client():
    """Create a Redis connection for tests, flush test DB, and clean up."""
    try:
        import redis.asyncio as aioredis
    except ImportError:
        pytest.skip("redis package not installed")

    client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


# ── HTTP client ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an httpx async client pointed at the API."""
    async with httpx.AsyncClient(
        base_url=API_BASE_URL,
        timeout=30.0,
        headers={"X-API-Key": os.getenv("TEST_API_KEY", "test-key-123")},
    ) as client:
        yield client


# ── Helper: run raw SQL ────────────────────────────────────────────


@pytest_asyncio.fixture
async def run_sql(db_pool: asyncpg.Pool):
    """Return a helper that executes raw SQL and returns fetch results."""

    async def _run(sql: str, *args):
        async with db_pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    return _run


# ── Test project ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_project(db_pool: asyncpg.Pool) -> uuid.UUID:
    """Insert a minimal project and return its UUID. Cleans up afterwards."""
    project_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.projects
                (project_id, user_id, chat_id, title, current_state, language)
            VALUES ($1, $2, $3, $4, 'received', 'en')
            """,
            project_id,
            12345,          # fake user_id
            67890,          # fake chat_id
            "Test Novel",
        )
    yield project_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.projects WHERE project_id = $1", project_id
        )


# ── Test novel ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_novel(db_pool: asyncpg.Pool, test_project: uuid.UUID) -> uuid.UUID:
    """Insert a novel linked to the test project."""
    novel_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.novels
                (novel_id, project_id, title, raw_text, cleaned_text,
                 word_count, char_count, encoding, language)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'utf-8', 'en')
            """,
            novel_id,
            test_project,
            "Test Novel",
            "Once upon a time ...",
            "Once upon a time ...",
            4,
            22,
        )
    yield novel_id
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM cineos_core.novels WHERE novel_id = $1", novel_id)


# ── Test chapter ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_chapter(
    db_pool: asyncpg.Pool, test_project: uuid.UUID, test_novel: uuid.UUID
) -> uuid.UUID:
    """Insert a chapter linked to the test novel."""
    chapter_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.chapters
                (chapter_id, novel_id, project_id, chapter_number, title,
                 summary, text, word_count, scene_count)
            VALUES ($1, $2, $3, 1, 'Chapter One', 'Intro', 'Text here', 100, 0)
            """,
            chapter_id,
            test_novel,
            test_project,
        )
    yield chapter_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.chapters WHERE chapter_id = $1", chapter_id
        )


# ── Test scene ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_scene(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_chapter: uuid.UUID,
) -> uuid.UUID:
    """Insert a scene linked to the test project and chapter."""
    scene_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.scenes
                (scene_id, project_id, chapter_id, chapter_number, scene_number,
                 state, full_text, summary, importance, has_dialogue)
            VALUES ($1, $2, $3, 1, 1, 'pending', 'Scene text here.', 'A summary',
                    'high', true)
            """,
            scene_id,
            test_project,
            test_chapter,
        )
    yield scene_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.scene_characters WHERE scene_id = $1", scene_id
        )
        await conn.execute(
            "DELETE FROM cineos_core.scenes WHERE scene_id = $1", scene_id
        )


# ── Test shot ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_shot(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_scene: uuid.UUID,
) -> uuid.UUID:
    """Insert a shot linked to the test scene."""
    shot_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.shots
                (shot_id, scene_id, project_id, chapter_number, scene_number,
                 shot_number, state, shot_type, importance, duration_seconds,
                 positive_prompt, negative_prompt)
            VALUES ($1, $2, $3, 1, 1, 1, 'pending', 'medium', 'high',
                    5.0, 'A cinematic shot of a forest', 'blurry, low quality')
            """,
            shot_id,
            test_scene,
            test_project,
        )
    yield shot_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.shots WHERE shot_id = $1", shot_id
        )


# ── Test character ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_character(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
) -> uuid.UUID:
    """Insert a character with extensive fields."""
    char_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.characters
                (character_id, project_id, canonical_name, role, gender,
                 estimated_age, eye_color, hair_color, skin_tone,
                 height, build, face_shape, voice_description,
                 confidence_score, visual_prompt_positive, visual_prompt_negative)
            VALUES ($1, $2, 'Elara', 'protagonist', 'female',
                    '25', 'blue', 'auburn', 'fair', '5ft 8in', 'athletic',
                    'oval', 'warm and melodic', 0.92,
                    'beautiful woman with auburn hair and blue eyes',
                    'ugly, deformed')
            """,
            char_id,
            test_project,
        )
    yield char_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.scene_characters WHERE character_id = $1",
            char_id,
        )
        await conn.execute(
            "DELETE FROM cineos_core.characters WHERE character_id = $1", char_id
        )


# ── Test location ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_location(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
) -> uuid.UUID:
    """Insert a location."""
    location_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.locations
                (location_id, project_id, name, location_type, description,
                 atmosphere, mood, architecture_style, lighting_default,
                 visual_atmosphere)
            VALUES ($1, $2, 'Enchanted Forest', 'outdoor',
                    'A mystical woodland', 'mysterious', 'dark',
                    'organic', 'dappled', 'ethereal glow')
            """,
            location_id,
            test_project,
        )
    yield location_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_core.locations WHERE location_id = $1", location_id
        )


# ── Test worker ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_worker(
    db_pool: asyncpg.Pool,
) -> uuid.UUID:
    """Insert a worker and return its UUID."""
    worker_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_exec.workers
                (worker_id, worker_name, worker_type, state, host, port,
                 supported_task_types, enabled, health_status)
            VALUES ($1, 'test-image-worker', 'image_generation', 'idle',
                    'localhost', 8001, ARRAY['image_generate'], true, 'healthy')
            """,
            worker_id,
        )
    yield worker_id
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


# ── Test job ───────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_job(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_worker: uuid.UUID,
) -> uuid.UUID:
    """Insert a pending job and return its UUID."""
    job_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_exec.jobs
                (job_id, project_id, job_type, state, worker_id,
                 priority, payload, timeout_ms)
            VALUES ($1, $2, 'image_generate', 'pending', $3,
                    5, $4::jsonb, 300000)
            """,
            job_id,
            test_project,
            test_worker,
            json.dumps({"shot_id": str(uuid.uuid4()), "variant": 1}),
        )
    yield job_id
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id)
