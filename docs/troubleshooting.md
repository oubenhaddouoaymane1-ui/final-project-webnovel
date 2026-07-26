# CineOS Troubleshooting Guide

This guide covers common issues, error codes, and diagnostic procedures for all CineOS components.

## Quick Diagnostics

### Health Check

```bash
# Check all services at once
make health

# Or individually
curl http://localhost:8000/health    # Supervisor
curl http://localhost:8100/health    # Image worker
curl http://localhost:8200/health    # Quality worker
curl http://localhost:8300/health    # Render worker
curl http://localhost:8400/health    # Voice worker
curl http://localhost:8500/health    # Animation worker
curl http://localhost:5678/healthz   # n8n
docker exec cineos-postgres pg_isready  # PostgreSQL
docker exec cineos-redis redis-cli ping  # Redis
```

### Service Status

```bash
docker compose ps
docker compose logs --tail=50
```

### Database State

```sql
-- Active projects
SELECT project_id, title, current_state, updated_at
FROM cineos_core.projects
WHERE current_state NOT IN ('completed', 'failed', 'cancelled')
ORDER BY updated_at DESC;

-- Recent errors
SELECT event_type, severity, message, created_at
FROM cineos_core.events
WHERE severity IN ('error', 'critical')
ORDER BY created_at DESC LIMIT 20;

-- Failed jobs
SELECT job_type, error_message, created_at
FROM cineos_exec.jobs
WHERE state = 'failed'
ORDER BY created_at DESC LIMIT 10;
```

## Component Issues

### PostgreSQL

#### Won't Start

```bash
# Check if port is in use
lsof -i :5432

# Check Docker logs
docker compose logs postgres

# Check disk space
df -h

# Check volume permissions
docker volume inspect cinematic-production-os_postgres_data
```

**Common Causes:**
- Port 5432 already in use by another PostgreSQL instance
- Disk full
- Corrupted volume data

**Fix:**

```bash
# Stop conflicting PostgreSQL
sudo systemctl stop postgresql

# Or change port in .env
POSTGRES_PORT=5433

# Reset volume if corrupted
docker compose down -v
docker compose up postgres
```

#### Connection Refused

```bash
# Verify PostgreSQL is running
docker compose ps postgres

# Test connection
docker exec cineos-postgres pg_isready -U cineos -d cineos

# Check credentials
docker exec cineos-postgres psql -U cineos -d cineos -c "SELECT 1"
```

#### Slow Queries

```sql
-- Check for long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes';

-- Check table sizes
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname LIKE 'cineos_%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
```

### Redis

#### Won't Start

```bash
docker compose logs redis

# Test connection
docker exec cineos-redis redis-cli ping
```

**Fix:**

```bash
# Clear Redis data
docker compose down redis
docker volume rm cinematic-production-os_redis_data
docker compose up redis
```

### n8n

#### Won't Start

```bash
docker compose logs n8n

# Check database connection
docker exec cineos-postgres pg_isready

# Check Redis connection
docker exec cineos-redis redis-cli ping
```

#### Workflows Not Triggering

```bash
# Check workflow status in n8n UI
# Open http://localhost:5678

# Verify webhook URLs
curl http://localhost:5678/webhook/telegram_intake

# Check n8n execution history
docker compose logs n8n | grep -i error
```

#### Import Fails

```bash
# Re-import workflows
make import-workflows

# Or manually via API
curl -X POST http://localhost:5678/api/v1/workflows \
  -H "Content-Type: application/json" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -d @workflows/001_telegram_intake.json
```

### Telegram Bot

#### Bot Won't Start

```bash
docker compose logs telegram_bot

# Verify token
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
```

**Common Causes:**
- Invalid bot token
- n8n not running (bot depends on n8n)
- Environment variable not set

#### Bot Doesn't Respond

```bash
# Check bot is running
docker compose ps telegram_bot

# Check for token conflicts (only one connection per token allowed)
# Stop any other bot instances using the same token
```

#### File Upload Fails

```bash
# Check file size (default limit: 50MB)
ls -la /path/to/novel.txt

# Check encoding
file -i /path/to/novel.txt

# Check bot temp directory permissions
docker exec cineos-telegram ls -la /app/temp
```

### Workers

#### Worker Won't Register

```bash
docker compose logs image_worker

# Check supervisor is running
curl http://localhost:8000/health

# Check PostgreSQL is accessible from worker
docker exec cineos-image-worker pg_isready -h postgres
```

#### Jobs Stay Pending

```sql
-- Check if workers are registered and idle
SELECT worker_name, state, last_heartbeat
FROM cineos_exec.workers;

-- Check if jobs match worker capabilities
SELECT job_type, state, worker_id
FROM cineos_exec.jobs
WHERE state = 'pending';
```

**Fix:**
- Verify worker type matches job type
- Check worker heartbeat is recent
- Restart the worker: `docker compose restart image_worker`

#### Image Worker Out of Memory

```bash
# Check GPU memory
nvidia-smi

# Reduce concurrent jobs
# In config/workers.yaml, reduce max_concurrent for gpu type

# Or increase Docker memory limit
# In docker-compose.yml:
# deploy.resources.limits.memory: 16G
```

#### Render Worker Timeout

```bash
# Check FFmpeg is available
docker exec cineos-render-worker ffmpeg -version

# Increase timeout in config/workers.yaml
# render:
#   timeout_seconds: 1200

# Check disk space for output
docker exec cineos-render-worker df -h /data/output
```

#### Quality Worker Always Fails

```bash
# Lower quality threshold in .env
QUALITY_THRESHOLD=0.60

# Or adjust in config/quality.yaml
# thresholds:
#   auto_approve: 0.80
```

