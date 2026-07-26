# PART 2 — COMPLETE SYSTEM ARCHITECTURE, LAYER MODEL, DEPLOYMENT TOPOLOGY, AND REMOTE EXECUTION DESIGN

## CineOS — Complete Layer-by-Layer Architecture

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

The platform is a modular, distributed production system orchestrated entirely by n8n.

**Architecture Pattern:** Strict Layered Architecture with Database-Mediated Communication

**Core Rules:**
- Each layer has a single responsibility
- Each layer communicates through PostgreSQL, REST APIs, explicit events, and the central state machine
- No layer depends on another layer's internal implementation
- Every layer is replaceable
- Every layer exposes a clearly defined interface
- Every layer is observable
- Every layer is recoverable

---

## 2. HIGH-LEVEL TOPOLOGY

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                     │
│                        Telegram User Interface                              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                         LAYER 1: TELEGRAM INTAKE                            │
│  Receive novels, commands, validate, create project, trigger orchestrator   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                         LAYER 2: MASTER ORCHESTRATOR                        │
│  n8n workflows — brain of the system, decides everything, performs nothing  │
└────┬────────────┬────────────┬────────────┬────────────┬────────────┬──────┘
     │            │            │            │            │            │
┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌────▼───┐  ┌────▼───┐
│LAYER 3 │  │LAYER 4 │  │LAYER 5 │  │LAYER 6 │  │LAYER 7 │  │LAYER 8 │
│State   │  │Memory  │  │Story   │  │Bible   │  │Planning│  │Prompt  │
│Machine │  │Manager │  │Intel   │  │Builder │  │Engines │  │Director│
└────────┘  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                         LAYER 9: JOB DISPATCH                               │
│  Queue management, worker selection, task assignment, timeout handling      │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                        LAYER 10: REMOTE EXECUTION                           │
│  GPU workers, CPU workers, vision workers, super-resolution workers         │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 11    │  LAYER 12    │  LAYER 13   │  LAYER 14   │  LAYER 15       │
│  Quality AI  │  Repair Eng  │  Voice Eng  │  Music Dir  │  Animation Eng  │
└──────────────┴──────────────┴─────────────┴─────────────┴─────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  LAYER 16           │  LAYER 17              │  LAYER 18                    │
│  Final Render Eng   │  Super Resolution      │  Auto Reviewer               │
└─────────────────────┴────────────────────────┴──────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                         LAYER 19: LEARNING ENGINE                           │
│  Post-project analysis, threshold tuning, prompt evolution, backend prefs   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                        LAYER 20: TELEGRAM DELIVERY                          │
│  Final video delivery, progress reports, archive, user feedback             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. COMPLETE LAYER SPECIFICATIONS

---

### LAYER 1 — TELEGRAM INTAKE LAYER

**Responsibilities:**
- Receive the novel or long story via Telegram file upload or text message
- Receive control commands (/start, /status, /cancel, /help, /settings)
- Validate incoming text (encoding, length, language, format)
- Create the project in PostgreSQL
- Generate project_id (UUID)
- Trigger the Master Orchestrator
- Store raw inputs and metadata
- Handle file downloads (Telegram Document → local file)
- Handle text messages (split long messages, concatenate multi-part uploads)
- Support Arabic and English input
- Support mixed-language input
- Enforce per-user project limits
- Enforce per-user rate limits

**Inputs:**
- Telegram messages (text, document, photo)
- Telegram commands (/start, /status, /cancel, /help, /settings)
- Optional metadata (user preferences, project settings)

**Outputs:**
- project_id (UUID)
- raw_story (text content)
- command_payload (for control commands)
- intake_metadata (word_count, language, encoding, file_size, timestamps)

**Internal Workflows:**
```
telegram_intake
├── [1] Telegram Trigger (message/document/command)
├── [2] Command Router (switch on message type)
│   ├── /start → Welcome Handler
│   ├── /status → Status Handler
│   ├── /cancel → Cancel Handler
│   ├── /help → Help Handler
│   ├── /settings → Settings Handler
│   └── document/text → Intake Pipeline
├── [3] Intake Pipeline
│   ├── [3a] File Download (if document)
│   ├── [3b] Encoding Detection (utf-8, latin-1, cp1252, arabic)
│   ├── [3c] Language Detection (en, ar, mixed)
│   ├── [3d] Text Validation (min 50 words, max 500k words)
│   ├── [3e] Text Normalization (unicode, whitespace, line breaks)
│   ├── [3f] Title Extraction (first line or first sentence)
│   └── [3g] Metadata Calculation (word_count, char_count, estimated_duration)
├── [4] Project Creation
│   ├── [4a] INSERT INTO projects (user_id, chat_id, state='created')
│   ├── [4b] INSERT INTO novels (project_id, title, raw_text, cleaned_text, ...)
│   └── [4c] INSERT INTO state_transitions
├── [5] Orchestrator Trigger
│   ├── [5a] HTTP POST to n8n webhook (project_orchestrator)
│   └── [5b] Body: { project_id, trigger: 'new_project' }
└── [6] Acknowledgment
    └── [6a] Telegram Send Message: "Novel received: {title} ({word_count} words). Starting production..."
```

**Error Handling:**
- File too large → "File exceeds 10MB limit. Please send a shorter novel."
- Too few words → "Novel must be at least 50 words. Current: {count}."
- Too many words → "Novel exceeds 500,000 word limit. Consider splitting into parts."
- Encoding failure → "Could not read file encoding. Please resend as UTF-8 text."
- Duplicate project → "You already have an active project. Use /cancel to stop it first."
- Rate limit → "Please wait {seconds} before sending another novel."

**Observable Metrics:**
- intake_total_received (counter)
- intake_total_completed (counter)
- intake_total_failed (counter)
- intake_average_word_count (gauge)
- intake_average_processing_time_ms (histogram)

---

### LAYER 2 — MASTER ORCHESTRATOR

**Responsibilities:**
- Read the current project state from PostgreSQL
- Decide which workflow to execute next
- Dispatch jobs to appropriate layers
- Update PostgreSQL with state changes
- Update the state machine via Layer 3
- Handle retry logic (exponential backoff)
- Handle resume logic (recovery from interruption)
- Handle failure routing (retry → repair → escalate → abort)
- Send progress updates to Telegram via Layer 20
- Maintain project execution order
- Enforce dependency ordering (references before generation)
- Manage parallel execution where safe
- Coordinate multi-project scheduling
- Never perform heavy generation tasks itself

**Inputs:**
- project_id (from webhook or scheduler)
- trigger_event (new_project, phase_complete, task_complete, task_failed, repair_complete)
- scheduler_tick (from cron, for polling stuck projects)

**Outputs:**
- workflow_dispatch (HTTP webhook to target layer)
- state_transition (via Layer 3)
- progress_update (via Layer 20)
- error_report (via Layer 20)

**Decision Matrix:**
```
┌─────────────────────────────┬──────────────────────────────────────┐
│ CURRENT STATE               │ NEXT WORKFLOW                         │
├─────────────────────────────┼──────────────────────────────────────┤
│ created                     │ (should not reach orchestrator)       │
│ intake_complete             │ chapter_extractor → scene_extractor   │
│ analysis_complete           │ reference_generator                   │
│ reference_generation_complete│ shot_planner                         │
│ shot_planning_complete      │ image_generator + audio_generator     │
│ quality_reviewing           │ quality_reviewer                      │
│ quality_failed              │ repair_dispatcher                     │
│ repair_complete             │ quality_reviewer (re-check)           │
│ unrecoverable               │ delivery_handler (failure report)     │
│ assembled                   │ final_reviewer                        │
│ final_review_passed         │ delivery_handler                      │
│ delivered                   │ learning_engine                       │
│ learning_complete           │ (terminal: completed)                 │
│ paused                      │ (wait for resume signal)              │
│ failed                      │ (wait for manual intervention)        │
└─────────────────────────────┴──────────────────────────────────────┘
```

**Internal Workflows:**
```
project_orchestrator
├── [1] Trigger
│   ├── Webhook: receives project_id + trigger_event
│   └── Cron: every 60s, polls for stuck projects
├── [2] Project Loader
│   └── PostgreSQL: SELECT * FROM projects WHERE id=$project_id
├── [3] State Router
│   └── Switch on project.state → determines next workflow
├── [4] Prerequisite Checker
│   ├── Verify all dependencies are met
│   ├── Verify no conflicting workflows running
│   └── Verify project not cancelled/paused
├── [5] Phase Transition
│   ├── Layer 3: transition(project_id, new_state='{phase}_running')
│   └── Layer 4: log event
├── [6] Workflow Dispatch
│   ├── HTTP POST to target layer's webhook
│   ├── Body: { project_id, phase, context_data }
│   └── Timeout: configured per phase
├── [7] Response Handler
│   ├── On success: transition to '{phase}_complete'
│   ├── On failure: increment error_count
│   │   ├── If error_count < max_retries: retry with backoff
│   │   ├── If error_count >= max_retries: transition to 'failed'
│   │   └── Notify user of failure
│   └── On timeout: requeue or escalate
├── [8] Progress Reporter
│   ├── Calculate progress percentage
│   ├── Send Telegram update via Layer 20
│   └── Throttle: max 1 update per 30 seconds
└── [9] Logger
    ├── INSERT INTO state_transitions
    ├── INSERT INTO workflow_executions
    └── INSERT INTO events
```

**Observable Metrics:**
- orchestrator_active_projects (gauge)
- orchestrator_workflow_dispatches_total (counter, by workflow)
- orchestrator_workflow_failures_total (counter, by workflow)
- orchestrator_average_phase_duration_ms (histogram, by phase)
- orchestrator_retry_rate (counter)
- orchestrator_stall_count (gauge)

---

### LAYER 3 — STATE MACHINE CONTROLLER

**Responsibilities:**
- Enforce legal state transitions (reject invalid transitions)
- Prevent invalid workflow execution (no workflow runs without valid state)
- Record complete state history (every transition logged)
- Manage checkpoints (project can resume from any completed phase)
- Allow recovery from interruptions (detect stuck states, offer resume)
- Control the lifecycle of every project, scene, shot, asset, and job
- Provide transition validation API for all layers
- Detect deadlock (no progress for configurable timeout)
- Detect livelock (oscillating between states)
- Support manual state overrides (admin intervention)

**Inputs:**
- transition_request: { entity_type, entity_id, from_state, to_state, triggered_by, reason }
- query_request: { entity_type, entity_id } → returns current state + history
- checkpoint_request: { entity_type, entity_id } → returns last stable state

**Outputs:**
- transition_result: { success, new_state, transition_id, timestamp }
- state_record: { current_state, history[], checkpoint_data }
- validation_result: { valid, reason }

**Transition Validation Rules:**
```
VALID TRANSITIONS (project level):
───────────────────────────────────
created              → intaking
intaking             → intake_complete
intake_complete      → analysis_running
analysis_running     → analysis_complete
analysis_complete    → reference_generation_running
reference_generation_running → reference_generation_complete
reference_generation_complete → shot_planning_running
shot_planning_running → shot_planning_complete
shot_planning_complete → asset_generation_running
asset_generation_running → quality_reviewing
quality_reviewing    → repair_running | assembling | unrecoverable
repair_running       → repair_complete
repair_complete      → quality_reviewing (re-check loop, max 3 times)
assembling           → assembled
assembled            → final_reviewing
final_reviewing      → delivery_running | repair_running | unrecoverable
delivery_running     → delivered
delivered            → learning_running
learning_running     → completed
any                  → paused (if no workflow actively running)
paused               → (previous state, resume)
any                  → failed (on unrecoverable error)
any                  → cancelled (on user request)
```

**Internal Workflows:**
```
state_machine_controller
├── [1] Transition Request Handler
│   ├── Receive: { entity_type, entity_id, from_state, to_state, triggered_by, reason }
│   ├── Validate transition is legal
│   ├── If illegal: reject with reason, log violation
│   └── If legal: proceed
├── [2] Atomic Transition
│   ├── BEGIN TRANSACTION
│   ├── UPDATE entities SET state = to_state WHERE id = entity_id AND state = from_state
│   ├── If affected_rows = 0: CONFLICT (concurrent modification)
│   │   ├── ROLLBACK
│   │   ├── Return conflict error
│   │   └── Caller must retry
│   ├── INSERT INTO state_transitions (entity_type, entity_id, from_state, to_state, ...)
│   ├── UPDATE entities SET updated_at = NOW()
│   └── COMMIT
├── [3] State Query Handler
│   ├── Receive: { entity_type, entity_id }
│   ├── Return: { current_state, state_changed_at, history[], checkpoint_data }
│   └── History includes: all transitions, timestamps, triggered_by
├── [4] Checkpoint Manager
│   ├── On phase completion: snapshot project state
│   ├── Store in projects.checkpoint_data (JSONB)
│   ├── Include: completed phases, entity counts, quality scores
│   └── Enable resume from any checkpoint
├── [5] Deadlock Detector
│   ├── Cron: every 5 minutes
│   ├── Check for projects in *_running state with no activity for > 30 minutes
│   ├── If detected: transition to 'paused', notify admin
│   └── Log event: 'deadlock_detected'
├── [6] Livelock Detector
│   ├── Check for projects with > 5 state changes in last 10 minutes without progress
│   ├── If detected: transition to 'paused', notify admin
│   └── Log event: 'livelock_detected'
└── [7] Audit Trail
    ├── Every transition recorded with full context
    ├── Immutable (never delete or modify history)
    └── Queryable for debugging and learning
```

