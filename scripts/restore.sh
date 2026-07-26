#!/usr/bin/env bash
##############################################################################
# CineOS — Restore Script
# Restores PostgreSQL, workflows, prompts, config, and learning data
# from a timestamped backup created by backup.sh.
##############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Configuration ──────────────────────────────────────────────────────────
BACKUP_DIR="${PROJECT_ROOT}/backups"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/restore_$(date +%Y%m%d_%H%M%S).log"

# ── Colors ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
info()    { echo -e "${GREEN}[INFO]${NC}  $(timestamp) $*" | tee -a "$LOG_FILE"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $(timestamp) $*" | tee -a "$LOG_FILE"; }
error()   { echo -e "${RED}[ERROR]${NC} $(timestamp) $*" | tee -a "$LOG_FILE"; }
section() { echo -e "${BLUE}[====]${NC} $(timestamp) $*" | tee -a "$LOG_FILE"; }

# ── Usage ──────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
CineOS Restore Script

Usage: $0 <backup_timestamp|latest> [OPTIONS]

Arguments:
  backup_timestamp   Backup timestamp (e.g. 20260726_143000)
  latest             Use the most recent backup

Options:
  --dry-run          Show what would be restored without making changes
  --force            Skip confirmation prompts
  --skip-db          Skip PostgreSQL restore
  --skip-workflows   Skip workflow restore
  --skip-prompts     Skip prompt template restore
  --skip-config      Skip config file restore
  --skip-learning    Skip learning data restore
  --help             Show this help message

Examples:
  $0 latest
  $0 20260726_143000
  $0 latest --dry-run
  $0 20260726_143000 --force --skip-config
EOF
    exit 0
}

# ── Parse arguments ────────────────────────────────────────────────────────
BACKUP_TIMESTAMP=""
DRY_RUN=false
FORCE=false
SKIP_DB=false
SKIP_WORKFLOWS=false
SKIP_PROMPTS=false
SKIP_CONFIG=false
SKIP_LEARNING=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        latest)
            BACKUP_TIMESTAMP="latest"
            shift
            ;;
        --dry-run)     DRY_RUN=true;       shift ;;
        --force)       FORCE=true;         shift ;;
        --skip-db)         SKIP_DB=true;       shift ;;
        --skip-workflows)  SKIP_WORKFLOWS=true; shift ;;
        --skip-prompts)    SKIP_PROMPTS=true;   shift ;;
        --skip-config)     SKIP_CONFIG=true;    shift ;;
        --skip-learning)   SKIP_LEARNING=true;  shift ;;
        --help|-h)     usage ;;
        *)
            if [[ -z "$BACKUP_TIMESTAMP" ]]; then
                BACKUP_TIMESTAMP="$1"
            else
                error "Unknown argument: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$BACKUP_TIMESTAMP" ]]; then
    error "No backup timestamp specified. Use 'latest' or a timestamp."
    echo ""
    usage
fi

# ── Setup ──────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

info "╔══════════════════════════════════════════════════════════════╗"
info "║  CineOS Restore                                            ║"
info "╚══════════════════════════════════════════════════════════════╝"

# ── Resolve backup ─────────────────────────────────────────────────────────
resolve_backup() {
    local ts="$1"
    local pg_file="" wf_file="" pr_file="" cf_file="" lr_file=""

    if [[ "$ts" == "latest" ]]; then
        pg_file=$(find "$BACKUP_DIR" -maxdepth 1 -name 'postgres_*.sql.gz' -type f | sort -zr | head -z -1)
        wf_file=$(find "$BACKUP_DIR" -maxdepth 1 -name 'workflows_*.tar.gz' -type f | sort -zr | head -z -1)
        pr_file=$(find "$BACKUP_DIR" -maxdepth 1 -name 'prompts_*.tar.gz' -type f | sort -zr | head -z -1)
        cf_file=$(find "$BACKUP_DIR" -maxdepth 1 -name 'config_*.tar.gz' -type f | sort -zr | head -z -1)
        lr_file=$(find "$BACKUP_DIR" -maxdepth 1 -name 'learning_*.tar.gz' -type f | sort -zr | head -z -1)
    else
        pg_file="${BACKUP_DIR}/postgres_${ts}.sql.gz"
        wf_file="${BACKUP_DIR}/workflows_${ts}.tar.gz"
        pr_file="${BACKUP_DIR}/prompts_${ts}.tar.gz"
        cf_file="${BACKUP_DIR}/config_${ts}.tar.gz"
        lr_file="${BACKUP_DIR}/learning_${ts}.tar.gz"
    fi

    echo "PG_FILE=$pg_file"
    echo "WF_FILE=$wf_file"
    echo "PR_FILE=$pr_file"
    echo "CF_FILE=$cf_file"
    echo "LR_FILE=$lr_file"
}

