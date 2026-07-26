"""Video assembly module for creating final cinematic video"""
import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.database import Database
from src.database.models import GeneratedImage, GeneratedAudio
from src.novel_analyzer.parser import Scene

logger = logging.getLogger(__name__)


@dataclass
class VideoClip:
    """Video clip data"""
    id: str
    image_path: str
    audio_path: str
    duration: float
    transition: str
    effects: List[str]


class TransitionEngine:
    """Handle video transitions"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def get_transition(self, scene: Scene) -> str:
        """Determine transition type for scene"""
        emotion_transitions = {
            "joy": "dissolve",
            "sadness": "fade",
            "anger": "wipe",
            "fear": "fade",
            "surprise": "slide",
            "neutral": "dissolve"
        }
        return emotion_transitions.get(scene.emotion, "dissolve")


class EffectsEngine:
    """Apply visual effects to clips"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def get_effects(self, scene: Scene) -> List[str]:
        """Determine effects for scene"""
        effects = []
        
        if scene.importance == "critical":
            effects.extend(["slow_motion", "vignette"])
        elif scene.importance == "important":
            effects.append("vignette")
            
        if scene.emotion == "fear":
            effects.append("dark_overlay")
        elif scene.emotion == "joy":
            effects.append("warm_filter")
            
        return effects


class FFmpegAssembler:
    """Assemble video using FFmpeg (production path)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.fps = config["video"]["fps"]
        self.resolution = config["video"]["resolution"]
        self.format = config["video"]["format"]
        
    def assemble(self, clips: List[VideoClip], output_path: str) -> bool:
        """Assemble clips into final video via FFmpeg"""
        try:
            import subprocess
            import tempfile
            
            with tempfile.TemporaryDirectory() as tmpdir:
                concat_file = Path(tmpdir) / "concat.txt"
                entries = []
                
                for i, clip in enumerate(clips):
                    if not Path(clip.image_path).exists():
                        continue
                        
                    frame_path = Path(tmpdir) / f"frame_{i:04d}.png"
                    img = __import__("PIL").Image.open(clip.image_path)
                    w, h = map(int, self.resolution.split("x"))
                    img = img.resize((w, h), __import__("PIL").Image.Resampling.LANCZOS)
                    img.save(frame_path)
                    entries.append(f"file '{frame_path}'")
                    entries.append(f"duration {clip.duration}")
                
                if not entries:
                    logger.error("No valid clips to assemble")
                    return False
                    
                concat_file.write_text("\n".join(entries))
                
                cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-vf", f"fps={self.fps}",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    output_path,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                if result.returncode == 0:
                    logger.info(f"Video assembled: {output_path}")
                    return True
                else:
                    logger.error(f"FFmpeg error: {result.stderr.decode()}")
                    return False
                    
        except Exception as e:
            logger.error(f"Assembly error: {e}")
            return False
            


class VideoAssembler:
    """Assemble final video from scenes"""
    
    def __init__(self, config: Dict[str, Any], db: Database):
        self.config = config
        self.db = db
        self.transition_engine = TransitionEngine(config)
        self.effects_engine = EffectsEngine(config)
        self.ffmpeg_assembler = FFmpegAssembler(config)
        
    async def assemble_video(
        self,
        project_id: str,
        scenes: List[Scene]
    ) -> str:
        """Assemble all scenes into final video"""
        video_path = str(Path(self.config['storage']['video_path']) / f"{project_id}.mp4")
        
        try:
            # Create video clips for each scene
            clips = []
            for scene in scenes:
                clip = await self._create_scene_clip(scene)
                if clip:
                    clips.append(clip)
                    
            if not clips:
                logger.error("No clips to assemble")
                return video_path
                
            # Combine clips into final video
            success = self.ffmpeg_assembler.assemble(clips, video_path)
            
            if success:
                logger.info(f"Video assembled successfully: {video_path}")
            else:
                logger.warning("Video assembly completed with issues")
                
            return video_path
            
        except Exception as e:
            logger.error(f"Error assembling video: {e}")
            return video_path
            
    async def _create_scene_clip(self, scene: Scene) -> Optional[VideoClip]:
        """Create video clip for a scene"""
        try:
            # Get generated images for scene
            with self.db.get_session() as session:
                images = session.query(GeneratedImage).filter(
                    GeneratedImage.scene_id == scene.id,
                    GeneratedImage.is_selected == True
                ).all()
                
                # Get generated audio for scene
                audio = session.query(GeneratedAudio).filter(
                    GeneratedAudio.scene_id == scene.id
                ).first()
                
            if not images:
                logger.warning(f"No images for scene {scene.id}")
                return None
                
            # Use first selected image
            image = images[0]
            
            # Get audio path
            audio_path = audio.audio_path if audio else ""
            if audio_path and not Path(audio_path).exists():
                audio_path = ""
                
            # Get transition type
            transition = self.transition_engine.get_transition(scene)
            
            # Get effects
            effects = self.effects_engine.get_effects(scene)
            
            # Use audio duration or default
            duration = audio.duration if audio else 5.0
            
            return VideoClip(
                id=str(uuid.uuid4()),
                image_path=image.image_path,
                audio_path=audio_path,
                duration=duration,
                transition=transition,
                effects=effects
            )
            
        except Exception as e:
            logger.error(f"Error creating clip for scene {scene.id}: {e}")
            return None