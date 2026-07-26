# CineOS -- Complete Deployment Guide (Zero to Running Bot)

This guide takes you from zero to a fully running CineOS Telegram bot.
No code modifications needed. Just follow every step.

---

## Which Cloud Platform Should You Use?

### Recommendation: Railway

Railway is the best platform for CineOS. Here is the full comparison:

|                        | Railway            | Fly.io             | Google Cloud Run        | VPS (Hetzner)     |
|------------------------|--------------------|--------------------|-------------------------|--------------------|
| Setup difficulty       | Easiest            | Medium             | Hard                    | Medium             |
| Time to first deploy   | ~15 min            | ~30 min            | ~1 hour                 | ~30 min            |
| Managed PostgreSQL     | Yes (one-click)    | Yes (one-click)    | No (Cloud SQL, $7+/mo)  | No (self-hosted)   |
| Managed Redis          | Yes (one-click)    | Yes (Upstash)      | No (Memorystore, $5+/mo)| No (self-hosted)   |
| Always-on              | Yes                | Yes                | No (scales to zero)     | Yes                |
| Monthly cost           | $5-12              | $2-5               | $12-20+                 | $4-6               |
| Free trial             | $5 credit / 30d    | ~2 hours runtime   | $300 credit / 90d       | None               |
| Post-trial cost        | $5/mo minimum      | Pay-per-use        | Pay-per-use             | Fixed monthly      |
| Docker support         | Native             | Native             | Native                  | Native             |
| Git push deploy        | Yes                | No (CLI only)      | No (Cloud Build)        | No (CLI only)      |

### Why Not the Others?

**Google Colab** -- NOT a hosting platform. It runs Jupyter notebooks with
temporary GPUs. Sessions die after 90 minutes of idle. Cannot host a Telegram
bot or PostgreSQL 24/7. CineOS uses Colab ONLY for optional GPU tasks
(ComfyUI, RealESRGAN), never for hosting.

**Google Cloud Run** -- The compute is cheap and has a generous free tier, but
you also need Cloud SQL for PostgreSQL ($7+/mo minimum) and Memorystore for
Redis ($5+/mo minimum). Total cost: $12-20+/mo. Too complex and too expensive
for this project.

**Fly.io** -- Good platform, but no free tier for new users (trial is ~2 hours
of VM runtime). Slightly more complex setup than Railway. Better suited for
multi-region edge deployments, which CineOS does not need.

**VPS (Hetzner, DigitalOcean, Linode)** -- Cheapest option at $4-6/mo, but you
manage everything yourself: install Docker, configure PostgreSQL, manage
backups, handle SSL certificates, monitor disk space. Good if you are
comfortable with Linux server administration.

### Why Railway Wins

1. **One-click Postgres and Redis** -- No database setup, no connection strings
   to figure out. Click a button, get a database.
2. **Git push deployment** -- Push code to GitHub, Railway detects the
   Dockerfile and deploys automatically.
3. **Managed environment variables** -- Set them in the dashboard, never touch
   `.env` files on servers.
4. **Built-in monitoring** -- Logs, metrics, deployment history all in the
   dashboard.
5. **$5 trial credit covers weeks** -- CineOS is lightweight (~1 GB RAM total).
   The $5 credit lasts far longer than 30 days of moderate usage.

---

## What You Need Before Starting

| Item                      | Where to Get It          | Cost  |
|---------------------------|--------------------------|-------|
| GitHub account            | github.com               | Free  |
| Railway account           | railway.app              | Free (credit card required for trial) |
| Telegram bot token        | @BotFather on Telegram   | Free  |
| OpenRouter API key        | openrouter.ai            | Free  |
| A .txt file with a novel  | Your own file            | Free  |

**Time estimate:** 30-45 minutes from zero to running bot.

---

## PHASE 1: Get Your API Keys (10 minutes)

### Step 1.1 -- Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send: `/newbot`
3. Choose a display name: `CineOS Bot` (or anything you like)
4. Choose a username: `cineos_yourname_bot` (must end in `bot`)
5. BotFather replies with a token:
   `8844705231:AAHXUbfuy7zZS4v_qRpUInmTlkSi4gVDj28`
6. **Copy this token immediately** -- you need it in Step 3.5

### Step 1.2 -- Get an OpenRouter API Key

1. Go to **https://openrouter.ai**
2. Sign in with Google, GitHub, or email
3. Go to **https://openrouter.ai/keys**
4. Click **Create Key**
5. Name it `cineos-production`
6. Copy the key (starts with `sk-or-v1-...`)

