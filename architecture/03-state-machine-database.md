# PART 3 — STATE MACHINE, CENTRAL MEMORY, DATABASE ARCHITECTURE, EVENT SYSTEM, AND PROJECT LIFECYCLE

## CineOS — Complete State Machine and Database Specification

---

## 1. CORE PHILOSOPHY

The entire platform is driven by a strict State Machine.

No workflow may execute unless the current state explicitly allows it.

Every transition must be:
- Validated
- Logged
- Versioned
- Recoverable
- Repeatable

The database is the only source of truth.

No workflow may rely on temporary RAM memory.

---

## 2. PROJECT LIFECYCLE — COMPLETE STATE SEQUENCE

```
received
    ↓
validated
    ↓
parsed
    ↓
understood
    ↓
biblified
    ↓
characterized
    ↓
worldbuilt
    ↓
timeline_verified
    ↓
planned
    ↓
prompted
    ↓
queued
    ↓
generating
    ↓
generated
    ↓
reviewing
    ↓
repairing (optional, loops back to reviewing)
    ↓
approved
    ↓
voiced
    ↓
musicked
    ↓
animated
    ↓
rendering
    ↓
rendered
    ↓
super_resolution (optional)
    ↓
final_review
    ↓
delivered
    ↓
learned
    ↓
completed
```

---

## 3. GLOBAL STATE MACHINE

### 3.1 State Type System

```sql
CREATE TYPE project_state AS ENUM (
    -- Normal lifecycle states (27 states)
    'received',
    'validated',
    'parsed',
    'understood',
    'biblified',
    'characterized',
    'worldbuilt',
    'timeline_verified',
    'planned',
    'prompted',
    'queued',
    'generating',
    'generated',
    'reviewing',
    'repairing',
    'approved',
    'voiced',
    'musicked',
    'animated',
    'rendering',
    'rendered',
    'super_resolution',
    'final_review',
    'delivered',
    'learned',
    'completed',
    -- Error/pause states (6 states)
    'waiting',
    'paused',
    'retrying',
    'failed',
    'manual_attention',
    'cancelled'
);

CREATE TYPE scene_state AS ENUM (
    'pending',
    'extracting',
    'extracted',
    'analyzing',
    'analyzed',
    'planning',
    'planned',
    'generating',
    'generated',
    'reviewing',
    'passed',
    'failed',
    'repairing',
    'assembled',
    'completed'
);

CREATE TYPE shot_state AS ENUM (
    'pending',
    'planning',
    'planned',
    'prompting',
    'prompted',
    'generating_image',
    'image_generated',
    'generating_audio',
    'audio_generated',
    'reviewing',
    'passed',
    'failed',
    'repairing',
    'animating',
    'animated',
    'assembled',
    'completed'
);

CREATE TYPE asset_state AS ENUM (
    'pending',
    'generating',
    'generated',
    'reviewing',
    'passed',
    'failed',
    'repairing',
    'repaired',
    'supersampled',
    'archived'
);

CREATE TYPE job_state AS ENUM (
    'pending',
    'queued',
    'assigned',
    'running',
    'completed',
    'failed',
    'timeout',
    'cancelled'
);

CREATE TYPE worker_state AS ENUM (
    'registering',
    'idle',
    'busy',
    'overloaded',
    'offline',
    'error',
    'maintenance',
    'deregistered'
);

CREATE TYPE event_severity AS ENUM (
    'debug',
    'info',
    'warning',
    'error',
    'critical'
);
```

### 3.2 State Definition Table

Every state is formally defined with entry conditions, exit conditions, allowed transitions, database updates, recovery strategy, retry policy, timeout policy, and owner workflow.

```sql
CREATE TABLE cineos.core.state_definitions (
    state_name VARCHAR(100) PRIMARY KEY,
    state_category VARCHAR(50) NOT NULL,       -- 'lifecycle', 'bible', 'reference', 'planning', 'generation', 'quality', 'media', 'final', 'error'
    state_order INTEGER NOT NULL,              -- canonical ordering in lifecycle

    -- Entry conditions (all must be true to enter this state)
    entry_conditions JSONB NOT NULL,           -- [{check: 'sql', query: '...'}, {check: 'exists', table: '...', where: '...'}]

    -- Exit conditions (all must be true to leave this state)
    exit_conditions JSONB NOT NULL,            -- [{check: 'sql', query: '...'}, {check: 'event', event_type: '...'}]

    -- Allowed transitions
    allowed_previous_states project_state[] NOT NULL,
    allowed_next_states project_state[] NOT NULL,

    -- Required database updates on entry
    entry_db_updates JSONB NOT NULL,           -- [{table: '...', operation: 'update', set: {...}, where: '...'}]

    -- Required database updates on exit
    exit_db_updates JSONB NOT NULL,            -- [{table: '...', operation: 'update', set: {...}, where: '...'}]

    -- Recovery
    recovery_strategy VARCHAR(50) NOT NULL,    -- 'resume_from_start', 'resume_from_checkpoint', 'retry_last_action', 'manual_intervention'
    retry_policy JSONB NOT NULL,               -- {max_retries: 3, backoff: 'exponential', base_delay_ms: 1000, max_delay_ms: 300000}
    timeout_ms INTEGER NOT NULL,               -- 0 = no timeout

    -- Owner
    owner_workflow VARCHAR(200) NOT NULL,      -- which n8n workflow owns this state

    -- Metadata
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 Complete State Definitions

```sql
-- ═══════════════════════════════════════════════════════════════
-- LIFECYCLE STATES
-- ═══════════════════════════════════════════════════════════════

INSERT INTO cineos.core.state_definitions VALUES
('received', 'lifecycle', 1,
 '{"all": [{"check": "exists", "table": "projects", "where": "project_id = $project_id AND novel_id IS NOT NULL"}]}',
 '{"all": [{"check": "sql", "query": "SELECT COUNT(*) > 0 FROM novels WHERE project_id = $project_id AND cleaned_text IS NOT NULL AND word_count >= 50"}]}',
 '{}',
 '{"allowed_next_states": ["validated", "cancelled"]}',
 '{"update": {"table": "projects", "set": {"progress": 0.02}, "where": "project_id = $project_id"}}',
 '{"update": {"table": "projects", "set": {"progress": 0.02}, "where": "project_id = $project_id"}}',
 'resume_from_start',
 '{"max_retries": 3, "backoff": "exponential", "base_delay_ms": 1000, "max_delay_ms": 300000}',
 60000,
 'telegram_intake',
 'Novel received via Telegram. Project created. Awaiting validation.');

-- Continue for all 27+ states...
```

### 3.4 State Transition Matrix

Complete allowed transitions:

```
┌─────────────────────────┬───────────────────────────────────────────┬───────────────────────────────────────────┐
│ CURRENT STATE           │ ALLOWED NEXT STATES                       │ REQUIRED CONDITION                        │
├─────────────────────────┼───────────────────────────────────────────┼───────────────────────────────────────────┤
│ received                │ validated, cancelled                      │ novel exists, word_count >= 50            │
│ validated               │ parsed, failed                            │ encoding valid, language detected         │
│ parsed                  │ understood, failed                        │ chapters extracted, scenes extracted      │
│ understood              │ biblified, failed                         │ story graph complete                      │
│ biblified               │ characterized, failed                     │ all 5 bibles created                      │
│ characterized           │ worldbuilt, failed                        │ all character bibles locked               │
│ worldbuilt              │ timeline_verified, failed                 │ world bible locked                        │
│ timeline_verified       │ planned, failed                           │ timeline consistent, no conflicts         │
│ planned                 │ prompted, failed                          │ all scenes have shots planned             │
│ prompted                │ queued, failed                            │ all shots have prompts generated          │
│ queued                  │ generating, failed                        │ all jobs submitted to queue               │
│ generating              │ generated, failed, retrying               │ all jobs completed                        │
│ generated               │ reviewing, failed                         │ all assets generated                      │
│ reviewing               │ approved, repairing, failed               │ quality review complete                   │
│ repairing               │ reviewing, retrying, failed, manual_attention │ repair attempts < max_retries         │
│ approved                │ voiced, failed                            │ assets accepted                           │
│ voiced                  │ musicked, failed                          │ narration generated                       │
│ musicked                │ animated, failed                          │ music plan attached                       │
│ animated                │ rendering, failed                         │ all clips animated                        │
│ rendering               │ rendered, failed, retrying                │ video rendering started                   │
│ rendered                │ super_resolution, final_review, failed     │ video file exists                         │
│ super_resolution        │ final_review, failed                      │ upscaled (or skipped)                     │
│ final_review            │ delivered, failed, repairing              │ final review complete                     │
│ delivered               │ learned, failed                           │ telegram delivery sent                    │
│ learned                 │ completed, failed                         │ learning data recorded                    │
│ completed               │ (terminal)                                │ project archived                          │
├─────────────────────────┼───────────────────────────────────────────┼───────────────────────────────────────────┤
│ waiting                 │ (previous state), cancelled               │ manual intervention received              │
│ paused                  │ (previous state), cancelled               │ resume signal received                    │
│ retrying                │ (previous state), cancelled               │ retry conditions met                      │
│ failed                  │ retrying, cancelled, manual_attention     │ admin intervention                        │
│ manual_attention        │ (previous state), cancelled               │ admin action taken                        │
│ cancelled               │ (terminal)                                │ user or admin cancellation                │
└─────────────────────────┴───────────────────────────────────────────┴───────────────────────────────────────────┘
```

### 3.5 State Machine Controller — n8n Workflow

```
state_machine_controller
├── [1] Trigger
│   ├── Webhook: { project_id, requested_state, reason, triggered_by }
│   └── Cron: every 30 seconds, check for stuck projects
├── [2] Load Current State
│   └── PostgreSQL: SELECT current_state, retry_count, error_count, last_state_change_at
│       FROM projects WHERE project_id = $project_id
├── [3] Transition Validation
│   ├── [3a] Load state definition for current_state
│   ├── [3b] Check: requested_state IN allowed_next_states
│   ├── [3c] If invalid: REJECT with reason, log violation event
│   └── [3d] If valid: proceed
├── [4] Entry Condition Check
│   ├── [4a] Load state definition for requested_state
│   ├── [4b] Execute each entry_condition check
│   ├── [4c] If any check fails: REJECT, log which condition failed
│   └── [4d] If all pass: proceed
├── [5] Atomic Transition
│   ├── BEGIN TRANSACTION
│   ├── UPDATE projects SET current_state = $requested_state, updated_at = NOW()
│   ├── If affected_rows = 0: CONFLICT (concurrent modification)
│   │   ├── ROLLBACK
│   │   └── Return conflict error
│   ├── INSERT INTO state_log (project_id, old_state, new_state, workflow, timestamp, operator)
│   ├── INSERT INTO events (project_id, event_type, workflow, state_before, state_after, timestamp, payload)
│   ├── Execute entry_db_updates from state definition
│   ├── COMMIT
│   └── Return success
├── [6] Workflow Dispatch
│   ├── [6a] Determine owner_workflow from state definition
│   ├── [6b] HTTP POST to n8n webhook for owner_workflow
│   └── [6c] Body: { project_id, state: requested_state }
├── [7] Timeout Monitor
│   ├── [7a] Cron: every 60 seconds
│   ├── [7b] For each project in *_running state:
│   │   ├── Check: NOW() - last_state_change_at > timeout_ms
│   │   ├── If timeout: transition to 'waiting' or 'retrying'
│   │   └── Log event: 'state_timeout'
│   └── [7c] For each project in 'generating' or 'rendering':
│       ├── Check job completion status
│       └── If all jobs complete: transition to next state
├── [8] Deadlock Detector
│   ├── [8a] Cron: every 5 minutes
│   ├── [8b] Projects with no state change in 30+ minutes while not in terminal states
│   ├── [8c] If detected: transition to 'paused', notify admin
│   └── [8d] Log event: 'deadlock_detected'
└── [9] Stuck Project Recovery
    ├── [9a] Projects in 'waiting' or 'paused' with no activity for 24+ hours
    ├── [9b] Send notification to admin
    └── [9c] Log event: 'project_stuck'