**Observable Metrics:**
- state_transitions_total (counter, by entity_type, from_state, to_state)
- state_transition_failures_total (counter, by rejection_reason)
- state_deadlocks_detected (counter)
- state_livelocks_detected (counter)
- state_average_transition_time_ms (histogram)
- state_active_projects_by_phase (gauge, by state)

---

### LAYER 4 — MEMORY MANAGER

**Responsibilities:**
- Store all persistent project data in PostgreSQL
- Store entity relationships (project→novel→chapters→scenes→shots)
- Store asset references (images, audio, video, references)
- Store prompt history (every prompt ever generated, versioned)
- Store review history (every quality review, every score)
- Store repair history (every repair attempt, before/after scores)
- Store execution history (every workflow execution, every task)
- Enforce data integrity (foreign keys, constraints)
- Provide read/write interfaces for all layers
- Enforce versioning rules (bibles are versioned, immutable after lock)
- Manage concurrent access (proper locking, transaction isolation)
- Provide audit trail for all mutations
- Support data export and backup
- Support data recovery from corruption

**Inputs:**
- write_requests: { table, operation, data, triggered_by }
- read_requests: { table, query, requesting_layer }
- version_requests: { entity_type, entity_id, operation: 'lock' | 'unlock' | 'revert' }

**Outputs:**
- query_results: { data, metadata, timestamp }
- write_results: { success, affected_rows, version }
- version_results: { success, version_number }

**Memory Access Protocol:**
```
READ ACCESS:
────────────
- Any layer may READ from any table
- Reads are logged in audit trail (entity, layer, timestamp)
- Reads never block writes (read-committed isolation)
- Bibles return the latest unlocked version by default
- Locked bibles return the locked version

WRITE ACCESS:
─────────────
- Layer 1 (Intake): may WRITE to projects, novels, state_transitions
- Layer 2 (Orchestrator): may WRITE to projects.state, state_transitions, workflow_executions
- Layer 3 (State Machine): may WRITE to state_transitions only (enforced by trigger)
- Layer 4 (Memory): is the WRITE interface — all writes go through this layer
- Layer 5 (Story Intelligence): may WRITE to chapters, scenes, scene_characters
- Layer 6 (Bible Builder): may WRITE to *_bibles (with versioning), character_references, world_references
- Layer 7 (Planning): may WRITE to shots
- Layer 8 (Prompt Director): may WRITE to shots.positive_prompt, shots.negative_prompt
- Layer 9 (Job Dispatch): may WRITE to tasks
- Layer 10 (Remote Execution): may WRITE to tasks.result, tasks.state
- Layer 11 (Quality AI): may WRITE to reviews
- Layer 12 (Repair Engine): may WRITE to repairs, tasks
- Layer 13-17 (Generation): may WRITE to images, audio, video_clips, final_videos
- Layer 18 (Auto Reviewer): may WRITE to reviews, final_videos.state
- Layer 19 (Learning): may WRITE to learning_data, system_config
- Layer 20 (Delivery): may WRITE to projects.state, final_videos.state

VERSIONING RULES:
─────────────────
- Bibles are versioned: each lock creates version N, unlock creates version N+1
- Prompts are versioned: each regeneration increments prompt_version
- Images are versioned: each variant is variant_number N+1
- Reviews are append-only (never modify, always add new record)
- Repairs are append-only
- State transitions are append-only
```

**Internal Workflows:**
```
memory_manager
├── [1] Write Request Handler
│   ├── Validate caller has write permission for target table
│   ├── Validate data against schema
│   ├── BEGIN TRANSACTION
│   ├── Execute write operation
│   ├── INSERT INTO audit trail
│   ├── COMMIT
│   └── Return result
├── [2] Read Request Handler
│   ├── Validate query
│   ├── Execute query
│   ├── Log read access
│   └── Return results
├── [3] Version Manager
│   ├── On bible lock: increment version, set locked=true, locked_at=NOW()
│   ├── On bible unlock: create new version row, copy data, set locked=false
│   ├── On bible revert: set current version, create new version pointing to old data
│   └── Enforce: locked bibles cannot be modified
├── [4] Integrity Enforcer
│   ├── Foreign key constraints (enforced by PostgreSQL)
│   ├── Check constraints (state values, score ranges)
│   ├── Unique constraints (no duplicate scenes, shots, etc.)
│   └── Not-null constraints on critical fields
├── [5] Backup Manager
│   ├── Cron: daily pg_dump to compressed file
│   ├── Retain: 7 daily, 4 weekly, 3 monthly
│   └── Verify: checksum validation
└── [6] Recovery Manager
    ├── On corruption detection: alert admin
    ├── Provide recovery commands
    └── Support point-in-time recovery from WAL
```

**Observable Metrics:**
- memory_writes_total (counter, by table, by layer)
- memory_reads_total (counter, by table, by layer)
- memory_write_latency_ms (histogram, by table)
- memory_read_latency_ms (histogram, by table)
- memory_version_operations_total (counter, by entity_type)
- memory_lock_operations_total (counter, by entity_type)
- memory_integrity_violations_total (counter)
- memory_backup_last_success (timestamp)

---

### LAYER 5 — STORY INTELLIGENCE ENGINE

**Responsibilities:**
- Read the full novel from PostgreSQL
- Understand the narrative deeply using LLM analysis
- Extract chapters (regex + LLM hybrid)
- Extract scenes (paragraph analysis + LLM segmentation)
- Extract dialogues (quote detection + speaker attribution)
- Extract characters (name extraction + evidence collection + LLM DNA)
- Extract relationships (proximity analysis + LLM inference)
- Extract locations (name extraction + description analysis)
- Extract timeline (temporal reference extraction + ordering)
- Extract battles (action sequence detection + intensity scoring)
- Extract emotional arcs (sentiment analysis per scene)
- Extract visual highlights (visually rich passages identified)
- Detect contradictions (cross-reference claims across chapters)
- Detect missing context (gaps in character/location introductions)
- Detect timeline issues (events out of order, impossible sequences)
- Produce structured story graphs (JSON representations of narrative structure)

**Inputs:**
- project_id
- novel.cleaned_text
- novel.language

**Outputs (all stored in PostgreSQL via Layer 4):**
```
- chapters[]          → cineos.core.chapters
- scenes[]            → cineos.core.scenes
- scene_characters[]  → cineos.core.scene_characters
- characters[]        → cineos.core.characters (evidence, not yet DNA)
- locations[]         → stored in scenes.location_name + location extraction
- timeline_events[]   → cineos.memory.timeline_bibles.events
- dialogue_data[]     → stored in scenes (dialogue count, lines)
- emotional_arcs[]    → stored in scenes (primary_emotion, secondary_emotions)
- contradictions[]    → cineos.memory.story_bibles.contradictions
- plot_holes[]        → cineos.memory.story_bibles.plot_holes
- visual_highlights[] → stored in scenes (importance scoring)
```

**Story Graph Structure:**
```json
{
  "story_graph": {
    "chapters": [
      {
        "number": 1,
        "title": "...",
        "scenes": [
          {
            "id": "ch1_sc1",
            "sequence": 1,
            "text": "...",
            "summary": "...",
            "location": { "name": "...", "type": "indoor/outdoor", "description": "..." },
            "time": { "reference": "dawn", "relative": "chapter_start", "absolute_order": 1 },
            "characters": [
              { "name": "Aldric", "role": "protagonist", "emotional_state": "determined" }
            ],
            "dialogues": [
              { "speaker": "Aldric", "text": "...", "emotion": "resolute" }
            ],
            "emotions": { "primary": "tension", "secondary": ["determination", "fear"] },
            "conflict": { "type": "internal", "description": "..." },
            "importance": "critical",
            "visual_highlights": ["sword gleaming in torchlight", "tower silhouette"],
            "action": { "present": true, "intensity": "high", "type": "combat" }
          }
        ]
      }
    ],
    "characters": [
      {
        "name": "Aldric",
        "first_appearance": "ch1_sc1",
        "scene_count": 5,
        "evidence": ["..."],
        "relationships": [{ "target": "Elara", "type": "ally", "evidence": "..." }]
      }
    ],
    "timeline": [
      {
        "order": 1,
        "scene_id": "ch1_sc1",
        "time_reference": "dawn",
        "duration_estimate": "1 hour"
      }
    ],
    "locations": [
      {
        "name": "Throne Room",
        "scene_ids": ["ch1_sc1", "ch2_sc3"],
        "description": "...",
        "type": "indoor"
      }
    ],
    "contradictions": [
      { "type": "timeline", "description": "...", "scenes": ["ch1_sc2", "ch3_sc1"] }
    ]
  }
}
```

**Internal Workflows:**
```
scene_extractor (main analysis workflow)
├── [1] Trigger: { project_id }
├── [2] Novel Loader: SELECT cleaned_text FROM novels WHERE project_id=$project_id
├── [3] Chapter Extraction
│   ├── [3a] Regex Splitter: Chapter N, CHAPTER N, Ch. N, الفصل
│   ├── [3b] LLM Chapter Detection: for ambiguous splits
│   └── [3c] Chapter Persister: INSERT INTO chapters
├── [4] Scene Segmentation (per chapter, parallel)
│   ├── [4a] Paragraph Analysis: detect scene breaks (blank lines, location changes, time jumps)
│   ├── [4b] LLM Scene Segmentation: identify narrative scene boundaries
│   ├── [4c] Scene Merging: combine overlapping segments
│   └── [4d] Scene Persister: INSERT INTO scenes
├── [5] Character Extraction
│   ├── [5a] Regex Name Detection: capitalized words near dialogue verbs
│   ├── [5b] LLM Character Extraction: identify all characters with evidence
│   ├── [5c] Deduplication: fuzzy matching, alias resolution
│   └── [5d] Character Persister: INSERT INTO characters (evidence only, no DNA yet)
├── [6] Scene-Character Linking
│   ├── [6a] For each scene: identify which characters are present
│   └── [6b] INSERT INTO scene_characters
├── [7] Location Extraction
│   ├── [7a] Regex: capitalized location names
│   ├── [7b] LLM: identify locations with descriptions
│   └── [7c] Location Persister: UPDATE scenes SET location_name
├── [8] Timeline Extraction
│   ├── [8a] Temporal Reference Detection: "three days later", "at dawn", "the next morning"
│   ├── [8b] LLM: order events chronologically
│   ├── [8c] Timeline Conflict Detection: events that can't be in order
│   └── [8d] Timeline Persister: INSERT INTO timeline_bibles.events
├── [9] Dialogue Extraction
│   ├── [9a] Quote Detection: "..." patterns, attribution verbs
│   ├── [9b] Speaker Attribution: match speaker to character
│   └── [9c] Dialogue Persister: UPDATE scenes SET dialogue_count, dialogue_present
├── [10] Emotional Arc Extraction
│   ├── [10a] Sentiment Analysis per scene
│   ├── [10b] LLM: identify emotional progression
│   └── [10c] Emotion Persister: UPDATE scenes SET primary_emotion, secondary_emotions
├── [11] Inconsistency Detection
│   ├── [11a] Cross-reference character claims across chapters
│   ├── [11b] Timeline consistency check
│   ├── [11c] Location consistency check
│   └── [11d] Persister: UPDATE story_bibles SET contradictions, plot_holes
├── [12] Visual Priority Scoring
│   ├── [12a] Score each scene for visual richness
│   ├── [12b] Identify "hero shots" — scenes with high visual potential
│   └── [12c] Persister: UPDATE scenes SET importance
└── [13] Transition
    ├── [13a] UPDATE projects SET state='analysis_complete', progress=0.25
    └── [13b] INSERT INTO state_transitions
```

**Observable Metrics:**
- analysis_chapters_extracted (counter)
- analysis_scenes_extracted (counter)
- analysis_characters_extracted (counter)
- analysis_locations_extracted (counter)
- analysis_contradictions_detected (counter)
- analysis_llm_calls_total (counter)
- analysis_llm_total_duration_ms (histogram)
- analysis_regex_fallback_count (counter)
- analysis_visual_highlights_identified (counter)

---

### LAYER 6 — BIBLE BUILDER LAYER

