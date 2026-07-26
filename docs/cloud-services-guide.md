# CineOS Cloud Services Guide

Reference for all cloud backends used by CineOS. Covers every supported service, configuration, rate limits, fallback behavior, and how to add new backends.

---

## 1. Cloud Backend Overview

CineOS runs heavy AI on free cloud services. Your local machine only handles orchestration and lightweight assembly.

| Service | Type | Signup Required | Free Tier | Primary Use |
|---------|------|----------------|-----------|-------------|
| OpenRouter | LLM API | Yes (free) | Unlimited (8B models) | Analysis, planning, quality review |
| HuggingFace Inference | Image API | Yes (free) | 3 req/min | Image generation |
| Pollinations | Image API | No | Unlimited | Image generation (fallback) |
| Google Colab | GPU Compute | Yes (free) | ~12h/day T4 GPU | ComfyUI + FLUX, RealESRGAN, LivePortrait |
| Edge-TTS | Voice API | No | Unlimited | Text-to-speech narration |

---

## 2. Backend Comparison

### Image Generation

| Backend | Quality | Speed | Resolution | Cost | Offline | Setup |
|---------|---------|-------|------------|------|---------|-------|
| Colab ComfyUI + FLUX | Excellent | 10-30s | Up to 2048x2048 | Free | No (needs Colab running) | Medium |
| HuggingFace FLUX.1-schnell | High | 5-15s | 1024x1024 | Free | No | Easy |
| HuggingFace SDXL | Good | 5-15s | 1024x1024 | Free | No | Easy |
| Pollinations | Good | 10-30s | Up to 1024x1024 | Free | No | None |

### LLM (Text Analysis)

| Backend | Quality | Speed | Context | Cost | Offline | Setup |
|---------|---------|-------|---------|------|---------|-------|
| OpenRouter Llama 3.1 70B | Excellent | 2-5s | 128k tokens | Free (limited) | No | Easy |
| OpenRouter Llama 3.1 8B | Good | 0.5-2s | 128k tokens | Free | No | Easy |
| OpenRouter Mistral 7B | Good | 0.5-2s | 32k tokens | Free | No | Easy |
| OpenRouter Gemma 2 9B | Good | 0.5-2s | 8k tokens | Free | No | Easy |
| Rule-based fallback | Basic | Instant | N/A | Free | Yes | None |

### Text-to-Speech

| Backend | Quality | Languages | Cost | Offline | Setup |
|---------|---------|-----------|------|---------|-------|
| Edge-TTS | High | 75+ | Free | No | None |
| Kokoro (local) | Excellent | Limited | Free | Yes | Medium |
| Piper (local) | Good | 30+ | Free | Yes | Easy |

---

## 3. Service Configuration

### 3.1 OpenRouter

**Environment Variables:**

```env
OPENROUTER_API_KEY=sk-or-v1-your_key_here
```

**n8n Configuration:**

The HTTP Request nodes in analysis workflows use these settings:

```
URL: https://openrouter.ai/api/v1/chat/completions
Method: POST
Headers:
  Authorization: Bearer {{ $env.OPENROUTER_API_KEY }}
  Content-Type: application/json
  HTTP-Referer: https://cineos.local
  X-Title: CineOS
Body:
  {
    "model": "meta-llama/llama-3.1-8b-instruct",
    "messages": [...],
    "temperature": 0.3,
    "max_tokens": 4096
  }
```

**Available Models (Free):**

| Model ID | Best For | Max Tokens |
|----------|----------|------------|
| `meta-llama/llama-3.1-8b-instruct` | General analysis, extraction | 128k |
| `mistralai/mistral-7b-instruct` | Structured output, planning | 32k |
| `google/gemma-2-9b-it` | Creative tasks, prompt building | 8k |
| `meta-llama/llama-3.1-70b-instruct` | Quality review, complex reasoning | 128k |

**Usage in CineOS Workflows:**

| Workflow | Model | Purpose |
|----------|-------|---------|
| 004 Story Parser | Llama 3.1 8B | Chapter/scene extraction |
| 005 Story Intelligence | Llama 3.1 8B | Theme, character, conflict analysis |
| 006 Character Engine | Llama 3.1 8B | Character DNA extraction |
| 007 World Engine | Llama 3.1 8B | World bible construction |
| 013 Prompt Builder | Gemma 2 9B | Prompt generation |
| 018 Quality AI | Llama 3.1 70B | Vision quality review |
| 019 Repair Engine | Mistral 7B | Repair strategy selection |

### 3.2 HuggingFace Inference API

