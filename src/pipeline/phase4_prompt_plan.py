"""Phase 4 — Prompt Plan: convert scene analysis into cinematic shot plans."""
from __future__ import annotations
import json
import logging
import uuid
from typing import List, Dict, Any

from .contracts import (
    Scene, CharacterDNA, WorldBible, ShotPlan, ScenePlan, PipelineResult
)
from src.llm import OllamaClient

logger = logging.getLogger(__name__)


class PromptPlanError(Exception):
    pass


# ── Shot type budgets (seconds) ──────────────────────────────────

SHOT_DURATIONS = {
    "establishing": 4.0,
    "wide": 3.0,
    "medium": 3.0,
    "close_up": 3.0,
    "extreme_close_up": 2.5,
    "action": 2.0,
}


async def phase4_prompt_plan(
    result: PipelineResult,
    config: Dict[str, Any],
) -> PipelineResult:
    """Generate cinematic shot plans for each scene.

    For each scene, produces 1-3 shots depending on importance.
    Each shot gets a detailed prompt, negative prompt, and duration.
    """
    llm = OllamaClient(config)
    scenes = result.scenes or []
    characters = result.characters or []
    world = result.world
    if not scenes or not world:
        raise PromptPlanError("No scenes or world bible in pipeline result.")

    scene_plans: List[ScenePlan] = []

    for scene in scenes:
        plan = await _plan_scene(scene, characters, world, llm)
        scene_plans.append(plan)
        logger.info(f"  {scene.id}: {len(plan.shots)} shots, {plan.total_duration:.1f}s, narration={len(plan.narration_text)} chars")

    total_video_dur = sum(p.total_duration for p in scene_plans)
    logger.info(f"Total planned video: {total_video_dur:.1f}s ({total_video_dur/60:.1f} min)")

    result.scene_plans = scene_plans
    return result


# ─── Per-scene planning ───────────────────────────────────────────

async def _plan_scene(
    scene: Scene,
    characters: List[CharacterDNA],
    world: WorldBible,
    llm: OllamaClient,
) -> ScenePlan:
    n_shots = _shot_count(scene.importance, scene.action_present, scene.dialogue_present)

    # Gather character refs for this scene
    scene_chars = [
        c for c in characters
        if c.canonical_name in scene.characters
    ]

    char_descriptions = []
    for c in scene_chars:
        parts = [c.canonical_name]
        if c.gender and c.gender != "unknown":
            parts.append(c.gender)
        if c.physical_description:
            parts.append(c.physical_description)
        if c.hair_color:
            parts.append(f"{c.hair_color} hair")
        if c.eye_color:
            parts.append(f"{c.eye_color} eyes")
        if c.clothing:
            parts.append(f"wearing {c.clothing}")
        if c.weapons:
            parts.append(f"with {', '.join(c.weapons)}")
        char_descriptions.append(" — ".join(parts))

    char_block = "\n".join(f"  {d}" for d in char_descriptions) if char_descriptions else "  (no named characters in this scene)"

    prompt = f"""You are a cinematic director planning shots for an anime/manhwa style video.

Scene: {scene.summary}
Location: {scene.location}
Time of day: {scene.time_of_day}
Atmosphere: {scene.emotion}
World: {world.technology_level} tech, {world.visual_atmosphere} atmosphere, colors: {', '.join(world.color_palette[:5])}
Dialogue present: {scene.dialogue_present}
Action present: {scene.action_present}

Characters in scene:
{char_block}

Plan {n_shots} shots. Return ONLY a JSON object:
{{
  "shots": [
    {{
      "shot_type": "establishing|wide|medium|close_up|extreme_close_up|action",
      "prompt": "detailed Stable Diffusion prompt describing the visual composition, art style, lighting, colors, mood. Include 'cinematic anime style, professional illustration, dramatic lighting, 4k, detailed' at the end",
      "negative_prompt": "text, watermark, signature, blurry, low quality, deformed, ugly, bad anatomy",
      "transition": "fade|cut|dissolve"
    }}
  ],
  "narration_text": "the narration voiceover text for this scene (1-3 sentences, present tense, cinematic tone)"
}}

Rules:
- Prompts MUST include specific character descriptions (hair, eyes, clothing) — never generic
- Establishing shot: wide view of location, atmosphere, no characters
- Close-ups focus on character emotion, facial expression
- Action shots show movement, dynamic angles
- Narration text should be dramatic, third-person present tense
- Keep prompts under 150 words each"""

    response = await llm._generate(prompt, max_tokens=1500)
    raw = llm._parse_json(response)

    if not isinstance(raw, dict) or "shots" not in raw:
        # Fallback: single medium shot
        fallback_prompt = _build_fallback_prompt(scene, world, scene_chars)
        raw = {
            "shots": [{
                "shot_type": "medium",
                "prompt": fallback_prompt,
                "negative_prompt": "text, watermark, blurry, low quality",
                "transition": "fade",
            }],
            "narration_text": scene.summary,
        }

    shots = []
    for s in raw["shots"]:
        shot_type = s.get("shot_type", "medium")
        shots.append(ShotPlan(
            shot_type=shot_type,
            duration_seconds=SHOT_DURATIONS.get(shot_type, 3.0),
            prompt=s.get("prompt", ""),
            negative_prompt=s.get("negative_prompt", "text, watermark, blurry"),
            transition=s.get("transition", "fade"),
        ))

    narration = raw.get("narration_text", scene.summary)
    if not narration or not narration.strip():
        narration = scene.summary

    total = sum(s.duration_seconds for s in shots)

    return ScenePlan(
        scene_id=scene.id,
        shots=shots,
        narration_text=narration,
        total_duration=total,
    )


def _shot_count(importance: str, has_action: bool, has_dialogue: bool) -> int:
    base = {"minor": 1, "normal": 2, "important": 2, "critical": 3}.get(importance, 2)
    if has_action:
        base = min(base + 1, 3)
    return base


def _build_fallback_prompt(scene: Scene, world: WorldBible, chars: list) -> str:
    parts = ["cinematic anime style, professional illustration,"]
    parts.append(f"{scene.emotion} atmosphere, {scene.time_of_day} lighting,")
    parts.append(f"{world.visual_atmosphere} mood,")
    if world.color_palette:
        parts.append(f"colors: {', '.join(world.color_palette[:3])},")
    if chars:
        c = chars[0]
        if c.physical_description:
            parts.append(f"{c.physical_description},")
        if c.hair_color:
            parts.append(f"{c.hair_color} hair,")
    parts.append("dramatic lighting, 4k, detailed, no text, no watermark")
    return " ".join(parts)
