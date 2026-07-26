#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# CineOS — Master Startup Script
# Brings up the entire stack: Docker services, DB migration, n8n setup, workers
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "\n${CYAN}${BOLD}═══ $* ═══${NC}"; }

# ─── 1. Check Docker ────────────────────────────────────────────────────────
step "Step 1/7 — Checking Docker"

if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Install Docker first."
    exit 1
fi

if ! docker info &>/dev/null; then
    error "Docker daemon is not running. Start Docker first."
    exit 1
fi

if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null; then
    if ! command -v docker-compose &>/dev/null; then
        error "Neither 'docker compose' nor 'docker-compose' available."
        exit 1
    fi
    COMPOSE="docker-compose"
else
    COMPOSE="docker compose"
fi

info "Docker is running ($($COMPOSE version 2>/dev/null || docker --version))"

# ─── 2. Environment file ────────────────────────────────────────────────────
step "Step 2/7 — Setting up environment"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        warn "Created .env from .env.example — edit it with your values!"
    elif [ -f .env.docker.example ]; then
        cp .env.docker.example .env
        warn "Created .env from .env.docker.example — edit it with your values!"
    else
        error "No .env.example or .env.docker.example found. Create a .env file manually."
        exit 1
    fi
else
    info ".env already exists"
fi

set -a
source .env 2>/dev/null || true
set +a

# ─── 3. Docker Compose Up ──────────────────────────────────────────────────
step "Step 3/7 — Starting Docker services"

info "Pulling latest images..."
$COMPOSE pull --quiet 2>/dev/null || $COMPOSE pull || warn "Some images could not be pulled"

info "Building and starting services..."
$COMPOSE up -d --build --remove-orphans

# ─── 4. Wait for healthy services ───────────────────────────────────────────
step "Step 4/7 — Waiting for services to become healthy"

WAIT_TIMEOUT=180
INTERVAL=3

wait_for_healthy() {
    local service="$1"
    local deadline=$((SECONDS + WAIT_TIMEOUT))
    info "Waiting for $service ..."
    while [ $SECONDS -lt "$deadline" ]; do
        local status
        status=$($COMPOSE ps --format json "$service" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('Health', d.get('health', 'unknown')))
except:
    print('unknown')
" 2>/dev/null || echo "unknown")

        if [ "$status" = "healthy" ]; then
            info "$service is healthy"
            return 0
        fi
        sleep "$INTERVAL"
    done
    warn "$service did not become healthy within ${WAIT_TIMEOUT}s"
    return 1
}

wait_for_healthy "postgres" || true
wait_for_healthy "n8n" || true
wait_for_healthy "redis" || true

info "Giving services a few extra seconds to stabilise..."
sleep 5

# ─── 5. Database migration ──────────────────────────────────────────────────
step "Step 5/7 — Running database migration"

if [ -f scripts/migrate_db.py ]; then
    info "Running migrate_db.py..."
    python3 scripts/migrate_db.py --force 2>&1 | while IFS= read -r line; do
        echo "  [migrate] $line"
    done
    info "Database migration complete"
else
    warn "scripts/migrate_db.py not found — skipping"
fi

# ─── 6. n8n workflow import ─────────────────────────────────────────────────
step "Step 6/7 — Importing n8n workflows"

if [ -f scripts/setup_n8n.py ]; then
    info "Running setup_n8n.py..."
    python3 scripts/setup_n8n.py 2>&1 | while IFS= read -r line; do
        echo "  [n8n] $line"
    done
    info "n8n setup complete"
else
    warn "scripts/setup_n8n.py not found — skipping"
fi

# ─── 7. Worker registration ─────────────────────────────────────────────────
step "Step 7/7 — Registering workers"

if [ -f scripts/register_workers.py ]; then
    info "Running register_workers.py..."
    python3 scripts/register_workers.py --once 2>&1 | while IFS= read -r line; do
        echo "  [workers] $line"
    done
    info "Worker registration complete"
else
    warn "scripts/register_workers.py not found — skipping"
fi

# ─── Status Summary ─────────────────────────────────────────────────────────
step "CineOS Status Summary"

echo ""
$COMPOSE ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || $COMPOSE ps
echo ""

POSTGRES_OK="NO"
N8N_OK="NO"
REDIS_OK="NO"

if docker inspect --format='{{.State.Health.Status}}' cineos-postgres 2>/dev/null | grep -q healthy; then
    POSTGRES_OK="YES"
fi
if docker inspect --format='{{.State.Health.Status}}' cineos-n8n 2>/dev/null | grep -q healthy; then
    N8N_OK="YES"
fi
if docker inspect --format='{{.State.Health.Status}}' cineos-redis 2>/dev/null | grep -q healthy; then
    REDIS_OK="YES"
fi

echo -e "${BOLD}Service Health:${NC}"
echo -e "  PostgreSQL : $([ "$POSTGRES_OK" = "YES" ] && echo -e "${GREEN}✓ healthy${NC}" || echo -e "${RED}✗ unhealthy${NC}")"
echo -e "  n8n        : $([ "$N8N_OK" = "YES" ] && echo -e "${GREEN}✓ healthy${NC}" || echo -e "${RED}✗ unhealthy${NC}")"
echo -e "  Redis      : $([ "$REDIS_OK" = "YES" ] && echo -e "${GREEN}✓ healthy${NC}" || echo -e "${RED}✗ unhealthy${NC}")"

echo ""
echo -e "${BOLD}Endpoints:${NC}"
echo -e "  PostgreSQL : localhost:${POSTGRES_PORT:-5432}"
echo -e "  n8n UI     : http://localhost:${N8N_PORT:-5678}"
echo -e "  Redis      : localhost:${REDIS_PORT:-6379}"

echo ""
info "CineOS is up and running!"
info "To view logs:  $COMPOSE logs -f"
info "To stop:       $COMPOSE down"
