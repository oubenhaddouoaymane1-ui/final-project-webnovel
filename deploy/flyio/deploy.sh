#!/usr/bin/env bash
##############################################################################
# CineOS — Fly.io Deployment Script
# Prerequisites: flyctl CLI authenticated (fly auth login)
##############################################################################
set -euo pipefail

APP_NAME="${FLY_APP_NAME:-cineos}"

echo "═══════════════════════════════════════════════════════════════"
echo " CineOS — Fly.io Deployment"
echo " App: ${APP_NAME}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Check if app exists ───────────────────────────────────────────
echo ""
echo "→ Checking app status..."
if ! fly apps list | grep -q "${APP_NAME}"; then
  echo "  Creating app: ${APP_NAME}"
  fly apps create "${APP_NAME}"
else
  echo "  ✓ App ${APP_NAME} exists"
fi

# ── Step 2: Create Fly Postgres ───────────────────────────────────────────
echo ""
echo "→ Setting up Fly Postgres..."
if ! fly postgres list | grep -q "cineos-db"; then
  fly postgres create \
    --name cineos-db \
    --app "${APP_NAME}" \
    --region iad \
    --initial-cluster-size 1 \
    --vm-size shared-cpu-1x
else
  echo "  ✓ Postgres cineos-db exists"
fi

# ── Step 3: Create Fly Redis ──────────────────────────────────────────────
echo ""
echo "→ Setting up Fly Redis..."
fly redis create \
  --name cineos-redis \
  --region iad \
  2>/dev/null || echo "  (Redis may already exist)"

# ── Step 4: Set secrets ───────────────────────────────────────────────────
echo ""
echo "→ Setting secrets..."
if [ -f .env ]; then
  set -a
  source .env
  set +a

  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && fly secrets set TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}" --app "${APP_NAME}"
  [ -n "${OPENROUTER_API_KEY:-}" ] && fly secrets set OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" --app "${APP_NAME}"
  [ -n "${HF_API_KEY:-}" ] && fly secrets set HF_API_KEY="${HF_API_KEY}" --app "${APP_NAME}"
  [ -n "${N8N_BASIC_AUTH_PASSWORD:-}" ] && fly secrets set N8N_BASIC_AUTH_PASSWORD="${N8N_BASIC_AUTH_PASSWORD}" --app "${APP_NAME}"
  [ -n "${N8N_ENCRYPTION_KEY:-}" ] && fly secrets set N8N_ENCRYPTION_KEY="${N8N_ENCRYPTION_KEY}" --app "${APP_NAME}"
  echo "  ✓ Secrets set from .env"
else
  echo "  ⚠ No .env file found. Set secrets manually:"
  echo "    fly secrets set TELEGRAM_BOT_TOKEN=xxx --app ${APP_NAME}"
fi

# ── Step 5: Deploy ────────────────────────────────────────────────────────
echo ""
echo "→ Deploying to Fly.io..."
fly deploy --app "${APP_NAME}" --config deploy/flyio/fly.toml

# ── Step 6: Apply database schema ─────────────────────────────────────────
echo ""
echo "→ Applying database schema..."
fly ssh console --app "${APP_NAME}" -C "echo 'Schema must be applied via fly proxy'" \
  2>/dev/null || true
echo "  Apply schema manually:"
echo "    fly proxy 5432:5432 --app ${APP_NAME}"
echo "    psql -h 127.0.0.1 -U cineos -d cineos < sql/init.sql"
echo "    psql -h 127.0.0.1 -U cineos -d cineos < database/seed/config_defaults.sql"

# ── Step 7: Set up n8n persistence ────────────────────────────────────────
echo ""
echo "→ Creating persistent volume for n8n data..."
fly volumes create n8n_data \
  --region iad \
  --size 1 \
  --app "${APP_NAME}" \
  2>/dev/null || echo "  (volume may already exist)"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " ✓ Deployment complete!"
echo ""
echo " Access n8n:"
echo "   fly apps list --format json | jq -r '.[] | select(.Name==\"'${APP_NAME}'\") | .Hostname'"
echo ""
echo " Next steps:"
echo "   1. Apply database schema (see above)"
echo "   2. Open n8n and import workflows"
echo "   3. Set Telegram webhook to your app's public URL"
echo "═══════════════════════════════════════════════════════════════"