```

### 3.6 Scene State Transition Matrix

```
┌──────────────┬───────────────────────────────────────┬──────────────────────────────┐
│ CURRENT      │ ALLOWED NEXT                          │ TRIGGER                      │
├──────────────┼───────────────────────────────────────┼──────────────────────────────┤
│ pending      │ extracting                            │ scene_extractor workflow      │
│ extracting   │ extracted, failed                     │ extraction complete          │
│ extracted    │ analyzing                             │ scene_analyzer workflow       │
│ analyzing    │ analyzed, failed                      │ LLM analysis complete         │
│ analyzed     │ planning                              │ shot_planner workflow          │
│ planning     │ planned, failed                       │ planning complete              │
│ planned      │ generating                            │ image_generator workflow       │
│ generating   │ generated, failed, repairing          │ generation complete            │
│ generated    │ reviewing                             │ quality_reviewer workflow      │
│ reviewing    │ passed, failed, repairing             │ review complete                │
│ passed       │ assembled                             │ clip_assembler workflow        │
│ failed       │ repairing, pending                    │ repair_dispatcher workflow     │
│ repairing    │ reviewing, failed                     │ repair complete                │
│ assembled    │ completed                             │ video_renderer workflow        │
│ completed    │ (terminal)                            │ project completed              │
└──────────────┴───────────────────────────────────────┴──────────────────────────────┘
```

### 3.7 Shot State Transition Matrix

```
┌──────────────────┬───────────────────────────────────┬──────────────────────────────────┐
│ CURRENT          │ ALLOWED NEXT                      │ TRIGGER                          │
├──────────────────┼───────────────────────────────────┼──────────────────────────────────┤
│ pending          │ planning                          │ shot_planner workflow             │
│ planning         │ planned, failed                   │ planning complete                 │
│ planned          │ prompting                         │ prompt_generator workflow          │
│ prompting        │ prompted, failed                  │ prompt generation complete        │
│ prompted         │ generating_image                  │ image_generator workflow           │
│ generating_image │ image_generated, failed           │ image generation complete         │
│ image_generated  │ generating_audio                  │ audio_generator workflow           │
│ generating_audio │ audio_generated, failed           │ audio generation complete         │
│ audio_generated  │ reviewing                         │ quality_reviewer workflow          │
│ reviewing        │ passed, failed, repairing         │ review complete                    │
│ passed           │ animating                         │ clip_assembler workflow            │
│ failed           │ repairing, pending                │ repair_dispatcher workflow         │
│ repairing        │ reviewing, failed                 │ repair complete                    │
│ animating        │ animated, failed                  │ animation complete                 │
│ animated         │ assembled                         │ clip render complete               │
│ assembled        │ completed                         │ project assembled                 │
│ completed        │ (terminal)                        │ project completed                  │
└──────────────────┴───────────────────────────────────┴──────────────────────────────────┘
```

---

## 4. EVENT SYSTEM

### 4.1 Event Types

```sql
CREATE TABLE cineos.core.event_types (
    event_type VARCHAR(100) PRIMARY KEY,
    category VARCHAR(50) NOT NULL,             -- 'lifecycle', 'quality', 'generation', 'error', 'system'
    severity VARCHAR(20) NOT NULL,             -- 'debug', 'info', 'warning', 'error', 'critical'
    description TEXT NOT NULL,
    payload_schema JSONB,                      -- expected payload structure
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO cineos.core.event_types (event_type, category, severity, description) VALUES
-- Lifecycle Events
('PROJECT_CREATED',            'lifecycle',   'info',     'New project created from Telegram intake'),
('PROJECT_VALIDATED',          'lifecycle',   'info',     'Project input validated successfully'),
('STORY_PARSED',               'lifecycle',   'info',     'Story parsed into chapters and scenes'),
('STORY_ANALYZED',             'lifecycle',   'info',     'Story intelligence analysis complete'),
('STORY_BIBLE_CREATED',        'lifecycle',   'info',     'Story Bible generated'),
('CHARACTER_BIBLE_CREATED',    'lifecycle',   'info',     'Character Bible generated and locked'),
('WORLD_BIBLE_CREATED',        'lifecycle',   'info',     'World Bible generated and locked'),
('TIMELINE_BIBLE_CREATED',     'lifecycle',   'info',     'Timeline Bible generated and verified'),
('STYLE_BIBLE_CREATED',        'lifecycle',   'info',     'Style Bible generated and locked'),
('CHARACTER_REFERENCE_CREATED','lifecycle',   'info',     'Character reference image generated'),
('WORLD_REFERENCE_CREATED',    'lifecycle',   'info',     'World reference image generated'),
('SCENE_PLANNED',              'lifecycle',   'info',     'Scene shot plan created'),
('SHOT_PLANNED',               'lifecycle',   'info',     'Individual shot planned'),
('PROMPTS_GENERATED',          'lifecycle',   'info',     'Structured prompts generated for all shots'),
('PROJECT_COMPLETED',          'lifecycle',   'info',     'Project fully completed'),

-- Generation Events
('JOB_CREATED',                'generation',  'info',     'New generation job created'),
('JOB_QUEUED',                 'generation',  'info',     'Job added to queue'),
('JOB_ASSIGNED',               'generation',  'info',     'Job assigned to worker'),
('JOB_STARTED',                'generation',  'info',     'Worker started processing job'),
('JOB_COMPLETED',              'generation',  'info',     'Job completed successfully'),
('JOB_FAILED',                 'generation',  'error',    'Job failed'),
('JOB_TIMEOUT',                'generation',  'warning',  'Job exceeded timeout'),
('IMAGE_GENERATED',            'generation',  'info',     'Image asset generated'),
('AUDIO_GENERATED',            'generation',  'info',     'Audio asset generated'),
('CLIP_RENDERED',              'generation',  'info',     'Video clip rendered'),
('VIDEO_RENDERED',             'generation',  'info',     'Final video rendered'),
('SUPER_RESOLUTION_APPLIED',   'generation',  'info',     'Super resolution applied to image'),

-- Quality Events
('QUALITY_REVIEW_STARTED',     'quality',     'info',     'Quality review initiated'),
('QUALITY_REVIEW_PASSED',      'quality',     'info',     'Quality review passed'),
('QUALITY_REVIEW_FAILED',      'quality',     'warning',  'Quality review failed'),
('QUALITY_REPAIR_TRIGGERED',   'quality',     'warning',  'Repair triggered for failed item'),
('QUALITY_REPAIR_COMPLETED',   'quality',     'info',     'Repair completed'),
('QUALITY_REPAIR_FAILED',      'quality',     'error',    'Repair failed after max attempts'),
('QUALITY_ESCALATED',          'quality',     'error',    'Quality issue escalated to manual attention'),
('QUALITY_THRESHOLD_UPDATED',  'quality',     'info',     'Quality threshold adjusted by learning engine'),

-- Error Events
('STATE_TIMEOUT',              'error',       'warning',  'Project stuck in state beyond timeout'),
('STATE_CONFLICT',             'error',       'error',    'Concurrent state modification detected'),
('DEADLOCK_DETECTED',          'error',       'critical', 'Project deadlock detected'),
('LIVELOCK_DETECTED',          'error',       'critical', 'Project livelock detected'),
('WORKER_OFFLINE',             'error',       'warning',  'Worker went offline'),
('WORKER_ALL_OFFLINE',         'error',       'critical', 'All workers of a type are offline'),
('BACKEND_FAILED',             'error',       'warning',  'Backend failed, switching to fallback'),
('BACKEND_EXHAUSTED',          'error',       'warning',  'Backend quota exhausted'),
('GPU_OOM',                    'error',       'error',    'GPU out of memory'),
('DISK_FULL',                  'error',       'critical', 'Disk space exhausted'),
('NETWORK_PARTITION',          'error',       'error',    'Network connectivity lost'),

-- System Events
('SYSTEM_STARTUP',             'system',      'info',     'System started'),
('SYSTEM_SHUTDOWN',            'system',      'info',     'System shutting down'),
('WORKER_REGISTERED',          'system',      'info',     'New worker registered'),
('WORKER_DEREGISTERED',        'system',      'info',     'Worker deregistered'),
('WORKER_HEARTBEAT',           'system',      'debug',    'Worker heartbeat received'),
('LEARNING_COMPLETED',         'system',      'info',     'Learning engine completed analysis'),
('THRESHOLD_TUNED',            'system',      'info',     'Quality thresholds tuned by learning'),
('BACKEND_RANKING_UPDATED',    'system',      'info',     'Backend preference rankings updated'),
('PROJECT_CANCELLED',          'lifecycle',   'info',     'Project cancelled by user or admin'),
('PROJECT_PAUSED',             'lifecycle',   'info',     'Project paused'),
('PROJECT_RESUMED',            'lifecycle',   'info',     'Project resumed from pause');
```

### 4.2 Event Storage

```sql
CREATE TABLE cineos.core.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,                           -- NULL for system-wide events
    event_type VARCHAR(100) NOT NULL REFERENCES cineos.core.event_types(event_type),
    workflow VARCHAR(200),                     -- which workflow emitted this event
    state_before VARCHAR(100),                 -- state before transition (if applicable)
    state_after VARCHAR(100),                  -- state after transition (if applicable)
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    message TEXT,
    payload JSONB DEFAULT '{}',                -- event-specific data
    metadata JSONB DEFAULT '{}',               -- additional context
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for event querying
CREATE INDEX idx_events_project ON cineos.core.events(project_id);
CREATE INDEX idx_events_type ON cineos.core.events(event_type);
CREATE INDEX idx_events_severity ON cineos.core.events(severity);
CREATE INDEX idx_events_created ON cineos.core.events(created_at);
CREATE INDEX idx_events_workflow ON cineos.core.events(workflow);
```

### 4.3 State Log

```sql
CREATE TABLE cineos.core.state_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL DEFAULT 'project',  -- 'project', 'scene', 'shot', 'asset'
    entity_id UUID NOT NULL,
    old_state VARCHAR(100),
    new_state VARCHAR(100) NOT NULL,
    workflow VARCHAR(200),                     -- which workflow triggered the transition
    operator VARCHAR(200),                     -- who triggered ('system', 'admin', 'user', workflow name)
    reason TEXT,                               -- why the transition happened
    validation_result JSONB,                   -- what checks were performed
    duration_ms INTEGER,                       -- time spent in old state
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_state_log_project ON cineos.core.state_log(project_id);
CREATE INDEX idx_state_log_entity ON cineos.core.state_log(entity_type, entity_id);
CREATE INDEX idx_state_log_new_state ON cineos.core.state_log(new_state);
CREATE INDEX idx_state_log_created ON cineos.core.state_log(created_at);
```

### 4.4 Event Emission Rule

```
EVENT EMISSION PROTOCOL:
────────────────────────

Every state transition MUST emit exactly 2 records:

1. state_log record:
   - project_id, entity_type, entity_id
   - old_state, new_state
   - workflow, operator, reason
   - duration_ms (time in old state)
   - created_at

2. events record:
   - project_id
   - event_type (derived from transition: e.g., PROJECT_CREATED, QUALITY_REVIEW_PASSED)
   - workflow
   - state_before, state_after
   - severity
   - message (human-readable description)
   - payload (entity-specific data)
   - created_at

Both records are written in the SAME transaction as the state update.
If either write fails, the entire transaction rolls back.
```

---

## 5. DATABASE ARCHITECTURE — COMPLETE SCHEMA

### 5.1 Schema Organization

```sql
CREATE SCHEMA IF NOT EXISTS cineos_core;      -- Projects, chapters, scenes, shots, core entities
CREATE SCHEMA IF NOT EXISTS cineos_memory;    -- Bibles, character data, world data
CREATE SCHEMA IF NOT EXISTS cineos_gen;       -- Generated assets (images, audio, video)
CREATE SCHEMA IF NOT EXISTS cineos_quality;   -- Reviews, scores, repairs
CREATE SCHEMA IF NOT EXISTS cineos_exec;      -- Workers, tasks, queue, jobs
CREATE SCHEMA IF NOT EXISTS cineos_audit;     -- Events, state log, learning, execution log
CREATE SCHEMA IF NOT EXISTS cineos_config;    -- System configuration, thresholds

-- Set default search path
ALTER DATABASE cineos SET search_path TO cineos_core, cineos_memory, cineos_gen, cineos_quality, cineos_exec, cineos_audit, cineos_config, public;
```

### 5.2 Core Schema — Projects

```sql
CREATE TABLE cineos_core.projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL,                    -- Telegram user ID
    chat_id BIGINT NOT NULL,                    -- Telegram chat ID
    title TEXT,
    current_state project_state NOT NULL DEFAULT 'received',
    previous_state project_state,               -- for transition validation
    language VARCHAR(20),                       -- 'en', 'ar', 'mixed'
    progress FLOAT DEFAULT 0.0,                 -- 0.0 to 1.0
    priority INTEGER DEFAULT 5,                 -- 1=highest, 10=lowest

    -- Retry tracking
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMPTZ,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,                     -- when processing began (state left 'received')
    last_state_change_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,

    -- Checkpoint data (for recovery)
    checkpoint_data JSONB DEFAULT '{}',         -- snapshot of completed phases

    -- Configuration overrides
    config JSONB DEFAULT '{}',                  -- per-project config overrides

    -- Metadata
    metadata JSONB DEFAULT '{}'                 -- flexible metadata storage
);