RESOLVED=$(resolve_backup "$BACKUP_TIMESTAMP")
eval "$RESOLVED"

info "Backup timestamp: $BACKUP_TIMESTAMP"
info "Log file: $LOG_FILE"

# Show what we found
info "Backup files found:"
[[ -n "$PG_FILE" && -f "$PG_FILE" ]]   && info "  PostgreSQL: $(basename "$PG_FILE") ($(du -sh "$PG_FILE" | cut -f1))" || warn "  PostgreSQL: NOT FOUND"
[[ -n "$WF_FILE" && -f "$WF_FILE" ]]   && info "  Workflows:  $(basename "$WF_FILE")" || warn "  Workflows:  NOT FOUND"
[[ -n "$PR_FILE" && -f "$PR_FILE" ]]   && info "  Prompts:    $(basename "$PR_FILE")" || warn "  Prompts:    NOT FOUND"
[[ -n "$CF_FILE" && -f "$CF_FILE" ]]   && info "  Config:     $(basename "$CF_FILE")" || warn "  Config:     NOT FOUND"
[[ -n "$LR_FILE" && -f "$LR_FILE" ]]   && info "  Learning:   $(basename "$LR_FILE")" || warn "  Learning:   NOT FOUND"

if $DRY_RUN; then
    warn "DRY RUN MODE — no changes will be made"
fi

# ── Confirmation ───────────────────────────────────────────────────────────
if ! $FORCE && ! $DRY_RUN; then
    echo ""
    warn "This will OVERWRITE current data with backup from $BACKUP_TIMESTAMP"
    read -p "Are you sure? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        info "Restore cancelled by user."
        exit 0
    fi
fi

##############################################################################
# 1. Restore PostgreSQL
##############################################################################
restore_postgres() {
    if [[ -z "$PG_FILE" || ! -f "$PG_FILE" ]]; then
        warn "PostgreSQL backup not found, skipping"
        return 0
    fi

    section "1/5 — Restoring PostgreSQL"

    if $DRY_RUN; then
        info "  Would restore from $(basename "$PG_FILE")"
        return 0
    fi

    local restore_target
    if docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        info "  Restoring via docker exec..."
        gunzip -c "$PG_FILE" | docker exec -i cineos-postgres \
            psql -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            2>>"$LOG_FILE"
    elif command -v psql &>/dev/null; then
        info "  Restoring via local psql..."
        gunzip -c "$PG_FILE" | psql \
            -h "${POSTGRES_HOST:-localhost}" \
            -p "${POSTGRES_PORT:-5432}" \
            -U "${POSTGRES_USER:-cineos}" \
            -d "${POSTGRES_DB:-cineos}" \
            2>>"$LOG_FILE"
    else
        error "  Cannot restore — no docker container or psql found"
        return 1
    fi

    info "  PostgreSQL restore complete"
}

