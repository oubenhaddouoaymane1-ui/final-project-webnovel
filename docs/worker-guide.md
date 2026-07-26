# CineOS Worker Guide

Workers are Python services that handle heavy AI computation. They register with the supervisor, receive jobs, process them, and report results back through the database. This guide covers all worker types, adding new workers, scaling, GPU setup, and monitoring.

## Worker Types

| Worker | Port | Hardware | Tasks | Max Concurrent |
|--------|------|----------|-------|----------------|
| Supervisor | 8000 | CPU only | Worker management, job assignment, health checks | — |
| Image Worker | 8100 | GPU 8GB+ | Image generation (ComfyUI, Pollinations), upscaling (RealESRGAN) | 2 |
| Quality Worker | 8200 | GPU 4GB+ | Vision-based quality review, consistency checks | 4 |
| Render Worker | 8300 | CPU 4+ cores | FFmpeg video assembly, clip concatenation, subtitle burn-in | 2 |
| Voice Worker | 8400 | CPU 2+ cores | TTS narration (Kokoro, Edge-TTS, Piper) | 4 |
| Animation Worker | 8500 | GPU 4GB+ | Ken Burns effect, LivePortrait, simple motion animation | 2 |

## Worker Architecture

```
n8n Workflow
    ↓
cineos_exec.jobs (PostgreSQL)
    ↓
Supervisor assigns job to worker
    ↓
Worker processes job
    ↓
Worker writes result to PostgreSQL
    ↓
Worker updates job state to "completed"
    ↓
n8n triggers next workflow
```

All workers inherit from a common base class and follow the same lifecycle:

1. **Register** with the supervisor on startup
2. **Heartbeat** every 30 seconds
3. **Poll** for jobs via PostgreSQL
4. **Process** jobs and write results
5. **Report** completion/failure
6. **Health check** responds on `/health`

## Worker Details

### Supervisor (Port 8000)

The supervisor is the coordinator. It manages the worker pool and assigns jobs.

**Responsibilities:**
- Maintains worker registry in `cineos_exec.workers`
- Monitors worker heartbeats
- Assigns jobs from `cineos_exec.jobs` to available workers
- Handles worker failure and job reassignment
- Exposes the main REST API

**Configuration:** `config/workers.yaml`

```yaml
supervisor:
  host: "0.0.0.0"
  port: 9000
  heartbeat_interval_seconds: 30
  max_worker_idle_seconds: 300
  health_check_interval_seconds: 60
```

### Image Worker (Port 8100)

Generates images using AI backends.

**Supported Backends:**
- **ComfyUI** (local GPU) — Primary backend, uses FLUX model
- **Pollinations** (API) — Free cloud fallback, no GPU needed
- **HuggingFace Inference** — Optional paid backend

**Task Types:**
- `image_generation` — Create images from prompts
- `super_resolution` — Upscale images with RealESRGAN

**Job Payload:**

```json
{
  "shot_id": "uuid",
  "prompt": "A medieval castle at sunset...",
  "negative_prompt": "blurry, low quality",
  "width": 1920,
  "height": 1080,
  "steps": 30,
  "cfg_scale": 7.5,
  "sampler": "euler_a",
  "seed": 42,
  "backend": "local_gpu",
  "model": "flux.1-dev"
}
```

**Result:**

```json
{
  "image_path": "/data/generated/images/img-001.png",
  "width": 1920,
  "height": 1080,
  "seed": 42,
  "generation_time_ms": 12500
}
```

### Quality Worker (Port 8200)

Reviews generated assets using vision AI models.

**Supported Backends:**
- **LLaVA** (local) — Free, runs on GPU
- **GPT-4o Vision** (API) — Paid, highest quality

**Task Types:**
- `quality_review` — Full quality assessment
- `consistency_check` — Character/world consistency

**Checks Performed:**
- Technical quality (resolution, artifacts, blur)
- Prompt alignment (does image match prompt?)
- Character consistency (do characters look correct?)
- World consistency (does environment match?)
- Composition (rule of thirds, focal point)

