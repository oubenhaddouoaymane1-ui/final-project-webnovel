# CineOS Quick Start Guide

Get from zero to your first cinematic video in 5 minutes. CineOS uses a cloud-first architecture — heavy AI runs on free cloud services, so your local machine only needs Docker.

## Prerequisites

- Docker and Docker Compose v2+ running
- A Telegram bot token (get one from @BotFather)
- 4 GB+ RAM (8 GB recommended)
- Broadband internet connection

No GPU required. No 16GB RAM required. All heavy AI runs on free cloud APIs.

## 1. Configure (1 minute)

```bash
cd cinematic-production-os
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
TELEGRAM_BOT_TOKEN=your_token_here
```

Optional but recommended — add free cloud API keys for better quality:

```env
OPENROUTER_API_KEY=your_key_here    # Free LLM at openrouter.ai
HF_API_KEY=your_key_here            # Free image gen at huggingface.co
```

## 2. Launch (2 minutes)

```bash
./scripts/run_all.sh
```

Wait for the status summary to show all services as healthy.

## 3. Send Your First Novel (1 minute)

1. Open Telegram
2. Find your bot by its username
3. Send `/start`
4. Send a `.txt` file containing your novel (50-500,000 words)

## 4. Monitor Progress (1 minute)

Send `/status` to the bot to check progress. The bot will notify you at 25%, 50%, 75%, and 100% milestones.

You can also monitor in real-time:

```bash
# Watch n8n workflow executions
# Open http://localhost:5678 in your browser

# Watch logs
docker compose logs -f n8n
docker compose logs -f render_worker
```

## 5. Receive Your Video (ongoing)

When processing completes, the bot will send you the cinematic video file. Processing time depends on novel length and which cloud backends you configured:

| Novel Length | With Cloud APIs | Without (fallback) |
|-------------|----------------|-------------------|
| Short story (5k words) | 15-30 minutes | 30-60 minutes |
| Novella (30k words) | 2-4 hours | 4-8 hours |
| Full novel (100k+ words) | 6-12 hours | 12-24 hours |

## What Happens Behind the Scenes

When you send a novel file, CineOS executes this pipeline — analysis and generation run on free cloud services, assembly runs locally:

1. **Intake** — Validates and stores the text (local)
2. **Parsing** — Splits into chapters and scenes (cloud LLM via OpenRouter)
3. **Analysis** — Extracts themes, characters, conflicts (cloud LLM)
4. **Story Bible** — Builds comprehensive story bible (cloud LLM)
5. **Characters** — Profiles all characters with visual descriptions (cloud LLM)
6. **World Building** — Creates world bible with geography and lore (cloud LLM)
7. **Timeline** — Constructs chronological timeline (cloud LLM)
8. **Scene Planning** — Plans shot sequences per scene (cloud LLM)
9. **Shot Planning** — Plans individual shot details (cloud LLM)
10. **Prompt Building** — Assembles image generation prompts (cloud LLM)
11. **Image Generation** — Creates images via cloud GPU (Colab/HuggingFace/Pollinations)
12. **Quality Review** — AI reviews all generated assets (cloud vision LLM)
13. **Repair** — Fixes failed quality checks (cloud LLM + cloud GPU)
14. **Voice** — Generates narration via Edge-TTS (free cloud API)
15. **Animation** — Ken Burns effects (local CPU) or LivePortrait (cloud GPU)
16. **Render** — Assembles final video with FFmpeg (local CPU)
17. **Final Review** — Last quality check (cloud vision LLM)
18. **Delivery** — Sends video via Telegram

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/status` | Check current project progress |
| `/cancel` | Cancel current project |
| `/help` | Show help message |

## What You Can Customize

- **Language**: Set `DEFAULT_LANGUAGE` in `.env` (default: `en`)
- **Quality**: Adjust `QUALITY_THRESHOLD` in `.env` (default: `0.80`)
- **Parallelism**: Set `MAX_PARALLEL_JOBS` in `.env` (default: `4`)
- **Models**: Edit `config/models.yaml` to change AI models

## Next Steps

- Read the [Workflow Guide](workflow-guide.md) to understand each pipeline stage
- Read the [Worker Guide](worker-guide.md) to set up GPU workers
- Read the [Troubleshooting Guide](troubleshooting.md) if something goes wrong