This gives you free access to Llama 3, Mistral, Gemma and other LLMs for
story analysis, character extraction, and quality review.

### Step 1.3 -- (Optional) Get a HuggingFace API Key

For better image generation quality:

1. Go to **https://huggingface.co**
2. Create an account
3. Go to **https://huggingface.co/settings/tokens**
4. Click **New token** -> type `read` -> Generate
5. Copy the token (starts with `hf_...`)

If you skip this, CineOS uses Pollinations (free, no signup needed) for all
image generation. It works fine, just slightly lower quality.

---

## PHASE 2: Push Code to GitHub (5 minutes)

### Step 2.1 -- Create a GitHub Repository

1. Go to **https://github.com/new**
2. Name it `cineos` (or anything)
3. **Do NOT** initialize with README (the project already has one)
4. Click **Create repository**

### Step 2.2 -- Push the CineOS Code

Open a terminal on your machine. Navigate to the CineOS project folder:

```bash
cd /path/to/cineos

# Initialize git
git init
git add .
git commit -m "Initial CineOS deployment"

# Connect to your GitHub repo
git remote add origin https://github.com/YOUR_USERNAME/cineos.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

---

## PHASE 3: Deploy to Railway (15 minutes)

### Step 3.1 -- Create a Railway Account

1. Go to **https://railway.app**
2. Click **Login** -> Sign in with GitHub
3. You get $5 in free credits (valid for 30 days or until spent)

### Step 3.2 -- Create a New Project

1. Click **New Project**
2. Select **Deploy from GitHub Repo**
3. Authorize Railway to access your GitHub
4. Select your `cineos` repository
5. Railway detects the Dockerfile and starts building (takes 2-3 minutes)

### Step 3.3 -- Add PostgreSQL

1. In your project dashboard, click **New** -> **Database** -> **PostgreSQL**
2. Railway creates a managed PostgreSQL instance (~30 seconds)
3. Click on the PostgreSQL service
4. Go to the **Variables** tab
5. You will see auto-generated values for `POSTGRES_HOST`, `POSTGRES_PORT`,
   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
6. **Copy all of these** -- you need them in Step 3.5

### Step 3.4 -- Add Redis

1. Click **New** -> **Database** -> **Redis**
2. Railway creates a managed Redis instance
3. Click on the Redis service -> **Variables** tab
4. **Copy `REDIS_HOST` and `REDIS_PORT`**

### Step 3.5 -- Set Environment Variables

Click on your **cineos** service (the one built from your Dockerfile) ->
**Variables** tab -> **New Variable** for each of these:

```
TELEGRAM_BOT_TOKEN        = (your bot token from Step 1.1)
OPENROUTER_API_KEY        = (your OpenRouter key from Step 1.2)
HF_API_KEY                = (your HuggingFace key from Step 1.3, or leave empty)

