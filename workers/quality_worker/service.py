import os
import uuid
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from workers.worker_base import WorkerBase

logger = logging.getLogger("cineos.quality_worker")

QUALITY_THRESHOLD = float(os.getenv("QUALITY_THRESHOLD", "0.6"))
REPAIR_THRESHOLD = float(os.getenv("REPAIR_THRESHOLD", "0.4"))
OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", os.getenv("OPENROUTER_API_KEY", ""))
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "openrouter")


class ReviewRequest(BaseModel):
    job_id: str
    asset_id: str
    asset_path: str
    asset_type: str = "image"
    review_criteria: Optional[List[str]] = None


class QualityWorker(WorkerBase):
    def __init__(self):
        super().__init__(
            name="quality-worker",
            worker_type="quality_review",
            job_types=["quality_review"],
            capabilities=["image_review", "video_review", "audio_review", "quality_scoring"],
            port=8200,
        )
        self.images_dir: str = os.getenv("IMAGES_DIR", "/data/images")
        self.review_results_dir: str = os.getenv("REVIEW_DIR", "/data/reviews")
        self.repair_job_queue: str = os.getenv("REPAIR_QUEUE", "repair_jobs")

        self._setup_quality_routes()

    def _setup_quality_routes(self):
        @self.app.post("/review")
        async def submit_review(req: ReviewRequest):
            job_id = str(uuid.uuid4())
            payload = req.dict()
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'quality_review', 'pending', 8, $2::jsonb)
                    """,
                    uuid.UUID(job_id),
                    json.dumps(payload),
                )
            return {"job_id": job_id, "status": "pending"}

        @self.app.get("/reviews/{review_id}")
        async def get_review(review_id: str):
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, job_id, asset_id, reviewer, overall_score,
                           feedback, details, created_at
                    FROM cineos_quality.reviews WHERE id = $1
                    """,
                    uuid.UUID(review_id),
                )
                if not row:
                    raise HTTPException(status_code=404, detail="Review not found")
                result = dict(row)
                result["id"] = str(result["id"])
                result["job_id"] = str(result["job_id"])
                return result

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job["payload"]
        asset_id = payload.get("asset_id", "")
        asset_path = payload.get("asset_path", "")
        asset_type = payload.get("asset_type", "image")
        criteria = payload.get("review_criteria") or [
            "technical_quality",
            "aesthetic_appeal",
            "content_appropriateness",
            "resolution_suitability",
            "color_balance",
        ]

        if not Path(asset_path).exists():
            raise FileNotFoundError(f"Asset not found: {asset_path}")

        vision_result = await self._analyze_with_vision_model(
            asset_path=asset_path,
            asset_type=asset_type,
            criteria=criteria,
        )

        scores = self._calculate_scores(vision_result, criteria)
        overall_score = scores.get("overall", 0.0)
        passed = overall_score >= QUALITY_THRESHOLD
        needs_repair = overall_score < REPAIR_THRESHOLD

        review_id = await self._store_review(
            job_id=job["id"],
            asset_id=asset_id,
            overall_score=overall_score,
            feedback=vision_result.get("feedback", ""),
            details={
                "scores": scores,
                "criteria": criteria,
                "vision_raw": vision_result,
                "asset_type": asset_type,
            },
        )

        for check_type, score in scores.items():
            await self._write_quality_check(
                job_id=job["id"],
                asset_id=asset_id,
                check_type=check_type,
                score=score,
                passed=score >= QUALITY_THRESHOLD,
                details={"review_id": review_id},
            )

        if needs_repair:
            await self._trigger_repair(job_id=job["id"], asset_id=asset_id, asset_path=asset_path, overall_score=overall_score, feedback=vision_result.get("feedback", ""))

        return {
            "review_id": review_id,
            "overall_score": overall_score,
            "scores": scores,
            "passed": passed,
            "needs_repair": needs_repair,
            "feedback": vision_result.get("feedback", ""),
        }

    async def _analyze_with_vision_model(
        self,
        asset_path: str,
        asset_type: str,
        criteria: List[str],
    ) -> Dict[str, Any]:
        prompt = self._build_review_prompt(asset_type, criteria)

        if asset_type == "image":
            image_data = Path(asset_path).read_bytes()
            image_b64 = __import__("base64").b64encode(image_data).decode("utf-8")
        else:
            image_b64 = ""

        if VISION_PROVIDER == "openrouter" or not OPENROUTER_KEY:
            return await self._openrouter_vision(prompt, image_b64)
        else:
            return await self._openrouter_vision(prompt, image_b64)

    def _build_review_prompt(self, asset_type: str, criteria: List[str]) -> str:
        criteria_text = "\n".join(f"- {c.replace('_', ' ').title()}" for c in criteria)
        return (
            f"You are a professional quality assurance reviewer for a cinematic production platform.\n\n"
            f"Analyze this {asset_type} and provide a detailed quality assessment.\n\n"
            f"Evaluate the following criteria:\n{criteria_text}\n\n"
            f"Return your assessment as JSON with the following structure:\n"
            f'{{\n'
            f'  "scores": {{\n'
            f'    "criteria_name": 0.0-1.0,\n'
            f'    ...\n'
            f'  }},\n'
            f'  "feedback": "detailed feedback text",\n'
            f'  "issues": ["list of specific issues found"],\n'
            f'  "recommendations": ["list of improvement recommendations"]\n'
            f'}}\n\n'
            f"Be precise and critical. Score 1.0 only for perfect quality."
        )

    async def _openrouter_vision(self, prompt: str, image_b64: str) -> Dict[str, Any]:
        messages = [{"role": "user", "content": []}]

        if image_b64:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            })

        messages[0]["content"].append({
            "type": "text",
            "text": prompt,
        })

        headers = {"Authorization": f"Bearer {OPENROUTER_KEY}"}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OPENROUTER_URL}/chat/completions",
                json={
                    "model": "openai/gpt-4o",
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._parse_vision_response(raw_text)

    def _parse_vision_response(self, raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {
                "scores": {"parse_error": 0.5},
                "feedback": raw_text,
                "issues": ["Could not parse structured response"],
                "recommendations": [],
            }

    def _calculate_scores(
        self, vision_result: Dict[str, Any], criteria: List[str]
    ) -> Dict[str, float]:
        raw_scores = vision_result.get("scores", {})
        scores: Dict[str, float] = {}

        for criterion in criteria:
            if criterion in raw_scores:
                val = raw_scores[criterion]
                if isinstance(val, (int, float)):
                    scores[criterion] = max(0.0, min(1.0, float(val)))
                else:
                    scores[criterion] = 0.5
            else:
                scores[criterion] = 0.5

        if scores:
            scores["overall"] = sum(scores.values()) / len(scores)
        else:
            scores["overall"] = 0.5

        return scores

    async def _store_review(
        self,
        job_id: str,
        asset_id: str,
        overall_score: float,
        feedback: str,
        details: Dict[str, Any],
    ) -> str:
        review_id = uuid.uuid4()
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cineos_quality.reviews
                    (id, job_id, asset_id, reviewer, overall_score, feedback, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                """,
                review_id,
                uuid.UUID(job_id),
                asset_id,
                "vision_model",
                overall_score,
                feedback,
                json.dumps(details),
            )
        return str(review_id)

    async def _trigger_repair(
        self,
        job_id: str,
        asset_id: str,
        asset_path: str,
        overall_score: float,
        feedback: str,
    ):
        repair_payload = {
            "original_job_id": job_id,
            "asset_id": asset_id,
            "asset_path": asset_path,
            "original_score": overall_score,
            "feedback": feedback,
            "repair_type": "image_regeneration",
        }

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.jobs (id, type, status, priority, payload)
                    VALUES ($1, 'image_regeneration', 'pending', 3, $2::jsonb)
                    """,
                    uuid.uuid4(),
                    json.dumps(repair_payload),
                )
            logger.info(
                "Repair job triggered for asset %s (score=%.2f)",
                asset_id,
                overall_score,
            )
        except Exception as exc:
            logger.error("Failed to trigger repair: %s", exc)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    worker = QualityWorker()
    worker.run()


if __name__ == "__main__":
    main()
