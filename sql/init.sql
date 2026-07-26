-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Complete PostgreSQL Schema
-- Novel-to-Cinematic AI Production Platform
-- n8n-Orchestrated, State-Driven, Remote-First
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. CUSTOM TYPES
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TYPE project_state AS ENUM (
    'received', 'validated', 'parsed', 'understood', 'biblified',
    'characterized', 'worldbuilt', 'timeline_verified', 'planned',
    'prompted', 'queued', 'generating', 'generated', 'reviewing',
    'repairing', 'approved', 'voiced', 'musicked', 'animated',
    'rendering', 'rendered', 'super_resolution', 'final_review',
    'delivered', 'learned', 'completed',
    'waiting', 'paused', 'retrying', 'failed', 'manual_attention', 'cancelled'
);

CREATE TYPE scene_state AS ENUM (
    'pending', 'extracting', 'extracted', 'analyzing', 'analyzed',
    'planning', 'planned', 'generating', 'generated', 'reviewing',
    'passed', 'failed', 'repairing', 'assembled', 'completed'
);

CREATE TYPE shot_state AS ENUM (
    'pending', 'planning', 'planned', 'prompting', 'prompted',
    'generating_image', 'image_generated', 'generating_audio',
    'audio_generated', 'reviewing', 'passed', 'failed', 'repairing',
    'animating', 'animated', 'assembled', 'completed'
);

CREATE TYPE asset_state AS ENUM (
    'pending', 'generating', 'generated', 'reviewing', 'passed',
    'failed', 'repairing', 'repaired', 'supersampled', 'archived'
);

CREATE TYPE job_state AS ENUM (
    'pending', 'queued', 'assigned', 'running', 'completed',
    'failed', 'timeout', 'cancelled'
);

CREATE TYPE worker_state AS ENUM (
    'registering', 'idle', 'busy', 'overloaded', 'offline',
    'error', 'maintenance', 'deregistered'
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. SCHEMAS
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS cineos_core;
CREATE SCHEMA IF NOT EXISTS cineos_memory;
CREATE SCHEMA IF NOT EXISTS cineos_gen;
CREATE SCHEMA IF NOT EXISTS cineos_quality;
CREATE SCHEMA IF NOT EXISTS cineos_exec;
CREATE SCHEMA IF NOT EXISTS cineos_audit;
CREATE SCHEMA IF NOT EXISTS cineos_config;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 3. CORE SCHEMA — Projects, Chapters, Scenes, Shots, Characters, Locations
-- ═══════════════════════════════════════════════════════════════════════════════

-- Projects
CREATE TABLE cineos_core.projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    title TEXT,
    current_state project_state NOT NULL DEFAULT 'received',
    previous_state project_state,
    language VARCHAR(20),
    progress FLOAT DEFAULT 0.0,
    priority INTEGER DEFAULT 5,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    last_state_change_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    checkpoint_data JSONB DEFAULT '{}',
    config JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_projects_user ON cineos_core.projects(user_id);
CREATE INDEX idx_projects_state ON cineos_core.projects(current_state);
CREATE INDEX idx_projects_updated ON cineos_core.projects(updated_at);
CREATE INDEX idx_projects_priority ON cineos_core.projects(priority, created_at);

-- Novels
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
    source_type VARCHAR(20) DEFAULT 'telegram',
    file_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id)
);

CREATE INDEX idx_novels_project ON cineos_core.novels(project_id);

-- Chapters
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

-- Scenes
CREATE TABLE cineos_core.scenes (
    scene_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    chapter_id UUID NOT NULL REFERENCES cineos_core.chapters(chapter_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    state scene_state NOT NULL DEFAULT 'pending',
    full_text TEXT NOT NULL,
    summary TEXT,
    beginning_text TEXT,
    ending_text TEXT,
    location_id UUID,
    location_name TEXT,
    location_type VARCHAR(50),
    time_of_day TEXT,
    weather TEXT,
    season TEXT,
    primary_emotion VARCHAR(50),
    secondary_emotions TEXT[],
    emotional_intensity FLOAT,
    emotional_arc TEXT,
    conflict_type VARCHAR(50),
    conflict_description TEXT,
    conflict_intensity FLOAT,
    importance VARCHAR(20) DEFAULT 'normal',
    pacing VARCHAR(20) DEFAULT 'normal',
    estimated_duration_seconds FLOAT,
    has_dialogue BOOLEAN DEFAULT FALSE,
    dialogue_count INTEGER DEFAULT 0,
    dialogue_lines JSONB,
    has_action BOOLEAN DEFAULT FALSE,
    action_intensity VARCHAR(20),
    action_type VARCHAR(50),
    combat_present BOOLEAN DEFAULT FALSE,
    visual_priority FLOAT DEFAULT 0.5,
    visual_highlights TEXT[],
    hero_moment BOOLEAN DEFAULT FALSE,
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',
    shot_count INTEGER DEFAULT 0,
    total_planned_duration_seconds FLOAT,
    quality_score FLOAT,
    quality_issues JSONB,
    music_profile JSONB,
    music_params JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, chapter_number, scene_number)
);