**Environment Variables:**

```env
HF_API_KEY=hf_your_token_here
```

**n8n Configuration:**

```
URL: https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell
Method: POST
Headers:
  Authorization: Bearer {{ $env.HF_API_KEY }}
Body (binary): raw image bytes from prompt
```

**For JSON input:**

```
URL: https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell
Method: POST
Headers:
  Authorization: Bearer {{ $env.HF_API_KEY }}
  Content-Type: application/json
Body:
  {
    "inputs": "masterpiece, best quality, {shot_prompt}",
    "parameters": {
      "width": 1024,
      "height": 1024,
      "num_inference_steps": 4
    }
  }
```

**Available Models:**

| Model ID | Quality | Speed | Notes |
|----------|---------|-------|-------|
| `black-forest-labs/FLUX.1-schnell` | High | Fast (4 steps) | Best free option |
| `stabilityai/stable-diffusion-xl-base-1.0` | Good | Medium | Reliable |
| `runwayml/stable-diffusion-v1-5` | Good | Fast | Older but stable |

**Response Handling:**

The API returns raw image bytes (PNG). In n8n, use the "Read Binary File" or write the response body directly to disk.

**Rate Limit Handling:**

HuggingFace free tier allows ~3 requests per minute. If rate-limited:

1. Wait 20 seconds and retry
2. Switch to Pollinations as fallback
3. Add additional HuggingFace accounts (see Section 7)

### 3.3 Pollinations

**Environment Variables:**

```env
POLLINATIONS_ENABLED=true
```

**No API key needed.** The API is accessed via URL:

```
GET https://image.pollinations.ai/prompt/{url_encoded_prompt}?width=1024&height=1024&seed=42
```

**Parameters:**

| Parameter | Default | Range | Notes |
|-----------|---------|-------|-------|
| `width` | 1024 | 256-2048 | Output width |
| `height` | 1024 | 256-2048 | Output height |
| `seed` | random | 0-999999 | For reproducibility |
| `model` | flux | flux, turbo | Model selection |
| `nologo` | false | true/false | Remove watermark |

**n8n Configuration:**

```
URL: https://image.pollinations.ai/prompt/{{ encodeURIComponent($json.prompt) }}?width=1024&height=1024
Method: GET
Response Format: Binary (image/png)
```

**Response:** Returns a PNG image directly. No JSON parsing needed.

### 3.4 Google Colab

**Environment Variables:**

```env
COLAB_COMFYUI_ENDPOINT=https://your-ngrok-url.ngrok-free.app
COLAB_API_KEY=your_shared_secret
COLAB_WARMUP_URL=
```

**n8n Configuration (ComfyUI job submission):**

```
URL: {{ $env.COLAB_COMFYUI_ENDPOINT }}/prompt
Method: POST
Headers:
  Content-Type: application/json
  Authorization: Bearer {{ $env.COLAB_API_KEY }}
Body:
  {
    "prompt": {
      "3": {
        "class_type": "KSampler",
        "inputs": {
          "seed": 42,
          "steps": 20,
          "cfg": 7.5,
          "sampler_name": "euler_a",
          "denoise": 1.0,
          "model": ["4", 0],
          "positive": ["6", 0],
          "negative": ["7", 0],
          "latent_image": ["5", 0]
        }
      },
      "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
          "text": "...",
          "clip": ["4", 1]
        }
      }
    }
  }
```

**Job Polling:**

```
URL: {{ $env.COLAB_COMFYUI_ENDPOINT }}/history/{prompt_id}
Method: GET
Poll interval: 5 seconds
Timeout: 300 seconds (5 minutes)
```

**Endpoint Lifecycle:**

1. Open Colab notebook → Run all cells
2. Cells install ComfyUI + FLUX, start server, create ngrok tunnel
3. ngrok URL displayed in cell output → copy to `.env`
4. Endpoint stays alive as long as Colab runtime is active
5. Auto-shutdown after 30 minutes of inactivity (configurable)
6. To resume: re-run notebook cells

See [Colab Setup Guide](colab-setup-guide.md) for complete setup instructions.

### 3.5 Edge-TTS

**No environment variable needed.** Pre-configured in the Voice Worker.

Edge-TTS uses Microsoft's free Azure Speech API. No API key required.

**Supported Voices (English):**

| Voice | Gender | Style |
|-------|--------|-------|
| en-US-AriaNeural | Female | Natural |
| en-US-GuyNeural | Male | Natural |
| en-US-JennyNeural | Female | Professional |
| en-US-AndrewNeural | Male | Warm |
| en-US-EmmaNeural | Female | Friendly |
| en-GB-SoniaNeural | Female | British |
| en-GB-RyanNeural | Male | British |

