# CineOS Deployment Guide

Complete guide for deploying the CineOS cloud-first architecture. Heavy AI runs on free cloud services — your local machine only needs Docker.

---

## 1. System Requirements

### Minimum (Cloud-First Mode)

| Component | Requirement | Notes |
|-----------|-------------|-------|
| CPU | Any dual-core | ARM, x86, all work |
| RAM | 4 GB | 8 GB recommended for smooth n8n + Postgres |
| GPU | None | All GPU work runs on cloud |
| Storage | 20 GB free | For Docker images + generated files |
| Network | Broadband | Cloud API calls require internet |

### What Runs Locally vs. Cloud

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR PC (4GB RAM OK)                     │
│                                                              │
│  ┌──────────┐  ┌───────┐  ┌──────┐  ┌──────────────────┐   │
│  │  n8n     │  │Redis  │  │Postgr│  │  Telegram Bot    │   │
│  │ orchestr.│  │queue  │  │eSQL  │  │  (Python)        │   │
│  └────┬─────┘  └───────┘  └──────┘  └──────────────────┘   │
│       │                                                      │
│  ┌────▼─────┐  ┌───────────────┐                            │
│  │Supervisor│  │Render Worker  │  (CPU-only, lightweight)   │
│  │(job mgmt)│  │(FFmpeg assembly)│                          │
│  └──────────┘  └───────────────┘                            │
│       │                                                      │
│  ┌────▼──────────────────────────────────────────────┐      │
│  │           Voice Worker (Edge-TTS cloud API)       │      │
│  └───────────────────────────────────────────────────┘      │
└──────────────────────────┬──────────────────────────────────┘
                           │  internet
        ┌──────────────────┼──────────────────────┐
        │                  │                      │
┌───────▼────────┐ ┌──────▼────────┐ ┌───────────▼──────────┐
│  OpenRouter    │ │ HuggingFace   │ │ Google Colab         │
│  (free LLM)   │ │ (free image)  │ │ (free GPU — optional) │
│  Vision/Chat   │ │ Inference API │ │ ComfyUI + FLUX       │
└────────────────┘ └───────────────┘ └──────────────────────┘
        │
┌───────▼────────┐
│  Pollinations  │
│  (free images) │
│  no signup     │
└────────────────┘
```

### What Each Service Does

| Local Service | Resource Use | Purpose |
|---------------|-------------|---------|
| PostgreSQL 16 | ~200 MB RAM | State machine, all data |
| Redis 7 | ~50 MB RAM | Caching, job queue |
| n8n | ~300 MB RAM | Workflow orchestration |
| Supervisor | ~100 MB RAM | Worker/job management |
| Render Worker | ~150 MB RAM | FFmpeg video assembly |
| Voice Worker | ~50 MB RAM | Edge-TTS (free cloud API) |
| Telegram Bot | ~80 MB RAM | User interface |
| **Total** | **~1 GB RAM** | Leaves room for OS on 4 GB machine |

---

## 2. Step-by-Step Deployment

### Step 1: Clone and Configure

```bash
git clone <repository-url>
cd cinematic-production-os
cp .env.example .env
```

Edit `.env` with a text editor. At minimum, set:

```env
# Required
TELEGRAM_BOT_TOKEN=your_token_here

