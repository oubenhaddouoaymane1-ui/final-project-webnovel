"""Cloudflare Workers AI backend — FLUX for images, MeloTTS for speech."""
from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
from typing import Optional

import httpx

from .base import ImageBackend, TTSBackend, BackendResult

logger = logging.getLogger(__name__)


class CloudflareImageBackend(ImageBackend):
    """Generate images via Cloudflare Workers AI (FLUX.1-schnell)."""

    name = "cloudflare"

    def __init__(self, account_id: str = "", api_token: str = ""):
        self.account_id = account_id or os.getenv("CF_ACCOUNT_ID", "")
        self.api_token = api_token or os.getenv("CF_API_TOKEN", "")
        self.model = "@cf/black-forest-labs/flux-1-schnell"

    @property
    def _url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
        )

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        if not self.account_id or not self.api_token:
            return BackendResult(
                success=False,
                error="Cloudflare credentials not configured. "
                "Set CF_ACCOUNT_ID and CF_API_TOKEN.",
                backend_name=self.name,
            )

        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
        }
        if seed is not None:
            payload["seed"] = seed

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if not data.get("success"):
                errors = data.get("errors", [])
                return BackendResult(
                    success=False,
                    error=f"Cloudflare error: {errors}",
                    backend_name=self.name,
                )

            result = data.get("result", {})
            image_b64 = result.get("image") or result.get("b64_json")
            if not image_b64:
                return BackendResult(
                    success=False,
                    error="No image in Cloudflare response",
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
                metadata={"model": self.model},
            )

        except httpx.HTTPStatusError as e:
            return BackendResult(
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                backend_name=self.name,
            )
        except Exception as e:
            return BackendResult(
                success=False,
                error=str(e),
                backend_name=self.name,
            )

    async def health_check(self) -> bool:
        if not self.account_id or not self.api_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}",
                    headers={"Authorization": f"Bearer {self.api_token}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


class CloudflareTTSBackend(TTSBackend):
    """Generate speech via Cloudflare Workers AI (MeloTTS)."""

    name = "cloudflare"

    def __init__(self, account_id: str = "", api_token: str = ""):
        self.account_id = account_id or os.getenv("CF_ACCOUNT_ID", "")
        self.api_token = api_token or os.getenv("CF_API_TOKEN", "")
        self.model = "@cf/myshell-ai/melo-tts"

    @property
    def _url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
        )

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        if not self.account_id or not self.api_token:
            return BackendResult(
                success=False,
                error="Cloudflare credentials not configured.",
                backend_name=self.name,
            )

        payload = {"text": text}
        if voice:
            payload["voice"] = voice

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    self._url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "audio" in content_type:
                audio_bytes = resp.content
            else:
                data = resp.json()
                audio_b64 = data.get("result", {}).get("audio")
                if not audio_b64:
                    return BackendResult(
                        success=False,
                        error="No audio in Cloudflare response",
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
        if not self.account_id or not self.api_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}",
                    headers={"Authorization": f"Bearer {self.api_token}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
