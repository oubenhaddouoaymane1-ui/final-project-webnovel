# PART 4 — N8N WORKFLOW ARCHITECTURE, ORCHESTRATION, WORKFLOW DECOMPOSITION, EXECUTION MODEL, RETRY, RESUME, AND REMOTE JOB MANAGEMENT

## CineOS — Complete n8n Workflow Specification

---

## 1. N8N DESIGN PHILOSOPHY

n8n is the Production Operating System Kernel.

n8n is NOT an AI engine.
n8n is NOT an image generator.
n8n is NOT a renderer.

n8n is the orchestration platform responsible for coordinating every subsystem.

**n8n Responsibilities:**
- Workflow Orchestration
- State Machine Control
- Task Scheduling
- Event Routing
- Database Coordination
- Retry Management
- Resume Management
- Remote Worker Dispatch
- Progress Tracking
- Error Recovery
- Telegram Communication
- Learning Coordination

Heavy AI computation must NEVER execute inside n8n.

---

## 2. WORKFLOW ARCHITECTURE PRINCIPLES

```
PRINCIPLE 1: One workflow = one responsibility.
PRINCIPLE 2: Master Orchestrator controls everything.
PRINCIPLE 3: PostgreSQL is always updated first.
PRINCIPLE 4: State Machine controls execution.
PRINCIPLE 5: Heavy tasks are dispatched to workers.
PRINCIPLE 6: No workflow bypasses orchestration.
PRINCIPLE 7: Every workflow is resumable.
PRINCIPLE 8: Every workflow is retryable.
PRINCIPLE 9: Every workflow is independently deployable.
PRINCIPLE 10: Every workflow is importable as independent JSON.
PRINCIPLE 11: Every workflow is observable.
PRINCIPLE 12: Every workflow reports progress.
PRINCIPLE 13: Every workflow emits events.
PRINCIPLE 14: Every workflow validates inputs.
PRINCIPLE 15: Every workflow validates outputs.
```

**Workflow Count:** 30 independent workflows

**Workflow Communication:** Through PostgreSQL only. Never direct invocation. Never Execute Workflow nodes between production workflows. Only the Master Orchestrator may trigger workflows.

---

## 3. WORKFLOW INVENTORY

```
┌──────┬──────────────────────────────┬──────────────────────────────────────────────┐
│ NUM  │ WORKFLOW NAME                │ RESPONSIBILITY                               │
├──────┼──────────────────────────────┼──────────────────────────────────────────────┤
│ 001  │ telegram_intake              │ Receive Telegram input, create project       │
│ 002  │ project_orchestrator         │ Master state machine controller              │
│ 003  │ project_validator            │ Validate project input                       │
│ 004  │ story_parser                 │ Split novel into chapters and scenes         │
│ 005  │ story_intelligence           │ Deep narrative analysis                      │
│ 006  │ story_bible_builder          │ Build all 5 bibles                           │
│ 007  │ character_engine             │ Character extraction, DNA, references        │
│ 008  │ world_engine                 │ World extraction, bible, references          │
│ 009  │ timeline_engine              │ Timeline construction and validation         │
│ 010  │ scene_planner                │ Scene-level production planning              │
│ 011  │ shot_planner                 │ Shot-level cinematic planning                │
│ 012  │ fight_director               │ Combat sequence choreography                 │
│ 013  │ emotion_director             │ Emotional cinematography adjustment          │
│ 014  │ prompt_builder               │ Structured prompt generation from DB memory  │
│ 015  │ job_dispatcher               │ Create jobs, assign priority, select worker   │
│ 016  │ remote_worker_manager        │ Worker registry, health, failover            │
│ 017  │ image_generation             │ Image generation dispatch and collection     │
│ 018  │ quality_ai                   │ Asset review and scoring                     │
│ 019  │ repair_engine                │ Targeted repair of failed assets             │
│ 020  │ voice_engine                 │ TTS narration generation                     │
│ 021  │ music_director               │ Music planning and cue assignment             │
│ 022  │ animation_engine             │ Motion and effect generation                 │
│ 023  │ render_manager               │ FFmpeg video assembly                        │
│ 024  │ super_resolution             │ Image upscaling                              │
│ 025  │ final_review                 │ Complete production review                   │
│ 026  │ delivery                     │ Telegram delivery                            │
│ 027  │ learning_engine              │ Post-project analysis                        │
│ 028  │ worker_monitor               │ Worker health monitoring                     │
│ 029  │ system_monitor               │ System health monitoring                     │
│ 030  │ admin_tools                  │ Admin intervention tools                     │
└──────┴──────────────────────────────┴──────────────────────────────────────────────┘
```

---

## 4. MASTER ORCHESTRATOR — WORKFLOW 002

The Master Orchestrator is the brain of the system. It performs zero production logic. It only coordinates.

```
project_orchestrator
│
├── [01] TRIGGER
│   ├── Type: Webhook
│   ├── Method: POST
│   ├── Path: /webhook/orchestrator
│   ├── Receives: { project_id, trigger_event, override_state }
│   └── Also: Cron Trigger every 60 seconds (for stuck project recovery)
│
├── [02] LOAD PROJECT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT project_id, current_state, previous_state, retry_count,
│   │          error_count, last_error, last_state_change_at,
│   │          checkpoint_data, config, progress
│   │   FROM cineos_core.projects
│   │   WHERE project_id = $project_id
│   └── Output: project record
│
├── [03] STATE VALIDATOR
│   ├── Type: IF
│   ├── Condition: project.current_state IN ('completed', 'cancelled', 'failed')
│   ├── True → [30] TERMINAL EXIT
│   └── False → continue
│
├── [04] TRANSITION VALIDATOR
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT allowed_next_states
│   │   FROM cineos_core.state_definitions
│   │   WHERE state_name = $current_state
│   ├── Type: Code
│   ├── Logic:
│   │   Load allowed_next_states for current_state
│   │   Determine next_state based on trigger_event and current_state
│   │   Validate next_state is in allowed_next_states
│   │   If invalid: log violation, return error
│   └── Output: { valid, next_state, reason }
│
├── [05] ENTRY CONDITION CHECK
│   ├── Type: PostgreSQL (dynamic query based on state)
│   ├── Logic:
│   │   For each entry_condition in state_definitions:
│   │     Execute the check query
│   │     If any fails: return failure with which condition failed
│   └── Output: { conditions_met, failed_conditions[] }
│
├── [06] STATE ROUTER
│   ├── Type: Switch
│   ├── Rules:
│   │   current_state == 'received'      → Route: VALIDATE
│   │   current_state == 'validated'     → Route: PARSE
│   │   current_state == 'parsed'        → Route: INTELLIGENCE
│   │   current_state == 'understood'    → Route: BIBLES
│   │   current_state == 'biblified'     → Route: CHARACTERS
│   │   current_state == 'characterized' → Route: WORLD
│   │   current_state == 'worldbuilt'    → Route: TIMELINE
│   │   current_state == 'timeline_verified' → Route: SCENE_PLAN
│   │   current_state == 'planned'       → Route: SHOT_PLAN
│   │   current_state == 'prompted'      → Route: QUEUE
│   │   current_state == 'queued'        → Route: GENERATE
│   │   current_state == 'generating'    → Route: CHECK_GENERATION
│   │   current_state == 'generated'     → Route: QUALITY
│   │   current_state == 'reviewing'     → Route: CHECK_REVIEW
│   │   current_state == 'repairing'     → Route: CHECK_REPAIR
│   │   current_state == 'approved'      → Route: VOICE
│   │   current_state == 'voiced'        → Route: MUSIC
│   │   current_state == 'musicked'      → Route: ANIMATE
│   │   current_state == 'animated'      → Route: RENDER
│   │   current_state == 'rendering'     → Route: CHECK_RENDER
│   │   current_state == 'rendered'      → Route: FINAL_REVIEW
│   │   current_state == 'super_resolution' → Route: SUPER_RES
│   │   current_state == 'final_review'  → Route: CHECK_FINAL
│   │   current_state == 'delivered'     → Route: LEARN
│   │   current_state == 'learned'       → Route: COMPLETE
│   │   current_state == 'retrying'      → Route: RETRY
│   │   current_state == 'waiting'       → Route: WAIT
│   │   current_state == 'paused'        → Route: PAUSE
│   │   default                          → Route: ERROR
│
├── [07] TRANSITION: Set state to {next_state}
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = $next_state,
│   │       previous_state = $current_state,
│   │       last_state_change_at = NOW(),
│   │       updated_at = NOW()
│   │   WHERE project_id = $project_id
│   │   AND current_state = $current_state  -- optimistic lock
│   └── If affected_rows = 0: CONFLICT → retry
│
├── [08] EMIT STATE CHANGE EVENT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.state_log
│   │     (project_id, entity_type, entity_id, old_state, new_state, workflow, operator, reason, created_at)
│   │   VALUES
│   │     ($project_id, 'project', $project_id, $old_state, $new_state, 'project_orchestrator', 'system', $reason, NOW());
│   │
│   │   INSERT INTO cineos_core.events
│   │     (project_id, event_type, workflow, state_before, state_after, severity, message, payload, created_at)
│   │   VALUES
│   │     ($project_id, $event_type, 'project_orchestrator', $old_state, $new_state, 'info', $message, $payload, NOW());
│
├── [09] DISPATCH WORKFLOW
│   ├── Type: HTTP Request
│   ├── URL: http://localhost:5678/webhook/{target_workflow_webhook}
│   ├── Method: POST
│   ├── Body: { project_id, state: $new_state, trigger_event: $trigger_event }
│   ├── Timeout: 5000 ms (just trigger, don't wait)
│   └── On Error: log, continue to progress update
│
├── [10] PROGRESS UPDATE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT progress, current_state, title
│   │   FROM cineos_core.projects
│   │   WHERE project_id = $project_id
│   ├── Type: Telegram
│   ├── Message: "📊 {title} | Phase: {current_state} | Progress: {progress*100}%"
│   ├── Throttle: max 1 per 30 seconds (check last notification time)
│   └── Condition: progress changed by > 0.02 since last notification
│
├── [11] VALIDATE ROUTE
│   ├── HTTP POST → /webhook/003_project_validator
│   └── Body: { project_id }
│
├── [12] PARSE ROUTE
│   ├── HTTP POST → /webhook/004_story_parser
│   └── Body: { project_id }
│
├── [13] INTELLIGENCE ROUTE
│   ├── HTTP POST → /webhook/005_story_intelligence
│   └── Body: { project_id }
│
├── [14] BIBLES ROUTE
│   ├── HTTP POST → /webhook/006_story_bible_builder
│   └── Body: { project_id }
│
├── [15] CHARACTERS ROUTE
│   ├── HTTP POST → /webhook/007_character_engine
│   └── Body: { project_id }
│
├── [16] WORLD ROUTE
│   ├── HTTP POST → /webhook/008_world_engine
│   └── Body: { project_id }
│
├── [17] TIMELINE ROUTE
│   ├── HTTP POST → /webhook/009_timeline_engine
│   └── Body: { project_id }
│
├── [18] SCENE_PLAN ROUTE
│   ├── HTTP POST → /webhook/010_scene_planner
│   └── Body: { project_id }
│
├── [19] SHOT_PLAN ROUTE
│   ├── HTTP POST → /webhook/011_shot_planner
│   └── Body: { project_id }
│
├── [20] QUEUE ROUTE
│   ├── HTTP POST → /webhook/015_job_dispatcher
│   └── Body: { project_id }
│
├── [21] GENERATE ROUTE
│   ├── HTTP POST → /webhook/017_image_generation
│   └── Body: { project_id }
│
├── [22] VOICE ROUTE
│   ├── HTTP POST → /webhook/020_voice_engine
│   └── Body: { project_id }
│
├── [23] MUSIC ROUTE
│   ├── HTTP POST → /webhook/021_music_director
│   └── Body: { project_id }
│
├── [24] ANIMATE ROUTE
│   ├── HTTP POST → /webhook/022_animation_engine
│   └── Body: { project_id }
│
├── [25] RENDER ROUTE
│   ├── HTTP POST → /webhook/023_render_manager
│   └── Body: { project_id }
│
├── [26] SUPER_RES ROUTE
│   ├── HTTP POST → /webhook/024_super_resolution
│   └── Body: { project_id }
│
├── [27] FINAL_REVIEW ROUTE
│   ├── HTTP POST → /webhook/025_final_review
│   └── Body: { project_id }
│
├── [28] LEARN ROUTE
│   ├── HTTP POST → /webhook/027_learning_engine
│   └── Body: { project_id }
│
├── [29] COMPLETE ROUTE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'completed',
│   │       completed_at = NOW(),
│   │       progress = 1.0
│   │   WHERE project_id = $project_id
│   ├── Type: Telegram
│   └── Message: "✅ Project completed: {title}"
│
├── [30] TERMINAL EXIT
│   ├── Type: Respond to Webhook
│   └── Body: { status: "terminal", state: $current_state }
│
├── [31] RETRY HANDLER
│   ├── Type: Code
│   ├── Logic:
│   │   Load retry_policy from state_definitions
│   │   Calculate backoff: base_delay * 2^retry_count
│   │   If retry_count < max_retries:
│   │     UPDATE projects SET retry_count = retry_count + 1
│   │     Set timeout for retry
│   │     Log event: 'retry_scheduled'
│   │   Else:
│   │     Transition to 'failed'
│   │     Notify admin
│   │     Log event: 'retry_exhausted'
│   └── Output: { retry_scheduled, next_attempt_at }
│
├── [32] WAIT HANDLER
│   ├── Type: Respond to Webhook
│   ├── Body: { status: "waiting", message: "Project waiting for admin intervention" }
│   └── Log event: 'project_waiting'
│
├── [33] PAUSE HANDLER
│   ├── Type: Respond to Webhook
│   ├── Body: { status: "paused", message: "Project paused" }
│   └── Log event: 'project_paused'
│
├── [34] ERROR HANDLER
│   ├── Type: Code
│   ├── Logic:
│   │   Increment error_count
│   │   Store error details
│   │   If error_count >= max_retries: transition to 'failed'
│   │   Else: transition to 'retrying'
│   │   Notify admin if critical
│   │   Log event: 'orchestrator_error'
│   └── Output: { error_handled, action_taken }
│
├── [35] CHECK_GENERATION
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT
│   │     COUNT(*) as total_shots,
│   │     COUNT(CASE WHEN state IN ('image_generated', 'audio_generated', 'passed', 'completed') THEN 1 END) as completed_shots,
│   │     COUNT(CASE WHEN state = 'failed' THEN 1 END) as failed_shots
│   │   FROM cineos_core.shots
│   │   WHERE project_id = $project_id
│   ├── Type: Code
│   ├── Logic:
│   │   If completed_shots == total_shots: transition to 'generated'
│   │   If failed_shots > 0 AND completed_shots + failed_shots == total_shots:
│   │     If failed_shots / total_shots < 0.3: transition to 'generated' (repair later)
│   │     Else: transition to 'failed' (too many failures)
│   │   Else: stay in 'generating', wait more
│   └── Output: { should_advance, reason }
│
├── [36] CHECK_REVIEW
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT
│   │     COUNT(*) as total,
│   │     COUNT(CASE WHEN passed = TRUE THEN 1 END) as passed_count,
│   │     COUNT(CASE WHEN passed = FALSE THEN 1 END) as failed_count
│   │   FROM cineos_quality.reviews
│   │   WHERE project_id = $project_id
│   │   AND created_at > (SELECT last_state_change_at FROM cineos_core.projects WHERE project_id = $project_id)
│   ├── Type: Code
│   ├── Logic:
│   │   If all passed: transition to 'approved'
│   │   If some failed and repairable: transition to 'repairing'
│   │   If too many failed: transition to 'failed'
│   └── Output: { decision, reason }
│
├── [37] CHECK_REPAIR
│   ├── Type: PostgreSQL
│   ├── Query: Check repair completion status
│   ├── Type: Code
│   ├── Logic:
│   │   If all repairs complete: transition to 'reviewing' (re-check)
│   │   If some still running: stay in 'repairing'
│   │   If repair failed: transition to 'manual_attention'
│   └── Output: { should_advance, reason }
│
├── [38] CHECK_RENDER
│   ├── Type: PostgreSQL
│   ├── Query: Check video render job status
│   ├── Type: Code
│   ├── Logic:
│   │   If render complete: transition to 'rendered'
│   │   If render failed: transition to 'retrying'
│   │   If still running: stay in 'rendering'
│   └── Output: { should_advance, reason }
│
├── [39] CHECK_FINAL
│   ├── Type: PostgreSQL
│   ├── Query: Check final review results
│   ├── Type: Code
│   ├── Logic:
│   │   Load latest final review
│   │   If score >= auto_approve_threshold: transition to 'delivered'
│   │   If score >= min_overall_quality: transition to 'delivered'
│   │   If score >= hard_failure_threshold: transition to 'repairing'
│   │   If score < hard_failure_threshold: transition to 'failed'
│   └── Output: { decision, score, reason }
│
└── [40] RESPOND
    ├── Type: Respond to Webhook
    └── Body: { status: "dispatched", workflow: $target_workflow, project_id: $project_id }
```

