-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Analytical Views
-- ═══════════════════════════════════════════════════════════════════════════════

-- Project summary with scene/shot counts, progress, quality scores
CREATE OR REPLACE VIEW cineos_core.v_project_summary AS
SELECT
    p.project_id,
    p.title,
    p.user_id,
    p.chat_id,
    p.current_state,
    p.previous_state,
    p.progress,
    p.priority,
    p.language,
    p.created_at,
    p.updated_at,
    p.started_at,
    p.completed_at,
    COALESCE(sc.scene_count, 0) AS scene_count,
    COALESCE(shot_data.shot_count, 0) AS shot_count,
    COALESCE(ch.chapter_count, 0) AS chapter_count,
    COALESCE(cu.character_count, 0) AS character_count,
    COALESCE(lo.location_count, 0) AS location_count,
    COALESCE(qa.avg_quality, 0) AS avg_quality_score,
    COALESCE(qa.review_count, 0) AS total_reviews,
    COALESCE(re.repair_count, 0) AS total_repairs,
    COALESCE(jb.active_jobs, 0) AS active_jobs,
    COALESCE(jb.completed_jobs, 0) AS completed_jobs
FROM cineos_core.projects p
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS scene_count
    FROM cineos_core.scenes s
    WHERE s.project_id = p.project_id
) sc ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS shot_count
    FROM cineos_core.shots sh
    WHERE sh.project_id = p.project_id
) shot_data ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS chapter_count
    FROM cineos_core.chapters ch
    WHERE ch.project_id = p.project_id
) ch ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS character_count
    FROM cineos_core.characters cu
    WHERE cu.project_id = p.project_id
) cu ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS location_count
    FROM cineos_core.locations lo
    WHERE lo.project_id = p.project_id
) lo ON TRUE
LEFT JOIN LATERAL (
    SELECT AVG(overall_score) AS avg_quality, COUNT(*) AS review_count
    FROM cineos_quality.reviews r
    WHERE r.project_id = p.project_id
) qa ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS repair_count
    FROM cineos_quality.repairs rp
    WHERE rp.project_id = p.project_id
) re ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE j.state IN ('pending', 'queued', 'assigned', 'running')) AS active_jobs,
        COUNT(*) FILTER (WHERE j.state = 'completed') AS completed_jobs
    FROM cineos_exec.jobs j
    WHERE j.project_id = p.project_id
) jb ON TRUE;

-- Active projects (not in terminal states)
CREATE OR REPLACE VIEW cineos_core.v_active_projects AS
SELECT *
FROM cineos_core.v_project_summary
WHERE current_state NOT IN ('completed', 'cancelled', 'failed');

-- Quality dashboard: scores per entity
CREATE OR REPLACE VIEW cineos_quality.v_quality_dashboard AS
SELECT
    r.review_id,
    r.project_id,
    r.entity_type,
    r.entity_id,
    r.review_type,
    r.overall_score,
    r.technical_quality_score,
    r.prompt_alignment_score,
    r.character_consistency_score,
    r.world_consistency_score,
    r.composition_score,
    r.audio_quality_score,
    r.naturalness_score,
    r.emotion_match_score,
    r.duration_fit_score,
    r.audio_video_sync_score,
    r.narrative_fidelity_score,
    r.passed,
    r.decision,
    r.issues,
    r.recommendations,
    r.reviewer_model,
    r.created_at,
    t.min_image_quality,
    t.min_character_consistency,
    t.min_world_consistency,
    t.min_composition,
    t.min_prompt_alignment,
    t.min_audio_quality,
    t.min_naturalness,
    t.min_overall_quality
FROM cineos_quality.reviews r
LEFT JOIN cineos_quality.thresholds t ON t.project_id = r.project_id
ORDER BY r.created_at DESC;

