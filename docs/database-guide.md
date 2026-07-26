# CineOS Database Guide

CineOS uses PostgreSQL 16 as its single source of truth. The database is organized into 7 schemas, each with a specific responsibility. This guide covers the schema overview, all tables, views, functions, triggers, and operational procedures.

## Schema Overview

| Schema | Purpose | Key Tables |
|--------|---------|------------|
| `cineos_core` | Core entities: projects, scenes, shots, characters, locations | projects, scenes, shots, characters, locations, events, state_log |
| `cineos_memory` | Persistent memory: bibles, references, patterns | story_bibles, character_bibles, world_bibles, prompt_patterns |
| `cineos_gen` | Generated assets: images, audio, video | images, audio, video_clips, final_videos, prompt_versions |
| `cineos_quality` | Quality control: reviews, repairs, checks | reviews, thresholds, repairs, checks |
| `cineos_exec` | Execution: workers, jobs, workflows | workers, jobs, workflow_executions |
| `cineos_audit` | Audit: logs, learning | learning_records, execution_log |
| `cineos_config` | Configuration: system config, versions | system_config, versions |

## Core Schema (`cineos_core`)

### projects

The central table. Every novel-to-video pipeline creates one project record.

```sql
cineos_core.projects
├── project_id UUID PK
├── user_id BIGINT           -- Telegram user ID
├── chat_id BIGINT           -- Telegram chat ID
├── title TEXT               -- Novel title
├── current_state project_state  -- Current pipeline state
├── previous_state project_state
├── language VARCHAR(20)
├── progress FLOAT           -- 0.0 to 1.0
├── priority INTEGER         -- 1 (highest) to 10 (lowest)
├── retry_count INTEGER
├── max_retries INTEGER
├── error_count INTEGER
├── last_error TEXT
├── created_at TIMESTAMPTZ
├── updated_at TIMESTAMPTZ
├── started_at TIMESTAMPTZ
├── completed_at TIMESTAMPTZ
├── checkpoint_data JSONB
├── config JSONB
└── metadata JSONB
```

### State Machine

Projects progress through 27 states:

```
received → validated → parsed → understood → biblified → characterized
→ worldbuilt → timeline_verified → planned → prompted → queued
→ generating → generated → reviewing → [repairing →] approved
→ voiced → musicked → animated → rendering → rendered
→ super_resolution → final_review → delivered → learned → completed
```

Terminal states: `completed`, `failed`, `cancelled`
Pause states: `waiting`, `paused`, `manual_attention`

### scenes

Scene-level data extracted from novels:

```sql
cineos_core.scenes
├── scene_id UUID PK
├── project_id UUID FK → projects
├── chapter_id UUID FK → chapters
├── chapter_number INTEGER
├── scene_number INTEGER
├── state scene_state
├── full_text TEXT           -- Original scene text
├── summary TEXT
├── location_name TEXT
├── primary_emotion VARCHAR(50)
├── emotional_intensity FLOAT
├── conflict_type VARCHAR(50)
├── has_dialogue BOOLEAN
├── has_action BOOLEAN
├── shot_count INTEGER
├── quality_score FLOAT
└── music_profile JSONB
```

### shots

Individual shots within scenes:

```sql
cineos_core.shots
├── shot_id UUID PK
├── scene_id UUID FK → scenes
├── project_id UUID FK → projects
├── shot_number INTEGER
├── state shot_state
├── shot_type VARCHAR(50)
├── duration_seconds FLOAT
├── camera_angle VARCHAR(50)
├── camera_movement VARCHAR(50)
├── lighting_style VARCHAR(50)
├── animation_type VARCHAR(50)
├── positive_prompt TEXT
├── negative_prompt TEXT
├── narration_text TEXT
└── quality_score FLOAT
```

### characters

Character profiles extracted from novels:

```sql
cineos_core.characters
├── character_id UUID PK
├── project_id UUID FK → projects
├── canonical_name TEXT
├── role VARCHAR(50)         -- protagonist, antagonist, supporting
├── physical attributes      -- 30+ columns for face, hair, body
├── personality traits       -- personality_traits, fears, desires
├── visual_prompt_positive TEXT
├── visual_prompt_negative TEXT
├── voice_parameters JSONB
├── relationships JSONB
├── confidence_score FLOAT
└── locked BOOLEAN
```

### locations

World locations with visual descriptions:

```sql
cineos_core.locations
├── location_id UUID PK
├── project_id UUID FK → projects
├── name TEXT
├── location_type VARCHAR(50)
├── description TEXT
├── atmosphere TEXT
├── color_palette TEXT[]
├── visual_keywords TEXT[]
├── visual_prompt_positive TEXT
├── visual_prompt_negative TEXT
└── time_of_day_variants JSONB
```