---

## 5. ALL WORKFLOWS — NODE-BY-NODE SPECIFICATION

### 5.001 — telegram_intake

```
001_telegram_intake
│
├── [01] TRIGGER
│   ├── Type: Telegram Trigger
│   ├── Event: message
│   ├── Filters:
│   │   - message.document (file upload)
│   │   - message.text (text message)
│   │   - message.text starts with / (command)
│
├── [02] COMMAND ROUTER
│   ├── Type: Switch
│   ├── Rules:
│   │   /start → [10] WELCOME
│   │   /help → [11] HELP
│   │   /status → [12] STATUS
│   │   /cancel → [13] CANCEL
│   │   /settings → [14] SETTINGS
│   │   has document → [20] FILE_INTAKE
│   │   has text (no /) → [30] TEXT_INTAKE
│   │   default → [99] UNKNOWN
│
├── [10] WELCOME
│   ├── Type: Telegram Send Message
│   ├── Text: "🎬 Welcome to CineOS!\n\nSend me a novel (.txt file) and I'll create a cinematic video.\n\nCommands:\n/status - Check project status\n/cancel - Cancel current project\n/settings - Configure preferences"
│   └── Respond and End
│
├── [11] HELP
│   ├── Type: Telegram Send Message
│   ├── Text: "📖 How to use:\n1. Send a .txt file with your novel\n2. Wait for processing\n3. Receive your cinematic video\n\nLimits: 50-500,000 words, UTF-8 text"
│   └── Respond and End
│
├── [12] STATUS
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT project_id, title, current_state, progress, created_at, completed_at
│   │   FROM cineos_core.projects
│   │   WHERE user_id = $user_id
│   │   AND current_state NOT IN ('completed', 'cancelled', 'failed')
│   │   ORDER BY created_at DESC LIMIT 1
│   ├── Type: Telegram Send Message
│   ├── Text: "📊 Active Project: {title}\nState: {current_state}\nProgress: {progress*100}%\nStarted: {created_at}"
│   └── Respond and End
│
├── [13] CANCEL
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'cancelled',
│   │       updated_at = NOW()
│   │   WHERE user_id = $user_id
│   │   AND current_state NOT IN ('completed', 'cancelled')
│   │   RETURNING project_id, title
│   ├── Type: PostgreSQL (emit event)
│   ├── Query:
│   │   INSERT INTO cineos_core.events (project_id, event_type, workflow, severity, message, created_at)
│   │   VALUES ($project_id, 'PROJECT_CANCELLED', 'telegram_intake', 'info', 'User cancelled project', NOW())
│   ├── Type: Telegram Send Message
│   └── Text: "❌ Project cancelled: {title}"
│
├── [14] SETTINGS
│   ├── Type: Telegram Send Message
│   ├── Text: "⚙️ Current settings:\nArt Style: anime\nResolution: 1920x1080\nFPS: 24\n\nTo change settings, use:\n/style anime|manhwa|realistic\n/resolution 1920x1080"
│   └── Respond and End
│
├── [20] FILE_INTAKE
│   ├── Type: Telegram Download File
│   ├── Save to: /tmp/cineos_intake/{file_id}.txt
│   ├── Type: Code
│   ├── Logic:
│   │   file_path = downloaded file path
│   │   file_size = os.path.getsize(file_path)
│   │   if file_size > 10 * 1024 * 1024: ERROR "File too large"
│   │   if not file_path.endswith('.txt'): ERROR "Only .txt files supported"
│   └── Output: { file_path, file_size }
│
├── [30] TEXT_INTAKE
│   ├── Type: Code
│   ├── Logic:
│   │   text = message.text
│   │   if len(text) < 50: ERROR "Text too short (minimum 50 characters)"
│   │   Save to /tmp/cineos_intake/{message_id}.txt
│   └── Output: { file_path, file_size }
│
├── [40] CHECK_DUPLICATE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT project_id FROM cineos_core.projects
│   │   WHERE user_id = $user_id
│   │   AND current_state NOT IN ('completed', 'cancelled', 'failed')
│   ├── Type: IF
│   ├── Condition: result exists
│   ├── True → [41] DUPLICATE_ERROR
│   └── False → continue
│
├── [41] DUPLICATE_ERROR
│   ├── Type: Telegram Send Message
│   └── Text: "⚠️ You already have an active project. Use /cancel to stop it first."
│
├── [50] DETECT_ENCODING
│   ├── Type: Code
│   ├── Logic:
│   │   with open(file_path, 'rb') as f:
│   │       raw = f.read()
│   │   for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']:
│   │       try:
│   │           text = raw.decode(encoding)
│   │           break
│   │       except: continue
│   │   else: ERROR "Cannot detect encoding"
│   └── Output: { text, encoding }
│
├── [51] DETECT_LANGUAGE
│   ├── Type: Code
│   ├── Logic:
│   │   arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
│   │   total_chars = len(text)
│   │   ratio = arabic_chars / total_chars
│   │   if ratio > 0.5: language = 'ar'
│   │   elif ratio > 0.1: language = 'mixed'
│   │   else: language = 'en'
│   └── Output: { language }
│
├── [52] NORMALIZE_TEXT
│   ├── Type: Code
│   ├── Logic:
│   │   import unicodedata
│   │   text = unicodedata.normalize('NFKC', text)
│   │   text = re.sub(r'\r\n', '\n', text)
│   │   text = re.sub(r'\n{3,}', '\n\n', text)
│   │   text = re.sub(r'[ \t]+', ' ', text)
│   │   text = text.strip()
│   │   title = text.split('\n')[0][:200]  # first line as title
│   │   word_count = len(text.split())
│   │   if word_count < 50: ERROR "Too few words"
│   │   if word_count > 500000: ERROR "Too many words"
│   └── Output: { cleaned_text, title, word_count, char_count }
│
├── [60] CREATE_PROJECT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.projects (user_id, chat_id, title, current_state, language, progress, created_at, last_state_change_at)
│   │   VALUES ($user_id, $chat_id, $title, 'received', $language, 0.0, NOW(), NOW())
│   │   RETURNING project_id
│   └── Output: { project_id }
│
├── [61] CREATE_NOVEL
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.novels (project_id, title, raw_text, cleaned_text, word_count, char_count, encoding, language, source_type)
│   │   VALUES ($project_id, $title, $raw_text, $cleaned_text, $word_count, $char_count, $encoding, $language, 'telegram')
│   └── Output: { novel_id }
│
├── [62] EMIT_EVENT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.state_log (project_id, entity_type, entity_id, old_state, new_state, workflow, operator, created_at)
│   │   VALUES ($project_id, 'project', $project_id, NULL, 'received', 'telegram_intake', 'system', NOW());
│   │
│   │   INSERT INTO cineos_core.events (project_id, event_type, workflow, state_before, state_after, severity, message, payload, created_at)
│   │   VALUES ($project_id, 'PROJECT_CREATED', 'telegram_intake', NULL, 'received', 'info', 'Project created from Telegram intake', $payload, NOW());
│
├── [70] SEND_ACK
│   ├── Type: Telegram Send Message
│   ├── Text: "✅ Novel received!\n\n📖 Title: {title}\n📝 Words: {word_count}\n🌐 Language: {language}\n\nStarting production pipeline..."
│   └── Parse Mode: Markdown
│
├── [80] TRIGGER_ORCHESTRATOR
│   ├── Type: HTTP Request
│   ├── URL: http://localhost:5678/webhook/orchestrator
│   ├── Method: POST
│   ├── Body: { project_id: $project_id, trigger_event: "new_project" }
│   └── Timeout: 5000 ms
│
├── [90] RESPOND
│   ├── Type: Respond to Webhook
│   └── Body: { status: "ok", project_id: $project_id }
│
├── [99] UNKNOWN
│   ├── Type: Telegram Send Message
│   └── Text: "I don't understand. Send a .txt file or use /help."
│
└── [ERROR] GLOBAL ERROR HANDLER
    ├── Type: Telegram Send Message
    └── Text: "❌ Error: {error.message}\nPlease try again or contact admin."
```

