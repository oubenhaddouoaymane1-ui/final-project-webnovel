# PART 6 — QUALITY AI, PARTIAL REPAIR, LEARNING ENGINE, REMOTE WORKERS, API CONTRACTS, AND PRODUCTION RULES

## CineOS — Quality Assurance, Repair, Learning, and Worker Architecture

---

## 1. DESIGN PHILOSOPHY

Generation is NEVER considered complete after image creation.

Every generated asset must pass an automated review.

The system follows:

```
Generate
    ↓
Review
    ↓
Repair (if necessary)
    ↓
Review Again
    ↓
Approve
    ↓
Continue
```

Generation without review is forbidden.

---

## 2. QUALITY AI PIPELINE

### 2.1 Pipeline Overview

Every generated asset enters the Quality Pipeline.

```
Quality Pipeline:
─────────────────
Load Asset
    ↓
Load Reference Data
    ↓
Load Character Bible
    ↓
Load World Bible
    ↓
Load Timeline Bible
    ↓
Load Shot Plan
    ↓
Load Prompt Version
    ↓
Run Vision Model
    ↓
Generate Report
    ↓
Store Review
    ↓
Approve OR Repair
```

### 2.2 Quality Check Categories

#### Identity Consistency
- Face Consistency
- Eye Colour
- Hair Style
- Body Shape
- Clothing
- Armour
- Weapon
- Accessories

#### Location Consistency
- Architecture
- Weather
- Lighting

#### Composition
- Camera Angle
- Composition
- Depth Of Field
- Perspective

#### Emotion
- Emotion Match
- Pose
- Action Accuracy
- Narrative Accuracy

#### Timeline
- Timeline Consistency

#### Visual Style
- Colour Palette
- Background Quality

#### Artifacts
- Image Artifacts
- Hand Quality
- Finger Count
- Text Errors

#### Technical
- Resolution
- Sharpness

### 2.3 Quality Output Schema

Every review returns:

```json
{
  "review_id": "uuid",
  "asset_id": "uuid",
  "asset_type": "image|audio|video_clip|final_video",
  "overall_score": 0.0-1.0,
  "scores": {
    "identity_score": 0.0-1.0,
    "face_consistency": 0.0-1.0,
    "eye_colour": 0.0-1.0,
    "hair_style": 0.0-1.0,
    "body_shape": 0.0-1.0,
    "clothing": 0.0-1.0,
    "armour": 0.0-1.0,
    "weapon": 0.0-1.0,
    "accessories": 0.0-1.0,
    "location_score": 0.0-1.0,
    "architecture": 0.0-1.0,
    "weather": 0.0-1.0,
    "lighting": 0.0-1.0,
    "composition_score": 0.0-1.0,
    "camera_angle": 0.0-1.0,
    "depth_of_field": 0.0-1.0,
    "perspective": 0.0-1.0,
    "emotion_score": 0.0-1.0,
    "pose": 0.0-1.0,
    "action_accuracy": 0.0-1.0,
    "narrative_accuracy": 0.0-1.0,
    "timeline_score": 0.0-1.0,
    "visual_style_score": 0.0-1.0,
    "colour_palette": 0.0-1.0,
    "background_quality": 0.0-1.0,
    "artifact_score": 0.0-1.0,
    "hand_quality": 0.0-1.0,
    "finger_count": 0.0-1.0,
    "text_errors": 0.0-1.0,
    "technical_score": 0.0-1.0,
    "resolution": 0.0-1.0,
    "sharpness": 0.0-1.0
  },
  "recommendation": "approve|repair|regenerate",
  "repair_required": true|false,
  "repair_targets": [
    {
      "region": "face|eyes|hands|weapon|armour|outfit|background|lighting|composition|colour|atmosphere",
      "severity": "minor|moderate|major|critical",
      "description": "string",
      "suggested_fix": "string"
    }
  ],
  "approval": "approved|conditional|rejected",
  "reviewer_model": "string",
  "reviewer_version": "string",
  "processing_time_ms": 0
}
```

### 2.4 Quality Scoring Thresholds

