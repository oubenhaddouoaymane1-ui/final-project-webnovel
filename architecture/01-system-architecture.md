# PART 1 — SYSTEM ARCHITECTURE SPECIFICATION

## Novel-to-Cinematic AI Production Platform
### n8n-Orchestrated, State-Driven, Remote-First

---

## 1. SYSTEM IDENTITY

**Codename:** CineOS (Cinematic Operating System)

**Classification:** AI Cinematic Production Platform

**Orchestration Kernel:** n8n Community Edition

**Single Source of Truth:** PostgreSQL 16+

**Primary Interface:** Telegram Bot

**Architecture Pattern:** State Machine + Event-Driven Micro-Workflows

---

## 2. EXISTING SYSTEM ANALYSIS

The current codebase implements a 7-stage Python pipeline:

```
Intake → Analysis → Verify → PromptPlan → Render → Assembly → Audit
```

**Current Limitations:**
- Monolithic orchestrator (`PipelineOrchestrator`) — single point of failure
- Sequential execution — no parallelism, no remote dispatch
- SQLite — no concurrency, no JSONB, single-writer
- File-based checkpoints — not crash-safe, not queryable
- No state machine — pipeline either runs or halts, no partial recovery
- No shot-level granularity — failures cascade to scene/project level
- No remote execution — all computation local
- No learning — no post-project improvement
- Hardcoded quality thresholds — no adaptive tuning
- No reference generation pipeline — characters analyzed but not visual-referenced

**What Works (Preserve):**
- Backend priority chain with fallback (`BackendManager`)
- Character DNA model (40+ columns of evidence)
- World Bible model (25+ attributes)
- Stage-gating philosophy (no silent failures)
- Multi-backend health detection
- Evidence-based character extraction

---

## 3. SYSTEM LAYERS

```
┌─────────────────────────────────────────────────────────────┐
│                     LAYER 0: INTERFACE                       │
│  Telegram Bot ←→ n8n Webhook ←→ Progress/Delivery           │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 1: ORCHESTRATION                    │
│  n8n Master Orchestrator Workflows (State Machine Controller)│
├─────────────────────────────────────────────────────────────┤
│                     LAYER 2: MEMORY                          │
│  PostgreSQL: Story Bible | Character Bible | World Bible     │
│  Timeline Bible | Style Bible | Project State | Audit Trail  │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 3: ANALYSIS                        │
│  LLM Workflows: Chapter | Scene | Character | World |        │
│  Timeline | Dialogue | Emotion | Inconsistency Detection     │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 4: PLANNING                        │
│  Shot Planning | Prompt Generation | Reference Planning      │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 5: GENERATION                      │
│  Image Gen | TTS | Narration | Music Suggestion              │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 6: QUALITY                         │
│  Review | Scoring | Failure Detection | Repair Dispatch      │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 7: ASSEMBLY                        │
│  Animation | Video Rendering | Final Composition             │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 8: DELIVERY                        │
│  Final Review | Telegram Delivery | Archive                  │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 9: LEARNING                        │
│  Post-Project Analysis | Threshold Tuning | Prompt Evolution │
├─────────────────────────────────────────────────────────────┤
│                     LAYER 10: EXECUTION                      │
│  Remote Workers | GPU Workers | CPU Workers | Task Queue     │
└─────────────────────────────────────────────────────────────┘
```

**Layer Communication Rules:**
- Layers communicate ONLY through PostgreSQL (database-mediated)
- No direct function calls between layers
- No shared memory between workflows
- Every inter-layer interaction is a database read/write with explicit state transition
- n8n workflows operate at Layers 0, 1, 3, 4, 6, 8, 9
- External workers operate at Layers 5, 7, 10

---

## 4. STATE MACHINE — MASTER DESIGN

### 4.1 Project State Machine

```
                                    ┌──────────┐
                                    │ CREATED  │
                                    └────┬─────┘
                                         │
                                    ┌────▼─────┐
                                    │ INTAKING │
                                    └────┬─────┘
                                         │
                              ┌──────────▼──────────┐
                              │   INTAKE_COMPLETE    │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  ANALYSIS_RUNNING    │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  ANALYSIS_COMPLETE   │
                              └──────────┬──────────┘
                                         │
                        ┌────────────────▼────────────────┐
                        │  REFERENCE_GENERATION_RUNNING    │
                        └────────────────┬────────────────┘
                                         │
                        ┌────────────────▼────────────────┐
                        │  REFERENCE_GENERATION_COMPLETE   │
                        └────────────────┬────────────────┘
                                         │
                        ┌────────────────▼────────────────┐
                        │  SHOT_PLANNING_RUNNING           │
                        └────────────────┬────────────────┘
                                         │
                        ┌────────────────▼────────────────┐
                        │  SHOT_PLANNING_COMPLETE          │
                        └────────────────┬────────────────┘
                                         │
                        ┌────────────────▼────────────────┐
                        │  ASSET_GENERATION_RUNNING        │
                        └────────────────┬────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  QUALITY_REVIEWING   │
                              └──────────┬──────────┘
                                    ┌────┴────┐
                               ┌────▼───┐ ┌──▼───────┐
                               │ PASSED │ │  FAILED   │
                               └────┬───┘ └────┬─────┘
                                    │     ┌────▼──────────┐
                                    │     │ REPAIR_RUNNING │
                                    │     └────┬──────────┘
                                    │     ┌────▼──────────┐
                                    │     │ REPAIR_COMPLETE│──→ (back to QUALITY_REVIEWING)
                                    │     └────┬──────────┘
                                    │     ┌────▼───────────┐
                                    │     │ UNRECOVERABLE   │
                                    │     └────────────────┘
                                    │
                              ┌─────▼──────┐
                              │ ASSEMBLING  │
                              └─────┬──────┘
                                    │
                              ┌─────▼──────┐
                              │ ASSEMBLED   │
                              └─────┬──────┘
                                    │
                              ┌─────▼──────┐
                              │ FINAL_REVIEW│
                              └─────┬──────┘
                              ┌─────┴─────┐
                         ┌────▼───┐ ┌─────▼──────┐
                         │APPROVED│ │ REJECTED   │──→ (back to REPAIR_RUNNING or FAILED)
                         └────┬───┘ └────────────┘
                              │
                         ┌────▼──────┐
                         │ DELIVERING │
                         └────┬──────┘
                              │
                         ┌────▼──────┐
                         │ DELIVERED  │
                         └────┬──────┘
                              │
                         ┌────▼──────┐
                         │ LEARNING   │
                         └────┬──────┘
                              │
                         ┌────▼──────┐
                         │ COMPLETED  │
                         └───────────┘
```

### 4.2 Project State Enum

```sql
CREATE TYPE project_state AS ENUM (
    'created',
    'intaking',
    'intake_complete',
    'analysis_running',
    'analysis_complete',
    'reference_generation_running',
    'reference_generation_complete',
    'shot_planning_running',
    'shot_planning_complete',
    'asset_generation_running',
    'quality_reviewing',
    'repair_running',
    'repair_complete',
    'unrecoverable',
    'assembling',
    'assembled',
    'final_reviewing',
    'delivery_running',
    'delivered',
    'learning_running',
    'completed',
    'failed',
    'paused',
    'cancelled'
);
```

### 4.3 Scene State Machine

```sql
CREATE TYPE scene_state AS ENUM (
    'pending',
    'analyzing',
    'analyzed',
    'reference_pending',
    'references_ready',
    'shot_planning',
    'shots_planned',
    'generating_assets',
    'assets_generated',
    'quality_reviewing',
    'passed',
    'failed',
    'repairing',
    'repair_complete',
    'assembled',
    'completed'
);
```

### 4.4 Shot State Machine

```sql
CREATE TYPE shot_state AS ENUM (
    'pending',
    'prompt_generating',
    'prompt_ready',
    'image_generating',
    'image_generated',
    'image_reviewing',
    'image_passed',
    'image_failed',
    'audio_generating',
    'audio_generated',
    'audio_reviewing',
    'audio_passed',
    'audio_failed',
    'ready_for_assembly',
    'assembled',
    'completed'
);
```

### 4.5 State Transition Rules

Every state transition is recorded in `state_transitions` table:

```sql
CREATE TABLE state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,       -- 'project', 'chapter', 'scene', 'shot'
    entity_id UUID NOT NULL,
    from_state VARCHAR(100) NOT NULL,
    to_state VARCHAR(100) NOT NULL,
    triggered_by VARCHAR(200),               -- workflow name or worker ID
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Transition Rules:**
1. Every transition MUST be recorded before the new state takes effect
2. Invalid transitions (from_state doesn't match current state) are rejected
3. Transitions are atomic — database transaction ensures consistency
4. The orchestrator is the ONLY entity that may trigger project-level transitions
5. Sub-workflows may trigger scene/shot-level transitions within their authorized scope

---

## 5. MEMORY ARCHITECTURE

### 5.1 Memory Hierarchy

```
                    ┌─────────────────┐
                    │  PROJECT MEMORY  │
                    │  (Project State) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──────┐ ┌────▼──────┐ ┌─────▼──────┐
    │  STORY BIBLE   │ │ CHARACTER │ │   WORLD    │
    │                │ │  BIBLE    │ │   BIBLE    │
    └────────┬───────┘ └─────┬─────┘ └─────┬─────┘
             │               │              │
    ┌────────▼───────┐ ┌─────▼─────┐ ┌─────▼──────┐
    │   TIMELINE     │ │  STYLE    │ │  SCENE     │
    │   BIBLE        │ │  BIBLE    │ │  MEMORY    │
    └────────────────┘ └───────────┘ └────────────┘
