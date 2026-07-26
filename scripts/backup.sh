#!/usr/bin/env bash
##############################################################################
# CineOS — Full Backup Script
# Creates timestamped backups of PostgreSQL, workflows, prompts, config,
# and learning data. Rotates old backups to keep disk usage bounded.
##############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Configuration ──────────────────────────────────────────────────────────
BACKUP_DIR="${PROJECT_ROOT}/backups"
LOG_DIR="${PROJECT_DIR:-$PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/backup_$(date +%Y%m%d_%H%M%S).log"
RETENTION_DAILY=7
RETENTION_WEEKLY=4

# ── Colors ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
info()    { echo -e "${GREEN}[INFO]${NC}  $(timestamp) $*" | tee -a "$LOG_FILE"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $(timestamp) $*" | tee -a "$LOG_FILE"; }
error()   { echo -e "${RED}[ERROR]${NC} $(timestamp) $*" | tee -a "$LOG_FILE"; }
section() { echo -e "${BLUE}[====]${NC} $(timestamp) $*" | tee -a "$LOG_FILE"; }

# ── Parse arguments ────────────────────────────────────────────────────────
DRY_RUN=false
VERBOSE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true;  shift ;;
        --verbose)  VERBOSE=true;  shift ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--verbose]"
            echo ""
            echo "Options:"
            echo "  --dry-run   Show what would be done without executing"
            echo "  --verbose   Print detailed output"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *) error "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Setup ──────────────────────────────────────────────────────────────────
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DAY=$(date +%Y%m%d)
BACKUP_WEEK=$(date +%Y%W)
ERRORS=0

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

info "╔══════════════════════════════════════════════════════════════╗"
info "║  CineOS Backup — $BACKUP_TS                          ║"
info "╚══════════════════════════════════════════════════════════════╝"
info "Project root: $PROJECT_ROOT"
info "Backup dir:   $BACKUP_DIR"
info "Log file:     $LOG_FILE"
if $DRY_RUN; then
    warn "DRY RUN MODE — no changes will be made"
fi

##############################################################################
# 1. PostgreSQL Backup
##############################################################################
section "1/5 — PostgreSQL backup"

PG_DUMP_FILE="${BACKUP_DIR}/postgres_${BACKUP_TS}.sql"
PG_DUMP_GZ="${PG_DUMP_FILE}.gz"

dump_postgres() {
    if docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        info "Dumping PostgreSQL via docker exec..."
        docker exec cineos-postgres pg_dump \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            --no-owner \
            --no-privileges \
            --clean \
            --if-exists \
            2>>"$LOG_FILE" | gzip > "$PG_DUMP_GZ"
    elif command -v pg_dump &>/dev/null; then
        info "Dumping PostgreSQL via local pg_dump..."
        pg_dump \
            -h "${POSTGRES_HOST:-localhost}" \
            -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            --no-owner \
            --no-privileges \
            --clean \
            --if-exists \
            2>>"$LOG_FILE" | gzip > "$PG_DUMP_GZ"
    else
        error "Cannot connect to PostgreSQL — no docker container or pg_dump found"
        return 1
    fi
}

if $DRY_RUN; then
    info "  Would dump PostgreSQL to $PG_DUMP_GZ"
else
    if dump_postgres; then
        PG_SIZE=$(du -sh "$PG_DUMP_GZ" 2>/dev/null | cut -f1)
        info "  PostgreSQL backup complete: $PG_DUMP_GZ ($PG_SIZE)"
    else
        error "  PostgreSQL backup FAILED"
        ((ERRORS++))
    fi
fi

##############################################################################
# 2. Workflow JSONs Backup
##############################################################################
section "2/5 — Workflow backup"

WORKFLOW_BACKUP="${BACKUP_DIR}/workflows_${BACKUP_DAY}"

