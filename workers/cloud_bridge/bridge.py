"""
Cloud Worker Bridge — Dispatches heavy AI jobs to free cloud services.

Runs locally. Polls job queue. Sends HTTP to cloud APIs. Waits for results.
Connects a weak local PC to free cloud GPU power for image generation,
quality review, animation, and super-resolution.
"""

import os
import io
import uuid
import json
import time
import asyncio
import hashlib
import logging
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import deque
from urllib.parse import quote

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("cineos.cloud_bridge")

# ─── Configuration ────────────────────────────────────────────────────────────

DB_DSN: str = os.getenv("DATABASE_URL", "postgresql://cineos:cineos@localhost:5432/cineos")
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "5"))
HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
HEALTH_CHECK_INTERVAL: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
METRICS_FLUSH_INTERVAL: int = int(os.getenv("METRICS_FLUSH_INTERVAL", "60"))
JOB_TIMEOUT: int = int(os.getenv("JOB_TIMEOUT", "300"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

POLLINATIONS_BASE_URL: str = os.getenv("POLLINATIONS_URL", "https://image.pollinations.ai/prompt")
POLLINATIONS_RATE_LIMIT: int = int(os.getenv("POLLINATIONS_RATE_LIMIT", "10"))

HF_API_URL: str = os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models")
HF_API_KEY: str = os.getenv("HF_API_KEY", "")
HF_DEFAULT_MODEL: str = os.getenv("HF_DEFAULT_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")

OPENROUTER_URL: str = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1")
OPENROUTER_KEY: str = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_VISION_MODEL: str = os.getenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o")

IMAGES_DIR: str = os.getenv("IMAGES_DIR", "/data/images")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "/data/output")

CLOUD_JOB_TYPES: List[str] = os.getenv(
    "CLOUD_JOB_TYPES",
    "image_generation,quality_review,super_resolution,image_animation"
).split(",")

COLAB_WARMUP_INTERVAL: int = int(os.getenv("COLAB_WARMUP_INTERVAL", "240"))


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class ColabRegistrationRequest(BaseModel):
    name: str
    endpoint_url: str
    capabilities: List[str] = []
    api_key: Optional[str] = None
    job_types: List[str] = []


class ColabCallbackRequest(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ─── Cloud Backend Base ────────────────────────────────────────────────────────

class CloudBackend:
    """Base class for all cloud backends."""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    async def submit(self, payload: Dict[str, Any]) -> str:
        """Submit a job. Returns a task_id for polling."""
        raise NotImplementedError

    async def poll(self, task_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Poll for results. Returns (status, result).
        Status: 'pending', 'running', 'completed', 'failed'
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Return True if the backend is reachable."""
        return True


# ─── Pollinations Backend ─────────────────────────────────────────────────────

class PollinationsBackend(CloudBackend):
    """Image generation via pollinations.ai — no API key needed."""

    def __init__(self):
        super().__init__("pollinations")
        self._timestamps: deque = deque()
        self._rate_limit = POLLINATIONS_RATE_LIMIT

    def _check_rate_limit(self) -> bool:
        now = time.monotonic()
        while self._timestamps and self._timestamps[0] < now - 60:
            self._timestamps.popleft()
        return len(self._timestamps) < self._rate_limit

    async def submit(self, payload: Dict[str, Any]) -> str:
        if not self._check_rate_limit():
            raise RuntimeError("Pollinations rate limit exceeded (10/min)")

        prompt = payload.get("prompt", "")
        width = payload.get("width", 1024)
        height = payload.get("height", 1024)
        seed = payload.get("seed")
        if seed is None:
            seed = int.from_bytes(os.urandom(4), "big")
        model = payload.get("model", "flux")

        encoded_prompt = quote(prompt, safe="")
        url = f"{POLLINATIONS_BASE_URL}/{encoded_prompt}"
        params: Dict[str, Any] = {
            "width": width,
            "height": height,
            "nologo": "true",
            "seed": seed,
            "model": model,
        }

        self._timestamps.append(time.monotonic())

        task_id = str(uuid.uuid4())
        asyncio.create_task(
            self._fetch_image(task_id, url, params, payload)
        )
        return task_id

    async def _fetch_image(
        self,
        task_id: str,
        url: str,
        params: Dict[str, Any],
        original_payload: Dict[str, Any],
    ):
        """Background task that fetches the image and stores the result."""
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "image" not in content_type:
                    raise RuntimeError(f"Non-image response: {content_type}")

                image_bytes = resp.content

            image_id = str(uuid.uuid4())
            images_dir = Path(IMAGES_DIR)
            images_dir.mkdir(parents=True, exist_ok=True)
            image_path = images_dir / f"{image_id}.png"
            image_path.write_bytes(image_bytes)

            checksum = hashlib.sha256(image_bytes).hexdigest()
            _PENDING_RESULTS[task_id] = {
                "status": "completed",
                "result": {
                    "image_id": image_id,
                    "image_path": str(image_path),
                    "source": "pollinations",
                    "width": original_payload.get("width", 1024),
                    "height": original_payload.get("height", 1024),
                    "seed": params.get("seed"),
                    "checksum": checksum,
                    "file_size_bytes": len(image_bytes),
                },
            }
        except Exception as exc:
            logger.error("Pollinations task %s failed: %s", task_id, exc)
            _PENDING_RESULTS[task_id] = {
                "status": "failed",
                "error": str(exc),
            }

    async def poll(self, task_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        entry = _PENDING_RESULTS.get(task_id)
        if entry is None:
            return "pending", None
        if entry["status"] == "completed":
            del _PENDING_RESULTS[task_id]
            return "completed", entry["result"]
        if entry["status"] == "failed":
            del _PENDING_RESULTS[task_id]
            return "failed", {"error": entry.get("error", "unknown")}
        return entry["status"], None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://image.pollinations.ai/prompt/test")
                return resp.status_code in (200, 429)
        except Exception:
            return False


# ─── HuggingFace Backend ──────────────────────────────────────────────────────

class HuggingFaceBackend(CloudBackend):
    """Image generation via HuggingFace Inference API — free tier."""

    def __init__(self):
        super().__init__("huggingface")
        self._api_key = HF_API_KEY
        self._api_url = HF_API_URL

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def submit(self, payload: Dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        model = payload.get("model", HF_DEFAULT_MODEL)
        prompt = payload.get("prompt", "")
        negative_prompt = payload.get("negative_prompt", "")
        width = payload.get("width", 1024)
        height = payload.get("height", 1024)
        steps = payload.get("steps", 30)
        guidance_scale = payload.get("cfg_scale", 7.0)
        seed = payload.get("seed")
        if seed is None:
            seed = int.from_bytes(os.urandom(4), "big")

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt} ### {negative_prompt}"

        body: Dict[str, Any] = {
            "inputs": full_prompt,
            "parameters": {
                "width": width,
                "height": height,
                "num_inference_steps": steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
            },
        }

        asyncio.create_task(
            self._inference_request(task_id, model, body, payload)
        )
        return task_id

    async def _inference_request(
        self,
        task_id: str,
        model: str,
        body: Dict[str, Any],
        original_payload: Dict[str, Any],
    ):
        try:
            url = f"{self._api_url}/{model}"
            max_retries = 3
            image_bytes: Optional[bytes] = None

            async with httpx.AsyncClient(timeout=120) as client:
                for attempt in range(max_retries):
                    resp = await client.post(url, json=body, headers=self._headers())

                    if resp.status_code == 503:
                        wait_time = resp.json().get("estimated_time", 10)
                        logger.info(
                            "HF model loading, waiting %.0fs (attempt %d/%d)",
                            wait_time, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(min(wait_time, 30))
                        continue

                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")

                    if "image" in content_type:
                        image_bytes = resp.content
                        break
                    elif "application/json" in content_type:
                        data = resp.json()
                        if "error" in data:
                            raise RuntimeError(f"HF error: {data['error']}")
                        image_b64 = data.get("images", [None])[0]
                        if image_b64:
                            image_bytes = base64.b64decode(image_b64)
                            break
                    else:
                        raise RuntimeError(f"Unexpected content type: {content_type}")

            if image_bytes is None:
                raise RuntimeError("Failed to get image from HF after retries")

            image_id = str(uuid.uuid4())
            images_dir = Path(IMAGES_DIR)
            images_dir.mkdir(parents=True, exist_ok=True)
            image_path = images_dir / f"{image_id}.png"
            image_path.write_bytes(image_bytes)

            checksum = hashlib.sha256(image_bytes).hexdigest()
            _PENDING_RESULTS[task_id] = {
                "status": "completed",
                "result": {
                    "image_id": image_id,
                    "image_path": str(image_path),
                    "source": "huggingface",
                    "model": model,
                    "width": original_payload.get("width", 1024),
                    "height": original_payload.get("height", 1024),
                    "seed": body["parameters"].get("seed"),
                    "checksum": checksum,
                    "file_size_bytes": len(image_bytes),
                },
            }
        except Exception as exc:
            logger.error("HF task %s failed: %s", task_id, exc)
            _PENDING_RESULTS[task_id] = {
                "status": "failed",
                "error": str(exc),
            }

    async def poll(self, task_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        entry = _PENDING_RESULTS.get(task_id)
        if entry is None:
            return "pending", None
        if entry["status"] == "completed":
            del _PENDING_RESULTS[task_id]
            return "completed", entry["result"]
        if entry["status"] == "failed":
            del _PENDING_RESULTS[task_id]
            return "failed", {"error": entry.get("error", "unknown")}
        return entry["status"], None

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = self._headers()
                resp = await client.get(
                    "https://huggingface.co/api/models/stabilityai/stable-diffusion-xl-base-1.0",
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception:
            return False


# ─── OpenRouter Vision Backend ────────────────────────────────────────────────

class OpenRouterVisionBackend(CloudBackend):
    """Quality review via OpenRouter vision models — sends images as base64."""

    def __init__(self):
        super().__init__("openrouter_vision")
        self._api_key = OPENROUTER_KEY
        self._model = OPENROUTER_VISION_MODEL

    async def submit(self, payload: Dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        asyncio.create_task(self._vision_request(task_id, payload))
        return task_id

    async def _vision_request(
        self,
        task_id: str,
        payload: Dict[str, Any],
    ):
        try:
            image_path = payload.get("image_path", "")
            asset_type = payload.get("asset_type", "image")
            criteria = payload.get("review_criteria") or [
                "technical_quality",
                "aesthetic_appeal",
                "content_appropriateness",
                "resolution_suitability",
                "color_balance",
                "composition",
            ]

            criteria_text = "\n".join(
                f"- {c.replace('_', ' ').title()}" for c in criteria
            )
            prompt = (
                "You are a professional quality assurance reviewer for a cinematic "
                "production platform.\n\n"
                f"Analyze this {asset_type} and provide a detailed quality assessment.\n\n"
                "Evaluate the following criteria:\n"
                f"{criteria_text}\n\n"
                "Return your assessment as JSON with this structure:\n"
                "{\n"
                '  "scores": {"criteria_name": 0.0-1.0, ...},\n'
                '  "feedback": "detailed feedback text",\n'
                '  "issues": ["specific issues found"],\n'
                '  "recommendations": ["improvement recommendations"]\n'
                "}\n\n"
                "Be precise and critical. Score 1.0 only for perfect quality."
            )

            image_b64 = ""
            if image_path and Path(image_path).exists():
                image_bytes = Path(image_path).read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            elif payload.get("image_base64"):
                image_b64 = payload["image_base64"]

            messages: List[Dict[str, Any]] = [{"role": "user", "content": []}]
            if image_b64:
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                })
            messages[0]["content"].append({
                "type": "text",
                "text": prompt,
            })

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{OPENROUTER_URL}/chat/completions",
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            raw_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            parsed = _parse_vision_response(raw_text)

            scores = parsed.get("scores", {})
            criteria_scores: Dict[str, float] = {}
            for c in criteria:
                if c in scores and isinstance(scores[c], (int, float)):
                    criteria_scores[c] = max(0.0, min(1.0, float(scores[c])))
                else:
                    criteria_scores[c] = 0.5
            if criteria_scores:
                criteria_scores["overall"] = sum(criteria_scores.values()) / len(criteria_scores)
            else:
                criteria_scores["overall"] = 0.5

            overall = criteria_scores["overall"]
            _PENDING_RESULTS[task_id] = {
                "status": "completed",
                "result": {
                    "scores": criteria_scores,
                    "overall_score": overall,
                    "passed": overall >= 0.6,
                    "feedback": parsed.get("feedback", ""),
                    "issues": parsed.get("issues", []),
                    "recommendations": parsed.get("recommendations", []),
                    "reviewer_model": self._model,
                },
            }
        except Exception as exc:
            logger.error("OpenRouter vision task %s failed: %s", task_id, exc)
            _PENDING_RESULTS[task_id] = {
                "status": "failed",
                "error": str(exc),
            }

    async def poll(self, task_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        entry = _PENDING_RESULTS.get(task_id)
        if entry is None:
            return "pending", None
        if entry["status"] == "completed":
            del _PENDING_RESULTS[task_id]
            return "completed", entry["result"]
        if entry["status"] == "failed":
            del _PENDING_RESULTS[task_id]
            return "failed", {"error": entry.get("error", "unknown")}
        return entry["status"], None

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{OPENROUTER_URL}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


# ─── Colab Backend ────────────────────────────────────────────────────────────

class ColabBackend(CloudBackend):
    """Generic Colab backend for ComfyUI, ESRGAN, LivePortrait, Kokoro.

    Colab endpoints are registered dynamically. The bridge polls them for
    readiness, submits jobs via HTTP POST, and long-polls for results.
    """

    def __init__(self):
        super().__init__("colab")
        self._endpoints: Dict[str, Dict[str, Any]] = {}
        self._active_tasks: Dict[str, Dict[str, Any]] = {}

    def register_endpoint(
        self,
        name: str,
        endpoint_url: str,
        capabilities: List[str],
        api_key: Optional[str] = None,
        job_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        ep_id = str(uuid.uuid4())
        self._endpoints[ep_id] = {
            "id": ep_id,
            "name": name,
            "endpoint_url": endpoint_url.rstrip("/"),
            "capabilities": capabilities,
            "api_key": api_key,
            "job_types": job_types or [],
            "status": "registered",
            "last_health_check": None,
            "healthy": False,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "last_warmup": None,
        }
        logger.info("Registered Colab endpoint '%s' at %s", name, endpoint_url)
        return self._endpoints[ep_id]

    def deregister_endpoint(self, endpoint_id: str) -> bool:
        if endpoint_id in self._endpoints:
            name = self._endpoints[endpoint_id]["name"]
            del self._endpoints[endpoint_id]
            logger.info("Deregistered Colab endpoint '%s'", name)
            return True
        return False

    def get_endpoints(self) -> List[Dict[str, Any]]:
        return list(self._endpoints.values())

    def _find_endpoint_for_job(self, job_type: str) -> Optional[Dict[str, Any]]:
        for ep in self._endpoints.values():
            if not ep["healthy"]:
                continue
            if ep["job_types"] and job_type not in ep["job_types"]:
                continue
            return ep
        for ep in self._endpoints.values():
            if not ep["job_types"]:
                return ep
        return None

    async def submit(self, payload: Dict[str, Any]) -> str:
        job_type = payload.get("cloud_job_type", "image_generation")
        ep = self._find_endpoint_for_job(job_type)
        if ep is None:
            raise RuntimeError(
                f"No healthy Colab endpoint available for job type '{job_type}'"
            )

        task_id = str(uuid.uuid4())
        self._active_tasks[task_id] = {
            "endpoint_id": ep["id"],
            "endpoint_url": ep["endpoint_url"],
            "submitted_at": time.monotonic(),
        }

        asyncio.create_task(
            self._colab_request(task_id, ep, payload, job_type)
        )
        return task_id

    async def _colab_request(
        self,
        task_id: str,
        endpoint: Dict[str, Any],
        payload: Dict[str, Any],
        job_type: str,
    ):
        try:
            url = endpoint["endpoint_url"]
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if endpoint.get("api_key"):
                headers["Authorization"] = f"Bearer {endpoint['api_key']}"

            submit_payload = {
                "task_id": task_id,
                "job_type": job_type,
                "payload": payload,
            }

            timeout = min(JOB_TIMEOUT, 300)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{url}/job",
                    json=submit_payload,
                    headers=headers,
                )
                resp.raise_for_status()
                result_data = resp.json()

            if result_data.get("status") == "completed":
                _PENDING_RESULTS[task_id] = {
                    "status": "completed",
                    "result": result_data.get("result", {}),
                }
            elif result_data.get("status") == "processing":
                _PENDING_RESULTS[task_id] = {
                    "status": "running",
                    "result": None,
                }
                asyncio.create_task(
                    self._poll_colab_result(task_id, endpoint, timeout)
                )
            else:
                _PENDING_RESULTS[task_id] = {
                    "status": "completed",
                    "result": result_data.get("result", result_data),
                }

        except httpx.ConnectError:
            logger.error("Colab endpoint offline: %s", endpoint["name"])
            endpoint["healthy"] = False
            _PENDING_RESULTS[task_id] = {
                "status": "failed",
                "error": f"Colab endpoint '{endpoint['name']}' is offline",
            }
        except Exception as exc:
            logger.error("Colab task %s failed: %s", task_id, exc)
            _PENDING_RESULTS[task_id] = {
                "status": "failed",
                "error": str(exc),
            }
        finally:
            self._active_tasks.pop(task_id, None)

    async def _poll_colab_result(
        self,
        task_id: str,
        endpoint: Dict[str, Any],
        timeout: int,
    ):
        url = endpoint["endpoint_url"]
        headers: Dict[str, str] = {}
        if endpoint.get("api_key"):
            headers["Authorization"] = f"Bearer {endpoint['api_key']}"

        start = time.monotonic()
        poll_interval = 5.0

        async with httpx.AsyncClient(timeout=30) as client:
            while time.monotonic() - start < timeout:
                await asyncio.sleep(poll_interval)
                try:
                    resp = await client.get(
                        f"{url}/status/{task_id}",
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    status = data.get("status", "running")

                    if status == "completed":
                        _PENDING_RESULTS[task_id] = {
                            "status": "completed",
                            "result": data.get("result", {}),
                        }
                        return
                    elif status == "failed":
                        _PENDING_RESULTS[task_id] = {
                            "status": "failed",
                            "error": data.get("error", "Colab task failed"),
                        }
                        return

                except httpx.ConnectError:
                    logger.warning("Colab disconnected during polling for task %s", task_id)
                    endpoint["healthy"] = False
                    _PENDING_RESULTS[task_id] = {
                        "status": "failed",
                        "error": "Colab disconnected during processing",
                    }
                    return
                except Exception:
                    continue

        _PENDING_RESULTS[task_id] = {
            "status": "failed",
            "error": f"Colab task timed out after {timeout}s",
        }

    async def poll(self, task_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        entry = _PENDING_RESULTS.get(task_id)
        if entry is None:
            return "pending", None
        if entry["status"] == "completed":
            del _PENDING_RESULTS[task_id]
            return "completed", entry["result"]
        if entry["status"] == "failed":
            del _PENDING_RESULTS[task_id]
            return "failed", {"error": entry.get("error", "unknown")}
        return entry["status"], None

    async def health_check_all(self):
        for ep in self._endpoints.values():
            try:
                url = ep["endpoint_url"]
                headers: Dict[str, str] = {}
                if ep.get("api_key"):
                    headers["Authorization"] = f"Bearer {ep['api_key']}"

                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{url}/health", headers=headers)
                    was_healthy = ep["healthy"]
                    ep["healthy"] = resp.status_code == 200
                    ep["last_health_check"] = datetime.now(timezone.utc).isoformat()
                    if ep["healthy"] and not was_healthy:
                        logger.info("Colab endpoint '%s' is back online", ep["name"])
                    elif not ep["healthy"] and was_healthy:
                        logger.warning("Colab endpoint '%s' went offline", ep["name"])
            except Exception:
                was_healthy = ep["healthy"]
                ep["healthy"] = False
                ep["last_health_check"] = datetime.now(timezone.utc).isoformat()
                if was_healthy:
                    logger.warning("Colab endpoint '%s' went offline", ep["name"])

    async def send_warmup(self):
        for ep in self._endpoints.values():
            if not ep["healthy"]:
                continue
            try:
                url = ep["endpoint_url"]
                headers: Dict[str, str] = {}
                if ep.get("api_key"):
                    headers["Authorization"] = f"Bearer {ep['api_key']}"

                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{url}/warmup", headers=headers)
                    if resp.status_code == 200:
                        ep["last_warmup"] = datetime.now(timezone.utc).isoformat()
            except Exception:
                pass

    async def health_check(self) -> bool:
        return len(self._endpoints) > 0 and any(
            ep["healthy"] for ep in self._endpoints.values()
        )


# ─── Bridge Metrics ───────────────────────────────────────────────────────────

@dataclass
class BridgeMetrics:
    jobs_dispatched: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_retried: int = 0
    total_latency_ms: float = 0.0
    cloud_errors: int = 0
    colab_disconnects: int = 0
    backend_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    last_dispatch_time: Optional[datetime] = None
    last_completion_time: Optional[datetime] = None
    recent_errors: List[Dict[str, Any]] = field(default_factory=list)

    def record_dispatch(self, backend: str):
        self.jobs_dispatched += 1
        self.last_dispatch_time = datetime.now(timezone.utc)
        if backend not in self.backend_stats:
            self.backend_stats[backend] = {"dispatched": 0, "completed": 0, "failed": 0}
        self.backend_stats[backend]["dispatched"] += 1

    def record_completion(self, backend: str, latency_ms: float):
        self.jobs_completed += 1
        self.total_latency_ms += latency_ms
        self.last_completion_time = datetime.now(timezone.utc)
        if backend in self.backend_stats:
            self.backend_stats[backend]["completed"] += 1

    def record_failure(self, backend: str, error: str):
        self.jobs_failed += 1
        if backend in self.backend_stats:
            self.backend_stats[backend]["failed"] += 1
        self.recent_errors.append({
            "backend": backend,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.recent_errors) > 50:
            self.recent_errors = self.recent_errors[-50:]

    def record_cloud_error(self):
        self.cloud_errors += 1

    def record_colab_disconnect(self):
        self.colab_disconnects += 1

    def avg_latency(self) -> float:
        if self.jobs_completed == 0:
            return 0.0
        return self.total_latency_ms / self.jobs_completed

    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uptime_seconds": round(self.uptime_seconds(), 2),
            "jobs_dispatched": self.jobs_dispatched,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "jobs_retried": self.jobs_retried,
            "avg_latency_ms": round(self.avg_latency(), 2),
            "cloud_errors": self.cloud_errors,
            "colab_disconnects": self.colab_disconnects,
            "backend_stats": dict(self.backend_stats),
            "last_dispatch": self.last_dispatch_time.isoformat() if self.last_dispatch_time else None,
            "last_completion": self.last_completion_time.isoformat() if self.last_completion_time else None,
            "recent_errors": self.recent_errors[-5:],
        }


# ─── Global State ─────────────────────────────────────────────────────────────

_PENDING_RESULTS: Dict[str, Dict[str, Any]] = {}

BRIDGE_ID = str(uuid.uuid4())


# ─── Helper Functions ─────────────────────────────────────────────────────────

def _parse_vision_response(raw_text: str) -> Dict[str, Any]:
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
            "scores": {},
            "feedback": raw_text,
            "issues": ["Could not parse structured response"],
            "recommendations": [],
        }


# ─── Cloud Worker Bridge ──────────────────────────────────────────────────────

class CloudWorkerBridge:
    """Main bridge service — polls job queue, dispatches to cloud, collects results."""

    def __init__(self):
        self.app = FastAPI(title="CineOS Cloud Worker Bridge", version="1.0.0")
        self.db_pool: Optional[asyncpg.Pool] = None
        self.metrics = BridgeMetrics()
        self.status = "starting"

        self._shutdown_event = asyncio.Event()
        self._poll_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        self._warmup_task: Optional[asyncio.Task] = None

        self._processing_lock = asyncio.Lock()
        self._inflight: Dict[str, Dict[str, Any]] = {}

        self.backends: Dict[str, CloudBackend] = {}
        self._job_backend_map: Dict[str, str] = {}

        self._setup_routes()
        self._setup_lifecycle()

    def _register_backends(self):
        self.backends["pollinations"] = PollinationsBackend()
        self.backends["huggingface"] = HuggingFaceBackend()
        self.backends["openrouter_vision"] = OpenRouterVisionBackend()
        self.backends["colab"] = ColabBackend()

        self._job_backend_map = {
            "image_generation": "pollinations",
            "quality_review": "openrouter_vision",
            "super_resolution": "colab",
            "image_animation": "colab",
        }

    def _select_backend(self, job_type: str, payload: Dict[str, Any]) -> CloudBackend:
        preferred = self._job_backend_map.get(job_type)

        if preferred and preferred in self.backends:
            backend = self.backends[preferred]
            if backend.enabled and isinstance(backend, ColabBackend):
                colab: ColabBackend = backend
                ep = colab._find_endpoint_for_job(job_type)
                if ep is not None:
                    return backend
            elif backend.enabled:
                return backend

        if job_type == "image_generation":
            if self.backends["huggingface"].enabled:
                return self.backends["huggingface"]
            return self.backends["pollinations"]

        if job_type == "quality_review":
            return self.backends["openrouter_vision"]

        if job_type in ("super_resolution", "image_animation"):
            colab_backend = self.backends["colab"]
            if colab_backend.enabled:
                return colab_backend

        for backend in self.backends.values():
            if backend.enabled:
                return backend

        raise RuntimeError(f"No available backend for job type '{job_type}'")

    # ── Routes ────────────────────────────────────────────────────────────

    def _setup_routes(self):
        @self.app.get("/health")
        async def health_check():
            db_ok = False
            if self.db_pool:
                try:
                    async with self.db_pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    db_ok = True
                except Exception:
                    pass

            backend_health: Dict[str, bool] = {}
            for name, backend in self.backends.items():
                try:
                    backend_health[name] = backend.enabled
                except Exception:
                    backend_health[name] = False

            colab_endpoints: List[Dict[str, Any]] = []
            colab = self.backends.get("colab")
            if isinstance(colab, ColabBackend):
                colab_endpoints = colab.get_endpoints()

            return JSONResponse(
                status_code=200 if (self.status == "healthy" and db_ok) else 503,
                content={
                    "status": self.status,
                    "bridge_id": BRIDGE_ID,
                    "database_connected": db_ok,
                    "backends": backend_health,
                    "colab_endpoints": len(colab_endpoints),
                    "inflight_jobs": len(self._inflight),
                    "metrics": self.metrics.to_dict(),
                },
            )

        @self.app.get("/metrics")
        async def metrics_endpoint():
            return self.metrics.to_dict()

        @self.app.post("/colab/register")
        async def register_colab(req: ColabRegistrationRequest):
            colab = self.backends.get("colab")
            if not isinstance(colab, ColabBackend):
                raise HTTPException(status_code=500, detail="Colab backend not initialized")
            ep = colab.register_endpoint(
                name=req.name,
                endpoint_url=req.endpoint_url,
                capabilities=req.capabilities,
                api_key=req.api_key,
                job_types=req.job_types,
            )
            return ep

        @self.app.post("/colab/deregister")
        async def deregister_colab(request: Request):
            body = await request.json()
            endpoint_id = body.get("endpoint_id", "")
            colab = self.backends.get("colab")
            if not isinstance(colab, ColabBackend):
                raise HTTPException(status_code=500, detail="Colab backend not initialized")
            removed = colab.deregister_endpoint(endpoint_id)
            if not removed:
                raise HTTPException(status_code=404, detail="Endpoint not found")
            return {"status": "deregistered", "endpoint_id": endpoint_id}

        @self.app.get("/colab/status")
        async def colab_status():
            colab = self.backends.get("colab")
            if not isinstance(colab, ColabBackend):
                return {"endpoints": []}
            return {"endpoints": colab.get_endpoints()}

        @self.app.post("/callback/cloud_result")
        async def cloud_result_callback(req: ColabCallbackRequest):
            if req.status == "completed" and req.result:
                _PENDING_RESULTS[req.task_id] = {
                    "status": "completed",
                    "result": req.result,
                }
            elif req.status == "failed":
                _PENDING_RESULTS[req.task_id] = {
                    "status": "failed",
                    "error": req.error or "Unknown error from cloud callback",
                }
            else:
                _PENDING_RESULTS[req.task_id] = {
                    "status": req.status,
                    "result": req.result,
                }
            return {"status": "received", "task_id": req.task_id}

        @self.app.post("/dispatch")
        async def manual_dispatch(request: Request):
            body = await request.json()
            job_type = body.get("job_type", "image_generation")
            payload = body.get("payload", {})
            try:
                backend = self._select_backend(job_type, payload)
                task_id = await backend.submit(payload)
                self.metrics.record_dispatch(backend.name)
                return {
                    "task_id": task_id,
                    "backend": backend.name,
                    "job_type": job_type,
                }
            except Exception as exc:
                raise HTTPException(status_code=503, detail=str(exc))

        @self.app.post("/shutdown")
        async def shutdown_endpoint():
            asyncio.create_task(self.shutdown())
            return {"status": "shutting_down"}

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _setup_lifecycle(self):
        @self.app.on_event("startup")
        async def on_startup():
            await self.startup()

        @self.app.on_event("shutdown")
        async def on_shutdown():
            await self.shutdown()

    async def startup(self):
        logger.info("Starting Cloud Worker Bridge (id=%s)", BRIDGE_ID)
        self.metrics.start_time = datetime.now(timezone.utc)

        self._register_backends()

        self.db_pool = await asyncpg.create_pool(
            DB_DSN, min_size=2, max_size=10, command_timeout=30
        )

        await self._register_bridge_worker()

        self._poll_task = asyncio.create_task(self._poll_jobs_loop())
        self._health_task = asyncio.create_task(self._check_colab_health_loop())
        self._metrics_task = asyncio.create_task(self._flush_metrics_loop())
        self._warmup_task = asyncio.create_task(self._warmup_loop())

        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        self.status = "healthy"
        logger.info("Cloud Worker Bridge started and healthy")

    async def shutdown(self):
        if self.status == "offline":
            return
        logger.info("Shutting down Cloud Worker Bridge")
        self.status = "shutting_down"
        self._shutdown_event.set()

        for task in (self._poll_task, self._health_task, self._metrics_task, self._warmup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self._deregister_bridge_worker()

        if self.db_pool:
            await self.db_pool.close()

        self.status = "offline"
        logger.info("Cloud Worker Bridge shut down")

    # ── Database Registration ─────────────────────────────────────────────

    async def _register_bridge_worker(self):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.workers (id, name, worker_type, status, capabilities, last_heartbeat, metadata)
                    VALUES ($1, $2, $3, $4, $5, NOW(), $6::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        capabilities = EXCLUDED.capabilities,
                        last_heartbeat = NOW(),
                        metadata = EXCLUDED.metadata
                    """,
                    uuid.UUID(BRIDGE_ID),
                    "cloud-worker-bridge",
                    "cloud_bridge",
                    "healthy",
                    ["cloud_dispatch", "image_generation", "quality_review", "super_resolution", "image_animation"],
                    json.dumps({
                        "backends": list(self.backends.keys()),
                        "colab_endpoints": len(
                            self.backends["colab"].get_endpoints()
                            if isinstance(self.backends.get("colab"), ColabBackend)
                            else []
                        ),
                    }),
                )
            logger.info("Bridge worker registered in database")
        except Exception as exc:
            logger.error("Failed to register bridge worker: %s", exc)

    async def _deregister_bridge_worker(self):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cineos_exec.workers
                    SET status = 'offline', last_heartbeat = NOW()
                    WHERE id = $1
                    """,
                    uuid.UUID(BRIDGE_ID),
                )
        except Exception as exc:
            logger.error("Failed to deregister bridge worker: %s", exc)

    # ── Job Polling ───────────────────────────────────────────────────────

    async def _poll_jobs_loop(self):
        while not self._shutdown_event.is_set():
            try:
                await self._poll_and_dispatch_jobs()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Poll loop error: %s", exc)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=POLL_INTERVAL
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _poll_and_dispatch_jobs(self):
        async with self._processing_lock:
            try:
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        UPDATE cineos_exec.jobs
                        SET status = 'assigned',
                            assigned_worker = $1,
                            started_at = NOW()
                        WHERE id = (
                            SELECT id FROM cineos_exec.jobs
                            WHERE status = 'pending'
                              AND type = ANY($2)
                            ORDER BY priority DESC, created_at ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 5
                        )
                        RETURNING id, type, status, priority, payload, created_at
                        """,
                        uuid.UUID(BRIDGE_ID),
                        CLOUD_JOB_TYPES,
                    )

                    if not rows:
                        return

                    for row in rows:
                        job_dict = dict(row)
                        job_dict["id"] = str(job_dict["id"])
                        job_dict["payload"] = (
                            job_dict["payload"]
                            if isinstance(job_dict["payload"], dict)
                            else {}
                        )
                        asyncio.create_task(self._dispatch_job(job_dict))

            except Exception as exc:
                logger.error("Failed to poll jobs: %s", exc)

    async def _dispatch_job(self, job: Dict[str, Any]):
        job_id = job["id"]
        job_type = job["type"]
        payload = job["payload"]
        start = time.monotonic()

        try:
            backend = self._select_backend(job_type, payload)
            task_id = await backend.submit(payload)

            self._inflight[job_id] = {
                "task_id": task_id,
                "backend": backend.name,
                "job_type": job_type,
                "submitted_at": time.monotonic(),
            }
            self.metrics.record_dispatch(backend.name)
            self._job_backend_map[task_id] = backend.name

            await self._log_job(
                uuid.UUID(job_id), "info",
                f"Dispatched to {backend.name} (task={task_id})",
            )
            logger.info(
                "Dispatched job %s (type=%s) to %s (task=%s)",
                job_id, job_type, backend.name, task_id,
            )

            asyncio.create_task(
                self._wait_for_result(job_id, task_id, backend)
            )

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("Failed to dispatch job %s: %s", job_id, exc)
            await self._update_job_status(
                uuid.UUID(job_id), "failed", error=str(exc)
            )
            await self._log_job(
                uuid.UUID(job_id), "error", f"Dispatch failed: {exc}"
            )
            self.metrics.record_failure("dispatch", str(exc))

    async def _wait_for_result(
        self,
        job_id: str,
        task_id: str,
        backend: CloudBackend,
    ):
        start = time.monotonic()
        poll_interval = 2.0
        max_poll_interval = 15.0
        max_wait = JOB_TIMEOUT

        try:
            while time.monotonic() - start < max_wait:
                await asyncio.sleep(poll_interval)

                try:
                    status, result = await backend.poll(task_id)
                except Exception as exc:
                    logger.warning(
                        "Poll error for task %s (job %s): %s",
                        task_id, job_id, exc,
                    )
                    self.metrics.record_cloud_error()
                    continue

                if status == "completed":
                    elapsed_ms = (time.monotonic() - start) * 1000
                    self._inflight.pop(job_id, None)
                    self.metrics.record_completion(backend.name, elapsed_ms)

                    await self._update_job_status(
                        uuid.UUID(job_id), "completed", result=result
                    )
                    await self._log_job(
                        uuid.UUID(job_id), "info",
                        f"Completed via {backend.name} in {elapsed_ms:.0f}ms",
                    )
                    logger.info(
                        "Job %s completed via %s in %.0fms",
                        job_id, backend.name, elapsed_ms,
                    )
                    return

                elif status == "failed":
                    self._inflight.pop(job_id, None)
                    error_msg = result.get("error", "Unknown error") if result else "Unknown error"
                    self.metrics.record_failure(backend.name, error_msg)

                    await self._update_job_status(
                        uuid.UUID(job_id), "failed", error=error_msg
                    )
                    await self._log_job(
                        uuid.UUID(job_id), "error",
                        f"Cloud task failed: {error_msg}",
                    )
                    logger.error(
                        "Job %s failed via %s: %s",
                        job_id, backend.name, error_msg,
                    )
                    return

                poll_interval = min(poll_interval * 1.5, max_poll_interval)

            self._inflight.pop(job_id, None)
            elapsed_ms = (time.monotonic() - start) * 1000
            timeout_error = f"Cloud task timed out after {elapsed_ms:.0f}ms"
            self.metrics.record_failure(backend.name, timeout_error)

            await self._update_job_status(
                uuid.UUID(job_id), "failed", error=timeout_error
            )
            await self._log_job(
                uuid.UUID(job_id), "error", timeout_error,
            )
            logger.error("Job %s timed out via %s", job_id, backend.name)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._inflight.pop(job_id, None)
            logger.error("Unexpected error waiting for task %s: %s", task_id, exc)
            self.metrics.record_failure(backend.name, str(exc))
            try:
                await self._update_job_status(
                    uuid.UUID(job_id), "failed", error=str(exc)
                )
            except Exception:
                pass

    # ── Colab Health Check Loop ──────────────────────────────────────────

    async def _check_colab_health_loop(self):
        while not self._shutdown_event.is_set():
            try:
                colab = self.backends.get("colab")
                if isinstance(colab, ColabBackend) and colab._endpoints:
                    await colab.health_check_all()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Colab health check error: %s", exc)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=HEALTH_CHECK_INTERVAL
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _warmup_loop(self):
        while not self._shutdown_event.is_set():
            try:
                colab = self.backends.get("colab")
                if isinstance(colab, ColabBackend) and colab._endpoints:
                    await colab.send_warmup()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Warmup error: %s", exc)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=COLAB_WARMUP_INTERVAL
                )
                break
            except asyncio.TimeoutError:
                pass

    # ── Metrics Flush Loop ────────────────────────────────────────────────

    async def _flush_metrics_loop(self):
        while not self._shutdown_event.is_set():
            try:
                await self._flush_metrics_to_db()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Metrics flush error: %s", exc)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=METRICS_FLUSH_INTERVAL
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _flush_metrics_to_db(self):
        if self.db_pool is None:
            return
        try:
            metrics_dict = self.metrics.to_dict()
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cineos_exec.workers
                    SET last_heartbeat = NOW(),
                        status = $1,
                        total_tasks_completed = $2,
                        total_tasks_failed = $3
                    WHERE id = $4
                    """,
                    self.status,
                    self.metrics.jobs_completed,
                    self.metrics.jobs_failed,
                    uuid.UUID(BRIDGE_ID),
                )
        except Exception as exc:
            logger.error("Failed to flush metrics: %s", exc)

    # ── DB Helpers ────────────────────────────────────────────────────────

    async def _update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        try:
            async with self.db_pool.acquire() as conn:
                if status == "completed":
                    await conn.execute(
                        """
                        UPDATE cineos_exec.jobs
                        SET status = $1, result = $2::jsonb, completed_at = NOW()
                        WHERE id = $3
                        """,
                        status,
                        json.dumps(result) if result else "{}",
                        job_id,
                    )
                elif status == "failed":
                    await conn.execute(
                        """
                        UPDATE cineos_exec.jobs
                        SET status = $1, error = $2, completed_at = NOW()
                        WHERE id = $3
                        """,
                        status,
                        error,
                        job_id,
                    )
                else:
                    await conn.execute(
                        "UPDATE cineos_exec.jobs SET status = $1 WHERE id = $2",
                        status,
                        job_id,
                    )
        except Exception as exc:
            logger.error("Failed to update job %s status: %s", job_id, exc)

    async def _log_job(
        self, job_id: uuid.UUID, level: str, message: str
    ):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cineos_exec.job_logs (job_id, level, message, created_at)
                    VALUES ($1, $2, $3, NOW())
                    """,
                    job_id,
                    level,
                    message,
                )
        except Exception as exc:
            logger.error("Failed to write job log: %s", exc)

    # ── Entry Point ───────────────────────────────────────────────────────

    def run(self):
        import uvicorn
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=8600,
            log_level="info",
            access_log=True,
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    bridge = CloudWorkerBridge()
    bridge.run()


if __name__ == "__main__":
    main()
