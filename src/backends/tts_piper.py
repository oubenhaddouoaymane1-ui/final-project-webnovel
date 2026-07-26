"""Piper TTS backend — fast local neural TTS, no internet needed after model download."""
from __future__ import annotations
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .base import TTSBackend, BackendResult

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.expanduser("~/.local/share/piper/models")
DEFAULT_MODEL = "en_US-lessac-medium"


class PiperTTSBackend(TTSBackend):
    """Generate speech locally via Piper TTS (ONNX-based, fast).

    Piper uses ONNX neural voices — no GPU required, runs on CPU.
    Models auto-download on first use from HuggingFace.

    Default voice: en_US-lessac-medium (English, high quality).
    """

    name = "piper_tts"
    priority = 2
    requires_internet = False  # after first run
    requires_api_key = False

    def __init__(self, model: str = ""):
        self.model = model or DEFAULT_MODEL

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        t0 = time.time()

        try:
            from piper import PiperVoice

            model_name = voice or self.model
            wav_path = output_path if output_path.endswith(".wav") else output_path + ".wav"

            def _generate():
                piper_voice = PiperVoice.load(model_name)
                Path(wav_path).parent.mkdir(parents=True, exist_ok=True)
                import wave
                with wave.open(wav_path, "wb") as wav_file:
                    piper_voice.synthesize(text, wav_file)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _generate)

            if not output_path.endswith(".wav") and os.path.exists(wav_path):
                if output_path != wav_path:
                    os.rename(wav_path, output_path)
                    wav_path = output_path

            elapsed = time.time() - t0
            return BackendResult(
                success=True,
                output_path=wav_path,
                backend_name=self.name,
                metadata={"model": model_name},
                duration=elapsed,
            )

        except ImportError:
            return BackendResult(
                success=False,
                error="piper-tts not installed. Run: pip install piper-tts",
                backend_name=self.name,
                duration=time.time() - t0,
            )
        except Exception as e:
            return BackendResult(
                success=False,
                error=f"Piper TTS error: {e}",
                backend_name=self.name,
                duration=time.time() - t0,
            )

    async def health_check(self) -> bool:
        try:
            from piper import PiperVoice
            # Check if we can at least import piper
            # Model may need download on first use, but piper is installed
            return True
        except ImportError:
            return False
