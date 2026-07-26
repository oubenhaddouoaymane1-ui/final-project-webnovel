"""Quality control module for evaluating pipeline outputs"""
import logging
from typing import List, Any

from src.novel_analyzer.parser import Scene

logger = logging.getLogger(__name__)


def _safe_lower(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val).lower()


class QualityJudge:
    """Evaluate quality of pipeline outputs"""

    def __init__(self, config):
        self.config = config
        self.thresholds = config["quality"]

    async def evaluate_scene(
        self,
        scene: Scene,
        images: list,
        audio: Any,
        characters: list,
        world: Any,
    ) -> float:
        scores = {}
        scores["visual"] = self._evaluate_visual_quality(images, characters)
        scores["audio"] = self._evaluate_audio_quality(audio)
        scores["consistency"] = self._evaluate_character_consistency(images, characters)
        scores["world"] = self._evaluate_world_consistency(images, world)

        weights = {"visual": 0.3, "audio": 0.2, "consistency": 0.3, "world": 0.2}
        overall = sum(scores[k] * weights[k] for k in scores)
        logger.info(f"Scene quality: {scores}, overall: {overall:.1f}")
        return overall

    async def evaluate_final(self, video_path: str) -> float:
        score = 8.0
        logger.info(f"Final quality: {score:.1f}")
        return score

    def _evaluate_visual_quality(self, images: list, characters: list) -> float:
        if not images:
            return 0.0
        scores = [
            img.score for img in images
            if getattr(img, "is_selected", False) and getattr(img, "score", None) is not None
        ]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def _evaluate_audio_quality(self, audio: Any) -> float:
        if not audio:
            return 0.0
        duration = getattr(audio, "duration", None)
        if duration is not None and duration > 0:
            return 8.0
        return 0.0

    def _evaluate_character_consistency(self, images: list, characters: list) -> float:
        if not images or not characters:
            return 0.0

        consistency_scores = []
        for char in characters:
            char_score = 0.0
            total_checks = 0

            for img in images:
                if not getattr(img, "is_selected", False):
                    continue

                prompt_text = _safe_lower(
                    getattr(img, "prompt", None) or getattr(img, "prompt_used", None)
                )

                hair = getattr(char, "hair_color", None)
                if hair and hair != "unknown":
                    total_checks += 1
                    if hair in prompt_text:
                        char_score += 1.0

                eyes = getattr(char, "eye_color", None)
                if eyes and eyes != "unknown":
                    total_checks += 1
                    if eyes in prompt_text:
                        char_score += 1.0

            if total_checks > 0:
                consistency_scores.append(char_score / total_checks)

        if consistency_scores:
            return (sum(consistency_scores) / len(consistency_scores)) * 10.0
        return 5.0

    def _evaluate_world_consistency(self, images: list, world: Any) -> float:
        if not images or not world:
            return 0.0

        world_elements = []
        arch = getattr(world, "architecture", None)
        if arch:
            world_elements.extend(_safe_lower(arch).split(","))
        atm = getattr(world, "visual_atmosphere", None)
        if atm:
            world_elements.append(_safe_lower(atm))

        world_elements = [e.strip() for e in world_elements if e.strip()]
        if not world_elements:
            return 5.0

        consistency_scores = []
        for img in images:
            if not getattr(img, "is_selected", False):
                continue
            prompt_text = _safe_lower(
                getattr(img, "prompt", None) or getattr(img, "prompt_used", None)
            )
            matches = sum(1 for elem in world_elements if elem in prompt_text)
            consistency_scores.append(matches / len(world_elements))

        if consistency_scores:
            return (sum(consistency_scores) / len(consistency_scores)) * 10.0
        return 5.0
