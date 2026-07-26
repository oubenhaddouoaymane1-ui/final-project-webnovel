import asyncio
import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import edge_tts
import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="CineOS Voice/TTS Worker", version="1.0.0")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
VOICE_OUTPUT_DIR = os.environ.get("VOICE_OUTPUT_DIR", "/voice/output")
VOICE_CACHE_DIR = os.environ.get("VOICE_CACHE_DIR", "/voice/cache")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "en-US-AriaNeural")
DEFAULT_RATE = os.environ.get("DEFAULT_RATE", "+0%")
DEFAULT_VOLUME = os.environ.get("DEFAULT_VOLUME", "+0%")
DEFAULT_PITCH = os.environ.get("DEFAULT_PITCH", "+0Hz")

redis_pool: Optional[aioredis.Redis] = None

Path(VOICE_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(VOICE_CACHE_DIR).mkdir(parents=True, exist_ok=True)

_start_time = time.time()


class TTSRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    rate: str = DEFAULT_RATE
    volume: str = DEFAULT_VOLUME
    pitch: str = DEFAULT_PITCH
    output_format: str = "audio-24khz-96kbitrate-mono-mp3"
    output_filename: Optional[str] = None
    use_cache: bool = True
    callback_url: Optional[str] = None


class TTSResponse(BaseModel):
    job_id: str
    status: str
    output_path: Optional[str] = None
    duration_ms: Optional[int] = None
    file_size_bytes: Optional[int] = None
    cached: bool = False


class VoiceInfo(BaseModel):
    name: str
    short_name: str
    gender: str
    locale: str


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    cached_voices: int


class VoicesResponse(BaseModel):
    voices: list[VoiceInfo]


def get_cache_key(req: TTSRequest) -> str:
    content = f"{req.text}|{req.voice}|{req.rate}|{req.volume}|{req.pitch}|{req.output_format}"
    return hashlib.sha256(content.encode()).hexdigest()


async def synthesize_speech(req: TTSRequest, output_path: str) -> int:
    communicate = edge_tts.Communicate(
        text=req.text,
        voice=req.voice,
        rate=req.rate,
        volume=req.volume,
        pitch=req.pitch,
    )
    await communicate.save(output_path)
    return os.path.getsize(output_path)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    cache_files = list(Path(VOICE_CACHE_DIR).glob("*.mp3")) if Path(VOICE_CACHE_DIR).exists() else []
    return HealthResponse(
        status="healthy",
        uptime_seconds=round(time.time() - _start_time, 2),
        cached_voices=len(cache_files),
    )


@app.get("/voices", response_model=VoicesResponse)
async def list_voices():
    voices = await edge_tts.list_voices()
    result = [
        VoiceInfo(
            name=v["FriendlyName"],
            short_name=v["ShortName"],
            gender=v["Gender"],
            locale=v["Locale"],
        )
        for v in voices
    ]
    return VoicesResponse(voices=result)


@app.post("/synthesize", response_model=TTSResponse)
async def synthesize(req: TTSRequest):
    job_id = uuid.uuid4().hex
    filename = req.output_filename or f"tts_{job_id}.mp3"

    if req.use_cache:
        cache_key = get_cache_key(req)
        cached_path = os.path.join(VOICE_CACHE_DIR, f"{cache_key}.mp3")
        if os.path.isfile(cached_path):
            output_path = os.path.join(VOICE_OUTPUT_DIR, filename)
            import shutil
            shutil.copy2(cached_path, output_path)
            file_size = os.path.getsize(output_path)

            if req.callback_url:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(req.callback_url, json={
                            "job_id": job_id,
                            "status": "completed",
                            "output_path": output_path,
                            "file_size_bytes": file_size,
                            "cached": True,
                        })
                except Exception:
                    pass

            return TTSResponse(
                job_id=job_id,
                status="completed",
                output_path=output_path,
                file_size_bytes=file_size,
                cached=True,
            )

    output_path = os.path.join(VOICE_OUTPUT_DIR, filename)

    try:
        file_size = await synthesize_speech(req, output_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")

    if req.use_cache:
        cache_key = get_cache_key(req)
        cached_path = os.path.join(VOICE_CACHE_DIR, f"{cache_key}.mp3")
        import shutil
        shutil.copy2(output_path, cached_path)

    if req.callback_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(req.callback_url, json={
                    "job_id": job_id,
                    "status": "completed",
                    "output_path": output_path,
                    "file_size_bytes": file_size,
                    "cached": False,
                })
        except Exception:
            pass

    return TTSResponse(
        job_id=job_id,
        status="completed",
        output_path=output_path,
        file_size_bytes=file_size,
        cached=False,
    )


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    file_path = os.path.join(VOICE_OUTPUT_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(file_path, media_type=media_type)


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
    port = int(os.environ.get("WORKER_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=2)