**Rate Limits:** No documented hard limit. Behave reasonably (max 10 concurrent requests).

---

## 4. Enabling and Disabling Backends

### Via Environment Variables

In `.env`, set or unset the relevant variables:

```env
# Enable OpenRouter LLM
OPENROUTER_API_KEY=sk-or-v1-xxx

# Disable OpenRouter (remove or leave empty)
OPENROUTER_API_KEY=

# Enable HuggingFace images
HF_API_KEY=hf_xxx

# Disable HuggingFace (remove or leave empty)
HF_API_KEY=

# Enable Pollinations fallback
POLLINATIONS_ENABLED=true

# Disable Pollinations
POLLINATIONS_ENABLED=false

# Enable Colab ComfyUI
COLAB_COMFYUI_ENDPOINT=https://xxx.ngrok-free.app

# Disable Colab (remove or leave empty)
COLAB_COMFYUI_ENDPOINT=
```

### Via Database Config

Override backend priority at runtime:

```sql
-- Change image generation priority
UPDATE cineos.config.system_config
SET value = '["hf_inference", "pollinations"]'
WHERE key = 'generation.default_image_backend_priority';

-- Change TTS priority
UPDATE cineos.config.system_config
SET value = '["edge_tts", "piper"]'
WHERE key = 'generation.default_tts_backend_priority';
```

### Via n8n Workflow Edit

Each workflow node that calls a cloud service has a conditional check:

```
IF $env.OPENROUTER_API_KEY is not empty
  → Use OpenRouter
ELSE
  → Use fallback (rule-based or local)
```

---

## 5. Adding New Cloud Backends

### Step 1: Create the Backend Client

Add a new backend in the relevant worker or n8n workflow. For image generation as an example:

In the image generation workflow (017_image_generation.json), add a new HTTP Request node after the existing backend nodes:

```
Node: "New Backend API"
Type: HTTP Request
Method: POST
URL: https://api.newservice.com/v1/generate
Headers:
  Authorization: Bearer {{ $env.NEW_SERVICE_API_KEY }}
  Content-Type: application/json
Body:
  {
    "prompt": "{{ $json.positive_prompt }}",
    "negative_prompt": "{{ $json.negative_prompt }}",
    "width": {{ $json.width }},
    "height": {{ $json.height }}
  }
```

### Step 2: Add the API Key Variable

Add to `.env.example`:

```env
# ── New Service (optional) ────────────────────────────────────────
NEW_SERVICE_API_KEY=
```

Add to `.env`:

```env
NEW_SERVICE_API_KEY=your_key_here
```

Add to `docker-compose.yml` n8n environment section:

```yaml
NEW_SERVICE_API_KEY: ${NEW_SERVICE_API_KEY:-}
```

### Step 3: Add to the Fallback Chain

Update the backend priority config in `database/seed/config_defaults.sql`:

```sql
INSERT INTO cineos.config.system_config (key, value, description, category) VALUES
('generation.default_image_backend_priority',
 '["local_gpu", "hf_inference", "new_service", "pollinations"]',
 'Image backend priority with new service',
 'generation')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
```

### Step 4: Add Error Handling

Add a Switch node after the HTTP Request to handle errors:

```
IF response.status >= 400
  → Log error to cineos.audit.events
  → Try next backend in fallback chain
ELSE
  → Process response image
  → Save to database
```

### Step 5: Test

1. Set the new API key in `.env`
2. Restart n8n: `docker compose restart n8n`
3. Trigger a test generation via n8n webhook or Telegram bot
4. Check the n8n execution log for the new backend node

---

## 6. API Key Management

### Security Rules

1. **Never commit API keys** to version control
2. **Rotate keys** every 90 days
3. **Use separate keys** for development and production
4. **Monitor usage** for unexpected spikes

### Key Storage

All keys are stored in `.env` and passed to containers via environment variables. They are never written to disk inside containers (except in memory).

### Key Rotation Procedure

1. Generate new key at the provider's website
2. Update `.env` with new key
3. Restart n8n: `docker compose restart n8n`
4. Verify the new key works: `make health`
5. Revoke the old key at the provider

### Sharing Keys Between Instances

For multiple CineOS instances, use a shared secrets manager or copy `.env` to each instance. Never hardcode keys in workflow JSON files.

---

## 7. Rate Limiting Per Service

### OpenRouter

