"""Database integration tests against the real CineOS PostgreSQL schema."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest


# ── Projects ───────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_project(db_pool: asyncpg.Pool):
    pid = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.projects
                (project_id, user_id, chat_id, title, current_state, language)
            VALUES ($1, 100, 200, 'My Test Project', 'received', 'en')
            """,
            pid,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.projects WHERE project_id = $1", pid
        )
        assert row is not None
        assert row["title"] == "My Test Project"
        assert row["current_state"] == "received"
        assert row["user_id"] == 100
        assert row["chat_id"] == 200
        assert row["progress"] >= 0.0
        await conn.execute(
            "DELETE FROM cineos_core.projects WHERE project_id = $1", pid
        )


@pytest.mark.integration
async def test_state_transition_valid(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cineos_core.projects
            SET current_state = 'validated'
            WHERE project_id = $1
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT current_state, previous_state FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        assert row["current_state"] == "validated"
        assert row["previous_state"] == "received"


@pytest.mark.integration
async def test_state_transition_invalid(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    async with db_pool.acquire() as conn:
        with pytest.raises(asyncpg.RaiseError, match="Invalid state transition"):
            await conn.execute(
                """
                UPDATE cineos_core.projects
                SET current_state = 'completed'
                WHERE project_id = $1
                """,
                test_project,
            )


# ── Novels ─────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_novel(
    db_pool: asyncpg.Pool, test_project: uuid.UUID
):
    novel_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.novels
                (novel_id, project_id, title, raw_text, cleaned_text,
                 word_count, char_count, encoding, language)
            VALUES ($1, $2, 'The Great Adventure', 'raw', 'cleaned',
                    1000, 5000, 'utf-8', 'en')
            """,
            novel_id,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.novels WHERE novel_id = $1", novel_id
        )
        assert row["title"] == "The Great Adventure"
        assert row["word_count"] == 1000
        assert row["project_id"] == test_project
        await conn.execute(
            "DELETE FROM cineos_core.novels WHERE novel_id = $1", novel_id
        )


# ── Chapters ───────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_chapter(
    db_pool: asyncpg.Pool, test_project: uuid.UUID, test_novel: uuid.UUID
):
    chapter_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.chapters
                (chapter_id, novel_id, project_id, chapter_number, title,
                 summary, text, word_count, scene_count)
            VALUES ($1, $2, $3, 1, 'The Beginning', 'An opening chapter',
                    'It was a dark and stormy night...', 2500, 5)
            """,
            chapter_id,
            test_novel,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.chapters WHERE chapter_id = $1",
            chapter_id,
        )
        assert row["title"] == "The Beginning"
        assert row["word_count"] == 2500
        assert row["scene_count"] == 5
        await conn.execute(
            "DELETE FROM cineos_core.chapters WHERE chapter_id = $1", chapter_id
        )