| Score Range | Decision | Action |
|-------------|----------|--------|
| 90–100 | Approved | Continue to next stage |
| 80–89 | Minor Repair | Auto-repair minor issues |
| 60–79 | Partial Repair | Repair specific regions |
| Below 60 | Regenerate | Full regeneration required |

---

## 3. PARTIAL REPAIR ENGINE

### 3.1 Repair Philosophy

The Repair Engine never regenerates the entire image unless absolutely necessary.

### 3.2 Repair Priority Order

```
Repair Priority:
────────────────
1. Face
2. Eyes
3. Hands
4. Weapon
5. Armour
6. Outfit
7. Background
8. Lighting
9. Composition
10. Colour
11. Atmosphere
```

### 3.3 Repair Pipeline

```
Receive Review
    ↓
Identify Failed Regions
    ↓
Select Repair Strategy
    ↓
Generate Repair Job
    ↓
Dispatch Worker
    ↓
Receive Repaired Asset
    ↓
Quality Review Again
    ↓
Approve
```

### 3.4 Repair Types

| Repair Type | Description | Strategy |
|-------------|-------------|----------|
| Face Repair | Fix facial features | Inpaint face region |
| Eye Repair | Fix eye color/shape | Inpaint eye region |
| Hair Repair | Fix hair style/color | Inpaint hair region |
| Hand Repair | Fix hand/finger issues | Inpaint hand region |
| Weapon Repair | Fix weapon appearance | Inpaint weapon region |
| Armour Repair | Fix armour appearance | Inpaint armour region |
| Outfit Repair | Fix clothing appearance | Inpaint outfit region |
| Background Repair | Fix background elements | Inpaint background |
| Lighting Repair | Adjust lighting | Color correction |
| Colour Repair | Fix color palette | Color grading |
| Composition Repair | Adjust framing | Crop/recompose |
| Perspective Repair | Fix perspective | Transform |
| Environment Repair | Fix environment | Inpaint environment |

### 3.5 Repair Strategies

```json
{
  "strategy": "inpaint|regenerate|adjust|composite",
  "target_region": "bounding_box_or_mask",
  "prompt_modification": "string",
  "negative_prompt_addition": "string",
  "seed Modification": "keep|random|increment",
  "cfg_adjustment": 0.0,
  "steps_adjustment": 0,
  "backend_override": "string"
}
```

---

## 4. LEARNING ENGINE

### 4.1 Learning Philosophy

Learning never modifies AI models directly.

Instead it builds an internal Production Knowledge Base.

### 4.2 Post-Project Data Collection

After every project, store:

| Data Type | Description |
|-----------|-------------|
| Best Prompt | Highest-scoring prompt pattern |
| Worst Prompt | Lowest-scoring prompt pattern |
| Generation Time | Average time per asset type |
| Repair Count | Total repairs per project |
| Average Quality | Mean quality score |
| Camera Success | Best-performing camera angles |
| Lighting Success | Best-performing lighting setups |
| Model Success | Best-performing models |
| Worker Success | Best-performing workers |
| Scene Ratings | Per-scene quality scores |
| Shot Ratings | Per-shot quality scores |
| Voice Ratings | Per-voice quality scores |
| Animation Ratings | Per-animation quality scores |
| Final Review | Overall project score |

### 4.3 Learning Database Schema

```sql
CREATE TABLE cineos_audit.learning_records (
    learning_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    scene_id UUID,
    shot_id UUID,
    prompt_version_id UUID,
    worker_id UUID,
    quality_score FLOAT,
    repair_count INTEGER,
    generation_time_ms INTEGER,
    camera_type VARCHAR(50),
    lighting_type VARCHAR(50),
    composition VARCHAR(50),
    model_used VARCHAR(200),
    notes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cineos_audit.prompt_patterns (
    pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type VARCHAR(50) NOT NULL, -- 'successful', 'failed', 'repaired'
    prompt_text TEXT NOT NULL,
    quality_score FLOAT,
    usage_count INTEGER DEFAULT 1,
    success_rate FLOAT,
    project_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cineos_audit.production_knowledge (
    knowledge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category VARCHAR(100) NOT NULL, -- 'camera', 'lighting', 'worker', 'repair', 'shot_type'
    key VARCHAR(200) NOT NULL,
    value JSONB NOT NULL,
    confidence FLOAT DEFAULT 0.0,
    usage_count INTEGER DEFAULT 1,
    success_rate FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category, key)
);
```

