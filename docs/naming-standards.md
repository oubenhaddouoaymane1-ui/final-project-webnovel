# CineOS Naming Standards

This document defines the naming conventions used across the CineOS cinematic production platform. Consistent naming improves readability, reduces ambiguity, and makes the codebase easier to navigate.

---

## Workflows

Workflow files follow a numbered prefix pattern with snake_case naming:

```
NNN_snake_case.json
```

Examples:
- `001_novel_ingestion.json`
- `012_scene_rendering.json`
- `099_post_processing.json`

The numeric prefix defines execution order. Use zero-padded three-digit numbers to preserve sort order.

---

## Database

### Tables

- Convention: `snake_case`
- Schema prefix: `cineos_schema.table_name`
- Use plural nouns for entity tables (e.g., `projects`, `scenes`, `shots`).

Examples:
- `cineos_schema.projects`
- `cineos_schema.scene_annotations`
- `cineos_schema.character_profiles`

### Columns

- Convention: `snake_case`
- Foreign keys: `referenced_table_id` (e.g., `project_id`, `character_id`)

Examples:
- `created_at`
- `updated_at`
- `shot_sequence_number`

### Indexes

- Convention: `idx_tablename_column`

Examples:
- `idx_projects_status`
- `idx_scenes_project_id`
- `idx_shots_sequence_number`

### Foreign Keys

- Convention: `fk_tablename_referencedColumn`

Examples:
- `fk_scenes_projectId`
- `fk_shots_sceneId`

---

## Python

### Files

- Convention: `snake_case.py`

Examples:
- `novel_processor.py`
- `scene_generator.py`
- `character_tracker.py`

### Classes

- Convention: `PascalCase`

Examples:
- `SceneRenderer`
- `CharacterTracker`
- `NovelIngestionPipeline`

### Functions and Methods

- Convention: `snake_case`

Examples:
- `render_scene()`
- `extract_character_arc()`
- `validate_novel_structure()`

### Variables

- Convention: `snake_case`

Examples:
- `scene_count`
- `character_name`
- `render_duration`

### Constants

- Convention: `UPPER_SNAKE_CASE`

Examples:
- `MAX_SCENE_DURATION`
- `DEFAULT_FRAME_RATE`
- `SUPPORTED_OUTPUT_FORMATS`

---

## Events

- Convention: `UPPER_SNAKE_CASE`

Examples:
- `SCENE_RENDER_COMPLETE`
- `NOVEL_INGESTION_STARTED`
- `CHARACTER_AMBIGUITY_DETECTED`

---

## States

- Convention: `lowercase`

Examples:
- `pending`
- `in_progress`
- `completed`
- `failed`

---

## Configuration

### Config Keys

- Convention: `section.subsection.key`

Examples:
- `database.host`
- `database.pool.max_connections`
- `rendering.output.format`
- `auth.token_expiry_seconds`

---

## API

### Endpoints

- Convention: `/api/resource` or `/api/resource/{id}`
- Use plural nouns for resource names.

Examples:
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}/scenes/{scene_id}`

### Webhooks

- Convention: `/webhook/action_name`

Examples:
- `POST /webhook/render_complete`
- `POST /webhook/ingestion_finished`

---

## Docker

### Services

- Convention: `cineos-service-name`

Examples:
- `cineos-api`
- `cineos-worker-render`
- `cineos-database`

### Image Names

- Convention: `cineos-component`

Examples:
- `cineos-api`
- `cineos-worker`
- `cineos-scheduler`

---

## Environment Variables

- Convention: `UPPER_SNAKE_CASE`

Examples:
- `CINEOS_DB_HOST`
- `CINEOS_RENDER_WORKERS`
- `CINEOS_LOG_LEVEL`
- `CINEOS_API_SECRET_KEY`

---

## File Paths

- Directories: `kebab-case/`
- Files: `snake_case.ext`

Examples:
- `src/novel-processor/character_extractor.py`
- `workers/scene-renderer/config/settings.json`
- `docs/naming-standards.md`

---

## Git

### Branches

- Convention: `type/description`
- Types: `feature`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
- `feature/character-arc-tracker`
- `fix/scene-render-timeout`
- `docs/api-reference-update`
- `refactor/novel-parsing-pipeline`

### Commit Messages

- Use imperative mood ("add feature" not "added feature").
- Keep the subject line under 72 characters.
- Reference issue numbers where applicable.

Examples:
- `Add character arc tracking to scene pipeline`
- `Fix timeout in scene renderer under high load`
- `Update API docs for v2 endpoints`

---

## Logging

### Log Prefixes

- Convention: `[ComponentName]`

Examples:
- `[SceneRenderer] Scene 42 completed in 3.2s`
- `[NovelIngestion] Parsing chapter 7 of source document`
- `[CharacterTracker] Ambiguity detected for character "John"`

---

## JSON

### Keys

- Convention: `snake_case`

Examples:
- `scene_id`
- `character_name`
- `render_status`

---

## URL Slugs

- Convention: `kebab-case`

Examples:
- `/projects/my-cinematic-masterpiece`
- `/scenes/act-one-opening`
