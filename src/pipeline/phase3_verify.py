"""Phase 3 — Verification: hard gate on analysis results before rendering."""
from __future__ import annotations
import logging
from typing import List

from .contracts import NovelText, Scene, CharacterDNA, WorldBible, PipelineResult

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    pass


async def phase3_verify(
    novel: NovelText,
    scenes: List[Scene],
    characters: List[CharacterDNA],
    world: WorldBible,
) -> PipelineResult:
    """Verify analysis output. Halt on any critical failure.

    Checks:
    1. Scenes have valid character names (not None/empty)
    2. Characters have canonical names
    3. World has at least one non-empty attribute
    4. Scene-to-character linkage is consistent
    5. No orphaned characters (appearing nowhere)
    """
    issues = []
    warnings = []
    critical = False

    # ── Check 1: Scene integrity ──
    for sc in scenes:
        if not sc.text or len(sc.text.strip()) < 30:
            issues.append(f"Scene {sc.id}: text too short ({len(sc.text)} chars)")
            critical = True
        if not sc.summary:
            warnings.append(f"Scene {sc.id}: missing summary")
        for cname in sc.characters:
            if not cname or cname.strip() == "":
                issues.append(f"Scene {sc.id}: empty character name in character list")
                critical = True

    # ── Check 2: Character integrity ──
    for char in characters:
        if not char.canonical_name or char.canonical_name.strip() == "":
            issues.append(f"Character {char.id}: missing canonical_name")
            critical = True
        if char.gender not in ("male", "female", "unknown"):
            warnings.append(f"Character {char.canonical_name}: unusual gender '{char.gender}'")

    # ── Check 3: World integrity ──
    non_empty = sum(1 for v in [
        world.technology_level, world.architecture, world.geography,
        world.climate, world.visual_atmosphere, world.magic_system, world.culture,
    ] if v and v != "unknown")
    if non_empty < 2:
        issues.append(f"World: only {non_empty} attributes filled — world bible too sparse")
        critical = True

    # ── Check 4: Scene↔Character linkage ──
    scene_char_names = set()
    for sc in scenes:
        for cname in sc.characters:
            scene_char_names.add(cname)

    known_names = set(c.canonical_name for c in characters)
    known_bases = {c.canonical_name.lower().strip() for c in characters}

    orphaned = set()
    for sc_name in scene_char_names:
        if sc_name.lower().strip() not in known_bases:
            orphaned.add(sc_name)
    if orphaned:
        warnings.append(f"Characters in scenes but not in character list: {orphaned}")

    # ── Check 5: Minimum content (scaled by word count) ──
    min_scenes = max(1, min(3, novel.word_count // 500))
    if len(scenes) < min_scenes:
        issues.append(f"Too few scenes: {len(scenes)} (minimum {min_scenes} for {novel.word_count} words)")
        critical = True

    if len(characters) < 1:
        issues.append("No characters found")
        critical = True

    # ── Decision ──
    if critical:
        raise VerificationError(
            "Verification FAILED. Issues:\n" + "\n".join(f"  ✗ {i}" for i in issues)
            + ("\n  Warnings:\n" + "\n".join(f"  ⚠ {w}" for w in warnings) if warnings else "")
        )

    logger.info(f"Verification PASSED: {len(scenes)} scenes, {len(characters)} characters, {non_empty}/7 world attrs")
    if warnings:
        logger.info(f"  Warnings: {warnings}")

    return PipelineResult(
        success=True,
        novel=novel,
        scenes=scenes,
        characters=characters,
        world=world,
    )
