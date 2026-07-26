#!/usr/bin/env bash
##############################################################################
# CineOS — Google Cloud Run Deployment Script
# Prerequisites: gcloud CLI authenticated, project set
##############################################################################
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${GCP_REGION:-us-central1}"
REPO="cineos"

echo "═══════════════════════════════════════════════════════════════"
echo " CineOS — Google Cloud Run Deployment"
echo " Project: ${PROJECT_ID}"
echo " Region:  ${REGION}"
echo "═══════════════════════════════════════════════════════════════"

# ── Step 1: Enable required APIs ──────────────────────────────────────────
echo ""
echo "→ Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT_ID}"

# ── Step 2: Create Artifact Registry repo ─────────────────────────────────
echo ""
echo "→ Creating Artifact Registry repo..."
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  2>/dev/null || echo "  (repo already exists)"

# ── Step 3: Create Cloud SQL instance ─────────────────────────────────────
echo ""
echo "→ Creating Cloud SQL PostgreSQL instance..."
gcloud sql instances create cineos-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  2>/dev/null || echo "  (instance already exists)"

# ── Step 4: Create database and user ──────────────────────────────────────
echo ""
echo "→ Setting up database..."
gcloud sql databases create cineos --instance=cineos-db --project="${PROJECT_ID}" \
  2>/dev/null || echo "  (database already exists)"

# ── Step 5: Store secrets in Secret Manager ───────────────────────────────
echo ""
echo "→ Storing secrets..."
for SECRET in TELEGRAM_BOT_TOKEN OPENROUTER_API_KEY POSTGRES_PASSWORD HF_API_KEY; do
  VALUE="${!SECRET:-}"
  if [ -n "${VALUE}" ]; then
    echo "${VALUE}" | gcloud secrets create "${SECRET,,}" \
      --data-file=- \
      --project="${PROJECT_ID}" \
      2>/dev/null || echo "${VALUE}" | gcloud secrets versions add "${SECRET,,}" \
      --data-file=- \
      --project="${PROJECT_ID}"
    echo "  ✓ ${SECRET} stored"
  else
    echo "  ⚠ ${SECRET} not set, skipping"
  fi
done

# ── Step 6: Build and push images ─────────────────────────────────────────
echo ""
echo "→ Building and pushing Docker images..."
gcloud builds submit \
  --config=deploy/gcp/cloudbuild.yaml \
  --project="${PROJECT_ID}" \
  .

# ── Step 7: Initialize database schema ────────────────────────────────────
echo ""
echo "→ Database schema must be applied manually via Cloud SQL Proxy:"
echo "  1. Install: https://cloud.google.com/sql/docs/postgres/connect-auth-proxy"
echo "  2. Run: cloud-sql-proxy ${PROJECT_ID}:${REGION}:cineos-db"
echo "  3. Apply: psql -h 127.0.0.1 -U cineos -d cineos < sql/init.sql"
echo "  4. Seed:  psql -h 127.0.0.1 -U cineos -d cineos < database/seed/config_defaults.sql"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " ✓ Deployment complete!"
echo ""
echo " Services:"
echo "   Cloud Run services deployed to ${REGION}"
echo "   Cloud SQL: ${PROJECT_ID}:${REGION}:cineos-db"
echo ""
echo " Next steps:"
echo "   1. Apply database schema (see above)"
echo "   2. Set Telegram webhook:"
echo "      curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \\"
echo "        -d url=https://cineos-telegram-bot-<hash>-uc.a.run.app/webhook"
echo "   3. Open n8n: https://cineos-n8n-<hash>-uc.a.run.app"
echo "═══════════════════════════════════════════════════════════════"
