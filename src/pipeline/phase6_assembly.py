"""Phase 6 — Assembly: merge images + audio into video via FFmpeg."""
from __future__ import annotations
import asyncio
import logging
import os
import subprocess
import json
from typing import List, Dict, Any, Optional

from .contracts import (
    ScenePlan, GeneratedImage, GeneratedAudio, AssembledVideo, PipelineResult
)

logger = logging.getLogger(__name__)


class AssemblyError(Exception):
    pass


async def phase6_assembly(
    result: PipelineResult,
    output_dir: str = "output",
    resolution: str = "1024x1024",
) -> PipelineResult:
    """Assemble rendered assets into a final video using FFmpeg.

    Steps:
    1. Verify FFmpeg is available
    2. Create per-scene video clips (image + duration + optional Ken Burns effect)
    3. Create per-scene audio clips (narration)
    4. Merge all clips in scene order with crossfades
    5. Output final MP4
    """
    # ── Gate: FFmpeg available ──
    ffmpeg_path = _find_ffmpeg()
    if not ffmpeg_path:
        raise AssemblyError("FFmpeg not found. Install: sudo apt install ffmpeg")

    images = result.images or []
    audio = result.audio or []
    scene_plans = result.scene_plans or []

    if not images:
        raise AssemblyError("No images to assemble.")

    video_dir = os.path.join(output_dir, "video")
    clips_dir = os.path.join(video_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    # ── Step 1: Create per-scene clips ──
    clip_paths = []
    for sp in scene_plans:
        clip_path = os.path.join(clips_dir, f"{sp.scene_id}.mp4")

        scene_images = [img for img in images if img.scene_id == sp.scene_id]
        scene_audio = next((a for a in audio if a.scene_id == sp.scene_id), None)

        if not scene_images:
            logger.warning(f"  {sp.scene_id}: no images, skipping clip")
            continue

        total_duration = sp.total_duration

        # Determine duration per image
        n_images = len(scene_images)
        dur_per_image = total_duration / n_images

        await _create_scene_clip(
            ffmpeg_path=ffmpeg_path,
            images=[img.image_path for img in scene_images],
            audio_path=scene_audio.audio_path if scene_audio else None,
            audio_duration=scene_audio.duration if scene_audio else total_duration,
            output_path=clip_path,
            duration_per_image=dur_per_image,
            resolution=resolution,
        )
        clip_paths.append(clip_path)
        logger.info(f"  Created clip: {sp.scene_id} ({total_duration:.1f}s)")

    if not clip_paths:
        raise AssemblyError("No clips created from rendered assets.")

    # ── Step 2: Concatenate all clips ──
    final_path = os.path.join(video_dir, "final.mp4")
    await _concatenate_clips(ffmpeg_path, clip_paths, final_path)

    # ── Gate: output file exists ──
    if not os.path.exists(final_path):
        raise AssemblyError(f"Final video not created: {final_path}")

    # Get duration
    duration = await _get_duration(ffmpeg_path, final_path)

    result.video = AssembledVideo(
        video_path=final_path,
        duration=duration,
        scene_count=len(clip_paths),
        resolution=resolution,
    )

    logger.info(f"Assembly OK: {final_path} ({duration:.1f}s, {len(clip_paths)} scenes)")
    return result


# ─── FFmpeg operations ────────────────────────────────────────────

def _find_ffmpeg() -> Optional[str]:
    try:
        result = subprocess.run(
            ["which", "ffmpeg"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    # Try common paths
    for path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]:
        if os.path.exists(path):
            return path
    return None


async def _create_scene_clip(
    ffmpeg_path: str,
    images: List[str],
    audio_path: Optional[str],
    audio_duration: float,
    output_path: str,
    duration_per_image: float,
    resolution: str,
):
    """Create a video clip from images + audio using FFmpeg.

    Uses zoompan filter for Ken Burns effect (slow zoom in/out).
    """
    w, h = resolution.split("x")

    # Build input args
    input_args = []
    for img in images:
        input_args.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])

    # Audio input
    has_audio = audio_path and os.path.exists(audio_path)
    if has_audio:
        input_args.extend(["-i", audio_path])

    # Build filter for Ken Burns (slow zoom)
    filter_parts = []
    n = len(images)
    for i in range(n):
        zoom_speed = 0.002 if i % 2 == 0 else -0.002  # alternate zoom in/out
        filter_parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"zoompan=z='min(zoom+{zoom_speed},1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration_per_image*25)}:s={w}x{h}:fps=25[v{i}]"
        )

    # Concat video
    concat_input = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_input}concat=n={n}:v=1:a=0[outv]")

    filter_complex = ";\n".join(filter_parts)

    cmd = [
        ffmpeg_path, "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
    ]

    if has_audio:
        cmd.extend(["-map", f"{n}:a", "-shortest"])

    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ])

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"FFmpeg clip error: {stderr.decode()[:500]}")
        raise AssemblyError(f"FFmpeg failed for clip: {stderr.decode()[:200]}")


async def _concatenate_clips(
    ffmpeg_path: str,
    clip_paths: List[str],
    output_path: str,
):
    """Concatenate clips using FFmpeg concat demuxer."""
    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise AssemblyError(f"FFmpeg concat failed: {stderr.decode()[:300]}")

    # Cleanup list file
    os.remove(list_file)


async def _get_duration(ffmpeg_path: str, video_path: str) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    try:
        info = json.loads(stdout.decode())
        return float(info["format"]["duration"])
    except Exception:
        return 0.0