### 5.003 — project_validator

```
003_project_validator
│
├── [01] TRIGGER
│   ├── Type: Webhook
│   ├── Path: /webhook/003_project_validator
│   ├── Receives: { project_id }
│
├── [02] LOAD PROJECT AND NOVEL
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT p.project_id, p.current_state, n.*
│   │   FROM cineos_core.projects p
│   │   JOIN cineos_core.novels n ON n.project_id = p.project_id
│   │   WHERE p.project_id = $project_id
│
├── [03] VALIDATE STATE
│   ├── Type: IF
│   ├── Condition: project.current_state != 'received'
│   ├── True → [90] WRONG_STATE EXIT
│   └── False → continue
│
├── [04] VALIDATION CHECKS
│   ├── Type: Code
│   ├── Logic:
│   │   errors = []
│   │   warnings = []
│   │
│   │   # Check story exists
│   │   if not novel.cleaned_text: errors.append("No text content")
│   │
│   │   # Check encoding
│   │   if novel.encoding not in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']: warnings.append("Unusual encoding")
│   │
│   │   # Check language
│   │   if novel.language not in ['en', 'ar', 'mixed']: errors.append("Unsupported language")
│   │
│   │   # Check word count
│   │   if novel.word_count < 50: errors.append("Too few words")
│   │   if novel.word_count > 500000: errors.append("Too many words")
│   │
│   │   # Check for corruption
│   │   null_count = novel.cleaned_text.count('\x00')
│   │   if null_count > 0: errors.append(f"Text contains {null_count} null bytes")
│   │
│   │   # Check for minimal structure
│   │   paragraphs = novel.cleaned_text.split('\n\n')
│   │   if len(paragraphs) < 3: warnings.append("Very few paragraphs")
│   │
│   │   # Check for dialogue markers
│   │   has_dialogue = any(c in novel.cleaned_text for c in ['"', '"', '«', '「'])
│   │
│   │   return { "valid": len(errors) == 0, "errors": errors, "warnings": warnings, "has_dialogue": has_dialogue }
│
├── [05] CHECK RESULT
│   ├── Type: IF
│   ├── Condition: validation.valid == false
│   ├── True → [60] VALIDATION_FAILED
│   └── False → continue
│
├── [10] TRANSITION STATE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'validated',
│   │       previous_state = 'received',
│   │       last_state_change_at = NOW()
│   │   WHERE project_id = $project_id
│   │   AND current_state = 'received'
│
├── [11] EMIT EVENT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.state_log (project_id, entity_type, entity_id, old_state, new_state, workflow, operator, created_at)
│   │   VALUES ($project_id, 'project', $project_id, 'received', 'validated', 'project_validator', 'system', NOW());
│   │
│   │   INSERT INTO cineos_core.events (project_id, event_type, workflow, state_before, state_after, severity, message, payload, created_at)
│   │   VALUES ($project_id, 'PROJECT_VALIDATED', 'project_validator', 'received', 'validated', 'info', 'Project validated successfully', $validation, NOW());
│
├── [20] SEND PROGRESS
│   ├── Type: Telegram Send Message
│   └── Text: "✅ Validation passed. Parsing story..."
│
├── [30] TRIGGER ORCHESTRATOR
│   ├── Type: HTTP Request
│   ├── URL: http://localhost:5678/webhook/orchestrator
│   ├── Method: POST
│   └── Body: { project_id: $project_id, trigger_event: "validation_complete" }
│
├── [60] VALIDATION_FAILED
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'failed',
│   │       last_error = $validation.errors,
│   │       last_error_at = NOW()
│   │   WHERE project_id = $project_id
│
├── [61] SEND ERROR
│   ├── Type: Telegram Send Message
│   └── Text: "❌ Validation failed:\n{validation.errors}\n\nPlease send a valid .txt file."
│
├── [90] WRONG_STATE
│   ├── Type: Respond to Webhook
│   └── Body: { status: "skipped", reason: "wrong_state" }
│
└── [99] RESPOND
    ├── Type: Respond to Webhook
    └── Body: { status: "ok", validation: $validation }
```

### 5.004 — story_parser

```
004_story_parser
│
├── [01] TRIGGER
│   ├── Type: Webhook
│   ├── Path: /webhook/004_story_parser
│   ├── Receives: { project_id }
│
├── [02] LOAD NOVEL
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT * FROM cineos_core.novels WHERE project_id = $project_id
│
├── [03] VALIDATE STATE
│   ├── Type: IF
│   ├── Condition: project.current_state == 'validated'
│   ├── True → continue
│   └── False → [90] WRONG_STATE
│
├── [10] CHAPTER EXTRACTION
│   ├── Type: Code
│   ├── Logic:
│   │   import re
│   │   text = novel.cleaned_text
│   │   patterns = [
│   │       r'(?m)^(?:Chapter|CHAPTER|Ch\.?)\s+(\d+)',
│   │       r'(?m)^(\d+)\.\s+',  # "1. Title"
│   │   ]
│   │   splits = []
│   │   for pattern in patterns:
│   │       matches = list(re.finditer(pattern, text))
│   │       if len(matches) >= 2:
│   │           splits = matches
│   │           break
│   │   if not splits:
│   │       # Fallback: split by double newlines into chunks of ~2000 words
│   │       # ... fallback logic
│   │   chapters = []
│   │   for i, match in enumerate(splits):
│   │       start = match.start()
│   │       end = splits[i+1].start() if i+1 < len(splits) else len(text)
│   │       chapter_text = text[start:end].strip()
│   │       chapters.append({
│   │           "chapter_number": i + 1,
│   │           "title": match.group(0).strip(),
│   │           "text": chapter_text,
│   │           "word_count": len(chapter_text.split())
│   │       })
│   └── Output: { chapters[] }
│
├── [11] PERSIST CHAPTERS
│   ├── Type: PostgreSQL (Batch)
│   ├── Query:
│   │   INSERT INTO cineos_core.chapters (novel_id, project_id, chapter_number, title, text, word_count)
│   │   VALUES ($novel_id, $project_id, $chapter.chapter_number, $chapter.title, $chapter.text, $chapter.word_count)
│   │   ON CONFLICT (novel_id, chapter_number) DO UPDATE
│   │   SET title = EXCLUDED.title, text = EXCLUDED.text, word_count = EXCLUDED.word_count
│   │   RETURNING chapter_id
│
├── [20] SCENE SEGMENTATION (per chapter, batch)
│   ├── Type: Split In Batches
│   ├── Batch Size: 1 (process one chapter at a time)
│
├── [21] LLM SCENE ANALYSIS
│   ├── Type: HTTP Request
│   ├── URL: http://localhost:11434/api/generate
│   ├── Method: POST
│   ├── Body:
│   │   {
│   │     "model": "llama3.2",
│   │     "prompt": "Analyze this chapter and identify all distinct scenes.\n\nChapter: {chapter.text}\n\nFor each scene, extract:\n- scene_number (sequential)\n- text (the scene text)\n- summary (1-2 sentence summary)\n- location (where it takes place)\n- time_of_day (dawn/morning/noon/afternoon/evening/night/unknown)\n- characters_present (list of character names)\n- primary_emotion (one word)\n- conflict_type (internal/interpersonal/external/societal/none)\n- importance (critical/high/normal/low)\n- has_dialogue (true/false)\n- has_action (true/false)\n\nReturn as JSON array.",
│   │     "stream": false
│   │   }
│   ├── Timeout: 120000 ms
│
├── [22] PARSE LLM RESPONSE
│   ├── Type: Code
│   ├── Logic:
│   │   import json, re
│   │   response = llm_response.response
│   │   # Extract JSON from response (handle markdown fences)
│   │   json_match = re.search(r'\[.*\]', response, re.DOTALL)
│   │   if json_match:
│   │       scenes = json.loads(json_match.group())
│   │   else:
│   │       # Fallback: paragraph-based segmentation
│   │       # ...
│   │   # Validate each scene
│   │   for scene in scenes:
│   │       if not scene.get('text') or len(scene['text']) < 20:
│   │           # Merge with adjacent scene
│   │           pass
│   └── Output: { scenes[] }
│
├── [23] PERSIST SCENES
│   ├── Type: PostgreSQL (Batch)
│   ├── Query:
│   │   INSERT INTO cineos_core.scenes
│   │     (project_id, chapter_id, chapter_number, scene_number, full_text, summary,
│   │      location_name, time_of_day, primary_emotion, conflict_type, importance,
│   │      has_dialogue, has_action, state)
│   │   VALUES
│   │     ($project_id, $chapter_id, $chapter_number, $scene.scene_number, $scene.text, $scene.summary,
│   │      $scene.location, $scene.time_of_day, $scene.primary_emotion, $scene.conflict_type, $scene.importance,
│   │      $scene.has_dialogue, $scene.has_action, 'extracted')
│   │   ON CONFLICT (project_id, chapter_number, scene_number) DO UPDATE
│   │   SET full_text = EXCLUDED.full_text, summary = EXCLUDED.summary
│   │   RETURNING scene_id
│
├── [24] LINK CHARACTERS TO SCENES
│   ├── Type: PostgreSQL (Batch)
│   ├── Query:
│   │   For each scene, for each character_name in scene.characters_present:
│   │     Find or create character in cineos_core.characters
│   │     INSERT INTO cineos_core.scene_characters (scene_id, character_id, role)
│   │     VALUES ($scene_id, $character_id, 'present')
│   │     ON CONFLICT DO NOTHING
│
├── [25] UPDATE CHAPTER SCENE COUNT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.chapters
│   │   SET scene_count = (SELECT COUNT(*) FROM cineos_core.scenes WHERE chapter_id = $chapter_id)
│   │   WHERE chapter_id = $chapter_id
│
├── [30] TRANSITION STATE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'parsed',
│   │       previous_state = 'validated',
│   │       last_state_change_at = NOW()
│   │   WHERE project_id = $project_id AND current_state = 'validated'
│
├── [31] EMIT EVENT
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_core.events (project_id, event_type, workflow, state_before, state_after, severity, message, payload, created_at)
│   │   VALUES ($project_id, 'STORY_PARSED', 'story_parser', 'validated', 'parsed', 'info',
│   │     'Story parsed: {chapter_count} chapters, {scene_count} scenes', $payload, NOW())
│
├── [40] SEND PROGRESS
│   ├── Type: Telegram Send Message
│   └── Text: "📖 Story parsed!\n📚 Chapters: {chapter_count}\n🎬 Scenes: {scene_count}\n\nAnalyzing narrative..."
│
├── [50] TRIGGER ORCHESTRATOR
│   ├── Type: HTTP Request
│   ├── URL: http://localhost:5678/webhook/orchestrator
│   ├── Method: POST
│   └── Body: { project_id: $project_id, trigger_event: "parsing_complete" }
│
├── [90] WRONG_STATE
│   ├── Type: Respond to Webhook
│   └── Body: { status: "skipped", reason: "wrong_state" }
│
└── [99] RESPOND
    ├── Type: Respond to Webhook
    └── Body: { status: "ok", chapters: $chapter_count, scenes: $scene_count }
```

