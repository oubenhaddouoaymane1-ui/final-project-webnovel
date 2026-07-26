#!/usr/bin/env bash
# CineOS — Startup Script (Cloud-First Architecture)
# Local PC runs ONLY lightweight services.
# Heavy AI workloads run on free cloud services (Pollinations, OpenRouter, Colab, Edge TTS).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─── Check prerequisites ───
info "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    error "Python 3 not found"; exit 1
fi

if ! command -v docker &>/dev/null; then
    warn "Docker not found — will try to run locally"
fi

# ─── Setup virtual environment ───
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# ─── Install dependencies ───
info "Installing dependencies (lightweight — no GPU libraries)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ─── Create directories ───
for dir in generated/images generated/audio generated/video temp logs; do
    mkdir -p "$dir"
done

# ─── Check for .env file ───
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        warn ".env not found. Copy .env.example to .env and set your tokens."
        warn "  cp .env.example .env"
        warn "  nano .env"
        echo ""
    fi
fi

# Load .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# ─── Check required tokens ───
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    warn "TELEGRAM_BOT_TOKEN not set. Bot will not start."
    warn "Set it in .env or export TELEGRAM_BOT_TOKEN=your_token"
    echo ""
fi

if [ -z "${OPENROUTER_KEY:-}" ] && [ -z "${OPENROUTER_API_KEY:-}" ]; then
    warn "OPENROUTER_KEY not set. LLM reasoning will not work."
    warn "Get a free key at https://openrouter.ai"
fi

# ─── Cloud service status ───
info "Cloud services (no local GPU required):"
info "  Image generation:  Pollinations.ai (free, no API key)"
info "  LLM reasoning:     OpenRouter (free tier available)"
info "  Vision QA:         OpenRouter — Gemini Flash (free)"
info "  Narration:         Microsoft Edge TTS (free)"
info "  Super resolution:  Google Colab — RealESRGAN (free GPU)"
info "  Animation:         Google Colab — LivePortrait (free GPU)"
echo ""

# ─── Start the pipeline ───
info "Starting CineOS Telegram Bot (cloud-first)..."
python -m src.telegram
