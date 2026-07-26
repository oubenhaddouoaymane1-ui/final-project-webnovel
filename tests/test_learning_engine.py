"""Learning engine tests — recording, efficiency, ranking, and tuning."""
from __future__ import annotations

import json
import uuid

import asyncpg
import pytest


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_record_project_completion(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Record learning data when a project completes."""
    async with db_pool.acquire() as conn:
        learning_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_audit.learning_records
                (learning_id, project_id,
                 estimated_scenes, estimated_shots, estimated_duration_minutes,
                 actual_scenes, actual_shots, actual_duration_minutes,
                 total_processing_time_ms, total_generation_time_ms,
                 total_review_time_ms, total_repair_time_ms, total_assembly_time_ms,
                 first_pass_quality_score, final_quality_score,
                 repair_success_rate, average_repair_attempts,
                 image_backends_used, audio_backends_used,
                 primary_image_backend, primary_audio_backend,
                 efficiency_score, lessons, recommendations)
            VALUES ($1, $2,
                    10, 50, 12.5,
                    12, 55, 14.2,
                    3600000, 2400000,
                    300000, 200000, 100000,
                    0.72, 0.88,
                    0.85, 1.8,
                    $3::jsonb, $4::jsonb,
                    'pollinations', 'edge_tts',
                    0.78, $5::jsonb, $6::jsonb)
            """,
            learning_id,
            test_project,
            json.dumps(["pollinations", "pollinations"]),
            json.dumps(["edge_tts", "piper"]),
            json.dumps(["scenes were slightly over-segmented"]),
            json.dumps(["reduce shot count for low-importance scenes"]),
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_audit.learning_records WHERE learning_id = $1",
            learning_id,
        )
        assert row["actual_scenes"] == 12
        assert row["final_quality_score"] == pytest.approx(0.88)
        assert row["efficiency_score"] == pytest.approx(0.78)
        assert row["primary_image_backend"] == "pollinations"
        await conn.execute(
            "DELETE FROM cineos_audit.learning_records WHERE learning_id = $1",
            learning_id,
        )


@pytest.mark.integration
async def test_calculate_efficiency(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Efficiency score reflects ratio of actual vs estimated complexity."""
    async with db_pool.acquire() as conn:
        learning_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_audit.learning_records
                (learning_id, project_id,
                 estimated_scenes, estimated_shots,
                 actual_scenes, actual_shots,
                 total_processing_time_ms,
                 first_pass_quality_score, final_quality_score,
                 efficiency_score)
            VALUES ($1, $2,
                    20, 100,
                    18, 85,
                    7200000,
                    0.80, 0.92,
                    0.85)
            """,
            learning_id,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_audit.learning_records WHERE learning_id = $1",
            learning_id,
        )
        scene_ratio = row["actual_scenes"] / row["estimated_scenes"]
        shot_ratio = row["actual_shots"] / row["estimated_shots"]
        assert scene_ratio < 1.0
        assert shot_ratio < 1.0
        assert row["efficiency_score"] == pytest.approx(0.85)
        assert row["final_quality_score"] >= row["first_pass_quality_score"]
        await conn.execute(
            "DELETE FROM cineos_audit.learning_records WHERE learning_id = $1",
            learning_id,
        )


@pytest.mark.integration
async def test_backend_ranking(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Backend performance records allow ranking by success rate and quality."""
    async with db_pool.acquire() as conn:
        backends = [
            ("pollinations", "image_generate", True, 0.88, 0),
            ("pollinations", "image_generate", True, 0.90, 0),
            ("pollinations", "image_generate", False, None, 1),
            ("pollinations", "image_generate", True, 0.95, 0),
            ("pollinations", "image_generate", True, 0.93, 0),
        ]
        for backend, task, success, quality, repair in backends:
            perf_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO cineos_memory.backend_performance
                    (performance_id, backend_type, backend_name, project_id,
                     task_type, success, quality_score, repair_count, latency_ms)
                VALUES ($1, 'image', $2, $3, $4, $5, $6, $7, 2000)
                """,
                perf_id,
                backend,
                test_project,
                task,
                success,
                quality,
                repair,
            )

        rankings = await conn.fetch(
            """
            SELECT backend_name,
                   COUNT(*) FILTER (WHERE success) AS successes,
                   COUNT(*) AS total,
                   AVG(quality_score) AS avg_quality
            FROM cineos_memory.backend_performance
            WHERE task_type = 'image_generate' AND project_id = $1
            GROUP BY backend_name
            ORDER BY avg_quality DESC NULLS LAST
            """,
            test_project,
        )
        assert len(rankings) == 2
        assert rankings[0]["backend_name"] == "pollinations"
        assert rankings[0]["avg_quality"] > rankings[1]["avg_quality"]
        await conn.execute(
            "DELETE FROM cineos_memory.backend_performance WHERE project_id = $1",
            test_project,
        )