## Pipeline Issues

### Project Stuck in a State

```sql
-- Find stuck projects
SELECT project_id, title, current_state, updated_at,
       NOW() - updated_at as stuck_duration
FROM cineos_core.projects
WHERE current_state NOT IN ('completed', 'failed', 'cancelled')
AND updated_at < NOW() - INTERVAL '2 hours';

-- Check what workflow should run next
SELECT workflow_name, state, error_data
FROM cineos_exec.workflow_executions
WHERE project_id = 'stuck-project-id'
ORDER BY created_at DESC LIMIT 5;
```

**Fix:**

```sql
-- Force state transition (use with caution)
UPDATE cineos_core.projects
SET current_state = 'next_state',
    last_state_change_at = NOW()
WHERE project_id = 'stuck-project-id';
```

### Project Failed

```sql
-- Check failure details
SELECT project_id, title, current_state, last_error, last_error_at
FROM cineos_core.projects
WHERE current_state = 'failed';

-- Check related events
SELECT event_type, message, created_at
FROM cineos_core.events
WHERE project_id = 'failed-project-id'
AND severity IN ('error', 'critical');
```

**Recovery:**

```sql
-- Reset to previous state for retry
UPDATE cineos_core.projects
SET current_state = 'previous_state',
    retry_count = retry_count + 1,
    last_error = NULL
WHERE project_id = 'failed-project-id';
```

### Quality Loop (Repeated Repairs)

```sql
-- Check repair history
SELECT repair_attempt_number, pre_repair_score, post_repair_score, success
FROM cineos_quality.repairs
WHERE project_id = 'project-id'
ORDER BY created_at;
```

**Fix:**
- Increase `max_repair_attempts` in `config/quality.yaml`
- Lower the quality threshold temporarily
- Skip quality check for specific assets

### Image Generation Fails Repeatedly

```bash
# Check ComfyUI is running
curl http://localhost:8188/system_stats

# Check GPU availability
nvidia-smi

# Switch to Pollinations fallback
# In config/models.yaml:
# image:
#   primary: "pollinations"
```

## Error Codes

### Worker Errors

| Code | Description | Fix |
|------|-------------|-----|
| `WORKER_TIMEOUT` | Job exceeded timeout | Increase timeout or optimize worker |
| `WORKER_OOM` | Worker out of memory | Reduce batch size, increase memory |
| `WORKER_GPU_OOM` | GPU out of memory | Reduce image size, use fewer steps |
| `BACKEND_UNAVAILABLE` | AI backend not responding | Check backend service (ComfyUI, etc.) |
| `BACKEND_ERROR` | Backend returned error | Check backend logs |

### Quality Errors

| Code | Description | Fix |
|------|-------------|-----|
| `QUALITY_THRESHOLD_NOT_MET` | Score below threshold | Lower threshold or improve prompt |
| `MAX_REPAIRS_EXCEEDED` | Too many repair attempts | Accept current quality or regenerate |
| `INCONSISTENT_CHARACTERS` | Characters look different | Use consistent seed/references |

### Pipeline Errors

| Code | Description | Fix |
|------|-------------|-----|
| `INVALID_STATE_TRANSITION` | Illegal state change | Check state machine rules |
| `PROJECT_NOT_FOUND` | Project doesn't exist | Verify project_id |
| `NO_WORKERS_AVAILABLE` | All workers busy | Scale up workers or wait |
| `DATABASE_ERROR` | PostgreSQL error | Check database health |

## Log Analysis

### Finding Relevant Logs

```bash
# All errors across all services
docker compose logs 2>&1 | grep -i error | tail -50

# Specific time range
docker compose logs --since="2026-07-26T12:00:00" --until="2026-07-26T13:00:00"

# Specific service
docker compose logs image_worker 2>&1 | grep -i "error\|fail\|warn"

# Structured log search
docker compose logs supervisor 2>&1 | grep '"level":"error"'
```

### Log Files

```bash
# Application logs
ls -la logs/

# Backup logs
ls -la logs/backup_*.log

# Cron logs
cat logs/cron_backup.log
```

### Common Log Patterns

| Pattern | Meaning |
|---------|---------|
| `Connection refused` | Service not running or wrong host/port |
| `Authentication failed` | Wrong credentials |
| `Timeout` | Operation took too long |
| `Out of memory` | Not enough RAM/VRAM |
| `Permission denied` | File/directory permissions issue |
| `Disk full` | Storage exhausted |

## Performance Issues

### Slow Image Generation

```bash
# Check GPU utilization
nvidia-smi

# Reduce image quality for speed
# In config/models.yaml:
# image:
#   backends:
#     local_gpu:
#       steps: 20      # Default 30
#       width: 1024     # Default 1920
#       height: 576     # Default 1080
```

### High Memory Usage

```bash
# Check container memory
docker stats

# Reduce parallelism
# In .env:
MAX_PARALLEL_JOBS=2    # Default 4

# Reduce worker concurrency
# In config/workers.yaml:
# worker_types:
#   gpu:
#     max_concurrent: 1
```

### Disk Space Issues

```bash
# Check disk usage
du -sh generated/ output/ cache/ temp/ logs/

# Clean up
make clean

# Remove old backups
find backups/ -name "*.gz" -mtime +30 -delete

# Remove old Docker images
docker image prune -a
```

## Getting Help

If the issue isn't covered here:

1. Check the [FAQ](faq.md)
2. Search the n8n execution history at `http://localhost:5678`
3. Check PostgreSQL for error events: `SELECT * FROM cineos_core.events WHERE severity = 'error' ORDER BY created_at DESC LIMIT 20;`
4. Review architecture docs in `architecture/`