| Tier | Limit | Notes |
|------|-------|-------|
| Free (8B models) | No hard limit | Be reasonable, ~100 req/min practical |
| Free (70B models) | ~200 req/day | Monitor usage in dashboard |
| Paid | Higher limits | Depends on credit balance |

**Rate limit error:** HTTP 429. Wait 10 seconds and retry.

### HuggingFace

| Tier | Limit | Notes |
|------|-------|-------|
| Free | 3 requests per minute | Per model, per account |
| Pro ($9/mo) | 10x higher | Worth it for heavy use |

**Rate limit error:** HTTP 429 or 503 (model loading). Wait 20 seconds and retry.

### Pollinations

| Tier | Limit | Notes |
|------|-------|-------|
| Free | No documented limit | Be reasonable, max 1 concurrent |

**Rate limit error:** HTTP 429. Wait 30 seconds and retry.

### Google Colab

| Tier | Limit | Notes |
|------|-------|-------|
| Free | ~12 hours/day GPU | Runtime disconnects after ~90 min idle |
| Colab Pro ($10/mo) | ~24 hours/day GPU | Longer runtime, better GPUs |

**Limit:** Colab disconnects if idle. Use auto-shutdown scripts to avoid wasting GPU time.

### Edge-TTS

| Tier | Limit | Notes |
|------|-------|-------|
| Free | No documented limit | Max 10 concurrent recommended |

---

## 8. Fallback Chains

CineOS automatically falls back to the next backend when one fails. The fallback order is configurable.

### Image Generation Fallback Chain

```
Priority 1: local_gpu (Colab ComfyUI)
    ↓ if unavailable or fails
Priority 2: hf_inference (HuggingFace FLUX.1-schnell)
    ↓ if rate-limited or fails
Priority 3: pollinations (Pollinations API)
    ↓ if fails
Priority 4: Error — mark shot as failed, trigger repair
```

### LLM Analysis Fallback Chain

```
Priority 1: openrouter (Llama 3.1 8B)
    ↓ if API key not set or fails
Priority 2: openrouter (Mistral 7B)
    ↓ if fails
Priority 3: Rule-based fallback (regex + templates)
    ↓ — always works, lower quality
```

### TTS Fallback Chain

```
Priority 1: edge_tts (Microsoft Edge-TTS)
    ↓ if fails
Priority 2: piper (local)
    ↓ if not installed
Priority 3: espeak (local, low quality)
```

### How Fallback Works in n8n

Each generation workflow implements the fallback chain using a series of IF nodes:

```
[Start] → [Check Backend 1] → IF success?
                                  ├── YES → [Save Result] → [End]
                                  └── NO → [Check Backend 2] → IF success?
                                                                  ├── YES → [Save Result] → [End]
                                                                  └── NO → [Check Backend 3] → ...
```

When a backend returns an error (HTTP 4xx/5xx, timeout, or empty response), the workflow catches the error and tries the next backend. Each attempt is logged in `cineos.audit.events` with the backend name and error details.

---

## 9. Monitoring Dashboard

### Database Queries for Cloud Usage

```sql
-- Image generation by backend (last 7 days)
SELECT backend_used,
       COUNT(*) as total,
       COUNT(*) FILTER (WHERE quality_score >= 0.6) as passed,
       AVG(generation_time_ms) as avg_ms
FROM cineos.generation.images
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY backend_used
ORDER BY total DESC;

-- LLM usage by model (last 7 days)
SELECT reviewer_model,
       COUNT(*) as reviews,
       AVG(overall_score) as avg_score
FROM cineos.quality.reviews
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY reviewer_model;

-- Backend failure rate
SELECT backend_used,
       COUNT(*) as total,
       COUNT(*) FILTER (WHERE state = 'rejected') as rejected,
       ROUND(COUNT(*) FILTER (WHERE state = 'rejected')::numeric / COUNT(*) * 100, 1) as fail_pct
FROM cineos.generation.images
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY backend_used;

-- Cloud API errors (last hour)
SELECT event_type, source, message, details->>'status_code' as status
FROM cineos.audit.events
WHERE created_at > NOW() - INTERVAL '1 hour'
AND event_type = 'error'
ORDER BY created_at DESC;
```

---

## See Also

- [Deployment Guide](deployment-guide.md) — Complete deployment walkthrough
- [Colab Setup Guide](colab-setup-guide.md) — Google Colab GPU setup
- [Worker Guide](worker-guide.md) — Local worker configuration
- [Workflow Guide](workflow-guide.md) — How n8n workflows use cloud backends
- [Troubleshooting](troubleshooting.md) — Common cloud service issues