### Render Worker (Port 8300)

Assembles video clips using FFmpeg.

**Task Types:**
- `video_render` — Render individual clips
- `clip_assembly` — Concatenate clips into final video

**Capabilities:**
- H.264/H.265 encoding
- Audio-video synchronization
- Subtitle overlay
- Transition effects
- Resolution scaling

### Voice Worker (Port 8400)

Generates text-to-speech narration.

**Supported Backends:**
- **Kokoro** (local) — High-quality, runs locally
- **Edge-TTS** (API) — Free, Microsoft voices
- **Piper** (local) — Lightweight alternative

**Task Type:**
- `tts_generation` — Generate audio from text

**Job Payload:**

```json
{
  "shot_id": "uuid",
  "text": "The castle stood tall against the setting sun...",
  "voice": "en-US-AriaNeural",
  "emotion": "neutral",
  "speed": 1.0,
  "pitch": 0.0,
  "backend": "edge_tts"
}
```

### Animation Worker (Port 8500)

Animates static images into video clips.

**Supported Backends:**
- **LivePortrait** (GPU) — High-quality face animation
- **Simple Motion** (CPU) — Ken Burns pan/zoom effects

**Task Type:**
- `image_animation` — Animate a still image
- `motion_transfer` — Apply motion from reference video

## Adding a New Worker

### 1. Create the Worker Directory

```bash
mkdir -p workers/my_worker
touch workers/my_worker/__init__.py
touch workers/my_worker/service.py
```

### 2. Implement the Service

Use the base worker class as a template:

```python
"""My custom worker service."""
import os
import logging
from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.my_worker")


class MyWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            worker_name="my_worker",
            worker_type="custom",
            port=8600,
            supported_task_types=["my_custom_task"],
        )

    async def process_job(self, job):
        """Process a single job."""
        payload = job["payload"]

        # Your processing logic here
        result = {"output_path": "/data/output/result.bin"}

        return result


if __name__ == "__main__":
    worker = MyWorker()
    worker.run()
```

### 3. Register with Supervisor

The worker must register itself on startup. The base class handles this automatically:

```python
class MyWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            worker_name="my_worker",
            worker_type="custom",
            port=8600,
            supported_task_types=["my_custom_task"],
            # Optional: hardware requirements
            required_hardware={"gpu": False, "min_ram_gb": 4},
        )
```

### 4. Add to Docker Compose

```yaml
# docker-compose.yml
my_worker:
  build:
    context: ./workers
    dockerfile: Dockerfile
  container_name: cineos-my-worker
  command: python -m workers.my_worker.service
  restart: unless-stopped
  ports:
    - "8600:8600"
  environment:
    SERVICE_NAME: my_worker
    POSTGRES_HOST: ${POSTGRES_HOST:-postgres}
    POSTGRES_PORT: ${POSTGRES_PORT:-5432}
    POSTGRES_DB: ${POSTGRES_DB:-cineos}
    POSTGRES_USER: ${POSTGRES_USER:-cineos}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme_in_production}
    REDIS_HOST: ${REDIS_HOST:-redis}
    REDIS_PORT: ${REDIS_PORT:-6379}
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
  depends_on:
    supervisor:
      condition: service_started
  networks:
    - cineos-network
```

### 5. Add Health Check Endpoint

Ensure your worker exposes a `/health` endpoint:

```python
@app.route("/health")
async def health():
    return {"status": "healthy", "worker": "my_worker"}
```

### 6. Update Supervisor Configuration

Add the new worker type to `config/workers.yaml`:

```yaml
worker_types:
  my_custom:
    count: 1
    max_concurrent: 2
    task_types: ["my_custom_task"]
    timeout_seconds: 300
    retry_max: 3
```

### 7. Test

```bash
docker compose up my_worker
docker compose logs -f my_worker
curl http://localhost:8600/health
```

## Scaling Workers

### Horizontal Scaling

Increase the number of worker instances:

