"""Configuration management for the pipeline"""
import os
from pathlib import Path
from typing import Dict, Any

import yaml
from dotenv import load_dotenv

def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file"""
    # Load environment variables
    load_dotenv()
    
    # Load config file
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Replace environment variables
    config = _replace_env_vars(config)
    
    return config

def _replace_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace ${VAR} patterns with environment variable values"""
    if isinstance(config, dict):
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                config[key] = os.getenv(env_var, "")
            elif isinstance(value, dict):
                config[key] = _replace_env_vars(value)
    return config