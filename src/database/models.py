"""Database models for the pipeline"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Character(Base):
    """Character DNA model"""
    __tablename__ = "characters"
    
    id = Column(String, primary_key=True)
    canonical_name = Column(String, nullable=False)
    alternative_names = Column(Text)
    nicknames = Column(Text)
    gender = Column(String)
    estimated_age = Column(String)
    body_type = Column(String)
    height_estimate = Column(String)
    face_geometry = Column(String)
    jaw_shape = Column(String)
    nose_shape = Column(String)
    eye_shape = Column(String)
    eye_color = Column(String)
    eyebrow_shape = Column(String)
    hair_style = Column(String)
    hair_length = Column(String)
    hair_color = Column(String)
    skin_tone = Column(String)
    body_proportions = Column(String)
    typical_expressions = Column(Text)
    typical_posture = Column(String)
    walking_style = Column(String)
    combat_style = Column(String)
    dominant_hand = Column(String)
    voice_personality = Column(String)
    speech_pattern = Column(Text)
    typical_emotions = Column(Text)
    favourite_expressions = Column(Text)
    typical_clothing = Column(Text)
    typical_armour = Column(Text)
    accessories = Column(Text)
    scars = Column(Text)
    tattoos = Column(Text)
    jewellery = Column(Text)
    weapons = Column(Text)
    magical_effects = Column(Text)
    forbidden_modifications = Column(Text)
    confidence_score = Column(Float)
    evidence_sources = Column(Text)
    version_number = Column(Integer, default=1)
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    scenes = relationship("SceneCharacter", back_populates="character")

class World(Base):
    """World Bible model"""
    __tablename__ = "worlds"
    
    id = Column(String, primary_key=True)
    novel_id = Column(String, nullable=False)
    history = Column(Text)
    geography = Column(Text)
    climate = Column(String)
    architecture = Column(Text)
    technology = Column(Text)
    magic = Column(Text)
    religion = Column(Text)
    politics = Column(Text)
    economy = Column(Text)
    transportation = Column(Text)
    food = Column(Text)
    currency = Column(String)
    military = Column(Text)
    culture = Column(Text)
    language = Column(String)
    symbols = Column(Text)
    animals = Column(Text)
    monsters = Column(Text)
    plants = Column(Text)
    clothing_styles = Column(Text)
    materials = Column(Text)
    lighting_style = Column(String)
    color_palette = Column(Text)
    visual_atmosphere = Column(String)
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Scene(Base):
    """Scene model"""
    __tablename__ = "scenes"
    
    id = Column(String, primary_key=True)
    novel_id = Column(String, nullable=False)
    chapter_number = Column(Integer)
    scene_number = Column(Integer)
    purpose = Column(Text)
    location_id = Column(String)
    time_of_day = Column(String)
    emotion = Column(String)
    conflict = Column(Text)
    importance = Column(String)
    beginning_text = Column(Text)
    ending_text = Column(Text)
    transition = Column(String)
    image_count = Column(Integer)
    audio_duration = Column(Float)
    video_duration = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    characters = relationship("SceneCharacter", back_populates="scene")

class SceneCharacter(Base):
    """Many-to-many relationship between scenes and characters"""
    __tablename__ = "scene_characters"
    
    scene_id = Column(String, ForeignKey("scenes.id"), primary_key=True)
    character_id = Column(String, ForeignKey("characters.id"), primary_key=True)
    role = Column(String)  # e.g., "protagonist", "antagonist", "supporting"
    
    scene = relationship("Scene", back_populates="characters")
    character = relationship("Character", back_populates="scenes")

class Novel(Base):
    """Novel metadata model"""
    __tablename__ = "novels"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    author = Column(String)
    genre = Column(String)
    word_count = Column(Integer)
    chapter_count = Column(Integer)
    file_path = Column(String)
    raw_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Project(Base):
    """Project tracking model"""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=True)
    novel_id = Column(String, ForeignKey("novels.id"), nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    progress = Column(Float, default=0.0)
    current_step = Column(String)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

class GeneratedImage(Base):
    """Generated image tracking"""
    __tablename__ = "generated_images"
    
    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False)
    image_path = Column(String, nullable=False)
    prompt_used = Column(Text)
    negative_prompt = Column(Text)
    seed = Column(Integer)
    score = Column(Float)
    is_selected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class GeneratedAudio(Base):
    """Generated audio tracking"""
    __tablename__ = "generated_audio"
    
    id = Column(String, primary_key=True)
    scene_id = Column(String, ForeignKey("scenes.id"), nullable=False)
    audio_path = Column(String, nullable=False)
    text_used = Column(Text)
    duration = Column(Float)
    emotion = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Checkpoint(Base):
    """Pipeline checkpoint"""
    __tablename__ = "checkpoints"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    step = Column(String, nullable=False)
    data = Column(Text)  # JSON data
    created_at = Column(DateTime, default=datetime.utcnow)