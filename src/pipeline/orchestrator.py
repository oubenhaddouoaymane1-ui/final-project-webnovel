"""Pipeline orchestrator — mandatory stage-gating, hard stops on failure."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .contracts import PipelineResult
from .phase1_intake import phase1_intake, IntakeError
from .phase2_analysis import phase2_analysis, AnalysisError
from .phase3_verify import phase3_verify, VerificationError
from .phase4_prompt_plan import phase4_prompt_plan, PromptPlanError
from .phase5_render import phase5_render, RenderError
from .phase6_assembly import phase6_assembly, AssemblyError
from .phase7_audit import phase7_audit, AuditError

from src.backends.manager import BackendManager, build_default_manager

logger = logging.getLogger(__name__)


class PipelineHalted(Exception):
    """Raised when pipeline halts at a hard gate."""
    pass


class PipelineOrchestrator:
    """Orchestrate the full novel-to-video pipeline with mandatory gating.

    Architecture:
        Input -> Intake -> Analysis -> Verify -> PromptPlan -> Render -> Assemble -> Audit -> Output

    Each phase must succeed before the next begins.
    If any phase fails, the pipeline HALTS immediately.
    No silent failures. No placeholders. No paid APIs.
    """

    STAGES = [
        "intake",
        "analysis",
        "verification",
        "prompt_plan",
        "render",
        "assembly",
        "audit",
    ]

    def __init__(
        self,
        config: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        checkpoint_dir: str = "checkpoints",
        output_dir: str = "output",
    ):
        self.config = config
        self.progress_callback = progress_callback
        self.checkpoint_dir = checkpoint_dir
        self.output_dir = output_dir
        self.backend_manager: Optional[BackendManager] = None
        os.makedirs(checkpoint_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

    # ── Public entry point ────────────────────────────────────────

    async def run(self, file_path: str) -> PipelineResult:
        """Run full pipeline. Halts on first critical failure."""
        start = time.time()
        result = PipelineResult(success=False)
        completed_stages = []

        try:
            # ═══ Stage 1: Intake ═══
            await self._report("intake", "Validating and loading novel...")
            result.novel = await phase1_intake(file_path)
            await self._save_checkpoint("intake", result)
            completed_stages.append("intake")
            await self._report("intake", f"OK — {result.novel.word_count} words, lang={result.novel.language}")

            # ═══ Stage 2: Analysis ═══
            await self._report("analysis", "Analyzing novel (chapters, scenes, characters, world)...")
            chapters, scenes, characters, world = await phase2_analysis(result.novel, self.config)
            result.chapters = chapters
            result.scenes = scenes
            result.characters = characters
            result.world = world
            await self._save_checkpoint("analysis", result)
            completed_stages.append("analysis")
            await self._report(
                "analysis",
                f"OK — {len(chapters)} chapters, {len(scenes)} scenes, "
                f"{len(characters)} chars, world={world.technology_level}"
            )

            # ═══ Stage 3: Verification ═══
            await self._report("verification", "Verifying analysis quality...")
            verified = await phase3_verify(result.novel, scenes, characters, world)
            result.scenes = verified.scenes
            result.characters = verified.characters
            result.world = verified.world
            completed_stages.append("verification")
            await self._report("verification", "OK — all quality gates passed")

            # ═══ Stage 4: Prompt Plan ═══
            await self._report("prompt_plan", "Generating cinematic shot plans...")
            result = await phase4_prompt_plan(result, self.config)
            await self._save_checkpoint("prompt_plan", result)
            completed_stages.append("prompt_plan")
            total_shots = sum(len(sp.shots) for sp in result.scene_plans)
            await self._report(
                "prompt_plan",
                f"OK — {total_shots} shots across {len(result.scene_plans)} scenes"
            )

            # ═══ Stage 5: Render ═══
            await self._report("render", "Detecting available backends...")
            self.backend_manager = build_default_manager()
            backend_report = await self.backend_manager.detect_and_verify()
            await self._report(
                "render",
                f"Backends: {backend_report['image_ready']} image, "
                f"{backend_report['tts_ready']} TTS ready "
                f"(primary: {backend_report['primary_image'] or 'none'}, "
                f"{backend_report['primary_tts'] or 'none'})"
            )

            await self._report("render", "Generating images and audio...")
            result = await phase5_render(result, self.backend_manager, self.output_dir)
            await self._save_checkpoint("render", result)
            completed_stages.append("render")
            await self._report(
                "render",
                f"OK — {len(result.images)} images, {len(result.audio)} audio tracks"
            )

            # ═══ Stage 6: Assembly ═══
            await self._report("assembly", "Assembling video with FFmpeg...")
            result = await phase6_assembly(result, self.output_dir)
            completed_stages.append("assembly")
            await self._report(
                "assembly",
                f"OK — {result.video.duration:.1f}s video at {result.video.video_path}"
            )

            # ═══ Stage 7: Audit ═══
            await self._report("audit", "Running final quality audit...")
            result = await phase7_audit(result)
            completed_stages.append("audit")
            await self._report(
                "audit",
                f"OK — overall score: {result.audit.overall_score:.2f}"
            )

            # ═══ Done ═══
            elapsed = time.time() - start
            result.success = True
            await self._report(
                "complete",
                f"Pipeline complete in {elapsed:.0f}s. Video: {result.video.video_path}"
            )

        except (IntakeError, AnalysisError, VerificationError,
                PromptPlanError, RenderError, AssemblyError, AuditError) as e:
            elapsed = time.time() - start
            failed_stage = completed_stages[-1] if completed_stages else "unknown"
            result.error = str(e)
            result.failed_stage = failed_stage
            logger.error(f"Pipeline HALTED at {failed_stage} after {elapsed:.0f}s: {e}")
            await self._report("halted", f"HALTED at {failed_stage}: {e}")
            raise PipelineHalted(f"Pipeline halted at stage '{failed_stage}': {e}") from e

        except Exception as e:
            elapsed = time.time() - start
            failed_stage = completed_stages[-1] if completed_stages else "unknown"
            result.error = str(e)
            result.failed_stage = failed_stage
            logger.error(f"Unexpected error at {failed_stage} after {elapsed:.0f}s: {e}")
            await self._report("error", f"Unexpected error at {failed_stage}: {e}")
            raise

        return result

    # ── Progress reporting ────────────────────────────────────────

    async def _report(self, stage: str, message: str):
        logger.info(f"[{stage}] {message}")
        if self.progress_callback:
            try:
                await self.progress_callback(stage, message)
            except Exception:
                pass

    # ── Checkpointing ─────────────────────────────────────────────

    async def _save_checkpoint(self, stage: str, result: PipelineResult):
        """Save minimal state for resume after crash."""
        try:
            cp = {
                "stage": stage,
                "novel_title": result.novel.title if result.novel else None,
                "scene_count": len(result.scenes) if result.scenes else 0,
                "character_count": len(result.characters) if result.characters else 0,
                "has_world": result.world is not None,
                "plan_count": len(result.scene_plans) if result.scene_plans else 0,
                "image_count": len(result.images) if result.images else 0,
                "audio_count": len(result.audio) if result.audio else 0,
                "has_video": result.video is not None,
            }
            path = os.path.join(self.checkpoint_dir, f"{stage}.json")
            with open(path, "w") as f:
                json.dump(cp, f, indent=2)
        except Exception as e:
            logger.warning(f"Checkpoint save failed: {e}")