# ── Scenes ─────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_scene(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_chapter: uuid.UUID,
):
    scene_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.scenes
                (scene_id, project_id, chapter_id, chapter_number, scene_number,
                 state, full_text, summary, location_name, time_of_day,
                 primary_emotion, conflict_type, importance, has_dialogue,
                 has_action, visual_priority, shot_count)
            VALUES ($1, $2, $3, 1, 1, 'pending',
                    'The hero stood at the edge of the cliff.',
                    'Hero at cliff edge',
                    'Cliffside', 'sunset', 'tension', 'man_vs_nature',
                    'critical', true, false, 0.9, 7)
            """,
            scene_id,
            test_project,
            test_chapter,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.scenes WHERE scene_id = $1", scene_id
        )
        assert row["summary"] == "Hero at cliff edge"
        assert row["primary_emotion"] == "tension"
        assert row["importance"] == "critical"
        assert row["has_dialogue"] is True
        assert row["shot_count"] == 7
        await conn.execute(
            "DELETE FROM cineos_core.scenes WHERE scene_id = $1", scene_id
        )


# ── Shots ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_shot(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_scene: uuid.UUID,
):
    shot_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.shots
                (shot_id, scene_id, project_id, chapter_number, scene_number,
                 shot_number, state, shot_type, importance, duration_seconds,
                 camera_angle, camera_movement, depth_of_field,
                 lighting_style, composition, positive_prompt, negative_prompt,
                 narration_text, narration_voice, narration_emotion)
            VALUES ($1, $2, $3, 1, 1, 1, 'pending', 'close_up', 'critical',
                    4.5, 'low_angle', 'dolly_in', 'shallow',
                    'golden_hour', 'rule_of_thirds',
                    'A warrior staring into the distance, cinematic',
                    'blurry, deformed, ugly',
                    'She gazed across the valley.', 'female_warm', 'determined')
            """,
            shot_id,
            test_scene,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.shots WHERE shot_id = $1", shot_id
        )
        assert row["shot_type"] == "close_up"
        assert row["duration_seconds"] == 4.5
        assert row["camera_angle"] == "low_angle"
        assert row["lighting_style"] == "golden_hour"
        assert row["narration_voice"] == "female_warm"
        await conn.execute(
            "DELETE FROM cineos_core.shots WHERE shot_id = $1", shot_id
        )


# ── Characters (40+ fields) ────────────────────────────────────────


@pytest.mark.integration
async def test_create_character(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
):
    char_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.characters
                (character_id, project_id, canonical_name, role, gender,
                 estimated_age, ethnicity, body_type, height, build,
                 face_shape, jaw_shape, nose_shape, eye_shape, eye_color,
                 eye_expression, eyebrow_shape, lip_shape,
                 hair_style, hair_length, hair_color, hair_texture,
                 skin_tone, skin_texture,
                 default_outfit, formal_outfit, combat_outfit,
                 primary_weapon, secondary_weapon,
                 personality_traits, core_values, fears, desires, habits,
                 speech_patterns, verbal_tics, voice_description,
                 voice_pitch, voice_pace, voice_accent,
                 visual_prompt_positive, visual_prompt_negative,
                 confidence_score, locked)
            VALUES ($1, $2, 'Garrin', 'antagonist', 'male',
                    '35', 'Northern', 'muscular', '6ft 2in', 'broad',
                    'square', 'strong', 'aquiline', 'narrow', 'green',
                    'piercing', 'thick', 'thin',
                    'shaved', 'none', 'black', 'coarse',
                    'dark', 'weathered',
                    'black plate armour', 'formal cape', 'battle-worn leather',
                    'greatsword', 'dagger',
                    ARRAY['ruthless','cunning','honorable'], ARRAY['power','order'],
                    ARRAY['betrayal'], ARRAY['legacy'], ARRAY['training daily'],
                    'speaks in commands', ARRAY['grunts'],
                    'deep baritone', 'low', 'slow', 'Northern accent',
                    'imposing man in black armour with scarred face',
                    'cartoon, anime, deformed',
                    0.88, false)
            """,
            char_id,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.characters WHERE character_id = $1",
            char_id,
        )
        assert row["canonical_name"] == "Garrin"
        assert row["role"] == "antagonist"
        assert row["gender"] == "male"
        assert row["eye_color"] == "green"
        assert row["hair_color"] == "black"
        assert row["confidence_score"] == pytest.approx(0.88)
        assert "ruthless" in row["personality_traits"]
        assert "power" in row["core_values"]
        assert row["voice_pitch"] == "low"
        await conn.execute(
            "DELETE FROM cineos_core.characters WHERE character_id = $1", char_id
        )


# ── Locations ──────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_location(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
):
    loc_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.locations
                (location_id, project_id, name, location_type, description,
                 detailed_description, atmosphere, mood, size,
                 architecture_style, lighting_default, visual_atmosphere,
                 visual_keywords, scene_count)
            VALUES ($1, $2, 'Throne Room', 'indoor',
                    'A grand hall of obsidian and gold',
                    'Pillars carved from volcanic stone...',
                    'oppressive', 'grand', 'massive',
                    'gothic-industrial', 'harsh overhead', 'dark elegance',
                    ARRAY['obsidian','gold','firelight'], 3)
            """,
            loc_id,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.locations WHERE location_id = $1",
            loc_id,
        )
        assert row["name"] == "Throne Room"
        assert row["location_type"] == "indoor"
        assert "obsidian" in row["visual_keywords"]
        await conn.execute(
            "DELETE FROM cineos_core.locations WHERE location_id = $1", loc_id
        )