### Additional Core Tables

| Table | Purpose |
|-------|---------|
| `chapters` | Chapter-level text and metadata |
| `scene_characters` | Scene-character junction with dialogue |
| `event_types` | Event type definitions |
| `events` | All system events |
| `state_log` | State transition history |
| `versions` | Entity version tracking |
| `checkpoints` | Pipeline checkpoint snapshots |

## Memory Schema (`cineos_memory`)

### Bibles

| Table | Purpose |
|-------|---------|
| `story_bibles` | Comprehensive story analysis: genre, themes, conflict, arc |
| `character_bibles` | Detailed character descriptions and visual prompts |
| `world_bibles` | World geography, culture, architecture, magic systems |
| `timeline_bibles` | Chronological event ordering |
| `style_bibles` | Visual style guide: palettes, lighting, camera preferences |

### References

| Table | Purpose |
|-------|---------|
| `character_references` | Generated reference images for characters |
| `world_references` | Generated reference images for locations |
| `style_references` | Style reference images |

### Knowledge Base

| Table | Purpose |
|-------|---------|
| `prompt_patterns` | Learned prompt patterns with success rates |
| `backend_performance` | Historical performance data per backend |

## Generation Schema (`cineos_gen`)

### Asset Tables

| Table | Purpose |
|-------|---------|
| `images` | Generated images with metadata, prompts, and scores |
| `audio` | Generated TTS audio with voice parameters |
| `video_clips` | Animated video clips per shot |
| `final_videos` | Completed video outputs |
| `prompt_versions` | Version history of generated prompts |

### Image Record Structure

```sql
cineos_gen.images
├── image_id UUID PK
├── shot_id UUID FK → shots
├── project_id UUID FK → projects
├── state asset_state
├── variant_number INTEGER
├── image_path TEXT
├── prompt_used TEXT
├── negative_prompt_used TEXT
├── backend_used VARCHAR(100)
├── model_used VARCHAR(200)
├── seed INTEGER
├── quality_score FLOAT
├── technical_quality_score FLOAT
├── prompt_alignment_score FLOAT
├── character_consistency_score FLOAT
├── is_selected BOOLEAN
├── is_upscaled BOOLEAN
└── repair_count INTEGER
```

## Quality Schema (`cineos_quality`)

### reviews

Every quality review creates a record with per-criteria scores:

```sql
cineos_quality.reviews
├── review_id UUID PK
├── project_id UUID FK → projects
├── entity_type VARCHAR(50)   -- image, audio, video
├── entity_id UUID
├── overall_score FLOAT
├── technical_quality_score FLOAT
├── prompt_alignment_score FLOAT
├── character_consistency_score FLOAT
├── passed BOOLEAN
├── decision VARCHAR(50)      -- approved, minor_repair, partial_repair, regenerate
├── issues JSONB
└── reviewer_model VARCHAR(100)
```

### Quality Decisions

| Score Range | Decision | Action |
|-------------|----------|--------|
| > 0.90 | auto_approve | No action needed |
| 0.80 - 0.90 | minor_repair | Fix minor issues |
| 0.60 - 0.80 | partial_repair | Fix specific problems |
| < 0.60 | regenerate | Generate new asset |

### Additional Quality Tables

| Table | Purpose |
|-------|---------|
| `thresholds` | Per-project quality thresholds |
| `repairs` | Repair attempt history |
| `checks` | Individual quality check results |

## Execution Schema (`cineos_exec`)

### workers

Registered AI workers:

```sql
cineos_exec.workers
├── worker_id UUID PK
├── worker_name VARCHAR(200)
├── worker_type VARCHAR(50)
├── state worker_state
├── host VARCHAR(200)
├── port INTEGER
├── endpoint_url TEXT
├── supported_backends TEXT[]
├── supported_task_types TEXT[]
├── gpu_model TEXT
├── gpu_vram_gb FLOAT
├── last_heartbeat TIMESTAMPTZ
├── current_load FLOAT
├── max_concurrent_tasks INTEGER
├── total_tasks_completed INTEGER
├── success_rate FLOAT
└── health_status VARCHAR(50)
```

### jobs

Job queue:

```sql
cineos_exec.jobs
├── job_id UUID PK
├── project_id UUID FK → projects
├── job_type VARCHAR(100)
├── state job_state
├── worker_id UUID FK → workers
├── priority INTEGER
├── payload JSONB
├── result JSONB
├── timeout_ms INTEGER
├── error_message TEXT
└── depends_on UUID[]
```

### workflow_executions

n8n execution tracking:

