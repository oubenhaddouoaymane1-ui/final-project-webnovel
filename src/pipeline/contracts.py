"""Pipeline data contracts — typed dataclasses for every stage boundary."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class NovelText:
    raw: str
    cleaned: str
    title: str
    word_count: int
    char_count: int
    encoding: str
    language: str  # "en", "ar", "mixed"


@dataclass
class Chapter:
    number: int
    text: str
    word_count: int


@dataclass
class Scene:
    id: str
    chapter_number: int
    scene_number: int
    text: str
    summary: str
    characters: List[str] = field(default_factory=list)
    location: str = "unknown"
    time_of_day: str = "unknown"
    emotion: str = "neutral"
    conflict: str = "none"
    importance: str = "normal"
    dialogue_present: bool = False
    action_present: bool = False


@dataclass
class CharacterDNA:
    id: str
    canonical_name: str
    gender: str = "unknown"
    estimated_age: str = "unknown"
    physical_description: str = ""
    hair_color: Optional[str] = None
    eye_color: Optional[str] = None
    skin_tone: Optional[str] = None
    height: Optional[str] = None
    build: Optional[str] = None
    clothing: Optional[str] = None
    accessories: Optional[str] = None
    personality: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    weapons: List[str] = field(default_factory=list)
    voice_description: Optional[str] = None
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    inferred: List[str] = field(default_factory=list)


@dataclass
class WorldBible:
    id: str
    technology_level: str = "unknown"
    architecture: str = "unknown"
    geography: str = "unknown"
    climate: str = "unknown"
    visual_atmosphere: str = "unknown"
    color_palette: List[str] = field(default_factory=list)
    magic_system: str = "none"
    culture: str = "unknown"
    era_name: str = "unknown"
    visual_keywords: List[str] = field(default_factory=list)


@dataclass
class ShotPlan:
    shot_type: str  # establishing, wide, medium, close_up, extreme_close_up, action
    duration_seconds: float
    prompt: str
    negative_prompt: str
    transition: str = "fade"


@dataclass
class ScenePlan:
    scene_id: str
    shots: List[ShotPlan] = field(default_factory=list)
    narration_text: str = ""
    total_duration: float = 0.0


@dataclass
class GeneratedImage:
    scene_id: str
    shot_index: int
    image_path: str
    prompt: str
    backend_used: str
    seed: Optional[int] = None


@dataclass
class GeneratedAudio:
    scene_id: str
    audio_path: str
    text: str
    duration: float
    backend_used: str


@dataclass
class AssembledVideo:
    video_path: str
    duration: float
    scene_count: int
    resolution: str


@dataclass
class AuditReport:
    character_consistency_score: float
    world_consistency_score: float
    scene_alignment_score: float
    audio_sync_score: float
    novel_fidelity_score: float
    overall_score: float
    issues: List[str] = field(default_factory=list)
    compliance: Dict[str, bool] = field(default_factory=dict)


@dataclass
class PipelineResult:
    success: bool
    novel: Optional[NovelText] = None
    chapters: List[Chapter] = field(default_factory=list)
    scenes: List[Scene] = field(default_factory=list)
    characters: List[CharacterDNA] = field(default_factory=list)
    world: Optional[WorldBible] = None
    scene_plans: List[ScenePlan] = field(default_factory=list)
    images: List[GeneratedImage] = field(default_factory=list)
    audio: List[GeneratedAudio] = field(default_factory=list)
    video: Optional[AssembledVideo] = None
    audit: Optional[AuditReport] = None
    error: Optional[str] = None
    failed_stage: Optional[str] = None