**Responsibilities:**
- Build Story Bible (narrative structure, themes, arcs, visual style notes)
- Build Character Bible (immutable character reference cards with 40+ attributes)
- Build World Bible (geography, architecture, technology, magic, culture)
- Build Timeline Bible (chronological event ordering with conflict detection)
- Build Style Bible (art style, color palette, lighting, composition rules)
- Freeze canonical rules after verification
- Define visual and audio translation notes
- Generate visual prompt fragments from bibles
- Generate negative prompt fragments from bibles
- Lock bibles (make immutable)
- Version bibles (unlock creates new version)
- Validate bible completeness before allowing generation
- Cross-reference bibles for consistency

**Inputs:**
- project_id
- Analysis results from Layer 5 (characters, scenes, timeline, etc.)
- User style preferences (if provided via /settings)

**Outputs:**
```
- story_bible       → cineos.memory.story_bibles
- character_bibles[] → cineos.memory.character_bibles (one per character)
- world_bible       → cineos.memory.world_bibles
- timeline_bible    → cineos.memory.timeline_bibles
- style_bible       → cineos.memory.style_bibles
- character_references[] → cineos.memory.character_references (reference images)
- world_references[] → cineos.memory.world_references (reference images)
```

**Bible Building Sequence (mandatory order):**
```
1. Style Bible        → defines visual language
2. World Bible        → defines environment rules
3. Character Bibles   → defines character appearance (uses world_bible for context)
4. Timeline Bible     → orders events (uses character_bibles for context)
5. Story Bible        → synthesizes all bibles into narrative overview
6. Reference Images   → generates visual references (uses all bibles)
7. Lock all bibles    → freeze before generation begins
```

**Internal Workflows:**
```
character_bible_builder (representative — all bible builders follow similar pattern)
├── [1] Trigger: { project_id }
├── [2] Data Loader
│   ├── Load characters from Layer 5 results
│   ├── Load scenes with character associations
│   ├── Load world_bible (for visual context)
│   └── Load style_bible (for visual language)
├── [3] LLM DNA Builder (per character)
│   ├── [3a] Prompt: "Based on these evidence quotes from the novel, build a complete character reference card..."
│   ├── [3b] Evidence quotes provided as context
│   ├── [3c] LLM returns structured JSON with 40+ fields
│   └── [3d] Validate: all mandatory fields present
├── [4] Visual Prompt Builder
│   ├── [4a] Compose visual_prompt_positive from DNA fields:
│   │   hair_color + eye_color + skin_tone + body_type + clothing + accessories
│   ├── [4b] Compose visual_prompt_negative from exclusions:
│   │   "wrong_hair_color, wrong_eye_color, deformed, blurry"
│   └── [4c] Store in character_bibles.visual_prompt_positive/negative
├── [5] Bible Persister
│   ├── [5a] INSERT INTO character_bibles (all fields)
│   └── [5b] Version = 1, locked = false
├── [6] Reference Image Trigger
│   ├── [6a] HTTP POST to reference_generator workflow
│   └── [6b] Body: { character_id, visual_prompt_positive }
├── [7] Completeness Validator
│   ├── [7a] Check: all characters have bibles
│   ├── [7b] Check: all mandatory fields populated
│   ├── [7c] Check: confidence_score > 0.5
│   └── [7d] If incomplete: trigger re-extraction for missing fields
└── [8] Transition
    ├── [8a] Log: bible built
    └── [8b] Continue to next bible (or signal completion)
```

**Reference Generation Workflow:**
```
reference_generator
├── [1] Trigger: { project_id, reference_type, entity_id }
├── [2] Prompt Builder
│   ├── Load entity's visual_prompt_positive
│   ├── Load style_bible.base_positive_prompt
│   ├── Compose: "{entity_prompt}, {style_prompt}, reference sheet, character portrait"
│   └── Load negative prompt from style_bible + entity
├── [3] Image Generation Task
│   ├── Create task in cineos.execution.tasks
│   ├── Payload: { prompt, negative_prompt, width: 1024, height: 1024, seed: random }
│   └── Dispatch to Layer 9 (Job Dispatch)
├── [4] Result Handler
│   ├── Receive generated image
│   ├── Save to disk
│   ├── INSERT INTO character_references or world_references
│   └── Set is_primary = true for first reference
├── [5] Quality Check
│   ├── Basic validation: file exists, size > 10KB, dimensions correct
│   ├── Optional: CLIP similarity check against prompt
│   └── If failed: retry with different seed (max 3 attempts)
└── [6] Lock Bible
    ├── After all references generated and validated
    ├── UPDATE character_bibles SET locked=true, locked_at=NOW()
    └── INSERT INTO state_transitions
```

**Observable Metrics:**
- bibles_built_total (counter, by bible_type)
- bibles_locked_total (counter)
- bibles_unlocked_total (counter)
- bibles_reverted_total (counter)
- bibles_average_confidence_score (histogram, by bible_type)
- references_generated_total (counter, by reference_type)
- references_quality_score (histogram)
- references_retry_rate (counter)

---

### LAYER 7 — PLANNING ENGINES

**Responsibilities:**
- Plan cinematic shots for every scene
- Determine shot types, durations, camera angles, movements
- Determine shot budgets based on scene importance
- Plan animation types for each shot
- Plan transitions between shots
- Determine narration text per shot
- Plan character appearances per shot
- Estimate total video duration
- Enforce shot budget limits (max shots per project)
- Ensure narrative flow between shots
- Balance pacing across chapters

**Inputs:**
- project_id
- All bibles from Layer 6 (locked)
- All scenes from Layer 5
- Character-scene associations
- Scene importance scores

**Outputs:**
```
- shots[] → cineos.core.shots (for every scene, every shot)
  - shot_type, duration_seconds, camera_angle, camera_movement
  - animation_type, animation_params
  - transition_in, transition_out
  - characters_in_shot[]
  - narration_text
  - narration_voice, narration_emotion
  - importance
```

**Shot Budget System:**
```
SCENE IMPORTANCE → SHOT BUDGET:
────────────────────────────────
critical    → 8-12 shots, 15-30 seconds per shot
high        → 6-8 shots, 10-20 seconds per shot
normal      → 4-6 shots, 8-15 seconds per shot
low         → 2-3 shots, 5-10 seconds per shot

SHOT TYPE DISTRIBUTION (per scene):
────────────────────────────────────
establishing    → 1 per scene (first shot)
wide            → 20% of shots
medium          → 30% of shots
close_up        → 25% of shots
extreme_close_up → 10% of shots
action          → 15% of shots (when action_present)

PROJECT LIMITS:
───────────────
max_shots_per_project: 1000
max_duration_per_project: 3600 seconds (60 minutes)
max_duration_per_shot: 30 seconds
min_duration_per_shot: 3 seconds
```

**Internal Workflows:**
```
shot_planner
├── [1] Trigger: { project_id }
├── [2] Data Loader
│   ├── Load all scenes (ordered by chapter_number, scene_number)
│   ├── Load all character_bibles (locked)
│   ├── Load world_bible (locked)
│   ├── Load style_bible (locked)
│   └── Load story_bible (locked)
├── [3] Budget Calculator
│   ├── Calculate total shot budget based on scene count and importance
│   ├── Distribute budget across scenes
│   └── Enforce project limits
├── [4] Shot Planning Loop (per scene)
│   ├── [4a] LLM Shot Planner
│   │   ├── Prompt: "Plan {budget} cinematic shots for this scene..."
│   │   ├── Context: scene text, characters present, world/style bibles
│   │   └── Response: JSON array of shot plans
│   ├── [4b] Budget Enforcer
│   │   ├── Trim excess shots (keep highest importance)
│   │   ├── Ensure minimum shots per scene
│   │   └── Enforce shot type distribution
│   ├── [4c] Camera Planner
│   │   ├── Assign camera_angle based on shot_type and emotion
│   │   ├── Assign camera_movement based on pacing and action
│   │   └── Calculate depth_of_field based on shot_type
│   ├── [4d] Animation Planner
│   │   ├── Assign animation_type based on shot_type
│   │   ├── Calculate animation_params (zoom factor, pan speed, focal point)
│   │   └── Ensure smooth transitions between shots
│   ├── [4e] Narration Planner
│   │   ├── Extract narration text from scene (LLM or rule-based)
│   │   ├── Split long narrations across multiple shots
│   │   ├── Assign voice and emotion per shot
│   │   └── Estimate narration duration
│   └── [4f] Shot Persister
│       ├── INSERT INTO shots (all fields)
│       └── UPDATE scenes SET shot_count, estimated_duration_seconds
├── [5] Flow Validator
│   ├── Check narrative continuity between shots
│   ├── Check character presence consistency
│   ├── Check location continuity
│   └── Check pacing distribution
├── [6] Duration Estimator
│   ├── Sum all shot durations
│   ├── Add transition durations
│   ├── Estimate total video duration
│   └── Warn if exceeds max_duration_per_project
├── [7] Transition
│   ├── UPDATE projects SET state='shot_planning_complete', progress=0.50
│   └── INSERT INTO state_transitions
└── [8] Return
    └── { total_shots, estimated_duration, scenes_planned }
```

**Observable Metrics:**
- planning_shots_created_total (counter)
- planning_total_duration_seconds (gauge)
- planning_budget_utilization (gauge, shots_created / budget)
- planning_shot_type_distribution (histogram, by shot_type)
- planning_llm_calls_total (counter)
- planning_flow_violations_detected (counter)

---

### LAYER 8 — PROMPT DIRECTOR

**Responsibilities:**
- Generate structured prompts for every shot
- Compose positive prompts from multiple sources (bibles, references, shot plan)
- Compose negative prompts from exclusions
- Apply style_bible.base_positive_prompt and base_negative_prompt
- Include character visual references in character-focused shots
- Include world visual references in location-focused shots
- Apply quality tags from style_bible
- Version prompts (every regeneration creates new version)
- Store prompt history for analysis
- Optimize prompts for target backend (different backends prefer different formats)
- Apply prompt engineering best practices (weighting, ordering, emphasis)

**Inputs:**
- project_id
- All shots from Layer 7
- All bibles from Layer 6
- Character reference prompts
- World reference prompts

**Outputs:**
```
- shots.positive_prompt (updated)
- shots.negative_prompt (updated)
- shots.prompt_version (incremented)
```

**Prompt Composition Formula:**
```
POSITIVE PROMPT STRUCTURE:
──────────────────────────
[quality_tags] [base_positive_prompt] [shot_specific] [character_prompts] [world_prompts] [style_modifiers]

Example:
"masterpiece, best quality, highly detailed, anime style, cinematic lighting,
 {shot.camera_angle} shot, {shot.shot_type},
 {character_1.visual_prompt_positive}, {character_2.visual_prompt_positive},
 {world.visual_prompt_positive}, {location.description},
 {scene.emotion} atmosphere, {style_bible.color_grading} color grading"

NEGATIVE PROMPT STRUCTURE:
──────────────────────────
[base_negative_prompt] [character_exclusions] [world_exclusions] [quality_exclusions]

Example:
"worst quality, low quality, blurry, deformed, ugly,
 {character_1.visual_prompt_negative},
 {world.visual_prompt_negative},
 extra fingers, extra limbs, disfigured, bad anatomy"
```

**Internal Workflows:**
```
prompt_generator
├── [1] Trigger: { project_id }
├── [2] Shot Loader
│   └── SELECT shots, scenes, character_bibles, world_bible, style_bible
├── [3] Prompt Composition Loop (per shot)
│   ├── [3a] Load shot context
│   │   ├── shot.shot_type, shot.camera_angle, shot.camera_movement
│   │   ├── shot.characters_in_shot
│   │   ├── scene.location_name, scene.primary_emotion
│   │   └── scene.importance
│   ├── [3b] Character Prompt Assembly
│   │   ├── For each character in shot:
│   │   │   └── Load character_bible.visual_prompt_positive
│   │   ├── Merge into character_prompt_fragment
│   │   └── Handle multiple characters (priority ordering)
│   ├── [3c] World Prompt Assembly
│   │   ├── Load world_bible.visual_prompt_positive
│   │   ├── Load location-specific details
│   │   └── Merge into world_prompt_fragment
│   ├── [3d] Style Prompt Assembly
│   │   ├── Load style_bible.base_positive_prompt
│   │   ├── Load style_bible.quality_tags
│   │   ├── Apply shot_type-specific modifiers
│   │   └── Merge into style_prompt_fragment
│   ├── [3e] Negative Prompt Assembly
│   │   ├── Load style_bible.base_negative_prompt
│   │   ├── For each character in shot: load visual_prompt_negative
│   │   ├── Load world_bible.visual_prompt_negative
│   │   └── Merge into negative_prompt
│   ├── [3f] Final Composition
│   │   ├── positive = quality_tags + " " + style + " " + shot_specific + " " + characters + " " + world
│   │   ├── negative = base_negative + " " + character_exclusions + " " + world_exclusions
│   │   └── Optimize for target backend (truncate if needed)
│   └── [3g] Prompt Persister
│       ├── UPDATE shots SET positive_prompt, negative_prompt, prompt_version += 1
│       └── INSERT INTO prompt_history (for learning)
├── [4] Prompt Validation
│   ├── Check prompt length < backend max tokens
│   ├── Check no empty fragments
│   ├── Check character references are consistent
│   └── Check world references are consistent
├── [5] Transition
│   └── UPDATE shots SET state='prompt_ready'
└── [6] Return
    └── { shots_updated, avg_prompt_length }
```

