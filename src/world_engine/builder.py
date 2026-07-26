"""World builder for constructing persistent world rules"""
import logging
import json
import uuid
from typing import List, Dict, Any

from src.database import Database
from src.database.models import World, Scene
from src.llm import OllamaClient

logger = logging.getLogger(__name__)


class WorldBuilder:
    """Build world from novel text and scenes using LLM"""
    
    def __init__(self, config: Dict[str, Any], db: Database):
        self.config = config
        self.db = db
        self.llm = OllamaClient(config)
        
    async def build_world(self, novel_text: str, scenes: List[Scene]) -> World:
        """Build world from novel text using LLM"""
        # Collect all locations from scenes
        locations = list(set(scene.location for scene in scenes if scene.location))
        
        # Use LLM to build world
        novel_excerpt = novel_text[:3000]  # Use first 3000 chars for context
        llm_world = await self.llm.build_world(novel_excerpt, locations)
        
        # Create World object
        world = World(
            id=str(uuid.uuid4()),
            novel_id="current",
            history=llm_world.get("history", "unknown"),
            geography=llm_world.get("geography", ", ".join(locations) if locations else "unknown"),
            climate=llm_world.get("climate", "temperate"),
            architecture=llm_world.get("architecture", "medieval"),
            technology=llm_world.get("technology", "medieval"),
            magic=llm_world.get("magic", "none"),
            religion=llm_world.get("religion", "unknown"),
            politics=llm_world.get("politics", "unknown"),
            economy=llm_world.get("economy", "unknown"),
            transportation=llm_world.get("transportation", "walking and horses"),
            food=llm_world.get("food", "simple fare"),
            currency=llm_world.get("currency", "gold coins"),
            military=llm_world.get("military", "medieval military"),
            culture=llm_world.get("culture", "medieval"),
            language=llm_world.get("language", "common tongue"),
            symbols=llm_world.get("symbols", "unknown"),
            animals=llm_world.get("animals", "common animals"),
            monsters=llm_world.get("monsters", "none"),
            plants=llm_world.get("plants", "common plants"),
            clothing_styles=llm_world.get("clothing_styles", "medieval clothing"),
            materials=llm_world.get("materials", "wood and stone"),
            lighting_style=llm_world.get("lighting_style", "natural"),
            color_palette=llm_world.get("color_palette", "earth tones"),
            visual_atmosphere=llm_world.get("visual_atmosphere", "neutral"),
            locked=True
        )
        
        # Save to database
        with self.db.get_session() as session:
            session.add(world)
            session.commit()
            session.refresh(world)  # Reload before detach
            session.expunge(world)
            
        logger.info(f"World built and locked: {world.visual_atmosphere} atmosphere, {world.technology} technology")
        return world