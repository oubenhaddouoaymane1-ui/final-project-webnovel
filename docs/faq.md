# CineOS Frequently Asked Questions

## General

### What is CineOS?

CineOS is a novel-to-cinematic AI production platform. It transforms novels sent via Telegram into cinematic videos through coordinated AI workflows, persistent memory, quality assurance, partial repair, and continuous learning.

### Is CineOS free?

Yes. CineOS uses a free-first stack: n8n Community Edition, PostgreSQL, Redis, FLUX (local), Kokoro/Edge-TTS, FFmpeg, LivePortrait, RealESRGAN, and Llama 3.2 — all free. Optional paid services include OpenRouter API and HuggingFace Inference.

### What hardware do I need?

- **Minimum:** 4 CPU cores, 16GB RAM, 50GB storage
- **Recommended:** 8 CPU cores, 32GB RAM, NVIDIA GPU with 8GB+ VRAM, 100GB+ SSD

Without a GPU, CineOS falls back to CPU-based generation via the Pollinations API (free, slower).

### How long does processing take?

| Novel Length | Estimated Time |
|-------------|----------------|
| Short story (5k words) | 15-30 minutes |
| Novella (30k words) | 2-4 hours |
| Full novel (100k+ words) | 6-12 hours |

Processing time depends on GPU availability, quality settings, and system load.

### What languages are supported?

CineOS supports any language that the underlying LLM and TTS engines support. Tested languages include English, Arabic, Spanish, French, German, and Japanese. The bot auto-detects the novel's language.

## Setup & Installation

### Can I run CineOS without Docker?

Yes. See the [Installation Guide](installation.md) for manual setup instructions. Docker is recommended for ease of deployment.

### Do I need a GPU?

No. CineOS works without a GPU using the Pollinations API for image generation. However, a GPU significantly improves generation speed (10-50x faster).

### How do I get a Telegram bot token?

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts to create your bot
4. Copy the token BotFather provides

### Can I run multiple CineOS instances?

Yes. Each instance needs its own PostgreSQL database and Telegram bot token. Use different `POSTGRES_DB` and `TELEGRAM_BOT_TOKEN` values.

## Usage

### What file formats are supported?

Currently `.txt` (plain text) and `.md` (Markdown) files. The text should be UTF-8 encoded, between 50 and 500,000 words.

### Can I process PDFs or EPUBs?

Not directly. Convert your PDF/EPUB to `.txt` first using tools like Calibre or `pdftotext`, then send the `.txt` file to the bot.

### Can I customize the output style?

Yes. Edit `config/models.yaml` to change:
- Art style (FLUX model settings)
- Voice (TTS backend and voice selection)
- Animation type (Ken Burns vs LivePortrait)
- Video quality (FFmpeg encoding settings)

### Can I resume a failed project?

Yes. CineOS uses checkpoints. If a project fails, the system can resume from the last successful checkpoint. The project state is stored in PostgreSQL.

### Can I process multiple novels at once?

By default, each user can have one active project at a time. To change this, edit `config/telegram.yaml`:

```yaml
limits:
  max_active_projects_per_user: 3
```

### How do I cancel a project?

Send `/cancel` to the Telegram bot. The project state changes to `cancelled` and all pending jobs are removed.

## Quality

### What quality threshold should I use?

The default `QUALITY_THRESHOLD=0.80` works well for most cases. Adjust in `.env`:

- `0.90` — Strict (fewer auto-approves, more repairs)
- `0.80` — Balanced (default)
- `0.60` — Lenient (faster, lower quality)

### Why are some images regenerated?

The quality pipeline scores each image. Images scoring below the threshold are sent for repair. If repair fails, the image is regenerated. This ensures consistent quality.

### How does character consistency work?

CineOS maintains character visual descriptions in the database. Each image prompt includes character-specific visual prompts generated from these descriptions. The quality worker checks character consistency after generation.

### Can I manually approve/reject images?

Not through the bot interface. You can modify the quality thresholds in `config/quality.yaml` or use the n8n UI to manually intervene.

## Workers

### How do I add more workers?

Increase the replica count in `docker-compose.yml` or use:

```bash
docker compose up --scale image_worker=3
```

### Can I run workers on different machines?

Yes. Workers connect to PostgreSQL and Redis via the network. Configure worker host/port in `config/workers.yaml` and ensure network connectivity.