### 4.4 Knowledge Extraction

Extract:

| Knowledge Type | Description |
|----------------|-------------|
| Successful Prompt Patterns | Prompts that consistently score high |
| Failed Prompt Patterns | Prompts that consistently fail |
| Best Camera Angles | Angles with highest quality scores |
| Best Lighting Setups | Lighting with highest quality scores |
| Best Worker Configurations | Workers with highest success rates |
| Best Repair Strategies | Repairs with highest improvement |
| Most Successful Shot Types | Shot types with highest scores |
| Least Successful Shot Types | Shot types with lowest scores |

---

## 5. REMOTE WORKER ARCHITECTURE

### 5.1 Worker Types

| Worker Type | Responsibility | Hardware Requirements |
|-------------|----------------|----------------------|
| GPU Worker | Image generation, super resolution | GPU with 8GB+ VRAM |
| Vision Worker | Quality review, consistency checks | GPU with 4GB+ VRAM |
| CPU Worker | TTS, audio processing, text analysis | 4+ CPU cores |
| Render Worker | FFmpeg video assembly | 4+ CPU cores, 8GB+ RAM |
| Voice Worker | TTS narration generation | 2+ CPU cores |
| Animation Worker | Motion and effects | GPU with 4GB+ VRAM |
| Super Resolution Worker | Image upscaling | GPU with 8GB+ VRAM |

### 5.2 Worker Registry Schema

```sql
CREATE TABLE cineos_exec.workers (
    worker_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name VARCHAR(200) NOT NULL,
    worker_type VARCHAR(50) NOT NULL,
    state worker_state NOT NULL DEFAULT 'registering',
    host VARCHAR(200),
    port INTEGER,
    protocol VARCHAR(20) DEFAULT 'http',
    endpoint_url TEXT,
    auth_token VARCHAR(500),
    supported_backends TEXT[],
    supported_task_types TEXT[],
    gpu_model TEXT,
    gpu_vram_gb FLOAT,
    gpu_driver_version TEXT,
    cpu_cores INTEGER,
    cpu_model TEXT,
    ram_gb FLOAT,
    storage_gb FLOAT,
    os VARCHAR(100),
    last_heartbeat TIMESTAMPTZ,
    heartbeat_interval_ms INTEGER DEFAULT 30000,
    current_task_id UUID,
    current_load FLOAT DEFAULT 0.0,
    max_concurrent_tasks INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 5,
    enabled BOOLEAN DEFAULT TRUE,
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    total_tasks_timeout INTEGER DEFAULT 0,
    avg_task_duration_ms FLOAT,
    success_rate FLOAT DEFAULT 1.0,
    last_task_completed_at TIMESTAMPTZ,
    health_status VARCHAR(50) DEFAULT 'unknown',
    health_check_url TEXT,
    health_check_interval_ms INTEGER DEFAULT 60000,
    last_health_check TIMESTAMPTZ,
    gpu_memory_used_mb FLOAT,
    gpu_memory_total_mb FLOAT,
    cpu_usage_percent FLOAT,
    ram_usage_percent FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.3 Worker Selection Algorithm

```
function selectWorker(taskType, priority):
    candidates = workers WHERE 
        worker_type = taskType 
        AND state IN ('idle', 'busy') 
        AND enabled = TRUE
        AND supported_task_types @> [taskType]
    
    for each candidate:
        score = (priority * 0.3) + 
                (success_rate * 0.4) + 
                (1.0 - current_load * 0.3)
    
    return highest scoring candidate
```

### 5.4 Job Execution Pipeline

```
Create Job
    ↓
Assign Worker
    ↓
Queue
    ↓