# Security (generate random strings)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
N8N_BASIC_AUTH_PASSWORD=$(openssl rand -hex 12)
N8N_ENCRYPTION_KEY=$(openssl rand -hex 16)
```

### Step 2: Start Docker Compose (Local Services Only)

```bash
docker compose up -d
```

Wait for all services to become healthy:

```bash
docker compose ps
```

Expected output:

```
NAME                STATUS          PORTS
cineos-postgres     Up (healthy)    0.0.0.0:5432->5432/tcp
cineos-redis        Up (healthy)    0.0.0.0:6379->6379/tcp
cineos-n8n          Up (healthy)    0.0.0.0:5678->5678/tcp
cineos-supervisor   Up              0.0.0.0:8000->8000/tcp
cineos-render       Up              0.0.0.0:8300->8300/tcp
cineos-voice        Up              0.0.0.0:8400->8400/tcp
cineos-telegram     Up
```

Verify health:

```bash
make health
```

### Step 3: Set Up Free Cloud Accounts

CineOS dispatches heavy AI work to free cloud APIs. You need at least one image generation backend and one LLM backend.

**Option A: Minimum Viable (no accounts needed)**

- **Pollinations**: Free image generation, no signup required. Already enabled by default (`POLLINATIONS_ENABLED=true`).
- **Edge-TTS**: Free TTS via Microsoft, no signup. Already configured in the Voice Worker.

With just these two, you can generate images and narration. LLM analysis will use rule-based fallbacks (lower quality but functional).

**Option B: Full Quality (free accounts)**

1. **OpenRouter** — Free LLM access (analysis, quality review, prompt building)
2. **HuggingFace** — Free image generation via Inference API

**Option C: Maximum Quality (add GPU)**

1. **Google Colab** — Free T4/A100 GPU for ComfyUI + FLUX

Proceed to Section 3 for detailed cloud service setup.

### Step 4: Import n8n Workflows

```bash
# Import all 25+ workflows into n8n
python scripts/setup_n8n.py

# Or import manually via n8n UI:
# Open http://localhost:5678
# Go to Workflows → Import from File
# Select each JSON file from n8n-workflows/
```

### Step 5: Start the Telegram Bot

The Telegram bot starts automatically with Docker Compose. Verify it's connected:

```
1. Open Telegram
2. Find your bot by its username
3. Send /start
4. You should receive a welcome message
```

### Step 6: Send Your First Novel

1. Send a `.txt` file containing a novel (50–500,000 words)
2. The bot acknowledges receipt and begins processing
3. Send `/status` to check progress at any time

---

## 3. Cloud Service Setup Guides

### 3.1 OpenRouter — Free LLM Access

OpenRouter provides access to multiple LLMs (Llama 3, Mistral, Gemma) with a generous free tier.

**Sign Up:**

1. Go to https://openrouter.ai
2. Click "Sign In" (Google, GitHub, or email)
3. Navigate to https://openrouter.ai/keys
4. Click "Create Key"
5. Copy the key (starts with `sk-or-v1-...`)

**Configure CineOS:**

```env
OPENROUTER_API_KEY=sk-or-v1-your_key_here
```

**Free Tier Limits:**

| Model | Free Limit | Speed | Quality |
|-------|-----------|-------|---------|
| meta-llama/llama-3.1-8b-instruct | Unlimited | Fast | Good |
| mistralai/mistral-7b-instruct | Unlimited | Fast | Good |
| google/gemma-2-9b-it | Unlimited | Fast | Good |
| meta-llama/llama-3.1-70b-instruct | ~200 req/day | Medium | Excellent |

**What CineOS Uses It For:**

- Story analysis (chapter/scene extraction)
- Character DNA extraction
- World bible building
- Shot planning
- Quality review (vision models via `/v1/chat/completions`)
- Prompt generation
- Repair strategy selection

### 3.2 HuggingFace — Free Image Generation

HuggingFace Inference API provides free access to FLUX, Stable Diffusion, and other models.

**Sign Up:**

1. Go to https://huggingface.co
2. Create an account
3. Go to https://huggingface.co/settings/tokens
4. Click "New token" → type "read" → Generate
5. Copy the token (starts with `hf_...`)

**Configure CineOS:**

```env
HF_API_KEY=hf_your_token_here
```

**Free Tier Limits:**

| Model | Rate Limit | Resolution | Quality |
|-------|-----------|------------|---------|
| FLUX.1-schnell | 3 req/min | 1024x1024 | High |
| stable-diffusion-xl-base-1.0 | 3 req/min | 1024x1024 | Good |
| stable-diffusion-2.1 | 3 req/min | 768x768 | Good |

**What CineOS Uses It For:**

- Character reference image generation
- Scene/shot image generation
- World reference images
- Repair regeneration (when local GPU unavailable)

### 3.3 Google Colab — Free GPU (Optional)

Google Colab provides free T4 or A100 GPUs for running ComfyUI + FLUX. This is optional but produces the highest quality images.

**Prerequisites:**

- Google account
- The CineOS Colab notebook (provided in the repo)

**Quick Setup:**

1. Open https://colab.research.google.com
2. Upload the notebook from `notebooks/comfyui_flux.ipynb`
3. Set runtime type: Runtime → Change runtime type → T4 GPU
4. Run all cells
5. Copy the ngrok URL when prompted
6. Set in `.env`:

```env
COLAB_COMFYUI_ENDPOINT=https://your-ngrok-url.ngrok-free.app
```

See [Colab Setup Guide](colab-setup-guide.md) for detailed instructions including auto-shutdown configuration.

### 3.4 Pollinations — Zero-Config Image Generation

Pollinations provides completely free image generation with no signup, no API key, and no rate limits.

**Setup:** Already enabled. No action needed.

```env
POLLINATIONS_ENABLED=true
```

**Limits:**

- Resolution: Up to 1024x1024
- Speed: 10-30 seconds per image
- Models: Pollinations proprietary (SDXL-based)
- Rate: No hard limit, but be reasonable

**What CineOS Uses It For:**

- Fallback image generation when other backends fail
- Default image generation when no local GPU or Colab available
- Background/establishing shot generation
- Quick prototyping and testing

---

## 4. How n8n Dispatches to Cloud Services

### The Dispatch Flow

```
n8n Workflow (e.g., 017_image_generation)
    │
    ├── Read shot record from PostgreSQL
    │   SELECT * FROM cineos.core.shots WHERE id = $shot_id
    │
    ├── Read backend priority from config
    │   SELECT value FROM cineos.config.system_config
    │   WHERE key = 'generation.default_image_backend_priority'
    │   -- ["local_gpu", "hf_inference", "pollinations"]
    │
    ├── Try backend #1 (local GPU)
    │   ├── POST to Colab endpoint or local ComfyUI
    │   ├── If success → save image, update shot state
    │   └── If fail → try next backend
    │
    ├── Try backend #2 (HuggingFace)
    │   ├── POST https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell
    │   ├── Headers: Authorization: Bearer hf_xxx
    │   ├── Body: { "inputs": "..." }
    │   ├── If success → save image
    │   └── If fail → try next backend
    │
    ├── Try backend #3 (Pollinations)
    │   ├── GET https://image.pollinations.ai/prompt/{encoded_prompt}
    │   ├── Download the generated image
    │   └── Save image
    │
    └── Update shot state in PostgreSQL
        UPDATE cineos.core.shots
        SET state = 'image_generated'
        WHERE id = $shot_id
