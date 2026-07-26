#!/bin/bash
set -euo pipefail

LOG_PREFIX="[CineOS n8n]"
N8N_PORT="${N8N_PORT:-5678}"

log() {
  echo "$LOG_PREFIX [$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

wait_for_postgres() {
  log "Waiting for PostgreSQL to be ready..."
  local retries=30
  local interval=2

  for i in $(seq 1 $retries); do
    if pg_isready -h postgres -p 5432 -U "${DB_POSTGRESDB_USER:-cineos}" -d "${DB_POSTGRESDB_DATABASE:-cineos}" >/dev/null 2>&1; then
      log "PostgreSQL is ready."
      return 0
    fi
    log "PostgreSQL not ready (attempt $i/$retries). Retrying in ${interval}s..."
    sleep "$interval"
  done

  log "ERROR: PostgreSQL did not become ready within $((retries * interval))s."
  exit 1
}

wait_for_n8n_api() {
  log "Waiting for n8n API to become available..."
  local retries=30
  local interval=2

  for i in $(seq 1 $retries); do
    if curl -sf "http://localhost:${N8N_PORT}/healthz" >/dev/null 2>&1; then
      log "n8n API is ready."
      return 0
    fi
    log "n8n API not ready (attempt $i/$retries). Retrying in ${interval}s..."
    sleep "$interval"
  done

  log "ERROR: n8n API did not become ready within $((retries * interval))s."
  return 1
}

import_workflows() {
  local workflows_dir="/workflows"

  if [ ! -d "$workflows_dir" ]; then
    log "No /workflows directory found. Skipping workflow import."
    return 0
  fi

  local json_count
  json_count=$(find "$workflows_dir" -maxdepth 1 -name '*.json' -type f | wc -l)

  if [ "$json_count" -eq 0 ]; then
    log "No workflow JSON files found in $workflows_dir. Skipping."
    return 0
  fi

  log "Found $json_count workflow file(s). Importing..."

  for workflow_file in "$workflows_dir"/*.json; do
    if [ ! -f "$workflow_file" ]; then
      continue
    fi
    local filename
    filename=$(basename "$workflow_file")
    log "Importing workflow: $filename"

    if n8n import:workflow --input="$workflow_file" 2>&1; then
      log "Successfully imported: $filename"
    else
      log "WARNING: Failed to import $filename. Continuing..."
    fi
  done

  log "Workflow import complete."
}

setup_credentials() {
  log "Setting up n8n credentials via API..."

  local n8n_url="http://localhost:${N8N_PORT}"
  local auth_header
  auth_header=$(echo -n "${N8N_BASIC_AUTH_USER:-admin}:${N8N_BASIC_AUTH_PASSWORD:-cineos_n8n}" | base64)

  create_credential() {
    local name="$1"
    local type="$2"
    local data="$3"

    local existing
    existing=$(curl -sf -H "Authorization: Basic $auth_header" "$n8n_url/api/v1/credentials" 2>/dev/null || echo "[]")

    if echo "$existing" | grep -q "\"name\":\"$name\""; then
      log "Credential '$name' already exists. Skipping."
      return 0
    fi

    local payload
    payload=$(cat <<EOF
{
  "name": "$name",
  "type": "$type",
  "data": $data
}
EOF
)

    local response
    response=$(curl -sf -X POST \
      -H "Authorization: Basic $auth_header" \
      -H "Content-Type: application/json" \
      -d "$payload" \
      "$n8n_url/api/v1/credentials" 2>&1) || true

    if echo "$response" | grep -q '"id"'; then
      log "Created credential: $name"
    else
      log "WARNING: Could not create credential '$name': $response"
    fi
  }

  create_credential "CineOS PostgreSQL" "postgres" '{
    "host": "postgres",
    "port": 5432,
    "database": "cineos",
    "user": "cineos",
    "password": "'"${POSTGRES_PASSWORD:-cineos_secret}"'",
    "ssl": false,
    "allowUnauthorizedCerts": false
  }'

  create_credential "CineOS Telegram Bot" "telegramApi" '{
    "accessToken": "'"${TELEGRAM_BOT_TOKEN:-}"'"
  }'

  create_credential "CineOS Redis" "redis" '{
    "host": "redis",
    "port": 6379,
    "database": 0
  }'

  log "Credential setup complete."
}

import_workflows_async() {
  import_workflows
  setup_credentials
}

main() {
  log "Starting CineOS n8n entrypoint..."
  log "Node environment: ${NODE_ENV:-production}"

  wait_for_postgres

  log "Starting n8n in background..."
  /docker-entrypoint.sh n8n &
  local n8n_pid=$!

  sleep 5

  if wait_for_n8n_api; then
    import_workflows_async
  else
    log "WARNING: n8n API not available. Workflow import skipped."
  fi

  log "n8n is running (PID: $n8n_pid). Handing off process..."
  wait $n8n_pid
}

main "$@"