### 5.005 — story_intelligence

```
005_story_intelligence
│
├── [01] TRIGGER
│   ├── Type: Webhook
│   ├── Path: /webhook/005_story_intelligence
│   ├── Receives: { project_id }
│
├── [02] LOAD DATA
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   SELECT * FROM cineos_core.chapters WHERE project_id = $project_id ORDER BY chapter_number;
│   │   SELECT * FROM cineos_core.scenes WHERE project_id = $project_id ORDER BY chapter_number, scene_number;
│   │   SELECT * FROM cineos_core.characters WHERE project_id = $project_id;
│
├── [03] VALIDATE STATE
│   ├── Type: IF
│   ├── Condition: project.current_state == 'parsed'
│   ├── True → continue
│   └── False → [90] WRONG_STATE
│
├── [10] CHARACTER EXTRACTION
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Extract all characters from these scenes. For each character provide: name, role (protagonist/antagonist/supporting/minor), first_appearance (scene reference), physical_description, personality_traits, relationships to other characters. Return as JSON array."
│   ├── Response: parsed JSON
│
├── [11] CHARACTER PERSISTENCE
│   ├── Type: PostgreSQL (Batch)
│   ├── Query:
│   │   INSERT INTO cineos_core.characters (project_id, canonical_name, role, gender, personality_traits, evidence_sources, state)
│   │   VALUES ($project_id, $char.name, $char.role, $char.gender, $char.personality_traits, $char.evidence, 'extracted')
│   │   ON CONFLICT (project_id, canonical_name) DO UPDATE
│   │   SET role = EXCLUDED.role, personality_traits = EXCLUDED.personality_traits
│   │   RETURNING character_id
│
├── [20] RELATIONSHIP MAPPING
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Map relationships between these characters. For each relationship provide: character_a, character_b, relationship_type (ally/enemy/lover/family/rival/mentor), description, evidence. Return as JSON array."
│   ├── Response: parsed JSON → UPDATE characters.relationships
│
├── [30] LOCATION EXTRACTION
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Extract all unique locations from these scenes. For each location: name, type (indoor/outdoor/mixed), description, atmosphere, visual_keywords. Return as JSON array."
│   ├── Response: parsed JSON
│
├── [31] LOCATION PERSISTENCE
│   ├── Type: PostgreSQL (Batch)
│   ├── Query:
│   │   INSERT INTO cineos_core.locations (project_id, name, location_type, description, atmosphere, visual_keywords, state)
│   │   VALUES ($project_id, $loc.name, $loc.type, $loc.description, $loc.atmosphere, $loc.visual_keywords, 'extracted')
│   │   ON CONFLICT (project_id, name) DO UPDATE
│   │   SET description = EXCLUDED.description
│   │   RETURNING location_id
│
├── [40] EMOTIONAL ARC MAPPING
│   ├── Type: Code
│   ├── Logic:
│   │   For each scene, map emotional progression:
│   │   - primary_emotion already set from parsing
│   │   - Calculate emotional_intensity (LLM or rule-based)
│   │   - Determine emotional_arc (ascending/descending/stable/volatile)
│   │   - Map scene pacing based on emotion and action
│   │   UPDATE scenes SET emotional_intensity, emotional_arc, pacing
│
├── [50] VISUAL PRIORITY SCORING
│   ├── Type: Code
│   ├── Logic:
│   │   For each scene, calculate visual_priority (0.0 to 1.0):
│   │   - importance weight: critical=1.0, high=0.7, normal=0.5, low=0.3
│   │   - action bonus: +0.2 if has_action
│   │   - emotion bonus: +0.15 if strong emotion
│   │   - dialogue penalty: -0.1 if only dialogue
│   │   - hero_moment flag if score > 0.8
│   │   UPDATE scenes SET visual_priority, hero_moment
│
├── [60] INCONSISTENCY DETECTION
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Check for inconsistencies in this story: character appearance contradictions, timeline conflicts, location contradictions. Return as JSON array of issues."
│   ├── Response: parsed JSON
│
├── [61] STORE INCONSISTENCIES
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_memory.story_bibles (project_id, contradictions, plot_holes, timeline_conflicts)
│   │   VALUES ($project_id, $contradictions, $plot_holes, $timeline_conflicts)
│   │   ON CONFLICT (project_id, version) DO UPDATE
│   │   SET contradictions = EXCLUDED.contradictions
│
├── [70] TRANSITION STATE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_core.projects
│   │   SET current_state = 'understood',
│   │       previous_state = 'parsed',
│   │       last_state_change_at = NOW()
│   │   WHERE project_id = $project_id AND current_state = 'parsed'
│
├── [71] EMIT EVENT
│   ├── Type: PostgreSQL
│   └── Query: INSERT INTO events (PROJECT_ANALYZED)
│
├── [80] SEND PROGRESS
│   ├── Type: Telegram Send Message
│   └── Text: "🧠 Story analyzed!\n👤 Characters: {character_count}\n📍 Locations: {location_count}\n🎭 Emotions mapped\n⚠️ Issues found: {issue_count}"
│
├── [85] TRIGGER ORCHESTRATOR
│   ├── Type: HTTP Request → /webhook/orchestrator
│   └── Body: { project_id, trigger_event: "analysis_complete" }
│
├── [90] WRONG_STATE
│   └── Body: { status: "skipped" }
│
└── [99] RESPOND
    └── Body: { status: "ok" }
```

### 5.006 — story_bible_builder

```
006_story_bible_builder
│
├── [01] TRIGGER
│   ├── Type: Webhook
│   ├── Path: /webhook/006_story_bible_builder
│   ├── Receives: { project_id }
│
├── [02] LOAD ALL DATA
│   ├── Type: PostgreSQL
│   ├── Query: Load novel, chapters, scenes, characters, locations
│
├── [03] VALIDATE STATE
│   └── Condition: current_state == 'understood'
│
├── [10] BUILD STORY BIBLE
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Based on this complete story analysis, build a Story Bible:\n- genre, subgenre, themes, central_conflict, resolution\n- narrative_arc, point_of_view, tense, tone, pacing\n- symbols, motifs, foreshadowing\n- visual_style, color_grading, lighting_mood, camera_style\nReturn as JSON."
│   ├── Response: parsed JSON
│
├── [11] PERSIST STORY BIBLE
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_memory.story_bibles (project_id, version, title, genre, subgenre, theme, themes, central_conflict, resolution, narrative_arc, point_of_view, tense, tone, pacing, symbols, motifs, foreshadowing, visual_style, color_grading, lighting_mood, camera_style, locked, confidence_score)
│   │   VALUES ($project_id, 1, $novel.title, ...)
│
├── [20] BUILD STYLE BIBLE
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Define the visual style for this production:\n- art_style (anime/manhwa/realistic/watercolor)\n- rendering_style (cel_shaded/painted/photorealistic)\n- color palette (primary, secondary, accent colors)\n- lighting styles (default, dramatic, soft, night, indoor)\n- composition rules\n- base_positive_prompt, base_negative_prompt, quality_tags\nReturn as JSON."
│   ├── Response: parsed JSON
│
├── [21] PERSIST STYLE BIBLE
│   ├── Type: PostgreSQL
│   ├── Query: INSERT INTO cineos_memory.style_bibles
│
├── [30] BUILD TIMELINE BIBLE
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Order all scenes chronologically. For each event: scene_id, sequence_number, time_reference, duration_estimate, characters_present, location, cause, effect. Detect any timeline contradictions. Return as JSON."
│   ├── Response: parsed JSON
│
├── [31] PERSIST TIMELINE BIBLE
│   ├── Type: PostgreSQL
│   ├── Query: INSERT INTO cineos_memory.timeline_bibles
│
├── [40] LOCK ALL BIBLES
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   UPDATE cineos_memory.story_bibles SET locked = TRUE, locked_at = NOW() WHERE project_id = $project_id AND version = 1;
│   │   UPDATE cineos_memory.style_bibles SET locked = TRUE, locked_at = NOW() WHERE project_id = $project_id AND version = 1;
│   │   UPDATE cineos_memory.timeline_bibles SET locked = TRUE, locked_at = NOW() WHERE project_id = $project_id AND version = 1;
│
├── [50] TRANSITION STATE
│   ├── Type: PostgreSQL
│   └── Query: UPDATE projects SET current_state = 'biblified' WHERE project_id = $project_id AND current_state = 'understood'
│
├── [60] EMIT EVENT + SEND PROGRESS + TRIGGER ORCHESTRATOR
│   └── Standard pattern
│
└── [99] RESPOND
```

