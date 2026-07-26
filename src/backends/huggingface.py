"""HuggingFace backend — free Inference API + ZeroGPU Spaces for images and TTS."""
from __future__ import annotations
import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from .base import ImageBackend, TTSBackend, BackendResult

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  IMAGE — HuggingFace Inference API (free, no key for public models)
# ════════════════════════════════════════════════════════════════════

class HFInferenceImageBackend(ImageBackend):
    """Generate images via HuggingFace free Inference API.

    Uses black-forest-labs/FLUX.1-schnell (fastest free model).
    Falls back to stabilityai/stable-diffusion-xl-base-1.0.
    No API key required for public models (rate-limited).
    """

    name = "hf_inference"
    priority = 2
    requires_gpu = False
    requires_internet = True
    requires_api_key = False

    MODEL_CANDIDATES = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
    ]

    def __init__(self):
        self._working_model = None

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        t0 = time.time()

        models = [self._working_model] if self._working_model else self.MODEL_CANDIDATES

        for model in models:
            if not model:
                continue

            try:
                payload = {"inputs": prompt}
                if seed is not None:
                    payload["parameters"] = {"seed": seed}

                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"https://api-inference.huggingface.co/models/{model}",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    if resp.status_code == 503:
                        # Model is loading — wait and retry once
                        try:
                            info = resp.json()
                            wait_time = info.get("estimated_time", 30)
                            if wait_time < 120:
                                logger.info(f"HF Inference: model loading, waiting {wait_time:.0f}s...")
                                await asyncio.sleep(min(wait_time, 60))
                                resp = await client.post(
                                    f"https://api-inference.huggingface.co/models/{model}",
                                    json=payload,
                                    headers={"Content-Type": "application/json"},
                                )
                        except Exception:
                            continue

                    if resp.status_code == 429:
                        logger.warning(f"HF Inference: rate limited on {model}")
                        continue

                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")

                    if "image" in content_type:
                        image_bytes = resp.content
                    else:
                        data = resp.json()
                        img_b64 = data.get("image") or data.get("images", [None])[0] if isinstance(data.get("images"), list) else None
                        if not img_b64:
                            continue
                        image_bytes = base64.b64decode(img_b64)

                    if len(image_bytes) < 500:
                        continue

                    if output_path:
                        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                        Path(output_path).write_bytes(image_bytes)

                    self._working_model = model
                    elapsed = time.time() - t0
                    return BackendResult(
                        success=True,
                        data=image_bytes,
                        output_path=output_path,
                        backend_name=self.name,
                        metadata={"model": model, "seed": seed},
                        duration=elapsed,
                    )

            except httpx.HTTPStatusError as e:
                logger.warning(f"HF Inference: {model} returned HTTP {e.response.status_code}")
                continue
            except Exception as e:
                logger.warning(f"HF Inference: {model} failed: {e}")
                continue

        return BackendResult(
            success=False,
            error="All HF Inference models failed or rate-limited",
            backend_name=self.name,
            duration=time.time() - t0,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
                )
                # 200=ready, 503=loading (still valid), 429=rate limited (still works)
                return resp.status_code in (200, 503, 429)
        except Exception:
            return False


# ════════════════════════════════════════════════════════════════════
#  IMAGE — HuggingFace ZeroGPU Spaces (via Gradio client)
# ════════════════════════════════════════════════════════════════════