```

### LLM Dispatch (Analysis Workflows)

```
n8n Workflow (e.g., 005_story_intelligence)
    │
    ├── Check OPENROUTER_API_KEY is set
    │
    ├── If set → Use OpenRouter
    │   ├── POST https://openrouter.ai/api/v1/chat/completions
    │   ├── Headers: Authorization: Bearer sk-or-v1-xxx
    │   ├── Body: { model: "meta-llama/llama-3.1-8b-instruct", messages: [...] }
    │   └── Parse JSON response
    │
    └── If not set → Use rule-based fallback
        ├── Regex chapter splitting
        ├── Pattern-based character extraction
        └── Template-based scene segmentation
```

---

## 5. How Results Flow Back

### Image Generation Result Flow

```
Cloud API returns image
    │
    ▼
n8n HTTP Request node receives binary data
    │
    ├── Save to disk: ./generated/images/{project_id}/{shot_id}.png
    │
    ├── INSERT INTO cineos.generation.images
    │   (shot_id, project_id, image_path, prompt_used, backend_used, ...)
    │
    ├── UPDATE cineos.core.shots
    │   SET state = 'image_generated', image_id = $new_image_id
    │
    ├── Trigger quality review workflow (018_quality_ai)
    │   ├── Send image to vision model (OpenRouter or local)
    │   ├── Score: composition, character consistency, prompt alignment
    │   ├── INSERT INTO cineos.quality.reviews
    │   └── If score >= threshold → state = 'image_passed'
    │       If score < threshold  → state = 'image_failed' → repair workflow
    │
    └── Notify Telegram of progress
        └── "Image 45/120 generated (37.5%)"