### 5.007 — character_engine

```
007_character_engine
│
├── [01] TRIGGER
│   └── Webhook: /webhook/007_character_engine { project_id }
│
├── [02] LOAD DATA
│   └── PostgreSQL: Load characters, scenes, scene_characters, style_bible
│
├── [03] VALIDATE STATE
│   └── current_state == 'biblified'
│
├── [10] CHARACTER DNA BUILDER (per character, batch)
│   ├── Type: HTTP Request (Ollama)
│   ├── Prompt: "Build complete Character DNA for {character.canonical_name}.\n\nEvidence from novel:\n{character.evidence_sources}\n\nProvide:\n- Physical: gender, age, ethnicity, body_type, height, build\n- Face: face_shape, jaw, nose, eye_shape, eye_color, eyebrows\n- Hair: style, length, color, texture\n- Skin: tone, texture\n- Markings: scars, tattoos, birthmarks\n- Clothing: default_outfit, formal_outfit, combat_outfit, accessories\n- Equipment: primary_weapon, secondary_weapon, magical_arts\n- Personality: traits, values, fears, desires, habits, speech_patterns\n- Voice: description, pitch, pace, accent\nReturn as JSON with all fields."
│   ├── Response: parsed JSON
│
├── [11] BUILD VISUAL PROMPTS
│   ├── Type: Code
│   ├── Logic:
│   │   positive = f"{dna.hair_color} hair, {dna.eye_color} eyes, {dna.skin_tone} skin, {dna.body_type} build, {dna.default_outfit}"
│   │   negative = f"wrong hair color, wrong eye color, deformed, blurry, low quality"
│   │   character.visual_prompt_positive = positive
│   │   character.visual_prompt_negative = negative
│
├── [12] PERSIST CHARACTER DNA
│   ├── Type: PostgreSQL
│   ├── Query: UPDATE characters SET all DNA fields, visual_prompt_positive, visual_prompt_negative, state = 'analyzed'
│
├── [20] GENERATE CHARACTER REFERENCES
│   ├── For each character:
│   │   ├── [21] BUILD REFERENCE PROMPT
│   │   │   └── Compose: "{visual_prompt_positive}, {style_bible.base_positive_prompt}, character portrait, reference sheet"
│   │   ├── [22] CREATE GENERATION JOB
│   │   │   ├── Type: PostgreSQL
│   │   │   └── Query: INSERT INTO cineos_exec.jobs (project_id, job_type, payload, priority, state) VALUES ($project_id, 'generate_image', $payload, 2, 'pending')
│   │   └── [23] WAIT FOR JOB (poll or webhook)
│   │       ├── Type: Polling (every 10 seconds)
│   │       ├── Query: SELECT state, result FROM cineos_exec.jobs WHERE job_id = $job_id
│   │       └── Until state = 'completed' or 'failed'
│
├── [30] GENERATE EXPRESSION SHEET (primary characters only)
│   ├── Similar to reference generation but with expression-focused prompt
│
├── [40] LOCK CHARACTER BIBLES
│   ├── Type: PostgreSQL
│   ├── Query:
│   │   INSERT INTO cineos_memory.character_bibles (project_id, character_id, version, canonical_name, reference_data, locked, locked_at)
│   │   SELECT $project_id, character_id, 1, canonical_name, row_to_json(characters), TRUE, NOW()
│   │   FROM cineos_core.characters WHERE project_id = $project_id
│
├── [50] TRANSITION STATE
│   ├── PostgreSQL: UPDATE projects SET current_state = 'characterized'
│
├── [60] EMIT + PROGRESS + TRIGGER
│   └── Standard pattern
│
└── [99] RESPOND
```

### 5.008 — world_engine