```

### 5.2 Story Bible

Stores deep understanding of the narrative structure.

```sql
CREATE TABLE story_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL DEFAULT 1,

    -- Core Narrative
    title TEXT NOT NULL,
    genre TEXT,
    subgenre TEXT,
    theme TEXT,
    central_conflict TEXT,
    resolution TEXT,
    narrative_arc TEXT,            -- 'linear', 'nonlinear', 'parallel', 'circular'
    point_of_view TEXT,            -- 'first', 'third_limited', 'third_omniscient'
    tense TEXT,                    -- 'past', 'present'
    tone TEXT,                     -- 'dark', 'light', 'epic', 'intimate'
    pacing TEXT,                   -- 'slow_burn', 'fast', 'varied'

    -- Structure
    total_chapters INTEGER,
    total_scenes INTEGER,
    estimated_duration_minutes FLOAT,

    -- Deep Analysis
    themes TEXT[],                 -- array of identified themes
    symbols TEXT[],                -- recurring symbols
    motifs TEXT[],                 -- recurring motifs
    foreshadowing JSONB,           -- events and their payoffs
    character_arcs JSONB,          -- each character's journey
    world_state_changes JSONB,     -- how the world changes over time

    -- Visual Translation Notes
    visual_style TEXT,             -- 'anime', 'manhwa', 'cinematic', 'realistic'
    color_grading TEXT,            -- 'warm', 'cool', 'desaturated', 'vibrant'
    lighting_mood TEXT,            -- 'dramatic', 'soft', 'naturalistic', 'noir'
    camera_style TEXT,             -- 'dynamic', 'static', 'handheld', 'aerial'

    -- Consistency
    contradictions JSONB,          -- detected narrative contradictions
    plot_holes JSONB,              -- detected plot holes
    timeline_conflicts JSONB,      -- detected timeline issues

    -- Metadata
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    confidence_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);
```

### 5.3 Character Bible

Each character gets an immutable reference card once locked.

```sql
CREATE TABLE character_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL DEFAULT 1,

    -- Identity
    canonical_name TEXT NOT NULL,
    alternative_names TEXT[],
    nicknames TEXT[],
    titles TEXT[],
    role TEXT,                      -- 'protagonist', 'antagonist', 'supporting', 'minor'

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
    voice_pitch TEXT,               -- 'deep', 'medium', 'high'
    voice_pace TEXT,                -- 'slow', 'normal', 'fast'
    voice_accent TEXT,

    -- Relationships
    relationships JSONB,            -- {character_id: {type, description}}

    -- Evidence
    evidence_sources TEXT[],        -- quotes from novel
    inferred_traits TEXT[],         -- LLM-inferred, not explicitly stated
    confidence_score FLOAT DEFAULT 0.0,

    -- Visual Prompt Components
    visual_prompt_positive TEXT,    -- pre-built positive prompt fragment
    visual_prompt_negative TEXT,    -- pre-built negative prompt fragment
    reference_image_path TEXT,      -- generated character reference image

    -- Consistency Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    lock_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, canonical_name)
);
```

### 5.4 World Bible

```sql
CREATE TABLE world_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL DEFAULT 1,

    -- Geography
    world_name TEXT,
    world_size TEXT,
    continents TEXT[],
    regions TEXT[],
    notable_landmarks TEXT[],
    geography_description TEXT,

    -- Climate
    climate_zones TEXT,
    weather_patterns TEXT,
    seasonal_changes TEXT,

    -- History
    era_name TEXT,
    historical_eras JSONB,          -- [{name, period, description}]
    founding_myths TEXT,
    major_events JSONB,             -- [{event, date, impact}]

    -- Architecture
    architectural_style TEXT,
    building_materials TEXT[],
    notable_structures TEXT[],
    urban_vs_rural TEXT,

    -- Technology
    technology_level TEXT,          -- 'stone_age', 'medieval', 'renaissance', 'industrial', 'modern', 'futuristic', 'magitech'
    technology_details TEXT,
    communication_methods TEXT[],
    transportation_methods TEXT[],

    -- Magic/Supernatural
    magic_system TEXT,
    magic_rules TEXT[],
    magical_creatures TEXT[],
    supernatural_forces TEXT,

    -- Society
    political_system TEXT,
    social_hierarchy TEXT,
    economic_system TEXT,
    religious_system TEXT,
    cultural_values TEXT[],

    -- Visual Design
    color_palette TEXT[],           -- dominant colors of the world
    lighting_style TEXT,            -- 'natural', 'dramatic', 'ethereal', 'harsh'
    visual_atmosphere TEXT,         -- 'gritty', 'pristine', 'decayed', 'vibrant'
    visual_keywords TEXT[],         -- words that capture the world's look
    material_aesthetics TEXT,       -- 'stone', 'wood', 'metal', 'glass', 'organic'

    -- Fauna and Flora
    notable_animals TEXT[],
    dangerous_creatures TEXT[],
    notable_plants TEXT[],
    mythical_species TEXT[],

    -- Evidence
    evidence_sources TEXT[],
    confidence_score FLOAT DEFAULT 0.0,

    -- Visual Prompt Components
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    reference_images JSONB,         -- [{description, path}]

    -- Lock
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);
```

### 5.5 Timeline Bible

```sql
CREATE TABLE timeline_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),

    -- Events in chronological order
    events JSONB NOT NULL,          -- [{
                                     --   id, scene_id, chapter_number,
                                     --   sequence_number,
                                     --   time_reference: "dawn", "three days later",
                                     --   absolute_order: 1,
                                     --   duration_estimate: "hours",
                                     --   characters_present: [],
                                     --   location: "",
                                     --   cause: "what triggered this event",
                                     --   effect: "what this event causes",
                                     --   concurrent_with: [],
                                     --   flashbacks_to: [],
                                     --   foreshadows: []
                                     -- }]

    -- Timeline metadata
    total_events INTEGER,
    time_span TEXT,                  -- "three years", "one night"
    has_flashbacks BOOLEAN DEFAULT FALSE,
    has_parallel_timelines BOOLEAN DEFAULT FALSE,
    timeline_type TEXT,              -- 'linear', 'nonlinear', 'parallel'

    -- Conflicts detected
    contradictions JSONB,
    paradoxes JSONB,

    locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.6 Style Bible

```sql
CREATE TABLE style_bibles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL DEFAULT 1,

    -- Global Visual Style
    art_style TEXT,                  -- 'anime', 'manhwa', 'realistic', 'watercolor'
    rendering_style TEXT,            -- 'cel_shaded', 'painted', 'photorealistic', 'sketch'
    line_weight TEXT,                -- 'bold', 'fine', 'varied'
    shading_style TEXT,              -- 'cel', 'soft', 'cross_hatch', 'minimal'

    -- Color System
    primary_palette TEXT[],
    secondary_palette TEXT[],
    accent_colors TEXT[],
    color_temperature TEXT,          -- 'warm', 'cool', 'neutral'
    saturation_level TEXT,           -- 'vibrant', 'muted', 'varied'

    -- Lighting
    default_lighting TEXT,
    dramatic_lighting TEXT,
    soft_lighting TEXT,
    night_lighting TEXT,
    indoor_lighting TEXT,

    -- Composition Rules
    rule_of_thirds BOOLEAN DEFAULT TRUE,
    depth_of_field TEXT,             -- 'shallow', 'deep', 'varied'
    camera_angles_preferred TEXT[],  -- ['eye_level', 'low_angle', 'dutch_angle']
    shot_types_distribution JSONB,   -- {establishing: 0.1, wide: 0.2, medium: 0.3, close_up: 0.3, extreme_close_up: 0.1}

    -- Character Rendering
    character_detail_level TEXT,     -- 'high', 'medium', 'low'
    facial_expressions_style TEXT,
    body_proportions TEXT,           -- 'realistic', 'stylized', 'chibi_moments'

    -- Background Rendering
    background_detail_level TEXT,
    background_blur_style TEXT,
    environment_mood TEXT,

    -- Transitions
    preferred_transitions TEXT[],    -- ['fade', 'dissolve', 'wipe', 'match_cut']
    transition_style TEXT,           -- 'smooth', 'sharp', 'cinematic'

    -- Typography (for any text overlays)
    font_style TEXT,
    subtitle_style TEXT,

    -- Global Prompt Fragments
    base_positive_prompt TEXT,       -- always prepended to prompts
    base_negative_prompt TEXT,       -- always appended to negative prompts
    quality_tags TEXT,               -- 'masterpiece, best quality, highly detailed'

    -- Reference
    reference_style_images JSONB,   -- [{description, path}]

    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version)
);
```

### 5.7 Memory Read/Write Rules

```
┌──────────────────────────────────────────────────────────────┐
│                    MEMORY ACCESS RULES                         │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Bibles are WRITTEN during their dedicated phase           │
│  2. Bibles are READ-ONLY after their phase completes          │
│  3. Bibles are LOCKED (immutable) after verification          │
│  4. Locked bibles can only be unlocked by orchestrator        │
│  5. Every bible has a version number                          │
│  6. Unlocking creates a new version, preserving old           │
│  7. Prompts are GENERATED FROM bibles, never the source       │
│  8. All writes to bibles require orchestrator authorization   │
│  9. All reads from bibles are logged in audit trail           │
│ 10. Bibles can be DOWNGRADED (reverted to previous version)   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. POSTGRESQL SCHEMA — COMPLETE DESIGN

### 6.1 Schema Organization

```
PostgreSQL Database: cineos

Schemas:
  cineos.core       — Projects, chapters, scenes, shots
  cineos.memory     — Bibles, character data, world data
  cineos.generation — Generated assets (images, audio, video)
  cineos.quality    — Reviews, scores, repair attempts
  cineos.execution  — Workers, tasks, queue
  cineos.audit      — Transitions, logs, learning data
  cineos.config     — System configuration, thresholds
```

### 6.2 Core Schema

```sql
-- Projects
CREATE TABLE cineos.core.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL,                    -- Telegram user ID
    chat_id BIGINT NOT NULL,                    -- Telegram chat ID
    state project_state NOT NULL DEFAULT 'created',
    progress FLOAT DEFAULT 0.0,                 -- 0.0 to 1.0
    current_phase VARCHAR(100),
    error_message TEXT,
    error_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    priority INTEGER DEFAULT 5,                 -- 1=highest, 10=lowest
    config JSONB DEFAULT '{}',                  -- per-project overrides
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

-- Novels
CREATE TABLE cineos.core.novels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT,
    word_count INTEGER,
    char_count INTEGER,
    encoding VARCHAR(50),
    language VARCHAR(20),
    source_type VARCHAR(20) DEFAULT 'telegram', -- 'telegram', 'file', 'paste'
    file_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chapters
CREATE TABLE cineos.core.chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    novel_id UUID NOT NULL REFERENCES cineos.core.novels(id),
    chapter_number INTEGER NOT NULL,
    title TEXT,
    text TEXT NOT NULL,
    word_count INTEGER,
    scene_count INTEGER DEFAULT 0,
    state scene_state DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(novel_id, chapter_number)
);

-- Scenes
CREATE TABLE cineos.core.scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    chapter_id UUID NOT NULL REFERENCES cineos.core.chapters(id),
    chapter_number INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    state scene_state NOT NULL DEFAULT 'pending',

    -- Content
    full_text TEXT NOT NULL,
    summary TEXT,
    beginning_text TEXT,
    ending_text TEXT,

    -- Extraction
    location_name TEXT,
    time_of_day TEXT,
    weather TEXT,
    primary_emotion TEXT,
    secondary_emotions TEXT[],
    conflict_type TEXT,
    conflict_description TEXT,
    importance VARCHAR(20) DEFAULT 'normal',    -- 'critical', 'high', 'normal', 'low'
    pacing VARCHAR(20) DEFAULT 'normal',        -- 'fast', 'normal', 'slow'

    -- Dialogue
    has_dialogue BOOLEAN DEFAULT FALSE,
    dialogue_count INTEGER DEFAULT 0,
    emotional_arc TEXT,

    -- Action
    has_action BOOLEAN DEFAULT FALSE,
    action_intensity TEXT,
    combat_present BOOLEAN DEFAULT FALSE,

    -- Transitions
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',

    -- Shot Plan Reference
    shot_count INTEGER DEFAULT 0,
    estimated_duration_seconds FLOAT,

    -- Quality
    quality_score FLOAT,
    quality_issues JSONB,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, chapter_number, scene_number)
);

-- Scene-Character Junction
CREATE TABLE cineos.core.scene_characters (
    scene_id UUID NOT NULL REFERENCES cineos.core.scenes(id),
    character_id UUID NOT NULL REFERENCES cineos.core.characters(id),
    role VARCHAR(50) DEFAULT 'present',        -- 'protagonist', 'antagonist', 'present', 'mentioned'
    emotional_state TEXT,
    dialogue_lines TEXT[],
    PRIMARY KEY (scene_id, character_id)
);

-- Shots
CREATE TABLE cineos.core.shots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID NOT NULL REFERENCES cineos.core.scenes(id),
    shot_number INTEGER NOT NULL,
    state shot_state NOT NULL DEFAULT 'pending',

    -- Shot Type
    shot_type VARCHAR(50) NOT NULL,            -- 'establishing', 'wide', 'medium', 'close_up', 'extreme_close_up', 'action', 'insert'
    duration_seconds FLOAT NOT NULL,
    importance VARCHAR(20) DEFAULT 'normal',

    -- Prompt
    positive_prompt TEXT,
    negative_prompt TEXT,
    prompt_version INTEGER DEFAULT 1,

    -- Camera
    camera_angle VARCHAR(50),
    camera_movement VARCHAR(50),               -- 'static', 'pan_left', 'pan_right', 'tilt_up', 'tilt_down', 'zoom_in', 'zoom_out', 'tracking'
    depth_of_field VARCHAR(20),

    -- Animation
    animation_type VARCHAR(50),                -- 'ken_burns_zoom_in', 'ken_burns_zoom_out', 'ken_burns_pan', 'parallax', 'subtle_breathing', 'none'
    animation_params JSONB,

    -- Transition
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',
    transition_duration_ms INTEGER DEFAULT 500,

    -- Character in shot
    characters_in_shot UUID[],

    -- Narration
    narration_text TEXT,
    narration_voice VARCHAR(100),
    narration_emotion VARCHAR(50),

    -- Quality
    quality_score FLOAT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(scene_id, shot_number)
);
```

### 6.3 Memory Schema

```sql
-- (Story Bible, Character Bible, World Bible, Timeline Bible, Style Bible)
-- Tables defined in Section 5 above, all in cineos.memory schema

