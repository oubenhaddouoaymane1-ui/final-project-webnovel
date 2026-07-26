"""Backend manager — auto-detect available free backends, priority fallback, retry+backoff."""
from __future__ import annotations
import asyncio
import logging
import time
from typing import List, Optional, Dict, Any

from .base import ImageBackend, TTSBackend, BackendResult

logger = logging.getLogger(__name__)


class BackendManager:
    """Manage multiple backends with automatic detection and fallback.

    Features:
    - Auto-detect available backends on startup
    - Priority-based fallback (lower priority = preferred)
    - Retry with exponential backoff on transient failures
    - Rate-limit awareness (auto-cooldown on 429s)
    - Auto-disable backends that exhaust quotas
    """

    def __init__(self):
        self._image_backends: List[ImageBackend] = []
        self._tts_backends: List[TTSBackend] = []
        self._healthy_images: List[ImageBackend] = []
        self._healthy_tts: List[TTSBackend] = []
        self._disabled_images: set = set()
        self._disabled_tts: set = set()
        self._cooldown_until: Dict[str, float] = {}

    def register_image_backend(self, backend: ImageBackend):
        self._image_backends.append(backend)

    def register_tts_backend(self, backend: TTSBackend):
        self._tts_backends.append(backend)

    def add_image_backends(self, backends: List[ImageBackend]):
        self._image_backends.extend(backends)

    def add_tts_backends(self, backends: List[TTSBackend]):
        self._tts_backends.extend(backends)

    async def detect_and_verify(self) -> Dict[str, Any]:
        """Run health checks on all backends. Returns status report."""
        report: Dict[str, Any] = {"image_backends": [], "tts_backends": []}

        for backend in sorted(self._image_backends, key=lambda b: b.priority):
            status = {"name": backend.name, "priority": backend.priority, "healthy": False, "error": None}
            try:
                healthy = await backend.health_check()
                status["healthy"] = healthy
                if healthy:
                    self._healthy_images.append(backend)
                    logger.info(f"  Image backend '{backend.name}' (priority={backend.priority}) — READY")
                else:
                    logger.info(f"  Image backend '{backend.name}' (priority={backend.priority}) — unavailable")
            except Exception as e:
                status["error"] = str(e)
                logger.info(f"  Image backend '{backend.name}' — error: {e}")
            report["image_backends"].append(status)

        for backend in sorted(self._tts_backends, key=lambda b: b.priority):
            status = {"name": backend.name, "priority": backend.priority, "healthy": False, "error": None}
            try:
                healthy = await backend.health_check()
                status["healthy"] = healthy
                if healthy:
                    self._healthy_tts.append(backend)
                    logger.info(f"  TTS backend '{backend.name}' (priority={backend.priority}) — READY")
                else:
                    logger.info(f"  TTS backend '{backend.name}' (priority={backend.priority}) — unavailable")
            except Exception as e:
                status["error"] = str(e)
                logger.info(f"  TTS backend '{backend.name}' — error: {e}")
            report["tts_backends"].append(status)

        report["image_ready"] = len(self._healthy_images)
        report["tts_ready"] = len(self._healthy_tts)
        report["primary_image"] = self._healthy_images[0].name if self._healthy_images else None
        report["primary_tts"] = self._healthy_tts[0].name if self._healthy_tts else None

        logger.info(
            f"Backend detection: {report['image_ready']} image, {report['tts_ready']} TTS ready"
        )
        if self._healthy_images:
            logger.info(f"  Primary image: {report['primary_image']}")
        if self._healthy_tts:
            logger.info(f"  Primary TTS: {report['primary_tts']}")

        return report

    def _is_cooled_down(self, name: str) -> bool:
        """Check if a backend is in cooldown (rate-limited)."""
        until = self._cooldown_until.get(name, 0)
        if time.time() < until:
            return True
        return False

    def _set_cooldown(self, name: str, seconds: float):
        """Set cooldown for a rate-limited backend."""
        self._cooldown_until[name] = time.time() + seconds
        logger.info(f"  Backend '{name}' cooling down for {seconds:.0f}s")

    def _get_active_image_backends(self) -> List[ImageBackend]:
        """Get healthy image backends that are not disabled or cooling down."""
        return [
            b for b in self._healthy_images
            if b.name not in self._disabled_images and not self._is_cooled_down(b.name)
        ]

    def _get_active_tts_backends(self) -> List[TTSBackend]:
        """Get healthy TTS backends that are not disabled or cooling down."""
        return [
            b for b in self._healthy_tts
            if b.name not in self._disabled_tts and not self._is_cooled_down(b.name)
        ]

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
        max_retries: int = 2,
    ) -> BackendResult:
        """Try each healthy image backend with retry + backoff."""
        errors = []
        active = self._get_active_image_backends()
        if not active:
            active = self._get_active_image_backends()
            if not active:
                return BackendResult(
                    success=False,
                    error="No healthy image backends available",
                )

        for backend in active:
            for attempt in range(max_retries + 1):
                logger.info(f"  Image: {backend.name}" + (f" (attempt {attempt+1})" if attempt > 0 else ""))
                try:
                    result = await backend.generate(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        width=width,
                        height=height,
                        seed=seed,
                        output_path=output_path,
                    )
                    result.backend_name = backend.name

                    if result.success:
                        return result

                    error_msg = result.error or ""

                    # Detect quota exhaustion → disable backend
                    if "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                        self._disabled_images.add(backend.name)
                        logger.warning(f"  Backend '{backend.name}' disabled (quota exhausted)")
                        break

                    # Detect rate limiting → cooldown
                    if "429" in error_msg or "rate" in error_msg.lower() or "too many" in error_msg.lower():
                        self._set_cooldown(backend.name, 10.0 * (attempt + 1))
                        errors.append(f"{backend.name}: rate limited")
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue

                    errors.append(f"{backend.name}: {error_msg}")
                    break

                except Exception as e:
                    errors.append(f"{backend.name}: {e}")
                    break

        return BackendResult(
            success=False,
            error=f"All image backends failed:\n" + "\n".join(f"  - {e}" for e in errors),
        )

    async def generate_tts(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        max_retries: int = 2,
    ) -> BackendResult:
        """Try each healthy TTS backend with retry + backoff."""
        errors = []
        active = self._get_active_tts_backends()
        if not active:
            active = self._get_active_tts_backends()
            if not active:
                return BackendResult(
                    success=False,
                    error="No healthy TTS backends available",
                )

        for backend in active:
            for attempt in range(max_retries + 1):
                logger.info(f"  TTS: {backend.name}" + (f" (attempt {attempt+1})" if attempt > 0 else ""))
                try:
                    result = await backend.generate(
                        text=text,
                        output_path=output_path,
                        voice=voice,
                        speed=speed,
                    )
                    result.backend_name = backend.name

                    if result.success:
                        return result

                    error_msg = result.error or ""

                    if "429" in error_msg or "rate" in error_msg.lower():
                        self._set_cooldown(backend.name, 10.0 * (attempt + 1))
                        errors.append(f"{backend.name}: rate limited")
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue

                    errors.append(f"{backend.name}: {error_msg}")
                    break

                except Exception as e:
                    errors.append(f"{backend.name}: {e}")
                    break

        return BackendResult(
            success=False,
            error=f"All TTS backends failed:\n" + "\n".join(f"  - {e}" for e in errors),
        )

    def get_report(self) -> str:
        """Human-readable status report."""
        lines = ["=== Backend Status ==="]
        lines.append(f"\nImage backends ({len(self._healthy_images)}/{len(self._image_backends)} healthy):")
        for b in self._image_backends:
            status = "READY" if b in self._healthy_images else "DOWN"
            if b.name in self._disabled_images:
                status = "DISABLED"
            lines.append(f"  [{status}] {b.name} (priority={b.priority})")

        lines.append(f"\nTTS backends ({len(self._healthy_tts)}/{len(self._tts_backends)} healthy):")
        for b in self._tts_backends:
            status = "READY" if b in self._healthy_tts else "DOWN"
            if b.name in self._disabled_tts:
                status = "DISABLED"
            lines.append(f"  [{status}] {b.name} (priority={b.priority})")

        return "\n".join(lines)


def build_default_manager() -> BackendManager:
    """Build a BackendManager with all free cloud backends in priority order.

    NO local GPU workloads. Heavy AI runs on:
      - Pollinations.ai (free image generation)
      - HuggingFace Inference API (free tier)
      - Google Colab (ComfyUI + FLUX, RealESRGAN, LivePortrait)
      - OpenRouter (LLM reasoning + vision QA)
      - Microsoft Edge TTS (free narration)
    """
    from .pollinations import PollinationsImageBackend
    from .tts_edge import EdgeTTSBackend

    manager = BackendManager()

    manager.add_image_backends([
        PollinationsImageBackend(),  # 1 — free, no API key, no GPU
    ])

    manager.add_tts_backends([
        EdgeTTSBackend(),           # 1 — free Microsoft TTS
    ])

    return manager
