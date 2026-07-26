import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="CineOS Render Worker", version="1.0.0")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
RENDER_DIR = os.environ.get("RENDER_DIR", "/render/output")
TEMP_DIR = os.environ.get("TEMP_DIR", "/render/tmp")
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
VIDEO_CODEC = os.environ.get("VIDEO_CODEC", "libx264")
AUDIO_CODEC = os.environ.get("AUDIO_CODEC", "aac")
DEFAULT_CRF = int(os.environ.get("DEFAULT_CRF", "23"))
DEFAULT_PRESET = os.environ.get("DEFAULT_PRESET", "medium")

redis_pool: Optional[aioredis.Redis] = None
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

Path(RENDER_DIR).mkdir(parents=True, exist_ok=True)
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


class RenderRequest(BaseModel):
    input_url: Optional[str] = None
    input_path: Optional[str] = None
    output_filename: str = Field(default_factory=lambda: f"render_{uuid.uuid4().hex[:8]}.mp4")
    video_codec: str = VIDEO_CODEC
    audio_codec: str = AUDIO_CODEC
    crf: int = DEFAULT_CRF
    preset: str = DEFAULT_PRESET
    resolution: Optional[str] = None
    fps: Optional[int] = None
    extra_flags: list[str] = Field(default_factory=list)
    callback_url: Optional[str] = None


class RenderResponse(BaseModel):
    job_id: str
    status: str
    output_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    active_jobs: int
    max_jobs: int
    uptime_seconds: float


_start_time = time.time()


def build_ffmpeg_command(req: RenderRequest, input_file: str, output_file: str) -> list[str]:
    cmd = ["ffmpeg", "-y", "-i", input_file]

    if req.resolution:
        w, h = req.resolution.split("x")
        cmd.extend(["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"])

    if req.fps:
        cmd.extend(["-r", str(req.fps)])

    cmd.extend(["-c:v", req.video_codec])
    cmd.extend(["-crf", str(req.crf)])
    cmd.extend(["-preset", req.preset])
    cmd.extend(["-c:a", req.audio_codec])
    cmd.extend(["-movflags", "+faststart"])
    cmd.extend(req.extra_flags)
    cmd.append(output_file)

    return cmd


async def download_file(url: str, dest: str) -> None:
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        active_jobs=MAX_CONCURRENT_JOBS - semaphore._value,
        max_jobs=MAX_CONCURRENT_JOBS,
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@app.post("/render", response_model=RenderResponse)
async def render_video(req: RenderRequest):
    if not req.input_url and not req.input_path:
        raise HTTPException(status_code=400, detail="input_url or input_path is required")

    job_id = uuid.uuid4().hex
    async with semaphore:
        tmp_dir = tempfile.mkdtemp(dir=TEMP_DIR, prefix=f"job_{job_id}_")
        try:
            if req.input_url:
                input_file = os.path.join(tmp_dir, "input")
                await download_file(req.input_url, input_file)
            else:
                input_file = req.input_path

            output_file = os.path.join(RENDER_DIR, req.output_filename)
            cmd = build_ffmpeg_command(req, input_file, output_file)

            start = time.time()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            duration = round(time.time() - start, 2)

            if proc.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"FFmpeg failed: {stderr.decode(errors='replace')[-500:]}",
                )

            file_size = os.path.getsize(output_file)

            if req.callback_url:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(req.callback_url, json={
                            "job_id": job_id,
                            "status": "completed",
                            "output_path": output_file,
                            "duration_seconds": duration,
                            "file_size_bytes": file_size,
                        })
                except Exception:
                    pass

            return RenderResponse(
                job_id=job_id,
                status="completed",
                output_path=output_file,
                duration_seconds=duration,
                file_size_bytes=file_size,
            )

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/output/{filename}")
async def get_output(filename: str):
    file_path = os.path.join(RENDER_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="video/mp4")


@app.on_event("startup")
async def startup():
    global redis_pool
    try:
        redis_pool = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_pool.ping()
    except Exception:
        redis_pool = None


@app.on_event("shutdown")
async def shutdown():
    if redis_pool:
        await redis_pool.close()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("WORKER_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