Execute
    ↓
Return Result
    ↓
Quality Review
    ↓
Approve
```

---

## 6. API CONTRACTS

### 6.1 Service Endpoints

Every service exposes REST endpoints.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/generate-image` | POST | Generate image from prompt |
| `/review-image` | POST | Review image quality |
| `/repair-image` | POST | Repair image region |
| `/generate-voice` | POST | Generate TTS audio |
| `/animate` | POST | Animate static image |
| `/render` | POST | Render video clip |
| `/upscale` | POST | Upscale image |
| `/worker/status` | GET | Get worker status |
| `/job/status` | GET | Get job status |
| `/health` | GET | Health check |

### 6.2 Standard Request Format

Every request includes:

```json
{
  "project_id": "uuid",
  "scene_id": "uuid",
  "shot_id": "uuid",
  "asset_id": "uuid",
  "version_id": "uuid",
  "worker_id": "uuid",
  "priority": 1-10,
  "parameters": {},
  "callback_url": "http://...",
  "timeout_ms": 300000
}
```

### 6.3 Standard Response Format

```json
{
  "status": "success|error|pending",
  "execution_id": "uuid",
  "asset_id": "uuid",
  "worker_id": "uuid",
  "processing_time_ms": 0,
  "quality_score": 0.0-1.0,
  "result": {},
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  },
  "logs": []
}
```

### 6.4 API Endpoint Specifications

#### POST /generate-image

**Request:**
```json
{
  "project_id": "uuid",
  "shot_id": "uuid",
  "positive_prompt": "string",
  "negative_prompt": "string",
  "width": 1920,
  "height": 1080,
  "seed": 12345,
  "steps": 30,
  "cfg_scale": 7.5,
  "sampler": "euler_a",
  "backend": "local_gpu|hf_inference|pollinations",
  "model": "string",
  "priority": 5,
  "timeout_ms": 120000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "asset_id": "uuid",
  "image_path": "/path/to/image.png",
  "seed": 12345,
  "generation_time_ms": 5000,
  "quality_score": 0.85
}
```

#### POST /review-image

**Request:**
```json
{
  "project_id": "uuid",
  "image_id": "uuid",
  "image_path": "/path/to/image.png",
  "character_bibles": [],
  "world_bible": {},
  "shot_plan": {},
  "prompt_version": {}
}
```

**Response:**
```json
{
  "status": "success",
  "review_id": "uuid",
  "overall_score": 0.82,
  "scores": {},
  "recommendation": "repair",
  "repair_required": true,
  "repair_targets": [],
  "approval": "conditional"
}
```

#### POST /repair-image

**Request:**
```json
{
  "project_id": "uuid",
  "image_id": "uuid",
  "repair_strategy": "inpaint",
  "target_region": {
    "x": 100,
    "y": 200,
    "width": 300,
    "height": 400
  },
  "prompt_modification": "string",
  "negative_prompt_addition": "string",
  "seed": "keep|random",
  "priority": 5,
  "timeout_ms": 120000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "asset_id": "uuid",
  "repaired_image_path": "/path/to/repaired.png",
  "repair_time_ms": 3000,
  "pre_repair_score": 0.65,
  "post_repair_score": 0.85,
  "improvement": 0.20
}
```

#### POST /generate-voice

**Request:**
```json
{
  "project_id": "uuid",
  "shot_id": "uuid",
  "text": "string",
  "voice": "string",
  "emotion": "neutral|happy|sad|angry|excited",
  "speed": 1.0,
  "pitch": 0.0,
  "backend": "edge_tts|piper|espeak",
  "priority": 5,
  "timeout_ms": 60000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "asset_id": "uuid",
  "audio_path": "/path/to/audio.wav",
  "duration_seconds": 5.2,
  "generation_time_ms": 1500
}
```

#### POST /animate

