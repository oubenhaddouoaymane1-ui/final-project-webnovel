# CineOS — Novel-to-Cinematic AI Production Platform

A production-ready, scalable, resumable operating system that transforms novels sent via Telegram into cinematic videos through coordinated AI workflows, persistent memory, quality assurance, partial repair, continuous learning, and cloud AI workers.

## Architecture — Cloud-First, Local Controller

```
                         YOUR PC (lightweight)              FREE CLOUD SERVICES
                         ====================              ====================
                         ┌──────────────────┐              ┌──────────────────┐
Telegram User ──────────►│ Telegram Bot     │              │ Pollinations.ai  │
                         │                  │   HTTP API   │ (image gen)      │
                         │ n8n Orchestrator │─────────────►├──────────────────┤
                         │                  │              │ OpenRouter       │
                         │ PostgreSQL       │◄─────────────│ (LLM + Vision)  │
                         │ Redis            │   results    ├──────────────────┤
                         │ FFmpeg Render    │              │ HuggingFace API  │
                         │ Edge TTS         │              │ (CLIP, SDXL)     │
                         │ Cloud Bridge     │              ├──────────────────┤
                         └──────────────────┘              │ Google Colab     │
                                                           │ (ComfyUI+FLUX)   │
                                                           │ (RealESRGAN)     │
                                                           │ (LivePortrait)   │
                                                           └──────────────────┘
```

**Your PC only runs:** n8n, PostgreSQL, Redis, Telegram bot, FFmpeg, Edge TTS, workflow orchestration
**Cloud services handle:** Image generation, quality review, super resolution, animation, LLM analysis

**Core Principles:**
- Local PC is a lightweight controller — no GPU required (4GB RAM minimum)
- All heavy AI runs on free cloud services (Pollinations, OpenRouter, HuggingFace, Google Colab)
- n8n Community Edition is the ONLY orchestrator
- PostgreSQL is the single source of truth
- Every workflow communicates through the database, never directly
- Quality gates are mandatory before progression
- Partial repair preferred over full regeneration

## Quick Start

### Prerequisites
- Docker & Docker Compose v2+
- 4 GB+ RAM (any CPU, no GPU needed)
- Broadband internet connection
- Telegram Bot Token (from @BotFather)
- Free account on OpenRouter (for LLM + vision)

No GPU required — all heavy AI runs on free cloud services.

### 1. Clone & Configure
```bash
git clone <repository-url>
cd cinematic-production-os
cp .env.example .env
# Edit .env with your settings (at minimum: TELEGRAM_BOT_TOKEN)
```

### 2. Launch Everything
```bash
chmod +x scripts/run_all.sh
./scripts/run_all.sh
```

This single command will:
1. Start PostgreSQL, Redis, n8n, all workers, and Telegram bot
2. Run database migrations automatically
3. Import all 25 n8n workflows
4. Register AI workers
5. Connect the Telegram bot
6. Print a status summary

### 3. Start Using
Open Telegram, find your bot, and send a `.txt` file with a novel.

### Manual Launch (Alternative)
```bash
# Start infrastructure
docker compose up -d

# Run migrations
python scripts/migrate_db.py

# Import workflows
python scripts/setup_n8n.py

# Register workers
python scripts/register_workers.py
```

## Project Structure