-- Character Reference Images
CREATE TABLE cineos.memory.character_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES cineos.core.characters(id),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    reference_type VARCHAR(50) NOT NULL,       -- 'portrait', 'full_body', 'expression_sheet', 'outfit'
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    backend_used VARCHAR(100),
    seed INTEGER,
    quality_score FLOAT,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- World Reference Images
CREATE TABLE cineos.memory.world_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    world_bible_id UUID NOT NULL REFERENCES cineos.memory.world_bibles(id),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    reference_type VARCHAR(50) NOT NULL,       -- 'landscape', 'building', 'interior', 'map'
    location_name TEXT,
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    backend_used VARCHAR(100),
    quality_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Style Reference Images
CREATE TABLE cineos.memory.style_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    reference_type VARCHAR(50) NOT NULL,       -- 'color_palette', 'mood', 'lighting', 'composition'
    description TEXT,
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.4 Generation Schema

```sql
-- Generated Images
CREATE TABLE cineos.generation.images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos.core.shots(id),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    variant_number INTEGER NOT NULL DEFAULT 1,

    -- Generation
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    prompt_used TEXT NOT NULL,
    negative_prompt_used TEXT,
    backend_used VARCHAR(100),
    model_used VARCHAR(200),
    seed INTEGER,
    width INTEGER,
    height INTEGER,
    steps INTEGER,
    cfg_scale FLOAT,

    -- Quality
    quality_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    composition_score FLOAT,
    prompt_alignment_score FLOAT,
    is_selected BOOLEAN DEFAULT FALSE,
    selection_reason TEXT,

    -- Source
    generated_locally BOOLEAN DEFAULT TRUE,
    worker_id UUID,
    generation_time_ms INTEGER,

    -- State
    state VARCHAR(50) DEFAULT 'generated',     -- 'generating', 'generated', 'reviewing', 'selected', 'rejected', 'repaired'
    rejection_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(shot_id, variant_number)
);

-- Generated Audio (Narration)
CREATE TABLE cineos.generation.audio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos.core.shots(id),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),

    -- Generation
    audio_path TEXT NOT NULL,
    text_used TEXT NOT NULL,
    voice_used VARCHAR(100),
    emotion VARCHAR(50),
    speed FLOAT DEFAULT 1.0,
    pitch FLOAT DEFAULT 1.0,

    -- Quality
    duration_seconds FLOAT,
    sample_rate INTEGER,
    quality_score FLOAT,
    is_selected BOOLEAN DEFAULT FALSE,

    -- Source
    backend_used VARCHAR(100),
    worker_id UUID,
    generation_time_ms INTEGER,

    -- State
    state VARCHAR(50) DEFAULT 'generated',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Generated Video Clips (individual shot videos with animation)
CREATE TABLE cineos.generation.video_clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos.core.shots(id),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),

    -- Source
    image_id UUID REFERENCES cineos.generation.images(id),
    audio_id UUID REFERENCES cineos.generation.audio(id),

    -- Output
    clip_path TEXT NOT NULL,
    duration_seconds FLOAT,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    codec VARCHAR(50),

    -- Animation
    animation_applied VARCHAR(50),
    animation_params JSONB,

    -- Quality
    quality_score FLOAT,
    state VARCHAR(50) DEFAULT 'pending',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Final Video
CREATE TABLE cineos.generation.final_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),

    -- Output
    video_path TEXT NOT NULL,
    thumbnail_path TEXT,
    duration_seconds FLOAT,
    file_size_bytes BIGINT,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    codec VARCHAR(50),
    bitrate INTEGER,

    -- Quality
    overall_quality_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    audio_video_sync_score FLOAT,
    narrative_fidelity_score FLOAT,

    -- State
    state VARCHAR(50) DEFAULT 'pending',       -- 'rendering', 'rendered', 'reviewing', 'approved', 'rejected', 'delivered'
    rejection_reason TEXT,

    -- Metadata
    total_scenes INTEGER,
    total_shots INTEGER,
    render_time_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.5 Quality Schema

```sql
-- Quality Reviews
CREATE TABLE cineos.quality.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    entity_type VARCHAR(50) NOT NULL,          -- 'project', 'scene', 'shot', 'image', 'audio', 'video'
    entity_id UUID NOT NULL,
    review_type VARCHAR(50) NOT NULL,          -- 'automatic', 'manual', 'repair_check'

    -- Scores (0.0 to 1.0)
    overall_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    composition_score FLOAT,
    prompt_alignment_score FLOAT,
    audio_quality_score FLOAT,
    video_quality_score FLOAT,
    narrative_fidelity_score FLOAT,

    -- Details
    passed BOOLEAN NOT NULL,
    issues JSONB,                              -- [{severity, category, description, entity_id}]
    recommendations JSONB,                     -- [{action, target, reason}]

    -- Model
    reviewer_model VARCHAR(100),               -- which model did the review
    reviewer_version VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Quality Thresholds (per-project, tunable)
CREATE TABLE cineos.quality.thresholds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),

    -- Image thresholds
    min_image_quality FLOAT DEFAULT 0.60,
    min_character_consistency FLOAT DEFAULT 0.70,
    min_world_consistency FLOAT DEFAULT 0.60,
    min_composition FLOAT DEFAULT 0.50,
    min_prompt_alignment FLOAT DEFAULT 0.60,

    -- Audio thresholds
    min_audio_quality FLOAT DEFAULT 0.50,

    -- Video thresholds
    min_video_quality FLOAT DEFAULT 0.60,
    min_overall_quality FLOAT DEFAULT 0.60,

    -- Repair thresholds
    max_repair_attempts INTEGER DEFAULT 3,
    repair_escalation_threshold FLOAT DEFAULT 0.30,

    -- Global
    hard_failure_threshold FLOAT DEFAULT 0.20,
    auto_approve_threshold FLOAT DEFAULT 0.85,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Repair Attempts
CREATE TABLE cineos.quality.repairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    original_entity_type VARCHAR(50) NOT NULL,
    original_entity_id UUID NOT NULL,
    repair_entity_type VARCHAR(50) NOT NULL,
    repair_entity_id UUID NOT NULL,

    -- What failed
    failure_reason TEXT,
    failure_score FLOAT,
    failure_issues JSONB,

    -- What was repaired
    repair_strategy VARCHAR(100),              -- 'regenerate_prompt', 'regenerate_image', 'adjust_prompt', 'change_backend', 'manual_override'
    repair_description TEXT,
    repair_attempt_number INTEGER,

    -- Result
    pre_repair_score FLOAT,
    post_repair_score FLOAT,
    improvement FLOAT,
    success BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.6 Execution Schema

```sql
-- Worker Registry
CREATE TABLE cineos.execution.workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name VARCHAR(200) NOT NULL,
    worker_type VARCHAR(50) NOT NULL,          -- 'gpu_image', 'cpu_tts', 'cpu_render', 'vision_review', 'super_resolution'
    host VARCHAR(200),
    port INTEGER,
    protocol VARCHAR(20) DEFAULT 'http',
    endpoint_url TEXT,

    -- Capabilities
    supported_backends TEXT[],
    gpu_model TEXT,
    gpu_vram_gb FLOAT,
    cpu_cores INTEGER,
    ram_gb FLOAT,
    storage_gb FLOAT,

    -- Status
    status VARCHAR(50) DEFAULT 'idle',         -- 'idle', 'busy', 'offline', 'error', 'maintenance'
    current_task_id UUID,
    last_heartbeat TIMESTAMPTZ,
    heartbeat_interval_ms INTEGER DEFAULT 30000,

    -- Metrics
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    avg_task_duration_ms FLOAT,
    success_rate FLOAT DEFAULT 1.0,

    -- Configuration
    max_concurrent_tasks INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 5,
    enabled BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Task Queue
CREATE TABLE cineos.execution.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    task_type VARCHAR(100) NOT NULL,           -- 'generate_image', 'generate_audio', 'render_clip', 'review_quality'
    state VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending', 'queued', 'assigned', 'running', 'completed', 'failed', 'cancelled'

    -- Assignment
    assigned_worker_id UUID REFERENCES cineos.execution.workers(id),
    priority INTEGER DEFAULT 5,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Payload
    payload JSONB NOT NULL,                    -- task-specific input data
    result JSONB,                              -- task output data

    -- Timing
    queued_at TIMESTAMPTZ,
    assigned_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    timeout_ms INTEGER DEFAULT 300000,         -- 5 minutes default

    -- Error
    error_message TEXT,
    error_traceback TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Workflow Executions
CREATE TABLE cineos.execution.workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),
    workflow_name VARCHAR(200) NOT NULL,
    n8n_execution_id VARCHAR(100),

    -- State
    state VARCHAR(50) NOT NULL DEFAULT 'pending',
    trigger_data JSONB,
    result_data JSONB,
    error_data JSONB,

    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,

    -- Retry
    attempt_number INTEGER DEFAULT 1,
    max_attempts INTEGER DEFAULT 3,
    parent_execution_id UUID,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.7 Audit Schema

```sql
-- State Transitions (full audit trail)
CREATE TABLE cineos.audit.state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    from_state VARCHAR(100),
    to_state VARCHAR(100) NOT NULL,
    triggered_by VARCHAR(200),
    trigger_workflow VARCHAR(200),
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- System Events
CREATE TABLE cineos.audit.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    event_type VARCHAR(100) NOT NULL,          -- 'error', 'warning', 'info', 'state_change', 'quality_gate', 'repair_triggered'
    source VARCHAR(200),                       -- workflow name or worker ID
    severity VARCHAR(20) DEFAULT 'info',
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Learning Data
CREATE TABLE cineos.audit.learning_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos.core.projects(id),

    -- Pre-project estimates
    estimated_scenes INTEGER,
    estimated_shots INTEGER,
    estimated_duration_minutes FLOAT,

    -- Actuals
    actual_scenes INTEGER,
    actual_shots INTEGER,
    actual_duration_minutes FLOAT,

    -- Performance
    total_generation_time_ms BIGINT,
    total_review_time_ms BIGINT,
    total_repair_time_ms BIGINT,
    total_assembly_time_ms BIGINT,

    -- Quality
    first_pass_quality_score FLOAT,
    final_quality_score FLOAT,
    repair_success_rate FLOAT,
    average_shots_per_repair INTEGER,

    -- Backend Usage
    image_backends_used JSONB,                 -- {backend: count}
    audio_backends_used JSONB,
    primary_image_backend VARCHAR(100),
    primary_audio_backend VARCHAR(100),

    -- Prompt Performance
    avg_prompt_alignment_score FLOAT,
    worst_prompt_alignment_score FLOAT,
    best_performing_shot_types JSONB,

    -- Lessons Learned
    lessons JSONB,                             -- [{category, lesson, impact}]
    recommendations JSONB,                     -- [{action, reason, priority}]

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.8 Config Schema

```sql
-- System Configuration
CREATE TABLE cineos.config.system_config (
    key VARCHAR(200) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    category VARCHAR(100),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(200)
);

-- Default Quality Thresholds
INSERT INTO cineos.config.system_config (key, value, description, category) VALUES
('quality.min_image_quality', '0.60', 'Minimum image quality score', 'quality'),
('quality.min_character_consistency', '0.70', 'Minimum character consistency', 'quality'),
('quality.min_world_consistency', '0.60', 'Minimum world consistency', 'quality'),
('quality.min_composition', '0.50', 'Minimum composition score', 'quality'),
('quality.min_prompt_alignment', '0.60', 'Minimum prompt alignment', 'quality'),
('quality.min_audio_quality', '0.50', 'Minimum audio quality', 'quality'),
('quality.min_video_quality', '0.60', 'Minimum video quality', 'quality'),
('quality.min_overall_quality', '0.60', 'Minimum overall quality', 'quality'),
('quality.max_repair_attempts', '3', 'Maximum repair attempts per item', 'quality'),
('quality.auto_approve_threshold', '0.85', 'Auto-approve above this score', 'quality'),
('generation.default_image_backend_priority', '["local_gpu","hf_inference","pollinations"]', 'Image backend priority', 'generation'),
('generation.default_tts_backend_priority', '["edge_tts","piper","espeak"]', 'TTS backend priority', 'generation'),
('generation.candidates_per_shot', '2', 'Number of image candidates per shot', 'generation'),
('generation.image_concurrency', '1', 'Concurrent image generation tasks', 'generation'),
('generation.audio_concurrency', '2', 'Concurrent audio generation tasks', 'generation'),
('video.default_fps', '24', 'Default video FPS', 'video'),
('video.default_resolution', '1920x1080', 'Default video resolution', 'video'),
('video.default_codec', 'libx264', 'Default video codec', 'video'),
('video.default_audio_codec', 'aac', 'Default audio codec', 'video'),
('limits.max_novel_words', '500000', 'Maximum novel word count', 'limits'),
('limits.max_scenes', '200', 'Maximum scenes per project', 'limits'),
('limits.max_shots', '1000', 'Maximum shots per project', 'limits'),
('limits.max_project_duration_hours', '72', 'Maximum project processing time', 'limits'),
('telegram.progress_update_interval_seconds', '30', 'Progress update frequency', 'telegram');
```

