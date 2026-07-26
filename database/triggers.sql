-- ═══════════════════════════════════════════════════════════════════════════════
-- CineOS — Trigger Functions and Trigger Definitions
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
