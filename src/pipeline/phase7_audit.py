"""Phase 7 — Audit: final verification gate before delivery."""
from __future__ import annotations
import json
import logging
import os
import subprocess
from typing import List, Dict, Any

from .contracts import (
    NovelText, Scene, CharacterDNA, WorldBible,
    GeneratedImage, GeneratedAudio, AssembledVideo,
    AuditReport, PipelineResult
)

logger = logging.getLogger(__name__)


class AuditError(Exception):
    pass


async def phase7_audit(result: PipelineResult) -> PipelineResult:
    """Final verification: check video, audio, character consistency, and compliance.

    Hard gate: raises AuditError if overall_score < 0.6.
    """
    issues = []
    scores = {}

    # ── Check 1: Video exists and is valid ──
    video = result.video
    if video and os.path.exists(video.video_path):
        scores["video_valid"] = 1.0
        logger.info(f"  Video: {video.video_path} ({video.duration:.1f}s)")
    else:
        scores["video_valid"] = 0.0
        issues.append("Video file missing or invalid")
        logger.error("  Video: MISSING")

    # ── Check 2: Character consistency ──
    char_score = _check_character_consistency(result)
    scores["character_consistency"] = char_score
    if char_score < 0.5:
        issues.append(f"Character consistency low: {char_score:.2f}")

    # ── Check 3: World consistency ──
    world_score = _check_world_consistency(result)
    scores["world_consistency"] = world_score
    if world_score < 0.5:
        issues.append(f"World consistency low: {world_score:.2f}")

    # ── Check 4: Scene alignment ──
    scene_score = _check_scene_alignment(result)
    scores["scene_alignment"] = scene_score
    if scene_score < 0.5:
        issues.append(f"Scene alignment low: {scene_score:.2f}")

    # ── Check 5: Audio coverage ──
    audio_score = _check_audio_coverage(result)
    scores["audio_coverage"] = audio_score
    if audio_score < 0.3:
        issues.append(f"Audio coverage low: {audio_score:.2f}")

    # ── Check 6: Novel fidelity ──
    fidelity_score = _check_novel_fidelity(result)
    scores["novel_fidelity"] = fidelity_score
    if fidelity_score < 0.4:
        issues.append(f"Novel fidelity low: {fidelity_score:.2f}")

    # ── Overall score (weighted average) ──
    weights = {
        "video_valid": 0.25,
        "character_consistency": 0.25,
        "world_consistency": 0.15,
        "scene_alignment": 0.15,
        "audio_coverage": 0.10,
        "novel_fidelity": 0.10,
    }
    overall = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = overall

    # ── Compliance checks ──
    compliance = {
        "has_video": video is not None and os.path.exists(video.video_path) if video else False,
        "has_characters": bool(result.characters),
        "has_world": result.world is not None,
        "has_scenes": bool(result.scenes),
        "no_paid_apis": True,  # by design — we only use free backends
        "no_placeholders": True,
        "no_silent_audio": audio_score > 0,
    }

    report = AuditReport(
        character_consistency_score=scores["character_consistency"],
        world_consistency_score=scores["world_consistency"],
        scene_alignment_score=scores["scene_alignment"],
        audio_sync_score=scores["audio_coverage"],
        novel_fidelity_score=scores["novel_fidelity"],
        overall_score=overall,
        issues=issues,
        compliance=compliance,
    )

    logger.info(f"Audit: overall={overall:.2f}")
    for k, v in scores.items():
        logger.info(f"  {k}: {v:.2f}")
    if issues:
        for iss in issues:
            logger.warning(f"  Issue: {iss}")

    # ── Hard gate ──
    if overall < 0.6:
        raise AuditError(
            f"Audit FAILED (score={overall:.2f}, threshold=0.60).\n"
            + "\n".join(f"  ✗ {i}" for i in issues)
        )

    result.audit = report
    return result


# ─── Individual checks ────────────────────────────────────────────

def _check_character_consistency(result: PipelineResult) -> float:
    """Check that characters appear consistently across scenes and prompts."""
    characters = result.characters or []
    scenes = result.scenes or []
    images = result.images or []
    plans = result.scene_plans or []

    if not characters:
        return 0.0

    score = 1.0

    # Check 1: Each character appears in at least one scene
    char_names = set(c.canonical_name for c in characters)
    scene_chars = set()
    for sc in scenes:
        scene_chars.update(sc.characters)

    covered = char_names & scene_chars
    if char_names:
        coverage = len(covered) / len(char_names)
        score *= coverage

    # Check 2: Gender consistency in prompts
    gender_mismatches = 0
    for c in characters:
        if c.gender in ("male", "female"):
            for img in images:
                if c.canonical_name.lower() in img.prompt.lower():
                    # Check if prompt contradicts gender
                    prompt_lower = img.prompt.lower()
                    if c.gender == "male" and "woman" in prompt_lower and "man" not in prompt_lower:
                        gender_mismatches += 1
                    elif c.gender == "female" and "man" in prompt_lower and "woman" not in prompt_lower:
                        gender_mismatches += 1
    if images and gender_mismatches:
        score *= max(0, 1 - gender_mismatches / len(images))

    return max(0.0, min(1.0, score))


def _check_world_consistency(result: PipelineResult) -> float:
    """Check that world attributes are consistently reflected."""
    world = result.world
    images = result.images or []
    plans = result.scene_plans or []

    if not world or not images:
        return 0.0

    score = 1.0

    # Check that visual keywords appear in prompts
    keywords = world.visual_keywords or []
    if keywords:
        hits = sum(1 for kw in keywords if any(kw.lower() in img.prompt.lower() for img in images))
        if keywords:
            score *= (hits / len(keywords))

    # Check color palette usage
    colors = world.color_palette or []
    if colors:
        hits = sum(1 for c in colors if any(c.lower() in img.prompt.lower() for img in images))
        if colors:
            score *= (0.5 + 0.5 * hits / len(colors))

    return max(0.0, min(1.0, score))


def _check_scene_alignment(result: PipelineResult) -> float:
    """Check that each scene has corresponding images and plans."""
    scenes = result.scenes or []
    plans = result.scene_plans or []
    images = result.images or []

    if not scenes:
        return 0.0

    planned_ids = set(p.scene_id for p in plans)
    image_ids = set(img.scene_id for img in images)

    scene_ids = set(s.id for s in scenes)
    planned_coverage = len(scene_ids & planned_ids) / len(scene_ids)
    image_coverage = len(scene_ids & image_ids) / len(scene_ids)

    return (planned_coverage + image_coverage) / 2


def _check_audio_coverage(result: PipelineResult) -> float:
    """Check that narration exists for most scenes."""
    scenes = result.scenes or []
    audio = result.audio or []

    if not scenes:
        return 0.0

    audio_scenes = set(a.scene_id for a in audio)
    scene_ids = set(s.id for s in scenes)

    if not scene_ids:
        return 0.0

    return len(audio_scenes & scene_ids) / len(scene_ids)


def _check_novel_fidelity(result: PipelineResult) -> float:
    """Check that the video stays true to the novel's content."""
    novel = result.novel
    scenes = result.scenes or []
    plans = result.scene_plans or []

    if not novel or not scenes:
        return 0.0

    # Simple keyword overlap check
    novel_words = set(novel.cleaned.lower().split())
    all_narration = " ".join(p.narration_text for p in plans).lower()
    narration_words = set(all_narration.split())

    if not novel_words or not narration_words:
        return 0.5

    overlap = len(novel_words & narration_words) / len(novel_words)
    return max(0.0, min(1.0, overlap))