```
cinematic-production-os/
├── docker/                    # Docker infrastructure
│   ├── docker-compose.yml     # Production compose
│   ├── postgres/              # PostgreSQL init scripts
│   ├── n8n/                   # n8n entrypoint & config
│   ├── workers/               # Worker Dockerfiles
│   ├── comfyui/               # ComfyUI config
│   ├── ffmpeg/                # FFmpeg render service
│   ├── voice/                 # Voice/TTS service
│   └── monitoring/            # Prometheus + Grafana
│
├── database/                  # PostgreSQL schema
│   ├── schema.sql             # All tables & enums
│   ├── indexes.sql            # Performance indexes
│   ├── constraints.sql        # Foreign keys & constraints
│   ├── views.sql              # Analytical views
│   ├── functions.sql          # Utility functions
│   ├── triggers.sql           # Auto-update triggers
│   ├── migrations/            # Migration tracking
│   └── seed/                  # Default data
│
├── workflows/                 # 25 n8n workflow JSONs
│   ├── 001_telegram_intake.json
│   ├── 002_project_orchestrator.json
│   ├── 003_story_parser.json
│   ├── ...
│   └── 025_learning_engine.json
│
├── prompts/                   # LLM prompt templates (Jinja2)
│   ├── story/                 # Story analysis prompts
│   ├── character/             # Character extraction
│   ├── world/                 # World building
│   ├── shot/                  # Shot planning
│   ├── quality/               # Quality review
│   └── repair/                # Repair prompts
│
├── workers/                   # Python worker services
│   ├── worker_base.py         # Base worker class
│   ├── cloud_bridge/          # Cloud dispatch (Pollinations, HF, Colab)
│   ├── render_worker/         # FFmpeg video rendering (local)
│   ├── voice_worker/          # Edge TTS (local)
│   └── supervisor/            # Worker management
│
├── api/                       # API specifications
│   ├── openapi.yaml           # OpenAPI 3.0 spec
│   ├── schemas/               # JSON Schemas
│   ├── examples/              # Request/response examples
│   └── contracts/             # Webhook contracts
│
├── config/                    # Configuration files
│   ├── settings.yaml          # System settings
│   ├── models.yaml            # AI model configuration
│   ├── workers.yaml           # Worker configuration
│   ├── quality.yaml           # Quality thresholds
│   └── telegram.yaml          # Bot configuration
│
├── scripts/                   # Setup & utility scripts
│   ├── run_all.sh             # One-command startup
│   ├── migrate_db.py          # Database migration
│   ├── setup_n8n.py           # n8n workflow import
│   └── register_workers.py    # Worker registration
│
├── src/                       # Application source code
│   └── telegram/              # Telegram bot bridge
│
├── docker-compose.yml         # Main Docker Compose
├── Dockerfile                 # Telegram bot container
├── Makefile                   # Development commands
├── .env.example               # Environment variables
├── requirements.txt           # Python dependencies
└── architecture/              # Architecture documentation
```

## Workflows (25 Total)

| # | Workflow | Description |
|---|----------|-------------|
| 001 | Telegram Intake | Receives novels via Telegram, creates projects |
| 002 | Project Orchestrator | Master controller — dispatches all production workflows |
| 003 | Story Parser | Splits novels into chapters and scenes |
| 004 | Story Intelligence | Analyzes themes, conflicts, character arcs |
| 005 | Story Bible Builder | Creates comprehensive story bible |
| 006 | Character Engine | Extracts and profiles all characters |
| 007 | World Engine | Builds world bible with geography and lore |
| 008 | Timeline Engine | Constructs chronological timeline |
| 009 | Scene Planner | Plans shot sequences per scene |
| 010 | Shot Planner | Plans individual shot details |
| 011 | Fight Director | Choreographs action sequences |
| 012 | Emotion Director | Maps emotional arcs across scenes |
| 013 | Prompt Builder | Assembles final image generation prompts |
| 014 | Job Dispatcher | Creates and queues generation jobs |
| 015 | Image Generation | Orchestrates image creation via workers |
| 016 | Quality AI | Reviews generated assets for quality |
| 017 | Repair Engine | Fixes failed quality checks |
| 018 | Voice Engine | Generates TTS narration |
| 019 | Music Director | Creates music/soundtrack plan |
| 020 | Animation Engine | Animates static images into video clips |
| 021 | Render Manager | Assembles final video with FFmpeg |
| 022 | Super Resolution | Upscales images and video frames |
| 023 | Final Review | Last quality check before delivery |
| 024 | Delivery | Sends final video via Telegram |
| 025 | Learning Engine | Analyzes completed projects for improvement |

## Workers — Local vs Cloud

### Local Workers (run on your PC — lightweight only)

| Worker | Port | Hardware | Tasks |
|--------|------|----------|-------|
| Supervisor | 8000 | CPU only | Worker management, job assignment |
| Cloud Bridge | 8600 | CPU only | Dispatches jobs to cloud APIs |
| Render Worker | 8300 | CPU only | FFmpeg video assembly |
| Voice Worker | 8400 | CPU only | Edge TTS narration (free API) |

### Cloud Workers (dispatched to free cloud services)

| Service | Provider | Tasks | Cost |
|---------|----------|-------|------|
| Image Generation | Pollinations.ai | FLUX image generation | Free |
| Image Generation | Google Colab | ComfyUI + FLUX (optional) | Free |
| LLM Analysis | OpenRouter | Story parsing, character extraction | Free tier |
| Quality Review | OpenRouter | Gemini Flash vision QA | Free tier |
| Super Resolution | Google Colab | RealESRGAN upscaling | Free |
| Animation | FFmpeg (local) | Ken Burns pan/zoom | Free |
| Animation | Google Colab | LivePortrait (optional) | Free |

## State Machine

Projects progress through 27 states:

```
received → validated → parsed → understood → biblified → characterized
→ worldbuilt → timeline_verified → planned → prompted → queued
→ generating → generated → reviewing → [repairing →] approved
→ voiced → musicked → animated → rendering → rendered
→ super_resolution → final_review → delivered → learned → completed
```