# ── Scene-Character junction (M2M) ─────────────────────────────────


@pytest.mark.integration
async def test_scene_character_junction(
    db_pool: asyncpg.Pool,
    test_scene: uuid.UUID,
    test_character: uuid.UUID,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.scene_characters
                (scene_id, character_id, role, emotional_state,
                 screen_time_seconds)
            VALUES ($1, $2, 'protagonist', 'determined', 12.5)
            """,
            test_scene,
            test_character,
        )
        rows = await conn.fetch(
            """
            SELECT sc.*, c.canonical_name
            FROM cineos_core.scene_characters sc
            JOIN cineos_core.characters c ON c.character_id = sc.character_id
            WHERE sc.scene_id = $1
            """,
            test_scene,
        )
        assert len(rows) == 1
        assert rows[0]["role"] == "protagonist"
        assert rows[0]["canonical_name"] == "Elara"
        assert rows[0]["screen_time_seconds"] == pytest.approx(12.5)
        await conn.execute(
            """
            DELETE FROM cineos_core.scene_characters
            WHERE scene_id = $1 AND character_id = $2
            """,
            test_scene,
            test_character,
        )


# ── Quality reviews ────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_review(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
):
    review_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, prompt_alignment_score,
                 character_consistency_score, world_consistency_score,
                 composition_score, passed, decision, issues, recommendations,
                 reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated',
                    0.85, 0.90, 0.80, 0.88, 0.75, 0.82,
                    true, 'approved', $4::jsonb, $5::jsonb, 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
            json.dumps(["slight color shift"]),
            json.dumps(["consider color correction"]),
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["overall_score"] == pytest.approx(0.85)
        assert row["passed"] is True
        assert row["decision"] == "approved"
        assert row["technical_quality_score"] == pytest.approx(0.90)
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


# ── Repairs ────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_repair(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
):
    review_id = uuid.uuid4()
    repair_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.45, false,
                    'minor_repair', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        await conn.execute(
            """
            INSERT INTO cineos_quality.repairs
                (repair_id, project_id, review_id, entity_type, entity_id,
                 failure_reason, failure_score, failure_issues,
                 repair_strategy, repair_description,
                 repair_attempt_number, max_repair_attempts,
                 pre_repair_score, post_repair_score, improvement, success)
            VALUES ($1, $2, $3, 'image', $4,
                    'low prompt alignment', 0.45, $5::jsonb,
                    'regenerate_with_modified_prompt',
                    'Adjusted prompt to improve character features',
                    1, 3, 0.45, 0.72, 0.27, true)
            """,
            repair_id,
            test_project,
            review_id,
            entity_id,
            json.dumps(["prompt alignment too low"]),
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_quality.repairs WHERE repair_id = $1",
            repair_id,
        )
        assert row["pre_repair_score"] == pytest.approx(0.45)
        assert row["post_repair_score"] == pytest.approx(0.72)
        assert row["improvement"] == pytest.approx(0.27)
        assert row["success"] is True
        await conn.execute(
            "DELETE FROM cineos_quality.repairs WHERE repair_id = $1", repair_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


# ── Quality checks ─────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_check(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
):
    review_id = uuid.uuid4()
    check_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.70, true,
                    'approved', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        await conn.execute(
            """
            INSERT INTO cineos_quality.checks
                (check_id, project_id, review_id, entity_type, entity_id,
                 check_name, check_category, score, weight, passed,
                 threshold, duration_ms)
            VALUES ($1, $2, $3, 'image', $4,
                    'technical_quality', 'technical', 0.92, 1.0, true,
                    0.60, 150)
            """,
            check_id,
            test_project,
            review_id,
            entity_id,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_quality.checks WHERE check_id = $1",
            check_id,
        )
        assert row["check_name"] == "technical_quality"
        assert row["score"] == pytest.approx(0.92)
        assert row["passed"] is True
        assert row["threshold"] == pytest.approx(0.60)
        await conn.execute(
            "DELETE FROM cineos_quality.checks WHERE check_id = $1", check_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


# ── Jobs ───────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_job(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_worker: uuid.UUID,
):
    job_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_exec.jobs
                (job_id, project_id, job_type, state, worker_id,
                 priority, payload, timeout_ms, max_retries)
            VALUES ($1, $2, 'image_generate', 'pending', $3,
                    8, $4::jsonb, 300000, 3)
            """,
            job_id,
            test_project,
            test_worker,
            json.dumps({"shot_id": str(uuid.uuid4()), "variant": 2}),
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        assert row["job_type"] == "image_generate"
        assert row["state"] == "pending"
        assert row["priority"] == 8

        await conn.execute(
            "UPDATE cineos_exec.jobs SET state = 'assigned', assigned_at = NOW() WHERE job_id = $1",
            job_id,
        )
        row = await conn.fetchrow(
            "SELECT state FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )
        assert row["state"] == "assigned"

        await conn.execute(
            "UPDATE cineos_exec.jobs SET state = 'completed', completed_at = NOW() WHERE job_id = $1",
            job_id,
        )
        row = await conn.fetchrow(
            "SELECT state, completed_at FROM cineos_exec.jobs WHERE job_id = $1",
            job_id,
        )
        assert row["state"] == "completed"
        assert row["completed_at"] is not None

        await conn.execute(
            "DELETE FROM cineos_exec.jobs WHERE job_id = $1", job_id
        )


# ── Workers ────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_worker(db_pool: asyncpg.Pool):
    worker_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_exec.workers
                (worker_id, worker_name, worker_type, state, host, port,
                 supported_task_types, gpu_model, gpu_vram_gb, ram_gb,
                 max_concurrent_tasks, enabled, health_status)
            VALUES ($1, 'gpu-worker-01', 'image_generation', 'idle',
                    '10.0.0.5', 8001,
                    ARRAY['image_generate', 'image_upscale'],
                    'RTX 4090', 24.0, 64.0, 2, true, 'healthy')
            """,
            worker_id,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )
        assert row["worker_name"] == "gpu-worker-01"
        assert row["worker_type"] == "image_generation"
        assert row["gpu_model"] == "RTX 4090"
        assert row["gpu_vram_gb"] == pytest.approx(24.0)
        assert row["enabled"] is True
        await conn.execute(
            "DELETE FROM cineos_exec.workers WHERE worker_id = $1", worker_id
        )


# ── Progress calculation (DB trigger) ──────────────────────────────


@pytest.mark.integration
async def test_update_progress(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cineos_core.projects
            SET current_state = 'generating'
            WHERE project_id = $1
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT progress FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        assert row["progress"] == pytest.approx(0.50)

        await conn.execute(
            """
            UPDATE cineos_core.projects
            SET current_state = 'completed'
            WHERE project_id = $1
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT progress FROM cineos_core.projects WHERE project_id = $1",
            test_project,
        )
        assert row["progress"] == pytest.approx(1.00)


# ── Versioning ─────────────────────────────────────────────────────


@pytest.mark.integration
async def test_versioning(
    db_pool: asyncpg.Pool,
    test_project: uuid.UUID,
    test_character: uuid.UUID,
):
    v1_id = uuid.uuid4()
    v2_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.versions
                (version_id, entity_type, entity_id, project_id,
                 version_number, data_snapshot, author, change_reason,
                 change_type, is_current)
            VALUES ($1, 'character', $2, $3, 1, $4::jsonb,
                    'system', 'Initial extraction', 'creation', false)
            """,
            v1_id,
            test_character,
            test_project,
            json.dumps({"name": "Elara", "eye_color": "blue"}),
        )
        await conn.execute(
            """
            INSERT INTO cineos_core.versions
                (version_id, entity_type, entity_id, project_id,
                 version_number, data_snapshot, author, change_reason,
                 change_type, is_current)
            VALUES ($1, 'character', $2, $3, 2, $4::jsonb,
                    'repair_worker', 'Fixed hair color', 'repair', true)
            """,
            v2_id,
            test_character,
            test_project,
            json.dumps({"name": "Elara", "eye_color": "blue", "hair_color": "red"}),
        )
        row = await conn.fetchrow(
            """
            SELECT * FROM cineos_core.versions
            WHERE entity_id = $1 AND is_current = true
            """,
            test_character,
        )
        assert row is not None
        assert row["version_number"] == 2
        assert row["author"] == "repair_worker"
        snapshot = row["data_snapshot"]
        assert snapshot["hair_color"] == "red"

        all_versions = await conn.fetch(
            """
            SELECT version_number FROM cineos_core.versions
            WHERE entity_id = $1 ORDER BY version_number
            """,
            test_character,
        )
        assert len(all_versions) == 2
        await conn.execute(
            "DELETE FROM cineos_core.versions WHERE entity_id = $1",
            test_character,
        )


# ── Checkpoints ────────────────────────────────────────────────────


@pytest.mark.integration
async def test_checkpoint(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    cp_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.checkpoints
                (checkpoint_id, project_id, state_at_checkpoint,
                 completed_phases, current_phase,
                 chapter_count, scene_count, shot_count,
                 character_count, location_count)
            VALUES ($1, $2, 'generated',
                    ARRAY['intake','analysis','verification','prompt_plan'],
                    'generated', 3, 12, 45, 5, 4)
            """,
            cp_id,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_core.checkpoints WHERE checkpoint_id = $1",
            cp_id,
        )
        assert row["state_at_checkpoint"] == "generated"
        assert "analysis" in row["completed_phases"]
        assert row["scene_count"] == 12
        assert row["shot_count"] == 45
        await conn.execute(
            "DELETE FROM cineos_core.checkpoints WHERE checkpoint_id = $1",
            cp_id,
        )


