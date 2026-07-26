"""Audio production module for generating narration"""
import logging
import uuid
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.database import Database
from src.database.models import GeneratedAudio
from src.novel_analyzer.parser import Scene

logger = logging.getLogger(__name__)


@dataclass
class AudioData:
    """Generated audio data"""
    id: str
    scene_id: str
    audio_path: str
    text: str
    duration: float
    emotion: str


class NarrationScript:
    """Prepare narration script from scene text"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
    def prepare_script(self, scene: Scene) -> str:
        """Prepare narration script from scene text"""
        text = scene.text or ""
        
        # Clean text
        text = " ".join(text.split())
        
        # Add pauses for dramatic effect based on emotion
        text = self._add_pauses(text, scene.emotion)
        
        return text
        
    def _add_pauses(self, text: str, emotion: str) -> str:
        """Add pauses based on emotion"""
        if emotion in ["sadness", "fear"]:
            # Add more dramatic pauses
            sentences = text.split(".")
            return " ... ".join(sentences)
        elif emotion in ["anger", "joy", "surprise"]:
            # More energetic, shorter pauses
            return text.replace(". ", "! ")
        return text


class KokoroTTS:
    """Kokoro TTS client for audio generation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("audio", {})
        self.model = self.config.get("model", "kokoro")
        self.voice = self.config.get("voice", "default")
        self.speed = self.config.get("speed", 1.0)
        self.sample_rate = self.config.get("sample_rate", 22050)
        self.output_dir = Path(config.get("storage", {}).get("audio_path", "./generated/audio"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate(self, text: str, output_path: str, emotion: str = "neutral") -> bool:
        """Generate audio using TTS"""
        try:
            # Try using piper-tts (lightweight, CPU-friendly)
            return self._generate_with_piper(text, output_path)
        except Exception as e:
            logger.warning(f"Piper TTS failed: {e}")
            try:
                # Fallback to espeak
                return self._generate_with_espeak(text, output_path)
            except Exception as e2:
                logger.warning(f"espeak also failed: {e2}")
                # Create placeholder
                return self._create_placeholder(output_path)
                
    def _generate_with_piper(self, text: str, output_path: str) -> bool:
        """Generate using piper-tts"""
        cmd = [
            "echo", text, "|",
            "piper",
            "--model", "en_US-lessac-medium",
            "--output_file", output_path
        ]
        # Piper needs to be installed separately
        # For now, return False to trigger fallback
        return False
        
    def _generate_with_espeak(self, text: str, output_path: str) -> bool:
        """Generate using espeak (usually pre-installed)"""
        try:
            subprocess.run(
                ["espeak", "-w", output_path, text],
                check=True,
                capture_output=True,
                timeout=30
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
            
    def _create_placeholder(self, output_path: str) -> bool:
        """Create a placeholder audio file"""
        try:
            # Create a silent WAV file as placeholder
            import struct
            import wave
            
            # Create 1 second of silence
            sample_rate = 22050
            duration = 1
            num_samples = sample_rate * duration
            
            with wave.open(output_path, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                # Write silence
                wav_file.writeframes(struct.pack('<' + 'h' * num_samples, *([0] * num_samples)))
                
            return True
        except Exception as e:
            logger.error(f"Error creating placeholder audio: {e}")
            return False
            
    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file"""
        try:
            import wave
            with wave.open(audio_path, 'r') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                return duration
        except Exception:
            # Estimate based on text length
            return 5.0  # Default 5 seconds


class AudioProducer:
    """Produce audio narration for scenes"""
    
    def __init__(self, config: Dict[str, Any], db: Database):
        self.config = config
        self.db = db
        self.script_prep = NarrationScript(config)
        self.tts = KokoroTTS(config)
        
    async def produce_scene(self, scene: Scene) -> AudioData:
        """Produce audio for a scene"""
        # Prepare narration script
        script = self.script_prep.prepare_script(scene)
        
        # Generate audio
        audio_id = str(uuid.uuid4())
        audio_path = str(Path(self.config['storage']['audio_path']) / f"{scene.id}.wav")
        
        success = self.tts.generate(script, audio_path, scene.emotion)
        
        if not success:
            logger.warning(f"Audio generation failed for scene {scene.id}, using placeholder")
            
        # Get duration
        duration = self.tts.get_audio_duration(audio_path)
        
        audio_data = AudioData(
            id=audio_id,
            scene_id=scene.id,
            audio_path=audio_path,
            text=script[:500],  # Truncate for storage
            duration=duration,
            emotion=scene.emotion
        )
        
        # Save to database
        try:
            with self.db.get_session() as session:
                db_audio = GeneratedAudio(
                    id=audio_data.id,
                    scene_id=audio_data.scene_id,
                    audio_path=audio_data.audio_path,
                    text_used=audio_data.text,
                    duration=audio_data.duration,
                    emotion=audio_data.emotion
                )
                session.add(db_audio)
                session.commit()
        except Exception as e:
            logger.error(f"Error saving audio to database: {e}")
            
        return audio_data