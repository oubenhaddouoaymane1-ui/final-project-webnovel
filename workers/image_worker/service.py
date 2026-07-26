import os
import io
import uuid
import json
import hashlib
import asyncio
import logging
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.image_worker")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = ""
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg_scale: float = 7.0
    seed: Optional[int] = None
    model: Optional[str] = None
    style: Optional[str] = None


class UpscaleRequest(BaseModel):
    image_path: str
    scale: int = 2
    model: str = "ffmpeg"


class ImageWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            name="image-worker",
            worker_type="image_generation",
            job_types=["image_generation", "super_resolution"],
            capabilities=["text_to_image", "upscale"],
            port=8100,
        )
        self.pollinations_url: str = os.getenv(
            "POLLINATIONS_URL", "https://image.pollinations.ai/prompt"
        )
        self.images_dir: str = os.getenv("IMAGES_DIR", "/data/images")
        self.colab_esrgan_url: str = os.getenv("COLAB_ESRGAN_ENDPOINT", "")

        self._setup_image_routes()

    def _setup_image_routes(self):
        @self.app.post("/generate")
        async def generate_image(req: GenerateRequest):
            job_id = str(uuid.uuid4())
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'image_generation', 'pending', 10, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(req.dict()),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.post("/upscale")
        async def upscale_image(req: UpscaleRequest):
            job_id = str(uuid.uuid4())
            payload = req.dict()
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'super_resolution', 'pending', 5, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(payload),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.get("/images/{image_id}")
        async def get_image(image_id: str):
            image_path = Path(self.images_dir) / f"{image_id}.png"
            if not image_path.exists():
                raise HTTPException(status_code=404, detail="Image not found")
            return FileResponse(str(image_path), media_type="image/png")

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        job_type = job["type"]
        payload = job["payload"]

        if job_type == "image_generation":
            return await self._handle_generation(payload, job["id"])
        elif job_type == "super_resolution":
            return await self._handle_upscale(payload, job["id"])
        else:
            raise ValueError(f"Unknown job type: {job_type}")

    async def _handle_generation(
        self, payload: Dict[str, Any], job_id: str
    ) -> Dict[str, Any]:
        prompt = payload.get("prompt", "")
        width = payload.get("width", 1024)
        height = payload.get("height", 1024)
        seed = payload.get("seed")

        if seed is None:
            seed = int.from_bytes(os.urandom(4), "big")

        image_bytes = await self._generate_pollinations(
            prompt=prompt, width=width, height=height, seed=seed,
        )
        source = "pollinations"
        logger.info("Generated image via Pollinations for job %s", job_id)

        image_id = str(uuid.uuid4())
        image_path = Path(self.images_dir) / f"{image_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image_bytes)

        checksum = hashlib.sha256(image_bytes).hexdigest()

        await self._write_quality_check(
            job_id=job_id,
            asset_id=image_id,
            check_type="image_generation_complete",
            score=1.0,
            passed=True,
            details={
                "source": source,
                "width": width,
                "height": height,
                "seed": seed,
                "checksum": checksum,
                "file_size_bytes": len(image_bytes),
            },
        )

        return {
            "image_id": image_id,
            "image_path": str(image_path),
            "source": source,
            "width": width,
            "height": height,
            "seed": seed,
            "checksum": checksum,
            "file_size_bytes": len(image_bytes),
        }

    async def _handle_upscale(
        self, payload: Dict[str, Any], job_id: str
    ) -> Dict[str, Any]:
        image_path = payload.get("image_path", "")
        scale = payload.get("scale", 2)

        if not Path(image_path).exists():
            raise FileNotFoundError(f"Source image not found: {image_path}")

        output_id = str(uuid.uuid4())
        output_path = Path(self.images_dir) / f"{output_id}.png"

        try:
            await self._upscale_ffmpeg(image_path, str(output_path), scale)
        except Exception as exc:
            logger.error("FFmpeg upscale failed for job %s: %s", job_id, exc)
            raise

        output_size = output_path.stat().st_size
        checksum = hashlib.sha256(output_path.read_bytes()).hexdigest()

        await self._write_quality_check(
            job_id=job_id,
            asset_id=output_id,
            check_type="super_resolution_complete",
            score=1.0,
            passed=True,
            details={
                "source_path": image_path,
                "scale": scale,
                "model": "ffmpeg_lanczos",
                "checksum": checksum,
                "file_size_bytes": output_size,
            },
        )

        return {
            "image_id": output_id,
            "image_path": str(output_path),
            "scale": scale,
            "checksum": checksum,
            "file_size_bytes": output_size,
        }

    async def _generate_pollinations(
        self, prompt: str, width: int, height: int, seed: int = 0,
    ) -> bytes:
        """Generate image via Pollinations.ai — free, no API key, no GPU."""
        encoded_prompt = prompt.replace(" ", "%20").replace(",", "%2C")
        url = f"{self.pollinations_url}/{encoded_prompt}"
        params = {"width": width, "height": height, "nologo": "true", "seed": seed}

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise RuntimeError(
                    f"Pollinations returned non-image content: {content_type}"
                )
            return resp.content

    async def _upscale_ffmpeg(
        self, input_path: str, output_path: str, scale: int
    ):
        """Upscale image using FFmpeg Lanczos (local, CPU only, lightweight)."""
        w = scale * 1920
        h = scale * 1080
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", f"scale={w}:{h}:flags=lanczos",
            "-q:v", "2",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg upscale failed (rc={proc.returncode}): {stderr.decode()}"
            )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = ImageWorker()
    worker.run()


if __name__ == "__main__":
    main()