**Observable Metrics:**
- prompts_generated_total (counter)
- prompts_average_length (histogram)
- prompts_character_reference_inclusion_rate (gauge)
- prompts_world_reference_inclusion_rate (gauge)
- prompts_backend_optimization_count (counter)

---

### LAYER 9 — JOB DISPATCH LAYER

**Responsibilities:**
- Manage the task queue in PostgreSQL
- Select appropriate worker for each task
- Assign tasks to workers
- Handle task timeout
- Handle task failure (reassign to different worker)
- Handle worker offline (reassign pending tasks)
- Prioritize tasks (critical shots first, then by project priority)
- Manage concurrency limits per worker
- Track task lifecycle (pending → queued → assigned → running → completed/failed)
- Provide task status API for other layers
- Handle task cancellation
- Handle duplicate task detection

**Inputs:**
- task_creation: { project_id, task_type, payload, priority, timeout_ms }
- task_update: { task_id, state, result, error }
- worker_heartbeat: { worker_id, status, current_load }
- task_query: { task_id } or { project_id, task_type, state }

**Outputs:**
- task_assignment: { task_id, worker_id, worker_endpoint }
- task_result: { task_id, state, result }
- queue_status: { pending_count, running_count, worker_availability }

**Task Priority System:**
```
PRIORITY LEVELS:
────────────────
1 (highest)  → Repair tasks (critical path)
2            → Reference generation (blocking other work)
3            → Image generation (main production path)
4            → Audio generation (can run in parallel)
5 (normal)   → Quality review
6            → Clip rendering
7            → Video rendering
8            → Learning engine (post-project)
9 (lowest)   → Backup, maintenance
```

**Internal Workflows:**
```
job_dispatcher (n8n workflow)
├── [1] Trigger
│   ├── Webhook: new task creation
│   ├── Cron: every 10 seconds, process queue
│   └── Webhook: worker heartbeat
├── [2] Task Queue Processor
│   ├── [2a] SELECT * FROM tasks WHERE state='pending' ORDER BY priority, created_at
│   ├── [2b] For each pending task:
│   │   ├── Find available worker (Layer 10 selection)
│   │   ├── If no worker: leave in queue
│   │   ├── If worker found:
│   │   │   ├── UPDATE tasks SET state='assigned', assigned_worker_id=worker.id
│   │   │   └── HTTP POST to worker endpoint with task payload
│   └── [2c] Enforce concurrency limits
├── [3] Worker Health Monitor
│   ├── [3a] Check last_heartbeat for all workers
│   ├── [3b] If heartbeat > 60s old: mark worker offline
│   ├── [3c] Reassign all pending tasks from offline worker
│   └── [3d] Notify admin of worker failure
├── [4] Task Timeout Handler
│   ├── [4a] SELECT * FROM tasks WHERE state='running' AND started_at + timeout < NOW()
│   ├── [4b] For each timed-out task:
│   │   ├── Mark task as failed (timeout)
│   │   ├── Increment retry_count
│   │   ├── If retry_count < max_retries: requeue
│   │   └── If retry_count >= max_retries: mark as permanently failed
│   └── [4c] Log timeout event
├── [5] Task Result Handler
│   ├── [5a] Receive result from worker webhook
│   ├── [5b] UPDATE tasks SET state='completed', result=$result
│   ├── [5c] Notify parent workflow (via webhook or DB poll)
│   └── [5d] Update worker metrics
├── [6] Worker Selection Algorithm
│   ├── Input: task_type, task_priority
│   ├── Candidates: workers WHERE worker_type matches AND status != 'offline'
│   ├── Score: priority * 0.3 + success_rate * 0.4 + (1 / avg_duration) * 0.3
│   ├── Prefer local worker if score difference < 10%
│   └── Return best candidate
└── [7] Queue Status Reporter
    ├── Count pending, assigned, running, completed, failed tasks
    ├── Count available workers by type
    └── Return queue_status
```

**Observable Metrics:**
- dispatch_tasks_created_total (counter, by task_type)
- dispatch_tasks_completed_total (counter, by task_type, by worker)
- dispatch_tasks_failed_total (counter, by failure_reason)
- dispatch_tasks_timeout_total (counter)
- dispatch_queue_depth (gauge, by task_type)
- dispatch_average_wait_time_ms (histogram)
- dispatch_worker_utilization (gauge, by worker_id)
- dispatch_worker_availability (gauge, by worker_type)

---

### LAYER 10 — REMOTE EXECUTION LAYER

**Responsibilities:**
- Execute heavy computation tasks on workers
- Support multiple worker types (GPU, CPU, vision, super-resolution)
- Support local and remote workers
- Register workers with orchestrator
- Send heartbeats to orchestrator
- Execute tasks and return results
- Report progress for long-running tasks
- Handle graceful shutdown
- Handle resource cleanup
- Support worker scaling (add/remove workers dynamically)

**Worker Types:**
```
1. gpu_image_worker
   - Image generation (SDXL, FLUX, Animagine, etc.)
   - Hardware: NVIDIA GPU 8GB+ VRAM
   - Software: Python, PyTorch, diffusers
   - Concurrency: 1 (GPU-bound)

2. cpu_tts_worker
   - Text-to-speech (Edge TTS, Piper, espeak)
   - Hardware: Any CPU
   - Software: Python, edge-tts, piper
   - Concurrency: 2-4 (CPU-bound, I/O light)

3. cpu_render_worker
   - Video clip rendering (FFmpeg)
   - Hardware: Any CPU, 4GB+ RAM
   - Software: FFmpeg, Python
   - Concurrency: 2-3 (CPU-bound)

4. vision_review_worker
   - Quality review (CLIP, InsightFace)
   - Hardware: CPU or GPU
   - Software: Python, transformers, insightface
   - Concurrency: 2-4

5. super_resolution_worker
   - Image upscaling (Real-ESRGAN)
   - Hardware: NVIDIA GPU 4GB+ VRAM
   - Software: Python, Real-ESRGAN
   - Concurrency: 1 (GPU-bound)
```

**Worker Protocol:**
```
WORKER LIFECYCLE:
─────────────────

1. STARTUP
   - Worker process starts
   - Load configuration (worker_type, capabilities, endpoint)
   - Register with orchestrator (POST /api/workers/register)
   - Start heartbeat loop (POST /api/workers/heartbeat every 30s)
   - Start task polling loop (GET /api/tasks/pending?worker_type={type})

2. TASK EXECUTION
   - Worker receives task via webhook or polling
   - Worker validates task payload
   - Worker executes task
   - Worker reports progress (optional, for long tasks)
   - Worker returns result (POST /api/tasks/{task_id}/complete)
   - Worker updates metrics

3. FAILURE HANDLING
   - On task failure: POST /api/tasks/{task_id}/failed with error
   - On resource exhaustion: POST /api/workers/status with 'overloaded'
   - On crash: heartbeat stops, orchestrator detects and reassigns

4. SHUTDOWN
   - Worker receives SIGTERM
   - Worker completes current task (with timeout)
   - Worker deregisters (POST /api/workers/deregister)
   - Worker exits
```

**Internal Workflows:**
```
worker_manager (n8n workflow — manages worker health and task dispatch)
├── [1] Trigger
│   ├── Cron: every 30 seconds (health check)
│   └── Webhook: worker registration/deregistration
├── [2] Worker Registry
│   ├── [2a] On registration: INSERT INTO workers
│   ├── [2b] On deregistration: UPDATE workers SET status='offline'
│   └── [2c] On heartbeat: UPDATE workers SET last_heartbeat, status
├── [3] Health Monitor
│   ├── [3a] SELECT workers WHERE last_heartbeat < NOW() - INTERVAL '90 seconds'
│   ├── [3b] Mark as offline
│   ├── [3c] Reassign pending tasks
│   └── [3d] Notify admin if all workers of a type are offline
├── [4] Task Dispatch
│   ├── [4a] For each pending task:
│   │   ├── Select worker using selection algorithm
│   │   ├── If worker available: assign and dispatch
│   │   └── If no worker: leave in queue
│   └── [4b] Handle dispatch failure (retry, reassign)
└── [5] Metrics Collector
    ├── [5a] Update worker metrics (success_rate, avg_duration)
    └── [5b] Update system metrics (queue_depth, utilization)
```

**Worker Selection Algorithm (detailed):**
```
function selectWorker(task_type, task_priority):
    candidates = query workers WHERE
        worker_type = task_type AND
        status IN ('idle', 'busy') AND
        enabled = true AND
        current_load < max_concurrent_tasks

    if candidates is empty:
        return null  # task stays in queue

    # Score each candidate
    for worker in candidates:
        worker.score = (
            worker.priority * 0.3 +           # lower priority number = better
            worker.success_rate * 0.4 +       # higher success rate = better
            (1.0 / max(worker.avg_task_duration_ms, 1)) * 0.3  # faster = better
        )

    # Prefer local worker if scores are close
    local_candidates = [w for w in candidates if w.host = 'localhost']
    if local_candidates and local_candidates[0].score > candidates[0].score * 0.9:
        return local_candidates[0]

    # Return highest scoring candidate
    return sort(candidates, by=score, descending)[0]
```

**Observable Metrics:**
- workers_total (gauge, by type, by status)
- workers_heartbeat_latency_ms (histogram)
- workers_task_duration_ms (histogram, by worker_id, by task_type)
- workers_success_rate (gauge, by worker_id)
- workers_current_load (gauge, by worker_id)
- workers_offline_total (counter)
- workers_failover_total (counter)

---

### LAYER 11 — QUALITY AI

**Responsibilities:**
- Review generated images for quality
- Review generated audio for quality
- Review shot composition
- Review scene coherence
- Review character consistency
- Review world consistency
- Review prompt alignment
- Review audio-video sync
- Review narrative fidelity
- Calculate composite quality scores
- Detect failures automatically
- Provide detailed issue reports
- Support multiple review strategies (regex, LLM, CLIP, InsightFace)

**Review Dimensions:**
```
IMAGE REVIEW:
─────────────
1. Technical Quality (0.0-1.0)
   - File exists and is valid image
   - Resolution meets minimum
   - Not corrupted, not blank
   - No obvious artifacts

2. Prompt Alignment (0.0-1.0)
   - Key prompt elements present
   - Shot type matches (establishing shows landscape, close_up shows face)
   - Characters mentioned in prompt are visible
   - Setting matches prompt description

3. Character Consistency (0.0-1.0)
   - Hair color matches character_bible.hair_color
   - Eye color matches character_bible.eye_color
   - Clothing matches character_bible.default_outfit
   - Body type matches character_bible.body_type
   - Accessories match character_bible.accessories

4. World Consistency (0.0-1.0)
   - Architecture matches world_bible.architectural_style
   - Atmosphere matches world_bible.visual_atmosphere
   - Technology level matches world_bible.technology_level
   - Color palette matches world_bible.color_palette

5. Composition (0.0-1.0)
   - Appropriate framing for shot_type
   - Rule of thirds (if applicable)
   - Subject is clear and well-positioned
   - Background is appropriate (not distracting)

AUDIO REVIEW:
─────────────
1. Technical Quality (0.0-1.0)
   - File exists and is valid audio
   - Duration > 0.5 seconds
   - File size > 1KB (not silent)
   - Sample rate is acceptable

2. Naturalness (0.0-1.0)
   - Speech sounds natural (not robotic)
   - No obvious artifacts
   - Appropriate speed and pitch

3. Emotion Match (0.0-1.0)
   - Voice emotion matches scene emotion
   - Pacing matches scene pacing
   - Volume is appropriate

4. Duration Fit (0.0-1.0)
   - Audio duration matches shot duration (±20%)
   - No awkward pauses
   - No cut-off speech

SHOT REVIEW:
────────────
- Image exists and passed review
- Audio exists and passed review
- Image and audio durations are aligned
- Combined quality score meets threshold

SCENE REVIEW:
─────────────
- All shots in scene are ready
- Narrative flow between shots is coherent
- Character appearance is consistent across shots
- World appearance is consistent across shots
- Scene pacing is appropriate
- Transitions between shots are smooth

PROJECT REVIEW:
───────────────
- All scenes are assembled
- Character consistency across entire video
- World consistency across entire video
- Narrative fidelity to novel
- Audio-video sync across video
- Overall production quality
```

