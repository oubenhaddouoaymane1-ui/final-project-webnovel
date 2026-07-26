"""Phase 5 — Render: generate images and TTS via BackendManager."""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from .contracts import (
    Scene, CharacterDNA, WorldBible, ShotPlan, ScenePlan,
    GeneratedImage, GeneratedAudio, PipelineResult
)
from src.backends.manager import BackendManager
from src.backends.base import BackendResult

logger = logging.getLogger(__name__)


class RenderError(Exception):
    pass


async def phase5_render(
    result: PipelineResult,
    backend_manager: BackendManager,
    output_dir: str = "output",
) -> PipelineResult:
    """Render images and TTS audio for all planned scenes.

    Runs image generation and TTS generation concurrently per scene,
    with a concurrency limit of 3 to avoid rate-limiting.
    """
    if not result.scene_plans:
        raise RenderError("No scene plans to render.")

    scenes = result.scenes or []
    characters = result.characters or []
    world = result.world

    # Ensure output directories
    img_dir = os.path.join(output_dir, "images")
    aud_dir = os.path.join(output_dir, "audio")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(aud_dir, exist_ok=True)

    # Build character lookup for prompt enrichment
    char_lookup = {c.canonical_name: c for c in characters}

    generated_images: List[GeneratedImage] = []
    generated_audio: List[GeneratedAudio] = []
    render_errors: List[str] = []

    # Process scenes with concurrency limit (1 for images to avoid rate limits)
    img_semaphore = asyncio.Semaphore(1)
    tts_semaphore = asyncio.Semaphore(2)

    async def render_scene(scene_plan: ScenePlan, idx: int):
        scene = _find_scene(scenes, scene_plan.scene_id)
        if not scene:
            render_errors.append(f"Scene {scene_plan.scene_id}: not found")
            return

        # ── Render each shot (serialized to avoid rate limits) ──
        for shot_idx, shot in enumerate(scene_plan.shots):
            async with img_semaphore:
                img_path = os.path.join(img_dir, f"{scene_plan.scene_id}_shot{shot_idx+1}.png")

                enriched_prompt = _enrich_prompt(
                    shot.prompt, scene, world, char_lookup
                )

                logger.info(f"  Generating image {scene_plan.scene_id}_shot{shot_idx+1}...")
                img_result = await backend_manager.generate_image(
                    prompt=enriched_prompt,
                    negative_prompt=shot.negative_prompt,
                    output_path=img_path,
                )

                if img_result.success:
                    generated_images.append(GeneratedImage(
                        scene_id=scene_plan.scene_id,
                        shot_index=shot_idx,
                        image_path=img_result.output_path or img_path,
                        prompt=enriched_prompt,
                        backend_used=img_result.backend_name or "unknown",
                        seed=img_result.metadata.get("seed") if img_result.metadata else None,
                    ))
                else:
                    render_errors.append(
                        f"{scene_plan.scene_id}_shot{shot_idx+1}: {img_result.error}"
                    )

            # ── Render TTS narration ──
            if scene_plan.narration_text.strip():
                async with tts_semaphore:
                    aud_path = os.path.join(aud_dir, f"{scene_plan.scene_id}.wav")

                    logger.info(f"  Generating TTS {scene_plan.scene_id}...")
                    aud_result = await backend_manager.generate_tts(
                        text=scene_plan.narration_text,
                        output_path=aud_path,
                    )

                if aud_result.success:
                    generated_audio.append(GeneratedAudio(
                        scene_id=scene_plan.scene_id,
                        audio_path=aud_result.output_path or aud_path,
                        text=scene_plan.narration_text,
                        duration=aud_result.duration or 3.0,
                        backend_used=aud_result.backend_name or "unknown",
                    ))
                else:
                    render_errors.append(
                        f"{scene_plan.scene_id}_tts: {aud_result.error}"
                    )

    # Run all scene renders
    tasks = [render_scene(sp, i) for i, sp in enumerate(result.scene_plans)]
    await asyncio.gather(*tasks)

    # ── Gate: at least 50% images succeeded ──
    total_shots = sum(len(sp.shots) for sp in result.scene_plans)
    if total_shots > 0 and len(generated_images) < total_shots * 0.5:
        raise RenderError(
            f"Too many image failures: {len(generated_images)}/{total_shots} succeeded. "
            f"Errors: {'; '.join(render_errors[:5])}"
        )

    if generated_images:
        logger.info(f"Render OK: {len(generated_images)} images, {len(generated_audio)} audio tracks")
    else:
        raise RenderError("No images generated.")

    result.images = generated_images
    result.audio = generated_audio
    return result


# ─── Helpers ──────────────────────────────────────────────────────

def _find_scene(scenes: List[Scene], scene_id: str) -> Optional[Scene]:
    for s in scenes:
        if s.id == scene_id:
            return s
    return None


def _enrich_prompt(
    base_prompt: str,
    scene: Scene,
    world: Optional[WorldBible],
    char_lookup: dict,
) -> str:
    """Enrich a shot prompt with world/character context to prevent drift."""
    parts = [base_prompt]

    # Ensure world style consistency
    if world:
        if world.visual_atmosphere and world.visual_atmosphere not in base_prompt.lower():
            parts.append(f"{world.visual_atmosphere} atmosphere")
        if world.color_palette:
            palette_str = ", ".join(world.color_palette[:3])
            if palette_str.lower() not in base_prompt.lower():
                parts.append(f"color palette: {palette_str}")

    # Append character-specific descriptors if scene mentions characters
    for cname in scene.characters:
        c = char_lookup.get(cname)
        if c:
            # Only append if not already in prompt
            if cname.lower() not in base_prompt.lower():
                desc_parts = [cname]
                if c.hair_color:
                    desc_parts.append(f"{c.hair_color} hair")
                if c.eye_color:
                    desc_parts.append(f"{c.eye_color} eyes")
                if c.clothing:
                    desc_parts.append(c.clothing)
                parts.append(", ".join(desc_parts))

    # Style consistency tag
    if "cinematic anime style" not in base_prompt.lower():
        parts.append("cinematic anime style, professional illustration, dramatic lighting, 4k, detailed")

    return ", ".join(parts)
