##############################################################################
# CineOS — Development Makefile
##############################################################################

.PHONY: up down restart logs db-shell db-reset db-migrate import-workflows \
        test lint clean backup-db restore-db status health build \
        cloud-up cloud-down cloud-build cloud-verify \
        deploy-gcp deploy-fly deploy-railway

COMPOSE := docker compose

# ── Lifecycle ───────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

status:
	$(COMPOSE) ps

# ── Database ────────────────────────────────────────────────────────────────

db-shell:
	docker exec -it cineos-postgres psql -U cineos -d cineos

db-reset:
	@echo "⚠  Dropping and recreating database..."
	docker exec cineos-postgres dropdb -U cineos cineos --if-exists
	docker exec cineos-postgres createdb -U cineos cineos
	@echo "Re-running init scripts..."
	docker exec cineos-postgres sh -c ' \
		for f in /docker-entrypoint-initdb.d/*.sql; do \
			echo "Running $$f ..."; \
			psql -U cineos -d cineos -f "$$f"; \
		done'
	@echo "✓  Database reset complete."

db-migrate:
	@echo "Running pending migrations..."
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/schema.sql
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/indexes.sql
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/constraints.sql
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/functions.sql
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/triggers.sql
	docker exec -i cineos-postgres psql -U cineos -d cineos < ./database/views.sql
	@echo "✓  Migrations applied."

backup-db:
	@mkdir -p backups
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	echo "Backing up to backups/cineos_$$TIMESTAMP.sql.gz ..."; \
	docker exec cineos-postgres pg_dump -U cineos -d cineos \
		| gzip > backups/cineos_$$TIMESTAMP.sql.gz
	@echo "✓  Backup complete."

restore-db:
	@read -p "Enter backup file path: " FILE; \
	if [ ! -f "$$FILE" ]; then \
		echo "File not found: $$FILE"; \
		exit 1; \
	fi; \
	echo "Restoring from $$FILE ..."; \
	gunzip -c "$$FILE" | docker exec -i cineos-postgres psql -U cineos -d cineos
	@echo "✓  Restore complete."

# ── n8n Workflows ───────────────────────────────────────────────────────────

import-workflows:
	@echo "Importing n8n workflows..."
	@for f in ./n8n-workflows/*.json; do \
		if [ -f "$$f" ]; then \
			echo "  Importing $$f ..."; \
			curl -s -X POST http://localhost:${N8N_PORT:-5678}/api/v1/workflows \
				-H "Content-Type: application/json" \
				-H "X-N8N-API-KEY: $${N8N_API_KEY:-}" \
				-d @$$f || true; \
		fi; \
	done
	@echo "✓  Workflow import complete."

# ── Testing & Linting ──────────────────────────────────────────────────────

test:
	python -m pytest tests/ -v

lint:
	python -m ruff check .
	python -m ruff format --check .

# ── Utilities ───────────────────────────────────────────────────────────────

clean:
	@echo "Removing temp, cache, and logs..."
	rm -rf temp/*
	rm -rf cache/*
	rm -rf logs/*
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓  Clean complete."

health:
	@echo "Checking service health..."
	@curl -sf http://localhost:8000/health > /dev/null && echo "  ✓ supervisor (8000)" || echo "  ✗ supervisor (8000)"
	@curl -sf http://localhost:8100/health > /dev/null && echo "  ✓ image_worker (8100)" || echo "  ✗ image_worker (8100)"
	@curl -sf http://localhost:8200/health > /dev/null && echo "  ✓ quality_worker (8200)" || echo "  ✗ quality_worker (8200)"
	@curl -sf http://localhost:8300/health > /dev/null && echo "  ✓ render_worker (8300)" || echo "  ✗ render_worker (8300)"
	@curl -sf http://localhost:8400/health > /dev/null && echo "  ✓ voice_worker (8400)" || echo "  ✗ voice_worker (8400)"
	@curl -sf http://localhost:8500/health > /dev/null && echo "  ✓ animation_worker (8500)" || echo "  ✗ animation_worker (8500)"
	@curl -sf http://localhost:8600/health > /dev/null && echo "  ✓ cloud_bridge (8600)" || echo "  ✗ cloud_bridge (8600)"
	@curl -sf http://localhost:${N8N_PORT:-5678}/healthz > /dev/null && echo "  ✓ n8n (5678)" || echo "  ✗ n8n (5678)"
	@docker exec cineos-postgres pg_isready -U cineos -d cineos > /dev/null 2>&1 && echo "  ✓ postgres" || echo "  ✗ postgres"
	@docker exec cineos-redis redis-cli ping > /dev/null 2>&1 && echo "  ✓ redis" || echo "  ✗ redis"

# ── Cloud Deployment ──────────────────────────────────────────────────────

cloud-up:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.cloud.yml up -d

cloud-down:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.cloud.yml down

cloud-build:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.cloud.yml build

cloud-verify:
	python scripts/verify_cloud_deployment.py --env-file .env

deploy-gcp:
	bash deploy/gcp/deploy.sh

deploy-fly:
	bash deploy/flyio/deploy.sh

deploy-railway:
	bash deploy/railway/deploy.sh

# ── Testing (all suites) ──────────────────────────────────────────────────

test-e2e:
	python -m pytest tests/test_e2e_validation.py -v

test-all:
	python -m pytest tests/ -v --tb=short
