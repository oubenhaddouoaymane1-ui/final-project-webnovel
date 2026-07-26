import os
import uuid
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger("cineos.supervisor")

WORKER_HEARTBEAT_TIMEOUT = int(os.getenv("WORKER_HEARTBEAT_TIMEOUT", "90"))


class WorkerRegistration(BaseModel):
    worker_id: str
    name: str
    worker_type: str
    job_types: List[str]
    capabilities: List[str] = []
    port: int = 8000


class HeartbeatUpdate(BaseModel):
    status: str = "healthy"
    metrics: Optional[Dict[str, Any]] = None


class JobAssignRequest(BaseModel):
    job_id: str
    worker_id: Optional[str] = None
    force: bool = False


class SupervisorService:
    def __init__(self):
        self.db_pool: Optional[asyncpg.Pool] = None
        self.app = FastAPI(title="CineOS Supervisor", version="1.0.0")
        self.worker_registry: Dict[str, Dict[str, Any]] = {}
        self._health_check_task: Optional[asyncio.Task] = None

        self.db_dsn: str = os.getenv(
            "DATABASE_URL", "postgresql://cineos:cineos@localhost:5432/cineos"
        )
        self.health_check_interval: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))

        self._setup_routes()
        self._setup_lifecycle()

    def _setup_routes(self):
        @self.app.get("/health")
        async def health():
            db_ok = False
            if self.db_pool:
                try:
                    async with self.db_pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    db_ok = True
                except Exception:
                    pass
            return {
                "status": "healthy" if db_ok else "degraded",
                "database_connected": db_ok,
                "registered_workers": len(self.worker_registry),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        @self.app.get("/workers")
        async def list_workers(
            worker_type: Optional[str] = Query(None),
            status: Optional[str] = Query(None),
        ):
            workers = list(self.worker_registry.values())
            if worker_type:
                workers = [w for w in workers if w.get("worker_type") == worker_type]
            if status:
                workers = [w for w in workers if w.get("status") == status]
            return {"workers": workers, "count": len(workers)}

        @self.app.get("/workers/{worker_id}")
        async def get_worker(worker_id: str):
            worker = self.worker_registry.get(worker_id)
            if not worker:
                raise HTTPException(status_code=404, detail="Worker not found")
            return worker

        @self.app.post("/workers")
        async def register_worker(reg: WorkerRegistration):
            worker_info = {
                "worker_id": reg.worker_id,
                "name": reg.name,
                "worker_type": reg.worker_type,
                "job_types": reg.job_types,
                "capabilities": reg.capabilities,
                "port": reg.port,
                "status": "healthy",
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "metrics": {},
                "active_job": None,
                "jobs_processed": 0,
                "jobs_failed": 0,
            }
            self.worker_registry[reg.worker_id] = worker_info
            logger.info(
                "Worker registered: %s (%s, type=%s)",
                reg.name, reg.worker_id, reg.worker_type,
            )
            return {"status": "registered", "worker_id": reg.worker_id}

        @self.app.delete("/workers/{worker_id}")
        async def deregister_worker(worker_id: str):
            if worker_id in self.worker_registry:
                del self.worker_registry[worker_id]
                logger.info("Worker deregistered: %s", worker_id)
            return {"status": "deregistered"}

        @self.app.post("/workers/{worker_id}/heartbeat")
        async def worker_heartbeat(worker_id: str, update: HeartbeatUpdate):
            if worker_id not in self.worker_registry:
                raise HTTPException(status_code=404, detail="Worker not registered")
            worker = self.worker_registry[worker_id]
            worker["status"] = update.status
            worker["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
            if update.metrics:
                worker["metrics"] = update.metrics
                worker["jobs_processed"] = update.metrics.get("jobs_processed", worker.get("jobs_processed", 0))
                worker["jobs_failed"] = update.metrics.get("jobs_failed", worker.get("jobs_failed", 0))
            return {"status": "ok"}

        @self.app.post("/jobs/{job_id}/assign")
        async def assign_job(job_id: str, req: Optional[JobAssignRequest] = None):
            worker_id = None
            force = False
            if req:
                worker_id = req.worker_id
                force = req.force

            async with self.db_pool.acquire() as conn:
                job = await conn.fetchrow(
                    "SELECT id, type, status, priority, payload FROM cineos_exec.jobs WHERE id = $1",
                    uuid.UUID(job_id),
                )
                if not job:
                    raise HTTPException(status_code=404, detail="Job not found")
                if job["status"] != "pending":
                    raise HTTPException(
                        status_code=409,
                        detail=f"Job is already in status '{job['status']}'",
                    )

                if worker_id:
                    if worker_id not in self.worker_registry:
                        raise HTTPException(status_code=404, detail="Worker not found")
                    chosen = self.worker_registry[worker_id]
                else:
                    chosen = self._select_best_worker(job["type"])
                    if not chosen:
                        raise HTTPException(
                            status_code=503,
                            detail="No available worker for this job type",
                        )

                worker_uuid = uuid.UUID(chosen["worker_id"])
                await conn.execute(
                    """
                    UPDATE cineos_exec.jobs
                    SET status = 'assigned', assigned_worker = $1, started_at = NOW()
                    WHERE id = $2
                    """,
                    worker_uuid,
                    uuid.UUID(job_id),
                )

            chosen["active_job"] = job_id
            logger.info(
                "Job %s assigned to worker %s (%s)",
                job_id, chosen["name"], chosen["worker_id"],
            )
            return {
                "job_id": job_id,
                "assigned_to": chosen["worker_id"],
                "worker_name": chosen["name"],
            }

        @self.app.get("/metrics")
        async def metrics_dashboard():
            workers = list(self.worker_registry.values())
            total_workers = len(workers)
            healthy_workers = sum(1 for w in workers if w.get("status") == "healthy")
            total_processed = sum(w.get("jobs_processed", 0) for w in workers)
            total_failed = sum(w.get("jobs_failed", 0) for w in workers)

            worker_type_counts: Dict[str, int] = {}
            for w in workers:
                wt = w.get("worker_type", "unknown")
                worker_type_counts[wt] = worker_type_counts.get(wt, 0) + 1

            async with self.db_pool.acquire() as conn:
                job_stats = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                        COUNT(*) FILTER (WHERE status = 'assigned') AS assigned,
                        COUNT(*) FILTER (WHERE status = 'running') AS running,
                        COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                        COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                        COUNT(*) AS total
                    FROM cineos_exec.jobs
                    """
                )

                avg_completion = await conn.fetchval(
                    """
                    SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))
                    FROM cineos_exec.jobs
                    WHERE completed_at IS NOT NULL AND started_at IS NOT NULL
                      AND completed_at > NOW() - INTERVAL '1 hour'
                    """
                )

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "workers": {
                    "total": total_workers,
                    "healthy": healthy_workers,
                    "unhealthy": total_workers - healthy_workers,
                    "by_type": worker_type_counts,
                },
                "jobs": dict(job_stats) if job_stats else {},
                "performance": {
                    "total_processed": total_processed,
                    "total_failed": total_failed,
                    "success_rate": round(
                        (total_processed / max(total_processed + total_failed, 1)) * 100, 2
                    ),
                    "avg_completion_time_seconds": round(float(avg_completion), 2) if avg_completion else None,
                },
                "worker_details": [
                    {
                        "worker_id": w["worker_id"],
                        "name": w["name"],
                        "type": w.get("worker_type"),
                        "status": w.get("status"),
                        "last_heartbeat": w.get("last_heartbeat"),
                        "jobs_processed": w.get("jobs_processed", 0),
                        "active_job": w.get("active_job"),
                    }
                    for w in workers
                ],
            }

        @self.app.get("/jobs/pending")
        async def pending_jobs(
            job_type: Optional[str] = Query(None),
            limit: int = Query(50, le=200),
        ):
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT id, type, status, priority, payload, created_at
                    FROM cineos_exec.jobs
                    WHERE status = 'pending'
                """
                params: list = []
                if job_type:
                    params.append(job_type)
                    query += f" AND type = ${len(params)}"
                query += " ORDER BY priority DESC, created_at ASC"
                params.append(limit)
                query += f" LIMIT ${len(params)}"

                rows = await conn.fetch(query, *params)
                jobs = []
                for row in rows:
                    j = dict(row)
                    j["id"] = str(j["id"])
                    j["payload"] = j["payload"] if isinstance(j["payload"], dict) else {}
                    jobs.append(j)
            return {"jobs": jobs, "count": len(jobs)}

    def _setup_lifecycle(self):
        @self.app.on_event("startup")
        async def on_startup():
            await self.startup()

        @self.app.on_event("shutdown")
        async def on_shutdown():
            await self.shutdown()

    async def startup(self):
        logger.info("Starting CineOS Supervisor")
        self.db_pool = await asyncpg.create_pool(
            self.db_dsn, min_size=3, max_size=15, command_timeout=30
        )

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, worker_type, status, capabilities, last_heartbeat
                FROM cineos_exec.workers
                WHERE status != 'offline'
                """
            )
            for row in rows:
                wid = str(row["id"])
                self.worker_registry[wid] = {
                    "worker_id": wid,
                    "name": row["name"],
                    "worker_type": row["worker_type"],
                    "job_types": [row["worker_type"]],
                    "capabilities": row["capabilities"] or [],
                    "port": 8000,
                    "status": row["status"],
                    "last_heartbeat": row["last_heartbeat"].isoformat() if row["last_heartbeat"] else None,
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                    "metrics": {},
                    "active_job": None,
                    "jobs_processed": 0,
                    "jobs_failed": 0,
                }
            logger.info("Loaded %d existing workers from database", len(rows))

        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Supervisor started")

    async def shutdown(self):
        logger.info("Shutting down Supervisor")
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        if self.db_pool:
            await self.db_pool.close()

    async def _health_check_loop(self):
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                now = datetime.now(timezone.utc)
                stale_workers: List[str] = []

                for wid, worker in self.worker_registry.items():
                    hb_str = worker.get("last_heartbeat")
                    if not hb_str:
                        stale_workers.append(wid)
                        continue
                    try:
                        hb_time = datetime.fromisoformat(hb_str.replace("Z", "+00:00"))
                    except ValueError:
                        stale_workers.append(wid)
                        continue

                    age = (now - hb_time).total_seconds()
                    if age > WORKER_HEARTBEAT_TIMEOUT:
                        if worker.get("status") != "offline":
                            worker["status"] = "offline"
                            logger.warning(
                                "Worker %s (%s) marked offline (no heartbeat for %ds)",
                                worker["name"], wid, int(age),
                            )
                            await self._handle_worker_offline(wid, worker)

                for wid in stale_workers:
                    if wid in self.worker_registry:
                        self.worker_registry[wid]["status"] = "offline"

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Health check error: %s", exc)

    async def _handle_worker_offline(self, worker_id: str, worker: Dict[str, Any]):
        active_job = worker.get("active_job")
        if active_job:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE cineos_exec.jobs
                        SET status = 'pending', assigned_worker = NULL, started_at = NULL
                        WHERE id = $1 AND status IN ('assigned', 'running')
                        """,
                        uuid.UUID(active_job),
                    )
                logger.info("Requeued job %s from offline worker %s", active_job, worker_id)
            except Exception as exc:
                logger.error("Failed to requeue job %s: %s", active_job, exc)
            worker["active_job"] = None

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE cineos_exec.workers
                    SET status = 'offline', last_heartbeat = NOW()
                    WHERE id = $1
                    """,
                    uuid.UUID(worker_id),
                )
        except Exception as exc:
            logger.error("Failed to update worker %s status in DB: %s", worker_id, exc)

    def _select_best_worker(self, job_type: str) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        for worker in self.worker_registry.values():
            if worker.get("status") != "healthy":
                continue
            if worker.get("active_job") is not None:
                continue
            if job_type not in worker.get("job_types", []):
                continue
            candidates.append(worker)

        if not candidates:
            return None

        scored: List[tuple] = []
        for c in candidates:
            metrics = c.get("metrics", {})
            processed = metrics.get("jobs_processed", c.get("jobs_processed", 0))
            failed = metrics.get("jobs_failed", c.get("jobs_failed", 0))
            avg_time = metrics.get("avg_processing_time_ms", 0)

            failure_rate = failed / max(processed + failed, 1)
            score = (1.0 - failure_rate) * 100 - (avg_time / 1000)
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    supervisor = SupervisorService()
    uvicorn.run(supervisor.app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
