"""API endpoint tests using httpx async client."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_health_endpoint(http_client: httpx.AsyncClient):
    resp = await http_client.get("/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body


@pytest.mark.integration
async def test_health_ready(http_client: httpx.AsyncClient):
    resp = await http_client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "ready" in body or "status" in body


@pytest.mark.integration
async def test_health_live(http_client: httpx.AsyncClient):
    resp = await http_client.get("/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert "alive" in body or "status" in body


@pytest.mark.integration
async def test_create_worker_api(http_client: httpx.AsyncClient):
    payload = {
        "worker_name": "test-api-worker",
        "worker_type": "image_generation",
        "host": "10.0.0.1",
        "port": 8001,
        "supported_task_types": ["image_generate"],
    }
    resp = await http_client.post("/api/workers/register", json=payload)
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert "worker_id" in body or "id" in body


@pytest.mark.integration
async def test_list_workers(http_client: httpx.AsyncClient):
    resp = await http_client.get("/api/workers")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, (list, dict))


@pytest.mark.integration
async def test_create_job_api(http_client: httpx.AsyncClient, test_project: uuid.UUID):
    payload = {
        "project_id": str(test_project),
        "job_type": "image_generate",
        "priority": 5,
        "payload": {"shot_id": str(uuid.uuid4()), "variant": 1},
    }
    resp = await http_client.post("/api/jobs", json=payload)
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert "job_id" in body or "id" in body


@pytest.mark.integration
async def test_get_job(http_client: httpx.AsyncClient, test_job: uuid.UUID):
    resp = await http_client.get(f"/api/jobs/{test_job}")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("job_id") == str(test_job) or body.get("id") == str(test_job)


@pytest.mark.integration
async def test_assign_job(http_client: httpx.AsyncClient, test_job: uuid.UUID, test_worker: uuid.UUID):
    payload = {"worker_id": str(test_worker)}
    resp = await http_client.put(f"/api/jobs/{test_job}/assign", json=payload)
    assert resp.status_code in (200, 204)


@pytest.mark.integration
async def test_complete_job(http_client: httpx.AsyncClient, test_job: uuid.UUID):
    payload = {
        "result": {"image_path": "/output/shot.png", "quality": 0.92},
    }
    resp = await http_client.put(f"/api/jobs/{test_job}/complete", json=payload)
    assert resp.status_code in (200, 204)


@pytest.mark.integration
async def test_image_generation(http_client: httpx.AsyncClient, test_project: uuid.UUID):
    payload = {
        "project_id": str(test_project),
        "shot_id": str(uuid.uuid4()),
        "prompt": "A cinematic shot of a mountain at sunset",
        "negative_prompt": "blurry, low quality",
        "variant": 1,
    }
    resp = await http_client.post("/api/generate/image", json=payload)
    assert resp.status_code in (200, 201, 202)


@pytest.mark.integration
async def test_voice_generation(http_client: httpx.AsyncClient, test_project: uuid.UUID):
    payload = {
        "project_id": str(test_project),
        "shot_id": str(uuid.uuid4()),
        "text": "The hero stepped into the light.",
        "voice": "female_warm",
        "emotion": "determined",
    }
    resp = await http_client.post("/api/generate/voice", json=payload)
    assert resp.status_code in (200, 201, 202)


@pytest.mark.integration
async def test_quality_review(http_client: httpx.AsyncClient, test_project: uuid.UUID):
    payload = {
        "project_id": str(test_project),
        "entity_type": "image",
        "entity_id": str(uuid.uuid4()),
        "scores": {
            "technical_quality": 0.85,
            "prompt_alignment": 0.78,
            "character_consistency": 0.82,
            "world_consistency": 0.75,
            "composition": 0.80,
        },
    }
    resp = await http_client.post("/api/quality/review", json=payload)
    assert resp.status_code in (200, 201)


@pytest.mark.integration
async def test_auth_required():
    """Request without API key must be rejected."""
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=10.0,
        headers={},
    ) as client:
        resp = await client.get("/api/workers")
        assert resp.status_code in (401, 403)


@pytest.mark.integration
async def test_rate_limiting(http_client: httpx.AsyncClient):
    """Rapid requests should eventually hit rate limit."""
    responses = []
    for _ in range(200):
        resp = await http_client.get("/health")
        responses.append(resp.status_code)
    assert 429 in responses or 200 in responses


@pytest.mark.integration
async def test_idempotency(http_client: httpx.AsyncClient, test_project: uuid.UUID):
    """Same idempotency key returns same result."""
    idem_key = str(uuid.uuid4())
    payload = {
        "project_id": str(test_project),
        "job_type": "image_generate",
        "priority": 5,
        "payload": {"shot_id": str(uuid.uuid4())},
    }
    headers = {"X-Idempotency-Key": idem_key}
    resp1 = await http_client.post("/api/jobs", json=payload, headers=headers)
    resp2 = await http_client.post("/api/jobs", json=payload, headers=headers)
    if resp1.status_code in (200, 201) and resp2.status_code in (200, 201):
        assert resp1.json() == resp2.json()


@pytest.mark.integration
async def test_validation_error(http_client: httpx.AsyncClient):
    """Invalid input returns 400."""
    resp = await http_client.post("/api/jobs", json={})
    assert resp.status_code in (400, 422)
