"""espeak-ng TTS backend — system fallback, always available on Linux."""
from __future__ import annotations
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import TTSBackend, BackendResult

logger = logging.getLogger(__name__)


class EspeakTTSBackend(TTSBackend):
    """Generate speech via espeak-ng (system TTS, always available).

    Low quality but guaranteed to work on any Linux system.
    Used as last-resort fallback when no other TTS is available.
    Supports 80+ languages.
    """

    name = "espeak_tts"
    priority = 99
    requires_internet = False
    requires_api_key = False

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        t0 = time.time()

        espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        if not espeak_bin:
            return BackendResult(
                success=False,
                error="Neither espeak-ng nor espeak found on system",
                backend_name=self.name,
                duration=0,
            )

        voice_name = voice or "en"
        speed_wpm = int(175 * speed)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Generate WAV first, then convert if needed
        wav_path = tempfile.mktemp(suffix=".wav")

        try:
            cmd = [
                espeak_bin,
                "-v", voice_name,
                "-s", str(speed_wpm),
                "-w", wav_path,
                text,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return BackendResult(
                    success=False,
                    error=f"espeak-ng failed: {stderr.decode()[:200]}",
                    backend_name=self.name,
                    duration=time.time() - t0,
                )

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                return BackendResult(
                    success=False,
                    error="espeak-ng produced empty output",
                    backend_name=self.name,
                    duration=time.time() - t0,
                )

            # Move WAV to output path
            shutil.move(wav_path, output_path)

            return BackendResult(
                success=True,
                output_path=output_path,
                backend_name=self.name,
                metadata={"voice": voice_name, "speed_wpm": speed_wpm},
                duration=time.time() - t0,
            )

        except Exception as e:
            if os.path.exists(wav_path):
                os.remove(wav_path)
            return BackendResult(
                success=False,
                error=f"espeak error: {e}",
                backend_name=self.name,
                duration=time.time() - t0,
            )

    async def health_check(self) -> bool:
        return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None
