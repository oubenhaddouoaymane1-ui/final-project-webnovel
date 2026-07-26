import os
import uuid
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

logger = logging.getLogger("cineos.worker")


class WorkerMetrics:
    def __init__(self):
        self.jobs_processed: int = 0
        self.jobs_failed: int = 0
        self.jobs_retried: int = 0
        self.total_processing_time_ms: float = 0.0
        self.start_time: Optional[datetime] = None
        self.last_job_time: Optional[datetime] = None
        self.current_job_id: Optional[str] = None
        self.errors: List[Dict[str, Any]] = []

    def record_success(self, processing_time_ms: float):
        self.jobs_processed += 1
        self.total_processing_time_ms += processing_time_ms
        self.last_job_time = datetime.now(timezone.utc)

    def record_failure(self, error: str):
        self.jobs_failed += 1
        self.errors.append({
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]
        self.last_job_time = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        uptime = 0.0
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        avg_time = 0.0
        if self.jobs_processed > 0:
            avg_time = self.total_processing_time_ms / self.jobs_processed
        return {
            "jobs_processed": self.jobs_processed,
            "jobs_failed": self.jobs_failed,
            "jobs_retried": self.jobs_retried,
            "uptime_seconds": round(uptime, 2),
            "avg_processing_time_ms": round(avg_time, 2),
            "current_job_id": self.current_job_id,
            "last_job_time": self.last_job_time.isoformat() if self.last_job_time else None,
            "recent_errors": self.errors[-5:],
        }


class WorkerBase:
    def __init__(
        self,
        name: str,
        worker_type: str,
        job_types: List[str],
        capabilities: Optional[List[str]] = None,
        port: int = 8000,
    ):
        self.worker_id: str = str(uuid.uuid4())
        self.name = name
        self.worker_type = worker_type
        self.job_types = job_types
        self.capabilities = capabilities or []
        self.port = port

        self.status: str = "starting"
        self.db_pool: Optional[asyncpg.Pool] = None
        self.metrics = WorkerMetrics()
        self.app = FastAPI(title=f"CineOS {name}", version="1.0.0")

        self._shutdown_event = asyncio.Event()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._current_job: Optional[str] = None
        self._processing_lock = asyncio.Lock()

        self.db_dsn: str = os.getenv(
            "DATABASE_URL", "postgresql://cineos:cineos@localhost:5432/cineos"
        )
        self.heartbeat_interval: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
        self.poll_interval: float = float(os.getenv("POLL_INTERVAL", "5"))
        self.supervisor_url: str = os.getenv("SUPERVISOR_URL", "http://supervisor:8000")
        self.job_timeout: int = int(os.getenv("JOB_TIMEOUT", "600"))
        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.output_dir: str = os.getenv("OUTPUT_DIR", "/data/output")

        self._setup_routes()
        self._setup_lifecycle()

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
            return JSONResponse(
                status_code=200 if (self.status == "healthy" and db_ok) else 503,
                content={
                    "status": self.status,
                    "worker_id": self.worker_id,
                    "worker_type": self.worker_type,
                    "name": self.name,
                    "database_connected": db_ok,
                    "metrics": self.metrics.to_dict(),
                },
            )

        @self.app.get("/metrics")
        async def metrics_endpoint():
            return self.metrics.to_dict()

        @self.app.post("/shutdown")
        async def shutdown_endpoint():
            asyncio.create_task(self.shutdown())
            return {"status": "shutting_down"}

    def _setup_lifecycle(self):
        @self.app.on_event("startup")
        async def on_startup():
            await self.startup()

        @self.app.on_event("shutdown")
        async def on_shutdown():
            await self.shutdown()

    async def startup(self):
        logger.info(
            "Starting worker %s (id=%s, type=%s)",
            self.name, self.worker_id, self.worker_type,
        )
        self.metrics.start_time = datetime.now(timezone.utc)

        self.db_pool = await asyncpg.create_pool(
            self.db_dsn, min_size=2, max_size=10, command_timeout=30
        )

        await self._register_worker()
        await self._register_with_supervisor()

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())

        os.makedirs(self.output_dir, exist_ok=True)

        self.status = "healthy"
        logger.info("Worker %s started and healthy", self.name)

    async def shutdown(self):
        if self.status == "offline":
            return
        logger.info("Shutting down worker %s", self.name)
        self.status = "shutting_down"
        self._shutdown_event.set()

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        await self._deregister_worker()
        await self._deregister_from_supervisor()

        if self.db_pool:
            await self.db_pool.close()

        self.status = "offline"
        logger.info("Worker %s shut down", self.name)

    async def _register_worker(self):
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
                uuid.UUID(self.worker_id),
                self.name,
                self.worker_type,
                self.status,
                self.capabilities,
                "{}",
            )
        logger.info("Worker %s registered in database", self.name)

    async def _deregister_worker(self):
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cineos_exec.workers
                    SET status = 'offline', last_heartbeat = NOW()
                    WHERE id = $1
                    """,
                    uuid.UUID(self.worker_id),
                )
        except Exception as exc:
            logger.error("Failed to deregister worker: %s", exc)

    async def _register_with_supervisor(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.supervisor_url}/workers",
                    json={
                        "worker_id": self.worker_id,
                        "name": self.name,
                        "worker_type": self.worker_type,
                        "job_types": self.job_types,
                        "capabilities": self.capabilities,
                        "port": self.port,
                    },
                )
                resp.raise_for_status()
            logger.info("Registered with supervisor")
        except Exception as exc:
            logger.warning("Could not register with supervisor: %s", exc)

    async def _deregister_from_supervisor(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.delete(
                    f"{self.supervisor_url}/workers/{self.worker_id}"
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Could not deregister from supervisor: %s", exc)

    async def _heartbeat_loop(self):
        while not self._shutdown_event.is_set():
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE cineos_exec.workers
                        SET last_heartbeat = NOW(), status = $1
                        WHERE id = $2
                        """,
                        self.status,
                        uuid.UUID(self.worker_id),
                    )

                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(
                            f"{self.supervisor_url}/workers/{self.worker_id}/heartbeat",
                            json={"status": self.status, "metrics": self.metrics.to_dict()},
                        )
                except Exception:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)

            await asyncio.sleep(self.heartbeat_interval)

    async def _poll_loop(self):
        while not self._shutdown_event.is_set():
            try:
                async with self._processing_lock:
                    if self._current_job is None:
                        job = await self._claim_job()
                        if job:
                            await self._process_job_wrapper(job)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Poll loop error: %s", exc)

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=self.poll_interval
                )
                break
            except asyncio.TimeoutError:
                pass

    async def _claim_job(self) -> Optional[Dict[str, Any]]:
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
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
                        LIMIT 1
                    )
                    RETURNING id, type, status, priority, payload, created_at
                    """,
                    uuid.UUID(self.worker_id),
                    self.job_types,
                )
                if row:
                    job_dict = dict(row)
                    job_dict["id"] = str(job_dict["id"])
                    job_dict["payload"] = (
                        job_dict["payload"]
                        if isinstance(job_dict["payload"], dict)
                        else {}
                    )
                    self._current_job = job_dict["id"]
                    self.metrics.current_job_id = job_dict["id"]
                    await self._log_job(
                        uuid.UUID(job_dict["id"]),
                        "info",
                        f"Job claimed by worker {self.name}",
                    )
                    logger.info("Claimed job %s (type=%s)", job_dict["id"], job_dict["type"])
                    return job_dict
        except Exception as exc:
            logger.error("Failed to claim job: %s", exc)
        return None

    async def _process_job_wrapper(self, job: Dict[str, Any]):
        job_id = job["id"]
        start = time.monotonic()
        try:
            await self._update_job_status(uuid.UUID(job_id), "running")
            await self._log_job(uuid.UUID(job_id), "info", f"Processing with {self.name}")

            result = await self.process_job(job)

            elapsed_ms = (time.monotonic() - start) * 1000
            await self._update_job_status(
                uuid.UUID(job_id), "completed", result=result
            )
            await self._log_job(
                uuid.UUID(job_id),
                "info",
                f"Completed in {elapsed_ms:.0f}ms",
            )
            self.metrics.record_success(elapsed_ms)
            logger.info("Job %s completed in %.0fms", job_id, elapsed_ms)

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            error_msg = str(exc)
            logger.error("Job %s failed: %s", job_id, error_msg)
            await self._update_job_status(
                uuid.UUID(job_id), "failed", error=error_msg
            )
            await self._log_job(uuid.UUID(job_id), "error", f"Failed: {error_msg}")
            self.metrics.record_failure(error_msg)

        finally:
            self._current_job = None
            self.metrics.current_job_id = None

    async def process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement process_job()"
        )

    async def _update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        async with self.db_pool.acquire() as conn:
            if status == "completed":
                import json
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

    async def _claim_specific_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE cineos_exec.jobs
                    SET status = 'assigned',
                        assigned_worker = $1,
                        started_at = NOW()
                    WHERE id = $2 AND status = 'pending'
                    RETURNING id, type, status, priority, payload, created_at
                    """,
                    uuid.UUID(self.worker_id),
                    uuid.UUID(job_id),
                )
                if row:
                    job_dict = dict(row)
                    job_dict["id"] = str(job_dict["id"])
                    job_dict["payload"] = (
                        job_dict["payload"]
                        if isinstance(job_dict["payload"], dict)
                        else {}
                    )
                    self._current_job = job_dict["id"]
                    self.metrics.current_job_id = job_dict["id"]
                    return job_dict
        except Exception as exc:
            logger.error("Failed to claim specific job: %s", exc)
        return None

    async def _get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, type, status, priority, payload, result, error,
                           assigned_worker, created_at, started_at, completed_at
                    FROM cineos_exec.jobs WHERE id = $1
                    """,
                    uuid.UUID(job_id),
                )
                if row:
                    job_dict = dict(row)
                    job_dict["id"] = str(job_dict["id"])
                    if job_dict.get("assigned_worker"):
                        job_dict["assigned_worker"] = str(job_dict["assigned_worker"])
                    job_dict["payload"] = (
                        job_dict["payload"]
                        if isinstance(job_dict["payload"], dict)
                        else {}
                    )
                    return job_dict
        except Exception as exc:
            logger.error("Failed to fetch job %s: %s", job_id, exc)
        return None

    async def _write_quality_check(
        self,
        job_id: str,
        asset_id: str,
        check_type: str,
        score: float,
        passed: bool,
        details: Optional[Dict[str, Any]] = None,
    ):
        import json
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cineos_quality.checks
                    (id, job_id, asset_id, check_type, score, passed, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                """,
                uuid.uuid4(),
                uuid.UUID(job_id),
                asset_id,
                check_type,
                score,
                passed,
                json.dumps(details) if details else "{}",
            )

    def run(self):
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info",
            access_log=True,
        )
