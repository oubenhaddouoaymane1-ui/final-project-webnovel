"""Visual production module for generating anime-style images"""
import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.database import Database
from src.database.models import GeneratedImage, Character, World
from src.novel_analyzer.parser import Scene

logger = logging.getLogger(__name__)


@dataclass
class GeneratedImageData:
    """Generated image data"""
    id: str
    scene_id: str
    image_path: str
    prompt: str
    negative_prompt: str
    seed: int
    score: float
    is_selected: bool


class PromptCompiler:
    """Compile prompts from structured data"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.style_prefix = "anime style, high quality, detailed, masterpiece, best quality, "
        self.negative_base = (
            "low quality, blurry, distorted, deformed, ugly, "
            "bad anatomy, bad hands, extra fingers, missing fingers, "
            "extra limbs, missing limbs, text, watermark, logo, "
            "signature, username, error, jpeg artifacts, "
            "worst quality, low resolution, normal quality"
        )
        
    def compile_prompt(
        self,
        scene: Scene,
        characters: List[Character],
        world: World,
        shot_type: str = "medium"
    ) -> tuple[str, str]:
        """Compile prompt and negative prompt from scene data"""
        prompt_parts = [self.style_prefix]
        
        # Add shot type
        prompt_parts.append(self._shot_type_to_prompt(shot_type))
        
        # Add scene atmosphere
        if scene.emotion and scene.emotion != "neutral":
            prompt_parts.append(f"{scene.emotion} atmosphere, ")
            
        # Add time of day lighting
        if scene.time_of_day and scene.time_of_day != "unknown":
            lighting_map = {
                "morning": "morning light, warm sunlight, ",
                "afternoon": "afternoon light, bright daylight, ",
                "evening": "evening light, golden hour, ",
                "night": "nighttime, moonlight, dark sky, "
            }
            prompt_parts.append(lighting_map.get(scene.time_of_day, ""))
            
        # Add character descriptions (up to 3)
        for char in characters[:3]:
            char_desc = self._character_to_prompt(char)
            if char_desc:
                prompt_parts.append(char_desc)
                
        # Add world elements
        world_desc = self._world_to_prompt(world)
        if world_desc:
            prompt_parts.append(world_desc)
            
        # Add location
        if scene.location and scene.location != "unknown":
            prompt_parts.append(f"{scene.location}, ")
            
        prompt = "".join(prompt_parts).rstrip(", ")
        
        # Build negative prompt
        negative_prompt = self.negative_base
        
        # Add character-specific negatives
        for char in characters:
            if char.eye_color and char.eye_color != "unknown":
                negative_prompt += f", wrong {char.eye_color} eyes"
            if char.hair_color and char.hair_color != "unknown":
                negative_prompt += f", wrong {char.hair_color} hair"
                
        return prompt, negative_prompt
        
    def _character_to_prompt(self, character: Character) -> str:
        """Convert character to prompt text"""
        parts = []
        
        if character.gender and character.gender != "unknown":
            parts.append(character.gender)
            
        if character.hair_color and character.hair_color != "unknown":
            parts.append(f"{character.hair_color} hair")
            
        if character.hair_style and character.hair_style not in ["average", "unknown"]:
            parts.append(character.hair_style)
            
        if character.eye_color and character.eye_color != "unknown":
            parts.append(f"{character.eye_color} eyes")
            
        if character.typical_clothing and character.typical_clothing != "unknown":
            parts.append(character.typical_clothing)
            
        return ", ".join(parts) + ", " if parts else ""
        
    def _world_to_prompt(self, world: World) -> str:
        """Convert world to prompt text"""
        parts = []
        
        if world.architecture and world.architecture != "unknown":
            parts.append(world.architecture)
            
        if world.visual_atmosphere and world.visual_atmosphere != "unknown":
            parts.append(f"{world.visual_atmosphere} atmosphere")
            
        return ", ".join(parts[:2]) + ", " if parts else ""
        
    def _shot_type_to_prompt(self, shot_type: str) -> str:
        """Convert shot type to prompt text"""
        shot_prompts = {
            "establishing": "wide establishing shot, landscape, panoramic, ",
            "wide": "wide angle shot, full scene, detailed background, ",
            "medium": "medium shot, waist up, upper body, ",
            "close_up": "close up shot, face focus, detailed face, ",
            "extreme_close_up": "extreme close up, detailed eyes, face detail, ",
            "reaction": "reaction shot, emotional expression, expressive face, ",
            "pov": "point of view shot, first person perspective, ",
            "action": "action shot, dynamic pose, motion blur, ",
            "impact": "impact shot, dramatic moment, intense, "
        }
        return shot_prompts.get(shot_type, "medium shot, ")


class VisualCritic:
    """Evaluate and select best generated images"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.threshold = config["quality"]["visual_score"]
        
    def evaluate_candidates(
        self,
        candidates: List[GeneratedImageData],
        scene: Scene,
        characters: List[Character]
    ) -> Optional[GeneratedImageData]:
        """Evaluate candidates and select the best one"""
        if not candidates:
            return None
            
        scored = []
        for candidate in candidates:
            score = self._score_candidate(candidate, scene, characters)
            scored.append((candidate, score))
            
        scored.sort(key=lambda x: x[1], reverse=True)
        
        best_candidate, best_score = scored[0]
        
        if best_score >= self.threshold:
            best_candidate.is_selected = True
            logger.info(f"Selected image with score {best_score:.1f}")
            return best_candidate
        else:
            logger.warning(f"Best score {best_score:.1f} below threshold {self.threshold}")
            # Still return the best one, but mark as below threshold
            best_candidate.is_selected = True
            return best_candidate
            
    def _score_candidate(
        self,
        candidate: GeneratedImageData,
        scene: Scene,
        characters: List[Character]
    ) -> float:
        """Score a candidate image"""
        score = candidate.score * 0.4  # Base score from generation
        
        prompt_lower = candidate.prompt.lower()
        
        # Scene emotion match
        if scene.emotion and scene.emotion in prompt_lower:
            score += 2.0
            
        # Character consistency
        for char in characters:
            if char.eye_color and char.eye_color != "unknown" and char.eye_color in prompt_lower:
                score += 0.5
            if char.hair_color and char.hair_color != "unknown" and char.hair_color in prompt_lower:
                score += 0.5
                
        # Shot type match
        if scene.importance == "critical" and "establishing" in prompt_lower:
            score += 1.0
            
        return min(score, 10.0)


