"""Phase 2 — Analysis: chapters, scenes, characters, world — with Arabic support."""
from __future__ import annotations
import json
import logging
import re
import uuid
from typing import List, Dict, Any

from .contracts import NovelText, Chapter, Scene, CharacterDNA, WorldBible
from src.llm import OllamaClient

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    pass


async def phase2_analysis(novel: NovelText, config: Dict[str, Any]) -> tuple[List[Chapter], List[Scene], List[CharacterDNA], WorldBible]:
    """Full analysis with hard gates at each sub-stage."""
    llm = OllamaClient(config)

    # ── Chapter splitting ──
    chapters = _split_chapters(novel)
    if not chapters:
        raise AnalysisError("No chapters found in text.")
    logger.info(f"Chapters: {len(chapters)}")

    # ── Scene segmentation ──
    all_scenes = []
    for ch in chapters:
        scenes = await _segment_scenes(ch, novel.language, llm)
        all_scenes.extend(scenes)
    if not all_scenes:
        raise AnalysisError("No meaningful scenes found.")
    logger.info(f"Scenes: {len(all_scenes)}")

    # ── Character extraction ──
    characters = await _extract_characters(all_scenes, novel, llm)
    if not characters:
        raise AnalysisError("No characters found.")
    logger.info(f"Characters: {len(characters)}")

    # ── World extraction ──
    world = await _extract_world(novel, all_scenes, llm)
    logger.info(f"World: {world.technology_level}, {world.visual_atmosphere}")

    return chapters, all_scenes, characters, world


# ─── Chapter splitting ────────────────────────────────────────────

def _split_chapters(novel: NovelText) -> List[Chapter]:
    text = novel.cleaned

    patterns = [
        r"(?:^|\n)\s*(?:Chapter|CHAPTER|الفصل)\s+(\d+|[IVXLC]+)",
        r"(?:^|\n)\s*\d+\.\s+[A-Z\u0600-\u06FF]",
    ]
    for pattern in patterns:
        splits = list(re.finditer(pattern, text))
        if len(splits) >= 2:
            chapters = []
            for i, match in enumerate(splits):
                start = match.start()
                end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
                ch_text = text[start:end].strip()
                if len(ch_text) > 100:
                    chapters.append(Chapter(
                        number=i + 1,
                        text=ch_text,
                        word_count=len(ch_text.split()),
                    ))
            if chapters:
                return chapters

    # Fallback: split by double newline at ~2000 word boundaries
    paragraphs = text.split("\n\n")
    chapters = []
    current = []
    word_count = 0
    for para in paragraphs:
        current.append(para)
        word_count += len(para.split())
        if word_count > 2000:
            ch_text = "\n\n".join(current).strip()
            if len(ch_text) > 100:
                chapters.append(Chapter(
                    number=len(chapters) + 1,
                    text=ch_text,
                    word_count=len(ch_text.split()),
                ))
            current = []
            word_count = 0
    if current:
        ch_text = "\n\n".join(current).strip()
        if len(ch_text) > 100:
            chapters.append(Chapter(
                number=len(chapters) + 1,
                text=ch_text,
                word_count=len(ch_text.split()),
            ))
    return chapters


# ─── Scene segmentation ───────────────────────────────────────────

async def _segment_scenes(chapter: Chapter, language: str, llm: OllamaClient) -> List[Scene]:
    paragraphs = chapter.text.split("\n\n")
    raw_segments = _merge_paragraphs(paragraphs)

    scenes = []
    for i, seg_text in enumerate(raw_segments):
        if len(seg_text.strip()) < 80:
            continue

        analysis = await _analyze_scene_llm(seg_text, chapter.number, i + 1, llm)

        scene = Scene(
            id=f"ch{chapter.number}_sc{i+1}",
            chapter_number=chapter.number,
            scene_number=i + 1,
            text=seg_text,
            summary=analysis.get("summary", seg_text[:120]),
            characters=_ensure_list(analysis.get("characters_present")),
            location=_ensure_str(analysis.get("location"), "unknown"),
            time_of_day=_ensure_str(analysis.get("time_of_day"), "unknown"),
            emotion=_ensure_str(analysis.get("emotion"), "neutral"),
            conflict=_ensure_str(analysis.get("conflict"), "none"),
            importance=_ensure_str(analysis.get("importance"), "normal"),
            dialogue_present=_has_dialogue(seg_text),
            action_present=_has_action(seg_text),
        )
        scenes.append(scene)

    return scenes


