# CineOS API Guide

CineOS exposes a REST API at `http://localhost:8000` for worker management, job scheduling, content generation, quality control, and webhook integrations. The full specification is in `api/openapi.yaml`.

## Authentication

### Bearer Token

All endpoints under `/api/` require a Bearer token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_API_TOKEN" http://localhost:8000/api/workers
```

### Webhook HMAC

Webhook endpoints (`/webhook/`) use shared-secret HMAC verification. The secret is configured via `N8N_ENCRYPTION_KEY` in your `.env` file.

### Health Endpoints

Health endpoints (`/health/`) are unauthenticated:

```bash
curl http://localhost:8000/health
```

## Rate Limits

| Endpoint Category | Rate Limit |
|-------------------|------------|
| Image generation | 30 requests/minute per worker |
| Voice generation | 60 requests/minute per worker |
| Job creation | 100 requests/minute per project |
| All other endpoints | 200 requests/minute per worker |

## API Reference

### Health Check

```http
GET /health
GET /health/ready
GET /health/live
```

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "services": {
    "database": "connected",
    "redis": "connected",
    "workers": {
      "image_worker": "online",
      "quality_worker": "online",
      "render_worker": "online",
      "voice_worker": "online",
      "animation_worker": "online"
    }
  }
}
```

### Workers

#### List Workers

```http
GET /api/workers
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| type | string | — | Filter by worker type |
| status | string | — | Filter by status |
| limit | integer | 50 | Max results |
| offset | integer | 0 | Pagination offset |

**Response:**

```json
{
  "total": 3,
  "offset": 0,
  "limit": 50,
  "workers": [
    {
      "worker_id": "wk-01H8X9A3B",
      "worker_type": "image_worker",
      "hostname": "gpu-node-01",
      "status": "online",
      "capabilities": ["image_generation", "upscaling"],
      "max_concurrent_jobs": 4,
      "current_job_count": 1,
      "last_heartbeat": "2026-07-26T10:15:30Z",
      "registered_at": "2026-07-26T08:00:00Z",
      "metadata": {
        "gpu_model": "NVIDIA RTX 4090",
        "gpu_vram_gb": 24
      }
    }
  ]
}
```

#### Get Worker

```http
GET /api/workers/:worker_id
```

#### Register Worker

```http
POST /api/workers
Content-Type: application/json

{
  "worker_name": "gpu-worker-01",
  "worker_type": "image_worker",
  "host": "192.168.1.100",
  "port": 8100,
  "supported_backends": ["comfyui", "pollinations"],
  "supported_task_types": ["image_generation", "super_resolution"],
  "gpu_model": "NVIDIA RTX 4090",
  "gpu_vram_gb": 24,
  "max_concurrent_tasks": 2
}
```

#### Update Worker Heartbeat

```http
PATCH /api/workers/:worker_id/heartbeat
Content-Type: application/json

{
  "current_load": 0.45,
  "gpu_memory_used_mb": 6200,
  "cpu_usage_percent": 35.2,
  "ram_usage_percent": 62.1
}
```

#### Deregister Worker

```http
DELETE /api/workers/:worker_id
```

### Jobs

#### List Jobs

```http
GET /api/jobs
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| project_id | uuid | Filter by project |
| state | string | Filter by state (pending, queued, running, completed, failed) |
| type | string | Filter by job type |
| limit | integer | Max results (default 50) |

**Response:**

```json
{
  "total": 12,
  "jobs": [
    {
      "job_id": "a1b2c3d4-...",
      "project_id": "...",
      "job_type": "image_generation",
      "state": "pending",
      "priority": 5,
      "payload": {
        "shot_id": "...",
        "prompt": "A medieval castle...",
        "width": 1920,
        "height": 1080
      },
      "created_at": "2026-07-26T12:00:00Z"
    }
  ]
}
```

#### Create Job

```http
POST /api/jobs
Content-Type: application/json

{
  "project_id": "project-uuid",
  "job_type": "image_generation",
  "priority": 5,
  "payload": {
    "shot_id": "shot-uuid",
    "prompt": "A medieval castle at sunset...",
    "negative_prompt": "blurry, low quality",
    "width": 1920,
    "height": 1080,
    "steps": 30,
    "cfg_scale": 7.5
  },
  "timeout_ms": 300000,
  "max_retries": 3
}
```

**Response:**

```json
{
  "job_id": "new-job-uuid",
  "state": "queued",
  "created_at": "2026-07-26T12:00:00Z"
}
```

#### Get Job Status

```http
GET /api/jobs/:job_id
```

#### Cancel Job

```http
POST /api/jobs/:job_id/cancel
```

### Image Generation

#### Generate Image

```http
POST /api/generate/image
Content-Type: application/json

{
  "shot_id": "shot-uuid",
  "prompt": "A medieval castle at sunset, cinematic lighting, detailed architecture",
  "negative_prompt": "blurry, low quality, deformed",
  "width": 1920,
  "height": 1080,
  "steps": 30,
  "cfg_scale": 7.5,
  "sampler": "euler_a",
  "seed": 42,
  "backend": "local_gpu",
  "model": "flux.1-dev",
  "variants": 2
}
```

**Response:**

```json
{
  "job_id": "job-uuid",
  "state": "queued",
  "estimated_time_seconds": 45,
  "variants": 2
}
```

#### Get Image Status

```http
GET /api/generate/image/:image_id
```

#### Upscale Image