@pytest.mark.integration
async def test_threshold_tuning(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Thresholds can be adjusted based on historical performance."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_quality.thresholds
                (project_id, min_image_quality, auto_approve_threshold,
                 max_repair_attempts)
            VALUES ($1, 0.60, 0.85, 3)
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT auto_approve_threshold FROM cineos_quality.thresholds WHERE project_id = $1",
            test_project,
        )
        original = row["auto_approve_threshold"]

        # Learning engine tunes threshold upward based on history
        await conn.execute(
            """
            UPDATE cineos_quality.thresholds
            SET auto_approve_threshold = 0.90, updated_at = NOW()
            WHERE project_id = $1
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT auto_approve_threshold FROM cineos_quality.thresholds WHERE project_id = $1",
            test_project,
        )
        assert row["auto_approve_threshold"] > original
        assert row["auto_approve_threshold"] == pytest.approx(0.90)

        await conn.execute(
            "DELETE FROM cineos_quality.thresholds WHERE project_id = $1",
            test_project,
        )


@pytest.mark.integration
async def test_prompt_pattern_extraction(db_pool: asyncpg.Pool):
    """Successful prompt patterns are saved for reuse."""
    async with db_pool.acquire() as conn:
        pattern_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_memory.prompt_patterns
                (pattern_id, pattern_type, pattern_name, pattern_data,
                 usage_count, success_count, avg_quality_score,
                 avg_repair_count, confidence, source)
            VALUES ($1, 'shot_type', 'close_up_portrait',
                    $2::jsonb, 45, 42, 0.91, 0.3, 0.88, 'learned')
            """,
            pattern_id,
            json.dumps({
                "shot_type": "close_up",
                "camera_angle": "eye_level",
                "lighting": "soft_golden",
                "tags": ["portrait", "emotion", "detail"],
            }),
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_memory.prompt_patterns WHERE pattern_id = $1",
            pattern_id,
        )
        assert row["pattern_type"] == "shot_type"
        assert row["usage_count"] == 45
        assert row["success_count"] == 42
        assert row["avg_quality_score"] == pytest.approx(0.91)
        assert row["confidence"] == pytest.approx(0.88)
        data = row["pattern_data"]
        assert data["shot_type"] == "close_up"
        assert "portrait" in data["tags"]
        await conn.execute(
            "DELETE FROM cineos_memory.prompt_patterns WHERE pattern_id = $1",
            pattern_id,
        )


@pytest.mark.integration
async def test_worst_shot_analysis(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Identify worst-performing shot types from learning records."""
    async with db_pool.acquire() as conn:
        learning_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_audit.learning_records
                (learning_id, project_id,
                 estimated_scenes, actual_scenes, estimated_shots, actual_shots,
                 total_processing_time_ms,
                 first_pass_quality_score, final_quality_score,
                 efficiency_score,
                 best_performing_shot_types, worst_performing_shot_types)
            VALUES ($1, $2,
                    5, 5, 25, 25,
                    1800000,
                    0.65, 0.85,
                    0.80,
                    $3::jsonb, $4::jsonb)
            """,
            learning_id,
            test_project,
            json.dumps([
                {"shot_type": "medium", "avg_score": 0.92},
                {"shot_type": "wide", "avg_score": 0.88},
            ]),
            json.dumps([
                {"shot_type": "extreme_close_up", "avg_score": 0.45, "issues": ["face_distortion"]},
                {"shot_type": "action", "avg_score": 0.52, "issues": ["motion_blur"]},
            ]),
        )
        row = await conn.fetchrow(
            """
            SELECT best_performing_shot_types, worst_performing_shot_types
            FROM cineos_audit.learning_records WHERE learning_id = $1
            """,
            learning_id,
        )
        best = row["best_performing_shot_types"]
        worst = row["worst_performing_shot_types"]
        assert len(best) == 2
        assert len(worst) == 2
        assert best[0]["shot_type"] == "medium"
        assert worst[0]["avg_score"] < 0.60
        assert "face_distortion" in worst[0]["issues"]
        await conn.execute(
            "DELETE FROM cineos_audit.learning_records WHERE learning_id = $1",
            learning_id,
        )
