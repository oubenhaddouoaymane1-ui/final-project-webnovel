"""Edge TTS backend — Microsoft Edge TTS, free, no API key, high quality."""
from __future__ import annotations
import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import TTSBackend, BackendResult

logger = logging.getLogger(__name__)

# Best free Edge TTS voices by language
VOICE_MAP = {
    "en": "en-US-AriaNeural",
    "ar": "ar-SA-ZariyahNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}


class EdgeTTSBackend(TTSBackend):
    """Generate speech via Microsoft Edge TTS (free, high quality).

    Uses the same API as Microsoft Edge browser's Read Aloud feature.
    No API key, no signup, no rate limit (practical).
    Supports 75+ languages with neural voices.
    """

    name = "edge_tts"
    priority = 1
    requires_internet = True
    requires_api_key = False

    def __init__(self, default_voice: str = ""):
        self.default_voice = default_voice

    def _pick_voice(self, voice: Optional[str] = None, text: str = "") -> str:
        if voice:
            return voice
        if self.default_voice:
            return self.default_voice
        # Auto-detect language from text (simple heuristic)
        import re
        arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
        if arabic_chars > len(text) * 0.1:
            return VOICE_MAP["ar"]
        return VOICE_MAP["en"]

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        t0 = time.time()

        try:
            import edge_tts

            chosen_voice = self._pick_voice(voice, text)

            # Edge TTS uses rate strings like "+0%", "-10%", "+20%"
            rate_pct = int((speed - 1.0) * 100)
            rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

            communicate = edge_tts.Communicate(
                text=text,
                voice=chosen_voice,
                rate=rate_str,
            )

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            await communicate.save(output_path)

            elapsed = time.time() - t0
            return BackendResult(
                success=True,
                output_path=output_path,
                backend_name=self.name,
                metadata={"voice": chosen_voice, "rate": rate_str},
                duration=elapsed,
            )

        except ImportError:
            return BackendResult(
                success=False,
                error="edge-tts not installed. Run: pip install edge-tts",
                backend_name=self.name,
                duration=time.time() - t0,
            )
        except Exception as e:
            return BackendResult(
                success=False,
                error=f"Edge TTS error: {e}",
                backend_name=self.name,
                duration=time.time() - t0,
            )

    async def health_check(self) -> bool:
        try:
            import edge_tts
            # Quick test: generate a tiny audio
            tmp = tempfile.mktemp(suffix=".mp3")
            try:
                communicate = edge_tts.Communicate("test", voice="en-US-AriaNeural")
                await communicate.save(tmp)
                ok = os.path.exists(tmp) and os.path.getsize(tmp) > 100
                if os.path.exists(tmp):
                    os.remove(tmp)
                return ok
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return False
        except ImportError:
            return False