**Request:**
```json
{
  "project_id": "uuid",
  "shot_id": "uuid",
  "image_path": "/path/to/image.png",
  "audio_path": "/path/to/audio.wav",
  "animation_type": "ken_burns_zoom_in|ken_burns_pan_left|parallax_depth|subtle_breathing",
  "animation_params": {
    "zoom_factor": 1.1,
    "pan_speed": 0.5,
    "focal_x": 0.5,
    "focal_y": 0.5,
    "easing": "ease_in_out"
  },
  "duration_seconds": 5.0,
  "fps": 24,
  "priority": 5,
  "timeout_ms": 120000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "clip_id": "uuid",
  "clip_path": "/path/to/clip.mp4",
  "duration_seconds": 5.0,
  "render_time_ms": 8000
}
```

#### POST /render

**Request:**
```json
{
  "project_id": "uuid",
  "clips": [
    {
      "clip_id": "uuid",
      "clip_path": "/path/to/clip.mp4",
      "order": 1,
      "transition_in": "cut|fade|dissolve",
      "transition_out": "cut|fade|dissolve",
      "transition_duration_ms": 500
    }
  ],
  "audio_tracks": [
    {
      "type": "narration|music|sfx",
      "path": "/path/to/audio.wav",
      "volume": 1.0,
      "start_time_ms": 0
    }
  ],
  "output_settings": {
    "width": 1920,
    "height": 1080,
    "fps": 24,
    "codec": "libx264",
    "audio_codec": "aac",
    "crf": 18,
    "preset": "medium"
  },
  "priority": 5,
  "timeout_ms": 600000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "video_id": "uuid",
  "video_path": "/path/to/final.mp4",
  "duration_seconds": 120.5,
  "file_size_bytes": 52428800,
  "render_time_ms": 45000
}
```

#### POST /upscale

**Request:**
```json
{
  "project_id": "uuid",
  "image_id": "uuid",
  "image_path": "/path/to/image.png",
  "upscale_factor": 2,
  "model": "Real-ESRGAN|SwinIR",
  "priority": 5,
  "timeout_ms": 120000
}
```

**Response:**
```json
{
  "status": "success",
  "execution_id": "uuid",
  "asset_id": "uuid",
  "upscaled_image_path": "/path/to/upscaled.png",
  "original_resolution": "1920x1080",
  "upscaled_resolution": "3840x2160",
  "upscale_time_ms": 5000
}
```

#### GET /worker/status

**Response:**
```json
{
  "worker_id": "uuid",
  "name": "gpu-worker-01",
  "type": "gpu_image",
  "status": "idle|busy|offline",
  "health_score": 0.95,
  "current_load": 0.3,
  "gpu_memory_used_mb": 4096,
  "gpu_memory_total_mb": 8192,
  "cpu_usage_percent": 25.0,
  "ram_usage_percent": 40.0,
  "current_jobs": 1,
  "max_concurrent_jobs": 2,
  "total_completed": 150,
  "success_rate": 0.98,
  "last_heartbeat": "2024-01-01T00:00:00Z"
}
```

#### GET /job/status

**Response:**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "job_type": "generate_image",
  "status": "pending|queued|assigned|running|completed|failed",
  "worker_id": "uuid",
  "progress": 0.5,
  "started_at": "2024-01-01T00:00:00Z",
  "estimated_completion": "2024-01-01T00:01:00Z",
  "result": {},
  "error": null
}
```

#### GET /health

**Response:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "components": {
    "database": "healthy",
    "gpu": "healthy",
    "storage": "healthy"
  }
}
```

---

## 7. JSON SCHEMA RULES

### 7.1 Input Schema Requirements

Every workflow input must have:

| Field | Description |
|-------|-------------|
| JSON Schema | Formal schema definition |
| Validation Rules | Input validation constraints |
| Required Fields | Fields that must be present |
| Optional Fields | Fields that are optional |
| Default Values | Default values for optional fields |
| Version Number | Schema version for compatibility |