backup_workflows() {
    local src_dirs=("${PROJECT_ROOT}/workflows" "${PROJECT_ROOT}/n8n-workflows")
    mkdir -p "$WORKFLOW_BACKUP"
    for src in "${src_dirs[@]}"; do
        if [ -d "$src" ]; then
            local dir_name=$(basename "$src")
            mkdir -p "${WORKFLOW_BACKUP}/${dir_name}"
            cp -a "$src"/*.json "${WORKFLOW_BACKUP}/${dir_name}/" 2>/dev/null || true
            local count=$(find "${WORKFLOW_BACKUP}/${dir_name}" -name '*.json' | wc -l)
            info "  Copied $count workflow(s) from $dir_name"
        fi
    done
    # Compress
    if ! $DRY_RUN; then
        tar -czf "${WORKFLOW_BACKUP}.tar.gz" -C "$BACKUP_DIR" "$(basename "$WORKFLOW_BACKUP")" 2>>"$LOG_FILE"
        rm -rf "$WORKFLOW_BACKUP"
        info "  Compressed to ${WORKFLOW_BACKUP}.tar.gz"
    fi
}

if $DRY_RUN; then
    info "  Would copy workflows from workflows/ and n8n-workflows/"
else
    if backup_workflows; then
        info "  Workflow backup complete"
    else
        error "  Workflow backup FAILED"
        ((ERRORS++))
    fi
fi

##############################################################################
# 3. Prompt Templates Backup
##############################################################################
section "3/5 — Prompt template backup"

PROMPT_BACKUP="${BACKUP_DIR}/prompts_${BACKUP_DAY}"

backup_prompts() {
    local src="${PROJECT_ROOT}/prompts"
    if [ -d "$src" ]; then
        mkdir -p "$PROMPT_BACKUP"
        cp -a "$src"/* "$PROMPT_BACKUP/" 2>/dev/null || true
        local count=$(find "$PROMPT_BACKUP" -type f | wc -l)
        info "  Copied $count prompt template(s)"
        # Compress
        if ! $DRY_RUN; then
            tar -czf "${PROMPT_BACKUP}.tar.gz" -C "$BACKUP_DIR" "$(basename "$PROMPT_BACKUP")" 2>>"$LOG_FILE"
            rm -rf "$PROMPT_BACKUP"
            info "  Compressed to ${PROMPT_BACKUP}.tar.gz"
        fi
    else
        warn "  No prompts directory found at $src"
    fi
}

if $DRY_RUN; then
    info "  Would copy prompt templates from prompts/"
else
    if backup_prompts; then
        info "  Prompt backup complete"
    else
        error "  Prompt backup FAILED"
        ((ERRORS++))
    fi
fi

##############################################################################
# 4. Config Files Backup
##############################################################################
section "4/5 — Config backup"

CONFIG_BACKUP="${BACKUP_DIR}/config_${BACKUP_DAY}"

backup_config() {
    local src="${PROJECT_ROOT}/config"
    mkdir -p "$CONFIG_BACKUP"

    # Copy YAML configs (skip anything with secrets in filenames)
    for f in "$src"/*.yaml "$src"/*.yml; do
        [ -f "$f" ] || continue
        cp "$f" "$CONFIG_BACKUP/"
    done

    # Copy .env (without secrets — redact password-like values)
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        sed -E 's/(PASSWORD|TOKEN|SECRET|KEY)=.*/\1=REDACTED/' \
            "${PROJECT_ROOT}/.env" > "${CONFIG_BACKUP}/env.redacted"
        info "  Copied .env (redacted)"
    fi

    # Copy docker-compose
    [ -f "${PROJECT_ROOT}/docker-compose.yml" ] && \
        cp "${PROJECT_ROOT}/docker-compose.yml" "$CONFIG_BACKUP/"

    [ -f "${PROJECT_ROOT}/Dockerfile" ] && \
        cp "${PROJECT_ROOT}/Dockerfile" "$CONFIG_BACKUP/"

    [ -f "${PROJECT_ROOT}/Makefile" ] && \
        cp "${PROJECT_ROOT}/Makefile" "$CONFIG_BACKUP/"

    local count=$(find "$CONFIG_BACKUP" -type f | wc -l)
    info "  Copied $count config file(s)"

    # Compress
    if ! $DRY_RUN; then
        tar -czf "${CONFIG_BACKUP}.tar.gz" -C "$BACKUP_DIR" "$(basename "$CONFIG_BACKUP")" 2>>"$LOG_FILE"
        rm -rf "$CONFIG_BACKUP"
        info "  Compressed to ${CONFIG_BACKUP}.tar.gz"
    fi
}

if $DRY_RUN; then
    info "  Would copy config files from config/"
else
    if backup_config; then
        info "  Config backup complete"
    else
        error "  Config backup FAILED"
        ((ERRORS++))
    fi
fi

##############################################################################
# 5. Learning Data Backup
##############################################################################
section "5/5 — Learning data backup"

LEARNING_BACKUP="${BACKUP_DIR}/learning_${BACKUP_DAY}"

