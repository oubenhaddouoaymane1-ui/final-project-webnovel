#!/bin/bash
set -euo pipefail

LOG_PREFIX="[CineOS Render]"

log() {
  echo "$LOG_PREFIX [$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

mkdir -p "${RENDER_DIR:-/render/output}" "${TEMP_DIR:-/render/tmp}"

log "Starting CineOS FFmpeg Render Worker..."
log "Render dir: ${RENDER_DIR:-/render/output}"
log "Temp dir: ${TEMP_DIR:-/render/tmp}"
log "Max concurrent jobs: ${MAX_CONCURRENT_JOBS:-2}"

exec python3 /app/render_server.py