### 7.2 Example JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Generate Image Request",
  "type": "object",
  "required": ["project_id", "shot_id", "positive_prompt"],
  "properties": {
    "project_id": {
      "type": "string",
      "format": "uuid",
      "description": "Project identifier"
    },
    "shot_id": {
      "type": "string",
      "format": "uuid",
      "description": "Shot identifier"
    },
    "positive_prompt": {
      "type": "string",
      "minLength": 10,
      "maxLength": 2000,
      "description": "Positive prompt for image generation"
    },
    "negative_prompt": {
      "type": "string",
      "maxLength": 1000,
      "default": "",
      "description": "Negative prompt"
    },
    "width": {
      "type": "integer",
      "minimum": 512,
      "maximum": 4096,
      "default": 1920,
      "description": "Image width"
    },
    "height": {
      "type": "integer",
      "minimum": 512,
      "maximum": 4096,
      "default": 1080,
      "description": "Image height"
    },
    "seed": {
      "type": "integer",
      "minimum": 0,
      "maximum": 4294967295,
      "description": "Random seed"
    },
    "steps": {
      "type": "integer",
      "minimum": 10,
      "maximum": 100,
      "default": 30,
      "description": "Sampling steps"
    },
    "cfg_scale": {
      "type": "number",
      "minimum": 1.0,
      "maximum": 30.0,
      "default": 7.5,
      "description": "CFG scale"
    },
    "backend": {
      "type": "string",
      "enum": ["local_gpu", "hf_inference", "pollinations"],
      "default": "local_gpu",
      "description": "Generation backend"
    },
    "priority": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "default": 5,
      "description": "Job priority"
    },
    "timeout_ms": {
      "type": "integer",
      "minimum": 10000,
      "maximum": 600000,
      "default": 120000,
      "description": "Timeout in milliseconds"
    }
  },
  "additionalProperties": false
}
```

---

## 8. PRODUCTION RULES

### 8.1 Core Rules

| Rule | Description |
|------|-------------|
| 1. Never skip Quality Review | Every asset must be reviewed |
| 2. Never overwrite approved assets | Version all changes |
| 3. Always version every output | Track all generations |
| 4. Always log every repair | Complete repair history |
| 5. Prefer partial repair | Don't regenerate entire assets |
| 6. Store every prompt version | Track prompt effectiveness |
| 7. PostgreSQL as single source of truth | No external state stores |
| 8. Every worker must report health | Heartbeat required |
| 9. Every workflow must support retry | Exponential backoff |
| 10. Every workflow must support resume | Checkpoint system |
| 11. No heavy AI tasks inside n8n | Dispatch to workers |
| 12. Heavy computation to workers | Remote execution |
| 13. Traceable assets | Link to prompt and workflow |

### 8.2 Workflow Rules

```
RULE 1: Every workflow starts with Load Project + Validate State
RULE 2: Every workflow ends with Emit Event + Trigger Orchestrator
RULE 3: Every database update is atomic
RULE 4: Every state transition is validated
RULE 5: Every error is logged and reported
RULE 6: Every retry uses exponential backoff
RULE 7: Every resume loads from checkpoint
RULE 8: Every progress update is throttled
RULE 9: Every Telegram message is rate-limited
RULE 10: Every worker dispatch has timeout
```

### 8.3 Quality Rules

```
RULE 1: No asset proceeds without review
RULE 2: No approved asset is overwritten
RULE 3: No repair exceeds max attempts
RULE 4: No low-quality asset bypasses review
RULE 5: All quality scores are persisted
RULE 6: All repairs are tracked
RULE 7: All reviews include timestamps
RULE 8: All thresholds are configurable
RULE 9: All scoring is deterministic
RULE 10: All reviews are auditable
```

---

## 9. FINAL PRODUCTION GOAL

The platform behaves as an autonomous cinematic production operating system where:

- n8n orchestrates everything
- PostgreSQL stores all knowledge
- Remote workers execute heavy AI tasks
- Quality AI validates every asset
- Repair Engine fixes only what is necessary
- Learning Engine continuously improves future productions
- Telegram remains the only user-facing interface

The result is a scalable, resumable, production-grade, free-first cinematic automation platform capable of transforming a single Telegram message into a high-quality cinematic video.

---

*End of Part 6 — Quality AI, Partial Repair, Learning Engine, Remote Workers, API Contracts, and Production Rules*