```yaml
# docker-compose.yml
image_worker:
  deploy:
    replicas: 3  # Run 3 image workers
```

Or use `docker compose up --scale image_worker=3`.

### Vertical Scaling

Increase resources per worker:

```yaml
image_worker:
  deploy:
    resources:
      limits:
        memory: 16G
        cpus: "4"
```

### GPU Scaling

For multiple GPUs, run separate worker instances per GPU:

```yaml
image_worker_gpu0:
  environment:
    CUDA_VISIBLE_DEVICES: "0"
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ["0"]
            capabilities: [gpu]

image_worker_gpu1:
  environment:
    CUDA_VISIBLE_DEVICES: "1"
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ["1"]
            capabilities: [gpu]
```

### Scaling Recommendations

| Scenario | Recommendation |
|----------|----------------|
| Single novel | 1x image worker, 1x render worker |
| Multiple concurrent novels | 2-4x image workers |
| High quality requirements | 2x quality workers |
| Large novels (100k+ words) | 2x render workers |
| Multiple languages | 2x voice workers |

## GPU Setup

### Prerequisites

1. NVIDIA GPU with 8GB+ VRAM (recommended)
2. NVIDIA drivers installed on host
3. NVIDIA Container Toolkit installed

### Verify GPU Access

```bash
# Check host GPU
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Configure GPU in Docker Compose

```yaml
image_worker:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ["0"]
            capabilities: [gpu]
```

### GPU Memory Management

- Image Worker: 8GB+ VRAM recommended for FLUX
- Quality Worker: 4GB+ VRAM for LLaVA
- Animation Worker: 4GB+ VRAM for LivePortrait

Monitor GPU usage:

```bash
nvidia-smi
watch -n 1 nvidia-smi
```

## Monitoring

### Health Checks

```bash
# Individual worker
curl http://localhost:8100/health

# All workers via supervisor
curl http://localhost:8000/api/workers | python -m json.tool

# Quick check all
make health
```

### Worker Status in Database

```sql
-- All workers and their status
SELECT worker_name, worker_type, state, last_heartbeat, current_load
FROM cineos_exec.workers
ORDER BY worker_type;

-- Workers that haven't heartbeated recently
SELECT worker_name, last_heartbeat,
       NOW() - last_heartbeat as time_since_heartbeat
FROM cineos_exec.workers
WHERE last_heartbeat < NOW() - INTERVAL '2 minutes';
```

### Job Monitoring

```sql
-- Jobs by state
SELECT state, COUNT(*) as count
FROM cineos_exec.jobs
GROUP BY state;

-- Recent failed jobs
SELECT job_type, error_message, created_at
FROM cineos_exec.jobs
WHERE state = 'failed'
ORDER BY created_at DESC LIMIT 10;

-- Job duration statistics
SELECT
    job_type,
    COUNT(*) as completed,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_seconds,
    MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_seconds
FROM cineos_exec.jobs
WHERE state = 'completed'
GROUP BY job_type;
```

### Worker Logs

```bash
# Real-time logs
docker compose logs -f image_worker
docker compose logs -f quality_worker

# Recent errors
docker compose logs --tail=100 image_worker 2>&1 | grep -i error
```

### Metrics (with Monitoring Stack)

If using the monitoring stack (`docker/monitoring/`):

- **Prometheus** collects metrics from workers
- **Grafana** dashboards visualize worker health

Access Grafana at `http://localhost:3000` (default credentials: admin/admin).

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Worker won't register | Check supervisor is running and PostgreSQL is reachable |
| Jobs stay in "pending" | Verify worker supports the job_type, check worker is idle |
| Worker runs out of memory | Increase memory limit or reduce batch size |
| GPU not detected | Verify NVIDIA Container Toolkit, check `nvidia-smi` |
| Jobs timeout | Increase `timeout_ms` in job payload or `timeout_seconds` in config |
| Worker crashes on startup | Check logs for import errors, verify Python dependencies |
| Stale heartbeats | Worker may be stuck — restart it with `docker compose restart <worker>` |