class HFZeroGPUSpaceBackend(ImageBackend):
    """Generate images via a HuggingFace Gradio Space with ZeroGPU.

    Connects to a public Gradio Space that exposes an image generation endpoint.
    The Space must accept (prompt, negative_prompt, width, height, seed) and
    return an image.

    Well-known free Spaces:
    - black-forest-labs/FLUX.1-schnell (official)
    - stabilityai/stable-diffusion-xl-base-1.0

    If space_url is not provided, tries the official FLUX Space.
    """

    name = "hf_space"
    priority = 3
    requires_gpu = False
    requires_internet = True
    requires_api_key = False

    DEFAULT_SPACES = [
        "black-forest-labs/FLUX.1-schnell",
    ]

    def __init__(self, space_id: str = ""):
        self.space_id = space_id or ""
        self._client = None
        self._connected_space = None

    async def _connect(self) -> bool:
        if self._client and self._connected_space:
            return True

        spaces = [self.space_id] if self.space_id else self.DEFAULT_SPACES

        for sid in spaces:
            try:
                from gradio_client import Client
                loop = asyncio.get_event_loop()
                client = await loop.run_in_executor(
                    None,
                    lambda: Client(sid, verbose=False),
                )
                self._client = client
                self._connected_space = sid
                logger.info(f"HF Space: connected to {sid}")
                return True
            except Exception as e:
                logger.warning(f"HF Space: failed to connect to {sid}: {e}")
                continue

        return False

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        t0 = time.time()

        if not await self._connect():
            return BackendResult(
                success=False,
                error="Could not connect to any HF Space",
                backend_name=self.name,
                duration=time.time() - t0,
            )

        try:
            loop = asyncio.get_event_loop()

            actual_seed = seed if seed is not None else 0
            randomize = seed is None

            def _predict():
                return self._client.predict(
                    prompt,
                    actual_seed,
                    randomize,
                    width,
                    height,
                    4,
                    api_name="/infer",
                )

            result = await loop.run_in_executor(None, _predict)

            # Result is (image_dict, seed) tuple
            if isinstance(result, (list, tuple)):
                image_data = result[0] if result else None
            else:
                image_data = result

            # image_data is a dict with 'path' or 'url' key
            if isinstance(image_data, dict):
                image_path = image_data.get("path") or image_data.get("url")
            elif isinstance(image_data, str):
                image_path = image_data
            else:
                image_path = str(image_data)

            if not image_path:
                return BackendResult(
                    success=False,
                    error=f"HF Space returned no image",
                    backend_name=self.name,
                    duration=time.time() - t0,
                )

            # Download if it's a URL, or read if it's a local path
            if image_path.startswith("http"):
                async with httpx.AsyncClient(timeout=30) as dl_client:
                    resp = await dl_client.get(image_path)
                    image_bytes = resp.content
            elif os.path.exists(str(image_path)):
                image_bytes = Path(str(image_path)).read_bytes()
            else:
                return BackendResult(
                    success=False,
                    error=f"HF Space returned invalid path: {image_path}",
                    backend_name=self.name,
                    duration=time.time() - t0,
                )

            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(image_bytes)

            return BackendResult(
                success=True,
                data=image_bytes,
                output_path=output_path,
                backend_name=self.name,
                metadata={"space": self._connected_space, "seed": seed},
                duration=time.time() - t0,
            )

        except Exception as e:
            return BackendResult(
                success=False,
                error=f"HF Space error: {e}",
                backend_name=self.name,
                duration=time.time() - t0,
            )

    async def health_check(self) -> bool:
        return await self._connect()


# ════════════════════════════════════════════════════════════════════
#  TTS — HuggingFace Inference API (free, Kokoro)
# ════════════════════════════════════════════════════════════════════

class HFInferenceTTSBackend(TTSBackend):
    """Generate speech via HuggingFace free Inference API (Kokoro TTS)."""

    name = "hf_tts"
    priority = 2
    requires_internet = True
    requires_api_key = False

    MODEL = "hexgrad/Kokoro-82M"

    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        t0 = time.time()

        try:
            # Kokoro TTS via HF Inference — try the pipeline endpoint
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"https://api-inference.huggingface.co/models/{self.MODEL}",
                    json={"inputs": text},
                    headers={"Content-Type": "application/json"},
                )

                if resp.status_code == 503:
                    try:
                        info = resp.json()
                        wait = min(info.get("estimated_time", 30), 60)
                        await asyncio.sleep(wait)
                        resp = await client.post(
                            f"https://api-inference.huggingface.co/models/{self.MODEL}",
                            json={"inputs": text},
                        )
                    except Exception:
                        pass

                if resp.status_code != 200:
                    return BackendResult(
                        success=False,
                        error=f"HF TTS HTTP {resp.status_code}",
                        backend_name=self.name,
                        duration=time.time() - t0,
                    )

                content_type = resp.headers.get("content-type", "")
                if "audio" in content_type:
                    audio_bytes = resp.content
                else:
                    data = resp.json()
                    audio_b64 = data.get("audio") or data.get("waveform")
                    if audio_b64:
                        import base64
                        audio_bytes = base64.b64decode(audio_b64)
                    else:
                        return BackendResult(
                            success=False,
                            error="No audio in HF TTS response",
                            backend_name=self.name,
                            duration=time.time() - t0,
                        )

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(audio_bytes)

            return BackendResult(
                success=True,
                data=audio_bytes,
                output_path=output_path,
                backend_name=self.name,
                duration=time.time() - t0,
            )

        except Exception as e:
            return BackendResult(
                success=False,
                error=str(e),
                backend_name=self.name,
                duration=time.time() - t0,
            )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api-inference.huggingface.co/models/{self.MODEL}"
                )
                return resp.status_code in (200, 503, 429)
        except Exception:
            return False
