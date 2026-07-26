import os
import uuid
import json
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.render_worker")

TRANSITIONS = {
    "crossfade": "xfade=transition=fade:duration={duration}:offset={offset}",
    "fade_black": "xfade=transition=fadeblack:duration={duration}:offset={offset}",
    "fade_white": "xfade=transition=fadewhite:duration={duration}:offset={offset}",
    "wipe_left": "xfade=transition=wipeleft:duration={duration}:offset={offset}",
    "wipe_right": "xfade=transition=wiperight:duration={duration}:offset={offset}",
    "slide_left": "xfade=transition=slideleft:duration={duration}:offset={offset}",
    "dissolve": "xfade=transition=dissolve:duration={duration}:offset={offset}",
    "pixelize": "xfade=transition=pixelize:duration={duration}:offset={offset}",
    "none": None,
}


class ClipInput(BaseModel):
    clip_id: str
    source_path: str
    duration: Optional[float] = None
    in_point: Optional[float] = 0.0
    out_point: Optional[float] = None
    transition: Optional[str] = "crossfade"
    transition_duration: Optional[float] = 1.0


class RenderRequest(BaseModel):
    project_id: str
    clips: List[ClipInput]
    output_format: str = "mp4"
    resolution: str = "1920x1080"
    fps: int = 24
    audio_tracks: Optional[List[Dict[str, Any]]] = None
    subtitle_path: Optional[str] = None
    output_name: Optional[str] = None


class SubtitleBurnRequest(BaseModel):
    video_path: str
    subtitle_path: str
    output_path: Optional[str] = None
    style: Optional[str] = "default"


class RenderWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            name="render-worker",
            worker_type="video_render",
            job_types=["video_render", "clip_assembly"],
            capabilities=["video_render", "clip_assembly", "transitions", "subtitles", "audio_mixing"],
            port=8300,
        )
        self.render_dir: str = os.getenv("RENDER_DIR", "/data/render")
        self.temp_dir: str = os.getenv("TEMP_DIR", "/tmp/cineos_render")
        self.ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
        self.ffprobe_path: str = os.getenv("FFPROBE_PATH", "ffprobe")
        self.default_audio_volume: float = float(os.getenv("DEFAULT_AUDIO_VOLUME", "0.8"))

        self._setup_render_routes()

    def _setup_render_routes(self):
        @self.app.post("/render")
        async def start_render(req: RenderRequest):
            job_id = str(uuid.uuid4())
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'video_render', 'pending', 7, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(req.dict()),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.post("/render/subtitles")
        async def burn_subtitles(req: SubtitleBurnRequest):
            job_id = str(uuid.uuid4())
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'clip_assembly', 'pending', 6, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps({
                        "operation": "subtitle_burn",
                        "video_path": req.video_path,
                        "subtitle_path": req.subtitle_path,
                        "output_path": req.output_path,
                        "style": req.style,
                    }),
                )
            return {"job_id": job_id, "status": "pending"}

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job["payload"]
        job_type = job["type"]

        if job_type == "video_render":
            return await self._handle_render(payload, job["id"])
        elif job_type == "clip_assembly":
            operation = payload.get("operation", "clip_assembly")
            if operation == "subtitle_burn":
                return await self._handle_subtitle_burn(payload, job["id"])
            return await self._handle_clip_assembly(payload, job["id"])
        else:
            raise ValueError(f"Unknown render job type: {job_type}")

    async def _handle_render(
        self, payload: Dict[str, Any], job_id: str
    ) -> Dict[str, Any]:
        clips = payload.get("clips", [])
        output_format = payload.get("output_format", "mp4")
        resolution = payload.get("resolution", "1920x1080")
        fps = payload.get("fps", 24)
        audio_tracks = payload.get("audio_tracks") or []
        subtitle_path = payload.get("subtitle_path")
        output_name = payload.get("output_name", f"render_{job_id[:8]}")

        width, height = resolution.split("x")

        render_temp = Path(self.temp_dir) / job_id
        render_temp.mkdir(parents=True, exist_ok=True)

        clip_paths: List[str] = []
        for i, clip in enumerate(clips):
            source = clip.get("source_path", "")
            if not Path(source).exists():
                raise FileNotFoundError(f"Clip source not found: {source}")

            in_point = clip.get("in_point", 0.0)
            out_point = clip.get("out_point")
            clip_duration = clip.get("duration")

            processed_path = str(render_temp / f"clip_{i:04d}.mp4")
            await self._extract_clip(
                source=source,
                output=processed_path,
                start=in_point,
                end=out_point,
                duration=clip_duration,
                width=int(width),
                height=int(height),
                fps=fps,
            )
            clip_paths.append(processed_path)

        if len(clip_paths) > 1:
            merged_path = str(render_temp / "merged.mp4")
            await self._merge_clips_with_transitions(
                clip_paths=clip_paths,
                clips_data=clips,
                output=merged_path,
                width=int(width),
                height=int(height),
                fps=fps,
            )
            current_video = merged_path
        elif clip_paths:
            current_video = clip_paths[0]
        else:
            raise ValueError("No clips provided for render")

        if audio_tracks:
            mixed_path = str(render_temp / "audio_mixed.mp4")
            await self._mix_audio(
                video_path=current_video,
                audio_tracks=audio_tracks,
                output=mixed_path,
            )
            current_video = mixed_path

        if subtitle_path and Path(subtitle_path).exists():
            subtitled_path = str(render_temp / "subtitled.mp4")
            await self._burn_subtitles(
                video_path=current_video,
                subtitle_path=subtitle_path,
                output=subtitled_path,
            )
            current_video = subtitled_path

        output_path = Path(self.render_dir) / f"{output_name}.{output_format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if current_video != str(output_path):
            if output_format == "mp4" and current_video.endswith(".mp4"):
                import shutil
                shutil.move(current_video, str(output_path))
            else:
                await self._transcode(
                    current_video, str(output_path), output_format, int(width), int(height), fps
                )

        file_size = output_path.stat().st_size
        video_duration = await self._get_duration(str(output_path))

        for clip_path in clip_paths:
            try:
                Path(clip_path).unlink(missing_ok=True)
            except Exception:
                pass
        try:
            import shutil
            shutil.rmtree(render_temp, ignore_errors=True)
        except Exception:
            pass

        return {
            "output_path": str(output_path),
            "output_name": output_name,
            "format": output_format,
            "resolution": resolution,
            "fps": fps,
            "duration_seconds": video_duration,
            "file_size_bytes": file_size,
            "clips_count": len(clips),
        }

    async def _handle_clip_assembly(
        self, payload: Dict[str, Any], job_id: str
    ) -> Dict[str, Any]:
        clips = payload.get("clips", [])
        output_name = payload.get("output_name", f"assembly_{job_id[:8]}")

        render_temp = Path(self.temp_dir) / job_id
        render_temp.mkdir(parents=True, exist_ok=True)

        concat_file = render_temp / "concat.txt"
        clip_paths: List[str] = []

        for i, clip in enumerate(clips):
            source = clip.get("source_path", "")
            if not Path(source).exists():
                raise FileNotFoundError(f"Clip not found: {source}")

            normalized = str(render_temp / f"norm_{i:04d}.mp4")
            await self._normalize_clip(source, normalized)
            clip_paths.append(normalized)

        with open(concat_file, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        output_path = Path(self.render_dir) / f"{output_name}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {stderr.decode()}")

        file_size = output_path.stat().st_size
        duration = await self._get_duration(str(output_path))

        import shutil
        shutil.rmtree(render_temp, ignore_errors=True)

        return {
            "output_path": str(output_path),
            "output_name": output_name,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "clips_count": len(clips),
        }

    async def _handle_subtitle_burn(
        self, payload: Dict[str, Any], job_id: str
    ) -> Dict[str, Any]:
        video_path = payload.get("video_path", "")
        subtitle_path = payload.get("subtitle_path", "")
        output_path_str = payload.get("output_path")

        if not Path(video_path).exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        if not Path(subtitle_path).exists():
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

        if not output_path_str:
            output_path_str = str(
                Path(self.render_dir) / f"subtitled_{job_id[:8]}.mp4"
            )

        await self._burn_subtitles(video_path, subtitle_path, output_path_str)

        file_size = Path(output_path_str).stat().st_size
        duration = await self._get_duration(output_path_str)

        return {
            "output_path": output_path_str,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
        }

    async def _extract_clip(
        self,
        source: str,
        output: str,
        start: float = 0.0,
        end: Optional[float] = None,
        duration: Optional[float] = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 24,
    ):
        cmd = [self.ffmpeg_path, "-y", "-ss", str(start), "-i", source]

        if end is not None:
            cmd.extend(["-to", str(end)])
        elif duration is not None:
            cmd.extend(["-t", str(duration)])

        cmd.extend([
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-pix_fmt", "yuv420p",
            output,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Clip extraction failed: {stderr.decode()}")

    async def _merge_clips_with_transitions(
        self,
        clip_paths: List[str],
        clips_data: List[Dict[str, Any]],
        output: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 24,
    ):
        if len(clip_paths) < 2:
            raise ValueError("Need at least 2 clips to merge")

        durations: List[float] = []
        for cp in clip_paths:
            d = await self._get_duration(cp)
            durations.append(d)

        filter_parts: List[str] = []
        inputs: List[str] = []
        for i, cp in enumerate(clip_paths):
            inputs.extend(["-i", cp])

        current_label = "[0:v]"
        current_audio = "[0:a]"

        for i in range(1, len(clip_paths)):
            clip_info = clips_data[i] if i < len(clips_data) else {}
            transition_type = clip_info.get("transition", "crossfade")
            transition_dur = clip_info.get("transition_duration", 1.0)

            offset = sum(durations[:i]) - (transition_dur * i) if i > 0 else 0
            offset = max(0, offset)

            next_label = f"[v{i}]"
            next_audio = f"[a{i}]"

            transition_filter = TRANSITIONS.get(transition_type)
            if transition_filter and i < len(clip_paths):
                xfade_expr = transition_filter.format(
                    duration=transition_dur, offset=offset
                )
                filter_parts.append(
                    f"{current_label}[{i}:v]{xfade_expr}{next_label}"
                )
                filter_parts.append(
                    f"{current_audio}[{i}:a]amix=inputs=2:duration=longest:dropout_transition=2{next_audio}"
                )
                current_label = next_label
                current_audio = next_audio
            else:
                filter_parts.append(
                    f"{current_label}[{i}:v]concat=n=2:v=1:a=0{next_label}"
                )
                filter_parts.append(
                    f"{current_audio}[{i}:a]concat=n=2:v=0:a=1{next_audio}"
                )
                current_label = next_label
                current_audio = next_audio

        filter_complex = ";".join(filter_parts)

        cmd = [
            self.ffmpeg_path, "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", current_label,
            "-map", current_audio,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            output,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"Merge with transitions failed: {stderr.decode()}")

    async def _mix_audio(
        self,
        video_path: str,
        audio_tracks: List[Dict[str, Any]],
        output: str,
    ):
        cmd = [self.ffmpeg_path, "-y", "-i", video_path]

        filter_inputs: List[str] = []
        for i, track in enumerate(audio_tracks):
            audio_path = track.get("path", "")
            if not audio_path or not Path(audio_path).exists():
                logger.warning("Audio track %d not found: %s", i, audio_path)
                continue
            cmd.extend(["-i", audio_path])
            volume = track.get("volume", self.default_audio_volume)
            start_at = track.get("start_at", 0.0)
            filter_inputs.append(
                f"[{i + 1}:a]volume={volume},adelay={int(start_at * 1000)}|{int(start_at * 1000)}[a{i}]"
            )

        if not filter_inputs:
            import shutil
            shutil.copy2(video_path, output)
            return

        mix_labels = "".join(f"[a{i}]" for i in range(len(filter_inputs)))
        n_inputs = len(filter_inputs) + 1
        filter_inputs.append(
            f"[0:a]{mix_labels}amix=inputs={n_inputs}:duration=first:dropout_transition=2[outa]"
        )
        filter_complex = ";".join(filter_inputs)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Audio mixing failed: {stderr.decode()}")

    async def _burn_subtitles(
        self,
        video_path: str,
        subtitle_path: str,
        output: str,
    ):
        sub_ext = Path(subtitle_path).suffix.lower()
        if sub_ext in (".srt", ".ass", ".ssa", ".vtt"):
            sub_filter = f"subtitles='{subtitle_path}':force_style='FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1'"
        else:
            raise ValueError(f"Unsupported subtitle format: {sub_ext}")

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vf", sub_filter,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "copy",
            output,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Subtitle burn failed: {stderr.decode()}")

    async def _normalize_clip(self, input_path: str, output_path: str):
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-r", "24",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Clip normalization failed: {stderr.decode()}")

    async def _transcode(
        self,
        input_path: str,
        output_path: str,
        fmt: str,
        width: int,
        height: int,
        fps: int,
    ):
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", input_path,
            "-vf", f"scale={width}:{height}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"Transcode failed: {stderr.decode()}")

    async def _get_duration(self, video_path: str) -> float:
        cmd = [
            self.ffprobe_path,
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
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
    worker = RenderWorker()
    worker.run()


if __name__ == "__main__":
    main()
