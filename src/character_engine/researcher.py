"""Character researcher for gathering evidence and building DNA"""
import logging
import json
import uuid
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.database import Database
from src.database.models import Character
from src.novel_analyzer.parser import Scene
from src.llm import OllamaClient

logger = logging.getLogger(__name__)


@dataclass
class CharacterEvidence:
    """Evidence for character DNA"""
    appearances: List[str]
    dialogues: List[str]
    actions: List[str]
    relationships: Dict[str, str]
    personality_traits: List[str]
    physical_descriptions: List[str]
    emotional_descriptions: List[str]
    combat_descriptions: List[str]
    titles: List[str]
    nicknames: List[str]


class CharacterResearcher:
    """Research characters and build Character DNA using LLM"""
    
    def __init__(self, config: Dict[str, Any], db: Database):
        self.config = config
        self.db = db
        self.llm = OllamaClient(config)
        
    async def research_characters(self, scenes: List[Scene]) -> List[Character]:
        """Research all characters in the scenes using LLM"""
        # Extract all unique character names
        all_characters = set()
        for scene in scenes:
            all_characters.update(scene.characters)
            
        characters = []
        for char_name in all_characters:
            try:
                # Collect regex-based evidence
                evidence = self._collect_evidence(char_name, scenes)
                
                # Use LLM to enhance character understanding
                llm_dna = await self.llm.build_character_dna(
                    char_name,
                    {
                        "appearances": evidence.appearances,
                        "dialogues": evidence.dialogues,
                        "physical_descriptions": evidence.physical_descriptions,
                        "personality_traits": evidence.personality_traits,
                        "actions": evidence.actions
                    }
                )
                
                # Build Character DNA combining regex and LLM
                character = self._build_character_dna(char_name, evidence, llm_dna)
                
                # Lock the character
                character.locked = True
                
                # Save to database
                with self.db.get_session() as session:
                    session.add(character)
                    session.commit()
                    session.refresh(character)  # Reload before detach
                    session.expunge(character)
                    
                characters.append(character)
                
                logger.info(f"Researched character: {char_name} (confidence: {(character.confidence_score or 0):.2f})")
                
            except Exception as e:
                logger.error(f"Error researching character {char_name}: {e}")
                continue
                
        logger.info(f"Researched {len(characters)} characters total")
        return characters
        
    def _collect_evidence(self, character_name: str, scenes: List[Scene]) -> CharacterEvidence:
        """Collect evidence for a character from scenes using regex"""
        appearances = []
        dialogues = []
        actions = []
        relationships = {}
        personality_traits = []
        physical_descriptions = []
        emotional_descriptions = []
        combat_descriptions = []
        titles = []
        nicknames = []
        
        for scene in scenes:
            if character_name in scene.characters:
                # Add scene appearance
                appearances.append(f"Chapter {scene.chapter_number}, Scene {scene.scene_number}")
                
                # Extract character-specific information from scene text
                char_text = self._extract_character_text(character_name, scene.text)
                
                if char_text:
                    dialogues.extend(self._extract_dialogues(character_name, char_text))
                    actions.extend(self._extract_actions(character_name, char_text))
                    relationships.update(self._extract_relationships(character_name, char_text))
                    personality_traits.extend(self._extract_personality(character_name, char_text))
                    physical_descriptions.extend(self._extract_physical(character_name, char_text))
                    emotional_descriptions.extend(self._extract_emotional(character_name, char_text))
                    combat_descriptions.extend(self._extract_combat(character_name, char_text))
                    titles.extend(self._extract_titles(character_name, char_text))
                    nicknames.extend(self._extract_nicknames(character_name, char_text))
        
        return CharacterEvidence(
            appearances=appearances,
            dialogues=dialogues,
            actions=actions,
            relationships=relationships,
            personality_traits=personality_traits,
            physical_descriptions=physical_descriptions,
            emotional_descriptions=emotional_descriptions,
            combat_descriptions=combat_descriptions,
            titles=titles,
            nicknames=nicknames
        )
        
    def _extract_character_text(self, character_name: str, scene_text: str) -> str:
        """Extract text related to a specific character"""
        paragraphs = scene_text.split('\n\n')
        char_paragraphs = [p for p in paragraphs if character_name in p]
        return '\n\n'.join(char_paragraphs)
        
    def _extract_dialogues(self, character_name: str, text: str) -> List[str]:
        """Extract dialogues spoken by the character"""
        dialogues = []
        patterns = [
            rf'{re.escape(character_name)}\s+(?:said|asked|replied|shouted|whispered|muttered|exclaimed|cried|yelled),?\s*"([^"]*)"',
            rf'"([^"]*)"\s*(?:said|asked|replied)\s+{re.escape(character_name)}',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dialogues.extend(matches)
        return dialogues[:10]
        
    def _extract_actions(self, character_name: str, text: str) -> List[str]:
        """Extract actions performed by the character"""
        actions = []
        pattern = rf'{re.escape(character_name)}\s+(went|ran|walked|jumped|flew|attacked|defended|used|held|carried|threw|caught|climbed|fought|killed|saved|helped|protected|battled)\s+([^.]*?)\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        actions.extend([f"{m[0]} {m[1]}" for m in matches])
        return actions[:10]
        
    def _extract_relationships(self, character_name: str, text: str) -> Dict[str, str]:
        """Extract relationships involving the character"""
        relationships = {}
        patterns = [
            rf'{re.escape(character_name)}(?:\'s|\s+(?:is|was))\s+(friend|enemy|brother|sister|father|mother|son|daughter|ally|rival)\s+(?:of\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                relationships[match[1]] = match[0]
        return relationships
        
    def _extract_personality(self, character_name: str, text: str) -> List[str]:
        """Extract personality traits"""
        traits = []
        trait_words = [
            'brave', 'cowardly', 'kind', 'cruel', 'intelligent', 'stupid',
            'loyal', 'treacherous', 'honest', 'deceitful', 'calm', 'angry',
            'patient', 'impulsive', 'generous', 'selfish', 'humble', 'proud'
        ]
        for trait in trait_words:
            if re.search(rf'{re.escape(character_name)}.*?{trait}', text, re.IGNORECASE):
                traits.append(trait)
        return list(set(traits))
        
    def _extract_physical(self, character_name: str, text: str) -> List[str]:
        """Extract physical descriptions"""
        descriptions = []
        patterns = [
            rf'{re.escape(character_name)}\s+(?:had|has|was|is)\s+(?:a |an )?([^.]*?)\.',
            rf'{re.escape(character_name)}\'s\s+([^.]*?)\.',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            descriptions.extend(matches)
        return descriptions[:5]
        
    def _extract_emotional(self, character_name: str, text: str) -> List[str]:
        """Extract emotional descriptions"""
        descriptions = []
        patterns = [
            rf'{re.escape(character_name)}\s+(?:felt|feels|was|is)\s+([^.]*?)\.',
            rf'{re.escape(character_name)}\s+(?:looked|looks)\s+([^.]*?)\.',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            descriptions.extend(matches)
        return descriptions[:5]
        
    def _extract_combat(self, character_name: str, text: str) -> List[str]:
        """Extract combat descriptions"""
        descriptions = []
        pattern = rf'{re.escape(character_name)}\s+(?:fought|attacked|defended|struck|dodged|parried|blocked|killed|defeated)\s+([^.]*?)\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        descriptions.extend(matches)
        return descriptions[:5]
        
    def _extract_titles(self, character_name: str, text: str) -> List[str]:
        """Extract titles"""
        titles = []
        pattern = rf'((?:King|Queen|Prince|Princess|Lord|Lady|Sir|Dame|Captain|General|Commander|Master|Professor|Doctor)\s+{re.escape(character_name)})'
        matches = re.findall(pattern, text, re.IGNORECASE)
        titles.extend(matches)
        return titles
        
    def _extract_nicknames(self, character_name: str, text: str) -> List[str]:
        """Extract nicknames"""
        nicknames = []
        patterns = [
            rf'(?:called|known as|nicknamed)\s+"([^"]*?)"',
            rf'"([^"]*?)"\s+(?:was|is)\s+(?:his|her|their)\s+(?:name|nickname)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            nicknames.extend(matches)
        return nicknames[:3]
        
    def _build_character_dna(
        self, 
        name: str, 
        evidence: CharacterEvidence, 
        llm_dna: Dict[str, Any]
    ) -> Character:
        """Build Character DNA combining regex evidence and LLM analysis"""
        # Calculate confidence score
        confidence = self._calculate_confidence(evidence)
        
        # Extract physical attributes from evidence
        physical = self._extract_physical_attributes(evidence.physical_descriptions)
        
        # Merge LLM data with regex data (LLM takes priority for quality)
        def get_val(key: str, default: str = "unknown") -> str:
            llm_val = llm_dna.get(key, default)
            if llm_val and llm_val != "unknown":
                return str(llm_val)
            return physical.get(key, default)

        def get_list(key: str, fallback: list = None) -> list:
            val = llm_dna.get(key)
            if isinstance(val, list):
                return val
            return fallback if fallback is not None else []

        def get_str_list(key: str, fallback: list = None) -> str:
            val = llm_dna.get(key)
            if isinstance(val, list):
                return json.dumps(val)
            if isinstance(val, str) and val:
                return json.dumps([val])
            return json.dumps(fallback if fallback is not None else [])

        character = Character(
            id=str(uuid.uuid4()),
            canonical_name=name,
            alternative_names=get_str_list("alternative_names"),
            nicknames=json.dumps(evidence.nicknames + get_list("nicknames")),
            gender=get_val("gender", self._infer_gender(name, evidence)),
            estimated_age=get_val("estimated_age", self._infer_age(evidence)),
            body_type=get_val("body_type", "average"),
            height_estimate=get_val("height", "average"),
            face_geometry=get_val("face_shape", "oval"),
            jaw_shape=get_val("jaw_shape", "average"),
            nose_shape=get_val("nose_shape", "average"),
            eye_shape=get_val("eye_shape", "average"),
            eye_color=get_val("eye_color", "unknown"),
            eyebrow_shape=get_val("eyebrow_shape", "average"),
            hair_style=get_val("hair_style", "average"),
            hair_length=get_val("hair_length", "medium"),
            hair_color=get_val("hair_color", "unknown"),
            skin_tone=get_val("skin_tone", "unknown"),
            body_proportions=get_val("proportions", "average"),
            typical_expressions=json.dumps(evidence.emotional_descriptions[:5]),
            typical_posture=self._infer_posture(evidence),
            walking_style=self._infer_walking_style(evidence),
            combat_style=get_val("combat_style", self._infer_combat_style(evidence)),
            dominant_hand="right",
            voice_personality=get_val("voice_personality", self._infer_voice(evidence)),
            speech_pattern=json.dumps(evidence.dialogues[:3]),
            typical_emotions=get_str_list("personality_traits", evidence.personality_traits[:5]),
            favourite_expressions=json.dumps(evidence.emotional_descriptions[:3]),
            typical_clothing=get_val("typical_clothing", "unknown"),
            typical_armour=get_val("typical_armour", "unknown"),
            accessories=get_val("accessories", "unknown"),
            scars=get_val("scars", "unknown"),
            tattoos=get_val("tattoos", "unknown"),
            jewellery=get_val("jewellery", "unknown"),
            weapons=get_str_list("weapons") if llm_dna.get("weapons") else self._infer_weapons(evidence),
            magical_effects=get_val("magical_effects", "unknown"),
            forbidden_modifications=json.dumps([
                "face_structure", "eye_color", "hair_color",
                "body_proportions", "artistic_style"
            ]),
            confidence_score=max(confidence, self._safe_float(llm_dna.get("confidence_score"), 0.5)),
            evidence_sources=json.dumps({
                "appearances": evidence.appearances[:5],
                "dialogues_count": len(evidence.dialogues),
                "actions_count": len(evidence.actions),
                "relationships_count": len(evidence.relationships),
                "llm_enhanced": bool(llm_dna)
            }),
            version_number=1
        )
        
        return character
        
    def _calculate_confidence(self, evidence: CharacterEvidence) -> float:
        """Calculate confidence score for character DNA"""
        score = 0.0
        score += min(len(evidence.appearances) * 0.1, 0.3)
        score += min(len(evidence.dialogues) * 0.05, 0.2)
        score += min(len(evidence.physical_descriptions) * 0.1, 0.2)
        score += min(len(evidence.personality_traits) * 0.05, 0.15)
        score += min(len(evidence.actions) * 0.05, 0.15)
        return min(score, 1.0)
        
    def _extract_physical_attributes(self, descriptions: List[str]) -> Dict[str, str]:
        """Extract physical attributes from descriptions"""
        attributes = {
            "body_type": "average", "height": "average", "face": "oval",
            "jaw": "average", "nose": "average", "eye_shape": "average",
            "eye_color": "unknown", "eyebrow": "average", "hair_style": "average",
            "hair_length": "medium", "hair_color": "unknown", "skin_tone": "unknown",
            "proportions": "average"
        }
        
        for desc in descriptions:
            desc_lower = desc.lower()
            for color in ['black', 'brown', 'blonde', 'red', 'blue', 'green', 'purple', 'white', 'gray']:
                if color in desc_lower:
                    attributes["hair_color"] = color
                    break
            for color in ['blue', 'green', 'brown', 'hazel', 'gray', 'amber', 'violet']:
                if color in desc_lower:
                    attributes["eye_color"] = color
                    break
            if 'tall' in desc_lower:
                attributes["height"] = "tall"
            elif 'short' in desc_lower:
                attributes["height"] = "short"
            if 'muscular' in desc_lower or 'strong' in desc_lower:
                attributes["body_type"] = "muscular"
            elif 'thin' in desc_lower or 'slim' in desc_lower:
                attributes["body_type"] = "thin"
            elif 'heavy' in desc_lower or 'large' in desc_lower:
                attributes["body_type"] = "heavy"
        return attributes
        
    def _infer_gender(self, name: str, evidence: CharacterEvidence) -> str:
        """Infer gender from name and evidence"""
        all_text = ' '.join(evidence.dialogues + evidence.actions).lower()
        male_count = sum(1 for w in ['he', 'him', 'his', 'man', 'boy', 'king', 'prince', 'lord'] if w in all_text)
        female_count = sum(1 for w in ['she', 'her', 'hers', 'woman', 'girl', 'queen', 'princess', 'lady'] if w in all_text)
        if male_count > female_count:
            return "male"
        elif female_count > male_count:
            return "female"
        return "unknown"
        
    def _infer_age(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.physical_descriptions + evidence.actions).lower()
        if any(w in all_text for w in ['young', 'boy', 'girl', 'child', 'teenager']):
            return "young"
        if any(w in all_text for w in ['old', 'elderly', 'ancient', 'venerable']):
            return "old"
        return "adult"
        
    def _infer_posture(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.physical_descriptions).lower()
        if any(w in all_text for w in ['straight', 'upright', 'tall', 'proud']):
            return "upright"
        if any(w in all_text for w in ['slouched', 'bent', 'curved', 'hunched']):
            return "slouched"
        return "upright"
        
    def _infer_walking_style(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.actions).lower()
        if any(w in all_text for w in ['confident', 'purposeful', 'determined']):
            return "confident"
        if any(w in all_text for w in ['agile', 'quick', 'swift', 'light']):
            return "agile"
        return "confident"
        
    def _infer_combat_style(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.combat_descriptions).lower()
        if any(w in all_text for w in ['aggressive', 'fierce', 'violent', 'brutal']):
            return "aggressive"
        if any(w in all_text for w in ['defensive', 'protective', 'shielding', 'blocking']):
            return "defensive"
        if any(w in all_text for w in ['tactical', 'strategic', 'clever', 'smart']):
            return "tactical"
        return "balanced"
        
    def _infer_voice(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.dialogues).lower()
        if any(w in all_text for w in ['deep', 'low', 'rumbling', 'booming']):
            return "deep"
        if any(w in all_text for w in ['soft', 'quiet', 'gentle', 'whispering']):
            return "soft"
        return "medium"
        
    def _infer_weapons(self, evidence: CharacterEvidence) -> str:
        all_text = ' '.join(evidence.combat_descriptions + evidence.actions).lower()
        weapons = [w for w in ['sword', 'axe', 'bow', 'spear', 'staff', 'wand', 'dagger', 'shield', 'hammer'] if w in all_text]
        return json.dumps(weapons) if weapons else "unarmed"

    @staticmethod
    def _safe_float(value, default: float = 0.5) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default