Terminal states: `completed`, `failed`, `cancelled`
Pause states: `waiting`, `paused`, `manual_attention`

## Quality Pipeline

1. **Auto-generate** quality scores per asset
2. **Review** with multi-criteria checks (face consistency, prompt alignment, composition)
3. **Score** on 0-1 scale with weighted criteria
4. **Decision:** Auto-approve (>0.90), Minor repair (0.80-0.90), Partial repair (0.60-0.80), Regenerate (<0.60)
5. **Repair** with priority: Face → Eyes → Hands → Weapon → Armour → Outfit → Background → Lighting
6. **Re-review** after repair
7. **Escalate** to manual after 3 failed attempts

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| POSTGRES_HOST | postgres | PostgreSQL hostname |
| POSTGRES_PORT | 5432 | PostgreSQL port |
| POSTGRES_DB | cineos | Database name |
| POSTGRES_USER | cineos | Database user |
| POSTGRES_PASSWORD | changeme | Database password |
| TELEGRAM_BOT_TOKEN | — | Telegram bot token (required) |
| N8N_PORT | 5678 | n8n web UI port |
| QUALITY_THRESHOLD | 0.80 | Minimum quality score |
| MAX_RETRY | 3 | Max retry attempts |
| MAX_PARALLEL_JOBS | 4 | Concurrent job limit |
| LOG_LEVEL | INFO | Logging level |

### AI Models (config/models.yaml)

- **LLM:** OpenRouter (Llama 3.2 free tier) for story analysis, character extraction
- **Image:** Pollinations.ai (FLUX) — free, no API key, no GPU
- **Quality Review:** OpenRouter (Gemini Flash) — free vision analysis
- **Voice:** Edge TTS (Microsoft) — free, 20+ languages
- **Animation:** FFmpeg Ken Burns — local CPU, lightweight
- **Super Resolution:** Google Colab + RealESRGAN — free GPU when needed
- **Optional:** Google Colab for ComfyUI+FLUX, LivePortrait, Kokoro TTS

## Free-First Stack

| Component | Technology | Runs On | Cost |
|-----------|-----------|---------|------|
| Orchestrator | n8n Community Edition | Local | Free |
| Database | PostgreSQL 16 | Local | Free |
| Queue | Redis 7 | Local | Free |
| Image Gen | Pollinations.ai (FLUX) | Cloud | Free |
| LLM | OpenRouter (Llama 3.2) | Cloud | Free tier |
| Vision QA | OpenRouter (Gemini Flash) | Cloud | Free tier |
| TTS | Edge TTS (Microsoft) | Local | Free |
| Video | FFmpeg | Local | Free |
| Animation | FFmpeg Ken Burns | Local | Free |
| Super Resolution | RealESRGAN (Colab) | Cloud | Free |
| Containers | Docker | Local | Free |

## Makefile Commands

```bash
make up              # Start all services
make down            # Stop all services
make restart         # Restart all services
make logs            # View all logs
make status          # Show service status
make health          # Check all health endpoints
make build           # Build all images
make db-shell        # Open psql shell
make db-reset        # Drop and recreate database
make db-migrate      # Run pending migrations
make import-workflows # Import workflows to n8n
make test            # Run test suite
make lint            # Run linting
make clean           # Remove temp/cache/logs
make backup-db       # Backup database
make restore-db      # Restore database backup
```

## API

REST API available at `http://localhost:8000`. See `api/openapi.yaml` for full specification.

Key endpoints:
- `GET /health` — System health
- `GET /api/workers` — List workers
- `POST /api/jobs` — Create job
- `POST /api/generate/image` — Generate image
- `POST /api/quality/review` — Submit for review
- `POST /webhook/telegram_intake` — Telegram webhook

## Documentation

- `docs/deployment-guide.md` — Complete cloud-first deployment guide
- `docs/cloud-services-guide.md` — Cloud services reference and configuration
- `docs/colab-setup-guide.md` — Google Colab GPU setup guide
- `docs/quickstart.md` — 5-minute getting started
- `docs/installation.md` — Full installation reference
- `docs/worker-guide.md` — Worker types and scaling
- `architecture/01-system-architecture.md` — System overview
- `architecture/02-layer-model-deployment.md` — Layer model
- `architecture/03-state-machine-database.md` — State machine & DB
- `architecture/04-n8n-workflow-architecture.md` — Workflow specs
- `architecture/06-quality-repair-learning-workers.md` — Quality & workers
- `api/openapi.yaml` — API specification

## License

MIT
