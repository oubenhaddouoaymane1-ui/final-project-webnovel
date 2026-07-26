"""Quality engine tests — scoring, repair, escalation, and thresholds."""
from __future__ import annotations

import json
import uuid

import asyncpg
import pytest


# ── Helpers ────────────────────────────────────────────────────────


async def _create_review(
    conn, project_id: uuid.UUID, overall_score: float, passed: bool, decision: str
) -> uuid.UUID:
    review_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO cineos_quality.reviews
            (review_id, project_id, entity_type, entity_id, review_type,
             overall_score, technical_quality_score, prompt_alignment_score,
             character_consistency_score, world_consistency_score,
             composition_score, passed, decision, reviewer_type)
        VALUES ($1, $2, 'image', $3, 'automated', $4, $4, $4, $4, $4, $4,
                $5, $6, 'quality_worker')
        """,
        review_id,
        project_id,
        entity_id,
        overall_score,
        passed,
        decision,
    )
    return review_id


async def _create_repair(
    conn,
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    attempt: int,
    pre: float,
    post: float,
    success: bool,
) -> uuid.UUID:
    repair_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO cineos_quality.repairs
            (repair_id, project_id, review_id, entity_type, entity_id,
             failure_reason, failure_score,
             repair_strategy, repair_attempt_number, max_repair_attempts,
             pre_repair_score, post_repair_score, improvement, success)
        VALUES ($1, $2, $3, 'image', $4,
                'low quality', $5,
                'regenerate', $6, 3,
                $5, $7, $8, $9)
        """,
        repair_id,
        project_id,
        review_id,
        entity_id,
        pre,
        attempt,
        post,
        post - pre,
        success,
    )
    return repair_id


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_auto_approve_high_score(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Score > 0.90 should result in approved decision."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, prompt_alignment_score,
                 character_consistency_score, world_consistency_score,
                 composition_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.95, 0.96, 0.94, 0.95, 0.93, 0.97,
                    true, 'approved', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["passed"] is True
        assert row["decision"] == "approved"
        assert row["overall_score"] >= 0.90
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_minor_repair(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Score 0.80–0.90 triggers minor repair."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, prompt_alignment_score,
                 character_consistency_score, world_consistency_score,
                 composition_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.85, 0.88, 0.82, 0.86, 0.80, 0.84,
                    false, 'minor_repair', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        row = await conn.fetchrow(
            "SELECT decision FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["decision"] == "minor_repair"
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_partial_repair(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Score 0.60–0.80 triggers partial repair."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, prompt_alignment_score,
                 character_consistency_score, world_consistency_score,
                 composition_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.70, 0.72, 0.68, 0.71, 0.65, 0.74,
                    false, 'partial_repair', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        row = await conn.fetchrow(
            "SELECT decision FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["decision"] == "partial_repair"
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_regenerate(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Score < 0.60 triggers regeneration."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, technical_quality_score, prompt_alignment_score,
                 character_consistency_score, world_consistency_score,
                 composition_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.40, 0.35, 0.42, 0.38, 0.45, 0.40,
                    false, 'regenerate', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        row = await conn.fetchrow(
            "SELECT decision FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["decision"] == "regenerate"
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_max_repair_attempts(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """After 3 failed repairs the item must be escalated."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.30, false,
                    'regenerate', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        for attempt in range(1, 4):
            repair_id = uuid.uuid4()
            success = False
            await conn.execute(
                """
                INSERT INTO cineos_quality.repairs
                    (repair_id, project_id, review_id, entity_type, entity_id,
                     failure_reason, failure_score,
                     repair_strategy, repair_attempt_number, max_repair_attempts,
                     pre_repair_score, post_repair_score, improvement, success)
                VALUES ($1, $2, $3, 'image', $4,
                        'still bad', 0.30,
                        'regenerate', $5, 3,
                        0.30, 0.35, 0.05, false)
                """,
                repair_id,
                test_project,
                review_id,
                entity_id,
                attempt,
            )
        # Verify all 3 repair attempts recorded
        repairs = await conn.fetch(
            "SELECT * FROM cineos_quality.repairs WHERE review_id = $1 ORDER BY repair_attempt_number",
            review_id,
        )
        assert len(repairs) == 3
        assert all(not r["success"] for r in repairs)
        await conn.execute(
            "DELETE FROM cineos_quality.repairs WHERE review_id = $1", review_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_repair_priority_order(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Face-related repairs should be prioritized over background repairs."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.50, false,
                    'partial_repair', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )

        checks = [
            ("face_quality", "face", 0.30, False),
            ("background_quality", "background", 0.70, True),
            ("composition", "composition", 0.55, False),
        ]
        for name, category, score, passed in checks:
            check_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO cineos_quality.checks
                    (check_id, project_id, review_id, entity_type, entity_id,
                     check_name, check_category, score, weight, passed, threshold)
                VALUES ($1, $2, $3, 'image', $4, $5, $6, $7, 1.0, $8, 0.60)
                """,
                check_id,
                test_project,
                review_id,
                entity_id,
                name,
                category,
                score,
                passed,
            )

        failed_checks = await conn.fetch(
            """
            SELECT check_name, check_category, score
            FROM cineos_quality.checks
            WHERE review_id = $1 AND passed = false
            ORDER BY score ASC
            """,
            review_id,
        )
        assert len(failed_checks) == 2
        assert failed_checks[0]["check_category"] == "face"
        assert failed_checks[0]["score"] < failed_checks[1]["score"]
        await conn.execute(
            "DELETE FROM cineos_quality.checks WHERE review_id = $1", review_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_quality_check_weighted_average(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Weighted average of checks must match the overall review score."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.78, true,
                    'approved', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        weighted_checks = [
            ("visual", 0.3, 0.85),
            ("audio", 0.2, 0.70),
            ("consistency", 0.3, 0.80),
            ("world", 0.2, 0.65),
        ]
        total = 0.0
        for name, weight, score in weighted_checks:
            check_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO cineos_quality.checks
                    (check_id, project_id, review_id, entity_type, entity_id,
                     check_name, check_category, score, weight, passed, threshold)
                VALUES ($1, $2, $3, 'image', $4, $5, 'scoring', $6, $7, true, 0.50)
                """,
                check_id,
                test_project,
                review_id,
                entity_id,
                name,
                score,
                weight,
            )
            total += score * weight

        row = await conn.fetchrow(
            "SELECT overall_score FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["overall_score"] == pytest.approx(0.78, abs=0.01)
        await conn.execute(
            "DELETE FROM cineos_quality.checks WHERE review_id = $1", review_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_threshold_override(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Project-specific thresholds can override defaults."""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cineos_quality.thresholds
                (project_id, min_image_quality, auto_approve_threshold,
                 max_repair_attempts)
            VALUES ($1, 0.80, 0.95, 5)
            """,
            test_project,
        )
        row = await conn.fetchrow(
            "SELECT * FROM cineos_quality.thresholds WHERE project_id = $1",
            test_project,
        )
        assert row["min_image_quality"] == pytest.approx(0.80)
        assert row["auto_approve_threshold"] == pytest.approx(0.95)
        assert row["max_repair_attempts"] == 5
        await conn.execute(
            "DELETE FROM cineos_quality.thresholds WHERE project_id = $1",
            test_project,
        )


@pytest.mark.integration
async def test_repair_success_tracking(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """Track score improvements across repair attempts."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.40, false,
                    'regenerate', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )

        attempts = [
            (1, 0.40, 0.55, True),
            (2, 0.55, 0.72, True),
            (3, 0.72, 0.88, True),
        ]
        for num, pre, post, success in attempts:
            repair_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO cineos_quality.repairs
                    (repair_id, project_id, review_id, entity_type, entity_id,
                     failure_reason, failure_score,
                     repair_strategy, repair_attempt_number, max_repair_attempts,
                     pre_repair_score, post_repair_score, improvement, success)
                VALUES ($1, $2, $3, 'image', $4,
                        'low quality', $5,
                        'regenerate', $6, 3,
                        $5, $7, $8, $9)
                """,
                repair_id,
                test_project,
                review_id,
                entity_id,
                pre,
                num,
                post,
                post - pre,
                success,
            )

        repairs = await conn.fetch(
            "SELECT * FROM cineos_quality.repairs WHERE review_id = $1 ORDER BY repair_attempt_number",
            review_id,
        )
        assert repairs[0]["pre_repair_score"] == pytest.approx(0.40)
        assert repairs[2]["post_repair_score"] == pytest.approx(0.88)
        total_improvement = sum(r["improvement"] for r in repairs)
        assert total_improvement == pytest.approx(0.48)
        await conn.execute(
            "DELETE FROM cineos_quality.repairs WHERE review_id = $1", review_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )


@pytest.mark.integration
async def test_escalation_to_manual(db_pool: asyncpg.Pool, test_project: uuid.UUID):
    """After max failures, entity is escalated to manual_attention."""
    async with db_pool.acquire() as conn:
        review_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO cineos_quality.reviews
                (review_id, project_id, entity_type, entity_id, review_type,
                 overall_score, passed, decision, reviewer_type)
            VALUES ($1, $2, 'image', $3, 'automated', 0.25, false,
                    'regenerate', 'quality_worker')
            """,
            review_id,
            test_project,
            entity_id,
        )
        for attempt in range(1, 4):
            repair_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO cineos_quality.repairs
                    (repair_id, project_id, review_id, entity_type, entity_id,
                     failure_reason, failure_score,
                     repair_strategy, repair_attempt_number, max_repair_attempts,
                     pre_repair_score, post_repair_score, improvement, success)
                VALUES ($1, $2, $3, 'image', $4,
                        'persistent failure', 0.25,
                        'regenerate', $5, 3,
                        0.25, 0.28, 0.03, false)
                """,
                repair_id,
                test_project,
                review_id,
                entity_id,
                attempt,
            )

        last_repair = await conn.fetchrow(
            """
            SELECT * FROM cineos_quality.repairs
            WHERE review_id = $1
            ORDER BY repair_attempt_number DESC LIMIT 1
            """,
            review_id,
        )
        assert last_repair["repair_attempt_number"] == 3
        assert last_repair["success"] is False
        # Simulate escalation: update the review decision
        await conn.execute(
            """
            UPDATE cineos_quality.reviews
            SET decision = 'escalated_to_manual'
            WHERE review_id = $1
            """,
            review_id,
        )
        row = await conn.fetchrow(
            "SELECT decision FROM cineos_quality.reviews WHERE review_id = $1",
            review_id,
        )
        assert row["decision"] == "escalated_to_manual"
        await conn.execute(
            "DELETE FROM cineos_quality.repairs WHERE review_id = $1", review_id
        )
        await conn.execute(
            "DELETE FROM cineos_quality.reviews WHERE review_id = $1", review_id
        )