def _merge_paragraphs(paragraphs: List[str], max_chars: int = 1500) -> List[str]:
    segments = []
    current = []
    current_len = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        current.append(para)
        current_len += len(para)
        if current_len >= max_chars:
            segments.append("\n\n".join(current))
            current = []
            current_len = 0
    if current:
        segments.append("\n\n".join(current))
    return segments


async def _analyze_scene_llm(text: str, chapter: int, scene_num: int, llm: OllamaClient) -> Dict[str, Any]:
    prompt = f"""Analyze this scene from Chapter {chapter}, Scene {scene_num}.
Return ONLY a JSON object with these fields:
- summary: one sentence summary
- characters_present: list of character names
- location: where the scene takes place
- time_of_day: morning/afternoon/evening/night/unknown
- emotion: dominant emotion (one word)
- conflict: type of conflict or "none"
- importance: minor/normal/important/critical

Scene text:
{text[:2000]}"""

    response = await llm._generate(prompt, max_tokens=300)
    return llm._parse_json(response)


async def _extract_characters(scenes: List[Scene], novel: NovelText, llm: OllamaClient) -> List[CharacterDNA]:
    all_names = set()
    for scene in scenes:
        all_names.update(scene.characters)

    if not all_names:
        all_names = _regex_extract_names(novel.cleaned, novel.language)

    characters = []
    for name in all_names:
        evidence = _collect_evidence(name, scenes, novel.cleaned)

        llm_dna = await _llm_character_dna(name, evidence, llm)

        dna = CharacterDNA(
            id=str(uuid.uuid4()),
            canonical_name=name,
            gender=_safe_str(llm_dna.get("gender"), evidence.get("gender", "unknown")),
            estimated_age=_safe_str(llm_dna.get("estimated_age"), "unknown"),
            physical_description=_safe_str(llm_dna.get("physical_description"), ""),
            hair_color=llm_dna.get("hair_color"),
            eye_color=llm_dna.get("eye_color"),
            skin_tone=llm_dna.get("skin_tone"),
            height=llm_dna.get("height"),
            build=llm_dna.get("build"),
            clothing=_safe_str(llm_dna.get("typical_clothing"), ""),
            personality=evidence.get("traits", []),
            relationships=evidence.get("relationships", {}),
            weapons=evidence.get("weapons", []),
            confidence=evidence.get("confidence", 0.5),
            evidence=evidence.get("raw_evidence", []),
            inferred=evidence.get("inferred", []),
        )
        characters.append(dna)

    # Deduplicate: merge "Sir Aldric" → "Aldric", "Princess Elara" → "Elara"
    characters = _deduplicate_characters(characters)

    # Update scene character references to use canonical base names
    canonical_map = {}
    for c in characters:
        for sc in scenes:
            for cname in sc.characters:
                if _base_name(cname) == _base_name(c.canonical_name):
                    canonical_map[cname] = c.canonical_name
    for sc in scenes:
        sc.characters = [canonical_map.get(cn, cn) for cn in sc.characters]

    return characters


def _deduplicate_characters(characters: List[CharacterDNA]) -> List[CharacterDNA]:
    """Merge duplicate character entries (e.g. 'Sir Aldric' + 'Aldric')."""
    if len(characters) <= 1:
        return characters

    # Sort by confidence descending so the richest record is kept
    characters.sort(key=lambda c: c.confidence, reverse=True)

    merged = []
    seen = set()
    for c in characters:
        base_name = _base_name(c.canonical_name)
        if base_name in seen:
            # Merge into the existing entry
            existing = next(m for m in merged if _base_name(m.canonical_name) == base_name)
            existing.confidence = max(existing.confidence, c.confidence)
            if not existing.physical_description and c.physical_description:
                existing.physical_description = c.physical_description
            if not existing.hair_color and c.hair_color:
                existing.hair_color = c.hair_color
            if not existing.eye_color and c.eye_color:
                existing.eye_color = c.eye_color
            if c.weapons:
                existing.weapons = list(set(existing.weapons + c.weapons))
            existing.evidence = list(set(existing.evidence + c.evidence))
            # Update scenes to use canonical name
            for scene_chars in [s.characters for s in []]:
                pass
        else:
            seen.add(base_name)
            merged.append(c)

    return merged