CREATE INDEX idx_projects_user ON cineos_core.projects(user_id);
CREATE INDEX idx_projects_state ON cineos_core.projects(current_state);
CREATE INDEX idx_projects_updated ON cineos_core.projects(updated_at);
CREATE INDEX idx_projects_priority ON cineos_core.projects(priority, created_at);
```

### 5.3 Core Schema — Novels

```sql
CREATE TABLE cineos_core.novels (
    novel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    author TEXT,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    char_count INTEGER NOT NULL,
    encoding VARCHAR(50) NOT NULL,
    language VARCHAR(20) NOT NULL,
    source_type VARCHAR(20) DEFAULT 'telegram', -- 'telegram', 'file', 'paste'
    file_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id)
);

CREATE INDEX idx_novels_project ON cineos_core.novels(project_id);
```

### 5.4 Core Schema — Chapters

```sql
CREATE TABLE cineos_core.chapters (
    chapter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    novel_id UUID NOT NULL REFERENCES cineos_core.novels(novel_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    title TEXT,
    summary TEXT,
    text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    scene_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(novel_id, chapter_number)
);

CREATE INDEX idx_chapters_novel ON cineos_core.chapters(novel_id);
CREATE INDEX idx_chapters_project ON cineos_core.chapters(project_id);
```

### 5.5 Core Schema — Scenes

```sql
CREATE TABLE cineos_core.scenes (
    scene_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    chapter_id UUID NOT NULL REFERENCES cineos_core.chapters(chapter_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    state scene_state NOT NULL DEFAULT 'pending',

    -- Content
    full_text TEXT NOT NULL,
    summary TEXT,
    beginning_text TEXT,
    ending_text TEXT,

    -- Extraction results
    location_id UUID,                          -- FK added after locations table
    location_name TEXT,
    location_type VARCHAR(50),                 -- 'indoor', 'outdoor', 'mixed', 'abstract'
    time_of_day TEXT,
    weather TEXT,
    season TEXT,

    -- Emotion
    primary_emotion VARCHAR(50),
    secondary_emotions TEXT[],
    emotional_intensity FLOAT,                 -- 0.0 to 1.0
    emotional_arc TEXT,                         -- 'ascending', 'descending', 'stable', 'volatile'

    -- Conflict
    conflict_type VARCHAR(50),                 -- 'internal', 'interpersonal', 'external', 'societal', 'none'
    conflict_description TEXT,
    conflict_intensity FLOAT,                  -- 0.0 to 1.0

    -- Importance and pacing
    importance VARCHAR(20) DEFAULT 'normal',   -- 'critical', 'high', 'normal', 'low'
    pacing VARCHAR(20) DEFAULT 'normal',       -- 'fast', 'normal', 'slow'
    estimated_duration_seconds FLOAT,

    -- Dialogue
    has_dialogue BOOLEAN DEFAULT FALSE,
    dialogue_count INTEGER DEFAULT 0,
    dialogue_lines JSONB,                      -- [{speaker, text, emotion}]

    -- Action
    has_action BOOLEAN DEFAULT FALSE,
    action_intensity VARCHAR(20),              -- 'none', 'low', 'medium', 'high', 'extreme'
    action_type VARCHAR(50),                   -- 'combat', 'chase', 'escape', 'battle', 'none'
    combat_present BOOLEAN DEFAULT FALSE,

    -- Visual
    visual_priority FLOAT DEFAULT 0.5,         -- 0.0 to 1.0, how visually important
    visual_highlights TEXT[],                   -- notable visual elements from text
    hero_moment BOOLEAN DEFAULT FALSE,         -- is this a "hero shot" scene

    -- Transitions
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',

    -- Shot plan
    shot_count INTEGER DEFAULT 0,
    total_planned_duration_seconds FLOAT,

    -- Quality
    quality_score FLOAT,
    quality_issues JSONB,

    -- Music
    music_profile JSONB,                       -- {genre, tempo, intensity, mood}
    music_params JSONB,                        -- {volume, crossfade, ducking}

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, chapter_number, scene_number)
);

CREATE INDEX idx_scenes_project ON cineos_core.scenes(project_id);
CREATE INDEX idx_scenes_chapter ON cineos_core.scenes(chapter_id);
CREATE INDEX idx_scenes_state ON cineos_core.scenes(state);
CREATE INDEX idx_scenes_importance ON cineos_core.scenes(importance);
CREATE INDEX idx_scenes_emotion ON cineos_core.scenes(primary_emotion);
```

### 5.6 Core Schema — Shots

```sql
CREATE TABLE cineos_core.shots (
    shot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID NOT NULL REFERENCES cineos_core.scenes(scene_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    shot_number INTEGER NOT NULL,
    state shot_state NOT NULL DEFAULT 'pending',

    -- Shot classification
    shot_type VARCHAR(50) NOT NULL,            -- 'establishing', 'wide', 'medium', 'close_up', 'extreme_close_up', 'action', 'insert'
    importance VARCHAR(20) DEFAULT 'normal',

    -- Timing
    duration_seconds FLOAT NOT NULL,

    -- Camera
    camera_angle VARCHAR(50),                  -- 'eye_level', 'low_angle', 'high_angle', 'dutch_angle', 'bird_eye', 'worm_eye'
    camera_movement VARCHAR(50),               -- 'static', 'pan_left', 'pan_right', 'tilt_up', 'tilt_down', 'zoom_in', 'zoom_out', 'tracking', 'dolly'
    depth_of_field VARCHAR(20),                -- 'shallow', 'medium', 'deep'
    lens VARCHAR(50),                          -- 'wide', 'normal', 'telephoto', 'macro'

    -- Lighting
    lighting_style VARCHAR(50),                -- 'natural', 'dramatic', 'soft', 'harsh', 'backlit', 'silhouette', 'neon'
    lighting_direction VARCHAR(50),            -- 'front', 'side', 'back', 'top', 'bottom'
    lighting_color VARCHAR(50),                -- 'warm', 'cool', 'neutral', 'colored'

    -- Composition
    composition VARCHAR(50),                   -- 'rule_of_thirds', 'centered', 'golden_ratio', 'leading_lines', 'frame_within_frame'
    focal_point VARCHAR(100),                  -- what the viewer should focus on

    -- Animation
    animation_type VARCHAR(50),                -- 'ken_burns_zoom_in', 'ken_burns_zoom_out', 'ken_burns_pan_left', 'ken_burns_pan_right', 'parallax_depth', 'subtle_breathing', 'subtle_floating', 'none'
    animation_params JSONB,                    -- {zoom_factor, pan_speed, focal_x, focal_y, easing}
    animation_intensity FLOAT,                 -- 0.0 to 1.0

    -- Transition
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',
    transition_duration_ms INTEGER DEFAULT 500,

    -- Characters
    characters_in_shot UUID[],                 -- array of character_ids
    character_positions JSONB,                 -- {character_id: {position: 'left/center/right', visibility: 'full/partial'}}

    -- Prompt
    positive_prompt TEXT,
    negative_prompt TEXT,
    prompt_version INTEGER DEFAULT 1,

    -- Narration
    narration_text TEXT,
    narration_voice VARCHAR(100),
    narration_emotion VARCHAR(50),
    narration_speed FLOAT DEFAULT 1.0,

    -- Quality
    quality_score FLOAT,

    -- Music
    music_cue TEXT,                            -- specific music instruction for this shot
    music_volume FLOAT DEFAULT 0.2,            -- background music volume (0.0 to 1.0)

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(scene_id, shot_number)
);

CREATE INDEX idx_shots_scene ON cineos_core.shots(scene_id);
CREATE INDEX idx_shots_project ON cineos_core.shots(project_id);
CREATE INDEX idx_shots_state ON cineos_core.shots(state);
CREATE INDEX idx_shots_type ON cineos_core.shots(shot_type);
```

### 5.7 Core Schema — Characters

```sql
CREATE TABLE cineos_core.characters (
    character_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state scene_state NOT NULL DEFAULT 'pending',  -- reuse scene_state for character lifecycle

    -- Identity
    canonical_name TEXT NOT NULL,
    alternative_names TEXT[],
    nicknames TEXT[],
    titles TEXT[],
    role VARCHAR(50),                          -- 'protagonist', 'antagonist', 'supporting', 'minor', 'mentioned'

    -- Physical (immutable once locked)
    gender TEXT,
    estimated_age TEXT,
    ethnicity TEXT,
    body_type TEXT,
    height TEXT,
    build TEXT,

    -- Face (immutable once locked)
    face_shape TEXT,
    jaw_shape TEXT,
    nose_shape TEXT,
    eye_shape TEXT,
    eye_color TEXT,
    eye_expression TEXT,
    eyebrow_shape TEXT,
    lip_shape TEXT,

    -- Hair (immutable once locked)
    hair_style TEXT,
    hair_length TEXT,
    hair_color TEXT,
    hair_texture TEXT,

    -- Skin (immutable once locked)
    skin_tone TEXT,
    skin_texture TEXT,

    -- Body Markings
    scars TEXT[],
    tattoos TEXT[],
    birthmarks TEXT[],
    freckles BOOLEAN DEFAULT FALSE,

    -- Clothing
    default_outfit TEXT,
    formal_outfit TEXT,
    combat_outfit TEXT,
    sleep_outfit TEXT,
    distinctive_accessories TEXT[],

    -- Equipment
    primary_weapon TEXT,
    secondary_weapon TEXT,
    magical_arts TEXT[],
    tools TEXT[],

    -- Personality
    personality_traits TEXT[],
    core_values TEXT[],
    fears TEXT[],
    desires TEXT[],
    habits TEXT[],
    speech_patterns TEXT,
    verbal_tics TEXT[],

    -- Voice
    voice_description TEXT,
    voice_pitch TEXT,
    voice_pace TEXT,
    voice_accent TEXT,
    voice_parameters JSONB,                    -- {speed: 1.0, pitch: 0.0, volume: 1.0}

    -- Relationships
    relationships JSONB,                       -- {character_id: {type, description, evidence}}

    -- Evidence
    evidence_sources TEXT[],
    inferred_traits TEXT[],
    confidence_score FLOAT DEFAULT 0.0,

    -- Visual Prompt Components
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,

    -- Reference Images
    primary_reference_id UUID,                 -- FK to character_references
    expression_sheet_id UUID,                  -- FK to character_references

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    lock_reason TEXT,

    -- Scene tracking
    total_scene_count INTEGER DEFAULT 0,
    first_appearance_scene_id UUID,
    last_appearance_scene_id UUID,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, canonical_name)
);

CREATE INDEX idx_characters_project ON cineos_core.characters(project_id);
CREATE INDEX idx_characters_state ON cineos_core.characters(state);
CREATE INDEX idx_characters_name ON cineos_core.characters(canonical_name);
CREATE INDEX idx_characters_role ON cineos_core.characters(role);
```

### 5.8 Core Schema — Locations

```sql
CREATE TABLE cineos_core.locations (
    location_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,

    -- Identity
    name TEXT NOT NULL,
    aliases TEXT[],
    location_type VARCHAR(50),                 -- 'indoor', 'outdoor', 'mixed', 'abstract', 'transport'

    -- Description
    description TEXT,
    detailed_description TEXT,
    atmosphere TEXT,
    mood TEXT,

    -- Physical properties
    size VARCHAR(50),                          -- 'tiny', 'small', 'medium', 'large', 'vast'
    materials TEXT[],                          -- 'stone', 'wood', 'metal', 'glass', 'organic'
    features TEXT[],                           -- notable features
    hazards TEXT[],                            -- dangerous elements

    -- Visual
    architecture_style TEXT,
    lighting_default VARCHAR(50),
    color_palette TEXT[],
    visual_atmosphere TEXT,
    visual_keywords TEXT[],

    -- Environment
    weather_default TEXT,
    temperature_range TEXT,
    time_of_day_variants JSONB,               -- {dawn: 'description', noon: 'description', ...}

    -- Visual References
    reference_image_id UUID,                   -- FK to world_references
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,

    -- Usage tracking
    scene_count INTEGER DEFAULT 0,
    scene_ids UUID[],

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, name)
);