##############################################################################
# 2. Restore Workflows
##############################################################################
restore_workflows() {
    if [[ -z "$WF_FILE" || ! -f "$WF_FILE" ]]; then
        warn "Workflow backup not found, skipping"
        return 0
    fi

    section "2/5 — Restoring workflows"

    if $DRY_RUN; then
        info "  Would restore workflows from $(basename "$WF_FILE")"
        return 0
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    tar -xzf "$WF_FILE" -C "$tmp_dir" 2>>"$LOG_FILE"

    # Find extracted directories
    for subdir in "$tmp_dir"/*/; do
        local dir_name=$(basename "$subdir")
        case "$dir_name" in
            workflows)
                cp -a "$subdir"*.json "${PROJECT_ROOT}/workflows/" 2>/dev/null || true
                info "  Restored workflows/ files"
                ;;
            n8n-workflows)
                cp -a "$subdir"*.json "${PROJECT_ROOT}/n8n-workflows/" 2>/dev/null || true
                info "  Restored n8n-workflows/ files"
                ;;
        esac
    done

    rm -rf "$tmp_dir"
    info "  Workflow restore complete"
}

##############################################################################
# 3. Restore Prompts
##############################################################################
restore_prompts() {
    if [[ -z "$PR_FILE" || ! -f "$PR_FILE" ]]; then
        warn "Prompt backup not found, skipping"
        return 0
    fi

    section "3/5 — Restoring prompt templates"

    if $DRY_RUN; then
        info "  Would restore prompts from $(basename "$PR_FILE")"
        return 0
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    tar -xzf "$PR_FILE" -C "$tmp_dir" 2>>"$LOG_FILE"

    # Find the prompts directory inside the archive
    local prompts_src=$(find "$tmp_dir" -maxdepth 2 -type d -name 'prompts' | head -1)
    if [[ -z "$prompts_src" ]]; then
        # Archive might have files directly
        prompts_src="$tmp_dir"
    fi

    cp -a "$prompts_src"/* "${PROJECT_ROOT}/prompts/" 2>/dev/null || \
        cp -a "$tmp_dir"/* "${PROJECT_ROOT}/prompts/" 2>/dev/null || true

    rm -rf "$tmp_dir"
    info "  Prompt restore complete"
}

##############################################################################
# 4. Restore Config
##############################################################################
restore_config() {
    if [[ -z "$CF_FILE" || ! -f "$CF_FILE" ]]; then
        warn "Config backup not found, skipping"
        return 0
    fi

    section "4/5 — Restoring config files"

    if $DRY_RUN; then
        info "  Would restore config from $(basename "$CF_FILE")"
        return 0
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    tar -xzf "$CF_FILE" -C "$tmp_dir" 2>>"$LOG_FILE"

    local config_dir=$(find "$tmp_dir" -maxdepth 2 -type d -name 'config_*' | head -1)
    if [[ -n "$config_dir" ]]; then
        # Restore YAML configs
        cp -a "$config_dir"/*.yaml "${PROJECT_ROOT}/config/" 2>/dev/null || true
        cp -a "$config_dir"/*.yml "${PROJECT_ROOT}/config/" 2>/dev/null || true

        # Restore env (redacted only — do NOT overwrite live .env)
        if [[ -f "$config_dir/env.redacted" ]]; then
            info "  Note: .env was backed up redacted — NOT overwriting live .env"
        fi

        # Restore docker-compose and Dockerfile
        [[ -f "$config_dir/docker-compose.yml" ]] && \
            cp "$config_dir/docker-compose.yml" "${PROJECT_ROOT}/"
        [[ -f "$config_dir/Dockerfile" ]] && \
            cp "$config_dir/Dockerfile" "${PROJECT_ROOT}/"
        [[ -f "$config_dir/Makefile" ]] && \
            cp "$config_dir/Makefile" "${PROJECT_ROOT}/"

        info "  Config restore complete"
    fi

    rm -rf "$tmp_dir"
}

##############################################################################
# 5. Restore Learning Data
##############################################################################
restore_learning() {
    if [[ -z "$LR_FILE" || ! -f "$LR_FILE" ]]; then
        warn "Learning backup not found, skipping"
        return 0
    fi

    section "5/5 — Restoring learning data"

    if $DRY_RUN; then
        info "  Would restore learning data from $(basename "$LR_FILE")"
        return 0
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    tar -xzf "$LR_FILE" -C "$tmp_dir" 2>>"$LOG_FILE"

    local lr_dir=$(find "$tmp_dir" -maxdepth 2 -type d -name 'learning_*' | head -1)
    if [[ -z "$lr_dir" ]]; then
        lr_dir="$tmp_dir"
    fi

    # Import learning records into PostgreSQL
    if [[ -f "$lr_dir/learning_records.json" ]] && \
       docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        info "  Importing learning records..."
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            docker exec cineos-postgres psql \
                -U "${POSTGRES_USER:-cineos}" \
                -d "${POSTGRES_DB:-cineos}" \
                -c "INSERT INTO cineos_audit.learning_records SELECT * FROM json_populate_record(NULL::cineos_audit.learning_records, '$line') ON CONFLICT DO NOTHING;" \
                2>>"$LOG_FILE" || true
        done < "$lr_dir/learning_records.json"
    fi

    # Import prompt patterns
    if [[ -f "$lr_dir/prompt_patterns.json" ]] && \
       docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        info "  Importing prompt patterns..."
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            docker exec cineos-postgres psql \
                -U "${POSTGRES_USER:-cineos}" \
                -d "${POSTGRES_DB:-cineos}" \
                -c "INSERT INTO cineos_memory.prompt_patterns SELECT * FROM json_populate_record(NULL::cineos_memory.prompt_patterns, '$line') ON CONFLICT DO NOTHING;" \
                2>>"$LOG_FILE" || true
        done < "$lr_dir/prompt_patterns.json"
    fi

    rm -rf "$tmp_dir"
    info "  Learning data restore complete"
}

##############################################################################
# Execute restores
##############################################################################
ERRORS=0

if ! $SKIP_DB; then
    restore_postgres || ((ERRORS++))
fi

if ! $SKIP_WORKFLOWS; then
    restore_workflows || ((ERRORS++))
fi

if ! $SKIP_PROMPTS; then
    restore_prompts || ((ERRORS++))
fi

if ! $SKIP_CONFIG; then
    restore_config || ((ERRORS++))
fi

if ! $SKIP_LEARNING; then
    restore_learning || ((ERRORS++))
fi

##############################################################################
# Verification
##############################################################################
section "Verification"

verify_component() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        info "  ✓ $name"
    else
        warn "  ✗ $name — check manually"
    fi
}

if ! $DRY_RUN; then
    if docker ps --format '{{.Names}}' | grep -q cineos-postgres; then
        verify_component "PostgreSQL connectivity" \
            "docker exec cineos-postgres pg_isready -U ${POSTGRES_USER:-cineos} -d ${POSTGRES_DB:-cineos}"

        verify_component "Projects table" \
            "docker exec cineos-postgres psql -U ${POSTGRES_USER:-cineos} -d ${POSTGRES_DB:-cineos} -c 'SELECT 1 FROM cineos_core.projects LIMIT 1'"

        verify_component "Scenes table" \
            "docker exec cineos-postgres psql -U ${POSTGRES_USER:-cineos} -d ${POSTGRES_DB:-cineos} -c 'SELECT 1 FROM cineos_core.scenes LIMIT 1'"

        verify_component "Quality reviews table" \
            "docker exec cineos-postgres psql -U ${POSTGRES_USER:-cineos} -d ${POSTGRES_DB:-cineos} -c 'SELECT 1 FROM cineos_quality.reviews LIMIT 1'"
    fi

    verify_component "Workflows directory" \
        "ls ${PROJECT_ROOT}/workflows/*.json >/dev/null 2>&1"

    verify_component "Prompts directory" \
        "ls ${PROJECT_ROOT}/prompts/**/*.j2 >/dev/null 2>&1"

    verify_component "Config directory" \
        "ls ${PROJECT_ROOT}/config/*.yaml >/dev/null 2>&1"
fi

##############################################################################
# Summary
##############################################################################
section "Restore Summary"

info "  Backup restored: $BACKUP_TIMESTAMP"
info "  Errors: $ERRORS"

if (( ERRORS > 0 )); then
    error "Restore completed with $ERRORS error(s). Check log: $LOG_FILE"
    exit 1
fi

info "Restore completed successfully."
exit 0