**Internal Workflows:**
```
quality_reviewer
├── [1] Trigger: { project_id, entity_type, entity_id }
├── [2] Entity Router
│   └── Switch: image | audio | shot | scene | project
├── [3] Image Review Pipeline
│   ├── [3a] Load image from generation.images
│   ├── [3b] Load character_bibles for characters in shot
│   ├── [3c] Load world_bible
│   ├── [3d] Technical quality check (file validation)
│   ├── [3e] Character consistency check
│   │   ├── Method 1 (fast): regex keyword matching in prompt
│   │   ├── Method 2 (accurate): CLIP similarity between image and character prompt
│   │   └── Method 3 (best): InsightFace feature comparison with reference
│   ├── [3f] World consistency check
│   │   ├── Method 1 (fast): keyword matching in prompt
│   │   └── Method 2 (accurate): CLIP similarity
│   ├── [3g] Composition check
│   │   ├── Image not blank/corrupted
│   │   └── Appropriate shot_type composition
│   ├── [3h] Calculate composite score
│   ├── [3i] INSERT INTO reviews
│   └── [3j] Return { passed, score, issues }
├── [4] Audio Review Pipeline
│   ├── [4a] Load audio from generation.audio
│   ├── [4b] Technical quality check (file validation, duration, size)
│   ├── [4c] Duration fit check (compare to shot duration)
│   ├── [4d] Calculate composite score
│   ├── [4e] INSERT INTO reviews
│   └── [4f] Return { passed, score, issues }
├── [5] Shot Review Pipeline
│   ├── [5a] Load shot, image review, audio review
│   ├── [5b] Check both image and audio passed
│   ├── [5c] Check duration alignment
│   ├── [5d] Calculate combined score
│   ├── [5e] INSERT INTO reviews
│   └── [5f] Return { passed, score, issues }
├── [6] Scene Review Pipeline
│   ├── [6a] Load all shots in scene
│   ├── [6b] Check all shots are ready
│   ├── [6c] Check narrative flow (LLM review optional)
│   ├── [6d] Check character consistency across shots
│   ├── [6e] Check world consistency across shots
│   ├── [6f] Calculate scene score
│   ├── [6g] INSERT INTO reviews
│   └── [6h] Return { passed, score, issues }
├── [7] Project Review Pipeline
│   ├── [7a] Load all scenes, all reviews
│   ├── [7b] Character consistency across entire project
│   ├── [7c] World consistency across entire project
│   ├── [7d] Narrative fidelity (all scenes present, critical scenes included)
│   ├── [7e] Audio-video sync (narration covers all shots)
│   ├── [7f] Calculate overall score
│   ├── [7g] INSERT INTO reviews
│   └── [7h] Return { passed, score, issues, breakdown }
├── [8] Decision Handler
│   ├── Load thresholds from quality.thresholds
│   ├── Compare score against threshold
│   ├── Decision: pass | fail_repairable | fail_unrecoverable
│   └── INSERT INTO state_transitions
└── [9] Return
    └── { passed, score, issues[], recommendations[] }
```

**Observable Metrics:**
- review_total (counter, by entity_type, by result)
- review_score_distribution (histogram, by entity_type)
- review_character_consistency_avg (gauge)
- review_world_consistency_avg (gauge)
- review_prompt_alignment_avg (gauge)
- review_failure_rate (gauge, by entity_type)
- review_average_duration_ms (histogram, by entity_type)

---

### LAYER 12 — REPAIR ENGINE

**Responsibilities:**
- Analyze failed items from quality review
- Determine repair strategy for each failure type
- Execute targeted repairs (not full regeneration)
- Track repair attempts and results
- Escalate after max repair attempts
- Learn from repair outcomes
- Prefer partial repair over full regeneration

**Repair Strategy Matrix:**
```
┌─────────────────────────┬──────────────────────────────────────┬───────────┐
│ FAILURE TYPE            │ REPAIR STRATEGY                       │ MAX ATTEMPTS│
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Prompt alignment < 0.6  │ 1. Add missing keywords to prompt    │ 3         │
│                         │ 2. Simplify prompt (remove complexity)│           │
│                         │ 3. Change shot_type for better match │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Character consistency   │ 1. Expand character prompt fragment   │ 3         │
│ < 0.7                   │ 2. Add character reference image      │           │
│                         │ 3. Regenerate with reference image    │           │
│                         │ 4. Switch to character-focused model  │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ World consistency       │ 1. Expand world prompt fragment       │ 3         │
│ < 0.6                   │ 2. Add world reference image          │           │
│                         │ 3. Regenerate with reference image    │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Composition < 0.5       │ 1. Change camera_angle                │ 2         │
│                         │ 2. Change shot_type                   │           │
│                         │ 3. Add composition hints              │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Audio quality < 0.5     │ 1. Switch TTS backend                 │ 3         │
│                         │ 2. Adjust speed/pitch parameters      │           │
│                         │ 3. Split long text into chunks        │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Backend failure         │ 1. Retry same backend                 │ 2         │
│                         │ 2. Switch to fallback backend         │           │
│                         │ 3. Switch to remote worker            │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Audio-video sync        │ 1. Adjust shot duration to match      │ 2         │
│                         │ 2. Re-render clip                     │           │
├─────────────────────────┼──────────────────────────────────────┼───────────┤
│ Overall quality         │ 1. Repair individual failed shots     │ 2         │
│ < 0.6                   │ 2. Regenerate all low-score shots     │           │
│                         │ 3. Escalate to manual review          │           │
└─────────────────────────┴──────────────────────────────────────┴───────────┘
```

**Internal Workflows:**
```
repair_dispatcher
├── [1] Trigger: { project_id, failed_items[] }
├── [2] Failed Items Loader
│   └── SELECT reviews WHERE passed=FALSE AND entity_id IN ($failed_ids)
├── [3] Strategy Selector (per failed item)
│   ├── [3a] Analyze failure type from review.issues
│   ├── [3b] Check repair_attempts count
│   │   ├── If attempts >= max_retries: escalate to unrecoverable
│   │   └── If attempts < max_retries: select strategy
│   ├── [3c] Strategy selection based on failure type:
│   │   ├── prompt_alignment → regenerate_prompt
│   │   ├── character_consistency → enhance_character_prompt
│   │   ├── world_consistency → enhance_world_prompt
│   │   ├── composition → adjust_camera
│   │   ├── audio_quality → switch_backend
│   │   └── backend_failure → switch_backend
│   └── [3d] Generate repair description
├── [4] Repair Task Creator
│   ├── [4a] INSERT INTO repairs (pre_repair_score, failure_reason, strategy)
│   ├── [4b] Generate new prompt/parameters based on strategy
│   ├── [4c] INSERT INTO tasks (task_type=repair, payload=updated_params)
│   └── [4d] Dispatch to Layer 9
├── [5] Repair Execution Monitor
│   ├── [5a] Wait for repair task completion
│   ├── [5b] On completion: receive repaired asset
│   └── [5c] On failure: increment attempt count, try alternative strategy
├── [6] Post-Repair Review
│   ├── [6a] Run quality review on repaired asset (Layer 11)
│   ├── [6b] Compare post_repair_score to pre_repair_score
│   ├── [6c] If improved: mark repair as success
│   ├── [6d] If not improved: mark as failure
│   └── [6e] UPDATE repairs SET post_repair_score, improvement, success
├── [7] Escalation Handler
│   ├── [7a] If all repair strategies exhausted:
│   │   ├── Transition project to 'unrecoverable'
│   │   ├── Notify admin with detailed failure report
│   │   └── Log event: 'repair_escalation'
│   └── [7b] If repair succeeded:
│       └── Transition entity to appropriate state
├── [8] Transition
│   └── UPDATE projects SET state='repair_complete'
└── [9] Return
    └── { repaired_count, failed_count, escalated_count }
```

**Observable Metrics:**
- repair_attempts_total (counter, by strategy, by result)
- repair_success_rate (gauge, by strategy)
- repair_average_improvement (histogram, by strategy)
- repair_escalation_rate (gauge)
- repair_average_duration_ms (histogram)
- repair_cost_savings (gauge, repair vs full regeneration)

---

### LAYER 13 — VOICE ENGINE

**Responsibilities:**
- Generate narration audio for every shot
- Select appropriate voice per character
- Apply emotion-based voice parameters
- Apply speech pacing based on scene emotion
- Handle multi-character dialogue (different voices)
- Handle narration vs dialogue distinction
- Post-process audio (normalize, pad, trim)
- Support multiple TTS backends
- Fallback chain for TTS failures

**Voice Selection Logic:**
```
VOICE MAPPING:
──────────────
1. Default narration voice: configurable (default: English neutral)
2. Character voices: derived from character_bible.voice_description
   - Deep voice → lower pitch
   - High voice → higher pitch
   - Slow speech → reduced speed
   - Fast speech → increased speed
3. Emotion mapping:
   - Anger → louder, faster, higher pitch
   - Sadness → softer, slower, lower pitch
   - Fear → trembling, faster
   - Joy → brighter, moderate speed
   - Neutral → default parameters

TTS BACKEND PRIORITY:
─────────────────────
1. Edge TTS (neural quality, 75+ languages, no API key)
2. Piper (local ONNX, CPU-friendly, consistent)
3. espeak (last resort, guaranteed available)
```

**Internal Workflows:**
```
audio_generator
├── [1] Trigger: { project_id }
├── [2] Pending Audio Shots Loader
│   └── SELECT shots WHERE state='image_passed' AND narration_text IS NOT NULL
├── [3] Voice Assignment (per shot)
│   ├── [3a] If shot has dialogue: use character_bible.voice for speaking character
│   ├── [3b] If shot has narration: use default narration voice
│   ├── [3c] Apply emotion-based parameters
│   └── [3d] Select TTS backend (check health)
├── [4] Audio Generation Task
│   ├── [4a] Create task: { text, voice, speed, pitch, backend }
│   ├── [4b] Dispatch to Layer 9 (cpu_tts_worker)
│   └── [4c] Timeout: 60 seconds
├── [5] Audio Result Handler
│   ├── [5a] Save audio file to disk
│   ├── [5b] INSERT INTO generation.audio
│   ├── [5c] Measure duration
│   └── [5d] UPDATE shots SET state='audio_generated'
├── [6] Post-Processing
│   ├── [6a] Normalize audio levels (FFmpeg loudnorm)
│   ├── [6b] Add silence padding (0.5s before, 0.3s after)
│   ├── [6c] Trim if too long
│   └── [6d] Save processed version
├── [7] Duration Sync
│   ├── [7a] Compare audio duration to shot duration
│   ├── [7b] If audio > shot: extend shot.duration_seconds
│   ├── [7c] If audio < shot: add padding or extend shot
│   └── [7d] UPDATE shots SET duration_seconds
├── [8] Transition
│   └── UPDATE shots WHERE project_id=$project_id SET state='audio_generated'
└── [9] Return
    └── { audio_generated, audio_failed, total_duration }
```

**Observable Metrics:**
- voice_tasks_total (counter, by backend, by result)
- voice_average_duration_ms (histogram, by backend)
- voice_backend_fallback_count (counter)
- voice_character_voice_usage (counter, by character)
- voice_emotion_distribution (histogram, by emotion)

---

### LAYER 14 — MUSIC DIRECTOR

**Responsibilities:**
- Analyze scene mood and emotional arc
- Suggest background music genre/style per scene
- Map scene characteristics to music parameters
- Handle background music volume (duck during narration)
- Crossfade between scenes
- Support optional background music (can be disabled)
- Provide music metadata for user-sourced tracks
- Optionally generate ambient background using music generation model

**Music Parameter Mapping:**
```
SCENE EMOTION → MUSIC STYLE:
─────────────────────────────
battle/action     → epic orchestral, fast tempo, forte
romance           → soft piano/strings, slow tempo, piano
mystery           → ambient, medium tempo, mysterious
triumph           → brass fanfare, moderate tempo, fortissimo
sadness           → solo strings/cello, slow tempo, piano
fear              → dissonant, low register, tremolo
peace             → acoustic guitar, light tempo, piano
anger             → heavy percussion, fast tempo, fortissimo
neutral           → ambient pad, slow tempo, piano

SCENE IMPORTANCE → MUSIC INTENSITY:
────────────────────────────────────
critical    → full arrangement, dramatic
high        → moderate arrangement, present
normal      → light arrangement, subtle
low         → minimal, atmospheric
```

**Internal Workflows:**
```
music_suggester
├── [1] Trigger: { project_id }
├── [2] Scene Analysis
│   ├── Load all scenes with emotions and importance
│   └── Generate music profile per scene
├── [3] Music Profile Generator
│   ├── [3a] Map emotion to genre
│   ├── [3b] Map importance to intensity
│   ├── [3c] Map pacing to tempo
│   └── [3d] Store in scenes.music_profile (JSONB)
├── [4] Background Music Selection (if enabled)
│   ├── [4a] Query royalty-free music library
│   ├── [4b] Match profiles to available tracks
│   └── [4c] Assign tracks to scenes
├── [5] Mixing Parameters
│   ├── [5a] Calculate volume levels per scene
│   ├── [5b] Calculate crossfade durations
│   ├── [5c] Calculate ducking parameters
│   └── [5d] Store in scenes.music_params (JSONB)
├── [6] Transition
│   └── Log music suggestions
└── [7] Return
    └── { scenes_with_music, total_music_duration }
```