```
008_world_engine
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → locations, scenes, style_bible, story_bible
├── [03] VALIDATE → current_state == 'characterized'
│
├── [10] WORLD BIBLE BUILDER
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Build comprehensive World Bible from these locations and story context:\n- world_name, geography, climate, architecture, technology_level\n- magic_system, culture, politics, economy\n- color_palette, lighting_style, visual_atmosphere, visual_keywords\n- material_aesthetics\nReturn as JSON."
│
├── [11] PERSIST WORLD BIBLE
│   └── INSERT INTO cineos_memory.world_bibles
│
├── [20] LOCATION CARD BUILDER (per location)
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Build detailed Location Card for {location.name}:\n- full description, architecture_style, lighting_default\n- color_palette, atmosphere, mood, visual_keywords\nReturn as JSON."
│   └── UPDATE cineos_core.locations
│
├── [30] GENERATE WORLD REFERENCES (per major location)
│   ├── Similar pattern to character_engine reference generation
│   │   CREATE job → WAIT → STORE in cineos_memory.world_references
│
├── [40] BUILD VISUAL PROMPTS
│   ├── Code: Compose visual_prompt_positive/negative from world data
│
├── [50] LOCK WORLD BIBLE
│   └── UPDATE world_bibles SET locked = TRUE
│
├── [60] TRANSITION → 'worldbuilt'
├── [70] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.009 — timeline_engine

```
009_timeline_engine
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → scenes, timeline_bible, characters
├── [03] VALIDATE → current_state == 'worldbuilt'
│
├── [10] CHRONOLOGICAL ORDERING
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Order these scenes chronologically. For each: sequence_number, absolute_time_order, time_reference, duration_estimate. Detect conflicts."
│
├── [11] CONTINUITY VALIDATION
│   ├── Code:
│   │   - Check character presence consistency (character can't be in two places)
│   │   - Check location consistency (events happen in valid locations)
│   │   - Check cause-effect chains (events follow logical order)
│   │   - Check temporal references (no impossible time jumps)
│
├── [12] UPDATE SCENE SEQUENCING
│   └── UPDATE scenes SET scene_number based on chronological order (if needed)
│
├── [20] UPDATE TIMELINE BIBLE
│   └── UPDATE cineos_memory.timeline_bibles SET events, contradictions, locked = TRUE
│
├── [30] TRANSITION → 'timeline_verified'
├── [40] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.010 — scene_planner

```
010_scene_planner
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → scenes, characters, locations, all bibles
├── [03] VALIDATE → current_state == 'timeline_verified'
│
├── [10] SCENE METADATA ENRICHMENT (per scene)
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Enrich this scene with production metadata:\n- detailed summary for narration\n- scene_purpose (introduction/rising_action/climax/falling_action/resolution)\n- key_visual_moments (3-5 visually important moments)\n- character_development_notes\n- suggested_music_mood\nReturn as JSON."
│   └── UPDATE scenes with enriched metadata
│
├── [20] FIGHT SCENE DETECTION
│   ├── Code:
│   │   For each scene with combat_present = TRUE:
│   │     Trigger fight_director workflow (012)
│
├── [30] EMOTION SCENE ADJUSTMENT
│   ├── Code:
│   │   For each scene with high emotional_intensity:
│   │     Trigger emotion_director workflow (013)
│
├── [40] CALCULATE SCENE DURATIONS
│   ├── Code:
│   │   For each scene:
│   │     estimated_duration = sum of planned shot durations
│   │     UPDATE scenes SET estimated_duration_seconds
│
├── [50] TRANSITION → 'planned'
├── [60] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.011 — shot_planner

```
011_shot_planner
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → scenes, characters, all bibles
├── [03] VALIDATE → current_state == 'planned'
│
├── [10] BUDGET CALCULATOR
│   ├── Code:
│   │   For each scene:
│   │     if importance == 'critical': budget = 10
│   │     if importance == 'high': budget = 7
│   │     if importance == 'normal': budget = 5
│   │     if importance == 'low': budget = 3
│   │   Total budget = sum of all scene budgets
│   │   If total > 1000: proportionally reduce
│
├── [20] SHOT PLANNING (per scene, batch)
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Plan {budget} cinematic shots for this scene.\n\nScene: {scene.summary}\nFull text: {scene.full_text}\nCharacters: {scene.characters}\nEmotion: {scene.primary_emotion}\nImportance: {scene.importance}\n\nFor each shot provide:\n- shot_type (establishing/wide/medium/close_up/extreme_close_up/action/insert)\n- duration_seconds (3-30)\n- camera_angle (eye_level/low_angle/high_angle/dutch_angle/bird_eye)\n- camera_movement (static/pan_left/pan_right/tilt_up/tilt_down/zoom_in/zoom_out/tracking)\n- depth_of_field (shallow/medium/deep)\n- focal_point (what to focus on)\n- characters_in_shot (list of character names)\n- narration_text (what narrator says)\n- transition_in/out (cut/fade/dissolve/wipe)\n\nReturn as JSON array."
│
├── [21] BUDGET ENFORCEMENT
│   ├── Code:
│   │   Trim shots exceeding budget per scene
│   │   Ensure minimum shots per scene
│   │   Enforce shot type distribution
│
├── [22] PERSIST SHOTS
│   ├── PostgreSQL (Batch):
│   │   INSERT INTO cineos_core.shots (scene_id, project_id, chapter_number, scene_number, shot_number, shot_type, importance, duration_seconds, camera_angle, camera_movement, depth_of_field, lens, focal_point, transition_in, transition_out, state)
│   │   VALUES (...)
│   │   RETURNING shot_id
│
├── [23] LINK CHARACTERS TO SHOTS
│   ├── PostgreSQL: UPDATE shots SET characters_in_shot = $character_ids
│
├── [30] UPDATE SCENE SHOT COUNTS
│   └── UPDATE scenes SET shot_count, total_planned_duration_seconds
│
├── [40] TRANSITION → 'prompted'
├── [50] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.012 — fight_director

```
012_fight_director
│
├── [01] TRIGGER → Webhook { project_id, scene_id }
├── [02] LOAD → scene data, characters involved, weapons, combat styles
│
├── [10] COMBAT BREAKDOWN
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Break down this combat scene into cinematic beats:\n\n{scene.full_text}\n\nCharacters: {characters}\nWeapons: {weapons}\n\nFor each beat:\n- beat_number\n- description\n- camera_movement (fast pan, tracking, slow-mo)\n- shot_type\n- intensity (1-10)\n- duration_seconds\n- impact_moment (boolean)\nReturn as JSON array."
│
├── [20] MAP BEATS TO SHOTS
│   ├── Code:
│   │   Convert combat beats into shot plans
│   │   Assign action-specific shot types
│   │   Set higher duration for impact moments
│   │   Add slow-motion markers for key moments
│
├── [30] UPDATE SHOTS
│   └── UPDATE shots SET shot_type = 'action', animation_params = combat-specific
│
└── [99] RESPOND
```

### 5.013 — emotion_director

```
013_emotion_director
│
├── [01] TRIGGER → Webhook { project_id, scene_id }
├── [02] LOAD → scene data, emotional arc, characters
│
├── [10] EMOTIONAL CINEMATOGRAPHY
│   ├── HTTP Request (Ollama)
│   ├── Prompt: "Adjust cinematography for emotional impact:\n\nScene emotion: {primary_emotion}\nIntensity: {emotional_intensity}\nArc: {emotional_arc}\n\nSuggest:\n- color_temperature adjustments\n- lighting_style for each shot\n- camera_movement speed\n- shot_type distribution (more close-ups for intimacy, more wide for isolation)\n- transition types (slow dissolves for sadness, quick cuts for anger)\nReturn as JSON."
│
├── [20] APPLY ADJUSTMENTS
│   └── UPDATE shots SET lighting_style, camera_movement, transition_in/out
│
└── [99] RESPOND
```

### 5.014 — prompt_builder

```
014_prompt_builder
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → shots, characters, locations, all bibles
├── [03] VALIDATE → current_state == 'prompted'
│
├── [10] PROMPT COMPOSITION (per shot, batch)
│   ├── Type: Code
│   ├── Logic:
│   │   # Load components
│   │   quality_tags = style_bible.quality_tags
│   │   base_positive = style_bible.base_positive_prompt
│   │   base_negative = style_bible.base_negative_prompt
│   │
│   │   # Character prompts
│   │   char_prompts = []
│   │   for char_id in shot.characters_in_shot:
│   │       char = load_character(char_id)
│   │       char_prompts.append(char.visual_prompt_positive)
│   │   char_fragment = ", ".join(char_prompts)
│   │
│   │   # World prompts
│   │   world_fragment = world_bible.visual_prompt_positive
│   │
│   │   # Shot-specific
│   │   shot_fragment = f"{shot.shot_type} shot, {shot.camera_angle}, {shot.lighting_style}"
│   │
│   │   # Compose
│   │   positive = f"{quality_tags}, {base_positive}, {shot_fragment}, {char_fragment}, {world_fragment}"
│   │   negative = f"{base_negative}, {char_exclusions}, {world_exclusions}"
│   │
│   │   # Truncate if needed (backend limit)
│   │   if len(positive) > 2000: positive = positive[:2000]
│   │   if len(negative) > 1000: negative = negative[:1000]
│
├── [11] STORE PROMPT VERSION
│   ├── PostgreSQL:
│   │   INSERT INTO cineos_gen.prompt_versions (shot_id, project_id, version_number, positive_prompt, negative_prompt, character_prompts, world_prompt, style_prompt, quality_tags, shot_specific_prompt, is_current)
│   │   VALUES ($shot_id, $project_id, 1, $positive, $negative, $char_prompts, $world_prompt, $style_prompt, $quality_tags, $shot_fragment, TRUE)
│
├── [12] UPDATE SHOTS
│   └── UPDATE shots SET positive_prompt, negative_prompt, prompt_version = 1, state = 'prompted'
│
├── [20] TRANSITION → 'queued'
├── [30] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.015 — job_dispatcher

```
015_job_dispatcher
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → shots with state='prompted', worker availability
├── [03] VALIDATE → current_state == 'queued'
│
├── [10] CREATE IMAGE JOBS (per shot)
│   ├── PostgreSQL:
│   │   INSERT INTO cineos_exec.jobs (project_id, job_type, payload, priority, state, timeout_ms)
│   │   VALUES ($project_id, 'generate_image', $payload, 3, 'pending', 120000)
│   │   payload = { shot_id, positive_prompt, negative_prompt, width, height, seed, backend }
│
├── [20] CREATE AUDIO JOBS (per shot with narration)
│   ├── PostgreSQL:
│   │   INSERT INTO cineos_exec.jobs (project_id, job_type, payload, priority, state, timeout_ms)
│   │   VALUES ($project_id, 'generate_audio', $payload, 4, 'pending', 60000)
│   │   payload = { shot_id, text, voice, emotion, speed, backend }
│
├── [30] ASSIGN JOBS TO WORKERS
│   ├── For each pending job:
│   │   SELECT worker using selection algorithm
│   │   UPDATE jobs SET state = 'queued', worker_id = $worker_id
│
├── [40] DISPATCH TO WORKERS
│   ├── For each queued job:
│   │   HTTP POST to worker endpoint with job payload
│   │   UPDATE jobs SET state = 'assigned', assigned_at = NOW()
│
├── [50] TRANSITION → 'generating'
├── [60] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.016 — remote_worker_manager

```
016_remote_worker_manager
│
├── [01] TRIGGER
│   ├── Cron: every 30 seconds
│   └── Webhook: worker registration/deregistration
│
├── [10] WORKER REGISTRATION
│   ├── PostgreSQL: INSERT INTO cineos_exec.workers
│
├── [20] HEARTBEAT CHECK
│   ├── PostgreSQL:
│   │   SELECT * FROM cineos_exec.workers
│   │   WHERE last_heartbeat < NOW() - INTERVAL '90 seconds'
│   │   AND state != 'offline'
│   ├── For each stale worker:
│   │   UPDATE workers SET state = 'offline'
│   │   REASSIGN pending jobs
│   │   EMIT WORKER_OFFLINE event
│
├── [30] WORKER SELECTION ALGORITHM
│   ├── Code:
│   │   function selectWorker(task_type, priority):
│   │     candidates = workers WHERE worker_type matches AND state IN ('idle','busy') AND enabled
│   │     score each: priority * 0.3 + success_rate * 0.4 + speed * 0.3
│   │     return highest scoring
│
├── [40] FAILOVER HANDLER
│   ├── For failed jobs:
│   │   If retry_count < max_retries: reassign to different worker
│   │   If retry_count >= max_retries: mark as permanently failed
│
└── [99] RESPOND
```

### 5.017 — image_generation

```
017_image_generation
│
├── [01] TRIGGER → Webhook { project_id, shot_id (optional) }
│
├── [10] LOAD PENDING JOBS
│   ├── PostgreSQL:
│   │   SELECT * FROM cineos_exec.jobs
│   │   WHERE project_id = $project_id AND job_type = 'generate_image' AND state IN ('queued','assigned')
│   │   ORDER BY priority, created_at
│
├── [20] DISPATCH TO WORKER
│   ├── HTTP POST to worker endpoint
│   ├── Body: job.payload
│   ├── Timeout: job.timeout_ms
│
├── [30] RECEIVE RESULT
│   ├── Webhook callback from worker
│   ├── Save image to disk
│   ├── INSERT INTO cineos_gen.images
│   ├── UPDATE jobs SET state = 'completed', result = $result
│   ├── UPDATE shots SET state = 'image_generated'
│
├── [40] HANDLE FAILURE
│   ├── If error is recoverable:
│   │   UPDATE jobs SET retry_count += 1, state = 'pending'
│   │   Requeue
│   ├── If error is not recoverable:
│   │   UPDATE jobs SET state = 'failed', error_message = $error
│   │   UPDATE shots SET state = 'failed'
│
├── [50] CHECK COMPLETION
│   ├── PostgreSQL: COUNT remaining pending jobs
│   ├── If all complete: transition project to 'generated'
│
└── [99] RESPOND
```

### 5.018 — quality_ai

```
018_quality_ai
│
├── [01] TRIGGER → Webhook { project_id, entity_type, entity_id }
│
├── [10] IMAGE REVIEW
│   ├── Load image, character_bibles, world_bible
│   ├── Technical quality check (file validation)
│   ├── Character consistency check (keyword matching + optional CLIP)
│   ├── World consistency check
│   ├── Composition check
│   ├── Calculate composite score
│   ├── INSERT INTO cineos_quality.reviews
│
├── [20] AUDIO REVIEW
│   ├── Load audio, shot duration
│   ├── Technical quality check
│   ├── Duration fit check
│   ├── Calculate score
│   ├── INSERT INTO cineos_quality.reviews
│
├── [30] SHOT REVIEW
│   ├── Check image and audio both passed
│   ├── Check duration alignment
│   ├── Calculate combined score
│
├── [40] SCENE REVIEW
│   ├── Check all shots ready
│   ├── Check narrative flow
│   ├── Check cross-shot consistency
│
├── [50] PROJECT REVIEW
│   ├── Check all scenes assembled
│   ├── Character consistency across project
│   ├── World consistency across project
│   ├── Narrative fidelity
│   ├── Calculate overall score
│
├── [60] DECISION
│   ├── Load thresholds from cineos_config.system_config
│   ├── If score >= auto_approve: decision = 'pass'
│   ├── If score >= min_quality: decision = 'pass'
│   ├── If score >= hard_failure: decision = 'fail_repairable'
│   └── If score < hard_failure: decision = 'fail_unrecoverable'
│
└── [99] RESPOND with { passed, score, issues, decision }
```

### 5.019 — repair_engine

```
019_repair_engine
│
├── [01] TRIGGER → Webhook { project_id, failed_items[] }
│
├── [10] STRATEGY SELECTOR (per failed item)
│   ├── Code:
│   │   Analyze review.issues
│   │   Select strategy based on failure type
│   │   Check repair_attempt count
│   │   If attempts >= max: escalate
│
├── [20] REPAIR DISPATCH
│   ├── Create repair record in cineos_quality.repairs
│   ├── Create repair job in cineos_exec.jobs
│   ├── Dispatch to appropriate worker
│
├── [30] POST-REPAIR REVIEW
│   ├── Wait for repair job completion
│   ├── Run quality_ai on repaired asset
│   ├── Compare pre/post scores
│   ├── UPDATE repairs SET improvement, success
│
├── [40] ESCALATION
│   ├── If all strategies exhausted:
│   │   Transition project to 'manual_attention'
│   │   Notify admin
│
└── [99] RESPOND
```

### 5.020 — voice_engine

```
020_voice_engine
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → shots with narration_text, character voices
├── [03] VALIDATE → current_state == 'approved'
│
├── [10] VOICE ASSIGNMENT (per shot)
│   ├── Code:
│   │   If shot has dialogue: use character_bible.voice for speaker
│   │   If narration: use default voice
│   │   Apply emotion parameters from scene
│   │   Select TTS backend (edge_tts → piper → espeak)
│
├── [20] CREATE AUDIO JOB
│   └── INSERT INTO cineos_exec.jobs (job_type='generate_audio')
│
├── [30] DISPATCH TO WORKER
│   └── HTTP POST to cpu_tts_worker
│
├── [40] RECEIVE RESULT
│   ├── Save audio file
│   ├── INSERT INTO cineos_gen.audio
│   ├── UPDATE shots SET state = 'audio_generated'
│   ├── Sync duration with shot
│
├── [50] POST-PROCESSING
│   ├── Normalize audio levels
│   ├── Add silence padding
│   ├── Trim to fit
│
├── [60] TRANSITION → 'voiced'
├── [70] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.021 — music_director

```
021_music_director
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → scenes, emotions, importance
├── [03] VALIDATE → current_state == 'voiced'
│
├── [10] MUSIC PROFILE GENERATION (per scene)
│   ├── Code:
│   │   Map emotion → genre/tempo/intensity
│   │   Map importance → arrangement complexity
│   │   Store in scenes.music_profile
│
├── [20] MUSIC PLAN CREATION
│   ├── Code:
│   │   Create crossfade parameters
│   │   Create volume levels
│   │   Create ducking parameters
│   │   Store in scenes.music_params
│
├── [30] TRANSITION → 'musicked'
├── [40] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.022 — animation_engine

```
022_animation_engine
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → shots, images, audio
├── [03] VALIDATE → current_state == 'musicked'
│
├── [10] ANIMATION PLANNING (per shot)
│   ├── Code:
│   │   Determine animation_type from shot_type and emotion
│   │   Calculate animation_params (focal point, zoom factor, pan speed)
│   │   UPDATE shots SET animation_type, animation_params
│
├── [20] CLIP RENDERING (per shot)
│   ├── Create job: { image_path, audio_path, animation_type, animation_params, duration }
│   ├── Dispatch to cpu_render_worker
│   ├── WAIT for completion
│   ├── Save clip to cineos_gen.video_clips
│   ├── UPDATE shots SET state = 'animated'
│
├── [30] VALIDATE ALL CLIPS
│   ├── Check all shots have clips
│   ├── Check clip durations match
│
├── [40] TRANSITION → 'animated'
├── [50] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.023 — render_manager

```
023_render_manager
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → video_clips ordered by shot sequence
├── [03] VALIDATE → current_state == 'animated'
│
├── [10] BUILD FFMPEG COMMAND
│   ├── Code:
│   │   Build concat list
│   │   Add global settings (resolution, fps, codec)
│   │   Add audio mixing (narration + music)
│   │   Add color grading from style_bible
│   │   Generate full FFmpeg command
│
├── [20] DISPATCH RENDER JOB
│   ├── Create job in cineos_exec.jobs
│   ├── Dispatch to cpu_render_worker
│   ├── Timeout: 600 seconds
│
├── [30] MONITOR RENDER
│   ├── Poll job status every 30 seconds
│   ├── Handle timeout (retry or escalate)
│
├── [40] RECEIVE RESULT
│   ├── Verify output file
│   ├── Extract metadata (ffprobe)
│   ├── Generate thumbnail
│   ├── INSERT INTO cineos_gen.final_videos
│
├── [50] TRANSITION → 'rendered'
├── [60] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.024 — super_resolution

```
024_super_resolution
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] VALIDATE → current_state == 'rendered'
│
├── [10] CHECK IF NEEDED
│   ├── Code:
│   │   Check if any images below target resolution
│   │   Check if project config requests super resolution
│   │   If not needed: skip to transition
│
├── [20] UPSCALE SELECTED IMAGES
│   ├── For each image needing upscale:
│   │   Create job: { image_path, upscale_factor: 2, model: 'Real-ESRGAN' }
│   │   Dispatch to super_resolution_worker
│   │   Save upscaled image
│   │   UPDATE images SET is_upscaled = TRUE
│
├── [30] TRANSITION → 'final_review'
├── [40] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.025 — final_review

```
025_final_review
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → final_video, all reviews, all shots, all scenes
├── [03] VALIDATE → current_state == 'rendered' OR 'super_resolution'
│
├── [10] CHARACTER CONSISTENCY CHECK
│   ├── Code:
│   │   For each character:
│   │     Calculate prompt inclusion rate across all shots
│   │     Check reference image usage consistency
│   │     Score: average inclusion rate
│
├── [20] WORLD CONSISTENCY CHECK
│   ├── Code:
│   │   For each location:
│   │     Calculate prompt inclusion rate
│   │     Check visual keyword consistency
│
├── [30] NARRATIVE FIDELITY CHECK
│   ├── Code:
│   │   Check all scenes represented
│   │   Check critical scenes present
│   │   Check story arc preserved
│
├── [40] AUDIO-VIDEO SYNC CHECK
│   ├── Code:
│   │   Check narration covers all shots
│   │   Check duration alignment
│
├── [50] OVERALL SCORE CALCULATION
│   ├── Code:
│   │   overall = (character * 0.25) + (world * 0.20) + (narrative * 0.25) + (sync * 0.20) + (production * 0.10)
│   │   INSERT INTO cineos_quality.reviews (entity_type='final_video')
│
├── [60] DECISION
│   ├── Code:
│   │   If overall >= 0.85: auto-approve → 'delivered'
│   │   If overall >= 0.60: approve → 'delivered'
│   │   If overall >= 0.30: repair → 'repairing'
│   │   If overall < 0.30: reject → 'failed'
│
├── [70] TRANSITION → based on decision
├── [80] EMIT + PROGRESS + TRIGGER
└── [99] RESPOND
```

### 5.026 — delivery

```
026_delivery
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → final_video, project, all reviews
├── [03] VALIDATE → current_state == 'delivered' OR 'final_review' with pass
│
├── [10] FILE SIZE CHECK
│   ├── Code:
│   │   If file_size > 50MB: compress or split
│
├── [20] BUILD DELIVERY REPORT
│   ├── Code:
│   │   Title, duration, scenes, shots
│   │   Quality scores breakdown
│   │   Processing time summary
│   │   Backend usage summary
│
├── [30] SEND VIDEO
│   ├── Type: Telegram Send Video
│   ├── Video: video_path
│   ├── Caption: delivery report
│
├── [40] SEND QUALITY REPORT
│   ├── Type: Telegram Send Message
│   └── Detailed quality breakdown
│
├── [50] ARCHIVE
│   ├── PostgreSQL:
│   │   UPDATE projects SET current_state = 'delivered', completed_at = NOW()
│   │   UPDATE final_videos SET state = 'delivered'
│
├── [60] TRIGGER LEARNING
│   └── HTTP POST → /webhook/027_learning_engine
│
└── [99] RESPOND
```

### 5.027 — learning_engine

```
027_learning_engine
│
├── [01] TRIGGER → Webhook { project_id }
├── [02] LOAD → all project data
├── [03] VALIDATE → current_state == 'delivered'
│
├── [10] PERFORMANCE ANALYSIS
│   ├── Code:
│   │   Calculate actual vs estimated metrics
│   │   Identify slowest phases
│   │   Identify most-used backends
│   │   Identify repair hotspots
│
├── [20] PROMPT PERFORMANCE ANALYSIS
│   ├── Code:
│   │   Correlate prompt elements with quality scores
│   │   Identify best/worst performing patterns
│
├── [30] BACKEND PERFORMANCE ANALYSIS
│   ├── Code:
│   │   Compare success rates, quality, speed across backends
│   │   Update preference rankings in system_config
│
├── [40] LESSONS EXTRACTION
│   ├── HTTP Request (Ollama)
│   └── Prompt: "Based on this project's performance data, extract lessons learned..."
│
├── [50] THRESHOLD TUNING
│   ├── Code:
│   │   If quality consistently high: consider raising thresholds
│   │   If repair rate high: consider adjustments
│   │   Apply with safety bounds
│
├── [60] STORE LEARNING DATA
│   └── INSERT INTO cineos_audit.learning_records
│
├── [70] TRANSITION → 'learned'
├── [80] TRIGGER ORCHESTRATOR → complete
└── [99] RESPOND
```

### 5.028 — worker_monitor

```
028_worker_monitor
│
├── [01] TRIGGER → Cron: every 30 seconds
│
├── [10] CHECK WORKER HEALTH
│   ├── PostgreSQL: SELECT workers WHERE last_heartbeat < NOW() - 90s
│   ├── For each stale worker:
│   │   UPDATE state = 'offline'
│   │   REASSIGN pending jobs
│   │   EMIT WORKER_OFFLINE event
│
├── [20] CHECK JOB TIMEOUTS
│   ├── PostgreSQL: SELECT jobs WHERE state = 'running' AND started_at + timeout < NOW()
│   ├── For each timed-out job:
│   │   UPDATE state = 'failed', error = 'timeout'
│   │   REQUEUE if retryable
│
├── [30] CHECK QUEUE DEPTH
│   ├── PostgreSQL: COUNT pending jobs by type
│   ├── If queue_depth > threshold: EMIT warning
│
└── [99] RESPOND
```

### 5.029 — system_monitor

```
029_system_monitor
│
├── [01] TRIGGER → Cron: every 5 minutes
│
├── [10] CHECK STUCK PROJECTS
│   ├── PostgreSQL: SELECT projects WHERE state NOT IN (terminal states) AND last_state_change_at < NOW() - 30 minutes
│   ├── For each stuck project:
│   │   EMIT STATE_TIMEOUT event
│   │   Transition to 'waiting' or 'paused'
│   │   Notify admin
│
├── [20] CHECK SYSTEM HEALTH
│   ├── PostgreSQL connection check
│   ├── Disk space check
│   ├── Worker availability check
│
├── [30] GENERATE HEALTH REPORT
│   ├── Code:
│   │   Active projects count
│   │   Queue depth
│   │   Worker availability
│   │   Error rate
│   │   Average processing time
│
└── [99] RESPOND
```

### 5.030 — admin_tools

```
030_admin_tools
│
├── [01] TRIGGER → Webhook { action, project_id, parameters }
│
├── [10] ACTION ROUTER
│   ├── Switch on action:
│   │   'pause' → pause project
│   │   'resume' → resume project
│   │   'retry' → retry failed phase
│   │   'skip' → skip to next phase
│   │   'override_state' → force state change
│   │   'recalculate_quality' → re-run quality review
│   │   'regenerate' → regenerate specific asset
│   │   'cancel' → cancel project
│   │   'status' → get detailed status
│
├── [20] EXECUTE ACTION
│   ├── For each action type:
│   │   Validate permissions
│   │   Execute state transition
│   │   Log action
│   │   Notify admin
│
└── [99] RESPOND
```

---

## 6. WORKFLOW COMMUNICATION MATRIX

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           WORKFLOW COMMUNICATION MAP                                │
├────────────────────┬──────────────────────────────────────────────────────────────┤
│ TRIGGER WORKFLOW    │ TARGET WORKFLOW (via orchestrator webhook)                   │
├────────────────────┼──────────────────────────────────────────────────────────────┤
│ telegram_intake    │ project_orchestrator                                         │
│ project_orchestrator│ 003-027 (any production workflow)                           │
│ 003_validator      │ project_orchestrator                                         │
│ 004_parser         │ project_orchestrator                                         │
│ 005_intelligence   │ project_orchestrator                                         │
│ 006_bibles         │ project_orchestrator                                         │
│ 007_characters     │ job_dispatcher (for reference gen) → project_orchestrator    │
│ 008_world          │ job_dispatcher (for reference gen) → project_orchestrator    │
│ 009_timeline       │ project_orchestrator                                         │
│ 010_scene_planner  │ fight_director, emotion_director → project_orchestrator      │
│ 011_shot_planner   │ project_orchestrator                                         │
│ 014_prompt_builder │ project_orchestrator                                         │
│ 015_job_dispatcher │ remote_worker_manager → image_generation                     │
│ 017_image_gen      │ quality_ai → project_orchestrator                            │
│ 018_quality_ai     │ repair_engine OR project_orchestrator                        │
│ 019_repair_engine  │ quality_ai (re-check) → project_orchestrator                 │
│ 020_voice_engine   │ project_orchestrator                                         │
│ 021_music_director │ project_orchestrator                                         │
│ 022_animation_engine│ render_manager → project_orchestrator                       │
│ 023_render_manager │ final_review → project_orchestrator                          │
│ 025_final_review   │ delivery → learning_engine → project_orchestrator            │
│ 026_delivery       │ learning_engine → project_orchestrator                       │
│ 027_learning_engine│ project_orchestrator                                         │
└────────────────────┴──────────────────────────────────────────────────────────────┘

COMMUNICATION RULE:
  Workflow A completes → writes to PostgreSQL → emits event →
  project_orchestrator detects state change → triggers Workflow B

NEVER:
  Workflow A → Execute Workflow → Workflow B (forbidden)
```

---

## 7. RETRY SYSTEM

```
RETRY CONFIGURATION PER WORKFLOW:
──────────────────────────────────

┌────────────────────────┬─────────────┬───────────────┬──────────────┬────────────────┐
│ WORKFLOW               │ MAX_RETRIES │ BASE_DELAY_MS │ MAX_DELAY_MS │ BACKOFF        │
├────────────────────────┼─────────────┼───────────────┼──────────────┼────────────────┤
│ 003_validator          │ 3           │ 1000          │ 30000        │ exponential    │
│ 004_parser             │ 3           │ 2000          │ 60000        │ exponential    │
│ 005_intelligence       │ 3           │ 5000          │ 120000       │ exponential    │
│ 006_bibles             │ 3           │ 5000          │ 120000       │ exponential    │
│ 007_characters         │ 3           │ 5000          │ 120000       │ exponential    │
│ 008_world              │ 3           │ 5000          │ 120000       │ exponential    │
│ 009_timeline           │ 2           │ 5000          │ 60000        │ exponential    │
│ 010_scene_planner      │ 3           │ 3000          │ 60000        │ exponential    │
│ 011_shot_planner       │ 3           │ 3000          │ 60000        │ exponential    │
│ 014_prompt_builder     │ 2           │ 1000          │ 30000        │ exponential    │
│ 015_job_dispatcher     │ 3           │ 2000          │ 60000        │ exponential    │
│ 017_image_generation   │ 3           │ 5000          │ 120000       │ exponential    │
│ 018_quality_ai         │ 2           │ 2000          │ 30000        │ exponential    │
│ 019_repair_engine      │ 3           │ 5000          │ 120000       │ exponential    │
│ 020_voice_engine       │ 3           │ 2000          │ 60000        │ exponential    │
│ 022_animation_engine   │ 3           │ 5000          │ 120000       │ exponential    │
│ 023_render_manager     │ 3           │ 10000         │ 300000       │ exponential    │
│ 025_final_review       │ 2           │ 5000          │ 60000        │ exponential    │
│ 026_delivery           │ 3           │ 5000          │ 60000        │ exponential    │
│ 027_learning_engine    │ 2           │ 10000         │ 120000       │ exponential    │
└────────────────────────┴─────────────┴───────────────┴──────────────┴────────────────┘

BACKOFF FORMULA:
  delay = min(base_delay * 2^retry_count, max_delay)

TRANSIENT ERRORS (retryable):
  - Network timeout
  - Worker busy
  - GPU OOM
  - Backend rate limit
  - Database connection timeout
  - LLM response timeout

PERMANENT ERRORS (not retryable):
  - Invalid input data
  - Schema validation failure
  - Authentication failure
  - Permission denied
  - Invalid state transition
  - Data corruption
```

---

## 8. RESUME SYSTEM

```
RESUME PROTOCOL:
────────────────

1. DETECT INTERRUPTED PROJECT
   - System startup scan
   - Cron: every 5 minutes
   - Projects in active states with no recent activity

2. READ CHECKPOINT
   - Load last checkpoint from cineos_core.checkpoints
   - Load project current_state
   - Determine what was in progress

3. ASSESS SITUATION
   - If state = 'generating': check job completion status
   - If state = 'rendering': check render job status
   - If state = 'repairing': check repair job status
   - If state = 'queued': check job queue status

4. DETERMINE RESUME POINT
   - If jobs were in progress: re-dispatch failed jobs, wait for running
   - If workflow was in progress: re-trigger workflow
   - If state transition was incomplete: complete transition

5. EXECUTE RESUME
   - Re-trigger appropriate workflow via orchestrator
   - Log resume event
   - Notify admin if manual intervention needed

6. CONTINUE
   - Orchestrator picks up from resume point
   - Normal processing continues

RESUME NEVER:
  - Restarts from beginning
  - Re-processes completed work
  - Loses generated assets
  - Skips quality gates
  - Bypasses state machine
```

---

## 9. REMOTE JOB MANAGEMENT

```
JOB LIFECYCLE:
──────────────

1. CREATED
   - Job record inserted into cineos_exec.jobs
   - State: 'pending'
   - Payload validated

2. QUEUED
   - Job assigned priority
   - Job waiting for worker selection
   - State: 'queued'

3. ASSIGNED
   - Worker selected by selection algorithm
   - Worker notified via HTTP
   - State: 'assigned'
   - Timeout timer starts

4. RUNNING
   - Worker confirms execution started
   - State: 'running'
   - Heartbeat expected from worker

5. COMPLETED
   - Worker reports success
   - Result stored in job.result
   - State: 'completed'
   - Timeout timer stopped

6. FAILED
   - Worker reports failure OR timeout exceeded
   - Error details stored
   - State: 'failed'
   - Retry logic evaluated

7. RETRYING
   - If retryable: state → 'pending' (requeue)
   - retry_count incremented
   - Backoff delay applied

8. CANCELLED
   - Admin cancellation
   - State: 'cancelled'
   - Worker notified to stop

JOB PAYLOAD STRUCTURE:
──────────────────────

{
  "job_id": "uuid",
  "project_id": "uuid",
  "job_type": "generate_image",
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
  "priority": 3,
  "retry_count": 0,
  "max_retries": 3
}

WORKER RESPONSE STRUCTURE:
──────────────────────────

Success:
{
  "job_id": "uuid",
  "state": "completed",
  "result": {
    "image_path": "/app/generated/images/shot_uuid.png",
    "seed": 42,
    "generation_time_ms": 15000,
    "backend_used": "local_gpu"
  }
}

Failure:
{
  "job_id": "uuid",
  "state": "failed",
  "error": {
    "message": "CUDA out of memory",
    "code": "GPU_OOM",
    "recoverable": true
  }
}
```

---

## 10. EVENT EMISSION PER WORKFLOW

Every workflow emits events on completion:

```
┌────────────────────────┬──────────────────────────────────────────────────┐
│ WORKFLOW               │ EVENTS EMITTED                                   │
├────────────────────────┼──────────────────────────────────────────────────┤
│ 001_telegram_intake    │ PROJECT_CREATED                                  │
│ 003_validator          │ PROJECT_VALIDATED                                │
│ 004_parser             │ STORY_PARSED                                     │
│ 005_intelligence       │ STORY_ANALYZED                                   │
│ 006_bibles             │ STORY_BIBLE_CREATED                              │
│ 007_characters         │ CHARACTER_BIBLE_CREATED, CHARACTER_REFERENCE_CREATED │
│ 008_world              │ WORLD_BIBLE_CREATED, WORLD_REFERENCE_CREATED     │
│ 009_timeline           │ TIMELINE_BIBLE_CREATED                           │
│ 010_scene_planner      │ SCENE_PLANNED                                    │
│ 011_shot_planner       │ SHOT_PLANNED                                     │
│ 014_prompt_builder     │ PROMPTS_GENERATED                               │
│ 015_job_dispatcher     │ JOB_CREATED, JOB_QUEUED, JOB_ASSIGNED           │
│ 017_image_generation   │ IMAGE_GENERATED, JOB_COMPLETED, JOB_FAILED      │
│ 018_quality_ai         │ QUALITY_REVIEW_PASSED, QUALITY_REVIEW_FAILED    │
│ 019_repair_engine      │ QUALITY_REPAIR_TRIGGERED, QUALITY_REPAIR_COMPLETED│
│ 020_voice_engine       │ AUDIO_GENERATED                                 │
│ 021_music_director     │ (no specific event)                             │
│ 022_animation_engine   │ CLIP_RENDERED                                   │
│ 023_render_manager     │ VIDEO_RENDERED                                  │
│ 024_super_resolution   │ SUPER_RESOLUTION_APPLIED                        │
│ 025_final_review       │ QUALITY_REVIEW_PASSED, QUALITY_REVIEW_FAILED    │
│ 026_delivery           │ PROJECT_DELIVERED                               │
│ 027_learning_engine    │ LEARNING_COMPLETED, THRESHOLD_TUNED             │
│ 028_worker_monitor     │ WORKER_OFFLINE, STATE_TIMEOUT                   │
│ 029_system_monitor     │ DEADLOCK_DETECTED, STATE_TIMEOUT                │
└────────────────────────┴──────────────────────────────────────────────────┘
```

---

## 11. LOGGING STANDARDS

Every workflow must log:

```json
{
  "workflow_name": "007_character_engine",
  "execution_id": "n8n-execution-uuid",
  "project_id": "project-uuid",
  "state_before": "biblified",
  "state_after": "characterized",
  "started_at": "2026-07-25T10:00:00Z",
  "completed_at": "2026-07-25T10:05:30Z",
  "duration_ms": 330000,
  "status": "success",
  "entities_processed": {
    "characters": 5,
    "references_generated": 5,
    "expression_sheets": 3
  },
  "errors": [],
  "worker_used": "local_gpu",
  "jobs_created": 5,
  "jobs_completed": 5,
  "jobs_failed": 0
}
```

Stored in: `cineos_audit.execution_log`

---

## 12. N8N DESIGN RULES — FINAL

```
 1. One workflow = one responsibility.
 2. Master Orchestrator controls everything.
 3. PostgreSQL is always updated first.
 4. State Machine controls execution.
 5. Heavy tasks are dispatched to workers.
 6. No workflow bypasses orchestration.
 7. Every workflow is resumable.
 8. Every workflow is retryable.
 9. Every workflow is independently deployable.
10. Every workflow is importable as independent JSON.
11. Every workflow is observable.
12. Every workflow reports progress.
13. Every workflow emits events.
14. Every workflow validates inputs.
15. Every workflow validates outputs.
```

---

*End of Part 4 — n8n Workflow Architecture, Orchestration, Workflow Decomposition, Execution Model, Retry, Resume, and Remote Job Management*