-- Add FK from scenes to locations
ALTER TABLE cineos_core.scenes ADD CONSTRAINT fk_scenes_location
    FOREIGN KEY (location_id) REFERENCES cineos_core.locations(location_id);

CREATE INDEX idx_locations_project ON cineos_core.locations(project_id);
CREATE INDEX idx_locations_type ON cineos_core.locations(location_type);
```

### 5.9 Core Schema — Scene-Character Junction

```sql
CREATE TABLE cineos_core.scene_characters (
    scene_id UUID NOT NULL REFERENCES cineos_core.scenes(scene_id) ON DELETE CASCADE,
    character_id UUID NOT NULL REFERENCES cineos_core.characters(character_id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'present',        -- 'protagonist', 'antagonist', 'present', 'mentioned', 'flashback'
    emotional_state TEXT,
    dialogue_lines JSONB,                      -- [{text, emotion}]
    screen_time_seconds FLOAT,
    PRIMARY KEY (scene_id, character_id)
);

CREATE INDEX idx_scene_characters_scene ON cineos_core.scene_characters(scene_id);
CREATE INDEX idx_scene_characters_character ON cineos_core.scene_characters(character_id);
```

### 5.10 Memory Schema — Bibles

```sql
-- Story Bible
CREATE TABLE cineos_memory.story_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,

    -- Core Narrative
    title TEXT NOT NULL,
    genre TEXT,
    subgenre TEXT,
    theme TEXT,
    themes TEXT[],
    central_conflict TEXT,
    resolution TEXT,
    narrative_arc TEXT,
    point_of_view TEXT,
    tense TEXT,
    tone TEXT,
    pacing TEXT,

    -- Structure
    total_chapters INTEGER,
    total_scenes INTEGER,
    estimated_duration_minutes FLOAT,

    -- Deep Analysis
    symbols TEXT[],
    motifs TEXT[],
    foreshadowing JSONB,
    character_arcs JSONB,
    world_state_changes JSONB,

    -- Visual Translation
    visual_style TEXT,
    color_grading TEXT,
    lighting_mood TEXT,
    camera_style TEXT,

    -- Consistency
    contradictions JSONB,
    plot_holes JSONB,
    timeline_conflicts JSONB,

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    confidence_score FLOAT DEFAULT 0.0,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);

-- Character Bible
CREATE TABLE cineos_memory.character_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    character_id UUID NOT NULL REFERENCES cineos_core.characters(character_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,

    -- All character fields (mirrors characters table but as immutable bible)
    canonical_name TEXT NOT NULL,
    full_description TEXT,
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    reference_data JSONB,                      -- complete character data snapshot

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, character_id, version)
);

-- World Bible
CREATE TABLE cineos_memory.world_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,

    world_name TEXT,
    world_size TEXT,
    continents TEXT[],
    regions TEXT[],
    notable_landmarks TEXT[],
    geography_description TEXT,
    climate_zones TEXT,
    weather_patterns TEXT,
    era_name TEXT,
    historical_eras JSONB,
    architectural_style TEXT,
    building_materials TEXT[],
    notable_structures TEXT[],
    technology_level TEXT,
    technology_details TEXT,
    magic_system TEXT,
    magic_rules TEXT[],
    political_system TEXT,
    social_hierarchy TEXT,
    economic_system TEXT,
    religious_system TEXT,
    cultural_values TEXT[],
    color_palette TEXT[],
    lighting_style TEXT,
    visual_atmosphere TEXT,
    visual_keywords TEXT[],
    material_aesthetics TEXT,
    notable_animals TEXT[],
    dangerous_creatures TEXT[],
    mythical_species TEXT[],

    -- Visual Prompt Components
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    reference_images JSONB,

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    confidence_score FLOAT DEFAULT 0.0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);

