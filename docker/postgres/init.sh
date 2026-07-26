#!/bin/bash
set -euo pipefail

INIT_DIR="/docker-entrypoint-initdb.d"
LOG_PREFIX="[CineOS Init]"

log() {
  echo "$LOG_PREFIX [$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting CineOS database initialization..."
log "Scanning $INIT_DIR for SQL files..."

sql_files=()
while IFS= read -r -d '' file; do
  sql_files+=("$file")
done < <(find "$INIT_DIR" -maxdepth 1 -name '*.sql' -print0 | sort -z)

if [ ${#sql_files[@]} -eq 0 ]; then
  log "No SQL files found in $INIT_DIR. Skipping."
  exit 0
fi

log "Found ${#sql_files[@]} SQL file(s) to execute."

for sql_file in "${sql_files[@]}"; do
  filename=$(basename "$sql_file")
  log "Executing: $filename"
  
  start_time=$(date +%s)
  
  if psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$sql_file"; then
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    log "Completed: $filename (${duration}s)"
  else
    log "ERROR: Failed to execute $filename"
    exit 1
  fi
done

log "Database initialization complete. ${#sql_files[@]} file(s) processed."

log "Verifying database schema..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "\dt" || true

log "CineOS database ready."
