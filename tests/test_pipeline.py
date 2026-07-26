"""Tests for the pipeline components"""
import pytest
import asyncio
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_project_structure():
    """Test that project structure is correct"""
    assert Path("src").exists()
    assert Path("src/telegram").exists()
    assert Path("src/novel_analyzer").exists()
    assert Path("src/character_engine").exists()
    assert Path("src/world_engine").exists()
    assert Path("src/visual_production").exists()
    assert Path("src/audio_production").exists()
    assert Path("src/video_assembly").exists()
    assert Path("src/quality_control").exists()
    assert Path("src/llm").exists()
    assert Path("src/utils").exists()

def test_database_models():
    """Test that database models are importable"""
    from src.database.models import Character, World, Scene, Novel, Project
    assert Character is not None
    assert World is not None
    assert Scene is not None
    assert Novel is not None
    assert Project is not None

def test_config_loading():
    """Test that configuration can be loaded"""
    from src.config import load_config
    config = load_config("config/config.example.yaml")
    assert config is not None
    assert "system" in config
    assert "database" in config
    assert "telegram" in config
    assert "llm" in config
    assert "image" in config
    assert "audio" in config

def test_llm_client_init():
    """Test that LLM client can be initialized"""
    from src.llm import OllamaClient
    config = {"llm": {"model": "llama3.2", "temperature": 0.7, "max_tokens": 4096}}
    client = OllamaClient(config)
    assert client is not None
    assert client.model == "llama3.2"

def test_novel_parser_init():
    """Test that novel parser can be initialized"""
    from src.novel_analyzer.parser import NovelParser
    config = {"llm": {"model": "llama3.2", "temperature": 0.7, "max_tokens": 4096}}
    parser = NovelParser(config)
    assert parser is not None

def test_prompt_compiler():
    """Test prompt compilation"""
    from src.visual_production.producer import PromptCompiler
    from src.novel_analyzer.parser import Scene
    from src.database.models import Character, World
    
    config = {"quality": {"visual_score": 8.0}}
    compiler = PromptCompiler(config)
    
    # Create mock scene
    scene = Scene(
        id="test_scene",
        chapter_number=1,
        scene_number=1,
        text="Test scene",
        characters=["John"],
        location="castle",
        time_of_day="morning",
        emotion="joy",
        importance="normal"
    )
    
    # Create mock character
    character = Character(
        id="test_char",
        canonical_name="John",
        gender="male",
        hair_color="brown",
        eye_color="blue"
    )
    
    # Create mock world
    world = World(
        id="test_world",
        novel_id="test",
        architecture="medieval",
        visual_atmosphere="mysterious"
    )
    
    prompt, negative = compiler.compile_prompt(scene, [character], world)
    
    assert "anime style" in prompt
    assert "brown hair" in prompt
    assert "blue eyes" in prompt
    assert "medieval" in prompt
    assert "low quality" in negative

def test_character_researcher_init():
    """Test that character researcher can be initialized"""
    from src.character_engine.researcher import CharacterResearcher
    from src.database import Database
    from pathlib import Path
    
    config = {
        "llm": {"model": "llama3.2", "temperature": 0.7, "max_tokens": 4096},
        "database": {"path": "./database"}
    }
    
    # Create test database
    Path("./database").mkdir(exist_ok=True)
    db = Database(Path("./database"))
    
    researcher = CharacterResearcher(config, db)
    assert researcher is not None

def test_world_builder_init():
    """Test that world builder can be initialized"""
    from src.world_engine.builder import WorldBuilder
    from src.database import Database
    from pathlib import Path
    
    config = {
        "llm": {"model": "llama3.2", "temperature": 0.7, "max_tokens": 4096},
        "database": {"path": "./database"}
    }
    
    db = Database(Path("./database"))
    builder = WorldBuilder(config, db)
    assert builder is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])