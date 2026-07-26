"""Pollinations.ai backend — free FLUX image generation, no signup."""
from __future__ import annotations
import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from .base import ImageBackend, BackendResult

logger = logging.getLogger(__name__)

# Rate limit: minimum seconds between requests
MIN_REQUEST_INTERVAL = 2.0
_last_request_time = 0.0


class PollinationsImageBackend(ImageBackend):
    """Generate images via Pollinations.ai (FLUX.1-schnell, free, no signup)."""

    name = "pollinations"
    priority = 10

    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt"

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        global _last_request_time
        import time as _time
        t0 = _time.time()

        # Rate limiting: wait if needed
        elapsed = _time.time() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)

        if seed is None:
            seed = random.randint(0, 2**31)

        encoded_prompt = quote(prompt)
        url = (
            f"{self.base_url}/{encoded_prompt}"
            f"?width={width}&height={height}&seed={seed}&nologo=true"
        )

        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                _last_request_time = time.time()
                resp = await client.get(url)
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and len(resp.content) < 1000:
                return BackendResult(
                    success=False,
                    error=f"Unexpected response type: {content_type}",
                    backend_name=self.name,
                )

            image_bytes = resp.content

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(image_bytes)

            return BackendResult(
                success=True,
                data=image_bytes,
                output_path=output_path,
                backend_name=self.name,
                metadata={"seed": seed},
                duration=_time.time() - t0,
            )

        except httpx.HTTPStatusError as e:
            return BackendResult(
                success=False,
                error=f"HTTP {e.response.status_code}",
                backend_name=self.name,
                duration=_time.time() - t0,
            )
        except Exception as e:
            return BackendResult(
                success=False,
                error=str(e),
                backend_name=self.name,
                duration=_time.time() - t0,
            )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://image.pollinations.ai/prompt/test?width=64&height=64&nologo=true")
                return resp.status_code == 200 and len(resp.content) > 1000
        except Exception:
            return False