# ── Event logging ──────────────────────────────────────────────────


@pytest.mark.integration
async def test_event_logging(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    event_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.events
                (id, project_id, event_type, workflow, state_before,
                 state_after, severity, message, payload)
            VALUES ($1, $2, 'PROJECT_CREATED', 'main_pipeline',
                    NULL, 'received', 'info', 'New project created',
                    $3::jsonb)
            """,
            event_id,
            test_project,
            json.dumps({"source": "telegram", "user_id": 12345}),
        )
        rows = await conn.fetch(
            """
            SELECT * FROM cineos_core.events
            WHERE project_id = $1 AND event_type = 'PROJECT_CREATED'
            """,
            test_project,
        )
        assert len(rows) >= 1
        assert rows[0]["severity"] == "info"
        assert rows[0]["message"] == "New project created"
        assert rows[0]["payload"]["source"] == "telegram"
        await conn.execute(
            "DELETE FROM cineos_core.events WHERE id = $1", event_id
        )


# ── State log ──────────────────────────────────────────────────────


@pytest.mark.integration
async def test_state_log(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_core.state_log
                (project_id, entity_type, entity_id, old_state, new_state,
                 workflow, operator, reason)
            VALUES ($1, 'project', $1, 'received', 'validated',
                    'intake_worker', 'auto_validator', 'Input file validated')
            """,
            test_project,
        )
        rows = await conn.fetch(
            "SELECT * FROM cineos_core.state_log WHERE project_id = $1",
            test_project,
        )
        assert len(rows) >= 1
        assert rows[0]["old_state"] == "received"
        assert rows[0]["new_state"] == "validated"
        assert rows[0]["operator"] == "auto_validator"