**Observable Metrics:**
- music_suggestions_total (counter, by genre)
- music_coverage_rate (gauge, scenes_with_music / total_scenes)
- music_generation_count (counter, if generation enabled)

---

### LAYER 15 — ANIMATION ENGINE

**Responsibilities:**
- Apply animation effects to static images
- Create Ken Burns effects (zoom, pan)
- Create parallax depth effects
- Create subtle motion effects (breathing, floating)
- Calculate animation parameters (focal point, speed, easing)
- Handle transition effects between shots
- Render animated clips with audio overlay
- Support multiple animation types
- Optimize animation for shot_type and emotion

**Animation Type Library:**
```
1. ken_burns_zoom_in
   - Start: 100% crop → End: 115% crop (centered on focal point)
   - Easing: ease-in-out
   - Focal point: face for close_up, horizon for establishing
   - Best for: establishing, close_up, insert

2. ken_burns_zoom_out
   - Start: 115% crop → End: 100% crop
   - Reveals context gradually
   - Best for: establishing (reversal), close_up (pull back)

3. ken_burns_pan_left
   - Start: right third → End: left third
   - Easing: linear
   - Best for: wide, establishing (directional movement)

4. ken_burns_pan_right
   - Start: left third → End: right third
   - Easing: linear
   - Best for: wide, establishing (opposite direction)

5. parallax_depth
   - Split image into foreground/midground/background
   - Move layers at different speeds (foreground faster)
   - Creates depth illusion
   - Best for: establishing, wide

6. subtle_breathing
   - Very slight zoom: 100% → 102% → 100% (cycle)
   - Creates "alive" feeling
   - Best for: medium, close_up (static moments)

7. subtle_floating
   - Slight vertical movement (up/down, 2% range)
   - Creates dreamy/ethereal feeling
   - Best for: dream sequences, flashbacks

8. none
   - Static image with audio only
   - For: extreme close_up (focus on detail), insert
```

**Animation Parameter Calculator:**
```
function calculateAnimation(shot, scene):
    # Determine animation type
    if shot.shot_type == 'establishing':
        animation = 'ken_burns_zoom_in'
    elif shot.shot_type == 'wide':
        animation = 'ken_burns_pan_right' if scene.importance != 'low' else 'ken_burns_pan_left'
    elif shot.shot_type == 'medium':
        animation = 'subtle_breathing'
    elif shot.shot_type == 'close_up':
        animation = 'ken_burns_zoom_in' if scene.primary_emotion in ['tension', 'determination'] else 'subtle_breathing'
    elif shot.shot_type == 'extreme_close_up':
        animation = 'none'
    elif shot.shot_type == 'action':
        animation = 'ken_burns_pan_right'
    else:
        animation = 'subtle_breathing'

    # Calculate parameters
    params = {
        'type': animation,
        'focal_point': determineFocalPoint(shot.characters_in_shot, shot.shot_type),
        'zoom_factor': calculateZoomFactor(shot.duration_seconds, shot.importance),
        'pan_speed': calculatePanSpeed(shot.duration_seconds, scene.pacing),
        'easing': 'ease-in-out' if animation.startswith('ken_burns') else 'linear'
    }

    return params
```

**Internal Workflows:**
```
clip_assembler
├── [1] Trigger: { project_id }
├── [2] Shot Loader
│   └── SELECT shots, images, audio WHERE state IN ('image_passed', 'audio_generated')
├── [3] Animation Planner (per shot)
│   ├── [3a] Determine animation_type from shot_type and emotion
│   ├── [3b] Calculate animation_params
│   ├── [3c] UPDATE shots SET animation_type, animation_params
│   └── [3d] Determine transition_in, transition_out
├── [4] Clip Rendering Loop
│   ├── [4a] For each shot:
│   │   ├── Create render task: { image, audio, animation, duration }
│   │   ├── Dispatch to Layer 9 (cpu_render_worker)
│   │   └── Timeout: 120 seconds
│   ├── [4b] Receive rendered clip
│   ├── [4c] Save to disk
│   ├── [4d] INSERT INTO video_clips
│   └── [4e] UPDATE shots SET state='assembled'
├── [5] Clip Validation
│   ├── [5a] Verify all clips rendered successfully
│   ├── [5b] Verify clip durations match shot durations
│   └── [5c] If any failed: trigger re-render
├── [6] Transition
│   └── UPDATE projects SET state='assembling'
└── [7] Return
    └── { clips_rendered, total_duration }
```

**Observable Metrics:**
- animation_clips_rendered_total (counter, by animation_type)
- animation_average_render_time_ms (histogram, by animation_type)
- animation_render_failure_rate (gauge)
- animation_transition_types_used (counter, by transition_type)

---

### LAYER 16 — FINAL RENDER ENGINE

**Responsibilities:**
- Concatenate all animated clips into final video
- Mix audio tracks (narration + background music)
- Apply global video settings (resolution, fps, codec)
- Apply color grading from style_bible
- Add opening title card (optional)
- Add ending credits (optional)
- Add subtitle overlay (optional)
- Apply final encode pass (quality optimization)
- Generate thumbnail
- Generate video metadata (duration, resolution, file size)

**Render Pipeline:**
```
STEP 1: Concatenation
  - Build FFmpeg concat list from all clips
  - Apply global video settings
  - Concatenate all clips into single video stream

STEP 2: Audio Mixing
  - Mix narration tracks (primary, volume 1.0)
  - Mix background music (secondary, volume 0.15-0.30)
  - Apply ducking (music volume drops during narration)
  - Apply crossfade between scenes
  - Normalize audio levels (loudnorm filter)

STEP 3: Post-Processing
  - Apply color grading (from style_bible.color_grading)
  - Apply brightness/contrast adjustments
  - Apply saturation adjustments
  - Add opening title card (if configured)
  - Add ending credits (if configured)
  - Add subtitle overlay (if configured)

STEP 4: Final Encode
  - Codec: H.264 (libx264) or H.265 (libx265)
  - Preset: medium (quality/speed balance)
  - CRF: 18 (high quality)
  - Audio: AAC 256kbps
  - movflags: +faststart (web optimization)

STEP 5: Thumbnail Generation
  - Extract frame at 10% of video duration
  - Apply slight enhancement (brightness, contrast)
  - Save as JPEG

STEP 6: Metadata Generation
  - Duration, resolution, file size
  - Codec information
  - Bitrate
  - Scene/shot counts
```

**Internal Workflows:**
```
video_renderer
├── [1] Trigger: { project_id }
├── [2] Clip Loader
│   └── SELECT video_clips WHERE project_id=$project_id ORDER BY shot order
├── [3] FFmpeg Command Builder
│   ├── [3a] Build concat list file
│   ├── [3b] Build FFmpeg command:
│   │   ffmpeg -f concat -safe 0 -i concat.txt \
│   │     -i background_music.mp3 \
│   │     -filter_complex "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[a]" \
│   │     -map 0:v -map "[a]" \
│   │     -c:v libx264 -preset medium -crf 18 \
│   │     -c:a aac -b:a 256k \
│   │     -movflags +faststart \
│   │     -y output.mp4
│   └── [3c] Validate command
├── [4] Render Task Dispatch
│   ├── [4a] Create task: { ffmpeg_command, input_files, output_path }
│   ├── [4b] Dispatch to Layer 9 (cpu_render_worker)
│   └── [4c] Timeout: 600 seconds (10 minutes)
├── [5] Render Monitor
│   ├── [5a] Poll task status or wait for webhook
│   ├── [5b] Handle timeout (retry or escalate)
│   └── [5c] Handle failure (retry with different settings)
├── [6] Post-Render Processing
│   ├── [6a] Verify output file exists
│   ├── [6b] Extract metadata (ffprobe)
│   ├── [6c] Generate thumbnail (ffmpeg -ss 10% -frames:v 1)
│   └── [6d] Calculate file size
├── [7] Final Video Persister
│   ├── [7a] INSERT INTO final_videos (all metadata)
│   └── [7b] UPDATE projects SET state='assembled'
├── [8] Final Review Trigger
│   ├── [8a] HTTP POST to final_reviewer workflow
│   └── [8b] Body: { project_id, video_id }
└── [9] Return
    └── { video_path, duration, file_size, resolution }
```

**Observable Metrics:**
- render_total (counter, by result)
- render_duration_seconds (histogram)
- render_file_size_bytes (histogram)
- render_ffmpeg_exit_code (counter)
- render_retry_count (counter)

---

### LAYER 17 — SUPER RESOLUTION LAYER

**Responsibilities:**
- Upscale low-resolution generated images
- Enhance image detail and sharpness
- Remove generation artifacts
- Apply face restoration (optional)
- Apply overall image enhancement
- Support optional activation (only when images are below resolution threshold)

**Super Resolution Strategy:**
```
WHEN TO ACTIVATE:
─────────────────
- Generated image width < target_width (1920)
- Generated image height < target_height (1080)
- Image quality score < 0.7 (needs enhancement)
- User requests higher quality output

UPSCALE PIPELINE:
─────────────────
1. Detect source resolution
2. Calculate upscale factor (2x or 4x)
3. Apply Real-ESRGAN upscale
4. Apply face restoration (optional, GFPGAN)
5. Apply sharpening (unsharp mask)
6. Resize to final target resolution
7. Quality check on upscaled image
```

**Internal Workflows:**
```
super_resolution (triggered conditionally)
├── [1] Trigger: { image_id, target_resolution }
├── [2] Image Loader
│   └── Load image, check current resolution
├── [3] Upscale Decision
│   ├── If current >= target: skip (return original)
│   └── If current < target: proceed with upscale
├── [4] Upscale Task
│   ├── [4a] Create task: { image_path, upscale_factor, model: 'Real-ESRGAN' }
│   ├── [4b] Dispatch to Layer 10 (super_resolution_worker)
│   └── [4c] Timeout: 120 seconds
├── [5] Post-Processing
│   ├── [5a] Resize to exact target resolution
│   ├── [5b] Apply optional face restoration
│   ├── [5c] Apply sharpening
│   └── [5d] Save upscaled image
├── [6] Quality Check
│   ├── [6a] Verify upscaled image quality
│   └── [6b] If degraded: revert to original
└── [7] Return
    └── { upscaled_path, original_resolution, new_resolution }
```

**Observable Metrics:**
- super_res_total (counter, by result)
- super_res_average_duration_ms (histogram)
- super_res_quality_improvement (histogram)

---

### LAYER 18 — AUTO REVIEWER

**Responsibilities:**
- Perform final review of assembled video
- Check character consistency across entire video
- Check world consistency across entire video
- Check audio-video synchronization
- Check narrative fidelity
- Calculate overall quality score
- Make approve/reject/repair decision
- Generate detailed review report
- Support auto-approve for high-quality results
- Support manual review escalation

**Review Score Calculation:**
```
FINAL VIDEO SCORE:
──────────────────
overall = (character_consistency * 0.25) +
          (world_consistency * 0.20) +
          (narrative_fidelity * 0.25) +
          (audio_video_sync * 0.20) +
          (production_quality * 0.10)

DECISION THRESHOLDS:
────────────────────
overall >= 0.85 → AUTO-APPROVE (no manual review needed)
overall >= 0.60 → APPROVE (meets quality bar)
overall >= 0.30 → REPAIR (send to repair engine)
overall < 0.30  → REJECT (escalate to manual review or abort)
```

**Internal Workflows:**
```
final_reviewer
├── [1] Trigger: { project_id, video_id }
├── [2] Video Metadata Loader
│   └── Load video, all reviews, all shots, all scenes
├── [3] Character Consistency Check
│   ├── [3a] For each character:
│   │   ├── Count shots where character appears
│   │   ├── Count shots where character reference was included in prompt
│   │   ├── Calculate inclusion rate
│   │   └── Verify reference image was used consistently
│   └── [3b] Score: average inclusion rate across all characters
├── [4] World Consistency Check
│   ├── [4a] For each major location:
│   │   ├── Count shots at location
│   │   ├── Count shots where world reference was included
│   │   └── Verify visual keywords are consistent
│   └── [4b] Score: average inclusion rate across all locations
├── [5] Narrative Fidelity Check
│   ├── [5a] Verify all scenes are represented
│   ├── [5b] Verify all critical scenes are present
│   ├── [5c] Verify story arc is preserved
│   └── [5d] Score: coverage percentage
├── [6] Audio-Video Sync Check
│   ├── [6a] Verify narration covers all shots
│   ├── [6b] Verify audio durations match video durations
│   └── [6c] Score: sync percentage
├── [7] Production Quality Check
│   ├── [7a] Average shot quality score
│   ├── [7b] Average audio quality score
│   └── [7c] Score: average of averages
├── [8] Overall Score Calculator
│   ├── [8a] Calculate weighted overall score
│   └── [8b] INSERT INTO reviews
├── [9] Decision Handler
│   ├── [9a] If overall >= 0.85: auto-approve
│   │   ├── UPDATE final_videos SET state='approved'
│   │   └── Trigger delivery_handler
│   ├── [9b] If overall >= 0.60: approve
│   │   ├── UPDATE final_videos SET state='approved'
│   │   └── Trigger delivery_handler
│   ├── [9c] If overall >= 0.30: repair
│   │   ├── Identify lowest-scoring components
│   │   ├── Trigger repair_dispatcher
│   │   └── After repair: re-review
│   └── [9d] If overall < 0.30: reject
│       ├── UPDATE final_videos SET state='rejected'
│       ├── Notify admin with detailed report
│       └── Provide options: retry from shot_planning, manual intervention
├── [10] Report Generator
│   ├── [10a] Generate detailed review report
│   ├── [10b] Include: scores, issues, recommendations
│   └── [10c] Store in reviews.recommendations
└── [11] Return
    └── { passed, overall_score, breakdown, issues[], recommendations[] }
```