CREATE INDEX idx_scenes_project ON cineos_core.scenes(project_id);
CREATE INDEX idx_scenes_chapter ON cineos_core.scenes(chapter_id);
CREATE INDEX idx_scenes_state ON cineos_core.scenes(state);
CREATE INDEX idx_scenes_importance ON cineos_core.scenes(importance);
CREATE INDEX idx_scenes_emotion ON cineos_core.scenes(primary_emotion);

-- Shots
CREATE TABLE cineos_core.shots (
    shot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID NOT NULL REFERENCES cineos_core.scenes(scene_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    scene_number INTEGER NOT NULL,
    shot_number INTEGER NOT NULL,
    state shot_state NOT NULL DEFAULT 'pending',
    shot_type VARCHAR(50) NOT NULL,
    importance VARCHAR(20) DEFAULT 'normal',
    duration_seconds FLOAT NOT NULL,
    camera_angle VARCHAR(50),
    camera_movement VARCHAR(50),
    depth_of_field VARCHAR(20),
    lens VARCHAR(50),
    lighting_style VARCHAR(50),
    lighting_direction VARCHAR(50),
    lighting_color VARCHAR(50),
    composition VARCHAR(50),
    focal_point VARCHAR(100),
    animation_type VARCHAR(50),
    animation_params JSONB,
    animation_intensity FLOAT,
    transition_in VARCHAR(50) DEFAULT 'cut',
    transition_out VARCHAR(50) DEFAULT 'cut',
    transition_duration_ms INTEGER DEFAULT 500,
    characters_in_shot UUID[],
    character_positions JSONB,
    positive_prompt TEXT,
    negative_prompt TEXT,
    prompt_version INTEGER DEFAULT 1,
    narration_text TEXT,
    narration_voice VARCHAR(100),
    narration_emotion VARCHAR(50),
    narration_speed FLOAT DEFAULT 1.0,
    quality_score FLOAT,
    music_cue TEXT,
    music_volume FLOAT DEFAULT 0.2,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scene_id, shot_number)
);

CREATE INDEX idx_shots_scene ON cineos_core.shots(scene_id);
CREATE INDEX idx_shots_project ON cineos_core.shots(project_id);
CREATE INDEX idx_shots_state ON cineos_core.shots(state);
CREATE INDEX idx_shots_type ON cineos_core.shots(shot_type);

-- Characters
CREATE TABLE cineos_core.characters (
    character_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state scene_state NOT NULL DEFAULT 'pending',
    canonical_name TEXT NOT NULL,
    alternative_names TEXT[],
    nicknames TEXT[],
    titles TEXT[],
    role VARCHAR(50),
    gender TEXT,
    estimated_age TEXT,
    ethnicity TEXT,
    body_type TEXT,
    height TEXT,
    build TEXT,
    face_shape TEXT,
    jaw_shape TEXT,
    nose_shape TEXT,
    eye_shape TEXT,
    eye_color TEXT,
    eye_expression TEXT,
    eyebrow_shape TEXT,
    lip_shape TEXT,
    hair_style TEXT,
    hair_length TEXT,
    hair_color TEXT,
    hair_texture TEXT,
    skin_tone TEXT,
    skin_texture TEXT,
    scars TEXT[],
    tattoos TEXT[],
    birthmarks TEXT[],
    freckles BOOLEAN DEFAULT FALSE,
    default_outfit TEXT,
    formal_outfit TEXT,
    combat_outfit TEXT,
    sleep_outfit TEXT,
    distinctive_accessories TEXT[],
    primary_weapon TEXT,
    secondary_weapon TEXT,
    magical_arts TEXT[],
    tools TEXT[],
    personality_traits TEXT[],
    core_values TEXT[],
    fears TEXT[],
    desires TEXT[],
    habits TEXT[],
    speech_patterns TEXT,
    verbal_tics TEXT[],
    voice_description TEXT,
    voice_pitch TEXT,
    voice_pace TEXT,
    voice_accent TEXT,
    voice_parameters JSONB,
    relationships JSONB,
    evidence_sources TEXT[],
    inferred_traits TEXT[],
    confidence_score FLOAT DEFAULT 0.0,
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    primary_reference_id UUID,
    expression_sheet_id UUID,
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    lock_reason TEXT,
    total_scene_count INTEGER DEFAULT 0,
    first_appearance_scene_id UUID,
    last_appearance_scene_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, canonical_name)
);

