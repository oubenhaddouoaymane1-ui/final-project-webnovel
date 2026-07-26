"""Novel parser for splitting novels into chapters and scenes"""
import re
import logging
import uuid
from typing import List, Dict, Any

from src.llm import OllamaClient

logger = logging.getLogger(__name__)


class Scene:
    """Scene data structure"""
    def __init__(
        self,
        id: str,
        chapter_number: int,
        scene_number: int,
        text: str,
        purpose: str = "general",
        characters: List[str] = None,
        location: str = "unknown",
        time_of_day: str = "unknown",
        emotion: str = "neutral",
        conflict: str = "none",
        importance: str = "normal"
    ):
        self.id = id
        self.chapter_number = chapter_number
        self.scene_number = scene_number
        self.text = text
        self.purpose = purpose
        self.characters = characters or []
        self.location = location
        self.time_of_day = time_of_day
        self.emotion = emotion
        self.conflict = conflict
        self.importance = importance


class NovelParser:
    """Parse novels into chapters and scenes using LLM"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm = OllamaClient(config)
        
    def parse_chapters(self, novel_text: str) -> List[str]:
        """Split novel into chapters"""
        chapter_patterns = [
            r'Chapter\s+\d+',
            r'CHAPTER\s+\d+',
            r'Chapter\s+[IVXLC]+',
            r'CHAPTER\s+[IVXLC]+',
            r'\d+\.\s+[A-Z]',
        ]
        
        for pattern in chapter_patterns:
            chapters = re.split(pattern, novel_text)
            if len(chapters) > 1:
                logger.info(f"Found {len(chapters)} chapters using pattern: {pattern}")
                return [ch.strip() for ch in chapters if ch.strip()]
            
        # If no chapters found, split by paragraphs
        logger.info("No chapter patterns found, splitting by size")
        paragraphs = novel_text.split('\n\n')
        chapters = []
        current_chapter = []
        
        for para in paragraphs:
            current_chapter.append(para)
            if len('\n\n'.join(current_chapter)) > 5000:
                chapters.append('\n\n'.join(current_chapter))
                current_chapter = []
                
        if current_chapter:
            chapters.append('\n\n'.join(current_chapter))
            
        return chapters
        
    async def segment_scenes(self, chapter_text: str, chapter_number: int) -> List[Scene]:
        """Segment chapter into scenes using LLM for analysis"""
        # First do paragraph-based splitting
        raw_scenes = self._raw_segmentation(chapter_text)
        
        # Enhance each scene with LLM analysis
        scenes = []
        for i, scene_text in enumerate(raw_scenes):
            if len(scene_text.strip()) < 100:
                continue
                
            try:
                # Use LLM to analyze the scene
                analysis = await self.llm.analyze_scene(scene_text, chapter_number, i + 1)
                
                # Normalize LLM output: some fields may be lists instead of strings
                def _str(val, default="unknown"):
                    if isinstance(val, list):
                        return val[0] if val else default
                    if isinstance(val, str) and val:
                        return val
                    return default
                
                def _list(val):
                    if isinstance(val, list):
                        return [str(v) for v in val if v]
                    if isinstance(val, str) and val:
                        return [val]
                    return []
                
                scene = Scene(
                    id=f"ch{chapter_number}_sc{i+1}",
                    chapter_number=chapter_number,
                    scene_number=i + 1,
                    text=scene_text,
                    purpose=_str(analysis.get("purpose"), "general"),
                    characters=_list(analysis.get("characters_present")),
                    location=_str(analysis.get("location")),
                    time_of_day=_str(analysis.get("time_of_day")),
                    emotion=_str(analysis.get("emotion"), "neutral"),
                    conflict=_str(analysis.get("conflict"), "none"),
                    importance=_str(analysis.get("importance"), "normal")
                )
                
                scenes.append(scene)
                
            except Exception as e:
                logger.warning(f"LLM analysis failed for scene {i+1}, using defaults: {e}")
                # Fallback to regex-based analysis
                scene = self._create_fallback_scene(scene_text, chapter_number, i + 1)
                scenes.append(scene)
                
        logger.info(f"Chapter {chapter_number}: {len(scenes)} scenes created")
        return scenes
        
    def _raw_segmentation(self, chapter_text: str) -> List[str]:
        """Initial paragraph-based scene segmentation"""
        paragraphs = chapter_text.split('\n\n')
        scenes = []
        current_scene = []
        current_length = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            current_scene.append(para)
            current_length += len(para)
            
            # Scene break conditions
            is_break = False
            
            # Explicit break markers
            if para in ['* * *', '---', '***', '*** *** ***']:
                is_break = True
                
            # Time/location changes
            time_indicators = ['later', 'next day', 'morning', 'evening', 'night', 'hours later']
            location_indicators = ['arrived at', 'entered', 'left', 'went to', 'traveled to']
            
            para_lower = para.lower()
            for indicator in time_indicators + location_indicators:
                if indicator in para_lower:
                    is_break = True
                    break
                    
            # Length-based break
            if current_length > 1500:
                is_break = True
                
            if is_break and current_length > 200:
                scenes.append('\n\n'.join(current_scene))
                current_scene = []
                current_length = 0
                
        if current_scene:
            scenes.append('\n\n'.join(current_scene))
            
        return scenes
        
    def _create_fallback_scene(self, text: str, chapter_number: int, scene_number: int) -> Scene:
        """Create scene with fallback regex analysis"""
        characters = self._extract_characters(text)
        location = self._extract_location(text)
        time_of_day = self._extract_time(text)
        emotion = self._extract_emotion(text)
        conflict = self._extract_conflict(text)
        importance = self._calculate_importance(text)
        purpose = self._determine_purpose(text)
        
        return Scene(
            id=f"ch{chapter_number}_sc{scene_number}",
            chapter_number=chapter_number,
            scene_number=scene_number,
            text=text,
            purpose=purpose,
            characters=characters,
            location=location,
            time_of_day=time_of_day,
            emotion=emotion,
            conflict=conflict,
            importance=importance
        )
        
    def _extract_characters(self, text: str) -> List[str]:
        """Extract character names from text"""
        names = set()
        patterns = [
            r'[A-Z][a-z]+ [A-Z][a-z]+',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Filter common false positives
                if not any(w in match.lower() for w in ['the ', 'and ', 'but ', 'for ', 'not ']):
                    names.add(match)
        return list(names)[:10]
        
    def _extract_location(self, text: str) -> str:
        patterns = [r'in the ([A-Z][a-z]+)', r'at the ([A-Z][a-z]+)', r'inside the ([A-Z][a-z]+)']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return "unknown location"
        
    def _extract_time(self, text: str) -> str:
        text_lower = text.lower()
        for time, indicators in {
            'morning': ['morning', 'dawn', 'sunrise'],
            'afternoon': ['afternoon', 'midday', 'noon'],
            'evening': ['evening', 'dusk', 'sunset'],
            'night': ['night', 'midnight', 'dark']
        }.items():
            if any(i in text_lower for i in indicators):
                return time
        return "unknown time"
        
    def _extract_emotion(self, text: str) -> str:
        text_lower = text.lower()
        for emotion, indicators in {
            'joy': ['happy', 'joy', 'laugh', 'smile'],
            'sadness': ['sad', 'cry', 'tear', 'sorrow'],
            'anger': ['angry', 'rage', 'furious', 'shout'],
            'fear': ['afraid', 'fear', 'terrified', 'scared'],
            'surprise': ['surprised', 'shocked', 'astonished']
        }.items():
            if any(i in text_lower for i in indicators):
                return emotion
        return "neutral"
        
    def _extract_conflict(self, text: str) -> str:
        text_lower = text.lower()
        for indicator in ['battle', 'fight', 'argument', 'conflict', 'struggle', 'confront']:
            if indicator in text_lower:
                return f"character vs {indicator}"
        return "no explicit conflict"
        
    def _calculate_importance(self, text: str) -> str:
        text_lower = text.lower()
        importance_words = ['important', 'crucial', 'vital', 'decisive', 'climax', 'resolution']
        score = sum(1 for w in importance_words if w in text_lower) + len(text) / 2000
        if score > 3:
            return "critical"
        elif score > 2:
            return "important"
        elif score > 1:
            return "normal"
        return "minor"
        
    def _determine_purpose(self, text: str) -> str:
        text_lower = text.lower()
        for purpose, indicators in {
            'introduction': ['introduce', 'first time', 'meet', 'arrive'],
            'climax': ['climax', 'peak', 'highest'],
            'resolution': ['resolve', 'conclude', 'end']
        }.items():
            if any(i in text_lower for i in indicators):
                return purpose
        return "general"