-- Timeline Bible
CREATE TABLE cineos_memory.timeline_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,

    events JSONB NOT NULL,                     -- [{id, scene_id, chapter_number, sequence_number, time_reference, absolute_order, duration_estimate, characters_present, location, cause, effect}]
    total_events INTEGER,
    time_span TEXT,
    has_flashbacks BOOLEAN DEFAULT FALSE,
    has_parallel_timelines BOOLEAN DEFAULT FALSE,
    timeline_type TEXT,                        -- 'linear', 'nonlinear', 'parallel'
    contradictions JSONB,
    paradoxes JSONB,

    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);

-- Style Bible
CREATE TABLE cineos_memory.style_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,

    art_style TEXT,
    rendering_style TEXT,
    line_weight TEXT,
    shading_style TEXT,
    primary_palette TEXT[],
    secondary_palette TEXT[],
    accent_colors TEXT[],
    color_temperature TEXT,
    saturation_level TEXT,
    default_lighting TEXT,
    dramatic_lighting TEXT,
    soft_lighting TEXT,
    night_lighting TEXT,
    indoor_lighting TEXT,
    rule_of_thirds BOOLEAN DEFAULT TRUE,
    depth_of_field TEXT,
    camera_angles_preferred TEXT[],
    shot_types_distribution JSONB,
    character_detail_level TEXT,
    facial_expressions_style TEXT,
    body_proportions TEXT,
    background_detail_level TEXT,
    background_blur_style TEXT,
    environment_mood TEXT,
    preferred_transitions TEXT[],
    transition_style TEXT,
    font_style TEXT,
    subtitle_style TEXT,
    base_positive_prompt TEXT,
    base_negative_prompt TEXT,
    quality_tags TEXT,

    reference_style_images JSONB,

    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);
```

### 5.11 Memory Schema — Reference Images

```sql
CREATE TABLE cineos_memory.character_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES cineos_core.characters(character_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    reference_type VARCHAR(50) NOT NULL,       -- 'portrait', 'full_body', 'expression_sheet', 'outfit_front', 'outfit_back', 'weapon', 'pose'
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    prompt_used TEXT,
    backend_used VARCHAR(100),
    seed INTEGER,
    quality_score FLOAT,
    is_primary BOOLEAN DEFAULT FALSE,
    is_locked BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cineos_memory.world_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID REFERENCES cineos_core.locations(location_id) ON DELETE SET NULL,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    reference_type VARCHAR(50) NOT NULL,       -- 'landscape', 'building_exterior', 'building_interior', 'map', 'detail'
    location_name TEXT,
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    prompt_used TEXT,
    backend_used VARCHAR(100),
    quality_score FLOAT,
    is_primary BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cineos_memory.style_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    reference_type VARCHAR(50) NOT NULL,       -- 'color_palette', 'mood', 'lighting', 'composition', 'texture'
    description TEXT,
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.12 Generation Schema — Assets

```sql
-- Generated Images
CREATE TABLE cineos_gen.images (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',
    variant_number INTEGER NOT NULL DEFAULT 1,

    -- File
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    file_size_bytes BIGINT,
    width INTEGER,
    height INTEGER,
    format VARCHAR(10),                        -- 'png', 'jpg', 'webp'

    -- Generation Parameters
    prompt_used TEXT NOT NULL,
    negative_prompt_used TEXT,
    backend_used VARCHAR(100),
    model_used VARCHAR(200),
    seed INTEGER,
    steps INTEGER,
    cfg_scale FLOAT,
    sampler VARCHAR(50),

    -- Quality Scores
    quality_score FLOAT,
    technical_quality_score FLOAT,
    prompt_alignment_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    composition_score FLOAT,

    -- Selection
    is_selected BOOLEAN DEFAULT FALSE,
    selection_reason TEXT,

    -- Source
    generated_locally BOOLEAN DEFAULT TRUE,
    worker_id UUID,
    job_id UUID,
    generation_time_ms INTEGER,

    -- Super Resolution
    is_upscaled BOOLEAN DEFAULT FALSE,
    original_image_id UUID,                    -- FK to self (before upscaling)
    upscale_factor FLOAT,
    upscale_model VARCHAR(100),

    -- State tracking
    state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    rejection_reason TEXT,
    repair_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(shot_id, variant_number)
);

-- Generated Audio (Narration)
CREATE TABLE cineos_gen.audio (
    audio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',

    -- File
    audio_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    format VARCHAR(10),                        -- 'wav', 'mp3', 'ogg'

    -- Generation Parameters
    text_used TEXT NOT NULL,
    voice_used VARCHAR(100),
    emotion VARCHAR(50),
    speed FLOAT DEFAULT 1.0,
    pitch FLOAT DEFAULT 0.0,
    volume FLOAT DEFAULT 1.0,

    -- Quality
    duration_seconds FLOAT,
    sample_rate INTEGER,
    bit_depth INTEGER,
    channels INTEGER,
    quality_score FLOAT,
    naturalness_score FLOAT,
    emotion_match_score FLOAT,
    duration_fit_score FLOAT,

    -- Selection
    is_selected BOOLEAN DEFAULT FALSE,

    -- Source
    backend_used VARCHAR(100),
    worker_id UUID,
    job_id UUID,
    generation_time_ms INTEGER,

    -- State tracking
    state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    repair_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Video Clips (individual shot videos)
CREATE TABLE cineos_gen.video_clips (
    clip_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',

    -- Source references
    image_id UUID REFERENCES cineos_gen.images(image_id),
    audio_id UUID REFERENCES cineos_gen.audio(audio_id),

    -- Output
    clip_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    duration_seconds FLOAT,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    codec VARCHAR(50),
    bitrate INTEGER,

    -- Animation
    animation_applied VARCHAR(50),
    animation_params JSONB,

    -- Transition
    transition_in VARCHAR(50),
    transition_out VARCHAR(50),
    transition_duration_ms INTEGER,

    -- Quality
    quality_score FLOAT,
    audio_video_sync_score FLOAT,

    -- Source
    worker_id UUID,
    job_id UUID,
    render_time_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Final Videos
CREATE TABLE cineos_gen.final_videos (
    video_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',

    -- Output
    video_path TEXT NOT NULL,
    thumbnail_path TEXT,
    file_size_bytes BIGINT,
    duration_seconds FLOAT,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    codec VARCHAR(50),
    audio_codec VARCHAR(50),
    bitrate INTEGER,
    format VARCHAR(10),                        -- 'mp4', 'webm'

    -- Quality Scores
    overall_quality_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    narrative_fidelity_score FLOAT,
    audio_video_sync_score FLOAT,
    production_quality_score FLOAT,

    -- Counts
    total_scenes INTEGER,
    total_shots INTEGER,
    total_clips INTEGER,

    -- Render
    render_time_ms INTEGER,
    render_settings JSONB,

    -- State tracking
    state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    rejection_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.13 Generation Schema — Prompt Versions

```sql
CREATE TABLE cineos_gen.prompt_versions (
    prompt_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,

    -- Prompt Content
    positive_prompt TEXT NOT NULL,
    negative_prompt TEXT NOT NULL,

    -- Source Components
    character_prompts JSONB,                  -- {character_id: prompt_fragment}
    world_prompt TEXT,
    style_prompt TEXT,
    quality_tags TEXT,
    shot_specific_prompt TEXT,

    -- Context
    shot_type VARCHAR(50),
    camera_angle VARCHAR(50),
    scene_emotion VARCHAR(50),

    -- Quality tracking
    quality_score FLOAT,                      -- score achieved with this prompt
    review_id UUID,                           -- FK to quality_reviews

    -- Generation
    backend_used VARCHAR(100),
    model_used VARCHAR(200),
    generation_time_ms INTEGER,

    -- Selection
    is_current BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(shot_id, version_number)
);

CREATE INDEX idx_prompt_versions_shot ON cineos_gen.prompt_versions(shot_id);
CREATE INDEX idx_prompt_versions_project ON cineos_gen.prompt_versions(project_id);
CREATE INDEX idx_prompt_versions_current ON cineos_gen.prompt_versions(is_current) WHERE is_current = TRUE;
```

### 5.14 Quality Schema

```sql
-- Quality Reviews
CREATE TABLE cineos_quality.reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,          -- 'image', 'audio', 'shot', 'scene', 'project', 'video_clip', 'final_video'
    entity_id UUID NOT NULL,
    review_type VARCHAR(50) NOT NULL,          -- 'automatic', 'manual', 'repair_check', 'final_review'

    -- Scores (0.0 to 1.0)
    overall_score FLOAT,
    technical_quality_score FLOAT,
    prompt_alignment_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    composition_score FLOAT,
    audio_quality_score FLOAT,
    naturalness_score FLOAT,
    emotion_match_score FLOAT,
    duration_fit_score FLOAT,
    audio_video_sync_score FLOAT,
    narrative_fidelity_score FLOAT,

    -- Decision
    passed BOOLEAN NOT NULL,
    decision VARCHAR(50) NOT NULL,             -- 'pass', 'fail_repairable', 'fail_unrecoverable'

    -- Details
    issues JSONB,                              -- [{severity, category, description, field, suggestion}]
    recommendations JSONB,                     -- [{action, target, reason, priority}]

    -- Reviewer
    reviewer_model VARCHAR(100),
    reviewer_version VARCHAR(50),
    reviewer_type VARCHAR(50),                 -- 'llm', 'clip', 'insightface', 'regex', 'manual'

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_project ON cineos_quality.reviews(project_id);
CREATE INDEX idx_reviews_entity ON cineos_quality.reviews(entity_type, entity_id);
CREATE INDEX idx_reviews_passed ON cineos_quality.reviews(passed);
CREATE INDEX idx_reviews_created ON cineos_quality.reviews(created_at);

-- Quality Thresholds (per-project, tunable)
CREATE TABLE cineos_quality.thresholds (
    threshold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,

    -- Image thresholds
    min_image_quality FLOAT DEFAULT 0.60,
    min_character_consistency FLOAT DEFAULT 0.70,
    min_world_consistency FLOAT DEFAULT 0.60,
    min_composition FLOAT DEFAULT 0.50,
    min_prompt_alignment FLOAT DEFAULT 0.60,

    -- Audio thresholds
    min_audio_quality FLOAT DEFAULT 0.50,
    min_naturalness FLOAT DEFAULT 0.50,
    min_emotion_match FLOAT DEFAULT 0.40,
    min_duration_fit FLOAT DEFAULT 0.60,

    -- Video thresholds
    min_video_quality FLOAT DEFAULT 0.60,
    min_audio_video_sync FLOAT DEFAULT 0.70,
    min_overall_quality FLOAT DEFAULT 0.60,

    -- Repair thresholds
    max_repair_attempts INTEGER DEFAULT 3,
    repair_escalation_threshold FLOAT DEFAULT 0.30,

    -- Global
    hard_failure_threshold FLOAT DEFAULT 0.20,
    auto_approve_threshold FLOAT DEFAULT 0.85,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id)
);

