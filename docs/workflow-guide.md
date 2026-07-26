# CineOS Workflow Guide

CineOS uses n8n Community Edition as its sole orchestrator. All 25+ workflows run in n8n and communicate through PostgreSQL. This guide explains every workflow, how to modify them, how to add new ones, and how to debug them.

## Workflow Overview

Workflows are stored as JSON in two directories:

- `workflows/` — Canonical workflow definitions (25 files)
- `n8n-workflows/` — n8n-imported versions (30 files, including utilities)

Each workflow has a numeric prefix indicating its position in the pipeline.

## The 25 Core Workflows

### Intake & Setup

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 001 | Telegram Intake | `001_telegram_intake.json` | Receives novels via Telegram, validates file format and size, creates a project record in PostgreSQL, sends confirmation message back to user |
| 002 | Project Orchestrator | `002_project_orchestrator.json` | Master controller that dispatches all production workflows. Listens for state changes and triggers the next workflow in the pipeline. Handles error recovery and retries |

### Story Analysis

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 003 | Story Parser | `003_story_parser.json` | Splits novels into chapters and scenes using LLM. Detects chapter boundaries, assigns scene numbers, extracts dialogue and action segments |
| 004 | Story Intelligence | `004_story_intelligence.json` | Analyzes themes, conflicts, character arcs, emotional progression. Uses LLM to identify narrative structure and key story elements |
| 005 | Story Bible Builder | `005_story_bible_builder.json` | Creates comprehensive story bible including genre, themes, narrative arc, tone, pacing, and visual style. Feeds into all downstream workflows |

### Character & World

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 006 | Character Engine | `006_character_engine.json` | Extracts and profiles all characters. Builds physical descriptions, personality traits, relationships, visual prompts. Handles character consistency across scenes |
| 007 | World Engine | `007_world_engine.json` | Builds world bible with geography, architecture, climate, culture, magic systems. Generates world visual prompts for consistent scene backgrounds |
| 008 | Timeline Engine | `008_timeline_engine.json` | Constructs chronological timeline from scenes. Detects flashbacks, parallel timelines, temporal contradictions. Ensures narrative consistency |

### Planning

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 009 | Scene Planner | `009_scene_planner.json` | Plans shot sequences per scene. Determines number of shots, pacing, transitions, emotional arc within each scene |
| 010 | Shot Planner | `010_shot_planner.json` | Plans individual shot details: camera angle, lighting, composition, duration, animation type. Creates shot-level production plans |
| 011 | Fight Director | `011_fight_director.json` | Specialized workflow for action sequences. Choreographs fight scenes with timing, camera movement, impact frames, and dynamic pacing |
| 012 | Emotion Director | `012_emotion_director.json` | Maps emotional arcs across scenes. Adjusts color grading, lighting, music cues, and pacing to match emotional intensity |

### Generation

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 013 | Prompt Builder | `013_prompt_builder.json` | Assembles final image generation prompts by combining character, world, style, and shot-specific elements into optimized prompt strings |
| 014 | Job Dispatcher | `014_job_dispatcher.json` | Creates and queues generation jobs in the database. Assigns jobs to available workers based on priority and worker capabilities |
| 015 | Image Generation | `015_image_generation.json` | Orchestrates image creation via remote workers. Manages parallel generation, variant creation, and retry logic for failed generations |

### Quality & Repair

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 016 | Quality AI | `016_quality_ai.json` | Reviews generated assets for quality. Scores images on technical quality, prompt alignment, character consistency, composition. Makes approve/repair/regenerate decisions |
| 017 | Repair Engine | `017_repair_engine.json` | Fixes failed quality checks using partial repair strategies. Priority order: face → eyes → hands → weapon → armour → outfit → background → lighting |

### Media Production

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 018 | Voice Engine | `018_voice_engine.json` | Generates TTS narration for each shot. Handles voice selection, emotion matching, speed adjustment, and duration fitting |
| 019 | Music Director | `019_music_director.json` | Creates music and soundtrack plan. Determines mood, tempo, instrumentation, and volume levels for each scene and transition |
| 020 | Animation Engine | `020_animation_engine.json` | Animates static images into video clips. Applies Ken Burns effect, LivePortrait, or simple motion based on shot requirements |
| 021 | Render Manager | `021_render_manager.json` | Assembles final video with FFmpeg. Combines clips, audio, transitions, and subtitles into the final rendered output |

### Final Stages

| # | Workflow | File | Description |
|---|----------|------|-------------|
| 022 | Super Resolution | `022_super_resolution.json` | Upscales images and video frames using RealESRGAN. Improves quality of low-resolution generations |
| 023 | Final Review | `023_final_review.json` | Last quality check before delivery. Verifies overall coherence, audio-video sync, and production quality |
| 024 | Delivery | `024_delivery.json` | Sends final video via Telegram. Handles file size limits, compression, and delivery confirmation |
| 025 | Learning Engine | `025_learning_engine.json` | Analyzes completed projects for improvement. Extracts prompt patterns, performance metrics, and lessons learned into the knowledge base |

## Utility Workflows (n8n-workflows/)

These additional workflows are only in `n8n-workflows/`:

| # | Workflow | Description |
|---|----------|-------------|
| 003 | Project Validator | Validates project data before processing |
| 016 | Remote Worker Manager | Manages remote worker registration and health |
| 028 | Worker Monitor | Monitors worker health and reassigns jobs |
| 029 | System Monitor | Monitors overall system health |
| 030 | Admin Tools | Administrative operations and manual overrides |

