"""OpenRouter LLM integration for novel analysis — cloud-only, no local GPU."""
import json
import logging
import os
import asyncio
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", os.getenv("OPENROUTER_API_KEY", ""))


class OpenRouterLLMClient:
    """Client for OpenRouter cloud LLM — replaces local Ollama."""

    def __init__(self, config: Dict[str, Any]):
        llm_config = config.get("llm", {})
        openrouter = llm_config.get("openrouter", llm_config)
        self.model = openrouter.get("model", "meta-llama/llama-3.2-3b-instruct")
        self.temperature = openrouter.get("temperature", 0.5)
        self.max_tokens = openrouter.get("max_tokens", 4096)
        self.api_key = openrouter.get("api_key", "") or OPENROUTER_KEY

    async def analyze_characters(self, text: str) -> List[Dict[str, Any]]:
        prompt = f"""Analyze the following text and extract all characters.
For each character provide JSON with:
- name, gender, physical_description, personality_traits, relationships, role

Return a JSON array. Only JSON, no other text.

Text:
{text[:3000]}"""

        response = await self._generate(prompt, max_tokens=300)
        result = self._parse_json(response)
        return result if isinstance(result, list) else [result] if isinstance(result, dict) and result else []

    async def analyze_scene(self, scene_text: str, chapter: int, scene_num: int) -> Dict[str, Any]:
        prompt = f"""Analyze scene from Chapter {chapter}, Scene {scene_num}. Extract JSON with:
- purpose, emotion, conflict, time_of_day, location, characters_present, importance

Only JSON, no other text.

Scene text:
{scene_text[:2000]}"""

        response = await self._generate(prompt, max_tokens=300)
        return self._parse_json(response)

    async def build_character_dna(self, name: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""Character "{name}".
Physical: {json.dumps(evidence.get('physical_descriptions', [])[:3])}
Traits: {json.dumps(evidence.get('personality_traits', [])[:3])}

Return flat JSON string fields only:
canonical_name, gender, hair_color, eye_color, hair_style, hair_length,
skin_tone, face_shape, typical_clothing, combat_style, voice_personality,
weapons, confidence_score

Example: {{"canonical_name": "Aldric", "gender": "male", "hair_color": "brown", "eye_color": "blue"}}

Return ONLY the JSON object."""

        response = await self._generate(prompt, max_tokens=400)
        result = self._parse_json(response)
        return self._safe_dict(result)

    async def build_world(self, novel_excerpt: str, locations: List[str]) -> Dict[str, Any]:
        prompt = f"""Create a flat JSON object with these fields about this world.
ALL values must be short strings (not objects or arrays).

Locations: {json.dumps(locations)}
Excerpt: {novel_excerpt[:1500]}

Required flat string fields:
history, geography, climate, architecture, technology, magic,
religion, politics, economy, culture, visual_atmosphere, color_palette

Example: {{"technology": "medieval", "visual_atmosphere": "mysterious", "architecture": "stone castles"}}

Return ONLY the JSON object."""

        response = await self._generate(prompt, max_tokens=300)
        result = self._parse_json(response)
        return self._safe_dict(result)

    @staticmethod
    def _safe_dict(data: Any) -> Dict[str, str]:
        """Ensure all dict values are strings."""
        if not isinstance(data, dict):
            return {}
        return {k: (str(v) if v is not None else "") for k, v in data.items()}

    async def _generate(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate text using OpenRouter cloud API (no local GPU)."""
        if not self.api_key:
            logger.error("OpenRouter API key not configured — set OPENROUTER_KEY or OPENROUTER_API_KEY")
            return "{}"

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": min(max_tokens, self.max_tokens),
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{OPENROUTER_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        except Exception as e:
            logger.error(f"OpenRouter LLM error: {e}")
            return "{}"

    def _parse_json(self, text: str) -> Any:
        """Parse JSON from LLM response, handling common issues."""
        text = text.strip()

        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                text = text[start:end].strip()

        start_bracket = text.find("[")
        start_brace = text.find("{")

        if start_bracket == -1 and start_brace == -1:
            return {}

        if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
            end = text.rfind("]")
            if end != -1:
                try:
                    return json.loads(text[start_bracket : end + 1])
                except json.JSONDecodeError:
                    pass
        elif start_brace != -1:
            end = text.rfind("}")
            if end != -1:
                try:
                    return json.loads(text[start_brace : end + 1])
                except json.JSONDecodeError:
                    pass

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}")
            return {}
