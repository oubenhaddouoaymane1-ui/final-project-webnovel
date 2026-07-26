#!/usr/bin/env bash
##############################################################################
# CineOS — Cron Backup Setup
# Installs cron jobs for automated backups and log rotation.
##############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup.sh"
CRON_MARKER="# cineos-backup"

# ── Colors ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Usage ──────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
CineOS Cron Backup Setup

Usage: $0 <command>

Commands:
  install    Install cron jobs for daily backups
  remove     Remove all CineOS cron jobs
  status     Show installed cron jobs
  test       Run backup script now (dry-run)
  help       Show this help message

Cron schedule installed:
  Daily backup:   02:00 AM every day
  Weekly archive:  03:00 AM every Sunday
  Log cleanup:     04:00 AM on the 1st of every month

Examples:
  $0 install
  $0 status
  $0 remove
EOF
    exit 0
}

# ── Parse command ──────────────────────────────────────────────────────────
COMMAND="${1:-help}"

case "$COMMAND" in
    install)  ;;
    remove)   ;;
    status)   ;;
    test)     ;;
    help|-h)  usage ;;
    *)        error "Unknown command: $COMMAND"; usage ;;
esac

##############################################################################
# Install
##############################################################################
do_install() {
    info "Installing CineOS cron jobs..."

    # Ensure backup script is executable
    chmod +x "$BACKUP_SCRIPT"

    # Check if already installed
    if crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
        warn "CineOS cron jobs already installed. Removing old entries first..."
        do_remove
    fi

    # Build cron entries
    local daily_cron="0 2 * * * ${BACKUP_SCRIPT} >> ${PROJECT_ROOT}/logs/cron_backup.log 2>&1 ${CRON_MARKER}-daily"
    local weekly_cron="0 3 * * 0 ${BACKUP_SCRIPT} >> ${PROJECT_ROOT}/logs/cron_backup.log 2>&1 ${CRON_MARKER}-weekly"
    local logrotate_cron="0 4 1 * * find ${PROJECT_ROOT}/logs -name 'backup_*.log' -mtime +30 -delete ${CRON_MARKER}-logrotate"

    # Install
    (crontab -l 2>/dev/null; echo "$daily_cron"; echo "$weekly_cron"; echo "$logrotate_cron") | crontab -

    info "Cron jobs installed:"
    info "  Daily backup:   02:00 AM every day"
    info "  Weekly archive:  03:00 AM every Sunday"
    info "  Log cleanup:     04:00 AM on the 1st of every month"
    info ""
    info "Logs written to: ${PROJECT_ROOT}/logs/cron_backup.log"
}

##############################################################################
# Remove
##############################################################################
do_remove() {
    info "Removing CineOS cron jobs..."

    if ! crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
        info "No CineOS cron jobs found."
        return 0
    fi

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | crontab -
    info "All CineOS cron jobs removed."
}

##############################################################################
# Status
##############################################################################
do_status() {
    info "Installed cron jobs:"
    echo ""

    local entries=$(crontab -l 2>/dev/null | grep "$CRON_MARKER" || true)

    if [[ -z "$entries" ]]; then
        warn "No CineOS cron jobs installed."
        echo ""
        info "Run '$0 install' to set up automated backups."
    else
        echo "$entries" | while IFS= read -r line; do
            # Extract the cron schedule and comment
            local schedule=$(echo "$line" | awk '{print $1, $2, $3, $4, $5}')
            local marker=$(echo "$line" | grep -o "${CRON_MARKER}-[a-z]*" || echo "unknown")
            local schedule_desc=""

            case "$marker" in
                *-daily)     schedule_desc="Daily at 02:00 AM" ;;
                *-weekly)    schedule_desc="Weekly on Sunday at 03:00 AM" ;;
                *-logrotate) schedule_desc="Monthly on 1st at 04:00 AM" ;;
            esac

            info "  $schedule_desc"
            info "    Schedule: $schedule"
        done
    fi
}

##############################################################################
# Test
##############################################################################
do_test() {
    info "Running backup dry-run test..."
    echo ""
    bash "$BACKUP_SCRIPT" --dry-run
}

##############################################################################
# Execute
##############################################################################
case "$COMMAND" in
    install) do_install ;;
    remove)  do_remove ;;
    status)  do_status ;;
    test)    do_test ;;
esac