```

### Complete Pipeline Progression

```
Novel received
  → n8n extracts chapters/scenes (LLM via OpenRouter)
  → n8n builds bibles (LLM via OpenRouter)
  → n8n plans shots (LLM via OpenRouter)
  → n8n generates prompts (LLM via OpenRouter)
  → n8n dispatches image generation:
      → Colab ComfyUI (highest quality) OR
      → HuggingFace Inference (good quality) OR
      → Pollinations (decent quality)
  → n8n quality-reviews images (vision LLM via OpenRouter)
  → n8n generates TTS (Edge-TTS cloud, free)
  → Render Worker assembles video (local FFmpeg)
  → n8n delivers via Telegram
```

---

## 6. Monitoring Cloud Workers

### Check Cloud Service Health

```bash
# OpenRouter — test LLM access
curl -s https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/llama-3.1-8b-instruct","messages":[{"role":"user","content":"Hello"}]}'

# HuggingFace — test image generation
curl -s https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell \
  -H "Authorization: Bearer $HF_API_KEY" \
  -d '{"inputs":"a red cat"}' \
  --output /dev/null -w "HTTP %{http_code}, size %{size_download}\n"

# Pollinations — test image generation
curl -s "https://image.pollinations.ai/prompt/a%20red%20cat" \
  -o /dev/null -w "HTTP %{http_code}, size %{size_download}\n"

# Colab ComfyUI — test endpoint (if set)
curl -s $COLAB_COMFYUI_ENDPOINT/health
```

### Monitor via n8n

Open `http://localhost:5678` in your browser:

1. **Executions** tab → see all workflow runs, their status, and errors
2. **Workflows** tab → see individual workflow health
3. Filter by "Error" to find failed cloud calls

### Monitor via Database

```sql
-- Recent image generations and which backend succeeded
SELECT backend_used, COUNT(*) as count,
       AVG(generation_time_ms) as avg_ms
FROM cineos.generation.images
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY backend_used;

-- Failed generations (need repair or fallback)
SELECT shot_id, backend_used, rejection_reason
FROM cineos.generation.images
WHERE state = 'rejected'
ORDER BY created_at DESC LIMIT 10;

-- Cloud API errors in the last hour
SELECT event_type, message, details
FROM cineos.audit.events
WHERE created_at > NOW() - INTERVAL '1 hour'
AND event_type = 'error'
ORDER BY created_at DESC;
```

### Monitor via Telegram

Send these commands to your bot:

| Command | What It Shows |
|---------|--------------|
| `/status` | Current project progress, current phase |
| `/help` | Available commands |

---

## 7. Cost Analysis

### Monthly Cost at Moderate Usage

Moderate usage = 2-3 novels per month, ~50k words each.

| Service | Free Tier | Monthly Usage | Cost |
|---------|-----------|---------------|------|
| OpenRouter (LLM) | Unlimited (8B models) | ~10,000 requests | $0 |
| HuggingFace (images) | 3 req/min | ~2,000 images | $0 |
| Pollinations (images) | Unlimited | ~1,000 images | $0 |
| Google Colab (GPU) | ~12h/day free T4 | ~20 hours | $0 |
| Edge-TTS (voice) | Unlimited | ~500 audio clips | $0 |
| Docker/Postgres/Redis/n8n | Open source | Self-hosted | $0 |
| Electricity | — | ~50W average | ~$3 |
| **Total** | | | **~$3/month** |

### Cost at Heavy Usage

Heavy usage = 10+ novels per month, 100k+ words each.

| Service | Monthly Usage | Cost |
|---------|---------------|------|
| OpenRouter (8B) | Unlimited | $0 |
| OpenRouter (70B) | ~2,000 requests | ~$5 |
| HuggingFace | Rate-limited (queue) | $0 |
| Google Colab Pro (optional) | 100 hours | $10 |
| Edge-TTS | Unlimited | $0 |
| **Total** | | **$5-15/month** |

