"""Basic tests for the pipeline"""
import pytest
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_project_structure():
    """Test that project structure is correct"""
    # Check main directories exist
    assert Path("src").exists()
    assert Path("src/telegram").exists()
    assert Path("src/novel_analyzer").exists()
    assert Path("src/character_engine").exists()
    assert Path("src/world_engine").exists()
    assert Path("src/visual_production").exists()
    assert Path("src/audio_production").exists()
    assert Path("src/video_assembly").exists()
    assert Path("src/quality_control").exists()
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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])