**Observable Metrics:**
- final_review_total (counter, by decision)
- final_review_score_distribution (histogram)
- final_review_auto_approve_rate (gauge)
- final_review_repair_rate (gauge)
- final_review_reject_rate (gauge)
- final_review_average_duration_ms (histogram)

---

### LAYER 19 — LEARNING ENGINE

**Responsibilities:**
- Analyze completed projects for patterns
- Extract lessons learned
- Update quality thresholds based on outcomes
- Update backend preference rankings
- Update prompt strategies based on quality scores
- Track performance metrics over time
- Identify systemic issues
- Recommend configuration changes
- Support A/B testing of strategies
- Build knowledge base of successful patterns

**Learning Data Collection:**
```
PER PROJECT:
────────────
- Total processing time
- Time per phase
- Quality scores per shot, scene, project
- Repair attempts and outcomes
- Backend usage and success rates
- Prompt patterns and their quality scores
- Shot types and their quality scores
- Character reference effectiveness
- World reference effectiveness
- User feedback (if provided)
```

**Internal Workflows:**
```
learning_engine
├── [1] Trigger: { project_id }
├── [2] Project Data Loader
│   └── Load all project data: shots, images, audio, reviews, repairs, workers, timing
├── [3] Performance Analyzer
│   ├── [3a] Calculate actual vs estimated metrics
│   ├── [3b] Identify slowest phases
│   ├── [3c] Identify most-used backends
│   ├── [3d] Identify repair hotspots
│   └── [3e] Identify highest/lowest quality shots
├── [4] Prompt Performance Analyzer
│   ├── [4a] Correlate prompt elements with quality scores
│   ├── [4b] Identify which patterns produce best results
│   ├── [4c] Identify which shot_types have highest quality
│   └── [4d] Identify character/world prompt effectiveness
├── [5] Backend Performance Analyzer
│   ├── [5a] Compare success rates across backends
│   ├── [5b] Compare quality scores across backends
│   ├── [5c] Compare speed across backends
│   └── [5d] Update backend preference rankings
├── [6] Threshold Tuner
│   ├── [6a] If quality consistently high: consider raising thresholds
│   ├── [6b] If repair rate high: consider lowering thresholds
│   ├── [6c] Adjust based on learning from multiple projects
│   └── [6d] Update system_config (with safety bounds)
├── [7] Lessons Extractor
│   ├── [7a] LLM analysis of performance data
│   ├── [7b] Extract: what worked, what didn't, what to try
│   └── [7c] Store in learning_data.lessons
├── [8] Knowledge Base Update
│   ├── [8a] Add project patterns to knowledge base
│   ├── [8b] Update prompt strategy recommendations
│   └── [8c] Update backend strategy recommendations
├── [9] Learning Data Persister
│   └── INSERT INTO learning_data (all analysis results)
└── [10] Return
    └── { lessons_learned, recommendations[], config_updates[] }
```

**Observable Metrics:**
- learning_projects_analyzed (counter)
- learning_threshold_adjustments (counter)
- learning_backend_re rankings (counter)
- learning_prompt_strategy_updates (counter)
- learning_average_quality_trend (gauge, over time)

---

### LAYER 20 — TELEGRAM DELIVERY LAYER

**Responsibilities:**
- Deliver final video to user via Telegram
- Send progress updates during production
- Send quality report after completion
- Send error notifications on failure
- Handle video file size limits (Telegram: 50MB for bots)
- Handle video compression for large files
- Support multiple delivery formats
- Handle delivery failures (retry, notification)
- Archive delivered content
- Support user feedback collection

**Delivery Protocol:**
```
PROGRESS UPDATES:
─────────────────
- Throttled: max 1 update per 30 seconds
- Format: "📊 Phase: {phase} | Progress: {progress}% | Status: {status}"
- Include: current phase, percentage, estimated time remaining
- Include: quality scores (if available)

FINAL DELIVERY:
───────────────
1. Check video file size
   - If <= 50MB: send directly
   - If > 50MB: compress or split
2. Generate delivery report:
   - Title, duration, scenes, shots
   - Quality scores breakdown
   - Processing time
   - Backend usage summary
3. Send video with report as caption
4. Send quality report as follow-up message
5. Ask for user feedback (optional)

FAILURE NOTIFICATION:
─────────────────────
- Send error message with details
- Include: failed phase, error description
- Include: options (retry, cancel, contact admin)
- Include: what was completed so far
```

**Internal Workflows:**
```
delivery_handler
├── [1] Trigger: { project_id }
├── [2] Video Loader
│   └── SELECT final_videos WHERE project_id=$project_id AND state='approved'
├── [3] File Size Check
│   ├── [3a] If file_size <= 50MB: proceed to send
│   └── [3b] If file_size > 50MB:
│       ├── Compress video (reduce bitrate, CRF)
│       ├── If still > 50MB: split into parts
│       └── Send multiple files
├── [4] Report Generator
│   ├── [4a] Build delivery report:
│   │   - Title, duration, scene_count, shot_count
│   │   - Quality scores (character, world, narrative, audio, overall)
│   │   - Processing time
│   │   - Backend usage summary
│   │   - File size and resolution
│   └── [4b] Format as Telegram message (markdown)
├── [5] Video Sender
│   ├── [5a] Telegram Send Video
│   │   - video: file_path
│   │   - caption: delivery report
│   │   - supports_streaming: true
│   └── [5b] If send fails: retry up to 3 times
├── [6] Quality Report Sender
│   ├── [6a] Telegram Send Message
│   │   - Detailed quality breakdown
│   │   - Character consistency report
│   │   - World consistency report
│   │   - Scene-by-scene summary
│   └── [6b] Format as readable message
├── [7] Archive
│   ├── [7a] UPDATE projects SET state='delivered', completed_at=NOW()
│   ├── [7b] UPDATE final_videos SET state='delivered'
│   └── [7c] INSERT INTO state_transitions
├── [8] Learning Trigger
│   ├── [8a] HTTP POST to learning_engine workflow
│   └── [8b] Body: { project_id }
├── [9] Feedback Request (optional)
│   ├── [9a] Telegram Send Message: "How was the result? Reply with 1-5 stars"
│   └── [9b] Store feedback in projects.metadata
└── [10] Return
    └── { delivered, file_size, delivery_time_ms }
```

**Observable Metrics:**
- delivery_total (counter, by result)
- delivery_file_size_bytes (histogram)
- delivery_duration_ms (histogram)
- delivery_compression_count (counter)
- delivery_split_count (counter)
- delivery_retry_count (counter)
- delivery_user_feedback_avg (gauge)

---

## 4. DEPLOYMENT TOPOLOGY

### 4.1 Single-Node Deployment (Development / Weak Machine)

```
┌─────────────────────────────────────────────────────────────┐
│                     SINGLE MACHINE                            │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   n8n    │  │PostgreSQL│  │  Redis   │  │ Telegram │   │
│  │ :5678    │  │ :5432    │  │ :6379    │  │   Bot    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LOCAL WORKER (all types)                  │   │
│  │  Image Gen | TTS | Render | Review | Super-Res        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────┐                                               │
│  │  Ollama  │  (optional, for LLM tasks)                    │
│  │ :11434   │                                               │
│  └──────────┘                                               │
│                                                              │
│  Resources: 4GB RAM, 2 CPU cores (minimum)                  │
│  Heavy tasks: dispatched to remote workers (optional)        │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Multi-Node Deployment (Production)

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATION NODE                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   n8n    │  │PostgreSQL│  │  Redis   │  │ Telegram │   │
│  │ :5678    │  │ :5432    │  │ :6379    │  │   Bot    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  Resources: 4GB RAM, 2 CPU cores                             │
│  Network: needs connectivity to all worker nodes             │
└───────────┬──────────────────┬──────────────────┬───────────┘
            │                  │                  │
     ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │  GPU NODE   │  │  CPU NODE   │  │  CPU NODE   │
     │             │  │             │  │  (remote)   │
     │ Image Gen   │  │ TTS         │  │             │
     │ Super-Res   │  │ Render      │  │ TTS         │
     │ Review      │  │ Review      │  │ Render      │
     │             │  │             │  │             │
     │ 8GB RAM     │  │ 4GB RAM     │  │ 4GB RAM     │
     │ NVIDIA GPU  │  │ 4 CPU cores │  │ 4 CPU cores │
     │ 8GB VRAM    │  │             │  │             │
     └─────────────┘  └─────────────┘  └─────────────┘
```

### 4.3 Cloud Deployment (Scalable)

```
┌─────────────────────────────────────────────────────────────┐
│                     CLOUD VM (Orchestration)                   │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │   n8n    │  │PostgreSQL│  │  Redis   │                   │
│  │ (Docker) │  │ (Docker) │  │ (Docker) │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
│                                                              │
│  ┌──────────┐                                               │
│  │ Telegram │                                               │
│  │   Bot    │                                               │
│  └──────────┘                                               │
└───────────┬──────────────────────────────────────────────────┘
            │ (API calls / webhooks)
            │
┌───────────▼──────────────────────────────────────────────────┐
│              GPU CLOUD INSTANCES (auto-scaling)                │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ GPU #1   │  │ GPU #2   │  │ GPU #3   │  │ GPU #N   │   │
│  │ Image Gen│  │ Image Gen│  │ Super-Res│  │ ...      │   │
│  │ Review   │  │ Review   │  │ Review   │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  Auto-scaling: based on queue depth                          │
│  Max instances: configurable                                 │
│  Spot instances: supported (for cost savings)                │
└──────────────────────────────────────────────────────────────┘
```

### 4.4 Docker Compose (Production-Ready)

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  # ── Orchestration ──────────────────
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
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
      - GENERIC_TIMEZONE=UTC
      - N8N_LOG_LEVEL=info
      - EXECUTIONS_MODE=regular
      - QUEUE_BULL_REDIS_HOST=redis
      - QUEUE_BULL_REDIS_PORT=6379
    volumes:
      - n8n_data:/home/node/.n8n
      - ./n8n/workflows:/home/node/workflows
      - ./n8n/credentials:/home/node/credentials
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:5678/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ── Database ───────────────────────
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=cineos
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/01-init.sql
      - ./sql/seed:/docker-entrypoint-initdb.d/02-seed.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d cineos"]
      interval: 10s
      timeout: 5s
      retries: 5
    shm_size: '256mb'

  # ── Queue / Cache ──────────────────
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── Telegram Bot ───────────────────
  telegram_bot:
    build:
      context: .
      dockerfile: Dockerfile.bot
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - N8N_WEBHOOK_URL=http://n8n:5678/webhook
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
      - LOG_LEVEL=info
    volumes:
      - ./logs/bot:/app/logs
    depends_on:
      n8n:
        condition: service_healthy
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ── Local GPU Worker ───────────────
  local_gpu_worker:
    build:
      context: .
      dockerfile: Dockerfile.gpu-worker
    restart: unless-stopped
    environment:
      - WORKER_TYPE=gpu_image
      - WORKER_NAME=local_gpu
      - WORKER_HOST=local_gpu_worker
      - WORKER_PORT=8081
      - ORCHESTRATOR_URL=http://n8n:5678
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
      - OLLAMA_HOST=http://host.docker.internal:11434
      - CUDA_VISIBLE_DEVICES=0
      - MAX_CONCURRENT_TASKS=1
      - WORKER_PRIORITY=1
    volumes:
      - worker_data:/app/data
      - ./generated:/app/generated
      - models_cache:/app/models
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    profiles:
      - gpu

  # ── Local CPU Worker ───────────────
  local_cpu_worker:
    build:
      context: .
      dockerfile: Dockerfile.cpu-worker
    restart: unless-stopped
    environment:
      - WORKER_TYPE=cpu_all
      - WORKER_NAME=local_cpu
      - WORKER_HOST=local_cpu_worker
      - WORKER_PORT=8082
      - ORCHESTRATOR_URL=http://n8n:5678
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/cineos
      - MAX_CONCURRENT_TASKS=2
      - WORKER_PRIORITY=1
    volumes:
      - worker_data:/app/data
      - ./generated:/app/generated
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 4G

  # ── Nginx Reverse Proxy (optional) ─
  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - n8n
      - telegram_bot
    profiles:
      - reverse-proxy