CREATE INDEX idx_characters_project ON cineos_core.characters(project_id);
CREATE INDEX idx_characters_state ON cineos_core.characters(state);
CREATE INDEX idx_characters_name ON cineos_core.characters(canonical_name);
CREATE INDEX idx_characters_role ON cineos_core.characters(role);

-- Locations
CREATE TABLE cineos_core.locations (
    location_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aliases TEXT[],
    location_type VARCHAR(50),
    description TEXT,
    detailed_description TEXT,
    atmosphere TEXT,
    mood TEXT,
    size VARCHAR(50),
    materials TEXT[],
    features TEXT[],
    hazards TEXT[],
    architecture_style TEXT,
    lighting_default VARCHAR(50),
    color_palette TEXT[],
    visual_atmosphere TEXT,
    visual_keywords TEXT[],
    weather_default TEXT,
    temperature_range TEXT,
    time_of_day_variants JSONB,
    reference_image_id UUID,
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    scene_count INTEGER DEFAULT 0,
    scene_ids UUID[],
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, name)
);

CREATE INDEX idx_locations_project ON cineos_core.locations(project_id);
CREATE INDEX idx_locations_type ON cineos_core.locations(location_type);

-- Scene-Character Junction
CREATE TABLE cineos_core.scene_characters (
    scene_id UUID NOT NULL REFERENCES cineos_core.scenes(scene_id) ON DELETE CASCADE,
    character_id UUID NOT NULL REFERENCES cineos_core.characters(character_id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'present',
    emotional_state TEXT,
    dialogue_lines JSONB,
    screen_time_seconds FLOAT,
    PRIMARY KEY (scene_id, character_id)
);

CREATE INDEX idx_scene_characters_scene ON cineos_core.scene_characters(scene_id);
CREATE INDEX idx_scene_characters_character ON cineos_core.scene_characters(character_id);

-- Add FK from scenes to locations (after locations table exists)
ALTER TABLE cineos_core.scenes ADD CONSTRAINT fk_scenes_location
    FOREIGN KEY (location_id) REFERENCES cineos_core.locations(location_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 4. MEMORY SCHEMA — Bibles
-- ═══════════════════════════════════════════════════════════════════════════════

-- Story Bible
CREATE TABLE cineos_memory.story_bibles (
    bible_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
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
    total_chapters INTEGER,
    total_scenes INTEGER,
    estimated_duration_minutes FLOAT,
    symbols TEXT[],
    motifs TEXT[],
    foreshadowing JSONB,
    character_arcs JSONB,
    world_state_changes JSONB,
    visual_style TEXT,
    color_grading TEXT,
    lighting_mood TEXT,
    camera_style TEXT,
    contradictions JSONB,
    plot_holes JSONB,
    timeline_conflicts JSONB,
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    confidence_score FLOAT DEFAULT 0.0,
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
    canonical_name TEXT NOT NULL,
    full_description TEXT,
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    reference_data JSONB,
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
    visual_prompt_positive TEXT,
    visual_prompt_negative TEXT,
    reference_images JSONB,
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
    events JSONB NOT NULL,
    total_events INTEGER,
    time_span TEXT,
    has_flashbacks BOOLEAN DEFAULT FALSE,
    has_parallel_timelines BOOLEAN DEFAULT FALSE,
    timeline_type TEXT,
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

-- Reference Images
CREATE TABLE cineos_memory.character_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES cineos_core.characters(character_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    reference_type VARCHAR(50) NOT NULL,
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
    reference_type VARCHAR(50) NOT NULL,
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
    reference_type VARCHAR(50) NOT NULL,
    description TEXT,
    image_path TEXT NOT NULL,
    prompt_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prompt Patterns (Production Knowledge Base)
CREATE TABLE cineos_memory.prompt_patterns (
    pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type VARCHAR(50) NOT NULL,
    pattern_name VARCHAR(200) NOT NULL,
    pattern_data JSONB NOT NULL,
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_quality_score FLOAT,
    avg_repair_count FLOAT,
    confidence FLOAT DEFAULT 0.5,
    source VARCHAR(50) DEFAULT 'learned',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prompt_patterns_type ON cineos_memory.prompt_patterns(pattern_type);
CREATE INDEX idx_prompt_patterns_confidence ON cineos_memory.prompt_patterns(confidence);

-- Backend Performance History
CREATE TABLE cineos_memory.backend_performance (
    performance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backend_type VARCHAR(50) NOT NULL,
    backend_name VARCHAR(100) NOT NULL,
    project_id UUID REFERENCES cineos_core.projects(project_id) ON DELETE SET NULL,
    job_id UUID,
    task_type VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    quality_score FLOAT,
    repair_count INTEGER DEFAULT 0,
    latency_ms INTEGER,
    error_type VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_backend_performance_type ON cineos_memory.backend_performance(backend_type, backend_name);
CREATE INDEX idx_backend_performance_success ON cineos_memory.backend_performance(success);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 5. GENERATION SCHEMA — Assets
-- ═══════════════════════════════════════════════════════════════════════════════

-- Generated Images
CREATE TABLE cineos_gen.images (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',
    variant_number INTEGER NOT NULL DEFAULT 1,
    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    file_size_bytes BIGINT,
    width INTEGER,
    height INTEGER,
    format VARCHAR(10),
    prompt_used TEXT NOT NULL,
    negative_prompt_used TEXT,
    backend_used VARCHAR(100),
    model_used VARCHAR(200),
    seed INTEGER,
    steps INTEGER,
    cfg_scale FLOAT,
    sampler VARCHAR(50),
    quality_score FLOAT,
    technical_quality_score FLOAT,
    prompt_alignment_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    composition_score FLOAT,
    is_selected BOOLEAN DEFAULT FALSE,
    selection_reason TEXT,
    generated_locally BOOLEAN DEFAULT TRUE,
    worker_id UUID,
    job_id UUID,
    generation_time_ms INTEGER,
    is_upscaled BOOLEAN DEFAULT FALSE,
    original_image_id UUID,
    upscale_factor FLOAT,
    upscale_model VARCHAR(100),
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
    audio_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    format VARCHAR(10),
    text_used TEXT NOT NULL,
    voice_used VARCHAR(100),
    emotion VARCHAR(50),
    speed FLOAT DEFAULT 1.0,
    pitch FLOAT DEFAULT 0.0,
    volume FLOAT DEFAULT 1.0,
    duration_seconds FLOAT,
    sample_rate INTEGER,
    bit_depth INTEGER,
    channels INTEGER,
    quality_score FLOAT,
    naturalness_score FLOAT,
    emotion_match_score FLOAT,
    duration_fit_score FLOAT,
    is_selected BOOLEAN DEFAULT FALSE,
    backend_used VARCHAR(100),
    worker_id UUID,
    job_id UUID,
    generation_time_ms INTEGER,
    state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    repair_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Video Clips
CREATE TABLE cineos_gen.video_clips (
    clip_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state asset_state NOT NULL DEFAULT 'pending',
    image_id UUID REFERENCES cineos_gen.images(image_id),
    audio_id UUID REFERENCES cineos_gen.audio(audio_id),
    clip_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    duration_seconds FLOAT,
    width INTEGER,
    height INTEGER,
    fps FLOAT,
    codec VARCHAR(50),
    bitrate INTEGER,
    animation_applied VARCHAR(50),
    animation_params JSONB,
    transition_in VARCHAR(50),
    transition_out VARCHAR(50),
    transition_duration_ms INTEGER,
    quality_score FLOAT,
    audio_video_sync_score FLOAT,
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
    format VARCHAR(10),
    overall_quality_score FLOAT,
    character_consistency_score FLOAT,
    world_consistency_score FLOAT,
    narrative_fidelity_score FLOAT,
    audio_video_sync_score FLOAT,
    production_quality_score FLOAT,
    total_scenes INTEGER,
    total_shots INTEGER,
    total_clips INTEGER,
    render_time_ms INTEGER,
    render_settings JSONB,
    state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prompt Versions
CREATE TABLE cineos_gen.prompt_versions (
    prompt_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID NOT NULL REFERENCES cineos_core.shots(shot_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    positive_prompt TEXT NOT NULL,
    negative_prompt TEXT NOT NULL,
    character_prompts JSONB,
    world_prompt TEXT,
    style_prompt TEXT,
    quality_tags TEXT,
    shot_specific_prompt TEXT,
    shot_type VARCHAR(50),
    camera_angle VARCHAR(50),
    scene_emotion VARCHAR(50),
    quality_score FLOAT,
    review_id UUID,
    backend_used VARCHAR(100),
    model_used VARCHAR(200),
    generation_time_ms INTEGER,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shot_id, version_number)
);

CREATE INDEX idx_prompt_versions_shot ON cineos_gen.prompt_versions(shot_id);
CREATE INDEX idx_prompt_versions_project ON cineos_gen.prompt_versions(project_id);
CREATE INDEX idx_prompt_versions_current ON cineos_gen.prompt_versions(is_current) WHERE is_current = TRUE;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 6. QUALITY SCHEMA
-- ═══════════════════════════════════════════════════════════════════════════════

-- Quality Reviews
CREATE TABLE cineos_quality.reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    review_type VARCHAR(50) NOT NULL,
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
    passed BOOLEAN NOT NULL,
    decision VARCHAR(50) NOT NULL,
    issues JSONB,
    recommendations JSONB,
    reviewer_model VARCHAR(100),
    reviewer_version VARCHAR(50),
    reviewer_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_project ON cineos_quality.reviews(project_id);
CREATE INDEX idx_reviews_entity ON cineos_quality.reviews(entity_type, entity_id);
CREATE INDEX idx_reviews_passed ON cineos_quality.reviews(passed);
CREATE INDEX idx_reviews_created ON cineos_quality.reviews(created_at);

-- Quality Thresholds
CREATE TABLE cineos_quality.thresholds (
    threshold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    min_image_quality FLOAT DEFAULT 0.60,
    min_character_consistency FLOAT DEFAULT 0.70,
    min_world_consistency FLOAT DEFAULT 0.60,
    min_composition FLOAT DEFAULT 0.50,
    min_prompt_alignment FLOAT DEFAULT 0.60,
    min_audio_quality FLOAT DEFAULT 0.50,
    min_naturalness FLOAT DEFAULT 0.50,
    min_emotion_match FLOAT DEFAULT 0.40,
    min_duration_fit FLOAT DEFAULT 0.60,
    min_video_quality FLOAT DEFAULT 0.60,
    min_audio_video_sync FLOAT DEFAULT 0.70,
    min_overall_quality FLOAT DEFAULT 0.60,
    max_repair_attempts INTEGER DEFAULT 3,
    repair_escalation_threshold FLOAT DEFAULT 0.30,
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
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    failure_reason TEXT,
    failure_score FLOAT,
    failure_issues JSONB,
    repair_strategy VARCHAR(100) NOT NULL,
    repair_description TEXT,
    repair_attempt_number INTEGER NOT NULL,
    max_repair_attempts INTEGER DEFAULT 3,
    new_entity_type VARCHAR(50),
    new_entity_id UUID,
    new_review_id UUID,
    pre_repair_score FLOAT,
    post_repair_score FLOAT,
    improvement FLOAT,
    success BOOLEAN,
    failure_reason_repair TEXT,
    worker_id UUID,
    job_id UUID,
    repair_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_repairs_project ON cineos_quality.repairs(project_id);
CREATE INDEX idx_repairs_entity ON cineos_quality.repairs(entity_type, entity_id);
CREATE INDEX idx_repairs_success ON cineos_quality.repairs(success);

-- Individual Quality Checks (per-check results)
CREATE TABLE cineos_quality.checks (
    check_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    review_id UUID NOT NULL REFERENCES cineos_quality.reviews(review_id),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    check_category VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    weight FLOAT DEFAULT 1.0,
    passed BOOLEAN NOT NULL,
    threshold FLOAT NOT NULL,
    details JSONB,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_checks_project ON cineos_quality.checks(project_id);
CREATE INDEX idx_checks_review ON cineos_quality.checks(review_id);
CREATE INDEX idx_checks_entity ON cineos_quality.checks(entity_type, entity_id);
CREATE INDEX idx_checks_name ON cineos_quality.checks(check_name);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 7. EXECUTION SCHEMA — Workers, Jobs, Workflow Executions
-- ═══════════════════════════════════════════════════════════════════════════════

-- Worker Registry
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

CREATE INDEX idx_workers_type ON cineos_exec.workers(worker_type);
CREATE INDEX idx_workers_state ON cineos_exec.workers(state);
CREATE INDEX idx_workers_enabled ON cineos_exec.workers(enabled);

-- Job Queue
CREATE TABLE cineos_exec.jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    job_type VARCHAR(100) NOT NULL,
    state job_state NOT NULL DEFAULT 'pending',
    worker_id UUID REFERENCES cineos_exec.workers(worker_id),
    priority INTEGER DEFAULT 5,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    payload JSONB NOT NULL,
    result JSONB,
    queued_at TIMESTAMPTZ,
    assigned_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    timeout_ms INTEGER DEFAULT 300000,
    error_message TEXT,
    error_code VARCHAR(50),
    error_traceback TEXT,
    is_recoverable BOOLEAN DEFAULT TRUE,
    depends_on UUID[],
    parent_job_id UUID,
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

-- ═══════════════════════════════════════════════════════════════════════════════
-- 8. AUDIT SCHEMA — Events, State Log, Learning, Execution Log
-- ═══════════════════════════════════════════════════════════════════════════════

-- Event Types
CREATE TABLE cineos_core.event_types (
    event_type VARCHAR(100) PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    payload_schema JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Events
CREATE TABLE cineos_core.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    event_type VARCHAR(100) NOT NULL REFERENCES cineos_core.event_types(event_type),
    workflow VARCHAR(200),
    state_before VARCHAR(100),
    state_after VARCHAR(100),
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    message TEXT,
    payload JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_project ON cineos_core.events(project_id);
CREATE INDEX idx_events_type ON cineos_core.events(event_type);
CREATE INDEX idx_events_severity ON cineos_core.events(severity);
CREATE INDEX idx_events_created ON cineos_core.events(created_at);
CREATE INDEX idx_events_workflow ON cineos_core.events(workflow);

-- State Log
CREATE TABLE cineos_core.state_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL DEFAULT 'project',
    entity_id UUID NOT NULL,
    old_state VARCHAR(100),
    new_state VARCHAR(100) NOT NULL,
    workflow VARCHAR(200),
    operator VARCHAR(200),
    reason TEXT,
    validation_result JSONB,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_state_log_project ON cineos_core.state_log(project_id);
CREATE INDEX idx_state_log_entity ON cineos_core.state_log(entity_type, entity_id);
CREATE INDEX idx_state_log_new_state ON cineos_core.state_log(new_state);
CREATE INDEX idx_state_log_created ON cineos_core.state_log(created_at);

-- Learning Data
CREATE TABLE cineos_audit.learning_records (
    learning_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    estimated_scenes INTEGER,
    estimated_shots INTEGER,
    estimated_duration_minutes FLOAT,
    actual_scenes INTEGER,
    actual_shots INTEGER,
    actual_duration_minutes FLOAT,
    total_processing_time_ms BIGINT,
    total_generation_time_ms BIGINT,
    total_review_time_ms BIGINT,
    total_repair_time_ms BIGINT,
    total_assembly_time_ms BIGINT,
    first_pass_quality_score FLOAT,
    final_quality_score FLOAT,
    repair_success_rate FLOAT,
    average_repair_attempts FLOAT,
    image_backends_used JSONB,
    audio_backends_used JSONB,
    render_backends_used JSONB,
    primary_image_backend VARCHAR(100),
    primary_audio_backend VARCHAR(100),
    avg_prompt_alignment_score FLOAT,
    worst_prompt_alignment_score FLOAT,
    best_performing_shot_types JSONB,
    worst_performing_shot_types JSONB,
    lessons JSONB,
    recommendations JSONB,
    cost_estimate_usd FLOAT,
    efficiency_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_learning_project ON cineos_audit.learning_records(project_id);

-- Execution Log
CREATE TABLE cineos_audit.execution_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    workflow_name VARCHAR(200) NOT NULL,
    execution_id UUID,
    node_name VARCHAR(200),
    node_type VARCHAR(100),
    state VARCHAR(50),
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

-- ═══════════════════════════════════════════════════════════════════════════════
-- 9. CONFIG SCHEMA
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE cineos_config.system_config (
    config_key VARCHAR(200) PRIMARY KEY,
    config_value JSONB NOT NULL,
    description TEXT,
    category VARCHAR(100),
    data_type VARCHAR(50),
    min_value FLOAT,
    max_value FLOAT,
    allowed_values JSONB,
    is_sensitive BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(200)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 10. VERSIONING
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE cineos_core.versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    parent_version_id UUID,
    data_snapshot JSONB NOT NULL,
    author VARCHAR(200) NOT NULL,
    change_reason TEXT NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    is_current BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_type, entity_id, version_number)
);

CREATE INDEX idx_versions_entity ON cineos_core.versions(entity_type, entity_id);
CREATE INDEX idx_versions_project ON cineos_core.versions(project_id);
CREATE INDEX idx_versions_current ON cineos_core.versions(is_current) WHERE is_current = TRUE;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 11. CHECKPOINTS
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE cineos_core.checkpoints (
    checkpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES cineos_core.projects(project_id) ON DELETE CASCADE,
    state_at_checkpoint project_state NOT NULL,
    completed_phases TEXT[],
    current_phase VARCHAR(100),
    chapter_count INTEGER,
    scene_count INTEGER,
    shot_count INTEGER,
    character_count INTEGER,
    location_count INTEGER,
    average_quality_score FLOAT,
    total_repairs INTEGER,
    images_generated INTEGER,
    audio_generated INTEGER,
    clips_rendered INTEGER,
    total_processing_time_ms BIGINT,
    phase_processing_times JSONB,
    pending_jobs UUID[],
    failed_jobs UUID[],
    state_snapshot JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_checkpoints_project ON cineos_core.checkpoints(project_id);
CREATE INDEX idx_checkpoints_state ON cineos_core.checkpoints(state_at_checkpoint);

-- ═══════════════════════════════════════════════════════════════════════════════
-- 12. TRIGGERS AND FUNCTIONS
-- ═══════════════════════════════════════════════════════════════════════════════

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION cineos_core.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

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
        IF NOT EXISTS (
            SELECT 1 FROM cineos_core.scenes
            WHERE project_id = NEW.project_id
            AND state != 'completed'
        ) THEN
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
    IF OLD.current_state = NEW.current_state THEN
        RETURN NEW;
    END IF;

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

    IF NOT (allowed_transitions ->> OLD.current_state::text) ? NEW.current_state::text THEN
        RAISE EXCEPTION 'Invalid state transition: % -> %', OLD.current_state, NEW.current_state;
    END IF;

    NEW.previous_state := OLD.current_state;
    NEW.last_state_change_at = NOW();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_enforce_state_transition
    BEFORE UPDATE OF current_state ON cineos_core.projects
    FOR EACH ROW EXECUTE FUNCTION cineos_core.enforce_state_transition();

-- ═══════════════════════════════════════════════════════════════════════════════
-- 13. DEFAULT CONFIGURATION
-- ═══════════════════════════════════════════════════════════════════════════════

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
('generation.default_image_backends', '["pollinations","hf_inference","colab_comfyui"]', 'Image backend priority order — cloud only, no local GPU', 'generation', 'array'),
('generation.default_tts_backends', '["edge_tts","colab_kokoro"]', 'TTS backend priority order — cloud only', 'generation', 'array'),
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

-- ═══════════════════════════════════════════════════════════════════════════════
-- 14. EVENT TYPE DEFINITIONS
-- ═══════════════════════════════════════════════════════════════════════════════

INSERT INTO cineos_core.event_types (event_type, category, severity, description) VALUES
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

-- ═══════════════════════════════════════════════════════════════════════════════
-- SCHEMA COMPLETE
-- ═══════════════════════════════════════════════════════════════════════════════
