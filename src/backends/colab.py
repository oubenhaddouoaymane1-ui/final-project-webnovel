"""Google Colab Free backend — connects to a user-deployed Gradio Space on Colab."""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from .base import ImageBackend, BackendResult

logger = logging.getLogger(__name__)


class ColabFreeBackend(ImageBackend):
    """Generate images via a Gradio Space running on Google Colab Free.

    How it works:
    1. User deploys a Gradio app on Colab that runs SDXL/FLUX
    2. Colab exposes a Gradio URL (via gradio.live or ngrok/cloudflare tunnel)
    3. This backend connects to that URL and calls the predict endpoint

    Setup instructions (in docs):
    - Run colab_app.py on Colab Free
    - It creates a Gradio interface and tunnels it
    - Set COLAB_GRADIO_URL env var to the tunnel URL

    If no URL is configured, this backend is skipped silently.
    """

    name = "colab_free"
    priority = 4
    requires_gpu = False
    requires_internet = True
    requires_api_key = False

    def __init__(self, gradio_url: str = ""):
        self.gradio_url = gradio_url or os.getenv("COLAB_GRADIO_URL", "")
        self._client = None

    async def health_check(self) -> bool:
        if not self.gradio_url:
            return False

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.gradio_url}/info")
                if resp.status_code == 200:
                    logger.info(f"Colab: Gradio Space reachable at {self.gradio_url}")
                    return True
            return False
        except Exception:
            return False

    async def _get_client(self):
        if self._client:
            return self._client

        from gradio_client import Client
        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(
            None,
            lambda: Client(self.gradio_url, verbose=False),
        )
        return self._client

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        import time
        t0 = time.time()

        if not self.gradio_url:
            return BackendResult(
                success=False,
                error="No Colab Gradio URL configured. Set COLAB_GRADIO_URL.",
                backend_name=self.name,
                duration=0,
            )

        try:
            client = await self._get_client()
            loop = asyncio.get_event_loop()

            def _predict():
                return client.predict(
                    prompt,
                    negative_prompt or "blurry, low quality",
                    width,
                    height,
                    seed if seed is not None else -1,
                    api_name="/generate",
                )

            result = await loop.run_in_executor(None, _predict)

            if isinstance(result, (list, tuple)):
                image_path = result[0] if result else None
            elif isinstance(result, str):
                image_path = result
            else:
                image_path = str(result)

            if not image_path or not os.path.exists(str(image_path)):
                return BackendResult(
                    success=False,
                    error=f"Colab returned invalid result: {result}",
                    backend_name=self.name,
                    duration=time.time() - t0,
                )

            image_bytes = Path(image_path).read_bytes()

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(image_bytes)

            return BackendResult(
                success=True,
                data=image_bytes,
                output_path=output_path,
                backend_name=self.name,
                metadata={"source": "colab", "url": self.gradio_url},
                duration=time.time() - t0,
            )

        except Exception as e:
            return BackendResult(
                success=False,
                error=f"Colab error: {e}",
                backend_name=self.name,
                duration=time.time() - t0,
            )