### Why This Works

- **LLM analysis**: 8B models are free on OpenRouter and fast enough for structured extraction
- **Image generation**: HuggingFace + Pollinations cover most needs for free
- **TTS**: Edge-TTS uses Microsoft's free API, no usage limits
- **Video assembly**: FFmpeg runs locally on CPU, no cost
- **Orchestration**: n8n Community Edition is free and self-hosted
- **Database**: PostgreSQL is free and runs locally

---

## 8. Cloud Provider Deployment

Beyond local Docker Compose, CineOS can deploy to managed cloud platforms. All options use the same lightweight containers — heavy AI still runs on free cloud APIs (Pollinations, OpenRouter, Colab).

### 8.1 Pre-flight Verification

Run the verification script before deploying:

```bash
# Verify all files, env vars, and cloud service reachability
python scripts/verify_cloud_deployment.py

# Verify for a specific provider
python scripts/verify_cloud_deployment.py --provider gcp
python scripts/verify_cloud_deployment.py --provider flyio
python scripts/verify_cloud_deployment.py --provider railway
```

### 8.2 Google Cloud Run

Fully serverless deployment. Scales to zero when idle.

**Prerequisites:**
- `gcloud` CLI authenticated (`gcloud auth login`)
- GCP project with billing enabled (free tier covers moderate usage)
- `.env` with production secrets

**Deploy:**

```bash
# One-command deployment
make deploy-gcp

# Or manually
bash deploy/gcp/deploy.sh
```

**What it does:**
1. Enables required GCP APIs (Cloud Run, SQL Admin, Artifact Registry)
2. Creates Artifact Registry repo for Docker images
3. Creates Cloud SQL PostgreSQL instance
4. Stores secrets in Secret Manager
5. Builds and pushes all Docker images
6. Deploys 5 Cloud Run services (bridge, supervisor, render, voice, telegram)

**Post-deploy:**
- Apply database schema via Cloud SQL Proxy
- Set Telegram webhook to the Cloud Run URL

### 8.3 Fly.io

Container-based deployment with persistent volumes. Best for always-on services.

**Prerequisites:**
- `flyctl` CLI authenticated (`fly auth login`)
- Fly.io account (free tier includes 3 shared-cpu VMs)

**Deploy:**

```bash
# One-command deployment
make deploy-fly

# Or manually
bash deploy/flyio/deploy.sh
```

**What it does:**
1. Creates/checks the Fly.io app
2. Creates Fly Postgres (managed PostgreSQL)
3. Creates Fly Redis
4. Sets secrets from `.env`
5. Deploys all services
6. Creates persistent volume for n8n data

**Post-deploy:**
- Apply schema via `fly proxy` + `psql`

### 8.4 Railway

Git-push deployment. Simplest option for getting started.

**Prerequisites:**
- `railway` CLI authenticated (`railway login`)
- Railway account (free tier available)

**Deploy:**

```bash
# One-command deployment
make deploy-railway

# Or manually
bash deploy/railway/deploy.sh
```

**What it does:**
1. Creates/checks the Railway project
2. Adds PostgreSQL and Redis plugins
3. Sets environment variables
4. Deploys via `railway up`
5. Generates a public domain

### 8.5 Docker Compose with Cloud Override

For self-hosted VPS (DigitalOcean, Hetzner, Linode), use the cloud compose override:

```bash
# Copy cloud env template
cp deploy/env.cloud.example .env.cloud

# Edit with your managed DB credentials
nano .env.cloud

# Deploy with cloud override
make cloud-up

# Or manually
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d
```

The cloud override adds the cloud bridge service and is tuned for production. Set `POSTGRES_HOST` and `REDIS_HOST` to your managed services to skip running local Postgres/Redis.

---

## 9. Scaling

### Adding More Colab Instances

For parallel image generation, open multiple Colab notebooks simultaneously:

```
1. Notebook 1 → ComfyUI on T4 GPU → ngrok URL 1
2. Notebook 2 → ComfyUI on T4 GPU → ngrok URL 2
```

Configure in `.env`:

