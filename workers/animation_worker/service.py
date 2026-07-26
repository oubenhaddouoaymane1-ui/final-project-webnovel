import os
import uuid
import json
import asyncio
import logging
import math
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.animation_worker")

KENBURNS_EFFECTS = {
    "zoom_in": {"direction": "in", "scale_start": 1.0, "scale_end": 1.3},
    "zoom_out": {"direction": "out", "scale_start": 1.3, "scale_end": 1.0},
    "pan_left": {"direction": "left", "x_start": 0, "x_end": -0.15},
    "pan_right": {"direction": "right", "x_start": 0, "x_end": 0.15},
    "pan_up": {"direction": "up", "y_start": 0, "y_end": -0.1},
    "pan_down": {"direction": "down", "y_start": 0, "y_end": 0.1},
    "zoom_in_left": {"direction": "in_left", "scale_start": 1.0, "scale_end": 1.2, "x_end": -0.08},
    "zoom_in_right": {"direction": "in_right", "scale_start": 1.0, "scale_end": 1.2, "x_end": 0.08},
    "zoom_out_left": {"direction": "out_left", "scale_start": 1.2, "scale_end": 1.0, "x_start": -0.08},
    "zoom_out_right": {"direction": "out_right", "scale_start": 1.2, "scale_end": 1.0, "x_start": 0.08},
}


class AnimateRequest(BaseModel):
    image_path: str
    duration: float = 5.0
    fps: int = 24
    effect: str = "zoom_in"
    resolution: str = "1920x1080"
    output_format: str = "mp4"
    output_name: Optional[str] = None
    use_live_portrait: bool = False
    live_portrait_params: Optional[Dict[str, Any]] = None


class AnimationWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            name="animation-worker",
            worker_type="image_animation",
            job_types=["image_animation"],
            capabilities=["ken_burns", "live_portrait", "image_to_video"],
            port=8500,
        )
        self.animation_dir: str = os.getenv("ANIMATION_DIR", "/data/animations")
        self.temp_dir: str = os.getenv("TEMP_DIR", "/tmp/cineos_animation")
        self.live_portrait_url: str = os.getenv("LIVE_PORTRAIT_URL", "http://liveportrait:8080")
        self.ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")

        self._setup_animation_routes()

    def _setup_animation_routes(self):
        @self.app.post("/animate")
        async def animate_image(req: AnimateRequest):
            job_id = str(uuid.uuid4())
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'image_animation', 'pending', 6, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(req.dict()),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.get("/effects")
        async def list_effects():
            return {"effects": list(KENBURNS_EFFECTS.keys())}

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job["payload"]
        image_path = payload.get("image_path", "")
        duration = payload.get("duration", 5.0)
        fps = payload.get("fps", 24)
        effect = payload.get("effect", "zoom_in")
        resolution = payload.get("resolution", "1920x1080")
        output_format = payload.get("output_format", "mp4")
        output_name = payload.get("output_name")
        use_live_portrait = payload.get("use_live_portrait", False)
        live_portrait_params = payload.get("live_portrait_params") or {}

        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        width, height = resolution.split("x")
        width, height = int(width), int(height)

        if use_live_portrait:
            try:
                result = await self._animate_live_portrait(
                    image_path=image_path,
                    duration=duration,
                    fps=fps,
                    width=width,
                    height=height,
                    params=live_portrait_params,
                    output_format=output_format,
                    output_name=output_name,
                    job_id=job["id"],
                )
                return result
            except Exception as exc:
                logger.warning(
                    "LivePortrait failed, falling back to Ken Burns: %s", exc
                )

        result = await self._animate_ken_burns(
            image_path=image_path,
            duration=duration,
            fps=fps,
            effect=effect,
            width=width,
            height=height,
            output_format=output_format,
            output_name=output_name,
            job_id=job["id"],
        )
        return result

    async def _animate_ken_burns(
        self,
        image_path: str,
        duration: float,
        fps: int,
        effect: str,
        width: int,
        height: int,
        output_format: str,
        output_name: Optional[str],
        job_id: str,
    ) -> Dict[str, Any]:
        effect_params = KENBURNS_EFFECTS.get(effect)
        if not effect_params:
            raise ValueError(
                f"Unknown effect '{effect}'. Available: {list(KENBURNS_EFFECTS.keys())}"
            )

        total_frames = int(duration * fps)

        if not output_name:
            output_name = f"anim_{job_id[:8]}"

        temp_dir = Path(self.temp_dir) / job_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        vf_parts: List[str] = []

        scale_start = effect_params.get("scale_start", 1.0)
        scale_end = effect_params.get("scale_end", 1.0)
        x_start = effect_params.get("x_start", 0)
        x_end = effect_params.get("x_end", 0)
        y_start = effect_params.get("y_start", 0)
        y_end = effect_params.get("y_end", 0)

        zoom_expr = f"if(eq(on,0),{scale_start},{scale_start}+({scale_end}-{scale_start})*on/{total_frames})"
        x_expr = f"if(eq(on,0),{x_start},{x_start}+({x_end}-{x_start})*on/{total_frames})"
        y_expr = f"if(eq(on,0),{y_start},{y_start}+({y_end}-{y_start})*on/{total_frames})"

        zoompan_filter = (
            f"zoompan=z='{zoom_expr}'"
            f":x='iw*({x_expr})'"
            f":y='ih*({y_expr})'"
            f":d={total_frames}"
            f":s={width}x{height}"
            f":fps={fps}"
        )

        vf_parts.append(zoompan_filter)
        vf_parts.append(f"format=yuv420p")

        vf = ",".join(vf_parts)

        output_path = Path(self.animation_dir) / f"{output_name}.{output_format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Ken Burns animation failed: {stderr.decode()}")

        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        file_size = output_path.stat().st_size
        actual_duration = await self._get_duration(str(output_path))
        checksum = hashlib.sha256(output_path.read_bytes()).hexdigest()

        return {
            "output_path": str(output_path),
            "output_name": output_name,
            "effect": effect,
            "duration_seconds": actual_duration,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "file_size_bytes": file_size,
            "checksum": checksum,
            "engine": "ken_burns",
        }

    async def _animate_live_portrait(
        self,
        image_path: str,
        duration: float,
        fps: int,
        width: int,
        height: int,
        params: Dict[str, Any],
        output_format: str,
        output_name: Optional[str],
        job_id: str,
    ) -> Dict[str, Any]:
        import base64

        image_bytes = Path(image_path).read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        request_payload = {
            "image": image_b64,
            "duration": duration,
            "fps": fps,
            "width": width,
            "height": height,
            "driving_video_path": params.get("driving_video_path"),
            "flag_relative": params.get("flag_relative", True),
            "flag_stitching": params.get("flag_stitching", True),
            "flag_pasteback": params.get("flag_pasteback", True),
            "expression_scale": params.get("expression_scale", 1.0),
        }

        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{self.live_portrait_url}/animate",
                json=request_payload,
            )
            resp.raise_for_status()
            result_data = resp.json()

        video_b64 = result_data.get("video")
        if not video_b64:
            raise RuntimeError("LivePortrait returned no video data")

        video_bytes = base64.b64decode(video_b64)

        if not output_name:
            output_name = f"lp_{job_id[:8]}"

        output_path = Path(self.animation_dir) / f"{output_name}.{output_format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_bytes)

        file_size = output_path.stat().st_size
        actual_duration = await self._get_duration(str(output_path))

        return {
            "output_path": str(output_path),
            "output_name": output_name,
            "effect": "live_portrait",
            "duration_seconds": actual_duration,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "file_size_bytes": file_size,
            "engine": "live_portrait",
        }

    async def _get_duration(self, video_path: str) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            return 0.0
        try:
            return float(stdout.decode().strip())
        except ValueError:
            return 0.0


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = AnimationWorker()
    worker.run()


if __name__ == "__main__":
    main()
