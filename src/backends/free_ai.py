"""free.ai backend — FLUX images + Kokoro/Piper TTS, 30K tokens/day free."""
from __future__ import annotations
import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

from .base import ImageBackend, TTSBackend, BackendResult

logger = logging.getLogger(__name__)


class FreeAIImageBackend(ImageBackend):
    """Generate images via free.ai (FLUX.1-schnell)."""

    name = "free_ai"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("FREE_AI_API_KEY", "")
        self.base_url = "https://api.free.ai/v1/image"

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        if not self.api_key:
            return BackendResult(
                success=False,
                error="free.ai API key not configured. Set FREE_AI_API_KEY.",
                backend_name=self.name,
            )

        payload = {
            "model": "flux-schnell",
            "prompt": prompt,
            "width": width,
            "height": height,
        }
        if seed is not None:
            payload["seed"] = seed

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.base_url}/generate",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            image_b64 = data.get("image") or data.get("b64_json")
            if not image_b64:
                return BackendResult(
                    success=False,
                    error="No image in free.ai response",
                    backend_name=self.name,
                )

            image_bytes = base64.b64decode(image_b64)
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(image_bytes)

            return BackendResult(
                success=True,
                data=image_bytes,
                output_path=output_path,
                backend_name=self.name,
            )

        except Exception as e:
            return BackendResult(
                success=False,
                error=str(e),
                backend_name=self.name,
            )

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


class FreeAITTSBackend(TTSBackend):
    """Generate speech via free.ai (Kokoro/Piper)."""

    name = "free_ai"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("FREE_AI_API_KEY", "")
        self.base_url = "https://api.free.ai/v1/tts"

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        if not self.api_key:
            return BackendResult(
                success=False,
                error="free.ai API key not configured.",
                backend_name=self.name,
            )

        payload = {"text": text, "model": "kokoro"}
        if voice:
            payload["voice"] = voice

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self.base_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            audio_b64 = data.get("audio") or data.get("b64_audio")
            if not audio_b64:
                return BackendResult(
                    success=False,
                    error="No audio in free.ai response",
                    backend_name=self.name,
                )

            audio_bytes = base64.b64decode(audio_b64)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(audio_bytes)

            return BackendResult(
                success=True,
                data=audio_bytes,
                output_path=output_path,
                backend_name=self.name,
            )

        except Exception as e:
            return BackendResult(
                success=False,
                error=str(e),
                backend_name=self.name,
            )

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