```env
COLAB_COMFYUI_ENDPOINT_1=https://ngrok-url-1.ngrok-free.app
COLAB_COMFYUI_ENDPOINT_2=https://ngrok-url-2.ngrok-free.app
```

The supervisor load-balances across available endpoints.

### Multiple HuggingFace API Keys

If you hit rate limits (3 req/min on free tier), create multiple HuggingFace accounts:

```env
HF_API_KEY=hf_account1_token
HF_API_KEY_2=hf_account2_token
HF_API_KEY_3=hf_account3_token
```

CineOS rotates through keys automatically.

### Scaling LLM Throughput

OpenRouter free tier has no hard request limit on small models. For higher throughput:

1. Use multiple OpenRouter accounts
2. Set different models for different workflow stages:
   - Fast extraction: `meta-llama/llama-3.1-8b-instruct`
   - Detailed analysis: `mistralai/mistral-7b-instruct`
   - Quality review (vision): `google/gemma-2-9b-it`

### Vertical Scaling (More Local Resources)

If you have a stronger machine, you can run more local services:

```yaml
# docker-compose.yml — scale up local workers
supervisor:
  deploy:
    resources:
      limits:
        memory: 2G

render_worker:
  deploy:
    replicas: 2  # Parallel video assembly
```

### Horizontal Scaling (Multiple Machines)

Run additional Docker Compose stacks on separate machines:

```bash
# Machine 1: Core services (Postgres, n8n, bot)
docker compose up -d postgres redis n8n telegram_bot

# Machine 2: Render farm
docker compose up -d render_worker supervisor
```

Point Machine 2's workers to Machine 1's Postgres via `POSTGRES_HOST=192.168.1.100`.

---

## 10. Quick Reference

### Essential Commands

```bash
docker compose up -d              # Start everything
docker compose down               # Stop everything
docker compose ps                 # Check status
docker compose logs -f n8n        # Watch n8n logs
docker compose restart            # Restart all services
make health                       # Check all health endpoints

# Cloud deployment
make cloud-up                     # Start with cloud bridge
make cloud-verify                 # Pre-flight check
make deploy-gcp                   # Deploy to Google Cloud Run
make deploy-fly                   # Deploy to Fly.io
make deploy-railway               # Deploy to Railway

# Testing
make test                         # Run unit tests
make test-e2e                     # Run E2E validation (111 checks)
```

### Key Ports

| Service | Port | URL |
|---------|------|-----|
| n8n UI | 5678 | http://localhost:5678 |
| Supervisor API | 8000 | http://localhost:8000/health |
| Render Worker | 8300 | http://localhost:8300/health |
| Voice Worker | 8400 | http://localhost:8400/health |
| Cloud Bridge | 8600 | http://localhost:8600/health |
| PostgreSQL | 5432 | localhost:5432 |

### Key Files

| File | Purpose |
|------|---------|
| `.env` | All configuration (API keys, passwords) |
| `docker-compose.yml` | Service definitions |
| `n8n-workflows/*.json` | All 25+ workflow definitions |
| `database/schema.sql` | Database schema |
| `config/models.yaml` | AI model configuration |

---

## See Also

- [Cloud Services Guide](cloud-services-guide.md) — Detailed cloud backend reference
- [Colab Setup Guide](colab-setup-guide.md) — Google Colab GPU setup
- [Quick Start](quickstart.md) — 5-minute getting started
- [Installation Guide](installation.md) — Full installation reference
- [Worker Guide](worker-guide.md) — Worker types and scaling
- [Troubleshooting](troubleshooting.md) — Common issues and fixes

### Cloud Provider Resources

| Provider | Free Tier | Best For | Deploy |
|----------|-----------|----------|--------|
| Google Cloud Run | 2M req/mo | Serverless, scales to zero | `make deploy-gcp` |
| Fly.io | 3 shared VMs | Always-on, persistent volumes | `make deploy-fly` |
| Railway | $5 credit | Git-push simplicity | `make deploy-railway` |
| VPS (Hetzner, DO) | ~$4/mo | Full control, Docker Compose | `make cloud-up` |