```sql
cineos_exec.workflow_executions
├── execution_id UUID PK
├── project_id UUID FK → projects
├── workflow_name VARCHAR(200)
├── n8n_execution_id VARCHAR(100)
├── state VARCHAR(50)
├── trigger_data JSONB
├── result_data JSONB
├── duration_ms INTEGER
└── attempt_number INTEGER
```

## Audit Schema (`cineos_audit`)

| Table | Purpose |
|-------|---------|
| `learning_records` | Completed project metrics for learning |
| `execution_log` | Node-level execution logs |

## Configuration Schema (`cineos_config`)

| Table | Purpose |
|-------|---------|
| `system_config` | Key-value configuration store |
| `versions` | Component version tracking |

## Views

Key analytical views defined in `database/views.sql`:

```sql
-- Active projects with progress
cineos_core.active_projects

-- Worker utilization
cineos_exec.worker_utilization

-- Quality statistics
cineos_quality.quality_stats

-- Project timeline
cineos_core.project_timeline
```

## Functions

| Function | Purpose |
|----------|---------|
| `cineos_core.update_timestamp()` | Auto-updates `updated_at` column |
| `cineos_core.check_all_scenes_completed()` | Triggers rendering when all scenes done |
| `cineos_core.create_checkpoint_on_phase()` | Auto-creates checkpoint on phase completion |
| `cineos_core.update_project_progress()` | Calculates progress percentage from state |
| `cineos_core.enforce_state_transition()` | Validates state machine transitions |

## Triggers

| Trigger | Table | Event | Purpose |
|---------|-------|-------|---------|
| `trg_projects_updated` | projects | BEFORE UPDATE | Updates `updated_at` |
| `trg_scenes_updated` | scenes | BEFORE UPDATE | Updates `updated_at` |
| `trg_shots_updated` | shots | BEFORE UPDATE | Updates `updated_at` |
| `trg_characters_updated` | characters | BEFORE UPDATE | Updates `updated_at` |
| `trg_scenes_check_completed` | scenes | AFTER UPDATE | Triggers rendering on completion |
| `trg_projects_checkpoint` | projects | AFTER UPDATE | Creates checkpoints |
| `trg_projects_progress` | projects | BEFORE UPDATE | Updates progress % |

## Migration Guide

### Running Migrations

```bash
# Via Makefile
make db-migrate

# Via script
python scripts/migrate_db.py

# Manual
psql -U cineos -d cineos -f database/schema.sql
psql -U cineos -d cineos -f database/indexes.sql
psql -U cineos -d cineos -f database/constraints.sql
psql -U cineos -d cineos -f database/functions.sql
psql -U cineos -d cineos -f database/triggers.sql
psql -U cineos -d cineos -f database/views.sql
```

### Adding a New Table

1. Write the CREATE TABLE statement in the appropriate schema
2. Add it to `database/schema.sql`
3. Add indexes to `database/indexes.sql`
4. Add constraints to `database/constraints.sql`
5. Run `make db-migrate`

### Adding a New Column

```sql
ALTER TABLE cineos_core.projects
ADD COLUMN new_column VARCHAR(50) DEFAULT 'default_value';
```

## Backup and Restore

### Quick Backup

```bash
# Database only
make backup-db

# Full system backup (DB + workflows + prompts + config + learning data)
./scripts/backup.sh
```

### Quick Restore

```bash
# Database only
make restore-db

# Full system restore
./scripts/restore.sh latest
./scripts/restore.sh 20260726_143000
```

### Automated Backups

```bash
# Install daily cron job
./scripts/cron_backup.sh install
```

See [Installation Guide](installation.md) for full backup/restore details.

## Common Queries

### Find Stuck Projects

```sql
SELECT project_id, title, current_state, updated_at,
       NOW() - updated_at as stuck_duration
FROM cineos_core.projects
WHERE current_state NOT IN ('completed', 'failed', 'cancelled')
AND updated_at < NOW() - INTERVAL '1 hour'
ORDER BY updated_at;
```

### Quality Statistics

```sql
SELECT
    entity_type,
    COUNT(*) as total_reviews,
    AVG(overall_score) as avg_score,
    SUM(CASE WHEN passed THEN 1 ELSE 0 END)::float / COUNT(*) as pass_rate
FROM cineos_quality.reviews
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY entity_type;
```

### Worker Performance

```sql
SELECT
    worker_type,
    COUNT(*) as total_tasks,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate,
    AVG(quality_score) as avg_quality,
    AVG(latency_ms) as avg_latency_ms
FROM cineos_memory.backend_performance
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY worker_type;
```

### Storage Usage

```sql
SELECT
    schemaname,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as size
FROM pg_tables
WHERE schemaname LIKE 'cineos_%'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;
```