### 6.9 Indexes

```sql
-- Performance Indexes
CREATE INDEX idx_projects_user ON cineos.core.projects(user_id);
CREATE INDEX idx_projects_state ON cineos.core.projects(state);
CREATE INDEX idx_projects_updated ON cineos.core.projects(updated_at);

CREATE INDEX idx_scenes_project ON cineos.core.scenes(project_id);
CREATE INDEX idx_scenes_state ON cineos.core.scenes(state);
CREATE INDEX idx_scenes_chapter ON cineos.core.scenes(chapter_id);

CREATE INDEX idx_shots_scene ON cineos.core.shots(scene_id);
CREATE INDEX idx_shots_state ON cineos.core.shots(state);

CREATE INDEX idx_images_shot ON cineos.generation.images(shot_id);
CREATE INDEX idx_images_project ON cineos.generation.images(project_id);
CREATE INDEX idx_images_selected ON cineos.generation.images(is_selected) WHERE is_selected = TRUE;

CREATE INDEX idx_audio_shot ON cineos.generation.audio(shot_id);
CREATE INDEX idx_audio_project ON cineos.generation.audio(project_id);

CREATE INDEX idx_tasks_state ON cineos.execution.tasks(state);
CREATE INDEX idx_tasks_type ON cineos.execution.tasks(task_type);
CREATE INDEX idx_tasks_worker ON cineos.execution.tasks(assigned_worker_id);
CREATE INDEX idx_tasks_project ON cineos.execution.tasks(project_id);
CREATE INDEX idx_tasks_priority ON cineos.execution.tasks(priority, created_at);

CREATE INDEX idx_workers_status ON cineos.execution.workers(status);
CREATE INDEX idx_workers_type ON cineos.execution.workers(worker_type);

CREATE INDEX idx_transitions_entity ON cineos.audit.state_transitions(entity_type, entity_id);
CREATE INDEX idx_transitions_project ON cineos.audit.state_transitions(created_at);

CREATE INDEX idx_events_project ON cineos.audit.events(project_id);
CREATE INDEX idx_events_type ON cineos.audit.events(event_type);
CREATE INDEX idx_events_severity ON cineos.audit.events(severity);

CREATE INDEX idx_reviews_entity ON cineos.quality.reviews(entity_type, entity_id);
CREATE INDEX idx_reviews_project ON cineos.quality.reviews(project_id);

CREATE INDEX idx_learning_project ON cineos.audit.learning_data(project_id);

-- Full-text search on novel text
CREATE INDEX idx_novels_text ON cineos.core.novels USING gin(to_tsvector('english', raw_text));
```

---

## 7. WORKFLOW DECOMPOSITION

### 7.1 Master Workflow Inventory

The system consists of **32 specialized workflows** organized into 6 tiers:

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER 0: INTERFACE (2 workflows)                                │
│  ├─ telegram_intake          — Receives files, creates projects │
│  └─ telegram_delivery        — Delivers final video + reports   │
├─────────────────────────────────────────────────────────────────┤
│  TIER 1: ORCHESTRATION (3 workflows)                            │
│  ├─ project_orchestrator     — Master state machine controller  │
│  ├─ project_scheduler        — Schedules/prioritizes projects   │
│  └─ worker_manager           — Health checks, failover          │
├─────────────────────────────────────────────────────────────────┤
│  TIER 2: ANALYSIS (8 workflows)                                 │
│  ├─ intake_validator         — File validation + normalization  │
│  ├─ chapter_extractor        — Chapter splitting                │
│  ├─ scene_extractor          — Scene segmentation               │
│  ├─ character_extractor      — Character extraction + DNA       │
│  ├─ world_extractor          — World extraction                 │
│  ├─ timeline_extractor       — Timeline construction            │
│  ├─ dialogue_extractor       — Dialogue extraction              │
│  └─ inconsistency_detector   — Contradictions + plot holes      │
├─────────────────────────────────────────────────────────────────┤
│  TIER 3: MEMORY + PLANNING (8 workflows)                        │
│  ├─ story_bible_builder      — Constructs story bible           │
│  ├─ character_bible_builder  — Locks character references       │
│  ├─ world_bible_builder      — Locks world references           │
│  ├─ timeline_bible_builder   — Constructs timeline              │
│  ├─ style_bible_builder      — Defines visual style             │
│  ├─ reference_generator      — Generates reference images       │
│  ├─ shot_planner             — Plans cinematic shots            │
│  └─ prompt_generator         — Generates structured prompts     │
├─────────────────────────────────────────────────────────────────┤
│  TIER 4: GENERATION (6 workflows)                               │
│  ├─ image_generator          — Dispatches image generation      │
│  ├─ audio_generator          — Dispatches TTS generation        │
│  ├─ music_suggester          — Suggests background music        │
│  ├─ quality_reviewer         — Reviews generated assets         │
│  ├─ repair_dispatcher        — Dispatches targeted repair       │
│  └─ asset_validator          — Validates asset completeness     │
├─────────────────────────────────────────────────────────────────┤
│  TIER 5: ASSEMBLY + DELIVERY (5 workflows)                      │
│  ├─ clip_assembler           — Assembles shot clips w/ animation│
│  ├─ video_renderer           — Renders final video              │
│  ├─ final_reviewer           — Final quality check              │
│  ├─ delivery_handler         — Sends to Telegram                │
│  └─ learning_engine          — Post-project analysis            │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Workflow Communication Protocol

```
WORKFLOW COMMUNICATION RULES:
─────────────────────────────

1. Workflows NEVER call each other directly
2. All communication is through PostgreSQL:
   a. Workflow A writes result to DB
   b. Workflow A transitions entity state
   c. Orchestrator detects state change
   d. Orchestrator triggers Workflow B

3. Each workflow:
   - Reads its input from DB
   - Processes independently
   - Writes output to DB
   - Transitions entity state
   - Returns (done)

4. The orchestrator:
   - Polls for projects in specific states
   - Determines next workflow to run
   - Triggers the workflow via n8n webhook
   - Monitors execution
   - Handles failures
   - Transitions project state

5. No workflow may:
   - Directly invoke another workflow
   - Modify project state (only scene/shot state within scope)
   - Skip quality gates
   - Bypass the orchestrator
   - Write to tables outside its scope
```

### 7.3 Workflow Execution Model

```
ORCHESTRATOR LOOP:
──────────────────

while project.state not in ['completed', 'failed', 'cancelled']:
    1. Read project current state
    2. Determine next phase based on state
    3. Check if prerequisites are met
    4. Transition project to "{phase}_running"
    5. Trigger appropriate workflow via n8n webhook
    6. Wait for workflow completion (webhook callback or DB poll)
    7. Read workflow result from DB
    8. If success: transition to "{phase}_complete"
    9. If failure: decide retry, repair, or escalate
    10. Log transition
    11. Send progress update to Telegram
    12. Continue loop
```

---

## 8. NODE-BY-NODE WORKFLOW SPECIFICATIONS

### 8.1 Workflow: `telegram_intake`

**Trigger:** Telegram webhook (file upload or text message)

```
Nodes:
──────

[1] Telegram Trigger
    - Type: n8n Telegram Trigger
    - Event: message (document or text)
    - Filter: allowed users only
    
[2] Input Router
    - Type: Switch
    - Conditions:
        - message has document → File Path
        - message has text → Text Path
        - /start command → Welcome Path
        - /status command → Status Path
        - /help command → Help Path

[3a] Welcome Handler (Welcome Path)
    - Type: Telegram Send Message
    - Message: "Welcome! Send me a novel (.txt) and I'll create a cinematic video."
    
[3b] Status Handler (Status Path)
    - Type: Code
    - Logic: Query DB for user's active projects
    - Output: formatted status message

[4] File Validator (File Path)
    - Type: HTTP Request + Code
    - Logic:
        - Check file size < 10MB
        - Check file extension .txt
        - Download file
        - Detect encoding (utf-8, latin-1, cp1252)
        - Count words
        - Validate minimum 50 words
        - Detect language (en/ar/mixed)

[5] Text Normalizer
    - Type: Code
    - Logic:
        - Normalize unicode
        - Fix line breaks
        - Remove excessive whitespace
        - Extract title (first line or first sentence)

[6] Project Creator
    - Type: PostgreSQL
    - Query: INSERT INTO cineos.core.projects (user_id, chat_id, state)
        VALUES ($user_id, $chat_id, 'created')
    - Returns: project_id

[7] Novel Creator
    - Type: PostgreSQL
    - Query: INSERT INTO cineos.core.novels (project_id, title, raw_text, cleaned_text, word_count, ...)
    - Returns: novel_id

[8] State Transition
    - Type: PostgreSQL
    - Query: UPDATE projects SET state = 'intake_complete'
    - Query: INSERT INTO state_transitions (entity_type='project', from_state='created', to_state='intake_complete')

[9] Progress Notification
    - Type: Telegram Send Message
    - Message: "Novel received: {title} ({word_count} words). Starting analysis..."

[10] Orchestrator Trigger
     - Type: HTTP Request
     - URL: n8n webhook for project_orchestrator
     - Body: { project_id: $project_id }
```

### 8.2 Workflow: `project_orchestrator`

**Trigger:** Webhook (from intake) or Cron (for polling stuck projects)

```
Nodes:
──────

[1] Trigger
    - Type: Webhook or Cron
    - Webhook: receives project_id
    - Cron: every 60 seconds, picks up stuck projects

[2] Project Loader
    - Type: PostgreSQL
    - Query: SELECT * FROM projects WHERE id = $project_id AND state NOT IN ('completed', 'failed', 'cancelled')

[3] State Router
    - Type: Switch
    - Conditions (match project.state):
        - intake_complete → Analysis Phase
        - analysis_complete → Reference Phase
        - reference_generation_complete → Planning Phase
        - shot_planning_complete → Generation Phase
        - quality_reviewing → Review Handler
        - repair_complete → Re-Review
        - assembled → Final Review
        - final_reviewing → Delivery Handler
        - delivered → Learning Phase
        - default → Error

[4a] Analysis Phase
    - Type: HTTP Request
    - URL: n8n webhook for chapter_extractor
    - Body: { project_id, novel_id }
    - On success: transition to analysis_complete

[4b] Reference Phase
    - Type: HTTP Request
    - URL: n8n webhook for reference_generator
    - Body: { project_id }
    - On success: transition to reference_generation_complete

[4c] Planning Phase
    - Type: HTTP Request
    - URL: n8n webhook for shot_planner
    - Body: { project_id }
    - On success: transition to shot_planning_complete

[4d] Generation Phase
    - Type: HTTP Request
    - URL: n8n webhook for image_generator + audio_generator
    - Body: { project_id }
    - On success: transition to quality_reviewing

[4e] Review Handler
    - Type: Code
    - Logic: Check review results
        - If all passed: transition to assembling, trigger clip_assembler
        - If some failed: transition to repair_running, trigger repair_dispatcher
        - If unrecoverable: transition to unrecoverable

[4f] Delivery Handler
    - Type: HTTP Request
    - URL: n8n webhook for delivery_handler
    - Body: { project_id }

[4g] Learning Phase
    - Type: HTTP Request
    - URL: n8n webhook for learning_engine
    - Body: { project_id }
    - On completion: transition to completed

[5] Progress Reporter
    - Type: Telegram Send Message
    - Message: "Phase {phase} complete. Progress: {progress}%"

[6] Error Handler
    - Type: Code
    - Logic:
        - Increment error_count
        - If error_count < max_retries: retry phase
        - If error_count >= max_retries: transition to failed
        - Notify user of failure

[7] Logger
    - Type: PostgreSQL
    - Query: INSERT INTO state_transitions, INSERT INTO events
```

