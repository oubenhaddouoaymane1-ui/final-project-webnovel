#!/usr/bin/env bash
##############################################################################
# CineOS — Railway Deployment Script
# Prerequisites: railway CLI authenticated (railway login)
##############################################################################
set -euo pipefail

PROJECT_NAME="${RAILWAY_PROJECT:-cineos}"

echo "═══════════════════════════════════════════════════════════════"
echo " CineOS — Railway Deployment"
echo " Project: ${PROJECT_NAME}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Check/create project ──────────────────────────────────────────
echo ""
echo "→ Checking Railway project..."
if ! railway project list 2>/dev/null | grep -q "${PROJECT_NAME}"; then
  echo "  Creating project: ${PROJECT_NAME}"
  railway project create "${PROJECT_NAME}"
else
  echo "  ✓ Project ${PROJECT_NAME} exists"
fi

# ── Step 2: Add PostgreSQL plugin ─────────────────────────────────────────
echo ""
echo "→ Adding PostgreSQL plugin..."
railway plugin add postgresql --project "${PROJECT_NAME}" \
  2>/dev/null || echo "  (PostgreSQL may already exist)"

# ── Step 3: Add Redis plugin ──────────────────────────────────────────────
echo ""
echo "→ Adding Redis plugin..."
railway plugin add redis --project "${PROJECT_NAME}" \
  2>/dev/null || echo "  (Redis may already exist)"

# ── Step 4: Set environment variables ─────────────────────────────────────
echo ""
echo "→ Setting environment variables..."
if [ -f .env ]; then
  set -a
  source .env
  set +a

  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && railway variables set "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}" --project "${PROJECT_NAME}"
  [ -n "${OPENROUTER_API_KEY:-}" ] && railway variables set "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}" --project "${PROJECT_NAME}"
  [ -n "${HF_API_KEY:-}" ] && railway variables set "HF_API_KEY=${HF_API_KEY}" --project "${PROJECT_NAME}"
  [ -n "${N8N_BASIC_AUTH_PASSWORD:-}" ] && railway variables set "N8N_BASIC_AUTH_PASSWORD=${N8N_BASIC_AUTH_PASSWORD}" --project "${PROJECT_NAME}"
  [ -n "${N8N_ENCRYPTION_KEY:-}" ] && railway variables set "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}" --project "${PROJECT_NAME}"
  echo "  ✓ Variables set from .env"
else
  echo "  ⚠ No .env file found. Set variables via Railway dashboard."
fi

# ── Step 5: Deploy ────────────────────────────────────────────────────────
echo ""
echo "→ Deploying to Railway..."
railway up --service "${PROJECT_NAME}"

# ── Step 6: Generate domain ───────────────────────────────────────────────
echo ""
echo "→ Generating public domain..."
railway domain --project "${PROJECT_NAME}" --service "${PROJECT_NAME}" \
  2>/dev/null || echo "  (domain may already exist)"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " ✓ Deployment complete!"
echo ""
echo " Next steps:"
echo "   1. Open Railway dashboard to get your app URL"
echo "   2. Apply database schema via Railway's PostgreSQL shell"
echo "   3. Import n8n workflows"
echo "   4. Set Telegram webhook to your Railway public URL"
echo "═══════════════════════════════════════════════════════════════"