POSTGRES_HOST             = (from Step 3.3 -- Railway's Postgres variable)
POSTGRES_PORT             = (from Step 3.3 -- usually 5432)
POSTGRES_DB               = (from Step 3.3 -- usually cineos)
POSTGRES_USER             = (from Step 3.3 -- usually cineos)
POSTGRES_PASSWORD         = (from Step 3.3 -- auto-generated password)

REDIS_HOST                = (from Step 3.4 -- Railway's Redis variable)
REDIS_PORT                = (from Step 3.4 -- usually 6379)

N8N_HOST                  = 0.0.0.0
N8N_PORT                  = 5678
N8N_PROTOCOL              = http
N8N_BASIC_AUTH_ACTIVE     = true
N8N_BASIC_AUTH_USER       = admin
N8N_BASIC_AUTH_PASSWORD   = (pick a strong password)
N8N_ENCRYPTION_KEY        = (run: openssl rand -hex 16)
WEBHOOK_URL               = http://localhost:5678/

DEFAULT_LANGUAGE          = en
QUALITY_THRESHOLD         = 0.80
MAX_RETRY                 = 3
MAX_PARALLEL_JOBS         = 4
LOG_LEVEL                 = INFO
TZ                        = UTC

POLLINATIONS_ENABLED      = true
COLAB_COMFYUI_ENDPOINT    = (leave empty for now)
COLAB_API_KEY             = (leave empty for now)

CINEOS_API_KEY_SALT       = (run: openssl rand -hex 16)
CINEOS_WEBHOOK_SECRET     = (run: openssl rand -hex 16)
CINEOS_ENCRYPTION_KEY     = (run: openssl rand -hex 32)
```

**How to generate random strings:** Open a terminal and run:
```bash
openssl rand -hex 16
```
Run it once for each value that needs a random string.

**How to connect Railway's databases:** Railway auto-creates environment
variables on each database service. Click the PostgreSQL service -> Variables
tab to see the actual host, port, user, password, and database name. Copy
those exact values into your cineos service variables.

### Step 3.6 -- Set the Service Start Command

Railway needs to know how to start the bot. In your cineos service settings:

1. Go to **Settings** tab
2. Under **Service Variables**, add:
   - `RAILWAY_EXECUTIVE_CMD` = `python -m src.telegram`

Or, if Railway does not detect the CMD from the Dockerfile, go to
**Settings** -> **Deploy** and set the **Start Command** to:
```
python -m src.telegram
```

### Step 3.7 -- Trigger a Redeploy

After setting all variables:

1. Go to the **Deployments** tab
2. Click **Deploy** (or push a small change to GitHub to trigger auto-deploy)
3. Watch the build logs -- it should take 2-3 minutes
4. Check the **Logs** tab for startup messages

You should see lines like:
```
CineOS Telegram Bot starting...
Bot connected: @cineos_yourname_bot
Health server running on port 8080
```

---

## PHASE 4: Initialize the Database (5 minutes)

The PostgreSQL database needs tables created. Railway provides a web shell:

### Step 4.1 -- Open the PostgreSQL Console

1. Click on your **PostgreSQL** service in Railway
2. Go to the **Data** tab
3. You will see a SQL query editor

### Step 4.2 -- Apply the Schema

The project contains SQL files that create all tables. You need to run them
in order. Open each file from the `database/` folder in the project and
paste the contents into the Railway SQL editor, one at a time:

1. `database/schema.sql` -- Creates all tables
2. `database/indexes.sql` -- Creates performance indexes
3. `database/constraints.sql` -- Creates data integrity constraints
4. `database/functions.sql` -- Creates helper functions
5. `database/triggers.sql` -- Creates auto-update triggers
6. `database/views.sql` -- Creates convenience views
7. `database/seed/config_defaults.sql` -- Inserts default config values

**Alternative (if you have psql installed):**
```bash
# Install Cloud SQL Proxy or connect directly
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/schema.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/indexes.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/constraints.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/functions.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/triggers.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/views.sql
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME" -f database/seed/config_defaults.sql
```

---

## PHASE 5: Import n8n Workflows (5 minutes)

CineOS ships with 25 n8n workflow JSON files in the `workflows/` directory.
These orchestrate the entire novel-to-video pipeline.

### Step 5.1 -- Access n8n

n8n runs inside the CineOS stack. If you deployed only the Telegram bot on
Railway, you also need to deploy n8n separately (see Phase 6 below for the
full-stack deployment).

For local testing:
```bash
docker compose up -d n8n
# Open http://localhost:5678
```

### Step 5.2 -- Import Workflows

In the n8n UI:

1. Click the hamburger menu (top-left) -> **Workflows** -> **Import from File**
2. Select each JSON file from `workflows/` folder
3. Import them in order: 001, 002, 003 ... through 025
4. Each workflow appears in your workflow list

### Step 5.3 -- Activate Workflows

1. Open each imported workflow
2. Toggle the **Active** switch (top-right) to ON
3. Repeat for all 25 workflows

---

## PHASE 6: Full-Stack Deployment (Railway)

The Telegram bot is just one service. For the full CineOS pipeline, you need
PostgreSQL, Redis, n8n, the bot, and workers all running. Here is how to
deploy the complete stack on Railway:

### Step 6.1 -- Create a Second Service for n8n

1. In your Railway project, click **New** -> **Service** -> **GitHub Repo**
2. Select the same `cineos` repository
3. Name it `n8n`
4. In the service **Settings**, set the **Start Command** to:
   ```
   n8n start
   ```
5. Set these environment variables on the n8n service:
   ```
   DB_TYPE                = postgresdb
   DB_POSTGRESDB_HOST     = (same Postgres host from Step 3.3)
   DB_POSTGRESDB_PORT     = (same Postgres port)
   DB_POSTGRESDB_DATABASE = (same Postgres DB name)
   DB_POSTGRESDB_USER     = (same Postgres user)
   DB_POSTGRESDB_PASSWORD = (same Postgres password)
   N8N_HOST               = 0.0.0.0
   N8N_PORT               = 5678
   N8N_PROTOCOL           = http
   WEBHOOK_URL            = (n8n's public Railway URL, see Step 6.2)
   N8N_BASIC_AUTH_ACTIVE  = true
   N8N_BASIC_AUTH_USER    = admin
   N8N_BASIC_AUTH_PASSWORD = (same as bot)
   N8N_ENCRYPTION_KEY     = (same as bot)
   OPENROUTER_API_KEY     = (same as bot)
   HF_API_KEY             = (same as bot)
   TELEGRAM_BOT_TOKEN     = (same as bot)
   ```

### Step 6.2 -- Generate a Public URL for n8n

1. Click on the n8n service
2. Go to **Settings** -> **Networking**
3. Click **Generate Domain**
4. Railway gives you a URL like: `n8n-xxxx.up.railway.app`
5. Update the n8n service's `WEBHOOK_URL` to: `https://n8n-xxxx.up.railway.app/`
6. Also update the Telegram bot service's `WEBHOOK_URL` to the same value

### Step 6.3 -- Deploy Workers (Optional)

For the render and voice workers, create additional services from the same
repo with these start commands:

| Service        | Start Command                            | Memory |
|----------------|------------------------------------------|--------|
| render_worker  | `python -m workers.render_worker.service`| 512 MB |
| voice_worker   | `python -m workers.voice_worker.service` | 256 MB |
| supervisor     | `python -m workers.supervisor.service`   | 256 MB |
| cloud_bridge   | `python -m workers.cloud_bridge`         | 256 MB |

Each worker needs the same Postgres and Redis environment variables as the bot.

---

## PHASE 7: Test the Bot (2 minutes)

### Step 7.1 -- Open Telegram

1. Find your bot by its username (the one you chose in Step 1.1)
2. Send: `/start`
3. You should receive a welcome message

### Step 7.2 -- Send a Test Text

1. Send a `.txt` file (can be a short story, 500-1000 words is fine for testing)
2. The bot acknowledges receipt
3. Send `/status` to check progress

### Step 7.3 -- Monitor Progress

- **Telegram**: Send `/status` anytime for progress updates
- **Railway dashboard**: Click the service -> **Logs** tab to see detailed output
- **n8n dashboard**: Open the n8n URL -> **Executions** tab to see workflow runs

---

## PHASE 8: Set Up Free Cloud AI (10 minutes)

By this point the bot is running but image generation uses Pollinations only.
For higher quality, set up the free cloud services:

### Step 8.1 -- OpenRouter (Already Done)

You set this up in Step 1.2. CineOS uses it for:
- Story analysis (chapter/scene extraction)
- Character DNA extraction
- World bible building
- Quality review (vision models)
- Prompt generation

### Step 8.2 -- Pollinations (Already Active)

No setup needed. `POLLINATIONS_ENABLED=true` is already set. CineOS uses
it for:
- Image generation (free, no API key)
- Background shots
- Fallback when other backends fail

### Step 8.3 -- HuggingFace (Optional)

If you got a HuggingFace key in Step 1.3, it is already set. CineOS uses it
for higher quality image generation via FLUX.1-schnell.

### Step 8.4 -- Google Colab for GPU (Optional, Highest Quality)

For the absolute best image quality, use Google Colab for ComfyUI + FLUX:

1. Go to **https://colab.research.google.com**
2. Upload the notebook from `notebooks/comfyui_flux.ipynb`
3. Runtime -> Change runtime type -> T4 GPU
4. Run all cells
5. Copy the ngrok URL from cell output
6. In Railway, set: `COLAB_COMFYUI_ENDPOINT=https://your-ngrok-url.ngrok-free.app`

The Colab endpoint is only active while the notebook is running. Start it
when you want maximum quality images. CineOS falls back to Pollinations
automatically when Colab is offline.

---

## Cost Summary

### During Trial (First 30 Days)

| Service                | Cost   |
|------------------------|--------|
| Railway ($5 credit)    | $0     |
| OpenRouter (8B models) | $0     |
| Pollinations           | $0     |
| HuggingFace            | $0     |
| Edge-TTS               | $0     |
| **Total**              | **$0** |

### After Trial (Monthly)

| Service                | Cost      |
|------------------------|-----------|
| Railway Hobby plan     | $5-12/mo  |
| OpenRouter (8B models) | $0        |
| Pollinations           | $0        |
| HuggingFace            | $0        |
| Edge-TTS               | $0        |
| **Total**              | **$5-12/mo** |

### Cheapest Alternative: Hetzner VPS

If Railway's $5-12/mo is too expensive after the trial:

1. Sign up at **https://hetzner.com** (no free tier, ~4 EUR/mo for CX22)
2. Create a Cloud Server (CX22, 2 vCPU, 4 GB RAM, Ubuntu 22.04)
3. SSH in and install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. Clone the repo and run:
   ```bash
   git clone https://github.com/YOUR_USERNAME/cineos.git
   cd cineos
   cp .env.example .env
   # Edit .env with your API keys
   docker compose up -d
   ```
5. Cost: ~$4-6/mo fixed, no surprise bills

---

## Troubleshooting

### Bot does not respond to messages

1. Check Railway logs: click the service -> **Logs** tab
2. Verify `TELEGRAM_BOT_TOKEN` is set correctly (no extra spaces)
3. Check that the bot is not blocked by Telegram (send `/start` again)
4. Verify the token with: `curl https://api.telegram.org/botYOUR_TOKEN/getMe`

### Bot starts but database errors

1. Verify `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
   `POSTGRES_DB` are all set in Railway
2. Make sure you ran the schema SQL files (Phase 4)
3. Check that the Postgres service is healthy (green status in Railway)

### n8n workflows not triggering

1. Make sure n8n is running and accessible via its public URL
2. Check that `WEBHOOK_URL` on the n8n service matches its actual public URL
3. Activate each workflow in the n8n UI (toggle Active switch)
4. Check n8n execution logs for errors

### Image generation fails

1. If using only Pollinations: check that `POLLINATIONS_ENABLED=true`
2. If using OpenRouter: verify `OPENROUTER_API_KEY` is set and valid
3. If using HuggingFace: verify `HF_API_KEY` is set and valid
4. Check the image generation workflow execution in n8n

### Railway costs exceeding $5

1. CineOS uses ~1 GB RAM total across all services
2. Railway charges per-second for CPU and memory
3. Check the **Usage** tab in Railway for a cost breakdown
4. Scale down unused workers (set replicas to 0)
5. Consider migrating to a Hetzner VPS (~$4/mo fixed)

### Deploy fails with "No start command"

1. Go to the service -> **Settings** -> **Deploy**
2. Set the **Start Command** to: `python -m src.telegram`
3. Redeploy

---

## Quick Reference

### Essential Railway Commands

| Action                   | How                                                    |
|--------------------------|--------------------------------------------------------|
| Check bot logs           | Railway dashboard -> Service -> Logs                   |
| Set environment variable | Railway dashboard -> Service -> Variables -> New       |
| Redeploy                 | Railway dashboard -> Service -> Deployments -> Deploy  |
| Check database           | Railway dashboard -> PostgreSQL -> Data tab            |
| Generate random string   | Terminal: `openssl rand -hex 16`                        |
| Test Telegram token      | `curl https://api.telegram.org/botTOKEN/getMe`         |

### Service Architecture

```
Railway Project
  |
  +-- cineos (Telegram Bot)     -- python -m src.telegram
  +-- n8n (Orchestrator)        -- n8n start
  +-- PostgreSQL (Database)     -- managed by Railway
  +-- Redis (Cache/Queue)       -- managed by Railway
  +-- render_worker (optional)  -- python -m workers.render_worker.service
  +-- voice_worker (optional)   -- python -m workers.voice_worker.service
  +-- supervisor (optional)     -- python -m workers.supervisor.service
```

### What Runs Where

| Component           | Where it runs      | Resource    |
|---------------------|--------------------|-------------|
| Telegram Bot        | Railway            | ~80 MB RAM  |
| n8n                 | Railway            | ~300 MB RAM |
| PostgreSQL          | Railway (managed)  | ~200 MB RAM |
| Redis               | Railway (managed)  | ~50 MB RAM  |
| Render Worker       | Railway (optional) | ~150 MB RAM |
| Voice Worker        | Railway (optional) | ~50 MB RAM  |
| Story Analysis (LLM)| OpenRouter cloud   | Free        |
| Image Generation    | Pollinations cloud | Free        |
| Image Gen (better)  | HuggingFace cloud  | Free        |
| Image Gen (best)    | Google Colab GPU   | Free        |
| Text-to-Speech      | Edge-TTS (Microsoft)| Free       |

---

## See Also

- [Deployment Guide](deployment-guide.md) -- Local Docker Compose deployment
- [Cloud Services Guide](cloud-services-guide.md) -- All cloud backend details
- [Colab Setup Guide](colab-setup-guide.md) -- Google Colab GPU notebooks
- [Worker Guide](worker-guide.md) -- Worker types and scaling
- [Troubleshooting](troubleshooting.md) -- Common issues and fixes
- [FAQ](faq.md) -- Frequently asked questions