def _base_name(name: str) -> str:
    """Strip titles and normalize for dedup: 'Sir Aldric' -> 'aldric', 'The King' -> 'king'."""
    prefixes = [
        "the ", "sir ", "king ", "queen ", "prince ", "princess ",
        "lord ", "lady ", "dr ", "professor ", "captain ", "general ",
    ]
    lower = name.strip().lower()
    for p in prefixes:
        if lower.startswith(p):
            lower = lower[len(p):]
    return lower.strip()


def _regex_extract_names(text: str, language: str) -> List[str]:
    names = set()
    if language == "ar":
        patterns = [
            r"[\u0627\u0644(?:)]+\s+[\u0627\u0644\u062a\u0631\u0627\u062a\u064a\u0628]+\s+[\u0627\u0644\u0639\u0631\u0628\u064a\u0629\u0627\u0644\u062a\u0623\u0631\u064a\u0643\u064a\u0629]+",
            r"[\u0627\u0644]+[\u0633\u064a\u062f]+\s+[\u0627\u0644]+[\u0639\u0644\u064a]+",
        ]
    else:
        patterns = [
            r"\b(Sir|King|Queen|Prince|Princess|Lord|Lady|Dr|Professor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"\b([A-Z][a-z]+)\s+(?:said|asked|replied|shouted|whispered|muttered|exclaimed)",
        ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(0).strip()
            if len(name) > 3:
                names.add(name)
    return list(names)[:20]


def _collect_evidence(name: str, scenes: List[Scene], full_text: str) -> Dict[str, Any]:
    appearances = []
    dialogues = []
    actions = []
    traits = []
    relationships = {}
    weapons = []
    raw_evidence = []
    inferred = []

    for scene in scenes:
        if name in scene.characters:
            appearances.append(f"Ch{scene.chapter_number} Sc{scene.scene_number}")
            char_text = _extract_char_paragraphs(name, scene.text)

            d = re.findall(
                rf'{re.escape(name)}[^"]*"([^"]*)"', char_text, re.IGNORECASE
            )
            dialogues.extend(d[:5])

            action_match = re.findall(
                rf'{re.escape(name)}\s+\w+\s+([^.]*?)\.', char_text, re.IGNORECASE
            )
            actions.extend([a.strip() for a in action_match[:5]])

            phys = re.findall(
                rf'{re.escape(name)}[^.]*?(hair|eyes|tall|short|brown|blue|golden|black|red|green|muscular|thin|slim)[^.]*\.',
                char_text, re.IGNORECASE
            )
            for p in phys:
                raw_evidence.append(p.strip())

    for trait_word in ["brave", "loyal", "kind", "cruel", "intelligent", "calm",
                        "proud", "humble", "wise", "foolish", "gentle", "fierce"]:
        if re.search(rf'\b{trait_word}\b', full_text, re.IGNORECASE):
            context = re.search(
                rf'[^.]*\b{name}\b[^.]*\b{trait_word}\b[^.]*\.', full_text, re.IGNORECASE
            )
            if context:
                traits.append(trait_word)

    relationship_patterns = [
        rf"{re.escape(name)}(?:'s|\s+(?:is|was))\s+(friend|enemy|brother|sister|father|mother|ally)\s+(?:of\s+)?([A-Z][a-z]+)",
    ]
    for pat in relationship_patterns:
        for m in re.finditer(pat, full_text, re.IGNORECASE):
            relationships[m.group(2)] = m.group(1)

    for w in ["sword", "axe", "bow", "spear", "staff", "wand", "dagger", "shield"]:
        if re.search(rf'\b{re.escape(name)}\b[^.]*\b{w}\b', full_text, re.IGNORECASE):
            weapons.append(w)

    confidence = min(1.0, len(appearances) * 0.15 + len(dialogues) * 0.1 + len(raw_evidence) * 0.1)

    gender = "unknown"
    gender_context = " ".join(dialogues + actions + raw_evidence).lower()
    if any(w in gender_context for w in ["he ", "him ", "his ", "king", "lord", "sir"]):
        gender = "male"
    elif any(w in gender_context for w in ["she ", "her ", "queen", "lady", "princess"]):
        gender = "female"

    return {
        "appearances": appearances,
        "dialogues": dialogues,
        "actions": actions,
        "traits": traits,
        "relationships": relationships,
        "weapons": weapons,
        "raw_evidence": raw_evidence,
        "confidence": confidence,
        "gender": gender,
        "inferred": inferred,
    }


def _extract_char_paragraphs(name: str, text: str) -> str:
    paragraphs = text.split("\n\n")
    return "\n\n".join(p for p in paragraphs if name.lower() in p.lower())


async def _llm_character_dna(name: str, evidence: Dict[str, Any], llm: OllamaClient) -> Dict[str, Any]:
    phys = evidence.get("raw_evidence", [])[:5]
    traits = evidence.get("traits", [])[:5]

    prompt = f"""Character: "{name}"
Physical clues from text: {json.dumps(phys)}
Personality traits: {json.dumps(traits)}

Return ONLY a JSON object with these fields (use null if not mentioned in text):
- gender: male/female/null
- physical_description: brief description or null
- hair_color: color or null
- eye_color: color or null
- skin_tone: description or null
- height: short/average/tall/null
- build: thin/average/muscular/null
- typical_clothing: description or null
- estimated_age: young/adult/old/null

Do NOT invent details. If the text does not mention a feature, use null."""

    response = await llm._generate(prompt, max_tokens=300)
    raw = llm._parse_json(response)
    if not isinstance(raw, dict):
        return {}
    return raw


async def _extract_world(novel: NovelText, scenes: List[Scene], llm: OllamaClient) -> WorldBible:
    locations = list(set(s.location for s in scenes if s.location != "unknown"))

    prompt = f"""Analyze this novel excerpt and extract world information.
Return ONLY a JSON object with:
- technology_level: stone_age/bronze/medieval/renaissance/industrial/modern/futuristic/magical
- architecture: brief description
- geography: brief description
- climate: brief description
- visual_atmosphere: dark/bright/mysterious/tense/peaceful/epic/warmer/colder
- color_palette: list of 3-5 dominant colors
- magic_system: description or "none"
- culture: brief description
- era_name: name for this era or "unknown"
- visual_keywords: list of 5-10 keywords for image generation

Locations found: {json.dumps(locations)}
Excerpt: {novel.cleaned[:2000]}"""

    response = await llm._generate(prompt, max_tokens=400)
    raw = llm._parse_json(response)

    if not isinstance(raw, dict):
        raw = {}

    safe = lambda k, d="unknown": raw.get(k) if raw.get(k) else d

    return WorldBible(
        id=str(uuid.uuid4()),
        technology_level=safe("technology_level", "medieval"),
        architecture=safe("architecture"),
        geography=safe("geography"),
        climate=safe("climate"),
        visual_atmosphere=safe("visual_atmosphere", "mysterious"),
        color_palette=raw.get("color_palette", []) if isinstance(raw.get("color_palette"), list) else [],
        magic_system=safe("magic_system", "none"),
        culture=safe("culture"),
        era_name=safe("era_name"),
        visual_keywords=raw.get("visual_keywords", []) if isinstance(raw.get("visual_keywords"), list) else [],
    )


def _ensure_str(val, default="unknown"):
    if isinstance(val, list):
        return val[0] if val else default
    if isinstance(val, str) and val:
        return val
    return default


def _ensure_list(val):
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val:
        return [val]
    return []


def _safe_str(val, default=""):
    if val is None:
        return default
    return str(val)


def _has_dialogue(text: str) -> bool:
    return bool(re.search(r'["\u0022\u0027\u2018\u2019\u201C\u201D\u060C].*["\u0022\u0027\u2018\u2019\u201C\u201D]', text))


def _has_action(text: str) -> bool:
    action_words = ["fought", "attacked", "defended", "ran", "jumped", "flew",
                    "struck", "killed", "saved", "fled", "charged", "rushed"]
    text_lower = text.lower()
    return any(w in text_lower for w in action_words)