volumes:
  n8n_data:
    driver: local
  postgres_data:
    driver: local
  redis_data:
    driver: local
  worker_data:
    driver: local
  models_cache:
    driver: local
```

---

## 5. REMOTE EXECUTION DESIGN

### 5.1 Worker Communication Protocol

```
ORCHESTRATOR → WORKER:
──────────────────────

HTTP POST /api/tasks/execute
Headers:
  Authorization: Bearer {worker_token}
  Content-Type: application/json
Body:
{
  "task_id": "uuid",
  "task_type": "generate_image",
  "payload": {
    "shot_id": "uuid",
    "positive_prompt": "...",
    "negative_prompt": "...",
    "width": 1024,
    "height": 1024,
    "seed": 42,
    "backend": "local_gpu"
  },
  "timeout_ms": 120000,
  "project_id": "uuid"
}

WORKER → ORCHESTRATOR:
──────────────────────

HTTP POST /api/tasks/{task_id}/complete
Headers:
  Authorization: Bearer {worker_token}
  Content-Type: application/json
Body:
{
  "task_id": "uuid",
  "state": "completed",
  "result": {
    "image_path": "/app/generated/images/shot_uuid.png",
    "seed": 42,
    "generation_time_ms": 15000,
    "backend_used": "local_gpu"
  },
  "worker_id": "uuid"
}

On failure:
HTTP POST /api/tasks/{task_id}/failed
Body:
{
  "task_id": "uuid",
  "state": "failed",
  "error": {
    "message": "CUDA out of memory",
    "code": "GPU_OOM",
    "recoverable": true
  },
  "worker_id": "uuid"
}
```

### 5.2 Worker Health Check Protocol

```
HEARTBEAT:
──────────

HTTP POST /api/workers/heartbeat
Headers:
  Authorization: Bearer {worker_token}
Body:
{
  "worker_id": "uuid",
  "status": "idle" | "busy" | "overloaded",
  "current_load": 0.5,
  "current_task_id": "uuid" | null,
  "metrics": {
    "tasks_completed": 42,
    "tasks_failed": 2,
    "avg_task_duration_ms": 15000,
    "gpu_memory_used_mb": 4096,
    "gpu_memory_total_mb": 8192,
    "cpu_usage_percent": 45.0,
    "ram_usage_percent": 60.0
  }
}

HEALTH CHECK RESPONSE:
──────────────────────

HTTP GET /api/workers/{worker_id}/health
Response:
{
  "worker_id": "uuid",
  "status": "healthy",
  "last_heartbeat": "2026-07-25T10:30:00Z",
  "uptime_seconds": 3600,
  "capabilities": ["image_generation", "super_resolution"],
  "supported_backends": ["local_gpu", "pollinations"]
}
```

### 5.3 Task Queue Architecture

```
POSTGRESQL-BASED QUEUE:
───────────────────────

Table: cineos.execution.tasks

States:
  pending → queued → assigned → running → completed/failed/cancelled

Processing:
  1. Worker polls: SELECT * FROM tasks WHERE state='pending' AND task_type=$type ORDER BY priority LIMIT 1
  2. Worker claims: UPDATE tasks SET state='assigned', assigned_worker_id=$worker_id WHERE id=$task_id AND state='pending'
  3. If affected_rows = 0: another worker claimed it (retry)
  4. Worker executes task
  5. Worker reports result

Priority Queue:
  - Tasks ordered by priority (1=highest, 9=lowest)
  - Within same priority: FIFO (created_at ascending)
  - Critical repairs get priority 1
  - Normal generation gets priority 3-5
  - Learning gets priority 8

Retry Logic:
  - On failure: increment retry_count
  - If retry_count < max_retries: state → pending (requeue)
  - If retry_count >= max_retries: state → failed (permanent)
  - Exponential backoff: wait_time = base_delay * 2^retry_count
  - Max backoff: 5 minutes

Timeout Logic:
  - Each task has timeout_ms
  - On timeout: task state → failed (timeout)
  - Worker notified of cancellation
  - Task requeued if retryable
```

### 5.4 Worker Auto-Scaling (Cloud)

```
SCALING RULES:
──────────────

Scale UP:
  - Queue depth > 10 pending tasks for 2+ minutes
  - All existing workers are busy
  - New worker instance started
  - Worker registers with orchestrator

Scale DOWN:
  - Queue depth < 2 for 10+ minutes
  - Workers idle for 10+ minutes
  - Worker gracefully shuts down
  - Worker deregisters from orchestrator

Scaling Constraints:
  - Min instances: 0 (can run with zero remote workers)
  - Max instances: configurable (default: 4)
  - Cooldown: 5 minutes between scaling events
  - Cost awareness: prefer spot instances (cloud)

Worker Types Scaling:
  - GPU workers: scale based on image generation queue
  - CPU workers: scale based on render + TTS queue
  - Vision workers: scale based on review queue
```

### 5.5 Failover Protocol

```
FAILOVER SEQUENCE:
──────────────────

1. DETECT FAILURE
   - Worker heartbeat missed for > 90 seconds
   - OR task timeout exceeded
   - OR worker returned error with recoverable=true

2. MARK WORKER OFFLINE
   - UPDATE workers SET status='offline' WHERE id=$worker_id
   - Log event: 'worker_offline'

3. REASSIGN PENDING TASKS
   - SELECT tasks WHERE assigned_worker_id=$worker_id AND state IN ('assigned', 'running')
   - For each task:
     - UPDATE tasks SET state='pending', assigned_worker_id=NULL
     - Log event: 'task_reassigned'

4. REASSIGN TO ALTERNATIVE WORKER
   - For each reassigned task:
     - Select new worker using selection algorithm
     - If new worker available: assign and dispatch
     - If no worker available: leave in queue

5. NOTIFY ADMIN (if critical)
   - If all workers of a type are offline:
     - Send Telegram notification
     - Log event: 'all_workers_offline'
     - Offer: retry later, add worker, manual intervention

6. RECOVERY
   - When worker comes back online:
     - Worker registers with orchestrator
     - Worker starts processing queued tasks
     - Orchestrator updates worker status to 'idle'
```

---

## 6. INTER-LAYER COMMUNICATION MATRIX

```
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ FROM \ TO │ Layer 2  │ Layer 3  │ Layer 4  │ Layer 5  │ Layer 6  │
│          │ Orchestr │ StateMac │ Memory   │ StoryInt │ BibleBld │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 1  │ webhook  │    -     │ INSERT   │    -     │    -     │
│ Intake   │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 2  │    -     │ transition│ UPDATE  │ webhook  │ webhook  │
│ Orchestr │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 3  │ callback │    -     │ INSERT   │    -     │    -     │
│ StateMac │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 4  │ callback │ validate │    -     │    -     │    -     │
│ Memory   │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 5  │ callback │    -     │ INSERT   │    -     │ webhook  │
│ StoryInt │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 6  │ callback │    -     │ INSERT   │    -     │    -     │
│ BibleBld │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 7  │ callback │    -     │ INSERT   │    -     │    -     │
│ Planning │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 8  │ callback │    -     │ UPDATE   │    -     │    -     │
│ Prompt   │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 9  │ callback │    -     │ INSERT   │    -     │    -     │
│ JobDisp  │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 10 │ webhook  │    -     │ UPDATE   │    -     │    -     │
│ Remote   │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 11 │ callback │    -     │ INSERT   │    -     │    -     │
│ Quality  │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 12 │ callback │    -     │ INSERT   │    -     │    -     │
│ Repair   │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 13-17│ callback│    -     │ INSERT   │    -     │    -     │
│ Gen/Render│         │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 18 │ callback │    -     │ INSERT   │    -     │    -     │
│ Reviewer │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 19 │ callback │    -     │ UPDATE   │    -     │    -     │
│ Learning │          │          │          │          │          │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Layer 20 │ callback │    -     │ UPDATE   │    -     │    -     │
│ Delivery │          │          │          │          │          │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

**Key:**
- `webhook` = HTTP POST to n8n workflow endpoint
- `callback` = HTTP POST to orchestrator's result webhook
- `INSERT` = direct PostgreSQL write (through Layer 4)
- `UPDATE` = direct PostgreSQL write (through Layer 4)
- `transition` = state transition request (through Layer 3)
- `validate` = state transition validation (through Layer 3)
- `-` = no direct communication (goes through database)

---

## 7. DEPENDENCY GRAPH

```
LAYER DEPENDENCIES (strict):
────────────────────────────

Layer 1 (Intake)          → Layer 4 (Memory)
Layer 2 (Orchestrator)    → Layer 3 (State), Layer 4 (Memory), Layer 20 (Delivery)
Layer 3 (State Machine)   → Layer 4 (Memory)
Layer 4 (Memory)          → (PostgreSQL only)
Layer 5 (Story Intel)     → Layer 4 (Memory)
Layer 6 (Bible Builder)   → Layer 4 (Memory), Layer 5 (Story Intel outputs)
Layer 7 (Planning)        → Layer 4 (Memory), Layer 6 (Bible outputs)
Layer 8 (Prompt Director) → Layer 4 (Memory), Layer 6 (Bible outputs), Layer 7 (Shot plan)
Layer 9 (Job Dispatch)    → Layer 4 (Memory), Layer 10 (Workers)
Layer 10 (Remote Exec)    → Layer 9 (Tasks)
Layer 11 (Quality AI)     → Layer 4 (Memory), Layer 10 (Generated assets)
Layer 12 (Repair)         → Layer 4 (Memory), Layer 9 (Tasks), Layer 11 (Reviews)
Layer 13-17 (Generation)  → Layer 9 (Tasks), Layer 4 (Memory)
Layer 18 (Auto Reviewer)  → Layer 4 (Memory), Layer 11 (Reviews)
Layer 19 (Learning)       → Layer 4 (Memory)
Layer 20 (Delivery)       → Layer 4 (Memory)

CRITICAL PATH:
──────────────
Layer 1 → Layer 2 → Layer 3 → Layer 5 → Layer 6 → Layer 7 → Layer 8 →
Layer 9 → Layer 10 → Layer 13/14 → Layer 11 → Layer 12 (if needed) →
Layer 15 → Layer 16 → Layer 18 → Layer 20 → Layer 19
```

---

## 8. FAILURE MODES AND RECOVERY

```
┌─────────────────────────┬──────────────────────────────────────┬────────────────────┐
│ FAILURE MODE            │ DETECTION                             │ RECOVERY            │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ n8n crash               │ Heartbeat timeout (if monitored)     │ Restart n8n, all   │
│                         │                                      │ state in PostgreSQL │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ PostgreSQL crash        │ Connection refused                   │ Restart PostgreSQL, │
│                         │                                      │ WAL recovery        │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Worker crash            │ Heartbeat timeout, task timeout      │ Reassign tasks,    │
│                         │                                      │ restart worker     │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ GPU OOM                 │ Worker error response                │ Retry on CPU,      │
│                         │                                      │ reduce resolution  │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ LLM timeout             │ Ollama response timeout              │ Retry with backoff,│
│                         │                                      │ switch model       │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Backend quota exceeded  │ API error response                   │ Switch to fallback │
│                         │                                      │ backend            │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Disk full               │ Write error                          │ Clean temp files,  │
│                         │                                      │ alert admin        │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Network partition       │ Worker unreachable                   │ Mark offline,      │
│                         │                                      │ reassign tasks     │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ State deadlock          │ No progress for 30+ minutes          │ Auto-pause,        │
│                         │                                      │ alert admin        │
├─────────────────────────┼──────────────────────────────────────┼────────────────────┤
│ Quality degradation     │ Review scores declining              │ Repair engine,     │
│                         │                                      │ threshold tuning   │
└─────────────────────────┴──────────────────────────────────────┴────────────────────┘
```

---

## 9. SECURITY CONSIDERATIONS

```
AUTHENTICATION:
───────────────
- n8n: Basic auth + optional OAuth
- Workers: Token-based auth (Bearer tokens)
- PostgreSQL: Role-based access (separate roles for n8n, workers, bot)
- Telegram: User whitelist (ALLOWED_USERS)

DATA PROTECTION:
────────────────
- All data stored locally (no external APIs for data)
- PostgreSQL: encrypted at rest (if needed)
- Files: stored on local disk
- Logs: no sensitive data logged
- API keys: never in logs or database

NETWORK:
────────
- Internal communication: Docker network (isolated)
- External: only Telegram API and optional image backends
- Workers: can be on private network
- VPN recommended for remote workers

PROMPT INJECTION DEFENSE:
─────────────────────────
- LLM prompts are constructed from structured data, not raw user input
- User text is analyzed, not used as prompt directly
- All LLM outputs are validated before use
- Character/world data is sanitized before inclusion in prompts
```

---

*End of Part 2 — Complete System Architecture, Layer Model, Deployment Topology, and Remote Execution Design*