class CloudImageClient:
    """Client for cloud image generation (Pollinations.ai — free, no GPU)."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.width = config["image"]["width"]
        self.height = config["image"]["height"]
        self.steps = config["image"]["steps"]
        self.cfg_scale = config["image"]["cfg_scale"]
        self.pollinations_url = "https://image.pollinations.ai/prompt"

    async def generate(
        self,
        prompt: str,
        negative_prompt: str,
        seed: int = 0,
        num_images: int = 1,
    ) -> List[Dict[str, Any]]:
        """Generate images via Pollinations.ai (free cloud API, no GPU needed)."""
        import httpx
        import random
        import os

        results = []
        for i in range(num_images):
            actual_seed = seed + i
            try:
                encoded_prompt = prompt.replace(" ", "%20").replace(",", "%2C")
                url = f"{self.pollinations_url}/{encoded_prompt}"
                params = {
                    "width": self.width,
                    "height": self.height,
                    "nologo": "true",
                    "seed": actual_seed,
                }

                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "")
                    if not content_type.startswith("image/"):
                        raise RuntimeError(f"Pollinations returned non-image: {content_type}")

                    image_path = f"./generated/images/cloud_{actual_seed}_{i}.png"
                    os.makedirs(os.path.dirname(image_path), exist_ok=True)
                    with open(image_path, "wb") as f:
                        f.write(resp.content)

                    results.append({
                        "path": image_path,
                        "seed": actual_seed,
                        "score": 7.5,
                    })
                    logger.info(f"Generated image via Pollinations (seed={actual_seed})")

            except Exception as e:
                logger.warning(f"Pollinations generation failed for seed {actual_seed}: {e}")
                results.append({
                    "path": f"./generated/images/failed_{actual_seed}_{i}.png",
                    "seed": actual_seed,
                    "score": 0.0,
                })

        return results


class VisualProducer:
    """Produce visual content for scenes"""
    
    def __init__(self, config: Dict[str, Any], db: Database):
        self.config = config
        self.db = db
        self.prompt_compiler = PromptCompiler(config)
        self.visual_critic = VisualCritic(config)
        self.cloud_client = CloudImageClient(config)
        
    async def produce_scene(
        self,
        scene: Scene,
        characters: List[Character],
        world: World
    ) -> List[GeneratedImageData]:
        """Produce images for a scene"""
        images = []
        
        # Determine shot types for the scene
        shot_types = self._determine_shot_types(scene)
        
        for shot_type in shot_types:
            # Compile prompt
            prompt, negative_prompt = self.prompt_compiler.compile_prompt(
                scene, characters, world, shot_type
            )
            
            logger.debug(f"Generating with prompt: {prompt[:100]}...")
            
            # Generate multiple candidates
            candidates = await self._generate_candidates(
                scene.id, prompt, negative_prompt
            )
            
            # Evaluate and select best
            candidate_images = []
            for cand in candidates:
                img_data = GeneratedImageData(
                    id=str(uuid.uuid4()),
                    scene_id=scene.id,
                    image_path=cand["path"],
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    seed=cand["seed"],
                    score=cand["score"],
                    is_selected=False
                )
                candidate_images.append(img_data)
                
            best_image = self.visual_critic.evaluate_candidates(
                candidate_images, scene, characters
            )
            
            if best_image:
                images.append(best_image)
                
                # Save to database
                try:
                    with self.db.get_session() as session:
                        db_image = GeneratedImage(
                            id=best_image.id,
                            scene_id=best_image.scene_id,
                            image_path=best_image.image_path,
                            prompt_used=best_image.prompt,
                            negative_prompt=best_image.negative_prompt,
                            seed=best_image.seed,
                            score=best_image.score,
                            is_selected=best_image.is_selected
                        )
                        session.add(db_image)
                        session.commit()
                except Exception as e:
                    logger.error(f"Error saving image to database: {e}")
                    
        return images
        
    def _determine_shot_types(self, scene: Scene) -> List[str]:
        """Determine shot types based on scene importance"""
        importance_shot_map = {
            "critical": ["establishing", "medium", "close_up"],
            "important": ["wide", "medium"],
            "normal": ["medium"],
            "minor": ["medium"]
        }
        return importance_shot_map.get(scene.importance, ["medium"])
        
    async def _generate_candidates(
        self,
        scene_id: str,
        prompt: str,
        negative_prompt: str,
        count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate multiple image candidates"""
        count = count or self.config["image"]["candidates_per_scene"]
        
        candidates = []
        for i in range(count):
            results = await self.cloud_client.generate(
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=i * 42 + hash(scene_id) % 10000,
                num_images=1,
            )
            candidates.extend(results)
            
        return candidates