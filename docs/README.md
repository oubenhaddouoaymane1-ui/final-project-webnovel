# CineOS Documentation

Welcome to the CineOS documentation. CineOS is a novel-to-cinematic AI production platform that transforms novels sent via Telegram into cinematic videos through coordinated AI workflows, persistent memory, quality assurance, partial repair, and continuous learning.

## Documentation Index

| Document | Description |
|----------|-------------|
| [Installation Guide](installation.md) | Prerequisites, system requirements, Docker and manual setup |
| [Quick Start](quickstart.md) | 5-minute setup — your first novel to video |
| [Deployment Guide](deployment-guide.md) | Complete cloud-first deployment: system requirements, architecture, step-by-step setup |
| [Cloud Services Guide](cloud-services-guide.md) | Cloud backend reference: all services, comparison, configuration, fallback chains |
| [Colab Setup Guide](colab-setup-guide.md) | Google Colab detailed setup: ComfyUI + FLUX, ngrok, auto-shutdown |
| [Workflow Guide](workflow-guide.md) | All 25+ n8n workflows explained, how to modify and debug |
| [Database Guide](database-guide.md) | Schema overview, all 7 schemas, tables, views, functions |
| [API Guide](api-guide.md) | REST API authentication, all endpoints, examples, webhooks |
| [Telegram Bot Guide](telegram-guide.md) | Bot setup, commands, file handling, customization |
| [Worker Guide](worker-guide.md) | Worker types, adding new workers, scaling, GPU setup |
| [Prompt Guide](prompt-guide.md) | Template syntax, all prompts, customization, A/B testing |
| [Troubleshooting](troubleshooting.md) | Common issues, error codes, log analysis |
| [FAQ](faq.md) | Frequently asked questions |

## Architecture Documentation

| Document | Description |
|----------|-------------|
| [System Architecture](../architecture/01-system-architecture.md) | System overview and component diagram |
| [Layer Model](../architecture/02-layer-model-deployment.md) | Deployment and layer architecture |
| [State Machine](../architecture/03-state-machine-database.md) | Project state machine and database design |
| [n8n Workflow Architecture](../architecture/04-n8n-workflow-architecture.md) | Workflow automation design |
| [Quality & Workers](../architecture/06-quality-repair-learning-workers.md) | Quality pipeline, repair, and worker system |

## Additional Resources

| Document | Description |
|----------|-------------|
| [API Specification](../api/openapi.yaml) | OpenAPI 3.0 spec with all endpoints |
| [Implementation Plan](../research/implementation-plan.md) | Development roadmap |
| [Technology Research](../research/technology-research.md) | Technology evaluation and choices |

## Architecture Overview

```
Telegram User → Telegram Bot → n8n Orchestrator → PostgreSQL (State)
                                       ↓
                    ┌──────────────────┼──────────────────┐
                    ↓                  ↓                  ↓
              AI Workflows      Quality Pipeline     Learning Engine
                    ↓                  ↓                  ↓
              Remote Workers    Partial Repair      Knowledge Base
              (GPU/CPU/Vision)  (Auto-fix)          (Prompt Patterns)
```

## Quick Reference

### Key Ports

| Service | Port | Description |
|---------|------|-------------|
| n8n | 5678 | Workflow orchestration UI |
| Supervisor | 8000 | Worker management API |
| Image Worker | 8100 | GPU image generation |
| Quality Worker | 8200 | Vision quality review |
| Render Worker | 8300 | FFmpeg video assembly |
| Voice Worker | 8400 | TTS narration |
| Animation Worker | 8500 | Image animation |

### Key Commands

```bash
make up              # Start all services
make down            # Stop all services
make status          # Show service status
make health          # Check health endpoints
make db-shell        # Open psql shell
make db-reset        # Drop and recreate database
make test            # Run test suite
make lint            # Run linting
make backup-db       # Backup database
./scripts/backup.sh  # Full system backup
```