-- Worker status summary
CREATE OR REPLACE VIEW cineos_exec.v_worker_status AS
SELECT
    w.worker_id,
    w.worker_name,
    w.worker_type,
    w.state,
    w.host,
    w.enabled,
    w.current_load,
    w.max_concurrent_tasks,
    w.priority,
    w.total_tasks_completed,
    w.total_tasks_failed,
    w.success_rate,
    w.avg_task_duration_ms,
    w.last_heartbeat,
    w.health_status,
    w.gpu_model,
    w.gpu_vram_gb,
    w.gpu_memory_used_mb,
    w.gpu_memory_total_mb,
    w.cpu_usage_percent,
    w.ram_usage_percent,
    COALESCE(j.running_jobs, 0) AS running_jobs,
    COALESCE(j.queued_jobs, 0) AS queued_jobs,
    CASE
        WHEN w.last_heartbeat IS NULL THEN 'never'
        WHEN w.last_heartbeat < NOW() - INTERVAL '90 seconds' THEN 'stale'
        ELSE 'alive'
    END AS heartbeat_status
FROM cineos_exec.workers w
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE j2.state = 'running') AS running_jobs,
        COUNT(*) FILTER (WHERE j2.state = 'queued') AS queued_jobs
    FROM cineos_exec.jobs j2
    WHERE j2.worker_id = w.worker_id
) j ON TRUE;

-- Pending/running jobs
CREATE OR REPLACE VIEW cineos_exec.v_job_queue AS
SELECT
    j.job_id,
    j.project_id,
    j.job_type,
    j.state,
    j.priority,
    j.retry_count,
    j.max_retries,
    j.payload,
    j.result,
    j.worker_id,
    w.worker_name,
    w.worker_type AS worker_type_name,
    j.queued_at,
    j.assigned_at,
    j.started_at,
    j.completed_at,
    j.timeout_ms,
    j.error_message,
    j.error_code,
    j.is_recoverable,
    j.created_at,
    CASE
        WHEN j.started_at IS NOT NULL AND j.completed_at IS NULL
            THEN EXTRACT(EPOCH FROM (NOW() - j.started_at)) * 1000
        WHEN j.assigned_at IS NOT NULL AND j.started_at IS NULL
            THEN EXTRACT(EPOCH FROM (NOW() - j.assigned_at)) * 1000
        ELSE NULL
    END AS elapsed_ms,
    CASE
        WHEN j.started_at IS NOT NULL AND j.completed_at IS NULL
            THEN j.timeout_ms - (EXTRACT(EPOCH FROM (NOW() - j.started_at)) * 1000)
        ELSE NULL
    END AS remaining_ms
FROM cineos_exec.jobs j
LEFT JOIN cineos_exec.workers w ON w.worker_id = j.worker_id
WHERE j.state IN ('pending', 'queued', 'assigned', 'running')
ORDER BY j.priority ASC, j.created_at ASC;

-- Project timeline: state transition history
CREATE OR REPLACE VIEW cineos_audit.v_project_timeline AS
SELECT
    sl.id,
    sl.project_id,
    p.title AS project_title,
    sl.entity_type,
    sl.entity_id,
    sl.old_state,
    sl.new_state,
    sl.workflow,
    sl.operator,
    sl.reason,
    sl.duration_ms,
    sl.created_at,
    LAG(sl.new_state) OVER (
        PARTITION BY sl.project_id, sl.entity_type, sl.entity_id
        ORDER BY sl.created_at
    ) AS previous_new_state,
    EXTRACT(EPOCH FROM (
        sl.created_at - LAG(sl.created_at) OVER (
            PARTITION BY sl.project_id, sl.entity_type, sl.entity_id
            ORDER BY sl.created_at
        )
    )) AS seconds_in_previous_state
FROM cineos_core.state_log sl
LEFT JOIN cineos_core.projects p ON p.project_id = sl.project_id
ORDER BY sl.project_id, sl.entity_type, sl.entity_id, sl.created_at;