### 8.3 Workflow: `chapter_extractor`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, novel_id

[2] Novel Loader
    - Type: PostgreSQL
    - Query: SELECT cleaned_text FROM novels WHERE id = $novel_id

[3] Chapter Splitter
    - Type: Code
    - Logic:
        - Regex patterns: "Chapter N", "CHAPTER N", "Ch. N", Arabic "الفصل"
        - Numbered sections with blank line separators
        - Fallback: split by major narrative breaks
    - Output: [{ chapter_number, title, text, word_count }]

[4] Chapter Persister
    - Type: PostgreSQL (Batch)
    - Query: INSERT INTO chapters (novel_id, chapter_number, title, text, word_count)
    - Returns: chapter_ids

[5] Transition
    - Type: PostgreSQL
    - Query: UPDATE projects SET state = 'analysis_complete', progress = 0.1
    - Query: INSERT INTO state_transitions

[6] Return
    - Type: Respond to Webhook
    - Body: { success: true, chapter_count: N }
```

### 8.4 Workflow: `scene_extractor`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Chapter Loader
    - Type: PostgreSQL
    - Query: SELECT * FROM chapters WHERE novel_id = $novel_id ORDER BY chapter_number

[3] Scene Segmentation Loop
    - Type: Split In Batches (per chapter)

[4] LLM Scene Analysis
    - Type: HTTP Request (Ollama API)
    - Endpoint: POST http://localhost:11434/api/generate
    - Prompt: "Analyze this chapter and identify all distinct scenes. For each scene, extract: location, time_of_day, characters_present, primary_emotion, conflict, importance, dialogue_present, action_present, summary"
    - Model: llama3.2
    - Response parsing: JSON extraction from LLM output

[5] Scene Validator
    - Type: Code
    - Logic:
        - Validate each scene has minimum text length
        - Validate location is not empty
        - Validate at least one character is present
        - Merge LLM analysis with regex fallback data

[6] Scene Persister
    - Type: PostgreSQL (Batch)
    - Query: INSERT INTO scenes (project_id, chapter_id, chapter_number, scene_number, full_text, summary, ...)
    - Query: INSERT INTO scene_characters (scene_id, character_id, role)

[7] Character Extraction (sub-workflow trigger)
    - Type: HTTP Request
    - URL: n8n webhook for character_extractor
    - Body: { project_id, all_scene_data }

[8] World Extraction (sub-workflow trigger)
    - Type: HTTP Request
    - URL: n8n webhook for world_extractor
    - Body: { project_id, all_scene_data }

[9] Timeline Extraction (sub-workflow trigger)
    - Type: HTTP Request
    - URL: n8n webhook for timeline_extractor
    - Body: { project_id, all_scenes, all_chapters }

[10] Dialogue Extraction (sub-workflow trigger)
     - Type: HTTP Request
     - URL: n8n webhook for dialogue_extractor
     - Body: { project_id, all_scenes }

[11] Inconsistency Detection (sub-workflow trigger)
     - Type: HTTP Request
     - URL: n8n webhook for inconsistency_detector
     - Body: { project_id }

[12] Merge Results
     - Type: Code
     - Logic: Wait for all extraction workflows to complete

[13] Transition
     - Type: PostgreSQL
     - Query: UPDATE projects SET state = 'analysis_complete', progress = 0.25
```

### 8.5 Workflow: `character_extractor`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, scene_data

[2] Character Candidate Extraction
    - Type: Code
    - Logic:
        - Regex: capitalized names near dialogue verbs
        - Regex: "he said", "she replied", character actions
        - Regex: titles + names ("King Aldric", "Princess Elara")
    - Output: list of candidate character names + evidence

[3] Character Deduplication
    - Type: Code
    - Logic:
        - Fuzzy matching (Levenshtein distance < 3)
        - Alias resolution ("the king" → "King Aldric")
        - Nickname matching

[4] LLM Character DNA Builder
    - Type: HTTP Request (Ollama)
    - Prompt: For each character, build comprehensive DNA:
        - Physical description, personality, relationships
        - Voice description, weapons, clothing
        - Personality traits, fears, desires
    - Response: structured JSON

[5] Evidence Consolidation
    - Type: Code
    - Logic:
        - Combine regex evidence with LLM analysis
        - Calculate confidence score
        - Mark inferred vs explicitly stated traits

[6] Character Bible Writer
    - Type: PostgreSQL
    - Query: INSERT INTO character_bibles (project_id, canonical_name, ...)
    - Query: Generate visual_prompt_positive from DNA fields

[7] Character Reference Trigger
    - Type: HTTP Request
    - URL: n8n webhook for reference_generator (character type)
    - Body: { character_id, character_bible_data }

[8] Transition
    - Type: PostgreSQL
    - Query: INSERT INTO state_transitions

[9] Return
    - Type: Respond to Webhook
    - Body: { character_count, characters: [{id, name, confidence}] }
```

### 8.6 Workflow: `world_extractor`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, scene_data

[2] Location Extraction
    - Type: Code
    - Logic:
        - Extract unique locations from scenes
        - Group by frequency
        - Identify primary vs secondary locations

[3] LLM World Builder
    - Type: HTTP Request (Ollama)
    - Prompt: "Based on these scenes, construct a comprehensive world bible covering: geography, architecture, technology_level, magic_system, culture, climate, visual_atmosphere, color_palette, lighting_style"
    - Response: structured JSON

[4] Visual Keyword Generator
    - Type: Code
    - Logic:
        - Build visual_keywords from world attributes
        - Build visual_prompt_positive from keywords
        - Build visual_prompt_negative (things NOT in this world)

[5] World Bible Writer
    - Type: PostgreSQL
    - Query: INSERT INTO world_bibles (project_id, ...)

[6] World Reference Trigger
    - Type: HTTP Request
    - URL: n8n webhook for reference_generator (world type)
    - Body: { world_bible_id, location_data }

[7] Transition
    - Type: PostgreSQL
```

### 8.7 Workflow: `reference_generator`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, reference_type, entity_id, entity_data

[2] Reference Type Router
    - Type: Switch
    - Cases:
        - character → Character Reference Pipeline
        - world → World Reference Pipeline
        - style → Style Reference Pipeline

[3] Character Reference Pipeline
    - Type: Sub-Flow
    - Logic:
        a. Build reference prompt from character_bible:
           "{character.visual_prompt_positive}, portrait, character sheet, 
            {style_bible.base_positive_prompt}"
        b. Dispatch to image_generator workflow
        c. Review generated reference
        d. If quality passed: save to character_references table
        e. If failed: retry with different seed/backend

[4] World Reference Pipeline
    - Type: Sub-Flow
    - Logic:
        a. Build reference prompt from world_bible:
           "{world.visual_prompt_positive}, {location_name}, environment concept art,
            {style_bible.base_positive_prompt}"
        b. Dispatch to image_generator workflow
        c. Review and save

[5] Style Reference Pipeline
    - Type: Sub-Flow
    - Logic:
        a. Generate color palette reference
        b. Generate mood reference
        c. Generate lighting reference
        d. Save all to style_references table

[6] Reference Validator
    - Type: Code
    - Logic:
        - Verify all required references exist
        - Verify quality scores above threshold
        - Report any missing references

[7] Transition
    - Type: PostgreSQL
    - Query: UPDATE project state
```

### 8.8 Workflow: `shot_planner`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Scene Loader
    - Type: PostgreSQL
    - Query: SELECT scenes.*, character_bibles, world_bible, style_bible, story_bible
             WHERE project_id = $project_id
             ORDER BY chapter_number, scene_number

[3] Shot Planning Loop
    - Type: Split In Batches (per scene)

[4] LLM Shot Planner
    - Type: HTTP Request (Ollama)
    - Prompt: """
        Plan cinematic shots for this scene.
        
        Scene: {scene.full_text}
        Characters present: {scene.characters}
        Character visual references: {character_bibles.visual_prompt_positive}
        World visual reference: {world_bible.visual_prompt_positive}
        Style: {style_bible.art_style}
        
        For each shot, specify:
        - shot_type (establishing/wide/medium/close_up/extreme_close_up/action)
        - duration_seconds (based on importance and pacing)
        - camera_angle
        - camera_movement
        - characters_in_shot
        - narration_text (what the narrator says during this shot)
        - transition_in/out
        
        Budget: critical scenes get 8-12 shots, normal scenes get 4-6, low importance get 2-3
        """
    - Response: structured JSON with shot array

[5] Shot Budget Enforcer
    - Type: Code
    - Logic:
        - Enforce minimum/maximum shots per scene
        - Enforce total project shot limit (max 1000)
        - Distribute budget based on scene importance

[6] Shot Persister
    - Type: PostgreSQL (Batch)
    - Query: INSERT INTO shots (scene_id, shot_number, shot_type, duration_seconds, ...)
    - Update scene.shots_planned state

[7] Prompt Generator (for each shot)
    - Type: Code
    - Logic:
        - Build positive_prompt from:
          shot.camera_angle + shot.characters_in_shot.descriptions +
          shot.location.description + style_bible.base_positive_prompt +
          character_bibles[chars_in_shot].visual_prompt_positive +
          world_bible.visual_prompt_positive
        - Build negative_prompt from:
          style_bible.base_negative_prompt +
          character_bibles[chars_in_shot].visual_prompt_negative +
          world_bible.visual_prompt_negative

[8] Prompt Persister
    - Type: PostgreSQL
    - Query: UPDATE shots SET positive_prompt, negative_prompt

[9] Transition
    - Type: PostgreSQL
    - Query: UPDATE project state to shot_planning_complete
```

### 8.9 Workflow: `image_generator`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id (generates all pending images)

[2] Pending Shots Loader
    - Type: PostgreSQL
    - Query: SELECT shots.*, scenes.* FROM shots
             JOIN scenes ON shots.scene_id = scenes.id
             WHERE scenes.project_id = $project_id
             AND shots.state = 'prompt_ready'
             ORDER BY scenes.chapter_number, scenes.scene_number, shots.shot_number

[3] Generation Loop
    - Type: Split In Batches (size: configurable concurrency)

[4] Backend Selector
    - Type: Code
    - Logic:
        - Query active workers and their capabilities
        - Select best worker for this task type
        - Fallback chain: local_gpu → remote_gpu → hf_inference → pollinations
        - Check worker health and load

[5] Image Generation Task Creator
    - Type: PostgreSQL
    - Query: INSERT INTO tasks (project_id, task_type='generate_image', payload={
        shot_id, positive_prompt, negative_prompt, 
        width, height, seed, backend, model
    })