### What GPU do I need?

- **Image generation:** NVIDIA GPU with 8GB+ VRAM (RTX 3060 or better)
- **Quality review:** NVIDIA GPU with 4GB+ VRAM
- **Animation:** NVIDIA GPU with 4GB+ VRAM (for LivePortrait)
- **Render/Voice:** No GPU needed

### How do I monitor worker health?

```bash
# Quick check
make health

# Detailed status
curl http://localhost:8000/api/workers | python -m json.tool

# Watch logs
docker compose logs -f image_worker
```

## Database

### How do I back up the database?

```bash
# Quick database backup
make backup-db

# Full system backup
./scripts/backup.sh

# Automated daily backups
./scripts/cron_backup.sh install
```

### How do I restore from backup?

```bash
# Restore database from file
make restore-db

# Full system restore
./scripts/restore.sh latest
```

### How do I access the database?

```bash
# Via Makefile
make db-shell

# Via Docker
docker exec -it cineos-postgres psql -U cineos -d cineos
```

### Can I use an external PostgreSQL instance?

Yes. Update the `POSTGRES_*` variables in your `.env` file to point to your external PostgreSQL server.

## n8n

### How do I access the n8n UI?

Open `http://localhost:5678` in your browser. Login with the credentials from your `.env` file (`N8N_BASIC_AUTH_USER` and `N8N_BASIC_AUTH_PASSWORD`).

### How do I add a new workflow?

1. Create it in the n8n UI
2. Export the JSON
3. Save it to `workflows/` or `n8n-workflows/`
4. See the [Workflow Guide](workflow-guide.md) for details

### Why isn't my workflow triggering?

Check that:
1. The workflow is active in n8n
2. The webhook URL is correctly configured
3. The project state matches the workflow's trigger condition

### How do I debug a workflow?

1. Open n8n UI at `http://localhost:5678`
2. Click on the workflow
3. Go to "Executions" tab
4. Click on a failed execution to see the error

## Troubleshooting

### The bot starts but doesn't respond to files

1. Check bot logs: `docker compose logs -f telegram_bot`
2. Verify n8n is running: `curl http://localhost:5678/healthz`
3. Verify the webhook URL is reachable from Telegram

### Image generation is very slow

1. Check GPU usage: `nvidia-smi`
2. Reduce image resolution in `config/models.yaml`
3. Reduce steps (e.g., from 30 to 20)
4. Use Pollinations as fallback if GPU is unavailable

### The final video has no audio

1. Check voice worker is running: `curl http://localhost:8400/health`
2. Check voice worker logs: `docker compose logs -f voice_worker`
3. Verify narration text was generated for shots

### Out of memory errors

1. Reduce `MAX_PARALLEL_JOBS` in `.env`
2. Reduce worker `max_concurrent` in `config/workers.yaml`
3. Increase Docker memory limits
4. Reduce image resolution/steps

### "Connection refused" errors

1. Check the target service is running: `docker compose ps`
2. Check the host/port configuration
3. Check the Docker network: `docker network inspect cinematic-production-os_cineos-network`

## Advanced

### How do I change the AI model?

Edit `config/models.yaml`:

```yaml
llm:
  ollama:
    model: "llama3.2"       # Change to any Ollama model
  openrouter:
    model: "meta-llama/llama-3.2-3b-instruct"  # Or OpenRouter model
```

### How do I add a new TTS voice?

1. Check available voices: `edge-tts --list-voices`
2. Add to `config/models.yaml` under `voice.backends.edge_tts.voices`
3. Reference in prompts by language code

### Can I run CineOS on a cloud VM?

Yes. Recommended cloud setup:
- **GPU:** AWS g4dn.xlarge, GCP a2-highgpu-1g, or Azure NC6s_v3
- **CPU-only:** Any instance with 16GB+ RAM

Ensure Docker and Docker Compose are installed, and open ports 5678, 8000-8500.

### How do I contribute?

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test`
5. Run linting: `make lint`
6. Submit a pull request

### Where can I find more help?

- [Installation Guide](installation.md)
- [Workflow Guide](workflow-guide.md)
- [Worker Guide](worker-guide.md)
- [Troubleshooting Guide](troubleshooting.md)
- Architecture docs in `architecture/`
- API specification in `api/openapi.yaml`