backup_learning() {
    mkdir -p "$LEARNING_BACKUP"

    # Export learning records from PostgreSQL
    if docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        docker exec cineos-postgres psql \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            -t -A -c "SELECT row_to_json(lr) FROM cineos_audit.learning_records lr ORDER BY created_at DESC LIMIT 1000;" \
            2>>"$LOG_FILE" > "${LEARNING_BACKUP}/learning_records.json" || true

        docker exec cineos-postgres psql \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            -t -A -c "SELECT row_to_json(pp) FROM cineos_memory.prompt_patterns pp ORDER BY usage_count DESC LIMIT 1000;" \
            2>>"$LOG_FILE" > "${LEARNING_BACKUP}/prompt_patterns.json" || true

        docker exec cineos-postgres psql \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            -t -A -c "SELECT row_to_json(bp) FROM cineos_memory.backend_performance bp ORDER BY created_at DESC LIMIT 1000;" \
            2>>"$LOG_FILE" > "${LEARNING_BACKUP}/backend_performance.json" || true
    fi

    # Copy generated output samples if they exist
    if [ -d "${PROJECT_ROOT}/generated" ]; then
        mkdir -p "${LEARNING_BACKUP}/generated_manifest"
        find "${PROJECT_ROOT}/generated" -type f \( -name "*.json" -o -name "*.txt" \) \
            -exec cp {} "${LEARNING_BACKUP}/generated_manifest/" \; 2>/dev/null || true
    fi

    local count=$(find "$LEARNING_BACKUP" -type f | wc -l)
    info "  Copied $count learning data file(s)"

    # Compress
    if ! $DRY_RUN; then
        tar -czf "${LEARNING_BACKUP}.tar.gz" -C "$BACKUP_DIR" "$(basename "$LEARNING_BACKUP")" 2>>"$LOG_FILE"
        rm -rf "$LEARNING_BACKUP"
        info "  Compressed to ${LEARNING_BACKUP}.tar.gz"
    fi
}

if $DRY_RUN; then
    info "  Would export learning data from PostgreSQL"
else
    if backup_learning; then
        info "  Learning data backup complete"
    else
        error "  Learning data backup FAILED"
        ((ERRORS++))
    fi
fi

##############################################################################
# 6. Backup Rotation
##############################################################################
if ! $DRY_RUN; then
    section "Rotating old backups"

    rotate_backups() {
        local pattern="$1"
        local keep="$2"
        local label="$3"

        local files=()
        while IFS= read -r -d '' f; do
            files+=("$f")
        done < <(find "$BACKUP_DIR" -maxdepth 1 -name "$pattern" -type f -print0 | sort -zr)

        local count=${#files[@]}
        if (( count > keep )); then
            local to_remove=$(( count - keep ))
            info "  $label: $count found, removing $to_remove oldest"
            for (( i=keep; i<count; i++ )); do
                if $VERBOSE; then
                    info "    Removing: $(basename "${files[$i]}")"
                fi
                rm -f "${files[$i]}"
            done
        else
            info "  $label: $count found, keeping all (limit: $keep)"
        fi
    }

    # Daily: keep last 7
    rotate_backups "postgres_*.sql.gz"           "$RETENTION_DAILY"  "Daily DB backups"
    rotate_backups "workflows_*.tar.gz"          "$RETENTION_DAILY"  "Daily workflow backups"
    rotate_backups "prompts_*.tar.gz"            "$RETENTION_DAILY"  "Daily prompt backups"
    rotate_backups "config_*.tar.gz"             "$RETENTION_DAILY"  "Daily config backups"
    rotate_backups "learning_*.tar.gz"           "$RETENTION_DAILY"  "Daily learning backups"

    # Weekly: keep last 4 (same files serve as both daily and weekly)
    # Additional weekly full backup
    DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
    if (( DAY_OF_WEEK == 7 )); then
        section "Weekly full backup"
        WEEKLY_DIR="${BACKUP_DIR}/weekly_${BACKUP_TS}"
        mkdir -p "$WEEKLY_DIR"

        # Full compressed archive of all current backups
        tar -czf "${WEEKLY_DIR}.tar.gz" \
            -C "$BACKUP_DIR" \
            postgres_*.sql.gz \
            workflows_*.tar.gz \
            prompts_*.tar.gz \
            config_*.tar.gz \
            learning_*.tar.gz \
            2>>"$LOG_FILE" || true

        info "  Weekly archive created: weekly_${BACKUP_TS}.tar.gz"

        # Rotate weekly backups
        rotate_backups "weekly_*.tar.gz" "$RETENTION_WEEKLY" "Weekly archives"
    fi
fi

##############################################################################
# 7. Summary
##############################################################################
section "Backup Summary"

TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
FILE_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -type f | wc -l)

info "  Backups directory: $BACKUP_DIR"
info "  Total files:       $FILE_COUNT"
info "  Total size:        $TOTAL_SIZE"
info "  Errors:            $ERRORS"

if (( ERRORS > 0 )); then
    error "Backup completed with $ERRORS error(s). Check log: $LOG_FILE"
    exit 1
fi

info "Backup completed successfully."
exit 0