[6] Task Dispatcher
    - Type: HTTP Request
    - URL: worker endpoint (selected worker's endpoint_url)
    - Body: task payload
    - Timeout: 120 seconds

[7] Task Result Handler
    - Type: Webhook (worker calls back)
    - Logic:
        - Receive generated image data
        - Save image to disk
        - Insert into generation.images table
        - Update shot state to image_generated
        - Update task state to completed

[8] Quality Gate (per image)
    - Type: HTTP Request
    - URL: quality_reviewer workflow
    - Body: { image_id, shot_id }

[9] Quality Result Handler
    - Type: Code
    - Logic:
        - If passed: mark shot.image_passed, proceed to audio
        - If failed: mark shot.image_failed, trigger repair

[10] Batch Complete Handler
     - Type: Code
     - Logic:
        - Count total, passed, failed
        - If all passed: transition project
        - If some failed: trigger repair_dispatcher
```

### 8.10 Workflow: `audio_generator`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Pending Audio Shots Loader
    - Type: PostgreSQL
    - Query: SELECT shots FROM shots
             JOIN scenes ON shots.scene_id = scenes.id
             WHERE scenes.project_id = $project_id
             AND shots.state IN ('image_passed', 'audio_pending')
             AND shots.narration_text IS NOT NULL

[3] TTS Backend Selector
    - Type: Code
    - Logic:
        - Priority: edge_tts → piper → espeak
        - Check backend health
        - Select voice based on narration_emotion and character voice_description

[4] Audio Generation Loop
    - Type: Split In Batches

[5] Audio Generation Task
    - Type: PostgreSQL + HTTP Request
    - Task: generate audio for shot
    - Payload: { shot_id, text, voice, emotion, speed, backend }

[6] Audio Result Handler
    - Type: Webhook
    - Logic:
        - Save audio file
        - Insert into generation.audio table
        - Measure duration
        - Update shot state

[7] Audio Duration Sync
    - Type: Code
    - Logic:
        - If audio duration > shot.duration: extend shot duration
        - If audio duration < shot.duration: add padding
        - Update shot.duration_seconds to match audio

[8] Transition
    - Type: PostgreSQL
```

### 8.11 Workflow: `quality_reviewer`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: entity_type, entity_id (can review image, audio, shot, scene, project)

[2] Entity Router
    - Type: Switch
    - Cases:
        - image → Image Review
        - audio → Audio Review
        - shot → Shot Review
        - scene → Scene Review
        - project → Project Review

[3] Image Review
    - Type: Sub-Flow
    - Logic:
        a. Load image from generation.images
        b. Load character_bibles for characters in shot
        c. Load world_bible
        d. Check character consistency:
           - Hair color matches character_bible.hair_color
           - Eye color matches character_bible.eye_color
           - Clothing matches character_bible.default_outfit
        e. Check world consistency:
           - Architecture matches world_bible.architectural_style
           - Atmosphere matches world_bible.visual_atmosphere
        f. Check composition:
           - Image is not blank/corrupted
           - Appropriate shot_type composition
        g. Check prompt alignment:
           - Key prompt elements present in image
        h. Calculate scores and overall
        i. Insert review record

[4] Audio Review
    - Type: Sub-Flow
    - Logic:
        a. Check audio file exists and is valid
        b. Check duration is reasonable
        c. Check file size (not silent, not corrupted)
        d. Calculate scores

[5] Shot Review
    - Type: Sub-Flow
    - Logic:
        a. Check image exists and passed
        b. Check audio exists and passed
        c. Check duration alignment (image and audio match)
        d. Calculate combined score

[6] Scene Review
    - Type: Sub-Flow
    - Logic:
        a. Check all shots in scene are ready
        b. Check narrative flow between shots
        c. Check character consistency across shots
        d. Check world consistency across shots
        e. Calculate scene score

[7] Project Review
    - Type: Sub-Flow
    - Logic:
        a. Check all scenes are assembled
        b. Overall quality metrics
        c. Character consistency across all scenes
        d. World consistency across all scenes
        e. Narrative fidelity
        f. Calculate overall project score

[8] Decision Maker
    - Type: Code
    - Logic:
        - Load thresholds from quality.thresholds
        - Compare scores against thresholds
        - Decision: pass, fail (repairable), fail (unrecoverable)

[9] Transition
    - Type: PostgreSQL
    - Record: review result, transition entity state
```

### 8.12 Workflow: `repair_dispatcher`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, failed_items[]

[2] Failed Items Loader
    - Type: PostgreSQL
    - Query: SELECT * FROM quality.reviews
             WHERE project_id = $project_id AND passed = FALSE
             AND entity_id IN ($failed_item_ids)

[3] Repair Strategy Selector
    - Type: Code
    - Logic per failed item:
        - Low prompt alignment → Regenerate prompt (adjust keywords)
        - Low character consistency → Add character reference to prompt
        - Low world consistency → Add world reference to prompt
        - Low composition → Change shot_type or camera_angle
        - Backend failure → Switch to different backend
        - Low overall score → Full regeneration with enhanced prompt

[4] Repair Attempts Check
    - Type: PostgreSQL
    - Query: SELECT COUNT(*) FROM repairs WHERE original_entity_id = $entity_id
    - Logic: If attempts >= max_retries → escalate to unrecoverable

[5] Repair Task Creator
    - Type: PostgreSQL
    - Query: INSERT INTO quality.repairs (...)
    - Query: INSERT INTO tasks (task_type = repair_strategy)

[6] Repair Execution Loop
    - Type: Split In Batches
    - Dispatch repair tasks to appropriate workers

[7] Repair Result Handler
    - Type: Webhook
    - Logic:
        - Save repaired asset
        - Run quality review on repaired asset
        - Update repair record with post_repair_score
        - If improved: mark success
        - If not improved: mark failure

[8] Transition
    - Type: PostgreSQL
    - Query: UPDATE project state to repair_complete
```

### 8.13 Workflow: `clip_assembler`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Shot Loader
    - Type: PostgreSQL
    - Query: SELECT shots, images, audio FROM shots
             JOIN scenes ON shots.scene_id = scenes.id
             LEFT JOIN images ON images.shot_id = shots.id AND images.is_selected = TRUE
             LEFT JOIN audio ON audio.shot_id = shots.id AND audio.is_selected = TRUE
             WHERE scenes.project_id = $project_id
             ORDER BY scenes.chapter_number, scenes.scene_number, shots.shot_number

[3] Animation Planner
    - Type: Code
    - Logic:
        - Assign animation type based on shot_type:
          establishing → ken_burns_zoom_in
          wide → ken_burns_pan
          medium → subtle_breathing
          close_up → ken_burns_zoom_in (slow)
          action → ken_burns_pan (fast)
          insert → ken_burns_zoom_out
        - Calculate animation parameters (zoom factor, pan speed)

[4] Clip Assembly Loop
    - Type: Split In Batches

[5] Clip Renderer (Task)
    - Type: PostgreSQL + HTTP Request
    - Task: render_clip
    - Payload: {
        image_path, audio_path,
        duration_seconds,
        animation_type, animation_params,
        transition_in, transition_out,
        width, height, fps
    }
    - Worker: CPU or GPU worker with FFmpeg

[6] Clip Result Handler
    - Type: Webhook
    - Logic:
        - Save clip to video_clips table
        - Update shot state to assembled

[7] Video Concatenation
    - Type: HTTP Request
    - URL: video_renderer workflow
    - Body: { project_id, clip_paths: [...] }

[8] Transition
    - Type: PostgreSQL
```

### 8.14 Workflow: `video_renderer`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, clip_paths[]

[2] FFmpeg Command Builder
    - Type: Code
    - Logic:
        - Build FFmpeg concat command
        - Add global video settings (resolution, fps, codec)
        - Add audio mixing (narration + optional background music)
        - Add subtitle overlay (if enabled)
        - Generate concat list file

[3] Render Task Dispatcher
    - Type: HTTP Request
    - URL: worker endpoint
    - Payload: { ffmpeg_command, clip_paths, output_path }
    - Timeout: 600 seconds (10 minutes)

[4] Render Monitor
    - Type: Polling or Webhook
    - Logic:
        - Monitor render progress
        - Handle timeout
        - Handle failure

[5] Render Result Handler
    - Type: Code
    - Logic:
        - Verify output file exists
        - Get file size, duration, resolution
        - Insert into final_videos table

[6] Final Review Trigger
    - Type: HTTP Request
    - URL: final_reviewer workflow
    - Body: { project_id, video_id }

[7] Transition
    - Type: PostgreSQL
```

### 8.15 Workflow: `final_reviewer`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id, video_id

[2] Video Metadata Loader
    - Type: PostgreSQL + Code
    - Logic:
        - Load video metadata (duration, resolution, etc.)
        - Load all scene reviews
        - Load all shot reviews
        - Load all image reviews
        - Load all audio reviews

[3] Character Consistency Check
    - Type: Code
    - Logic:
        - Check character reference images were used consistently
        - Check character prompt fragments were included
        - Score: percentage of shots with consistent character references

[4] World Consistency Check
    - Type: Code
    - Logic:
        - Check world reference images were used
        - Check world prompt fragments were included
        - Score: percentage of shots with consistent world references

[5] Audio-Video Sync Check
    - Type: Code
    - Logic:
        - Check narration covers all shots
        - Check audio durations match video durations
        - Score: sync percentage

[6] Narrative Fidelity Check
    - Type: Code
    - Logic:
        - Check all scenes are represented
        - Check all critical scenes are included
        - Check story arc is preserved
        - Score: coverage percentage

[7] Overall Score Calculator
    - Type: Code
    - Formula:
        overall = (character_consistency * 0.25) +
                  (world_consistency * 0.20) +
                  (audio_sync * 0.20) +
                  (narrative_fidelity * 0.25) +
                  (avg_scene_quality * 0.10)

[8] Decision
    - Type: Code
    - Logic:
        - If overall >= auto_approve_threshold (0.85): auto-approve
        - If overall >= min_overall_quality (0.60): approve
        - If overall >= hard_failure_threshold (0.20): repair
        - If overall < hard_failure_threshold: reject

[9] Transition
    - Type: PostgreSQL
    - Query: UPDATE final_videos SET state, overall_quality_score, ...
```

### 8.16 Workflow: `delivery_handler`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Video Loader
    - Type: PostgreSQL
    - Query: SELECT final_videos.* FROM final_videos
             WHERE project_id = $project_id AND state = 'approved'

[3] Report Generator
    - Type: Code
    - Logic:
        - Build delivery report:
          - Total duration
          - Scene count, shot count
          - Quality scores breakdown
          - Backend usage summary
          - Processing time
          - File size

[4] Video Sender
    - Type: Telegram Send Video
    - Video: video_path
    - Caption: delivery report

[5] Progress Sender
    - Type: Telegram Send Message
    - Message: "Project complete! Quality: {score}/1.0. Duration: {duration}s"

[6] Archive
    - Type: PostgreSQL
    - Query: UPDATE projects SET state = 'delivered', completed_at = NOW()

[7] Learning Trigger
    - Type: HTTP Request
    - URL: n8n webhook for learning_engine
    - Body: { project_id }
```

### 8.17 Workflow: `learning_engine`

```
Nodes:
──────

[1] Trigger
    - Type: Webhook
    - Receives: project_id

[2] Project Data Loader
    - Type: PostgreSQL
    - Query: Load all project data: scenes, shots, images, audio, reviews, repairs, workers used

[3] Performance Analyzer
    - Type: Code
    - Logic:
        - Calculate actual vs estimated metrics
        - Identify slowest phases
        - Identify most-used backends
        - Identify repair hotspots
        - Identify highest/lowest quality shots

[4] Prompt Performance Analyzer
    - Type: Code
    - Logic:
        - Correlate prompt elements with quality scores
        - Identify which prompt patterns produce best results
        - Identify which shot_types have highest quality
        - Identify character/world prompt effectiveness

[5] Backend Performance Analyzer
    - Type: Code
    - Logic:
        - Compare backend success rates
        - Compare backend quality scores
        - Compare backend speed
        - Update backend preference rankings

[6] Lessons Extractor
    - Type: HTTP Request (Ollama)
    - Prompt: "Based on this project's performance data, extract lessons learned and recommendations for future projects"
    - Response: structured JSON

[7] Threshold Tuner
    - Type: Code
    - Logic:
        - If quality consistently high: consider raising thresholds
        - If repair rate high: consider lowering thresholds or improving prompts
        - Adjust based on learning data from multiple projects

[8] Learning Data Persister
    - Type: PostgreSQL
    - Query: INSERT INTO learning_data (project_id, ...)

[9] System Config Update
    - Type: PostgreSQL
    - Query: UPDATE system_config with learned preferences

[10] Transition
     - Type: PostgreSQL
     - Query: UPDATE projects SET state = 'completed'
```

---

## 9. QUALITY AND REPAIR PIPELINE

### 9.1 Quality Gate Architecture

```
QUALITY GATES (mandatory, sequential):
──────────────────────────────────────

Gate 1: Analysis Validation
  → All chapters extracted
  → All scenes have minimum text
  → All characters have names
  → World has minimum attributes
  → Timeline is internally consistent

Gate 2: Reference Validation
  → Every character has a reference image
  → Every major location has a reference image
  → Style bible is defined
  → Visual keywords are populated

Gate 3: Shot Plan Validation
  → Every scene has shots
  → Shot types are appropriate for scene importance
  → Shot durations are reasonable
  → All prompts are populated
  → Character references included in relevant prompts

Gate 4: Asset Validation
  → Every shot has a generated image (quality > threshold)
  → Every shot has generated audio (quality > threshold)
  → No corrupted files
  → No placeholder images

Gate 5: Assembly Validation
  → All clips are rendered
  → Video file is valid
  → Audio is synced
  → Duration matches expected

Gate 6: Final Review
  → Character consistency across video
  → World consistency across video
  → Narrative fidelity
  → Overall quality score
```

### 9.2 Repair Strategy Matrix

```
┌─────────────────────┬──────────────────────────────────────┬────────────────────┐
│ FAILURE TYPE        │ REPAIR STRATEGY                       │ MAX ATTEMPTS       │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Prompt alignment    │ 1. Add missing keywords              │ 3                  │
│                     │ 2. Simplify prompt                   │                    │
│                     │ 3. Change shot_type                  │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Character           │ 1. Add character reference image     │ 3                  │
│ consistency         │ 2. Expand character prompt fragment   │                    │
│                     │ 3. Regenerate with reference image   │                    │
│                     │ 4. Switch to character-focused model  │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ World               │ 1. Add world reference image         │ 3                  │
│ consistency         │ 2. Expand world prompt fragment      │                    │
│                     │ 3. Regenerate with reference image   │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Composition         │ 1. Change camera_angle               │ 2                  │
│                     │ 2. Change shot_type                  │                    │
│                     │ 3. Add composition hints to prompt   │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Audio quality       │ 1. Switch TTS backend                │ 3                  │
│                     │ 2. Adjust speed/pitch                │                    │
│                     │ 3. Split long text into chunks       │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Backend failure     │ 1. Retry same backend                │ 2                  │
│                     │ 2. Switch to fallback backend        │                    │
│                     │ 3. Switch to remote worker           │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Audio-video sync    │ 1. Adjust shot duration to match     │ 2                  │
│                     │ 2. Re-render clip                     │                    │
├─────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Overall quality     │ 1. Repair individual failed shots    │ 2                  │
│                     │ 2. Regenerate all low-score shots    │                    │
│                     │ 3. Escalate to manual review         │                    │
└─────────────────────┴──────────────────────────────────────┴────────────────────┘
```

### 9.3 Review Scoring System

```python
# Image Quality Score Components (0.0 to 1.0)
image_score = (
    prompt_alignment * 0.30 +       # Does the image match the prompt?
    character_consistency * 0.25 +   # Do characters look correct?
    world_consistency * 0.20 +       # Does the world look right?
    composition * 0.15 +            # Is it well-composed?
    technical_quality * 0.10         # Resolution, artifacts, etc.
)

# Audio Quality Score Components (0.0 to 1.0)
audio_score = (
    naturalness * 0.30 +            # Does it sound natural?
    clarity * 0.25 +                # Is the speech clear?
    emotion_match * 0.25 +          # Does emotion match narration?
    duration_fit * 0.20             # Does duration match shot?
)

# Scene Quality Score Components (0.0 to 1.0)
scene_score = (
    avg_shot_quality * 0.40 +       # Average quality of all shots
    narrative_flow * 0.20 +         # Do shots tell the story?
    character_continuity * 0.20 +   # Consistent character appearance
    pacing * 0.10 +                 # Shot durations appropriate
    transitions * 0.10              # Smooth transitions between shots
)

# Final Video Score Components (0.0 to 1.0)
final_score = (
    character_consistency * 0.25 +  # Consistent across entire video
    world_consistency * 0.20 +     # Consistent across entire video
    narrative_fidelity * 0.25 +    # Faithful to novel
    audio_video_sync * 0.20 +     # Narration matches visuals
    production_quality * 0.10      # Technical quality
)
```

---

## 10. VOICE, MUSIC, ANIMATION, AND RENDER PIPELINE

### 10.1 Voice Pipeline

```
VOICE GENERATION FLOW:
──────────────────────

1. Narration Text Preparation
   - shot.narration_text loaded from shot_planner output
   - Emotion tags added based on scene.primary_emotion
   - Pause markers inserted at punctuation
   - Character dialogue marked for voice variation

2. Voice Selection
   - Base voice: configurable per project (default: English male/female)
   - Character voices: derived from character_bible.voice_description
   - Emotion mapping: scene emotion → voice emotion parameter
   - Voice variants: different pitch/speed for different characters

3. TTS Backend Selection
   - Priority: edge_tts (neural quality) → piper (local) → espeak (fallback)
   - Edge TTS: 75+ languages, emotion-aware
   - Piper: local ONNX, CPU-friendly, consistent quality
   - espeak: last resort, low quality but guaranteed

4. Post-Processing
   - Normalize audio levels
   - Add silence padding (0.5s before, 0.3s after)
   - Optional: add subtle reverb for atmosphere
   - Split long narrations into segments

5. Quality Check
   - File exists and is valid WAV/MP3
   - Duration > 0.5 seconds
   - File size > 1KB (not silent)
   - Duration matches shot duration (±20%)
```

### 10.2 Music Suggestion Pipeline

```
MUSIC SUGGESTION FLOW:
──────────────────────

1. Scene Music Analysis
   - Analyze scene.emotion → mood classification
   - Analyze scene.importance → intensity level
   - Analyze scene.conflict → tension level
   - Analyze scene.pacing → tempo requirement

2. Music Profile Generation
   - Map mood to music genre/style:
     - battle → epic orchestral, fast tempo
     - romance → soft piano, slow tempo
     - mystery → ambient, medium tempo
     - triumph → brass fanfare, moderate tempo
     - sadness → solo strings, slow tempo
   - Map intensity to volume/dynamics
   - Map tension to dissonance/harmony

3. Background Music Track Selection
   - Use royalty-free music library (if available)
   - Or: generate ambient background using music generation model
   - Or: provide music metadata for user to source
   - Default: no background music (narration only)

4. Audio Mixing
   - Narration: primary (volume 1.0)
   - Background music: secondary (volume 0.15-0.30)
   - Crossfade between scenes
   - Duck music during narration
```

### 10.3 Animation Pipeline

```
ANIMATION TYPES:
────────────────

1. Ken Burns Zoom In
   - Start: 100% crop
   - End: 115% crop (centered on focal point)
   - Duration: shot.duration_seconds
   - Easing: ease-in-out
   - Focal point: based on shot_type (face for close_up, horizon for establishing)

2. Ken Burns Zoom Out
   - Start: 115% crop
   - End: 100% crop
   - Reveals context gradually

3. Ken Burns Pan
   - Start: left third of image
   - End: right third of image (or vice versa)
   - Speed: based on shot pacing
   - Direction: left-to-right for progression, right-to-left for regression

4. Parallax Effect
   - Split image into layers (foreground, midground, background)
   - Move layers at different speeds
   - Creates depth illusion
   - Best for establishing shots

5. Subtle Breathing
   - Very slight zoom in/out (100% → 102% → 100%)
   - Creates "alive" feeling for static shots
   - Good for medium shots, close-ups

6. Cross-Dissolve Transition
   - Blend between two shots
   - Duration: transition_duration_ms
   - Easing: linear or ease-in-out

7. Cut (Default)
   - Instant transition
   - No blending
   - Default for action scenes

ANIMATION PARAMETER CALCULATION:
────────────────────────────────

For each shot:
  animation_type = determine_from_shot_type(shot.shot_type)
  focal_point = determine_focal_point(shot.characters_in_shot, shot.shot_type)
  zoom_factor = calculate_zoom_factor(shot.duration_seconds, shot.importance)
  pan_speed = calculate_pan_speed(shot.duration_seconds, shot.pacing)
```

### 10.4 Render Pipeline

```
RENDER FLOW:
────────────

1. Clip Rendering (per shot)
   Input: image + audio + animation_params
   Process:
     a. Apply animation to image (Ken Burns, parallax, etc.)
     b. Overlay audio track
     c. Add transition effects (if applicable)
     d. Render to video clip (H.264, same resolution as image)
   Output: individual .mp4 clip

2. Concatenation
   Input: all clips in order
   Process:
     a. Build FFmpeg concat list
     b. Apply global video settings
     c. Concatenate all clips
   Output: single .mp4 file

3. Audio Mixing
   Input: concatenated video + background music (optional)
   Process:
     a. Mix narration audio
     b. Add background music (if enabled)
     c. Apply volume normalization
     d. Apply audio codec (AAC)
   Output: final video with mixed audio

4. Post-Processing
   Input: final video
   Process:
     a. Add subtitle overlay (optional)
     b. Apply color grading (from style_bible)
     c. Add opening title card (optional)
     d. Add ending credits (optional)
     e. Final encode pass
   Output: deliverable video

FFmpeg COMMAND TEMPLATES:
─────────────────────────

# Clip rendering (with Ken Burns zoom)
ffmpeg -loop 1 -i {image} -i {audio} \
  -filter_complex "[0:v]zoompan=z='min(zoom+0.001,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}[v]" \
  -map "[v]" -map 1:a \
  -c:v libx264 -preset medium -crf 18 \
  -c:a aac -b:a 192k \
  -t {duration} \
  -y {output}

# Concatenation
ffmpeg -f concat -safe 0 -i {concat_list} \
  -c:v libx264 -preset medium -crf 18 \
  -c:a aac -b:a 192k \
  -y {output}

# Final post-processing
ffmpeg -i {input} \
  -vf "eq=brightness=0.02:contrast=1.1:saturation=1.05" \
  -c:v libx264 -preset slow -crf 16 \
  -c:a aac -b:a 256k \
  -movflags +faststart \
  -y {output}
```

---

## 11. REMOTE EXECUTION LAYER

### 11.1 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATION NODE                            │
│                                                                  │
│  n8n Orchestrator                                                │
│       │                                                          │
│       ├── Task Queue (PostgreSQL)                                │
│       │   cineos.execution.tasks                                 │
│       │                                                          │
│       ├── Worker Registry (PostgreSQL)                           │
│       │   cineos.execution.workers                               │
│       │                                                          │
│       └── Result Collector                                       │
│           (Webhook endpoints for worker callbacks)               │
│                                                                  │
└───────────┬──────────────────┬──────────────────┬────────────────┘
            │                  │                  │
     ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │  LOCAL      │  │  REMOTE     │  │  REMOTE     │
     │  WORKER     │  │  GPU WORKER │  │  CPU WORKER │
     │             │  │             │  │             │
     │ Image Gen   │  │ Image Gen   │  │ TTS         │
     │ TTS         │  │ Super-Res   │  │ Rendering   │
     │ Rendering   │  │ Quality     │  │ Quality     │
     │ Quality     │  │ Review      │  │ Review      │
     └─────────────┘  └─────────────┘  └─────────────┘
```

### 11.2 Worker Protocol

```
WORKER REGISTRATION:
────────────────────

1. Worker starts and registers with orchestrator
2. Worker provides:
   - Name, type, capabilities
   - Hardware specs (GPU model, VRAM, CPU cores, RAM)
   - Supported backends
   - Endpoint URL
   - Max concurrent tasks
3. Orchestrator stores in workers table
4. Worker sends heartbeat every 30 seconds
5. Orchestrator marks workers offline if heartbeat missed

TASK DISPATCH:
──────────────

1. Orchestrator creates task in tasks table
2. Orchestrator selects worker based on:
   - Worker type matches task type
   - Worker status is 'idle' or 'busy' (under capacity)
   - Worker priority (higher priority workers preferred)
   - Worker success rate (prefer reliable workers)
3. Orchestrator assigns task to worker
4. Worker polls for assigned tasks (or receives push notification)
5. Worker executes task
6. Worker reports result via webhook
7. Orchestrator updates task status and saves result

FAILOVER:
─────────

1. Worker heartbeat timeout → mark offline
2. Pending tasks on offline worker → reassign to next available worker
3. If no workers available → queue task, retry when worker comes online
4. Maximum failover attempts: 3
5. After 3 failovers → escalate to user (notify via Telegram)

WORKER TYPES:
─────────────

1. gpu_image_worker
   - Capabilities: image generation (SDXL, FLUX, Animagine)
   - Hardware: NVIDIA GPU with 8GB+ VRAM
   - Software: Python, PyTorch, diffusers, ComfyUI

2. cpu_tts_worker
   - Capabilities: text-to-speech (Edge TTS, Piper, espeak)
   - Hardware: Any CPU
   - Software: Python, edge-tts, piper-tts

3. cpu_render_worker
   - Capabilities: video rendering (FFmpeg, MoviePy)
   - Hardware: Any CPU with 4GB+ RAM
   - Software: FFmpeg, Python, MoviePy

4. vision_review_worker
   - Capabilities: quality review (CLIP, InsightFace)
   - Hardware: CPU or GPU
   - Software: Python, transformers, insightface

5. super_resolution_worker
   - Capabilities: image upscaling (Real-ESRGAN, ESRGAN)
   - Hardware: NVIDIA GPU with 4GB+ VRAM
   - Software: Python, Real-ESRGAN
```

### 11.3 Worker Selection Algorithm

```python
def select_worker(task_type: str, task_priority: int) -> Worker:
    candidates = db.query(
        "SELECT * FROM workers WHERE "
        "worker_type = %s AND status IN ('idle', 'busy') AND enabled = TRUE "
        "AND (SELECT COUNT(*) FROM tasks WHERE assigned_worker_id = workers.id AND state = 'running') < max_concurrent_tasks"
        "ORDER BY priority ASC, success_rate DESC, avg_task_duration_ms ASC",
        task_type
    )
    
    if not candidates:
        # No workers available, queue for later
        return None
    
    # Prefer local worker if available and not overloaded
    local = [w for w in candidates if w.host == 'localhost']
    if local and local[0].current_load < 0.8:
        return local[0]
    
    # Otherwise, pick best remote worker
    return candidates[0]
```

---

## 12. DEPLOYMENT STRUCTURE

### 12.1 Docker Compose Architecture

```yaml
# docker-compose.yml
version: '3.8'

services:
  # ── Orchestration ──────────────────
  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=cineos
      - DB_POSTGRESDB_USER=${DB_USER}
      - DB_POSTGRESDB_PASSWORD=${DB_PASSWORD}
      - WEBHOOK_URL=http://localhost:5678
    volumes:
      - n8n_data:/home/node/.n8n
      - ./workflows:/home/node/workflows
    depends_on:
      - postgres
      - redis

  # ── Database ───────────────────────
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=cineos
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql

  # ── Queue / Cache ──────────────────
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  # ── Telegram Bot ───────────────────
  telegram_bot:
    build:
      context: .
      dockerfile: Dockerfile.bot
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - N8N_WEBHOOK_URL=http://n8n:5678/webhook
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
    depends_on:
      - n8n
      - postgres

  # ── Local Worker ───────────────────
  local_worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - WORKER_TYPE=local_all
      - WORKER_NAME=local_worker
      - ORCHESTRATOR_URL=http://n8n:5678
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
      - OLLAMA_HOST=http://host.docker.internal:11434
    volumes:
      - worker_data:/app/data
      - ./generated:/app/generated
    depends_on:
      - postgres
      - n8n
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    profiles:
      - gpu

  # ── CPU Worker ─────────────────────
  cpu_worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - WORKER_TYPE=cpu_all
      - WORKER_NAME=cpu_worker
      - ORCHESTRATOR_URL=http://n8n:5678
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
    volumes:
      - worker_data:/app/data
      - ./generated:/app/generated
    depends_on:
      - postgres
      - n8n

volumes:
  n8n_data:
  postgres_data:
  redis_data:
  worker_data:
```

### 12.2 Directory Structure

```
cineos/
├── docker-compose.yml
├── .env                          # Secrets (not committed)
├── .env.example                  # Template
├── .gitignore
│
├── sql/
│   ├── init.sql                  # Schema creation
│   ├── migrations/               # Alembic-style migrations
│   │   ├── 001_initial.sql
│   │   ├── 002_add_learning.sql
│   │   └── ...
│   └── seed/
│       └── default_config.sql    # Default system_config values
│
├── n8n/
│   ├── workflows/                # n8n workflow JSON exports
│   │   ├── 01_telegram_intake.json
│   │   ├── 02_project_orchestrator.json
│   │   ├── 03_chapter_extractor.json
│   │   ├── 04_scene_extractor.json
│   │   ├── 05_character_extractor.json
│   │   ├── 06_world_extractor.json
│   │   ├── 07_timeline_extractor.json
│   │   ├── 08_dialogue_extractor.json
│   │   ├── 09_inconsistency_detector.json
│   │   ├── 10_story_bible_builder.json
│   │   ├── 11_character_bible_builder.json
│   │   ├── 12_world_bible_builder.json
│   │   ├── 13_timeline_bible_builder.json
│   │   ├── 14_style_bible_builder.json
│   │   ├── 15_reference_generator.json
│   │   ├── 16_shot_planner.json
│   │   ├── 17_prompt_generator.json
│   │   ├── 18_image_generator.json
│   │   ├── 19_audio_generator.json
│   │   ├── 20_music_suggester.json
│   │   ├── 21_quality_reviewer.json
│   │   ├── 22_repair_dispatcher.json
│   │   ├── 23_asset_validator.json
│   │   ├── 24_clip_assembler.json
│   │   ├── 25_video_renderer.json
│   │   ├── 26_final_reviewer.json
│   │   ├── 27_delivery_handler.json
│   │   ├── 28_learning_engine.json
│   │   ├── 29_project_scheduler.json
│   │   └── 30_worker_manager.json
│   └── credentials/              # n8n encrypted credentials
│
├── workers/
│   ├── base_worker.py            # Base worker class
│   ├── image_worker.py           # Image generation worker
│   ├── tts_worker.py             # TTS worker
│   ├── render_worker.py          # Video render worker
│   ├── review_worker.py          # Quality review worker
│   └── super_resolution_worker.py
│
├── bot/
│   ├── main.py                   # Telegram bot entry point
│   ├── handlers.py               # Message handlers
│   ├── keyboards.py              # Telegram keyboards
│   └── formatters.py             # Message formatters
│
├── backends/
│   ├── base.py                   # Abstract backends
│   ├── image/
│   │   ├── local_gpu.py
│   │   ├── pollinations.py
│   │   ├── hf_inference.py
│   │   ├── cloudflare.py
│   │   └── manager.py
│   └── audio/
│       ├── edge_tts.py
│       ├── piper.py
│       ├── espeak.py
│       └── manager.py
│
├── config/
│   ├── config.yaml               # System configuration
│   └── config.example.yaml
│
├── tests/
│   ├── test_state_machine.py
│   ├── test_workflows.py
│   ├── test_backends.py
│   ├── test_quality.py
│   └── test_integration.py
│
├── scripts/
│   ├── setup.sh                  # Initial setup
│   ├── start.sh                  # Start all services
│   ├── stop.sh                   # Stop all services
│   ├── migrate.sh                # Run database migrations
│   ├── import_workflows.sh       # Import n8n workflows
│   └── health_check.sh           # Check all services
│
├── generated/                    # Generated assets (gitignored)
│   ├── images/
│   ├── audio/
│   ├── video/
│   └── temp/
│
├── logs/
│   ├── n8n/
│   ├── bot/
│   ├── workers/
│   └── pipeline.log
│
└── docs/
    ├── architecture/
    │   ├── 01-system-architecture.md
    │   ├── 02-workflow-specifications.md
    │   └── ...
    ├── api/
    └── deployment/
```

### 12.3 Resource Requirements

```
MINIMUM (Weak Machine):
───────────────────────
- n8n: 512MB RAM
- PostgreSQL: 256MB RAM
- Redis: 64MB RAM
- Bot: 128MB RAM
- CPU Worker: 1GB RAM
- Total: ~2GB RAM, 2 CPU cores
- Heavy tasks dispatched to remote workers

RECOMMENDED (Moderate Machine):
───────────────────────────────
- n8n: 1GB RAM
- PostgreSQL: 1GB RAM
- Redis: 128MB RAM
- Bot: 256MB RAM
- Local Worker: 4GB RAM
- Total: ~6.5GB RAM, 4 CPU cores
- Optional: 1 GPU with 8GB VRAM

PRODUCTION (Powerful Machine):
──────────────────────────────
- n8n: 2GB RAM
- PostgreSQL: 4GB RAM
- Redis: 256MB RAM
- Bot: 512MB RAM
- GPU Worker: 8GB RAM + GPU
- CPU Worker: 4GB RAM
- Total: ~19GB RAM, 8 CPU cores, 1 GPU

REMOTE WORKERS (Additional):
────────────────────────────
- GPU Worker: 8GB+ RAM, NVIDIA GPU 8GB+ VRAM
- CPU Worker: 4GB+ RAM, 4+ CPU cores
- Can be added incrementally
- Auto-discovered by orchestrator
```

---

## 13. FINAL DELIVERABLES — IMPLEMENTATION PHASES

### Phase 1: Foundation (Week 1-2)
- PostgreSQL schema creation and migration system
- n8n workflow template structure
- Telegram bot → n8n webhook bridge
- Project state machine implementation
- Basic orchestrator workflow
- Worker registration protocol

### Phase 2: Analysis Engine (Week 3-4)
- Chapter extractor workflow
- Scene extractor workflow
- Character extractor workflow
- World extractor workflow
- Timeline extractor workflow
- Dialogue extractor workflow
- Inconsistency detector workflow

### Phase 3: Memory System (Week 5-6)
- Story bible builder workflow
- Character bible builder workflow
- World bible builder workflow
- Timeline bible builder workflow
- Style bible builder workflow
- Reference generator workflow

### Phase 4: Planning Engine (Week 7-8)
- Shot planner workflow
- Prompt generator workflow
- Shot budget optimizer
- Camera angle calculator
- Animation type selector

### Phase 5: Generation Engine (Week 9-10)
- Image generator workflow + backend integration
- Audio generator workflow + TTS backend integration
- Music suggester workflow
- Quality reviewer workflow
- Repair dispatcher workflow

### Phase 6: Assembly Engine (Week 11-12)
- Clip assembler workflow
- Video renderer workflow
- Animation pipeline
- FFmpeg integration
- Final reviewer workflow

### Phase 7: Delivery + Learning (Week 13-14)
- Delivery handler workflow
- Learning engine workflow
- Progress notification system
- User feedback integration

### Phase 8: Remote Execution (Week 15-16)
- Remote worker framework
- Worker health monitoring
- Task queue optimization
- Failover logic
- Performance tuning

### Phase 9: Polish + Testing (Week 17-18)
- End-to-end integration testing
- Load testing with long novels
- Error injection testing
- Recovery testing
- Performance benchmarking
- Documentation completion

---

## 14. CRITICAL INVARIANTS

These rules are NEVER violated:

1. **Database is truth.** No workflow may assume state not backed by a database record.

2. **State transitions are atomic.** A state change and its audit record are written in one transaction.

3. **No workflow bypasses the orchestrator.** The orchestrator is the only entity that may trigger project-level state transitions.

4. **References before generation.** Character and world references MUST exist before any scene is generated.

5. **Quality gates are mandatory.** No asset proceeds to the next phase without passing its quality gate.

6. **Partial repair before regeneration.** The system always attempts to repair a failed asset before regenerating it from scratch.

7. **Every action is logged.** Every state change, every generation, every review is recorded in the audit trail.

8. **Workers are replaceable.** No worker is special. Any worker of the same type can replace any other.

9. **Prompts are derived, not authoritative.** Prompts are generated from bibles. If a prompt produces bad results, the fix is in the bible or the prompt generator, not in storing a "corrected" prompt.

10. **The system is restartable at any point.** If n8n crashes, all project state is in PostgreSQL. On restart, the orchestrator picks up where it left off by checking project states.

---

*End of Part 1 — System Architecture Specification*