-- Repair History
CREATE TABLE cineos_quality.repairs (
    repair_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    review_id UUID NOT NULL REFERENCES cineos_quality.reviews(review_id),

    -- What failed
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    failure_reason TEXT,
    failure_score FLOAT,
    failure_issues JSONB,

    -- Repair action
    repair_strategy VARCHAR(100) NOT NULL,     -- 'regenerate_prompt', 'regenerate_image', 'adjust_prompt', 'change_backend', 'switch_voice', 'adjust_camera'
    repair_description TEXT,
    repair_attempt_number INTEGER NOT NULL,
    max_repair_attempts INTEGER DEFAULT 3,

    -- New asset created
    new_entity_type VARCHAR(50),
    new_entity_id UUID,
    new_review_id UUID,

    -- Result
    pre_repair_score FLOAT,
    post_repair_score FLOAT,
    improvement FLOAT,
    success BOOLEAN,
    failure_reason_repair TEXT,                -- why repair failed (if applicable)

    -- Worker
    worker_id UUID,
    job_id UUID,
    repair_time_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_repairs_project ON cineos_quality.repairs(project_id);
CREATE INDEX idx_repairs_entity ON cineos_quality.repairs(entity_type, entity_id);
CREATE INDEX idx_repairs_success ON cineos_quality.repairs(success);
```

### 5.15 Execution Schema — Workers and Jobs

```sql
-- Worker Registry
CREATE TABLE cineos_exec.workers (
    worker_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name VARCHAR(200) NOT NULL,
    worker_type VARCHAR(50) NOT NULL,          -- 'gpu_image', 'cpu_tts', 'cpu_render', 'vision_review', 'super_resolution', 'local_all'
    state worker_state NOT NULL DEFAULT 'registering',

    -- Connection
    host VARCHAR(200),
    port INTEGER,
    protocol VARCHAR(20) DEFAULT 'http',
    endpoint_url TEXT,
    auth_token VARCHAR(500),

    -- Capabilities
    supported_backends TEXT[],
    supported_task_types TEXT[],

    -- Hardware
    gpu_model TEXT,
    gpu_vram_gb FLOAT,
    gpu_driver_version TEXT,
    cpu_cores INTEGER,
    cpu_model TEXT,
    ram_gb FLOAT,
    storage_gb FLOAT,
    os VARCHAR(100),

    -- Status
    last_heartbeat TIMESTAMPTZ,
    heartbeat_interval_ms INTEGER DEFAULT 30000,
    current_task_id UUID,
    current_load FLOAT DEFAULT 0.0,            -- 0.0 to 1.0

    -- Limits
    max_concurrent_tasks INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 5,
    enabled BOOLEAN DEFAULT TRUE,

    -- Metrics
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    total_tasks_timeout INTEGER DEFAULT 0,
    avg_task_duration_ms FLOAT,
    success_rate FLOAT DEFAULT 1.0,
    last_task_completed_at TIMESTAMPTZ,

    -- Health
    health_status VARCHAR(50) DEFAULT 'unknown', -- 'healthy', 'degraded', 'unhealthy', 'unknown'
    health_check_url TEXT,
    health_check_interval_ms INTEGER DEFAULT 60000,
    last_health_check TIMESTAMPTZ,

    -- Resource usage
    gpu_memory_used_mb FLOAT,
    gpu_memory_total_mb FLOAT,
    cpu_usage_percent FLOAT,
    ram_usage_percent FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workers_type ON cineos_exec.workers(worker_type);
CREATE INDEX idx_workers_state ON cineos_exec.workers(state);
CREATE INDEX idx_workers_enabled ON cineos_exec.workers(enabled);

-- Job Queue
CREATE TABLE cineos_exec.jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL,            -- 'generate_image', 'generate_audio', 'render_clip', 'review_quality', 'super_resolution'
    state job_state NOT NULL DEFAULT 'pending',

    -- Assignment
    worker_id UUID REFERENCES cineos_exec.workers(worker_id),
    priority INTEGER DEFAULT 5,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Payload
    payload JSONB NOT NULL,
    result JSONB,

    -- Timing
    queued_at TIMESTAMPTZ,
    assigned_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    timeout_ms INTEGER DEFAULT 300000,

    -- Error
    error_message TEXT,
    error_code VARCHAR(50),
    error_traceback TEXT,
    is_recoverable BOOLEAN DEFAULT TRUE,

    -- Dependencies
    depends_on UUID[],                         -- other job_ids that must complete first
    parent_job_id UUID,                        -- parent job if this is a sub-job

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_state ON cineos_exec.jobs(state);
CREATE INDEX idx_jobs_type ON cineos_exec.jobs(job_type);
CREATE INDEX idx_jobs_worker ON cineos_exec.jobs(worker_id);
CREATE INDEX idx_jobs_project ON cineos_exec.jobs(project_id);
CREATE INDEX idx_jobs_priority ON cineos_exec.jobs(priority, created_at);

-- Workflow Executions
CREATE TABLE cineos_exec.workflow_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    workflow_name VARCHAR(200) NOT NULL,
    n8n_execution_id VARCHAR(100),

    state VARCHAR(50) NOT NULL DEFAULT 'pending',
    trigger_data JSONB,
    result_data JSONB,
    error_data JSONB,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    attempt_number INTEGER DEFAULT 1,
    max_attempts INTEGER DEFAULT 3,
    parent_execution_id UUID,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workflow_executions_project ON cineos_exec.workflow_executions(project_id);
CREATE INDEX idx_workflow_executions_workflow ON cineos_exec.workflow_executions(workflow_name);
CREATE INDEX idx_workflow_executions_state ON cineos_exec.workflow_executions(state);
```

### 5.16 Audit Schema — Learning

```sql
-- Learning Data
CREATE TABLE cineos_audit.learning_records (
    learning_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,

    -- Pre-project estimates
    estimated_scenes INTEGER,
    estimated_shots INTEGER,
    estimated_duration_minutes FLOAT,

    -- Actuals
    actual_scenes INTEGER,
    actual_shots INTEGER,
    actual_duration_minutes FLOAT,

    -- Performance
    total_processing_time_ms BIGINT,
    total_generation_time_ms BIGINT,
    total_review_time_ms BIGINT,
    total_repair_time_ms BIGINT,
    total_assembly_time_ms BIGINT,

    -- Quality
    first_pass_quality_score FLOAT,
    final_quality_score FLOAT,
    repair_success_rate FLOAT,
    average_repair_attempts FLOAT,

    -- Backend Usage
    image_backends_used JSONB,                 -- {backend: count}
    audio_backends_used JSONB,
    render_backends_used JSONB,
    primary_image_backend VARCHAR(100),
    primary_audio_backend VARCHAR(100),

    -- Prompt Performance
    avg_prompt_alignment_score FLOAT,
    worst_prompt_alignment_score FLOAT,
    best_performing_shot_types JSONB,
    worst_performing_shot_types JSONB,

    -- Lessons
    lessons JSONB,                             -- [{category, lesson, impact, evidence}]
    recommendations JSONB,                     -- [{action, reason, priority, expected_impact}]

    -- Metrics
    cost_estimate_usd FLOAT,                   -- estimated compute cost
    efficiency_score FLOAT,                    -- quality per minute of processing

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_learning_project ON cineos_audit.learning_records(project_id);

-- Execution Log (detailed per-workflow execution tracking)
CREATE TABLE cineos_audit.execution_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    workflow_name VARCHAR(200) NOT NULL,
    execution_id UUID,                         -- FK to workflow_executions
    node_name VARCHAR(200),
    node_type VARCHAR(100),

    state VARCHAR(50),                         -- 'started', 'completed', 'failed'
    input_data JSONB,
    output_data JSONB,
    error_data JSONB,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_execution_log_project ON cineos_audit.execution_log(project_id);
CREATE INDEX idx_execution_log_workflow ON cineos_audit.execution_log(workflow_name);
```

### 5.17 Config Schema

```sql
-- System Configuration
CREATE TABLE cineos_config.system_config (
    config_key VARCHAR(200) PRIMARY KEY,
    config_value JSONB NOT NULL,
    description TEXT,
    category VARCHAR(100),
    data_type VARCHAR(50),                     -- 'string', 'number', 'boolean', 'array', 'object'
    min_value FLOAT,                           -- for numeric configs
    max_value FLOAT,                           -- for numeric configs
    allowed_values JSONB,                      -- for enum configs
    is_sensitive BOOLEAN DEFAULT FALSE,        -- hide from logs
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(200)
);

-- Default Configuration Values
INSERT INTO cineos_config.system_config (config_key, config_value, description, category, data_type) VALUES
-- Quality
('quality.min_image_quality', '0.60', 'Minimum image quality score to pass review', 'quality', 'number'),
('quality.min_character_consistency', '0.70', 'Minimum character consistency score', 'quality', 'number'),
('quality.min_world_consistency', '0.60', 'Minimum world consistency score', 'quality', 'number'),
('quality.min_composition', '0.50', 'Minimum composition score', 'quality', 'number'),
('quality.min_prompt_alignment', '0.60', 'Minimum prompt alignment score', 'quality', 'number'),
('quality.min_audio_quality', '0.50', 'Minimum audio quality score', 'quality', 'number'),
('quality.min_naturalness', '0.50', 'Minimum TTS naturalness score', 'quality', 'number'),
('quality.min_emotion_match', '0.40', 'Minimum emotion match score', 'quality', 'number'),
('quality.min_duration_fit', '0.60', 'Minimum audio-video duration fit', 'quality', 'number'),
('quality.min_video_quality', '0.60', 'Minimum video clip quality', 'quality', 'number'),
('quality.min_audio_video_sync', '0.70', 'Minimum audio-video sync score', 'quality', 'number'),
('quality.min_overall_quality', '0.60', 'Minimum overall project quality', 'quality', 'number'),
('quality.max_repair_attempts', '3', 'Maximum repair attempts per item', 'quality', 'number'),
('quality.repair_escalation_threshold', '0.30', 'Score below which repair is escalated', 'quality', 'number'),
('quality.hard_failure_threshold', '0.20', 'Score below which item is rejected', 'quality', 'number'),
('quality.auto_approve_threshold', '0.85', 'Score above which auto-approve', 'quality', 'number'),

-- Generation
('generation.default_image_backends', '["local_gpu","hf_inference","pollinations"]', 'Image backend priority order', 'generation', 'array'),
('generation.default_tts_backends', '["edge_tts","piper","espeak"]', 'TTS backend priority order', 'generation', 'array'),
('generation.candidates_per_shot', '2', 'Number of image variants per shot', 'generation', 'number'),
('generation.image_concurrency', '1', 'Concurrent image generation tasks', 'generation', 'number'),
('generation.audio_concurrency', '2', 'Concurrent audio generation tasks', 'generation', 'number'),
('generation.max_seed_retries', '3', 'Max retries with different seeds', 'generation', 'number'),

-- Video
('video.default_fps', '24', 'Default video frames per second', 'video', 'number'),
('video.default_resolution_width', '1920', 'Default video width', 'video', 'number'),
('video.default_resolution_height', '1080', 'Default video height', 'video', 'number'),
('video.default_codec', 'libx264', 'Default video codec', 'video', 'string'),
('video.default_audio_codec', 'aac', 'Default audio codec', 'video', 'string'),
('video.default_crf', '18', 'Default constant rate factor (lower = better)', 'video', 'number'),
('video.default_preset', 'medium', 'Default encoding preset', 'video', 'string'),
('video.max_telegram_file_size_mb', '50', 'Maximum file size for Telegram bot upload', 'video', 'number'),

-- Shot Planning
('planning.shots_per_scene_critical', '10', 'Target shots for critical scenes', 'planning', 'number'),
('planning.shots_per_scene_high', '7', 'Target shots for high importance scenes', 'planning', 'number'),
('planning.shots_per_scene_normal', '5', 'Target shots for normal scenes', 'planning', 'number'),
('planning.shots_per_scene_low', '3', 'Target shots for low importance scenes', 'planning', 'number'),
('planning.max_total_shots', '1000', 'Maximum total shots per project', 'planning', 'number'),
('planning.max_video_duration_seconds', '3600', 'Maximum video duration in seconds', 'planning', 'number'),
('planning.max_shot_duration_seconds', '30', 'Maximum single shot duration', 'planning', 'number'),
('planning.min_shot_duration_seconds', '3', 'Minimum single shot duration', 'planning', 'number'),

-- Limits
('limits.max_novel_words', '500000', 'Maximum novel word count', 'limits', 'number'),
('limits.max_scenes', '200', 'Maximum scenes per project', 'limits', 'number'),
('limits.max_project_duration_hours', '72', 'Maximum project processing time', 'limits', 'number'),
('limits.min_novel_words', '50', 'Minimum novel word count', 'limits', 'number'),

-- Telegram
('telegram.progress_update_interval_seconds', '30', 'Progress update throttle interval', 'telegram', 'number'),
('telegram.max_message_length', '4096', 'Maximum Telegram message length', 'telegram', 'number'),
('telegram.allowed_user_ids', '[]', 'Telegram user IDs allowed to use bot', 'telegram', 'array'),

-- Worker
('worker.heartbeat_timeout_seconds', '90', 'Seconds before worker declared offline', 'worker', 'number'),
('worker.health_check_interval_seconds', '60', 'Worker health check interval', 'worker', 'number'),
('worker.max_task_timeout_seconds', '300', 'Default maximum task timeout', 'worker', 'number'),
('worker.retry_backoff_base_ms', '1000', 'Base delay for exponential backoff', 'worker', 'number'),
('worker.retry_backoff_max_ms', '300000', 'Maximum backoff delay', 'worker', 'number');
```

---

## 6. VERSIONING SYSTEM

### 6.1 Universal Versioning Table

```sql
CREATE TABLE cineos_core.versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,          -- 'character_bible', 'world_bible', 'style_bible', 'prompt', 'image', 'project_config'
    entity_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,

    -- Parent
    parent_version_id UUID,                    -- FK to versions.version_id

    -- Data snapshot
    data_snapshot JSONB NOT NULL,              -- complete data at this version

    -- Metadata
    author VARCHAR(200) NOT NULL,              -- 'system', 'learning_engine', 'admin', workflow name
    change_reason TEXT NOT NULL,
    change_type VARCHAR(50) NOT NULL,          -- 'create', 'update', 'lock', 'unlock', 'revert', 'repair'

    -- State
    is_current BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(entity_type, entity_id, version_number)
);

CREATE INDEX idx_versions_entity ON cineos_core.versions(entity_type, entity_id);
CREATE INDEX idx_versions_project ON cineos_core.versions(project_id);
CREATE INDEX idx_versions_current ON cineos_core.versions(is_current) WHERE is_current = TRUE;
```

### 6.2 Versioning Rules

```
VERSIONING PROTOCOL:
────────────────────

1. EVERY versioned entity starts at version 1 on creation.

2. On ANY modification:
   a. Read current version
   b. Increment version_number
   c. Create new version record with updated data
   d. Mark old version as is_current = FALSE
   e. Mark new version as is_current = TRUE
   f. Store complete data_snapshot (not delta)

3. On LOCK:
   a. Current version gets is_locked = TRUE
   b. No further modifications allowed until UNLOCK
   c. Lock event recorded in state_log

4. On UNLOCK:
   a. Current version gets is_locked = FALSE
   b. New version created with same data (version_number + 1)
   c. New version is unlocked (is_locked = FALSE)
   d. Unlock event recorded in state_log

5. On REVERT:
   a. Target version identified
   b. New version created with target version's data_snapshot
   c. New version marked as is_current = TRUE
   d. All intermediate versions marked as is_current = FALSE
   e. Revert event recorded with reason

6. RETRIEVAL:
   a. Default query returns is_current = TRUE version
   b. Historical query returns specific version_number
   c. Locked entities always return locked version regardless of is_current

7. ENTITIES THAT SUPPORT VERSIONING:
   - character_bibles
   - world_bibles
   - style_bibles
   - story_bibles
   - timeline_bibles
   - prompt_versions
   - project config (config field in projects table)
```

---

## 7. RECOVERY SYSTEM

### 7.1 Recovery Protocol

```
RECOVERY PROCEDURE:
───────────────────

On system startup or crash recovery:

1. DATABASE CHECK
   a. Verify PostgreSQL connection
   b. Check for incomplete transactions (PostgreSQL handles via WAL)
   c. Verify no corrupted records

2. PROJECT STATE SCAN
   a. SELECT all projects WHERE current_state NOT IN ('completed', 'cancelled', 'failed')
   b. For each project:
      - Check if any jobs are in 'running' state (mark as 'failed' → requeue)
      - Check if any workflows are in progress (mark as 'failed' → requeue)
      - Check if project is in 'waiting' or 'paused' (leave as-is, wait for signal)
      - Check if project is in active state with no recent activity (mark as 'waiting')

3. JOB QUEUE CLEANUP
   a. SELECT all jobs WHERE state = 'running' AND worker_id IN (SELECT worker_id WHERE state = 'offline')
   b. Reset these jobs to 'pending' state
   c. Requeue for assignment to available workers

4. WORKER STATUS RESET
   a. Mark all workers as 'offline' (they will re-register via heartbeat)
   b. Clear all current_task_id references
   c. Reset current_load to 0

5. ORCHESTRATOR RESUME
   a. For each project in active state:
      - Determine what workflow should be running
      - Re-trigger the workflow via n8n webhook
      - Log recovery event

6. NOTIFICATION
   a. Send Telegram notification to admin: "System recovered. X projects resumed."
   b. Log recovery details in events table
```

### 7.2 Checkpoint System

```sql
CREATE TABLE cineos_core.checkpoints (
    checkpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state_at_checkpoint project_state NOT NULL,

    -- Completed phases
    completed_phases TEXT[],
    current_phase VARCHAR(100),

    -- Entity counts
    chapter_count INTEGER,
    scene_count INTEGER,
    shot_count INTEGER,
    character_count INTEGER,
    location_count INTEGER,

    -- Quality summary
    average_quality_score FLOAT,
    total_repairs INTEGER,

    -- Asset counts
    images_generated INTEGER,
    audio_generated INTEGER,
    clips_rendered INTEGER,

    -- Timing
    total_processing_time_ms BIGINT,
    phase_processing_times JSONB,              -- {phase: duration_ms}

    -- Recovery data
    pending_jobs UUID[],                       -- jobs that need to be re-dispatched
    failed_jobs UUID[],                        -- jobs that failed

    -- Full state snapshot
    state_snapshot JSONB,                      -- complete project state for recovery

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_checkpoints_project ON cineos_core.checkpoints(project_id);
CREATE INDEX idx_checkpoints_state ON cineos_core.checkpoints(state_at_checkpoint);

-- Checkpoint creation trigger
-- On every phase completion, create a checkpoint
```

### 7.3 Recovery Decision Matrix

```
┌──────────────────────────┬──────────────────────────────────────┬──────────────────────────┐
│ PROJECT STATE            │ RECOVERY ACTION                       │ CHECKPOINT USED          │
├──────────────────────────┼──────────────────────────────────────┼──────────────────────────┤
│ received                 │ Re-trigger telegram_intake            │ None (fresh start)       │
│ validated                │ Re-trigger validation                 │ None                     │
│ parsed                   │ Re-trigger chapter_extractor          │ None                     │
│ understood               │ Re-trigger scene_extractor            │ None                     │
│ biblified                │ Re-trigger bible_builders             │ None                     │
│ characterized            │ Re-trigger character_bible_builder    │ None                     │
│ worldbuilt               │ Re-trigger world_bible_builder        │ None                     │
│ timeline_verified        │ Re-trigger timeline_bible_builder     │ None                     │
│ planned                  │ Re-trigger shot_planner               │ None                     │
│ prompted                 │ Re-trigger prompt_generator           │ None                     │
│ queued                   │ Re-dispatch pending jobs               │ checkpoint               │
│ generating               │ Re-dispatch failed jobs, wait for running │ checkpoint          │
│ generated                │ Re-trigger quality_reviewer           │ checkpoint               │
│ reviewing                │ Re-trigger quality_reviewer           │ checkpoint               │
│ repairing                │ Re-trigger repair_dispatcher          │ checkpoint               │
│ approved                 │ Re-trigger voiced workflow            │ checkpoint               │
│ voiced                   │ Re-trigger musicked workflow          │ checkpoint               │
│ musicked                 │ Re-trigger animated workflow          │ checkpoint               │
│ animated                 │ Re-trigger video_renderer             │ checkpoint               │
│ rendering                │ Re-trigger video_renderer             │ checkpoint               │
│ rendered                 │ Re-trigger final_reviewer             │ checkpoint               │
│ super_resolution         │ Re-trigger super_resolution           │ checkpoint               │
│ final_review             │ Re-trigger final_reviewer             │ checkpoint               │
│ delivered                │ Re-trigger delivery_handler           │ checkpoint               │
│ learned                  │ Re-trigger learning_engine            │ checkpoint               │
│ waiting                  │ Wait for admin signal                  │ checkpoint               │
│ paused                   │ Wait for resume signal                 │ checkpoint               │
│ retrying                 │ Re-trigger previous workflow           │ checkpoint               │
│ failed                   │ Wait for admin intervention            │ checkpoint               │
│ manual_attention         │ Wait for admin intervention            │ checkpoint               │
│ cancelled                │ Terminal, no recovery                  │ None                     │
└──────────────────────────┴──────────────────────────────────────┴──────────────────────────┘
```

---

## 8. TRIGGERS AND AUTOMATION

### 8.1 Database Triggers

```sql
-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION cineos_core.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER trg_projects_updated
    BEFORE UPDATE ON cineos_core.projects
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_timestamp();

CREATE TRIGGER trg_scenes_updated
    BEFORE UPDATE ON cineos_core.scenes
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_timestamp();

CREATE TRIGGER trg_shots_updated
    BEFORE UPDATE ON cineos_core.shots
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_timestamp();

CREATE TRIGGER trg_characters_updated
    BEFORE UPDATE ON cineos_core.characters
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_timestamp();

CREATE TRIGGER trg_locations_updated
    BEFORE UPDATE ON cineos_core.locations
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_timestamp();

-- Auto-transition project state on scene completion
CREATE OR REPLACE FUNCTION cineos_core.check_all_scenes_completed()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.state = 'completed' THEN
        -- Check if ALL scenes in project are completed
        IF NOT EXISTS (
            SELECT 1 FROM cineos_core.scenes
            WHERE project_id = NEW.project_id
            AND state != 'completed'
        ) THEN
            -- All scenes completed, can proceed to assembly
            UPDATE cineos_core.projects
            SET current_state = 'rendering',
                last_state_change_at = NOW()
            WHERE project_id = NEW.project_id
            AND current_state = 'animated';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_scenes_check_completed
    AFTER UPDATE ON cineos_core.scenes
    FOR EACH ROW EXECUTE FUNCTION cineos_core.check_all_scenes_completed();

-- Auto-create checkpoint on phase completion
CREATE OR REPLACE FUNCTION cineos_core.create_checkpoint_on_phase()
RETURNS TRIGGER AS $$
BEGIN
    -- Only create checkpoint when state changes to a _complete state
    IF NEW.current_state IN (
        'parsed', 'understood', 'biblified', 'characterized',
        'worldbuilt', 'timeline_verified', 'planned', 'prompted',
        'generated', 'voiced', 'musicked', 'animated', 'rendered',
        'delivered', 'learned'
    ) THEN
        INSERT INTO cineos_core.checkpoints (
            project_id, state_at_checkpoint, current_phase,
            created_at
        ) VALUES (
            NEW.project_id, NEW.current_state, NEW.current_state::text,
            NOW()
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_projects_checkpoint
    AFTER UPDATE ON cineos_core.projects
    FOR EACH ROW EXECUTE FUNCTION cineos_core.create_checkpoint_on_phase();

-- Auto-update project progress based on state
CREATE OR REPLACE FUNCTION cineos_core.update_project_progress()
RETURNS TRIGGER AS $$
DECLARE
    progress_map JSONB := '{
        "received": 0.02,
        "validated": 0.04,
        "parsed": 0.08,
        "understood": 0.12,
        "biblified": 0.16,
        "characterized": 0.20,
        "worldbuilt": 0.24,
        "timeline_verified": 0.28,
        "planned": 0.35,
        "prompted": 0.40,
        "queued": 0.42,
        "generating": 0.50,
        "generated": 0.55,
        "reviewing": 0.60,
        "repairing": 0.58,
        "approved": 0.65,
        "voiced": 0.70,
        "musicked": 0.73,
        "animated": 0.78,
        "rendering": 0.82,
        "rendered": 0.88,
        "super_resolution": 0.90,
        "final_review": 0.93,
        "delivered": 0.97,
        "learned": 0.99,
        "completed": 1.00
    }'::jsonb;
BEGIN
    NEW.progress := (progress_map ->> NEW.current_state::text)::float;
    IF NEW.progress IS NULL THEN
        NEW.progress := OLD.progress;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_projects_progress
    BEFORE UPDATE ON cineos_core.projects
    FOR EACH ROW EXECUTE FUNCTION cineos_core.update_project_progress();

-- Enforce state machine transitions at database level
CREATE OR REPLACE FUNCTION cineos_core.enforce_state_transition()
RETURNS TRIGGER AS $$
DECLARE
    allowed_transitions JSONB;
BEGIN
    -- Only check if state is actually changing
    IF OLD.current_state = NEW.current_state THEN
        RETURN NEW;
    END IF;

    -- Load allowed transitions
    allowed_transitions := '{
        "received": ["validated", "cancelled"],
        "validated": ["parsed", "failed"],
        "parsed": ["understood", "failed"],
        "understood": ["biblified", "failed"],
        "biblified": ["characterized", "failed"],
        "characterized": ["worldbuilt", "failed"],
        "worldbuilt": ["timeline_verified", "failed"],
        "timeline_verified": ["planned", "failed"],
        "planned": ["prompted", "failed"],
        "prompted": ["queued", "failed"],
        "queued": ["generating", "failed"],
        "generating": ["generated", "failed", "retrying"],
        "generated": ["reviewing", "failed"],
        "reviewing": ["approved", "repairing", "failed"],
        "repairing": ["reviewing", "retrying", "failed", "manual_attention"],
        "approved": ["voiced", "failed"],
        "voiced": ["musicked", "failed"],
        "musicked": ["animated", "failed"],
        "animated": ["rendering", "failed"],
        "rendering": ["rendered", "failed", "retrying"],
        "rendered": ["super_resolution", "final_review", "failed"],
        "super_resolution": ["final_review", "failed"],
        "final_review": ["delivered", "failed", "repairing"],
        "delivered": ["learned", "failed"],
        "learned": ["completed", "failed"],
        "completed": [],
        "waiting": ["received", "validated", "parsed", "understood", "biblified", "characterized", "worldbuilt", "timeline_verified", "planned", "prompted", "queued", "generating", "generated", "reviewing", "repairing", "approved", "voiced", "musicked", "animated", "rendering", "rendered", "super_resolution", "final_review", "delivered", "learned", "cancelled"],
        "paused": ["received", "validated", "parsed", "understood", "biblified", "characterized", "worldbuilt", "timeline_verified", "planned", "prompted", "queued", "generating", "generated", "reviewing", "repairing", "approved", "voiced", "musicked", "animated", "rendering", "rendered", "super_resolution", "final_review", "delivered", "learned", "cancelled"],
        "retrying": ["received", "validated", "parsed", "understood", "biblified", "characterized", "worldbuilt", "timeline_verified", "planned", "prompted", "queued", "generating", "generated", "reviewing", "repairing", "approved", "voiced", "musicked", "animated", "rendering", "rendered", "super_resolution", "final_review", "delivered", "learned"],
        "failed": ["retrying", "manual_attention", "cancelled"],
        "manual_attention": ["received", "validated", "parsed", "understood", "biblified", "characterized", "worldbuilt", "timeline_verified", "planned", "prompted", "queued", "generating", "generated", "reviewing", "repairing", "approved", "voiced", "musicked", "animated", "rendering", "rendered", "super_resolution", "final_review", "delivered", "learned", "cancelled"],
        "cancelled": []
    }'::jsonb;

    -- Validate transition
    IF NOT (allowed_transitions ->> OLD.current_state::text) ? NEW.current_state::text THEN
        RAISE EXCEPTION 'Invalid state transition: % -> %', OLD.current_state, NEW.current_state;
    END IF;

    -- Record old state for audit
    NEW.previous_state := OLD.current_state;
    NEW.last_state_change_at := NOW();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_state_transition
    BEFORE UPDATE OF current_state ON cineos_core.projects
    FOR EACH ROW EXECUTE FUNCTION cineos_core.enforce_state_transition();
```

---

## 9. ARCHITECTURAL RULES — ENFORCED AT DATABASE LEVEL

```
RULE 1: PostgreSQL is the only permanent memory.
  ENFORCED BY: All tables in PostgreSQL, no external state stores for project data.

RULE 2: State Machine controls every workflow.
  ENFORCED BY: trg_enforce_state_transition trigger rejects invalid transitions.

RULE 3: Every workflow updates the database.
  ENFORCED BY: All workflows must write results to DB before signaling completion.

RULE 4: Every state change is logged.
  ENFORCED BY: trg_projects_checkpoint and state_log INSERT on every transition.

RULE 5: Every asset is versioned.
  ENFORCED BY: versions table, prompt_versions table, variant_number on images.

RULE 6: Every repair is tracked.
  ENFORCED BY: cineos_quality.repairs table, linked to review_id.

RULE 7: Every prompt is versioned.
  ENFORGED BY: cineos_gen.prompt_versions table with version_number.

RULE 8: Every event is stored.
  ENFORCED BY: cineos_core.events table, emitted on every transition.

RULE 9: Every worker reports status.
  ENFORCED BY: cineos_exec.workers.heartbeat_required, timeout marks offline.

RULE 10: Every project can resume from its last successful checkpoint.
  ENFORCED BY: cineos_core.checkpoints table, recovery protocol on startup.
```

---

*End of Part 3 — State Machine, Central Memory, Database Architecture, Event System, and Project Lifecycle*
