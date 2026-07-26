import os
import uuid
import json
import hashlib
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.voice_worker")

EDGE_TTS_VOICES: Dict[str, str] = {
    "en-US": "en-US-GuyNeural",
    "en-GB": "en-GB-RyanNeural",
    "en-AU": "en-AU-WilliamNeural",
    "fr-FR": "fr-FR-HenriNeural",
    "de-DE": "de-DE-ConradNeural",
    "es-ES": "es-ES-AlvaroNeural",
    "it-IT": "it-IT-DiegoNeural",
    "pt-BR": "pt-BR-AntonioNeural",
    "ja-JP": "ja-JP-KeitaNeural",
    "ko-KR": "ko-KR-InJoonNeural",
    "zh-CN": "zh-CN-YunxiNeural",
    "hi-IN": "hi-IN-MadhurNeural",
    "ar-SA": "ar-SA-HamedNeural",
    "ru-RU": "ru-RU-DmitryNeural",
    "pl-PL": "pl-PL-MarekNeural",
    "nl-NL": "nl-NL-MaartenNeural",
    "sv-SE": "sv-SE-SofieNeural",
    "da-DK": "da-DK-ChristelNeural",
    "fi-FI": "fi-FI-HarriNeural",
    "nb-NO": "nb-NO-PernilleNeural",
}


class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US"
    rate: Optional[str] = "+0%"
    pitch: Optional[str] = "+0Hz"
    output_format: Optional[str] = "mp3"
    cache_key: Optional[str] = None


class VoiceWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            name="voice-worker",
            worker_type="tts_generation",
            job_types=["tts_generation"],
            capabilities=["text_to_speech", "multi_language", "voice_synthesis"],
            port=8400,
        )
        self.audio_dir: str = os.getenv("AUDIO_DIR", "/data/audio")
        self.cache_dir: str = os.getenv("TTS_CACHE_DIR", "/data/tts_cache")
        self.tts_engine: str = os.getenv("TTS_ENGINE", "edge-tts")
        self.kokoro_url: str = os.getenv("KOKORO_URL", "http://kokoro:5000")
        self.cache_enabled: bool = os.getenv("TTS_CACHE_ENABLED", "true").lower() == "true"

        self._setup_voice_routes()

    def _setup_voice_routes(self):
        @self.app.post("/synthesize")
        async def synthesize_speech(req: SynthesizeRequest):
            job_id = str(uuid.uuid4())
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'tts_generation', 'pending', 9, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(req.dict()),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.get("/audio/{audio_id}")
        async def get_audio(audio_id: str):
            for ext in ["mp3", "wav", "ogg", "flac"]:
                path = Path(self.audio_dir) / f"{audio_id}.{ext}"
                if path.exists():
                    media_types = {
                        "mp3": "audio/mpeg",
                        "wav": "audio/wav",
                        "ogg": "audio/ogg",
                        "flac": "audio/flac",
                    }
                    return FileResponse(str(path), media_type=media_types.get(ext, "audio/mpeg"))
            raise HTTPException(status_code=404, detail="Audio not found")

        @self.app.get("/voices")
        async def list_voices():
            return {"voices": EDGE_TTS_VOICES, "engine": self.tts_engine}

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job["payload"]
        text = payload.get("text", "")
        voice = payload.get("voice", "en-US")
        rate = payload.get("rate", "+0%")
        pitch = payload.get("pitch", "+0Hz")
        output_format = payload.get("output_format", "mp3")
        cache_key = payload.get("cache_key")

        if not text.strip():
            raise ValueError("Empty text provided for TTS")

        if self.cache_enabled:
            cached = await self._check_cache(text, voice, rate, pitch)
            if cached:
                logger.info("Cache hit for TTS: %s", cache_key or text[:30])
                return cached

        if self.tts_engine == "kokoro":
            audio_bytes = await self._synthesize_kokoro(text, voice)
        else:
            audio_bytes = await self._synthesize_edge_tts(text, voice, rate, pitch, output_format)

        audio_id = str(uuid.uuid4())
        audio_path = Path(self.audio_dir) / f"{audio_id}.{output_format}"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(audio_bytes)

        duration = await self._get_audio_duration(str(audio_path))
        file_size = len(audio_bytes)
        checksum = hashlib.sha256(audio_bytes).hexdigest()

        if self.cache_enabled:
            await self._store_cache(text, voice, rate, pitch, audio_id, output_format, file_size)

        await self._write_quality_check(
            job_id=job["id"],
            asset_id=audio_id,
            check_type="tts_generation_complete",
            score=1.0,
            passed=True,
            details={
                "voice": voice,
                "engine": self.tts_engine,
                "duration_seconds": duration,
                "file_size_bytes": file_size,
                "checksum": checksum,
                "text_length": len(text),
            },
        )

        return {
            "audio_id": audio_id,
            "audio_path": str(audio_path),
            "format": output_format,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "checksum": checksum,
            "voice": voice,
            "engine": self.tts_engine,
        }

    async def _synthesize_edge_tts(
        self, text: str, voice: str, rate: str, pitch: str, output_format: str
    ) -> bytes:
        import edge_tts

        voice_name = EDGE_TTS_VOICES.get(voice, voice)

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate=rate,
            pitch=pitch,
        )

        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        if not audio_data:
            raise RuntimeError(f"Edge-TTS returned no audio data for voice {voice_name}")

        if output_format == "wav" and not audio_data[:4] == b"RIFF":
            audio_bytes = await self._convert_to_wav(bytes(audio_data))
            return audio_bytes

        return bytes(audio_data)

    async def _synthesize_kokoro(self, text: str, voice: str) -> bytes:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.kokoro_url}/v1/tts",
                json={
                    "text": text,
                    "voice": voice,
                    "format": "mp3",
                },
            )
            resp.raise_for_status()
            return resp.content

    async def _convert_to_wav(self, mp3_bytes: bytes) -> bytes:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_in:
            tmp_in.write(mp3_bytes)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path.replace(".mp3", ".wav")

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", tmp_in_path,
                "-ar", "44100",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                tmp_out_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return mp3_bytes
            return Path(tmp_out_path).read_bytes()
        finally:
            try:
                Path(tmp_in_path).unlink(missing_ok=True)
                Path(tmp_out_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def _get_audio_duration(self, audio_path: str) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
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

    def _compute_cache_hash(self, text: str, voice: str, rate: str, pitch: str) -> str:
        key = f"{text}|{voice}|{rate}|{pitch}"
        return hashlib.sha256(key.encode()).hexdigest()

    async def _check_cache(
        self, text: str, voice: str, rate: str, pitch: str
    ) -> Optional[Dict[str, Any]]:
        cache_hash = self._compute_cache_hash(text, voice, rate, pitch)
        cache_path = Path(self.cache_dir) / f"{cache_hash}.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text())
                audio_id = cached.get("audio_id", "")
                for ext in ["mp3", "wav", "ogg", "flac"]:
                    audio_path = Path(self.audio_dir) / f"{audio_id}.{ext}"
                    if audio_path.exists():
                        return {
                            "audio_id": audio_id,
                            "audio_path": str(audio_path),
                            "format": ext,
                            "duration_seconds": cached.get("duration_seconds", 0),
                            "file_size_bytes": cached.get("file_size_bytes", 0),
                            "checksum": cached.get("checksum", ""),
                            "voice": voice,
                            "engine": self.tts_engine,
                            "cached": True,
                        }
            except Exception:
                pass
        return None

    async def _store_cache(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        audio_id: str,
        fmt: str,
        file_size: int,
    ):
        cache_hash = self._compute_cache_hash(text, voice, rate, pitch)
        cache_path = Path(self.cache_dir) / f"{cache_hash}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        audio_path = Path(self.audio_dir) / f"{audio_id}.{fmt}"
        duration = await self._get_audio_duration(str(audio_path)) if audio_path.exists() else 0.0
        checksum = hashlib.sha256(audio_path.read_bytes()).hexdigest() if audio_path.exists() else ""

        cache_data = {
            "audio_id": audio_id,
            "format": fmt,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "checksum": checksum,
            "text_hash": cache_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        cache_path.write_text(json.dumps(cache_data))


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = VoiceWorker()
    worker.run()


if __name__ == "__main__":
    main()
