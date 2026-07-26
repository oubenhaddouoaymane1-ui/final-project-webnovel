# CineOS Installation Guide

This guide covers everything you need to install and run CineOS, from system requirements through a fully operational deployment.

## Prerequisites

### Hardware Requirements

CineOS uses a cloud-first architecture. Heavy AI (image generation, LLM analysis, TTS) runs on free cloud services. Your local machine only runs Docker containers for orchestration and video assembly.

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores (any) | 4+ cores |
| RAM | 4 GB | 8 GB |
| GPU | None | None needed |
| Storage | 20 GB free | 50+ GB SSD |
| Network | Broadband | Broadband |

**No GPU required locally.** All heavy computation runs on free cloud APIs:
- **Image generation**: HuggingFace Inference API, Pollinations, or Google Colab GPU
- **LLM analysis**: OpenRouter (free Llama 3, Mistral, Gemma models)
- **TTS**: Edge-TTS (free Microsoft voices)
- **Video assembly**: FFmpeg runs locally on CPU (lightweight)

See [Deployment Guide](deployment-guide.md) for the full cloud-first architecture.

### Software Requirements

| Software | Version | Purpose |
|----------|---------|---------|
| Docker | 24.0+ | Container runtime |
| Docker Compose | v2.20+ | Service orchestration |
| Python | 3.10+ | Bot and utilities |
| Git | 2.30+ | Source control |

Optional (for local GPU acceleration if you have a GPU):

| Software | Version | Purpose |
|----------|---------|---------|
| NVIDIA Container Toolkit | Latest | GPU access in Docker |
| Ollama | Latest | Local LLM inference (replaces OpenRouter) |

### Telegram Bot Token

You need a Telegram bot token from BotFather:

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name for your bot (e.g., "CineOS Bot")
4. Choose a username ending in `bot` (e.g., `mycineos_bot`)
5. Copy the token BotFather provides

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd cinematic-production-os
```

### 2. Create Environment File

```bash
cp .env.example .env
```

Edit `.env` with your values. At minimum, set:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
POSTGRES_PASSWORD=your_secure_password
N8N_BASIC_AUTH_PASSWORD=your_n8n_password
N8N_ENCRYPTION_KEY=random_32_character_string_here
```

### 3. Start Everything

```bash
chmod +x scripts/run_all.sh
./scripts/run_all.sh
```

This single command will:
1. Build Docker images
2. Start PostgreSQL, Redis, n8n, all workers, and the Telegram bot
3. Run database migrations
4. Import all n8n workflows
5. Register AI workers
6. Connect the Telegram bot
7. Print a status summary

### 4. Verify Installation

```bash
make health
```

You should see green checkmarks for all services:

```
  ✓ supervisor (8000)
  ✓ image_worker (8100)
  ✓ quality_worker (8200)
  ✓ render_worker (8300)
  ✓ voice_worker (8400)
  ✓ animation_worker (8500)
  ✓ n8n (5678)
  ✓ postgres
  ✓ redis
```

## Docker Setup (Recommended)

Docker is the recommended way to run CineOS. It manages all services in isolated containers.

### Start All Services

```bash
docker compose up -d
```

### View Logs

```bash
docker compose logs -f                    # All services
docker compose logs -f supervisor         # Single service
docker compose logs --tail=100            # Last 100 lines
```

### Check Status

```bash
docker compose ps
```

### Restart a Service

```bash
docker compose restart image_worker
docker compose restart                    # All services
```

### Stop Everything

```bash
docker compose down
docker compose down -v                    # Also remove volumes (DELETES DATA)
```

### GPU Support

For GPU-accelerated image generation, install the NVIDIA Container Toolkit:

```bash
# Install NVIDIA Container Toolkit (Ubuntu/Debian)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

After installation, restart the CineOS services:

```bash
docker compose down && docker compose up -d
```

### Compose File Architecture

The `docker-compose.yml` defines these services:

```
cineos-network (bridge)
├── postgres          (port 5432)
├── redis             (port 6379)
├── n8n               (port 5678)
├── supervisor        (port 8000)
├── image_worker      (port 8100)
├── quality_worker    (port 8200)
├── render_worker     (port 8300)
├── voice_worker      (port 8400)
├── animation_worker  (port 8500)
└── telegram_bot      (internal)
```

## Manual Setup (Without Docker)

For development or custom deployments.

### 1. Install Python Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install PostgreSQL

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Create database
sudo -u postgres createdb cineos
sudo -u postgres psql -c "CREATE USER cineos WITH PASSWORD 'cineos_secret';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE cineos TO cineos;"
```

### 3. Run Database Migrations

```bash
psql -U cineos -d cineos -f sql/init.sql
```

Or use the migration script:

```bash
python scripts/migrate_db.py
```

### 4. Install Redis

```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis
```

### 5. Install n8n

```bash
npm install -g n8n
n8n start
```

### 6. Configure Workers

Edit `config/workers.yaml` to point to your local services:

```yaml
supervisor:
  host: "0.0.0.0"
  port: 9000
```

### 7. Start Workers

```bash
python -m workers.supervisor.service &
python -m workers.image_worker.service &
python -m workers.quality_worker.service &
python -m workers.render_worker.service &
python -m workers.voice_worker.service &
python -m workers.animation_worker.service &
```

### 8. Import n8n Workflows

```bash
python scripts/setup_n8n.py
```

### 9. Start the Telegram Bot

```bash
python -m src.main
```

Or use the startup script:

```bash
./run.sh
```

## Post-Installation Verification

### Check Database

```bash
make db-shell

# Inside psql:
\dt                          # List all tables
\dt cineos_core.*            # List core tables
SELECT count(*) FROM cineos_core.projects;
```

### Check n8n

Open `http://localhost:5678` in your browser. Log in with the credentials from your `.env` file. You should see all 25+ imported workflows.

### Check Workers

```bash
curl http://localhost:8000/health    # Supervisor
curl http://localhost:8100/health    # Image worker
curl http://localhost:8200/health    # Quality worker
curl http://localhost:8300/health    # Render worker
curl http://localhost:8400/health    # Voice worker
curl http://localhost:8500/health    # Animation worker
```

### Test the Bot

Open Telegram, find your bot, and send `/help`. You should receive the welcome message.

## Troubleshooting Installation

| Issue | Solution |
|-------|----------|
| Docker build fails | Run `docker compose build --no-cache` |
| PostgreSQL won't start | Check port 5432 is free: `lsof -i :5432` |
| n8n can't connect to DB | Verify POSTGRES_* env vars in `.env` |
| Bot won't start | Verify TELEGRAM_BOT_TOKEN is set correctly |
| GPU not detected | Install NVIDIA Container Toolkit (see above) |
| Port already in use | Change port in `.env` or stop conflicting service |
| Memory errors | Increase Docker memory limit or reduce MAX_PARALLEL_JOBS |

### Viewing Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f supervisor

# Last 50 lines
docker compose logs --tail=50 image_worker

# Errors only
docker compose logs supervisor 2>&1 | grep -i error
```

### Resetting Everything

```bash
# Stop and remove all data
docker compose down -v

# Remove generated files
make clean

# Start fresh
./scripts/run_all.sh
```