## How Workflows Communicate

All workflows communicate through PostgreSQL — never directly to each other:

```
Workflow A writes to PostgreSQL
         ↓
State change triggers state_log entry
         ↓
Workflow B polls for work / gets triggered by n8n
         ↓
Workflow B reads from PostgreSQL
```

### Key Communication Tables

| Table | Used By | Purpose |
|-------|---------|---------|
| `cineos_core.projects` | All workflows | Project state and progress |
| `cineos_core.scenes` | 003-021 | Scene data and state |
| `cineos_core.shots` | 009-021 | Shot data and state |
| `cineos_exec.jobs` | 014-021 | Job queue and assignment |
| `cineos_quality.reviews` | 016-017 | Quality review results |
| `cineos_core.events` | All workflows | Event logging |
| `cineos_core.state_log` | All workflows | State transition history |

## Modifying a Workflow

### Via n8n UI

1. Open `http://localhost:5678`
2. Find the workflow in the list
3. Click to edit
4. Make changes visually
5. Save (Ctrl+S)
6. Test with a small project

### Via JSON

1. Edit the workflow JSON in `workflows/` or `n8n-workflows/`
2. Import into n8n via the UI or API
3. Test changes

### Common Modifications

**Change LLM model** — Find the HTTP Request node calling Ollama/OpenRouter and update the model parameter.

**Adjust quality thresholds** — Edit `config/quality.yaml` (thresholds are read by the quality worker, not hardcoded in workflows).

**Add notification** — Add a Telegram node to the end of the relevant workflow.

**Change retry logic** — Edit the retry settings in the relevant workflow's Error Trigger node.

## Adding a New Workflow

1. Create a new n8n workflow in the UI
2. Design it using the same patterns as existing workflows:
   - Start with a Webhook or PostgreSQL trigger
   - Use PostgreSQL for all state management
   - Call workers via HTTP for heavy computation
   - Log events to `cineos_core.events`
   - Update state in the appropriate table
3. Export the workflow JSON
4. Save it to `workflows/` with the next numeric prefix
5. Add the state transition to the state machine in `sql/init.sql`
6. Update the orchestrator (workflow 002) to dispatch to the new workflow
7. Test with a small project

### Workflow Pattern

Every workflow follows this pattern:

```json
{
  "nodes": [
    {
      "type": "n8n-nodes-base.postgres",
      "name": "Check State",
      "parameters": { "query": "SELECT current_state FROM cineos_core.projects WHERE project_id = '{{$json.project_id}}'" }
    },
    {
      "type": "n8n-nodes-base.httpRequest",
      "name": "Call Worker",
      "parameters": { "url": "http://worker:port/task" }
    },
    {
      "type": "n8n-nodes-base.postgres",
      "name": "Update State",
      "parameters": { "query": "UPDATE cineos_core.projects SET current_state = 'next_state' WHERE project_id = '{{$json.project_id}}'" }
    }
  ]
}
```

## Debugging Workflows

### Check n8n Execution History

1. Open `http://localhost:5678`
2. Click on the workflow
3. Go to "Executions" tab
4. Click on a failed execution to see the error

### Check Database State

```sql
-- Find stuck projects
SELECT project_id, title, current_state, last_error, updated_at
FROM cineos_core.projects
WHERE current_state NOT IN ('completed', 'failed', 'cancelled')
ORDER BY updated_at DESC;

-- Check recent events
SELECT event_type, severity, message, created_at
FROM cineos_core.events
ORDER BY created_at DESC LIMIT 20;

-- Check failed jobs
SELECT job_id, job_type, state, error_message, created_at
FROM cineos_exec.jobs
WHERE state = 'failed'
ORDER BY created_at DESC LIMIT 10;
```

### Check Workflow Execution Logs

```sql
SELECT workflow_name, state, error_data, duration_ms, created_at
FROM cineos_exec.workflow_executions
WHERE state = 'failed'
ORDER BY created_at DESC LIMIT 10;
```

### Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Workflow never starts | n8n webhook not registered | Re-import the workflow |
| Stuck in "generating" | Worker offline or overloaded | Check worker health: `make health` |
| Quality always fails | Threshold too high | Lower `QUALITY_THRESHOLD` in `.env` |
| Memory errors | Too many parallel jobs | Lower `MAX_PARALLEL_JOBS` in `.env` |
| Timeout errors | Worker too slow | Increase timeout in `config/workers.yaml` |

## Monitoring Workflows

### Real-Time Dashboard

Open `http://localhost:5678` to see workflow execution status, active workflows, and recent errors.

### Database Monitoring

```sql
-- Active projects by state
SELECT current_state, COUNT(*) as count
FROM cineos_core.projects
WHERE current_state NOT IN ('completed', 'failed', 'cancelled')
GROUP BY current_state ORDER BY count DESC;

-- Average processing time per phase
SELECT
    workflow_name,
    COUNT(*) as executions,
    AVG(duration_ms)/1000 as avg_seconds,
    MAX(duration_ms)/1000 as max_seconds
FROM cineos_exec.workflow_executions
WHERE state = 'completed'
GROUP BY workflow_name
ORDER BY avg_seconds DESC;
```

### Worker Health

```bash
curl http://localhost:8000/api/workers | python -m json.tool
```