```http
POST /api/generate/upscale
Content-Type: application/json

{
  "image_id": "image-uuid",
  "scale": 2,
  "model": "RealESRGAN_x4plus_anime_6B"
}
```

### Voice Generation

#### Generate Speech

```http
POST /api/generate/voice
Content-Type: application/json

{
  "shot_id": "shot-uuid",
  "text": "The castle stood tall against the setting sun...",
  "voice": "en-US-AriaNeural",
  "emotion": "neutral",
  "speed": 1.0,
  "pitch": 0.0,
  "backend": "edge_tts"
}
```

**Response:**

```json
{
  "job_id": "job-uuid",
  "state": "queued",
  "estimated_time_seconds": 10
}
```

### Animation

#### Animate Image

```http
POST /api/generate/animation
Content-Type: application/json

{
  "image_id": "image-uuid",
  "shot_id": "shot-uuid",
  "animation_type": "ken_burns",
  "duration_seconds": 5.0,
  "intensity": 0.6,
  "params": {
    "zoom_start": 1.0,
    "zoom_end": 1.2,
    "pan_direction": "right"
  }
}
```

### Quality

#### Review Asset

```http
POST /api/quality/review
Content-Type: application/json

{
  "project_id": "project-uuid",
  "entity_type": "image",
  "entity_id": "image-uuid",
  "review_type": "full_review"
}
```

**Response:**

```json
{
  "review_id": "review-uuid",
  "overall_score": 0.85,
  "passed": true,
  "decision": "approved",
  "scores": {
    "technical_quality": 0.90,
    "prompt_alignment": 0.88,
    "character_consistency": 0.82,
    "world_consistency": 0.80,
    "composition": 0.85
  },
  "issues": [],
  "recommendations": []
}
```

#### Get Review

```http
GET /api/quality/review/:review_id
```

#### List Reviews for Project

```http
GET /api/quality/reviews?project_id=project-uuid
```

### Webhooks

#### Telegram Intake

```http
POST /webhook/telegram_intake
Content-Type: application/json

{
  "update_id": 123456,
  "message": {
    "from": {"id": 123456789, "first_name": "User"},
    "chat": {"id": 123456789},
    "document": {
      "file_id": "file-id-from-telegram",
      "file_name": "my_novel.txt",
      "file_size": 1024000
    }
  }
}
```

#### n8n State Callback

```http
POST /webhook/state_callback
Content-Type: application/json

{
  "project_id": "project-uuid",
  "workflow_name": "003_story_parser",
  "new_state": "parsed",
  "result_data": {
    "chapter_count": 12,
    "scene_count": 48
  }
}
```

#### Worker Callback

```http
POST /webhook/worker_callback
Content-Type: application/json

{
  "job_id": "job-uuid",
  "worker_id": "worker-uuid",
  "state": "completed",
  "result": {
    "image_path": "/data/generated/images/img-001.png",
    "quality_score": 0.87,
    "generation_time_ms": 12500
  }
}
```

## Error Handling

### Error Response Format

All errors follow this format:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Worker with ID 'wk-123' not found",
    "details": {
      "resource_type": "worker",
      "resource_id": "wk-123"
    }
  },
  "timestamp": "2026-07-26T12:00:00Z",
  "request_id": "req-uuid"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (e.g., after delete) |
| 400 | Bad Request — invalid parameters |
| 401 | Unauthorized — missing or invalid token |
| 404 | Resource Not Found |
| 409 | Conflict — resource already exists |
| 422 | Unprocessable Entity — validation failed |
| 429 | Too Many Requests — rate limit exceeded |
| 500 | Internal Server Error |
| 503 | Service Unavailable — worker offline |

### Common Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| `WORKER_OFFLINE` | Requested worker is not responding | Check worker health, restart if needed |
| `JOB_TIMEOUT` | Job exceeded timeout limit | Increase timeout or optimize worker |
| `QUALITY_THRESHOLD_NOT_MET` | Asset failed quality review | Retry with different parameters |
| `INVALID_STATE_TRANSITION` | Cannot move project to requested state | Check current project state |
| `RATE_LIMITED` | Too many requests | Wait and retry |

## Client Examples

### cURL

```bash
# List workers
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/workers

# Create a job
curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"...","job_type":"image_generation","payload":{...}}' \
     http://localhost:8000/api/jobs

# Check health
curl http://localhost:8000/health
```

### Python

```python
import requests

API_BASE = "http://localhost:8000"
TOKEN = "your_api_token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# List workers
resp = requests.get(f"{API_BASE}/api/workers", headers=HEADERS)
workers = resp.json()["workers"]

# Create a job
resp = requests.post(f"{API_BASE}/api/jobs", headers=HEADERS, json={
    "project_id": "project-uuid",
    "job_type": "image_generation",
    "payload": {"prompt": "A castle at sunset", "width": 1920, "height": 1080}
})
job = resp.json()

# Poll for completion
import time
while True:
    resp = requests.get(f"{API_BASE}/api/jobs/{job['job_id']}", headers=HEADERS)
    if resp.json()["state"] in ("completed", "failed"):
        break
    time.sleep(5)
```

## OpenAPI Specification

The full OpenAPI 3.0 specification is at `api/openapi.yaml`. You can view it interactively:

```bash
# Using Swagger UI
docker run -p 8081:8080 -e SWAGGER_JSON=/api/openapi.yaml \
  -v $(pwd)/api:/api swaggerapi/swagger-ui

# Then open http://localhost:8081
```
