-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Utility Functions
-- ═══════════════════════════════════════════════════════════════════════════════

-- State machine transition with validation
CREATE OR REPLACE FUNCTION cineos_core.fn_transition_state(
    p_entity_type TEXT,
    p_entity_id UUID,
    p_new_state TEXT,
    p_workflow TEXT DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_project_id UUID;
    v_old_state TEXT;
    v_allowed_transitions JSONB;
BEGIN
    v_allowed_transitions := '{
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

    IF p_entity_type = 'project' THEN
        SELECT current_state, project_id INTO v_old_state, v_project_id
        FROM cineos_core.projects WHERE project_id = p_entity_id;

        IF v_old_state IS NULL THEN
            RAISE EXCEPTION 'Project % not found', p_entity_id;
        END IF;

        IF NOT (v_allowed_transitions ->> v_old_state) ? p_new_state THEN
            RAISE EXCEPTION 'Invalid state transition: % -> %', v_old_state, p_new_state;
        END IF;

        UPDATE cineos_core.projects
        SET current_state = p_new_state::project_state,
            previous_state = v_old_state::project_state,
            last_state_change_at = NOW()
        WHERE project_id = p_entity_id;

        INSERT INTO cineos_core.state_log (project_id, entity_type, entity_id, old_state, new_state, workflow)
        VALUES (v_project_id, p_entity_type, p_entity_id, v_old_state, p_new_state, p_workflow);
    ELSE
        RAISE EXCEPTION 'Unsupported entity type: %', p_entity_type;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Recalculate project progress percentage
CREATE OR REPLACE FUNCTION cineos_core.fn_update_progress(p_project_id UUID)
RETURNS FLOAT AS $$
DECLARE
    v_progress FLOAT;
    v_state project_state;
    v_progress_map JSONB;
BEGIN
    v_progress_map := '{
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

    SELECT current_state INTO v_state
    FROM cineos_core.projects WHERE project_id = p_project_id;

    IF v_state IS NULL THEN
        RAISE EXCEPTION 'Project % not found', p_project_id;
    END IF;

    v_progress := (v_progress_map ->> v_state::text)::float;

    IF v_progress IS NULL THEN
        v_progress := 0.0;
    END IF;

    UPDATE cineos_core.projects
    SET progress = v_progress
    WHERE project_id = p_project_id;

    RETURN v_progress;
END;
$$ LANGUAGE plpgsql;

-- Insert event
CREATE OR REPLACE FUNCTION cineos_core.fn_log_event(
    p_project_id UUID,
    p_event_type TEXT,
    p_message TEXT DEFAULT NULL,
    p_payload JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_id UUID;
    v_severity VARCHAR(20);
BEGIN
    SELECT severity INTO v_severity
    FROM cineos_core.event_types WHERE event_type = p_event_type;

    IF v_severity IS NULL THEN
        v_severity := 'info';
    END IF;

    INSERT INTO cineos_core.events (project_id, event_type, severity, message, payload)
    VALUES (p_project_id, p_event_type, v_severity, p_message, p_payload)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- Calculate weighted overall score from quality checks
CREATE OR REPLACE FUNCTION cineos_quality.fn_calculate_quality_score(p_review_id UUID)
RETURNS FLOAT AS $$
DECLARE
    v_overall FLOAT;
    v_total_weight FLOAT;
    v_weighted_sum FLOAT;
    v_check RECORD;
BEGIN
    v_total_weight := 0;
    v_weighted_sum := 0;

    FOR v_check IN
        SELECT score, weight FROM cineos_quality.checks WHERE review_id = p_review_id
    LOOP
        v_weighted_sum := v_weighted_sum + (v_check.score * v_check.weight);
        v_total_weight := v_total_weight + v_check.weight;
    END LOOP;

    IF v_total_weight > 0 THEN
        v_overall := v_weighted_sum / v_total_weight;
    ELSE
        v_overall := 0.0;
    END IF;

    UPDATE cineos_quality.reviews
    SET overall_score = v_overall
    WHERE review_id = p_review_id;

    RETURN v_overall;
END;
$$ LANGUAGE plpgsql;

-- Assign job to worker
CREATE OR REPLACE FUNCTION cineos_exec.fn_assign_job(
    p_job_id UUID,
    p_worker_id UUID
) RETURNS VOID AS $$
DECLARE
    v_job_state job_state;
BEGIN
    SELECT state INTO v_job_state
    FROM cineos_exec.jobs WHERE job_id = p_job_id;

    IF v_job_state IS NULL THEN
        RAISE EXCEPTION 'Job % not found', p_job_id;
    END IF;

    IF v_job_state NOT IN ('pending', 'queued') THEN
        RAISE EXCEPTION 'Job % cannot be assigned in state %', p_job_id, v_job_state;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM cineos_exec.workers
        WHERE worker_id = p_worker_id AND state = 'idle' AND enabled = TRUE
    ) THEN
        RAISE EXCEPTION 'Worker % is not available', p_worker_id;
    END IF;

    UPDATE cineos_exec.jobs
    SET worker_id = p_worker_id,
        state = 'assigned',
        assigned_at = NOW()
    WHERE job_id = p_job_id;

    UPDATE cineos_exec.workers
    SET state = 'busy',
        current_load = current_load + 1
    WHERE worker_id = p_worker_id;
END;
$$ LANGUAGE plpgsql;

-- Mark job complete
CREATE OR REPLACE FUNCTION cineos_exec.fn_complete_job(
    p_job_id UUID,
    p_result JSONB DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_worker_id UUID;
BEGIN
    SELECT worker_id INTO v_worker_id
    FROM cineos_exec.jobs WHERE job_id = p_job_id;

    UPDATE cineos_exec.jobs
    SET state = 'completed',
        result = p_result,
        completed_at = NOW()
    WHERE job_id = p_job_id;

    IF v_worker_id IS NOT NULL THEN
        UPDATE cineos_exec.workers
        SET current_load = GREATEST(current_load - 1, 0),
            total_tasks_completed = total_tasks_completed + 1,
            last_task_completed_at = NOW()
        WHERE worker_id = v_worker_id;

        UPDATE cineos_exec.workers
        SET state = CASE
            WHEN current_load <= 0 THEN 'idle'::worker_state
            ELSE state
        END
        WHERE worker_id = v_worker_id AND current_load <= 0;
    END IF;
END;
$$ LANGUAGE plpgsql;
