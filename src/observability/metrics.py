"""Metrics collection, storage, and Prometheus export for CineOS."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point."""
    timestamp: float
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "name": self.name,
            "value": self.value,
            "labels": self.labels,
            "unit": self.unit,
        }


class MetricsCollector:
    """Collects, aggregates, and stores system metrics.

    Tracks project state, pipeline performance, worker health,
    and resource utilization. Stores points in memory and flushes
    periodically to the audit database.
    """

    _instance: Optional[MetricsCollector] = None

    def __init__(self) -> None:
        self._gauges: Dict[str, float] = {}
        self._counters: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._points: List[MetricPoint] = []
        self._collectors: List[Callable[[], List[MetricPoint]]] = []
        self._running = False
        self._flush_interval: float = 30.0
        self._max_points: int = 10000
        self._db_pool: Any = None

    @classmethod
    def get_instance(cls) -> MetricsCollector:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    # ── Gauge operations ──────────────────────────────────────────

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None, unit: str = "") -> None:
        """Set a gauge metric to a specific value."""
        point = MetricPoint(
            timestamp=time.time(),
            name=name,
            value=value,
            labels=labels or {},
            unit=unit,
        )
        self._gauges[name] = value
        self._points.append(point)
        self._maybe_trim()

    def get_gauge(self, name: str) -> Optional[float]:
        """Get current gauge value."""
        return self._gauges.get(name)

    # ── Counter operations ────────────────────────────────────────

    def increment(self, name: str, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        self._counters[name] += amount
        point = MetricPoint(
            timestamp=time.time(),
            name=name,
            value=self._counters[name],
            labels=labels or {},
            unit="count",
        )
        self._points.append(point)
        self._maybe_trim()

    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        return self._counters.get(name, 0.0)

    # ── Histogram operations ──────────────────────────────────────

    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None, unit: str = "") -> None:
        """Record a value in a histogram bucket."""
        self._histograms[name].append(value)
        point = MetricPoint(
            timestamp=time.time(),
            name=name,
            value=value,
            labels=labels or {},
            unit=unit,
        )
        self._points.append(point)
        self._maybe_trim()

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram summary statistics."""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p90": 0, "p99": 0}
        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "sum": sum(sorted_vals),
            "avg": sum(sorted_vals) / count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "p50": sorted_vals[int(count * 0.5)],
            "p90": sorted_vals[int(count * 0.9)],
            "p99": sorted_vals[min(int(count * 0.99), count - 1)],
        }

    # ── High-level metric helpers ─────────────────────────────────

    def record_project_state(self, project_id: str, state: str) -> None:
        """Record a project state transition."""
        self.increment("projects_state_change", labels={"project_id": project_id, "state": state})
        if state == "completed":
            self.increment("projects_completed")
        elif state == "failed":
            self.increment("projects_failed")

    def record_generation_time(self, backend: str, task_type: str, duration_ms: float) -> None:
        """Record generation time for a backend task."""
        self.record_histogram(
            "generation_time_ms",
            duration_ms,
            labels={"backend": backend, "task_type": task_type},
            unit="ms",
        )

    def record_review_score(self, entity_type: str, score: float) -> None:
        """Record a quality review score."""
        self.record_histogram(
            "review_score",
            score,
            labels={"entity_type": entity_type},
            unit="score",
        )

    def record_repair_time(self, backend: str, duration_ms: float) -> None:
        """Record repair operation time."""
        self.record_histogram(
            "repair_time_ms",
            duration_ms,
            labels={"backend": backend},
            unit="ms",
        )

    def set_worker_availability(self, available: int, total: int) -> None:
        """Set worker availability gauge."""
        self.set_gauge("worker_availability", available / max(total, 1), unit="ratio")
        self.set_gauge("worker_count_total", float(total), unit="count")
        self.set_gauge("worker_count_available", float(available), unit="count")

    def set_system_resources(
        self,
        gpu_util: float = 0.0,
        cpu_util: float = 0.0,
        ram_usage: float = 0.0,
        disk_usage: float = 0.0,
    ) -> None:
        """Set system resource gauges."""
        self.set_gauge("gpu_utilization", gpu_util, unit="percent")
        self.set_gauge("cpu_utilization", cpu_util, unit="percent")
        self.set_gauge("ram_usage", ram_usage, unit="percent")
        self.set_gauge("disk_usage", disk_usage, unit="percent")

    def set_queue_size(self, size: int) -> None:
        """Set job queue size."""
        self.set_gauge("queue_size", float(size), unit="count")

    # ── Collector registration ────────────────────────────────────

    def register_collector(self, collector: Callable[[], List[MetricPoint]]) -> None:
        """Register a callback that produces additional metric points."""
        self._collectors.append(collector)

    # ── Collection loop ───────────────────────────────────────────

    async def start(self, db_pool: Any = None, flush_interval: float = 30.0) -> None:
        """Start the background collection and flush loop."""
        self._db_pool = db_pool
        self._flush_interval = flush_interval
        self._running = True
        logger.info("MetricsCollector started (flush every %.1fs)", flush_interval)
        asyncio.get_event_loop().create_task(self._collection_loop())

    async def stop(self) -> None:
        """Stop the collection loop and flush remaining points."""
        self._running = False
        await self._flush_to_db()
        logger.info("MetricsCollector stopped")

    async def _collection_loop(self) -> None:
        """Background loop: invoke registered collectors then flush."""
        while self._running:
            try:
                for collector_fn in self._collectors:
                    try:
                        extra = collector_fn()
                        if extra:
                            self._points.extend(extra)
                    except Exception as exc:
                        logger.warning("Collector callback failed: %s", exc)
                await self._flush_to_db()
            except Exception as exc:
                logger.error("Metrics collection loop error: %s", exc)
            await asyncio.sleep(self._flush_interval)

    async def _flush_to_db(self) -> None:
        """Flush accumulated points to the database."""
        if not self._points or self._db_pool is None:
            return
        batch = list(self._points)
        self._points.clear()

        try:
            async with self._db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO cineos_audit.metrics
                        (metric_id, metric_name, metric_value, labels, unit, collected_at)
                    VALUES ($1, $2, $3, $4, $5, to_timestamp($6))
                    """,
                    [
                        (
                            str(uuid.uuid4()),
                            p.name,
                            p.value,
                            json.dumps(p.labels),
                            p.unit,
                            p.timestamp,
                        )
                        for p in batch
                    ],
                )
            logger.debug("Flushed %d metric points to database", len(batch))
        except Exception as exc:
            logger.error("Failed to flush metrics to DB: %s", exc)
            self._points = batch + self._points

    def _maybe_trim(self) -> None:
        """Trim points list if it exceeds the max size."""
        if len(self._points) > self._max_points:
            self._points = self._points[-self._max_points:]

    # ── Snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Return a complete snapshot of all current metrics."""
        return {
            "gauges": dict(self._gauges),
            "counters": dict(self._counters),
            "histograms": {k: self.get_histogram_stats(k) for k in self._histograms},
            "pending_points": len(self._points),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class PrometheusExporter:
    """Exports MetricsCollector state in Prometheus exposition format.

    Intended to be mounted at /metrics on an HTTP server.
    """

    def __init__(self, collector: Optional[MetricsCollector] = None) -> None:
        self._collector = collector or MetricsCollector.get_instance()

    def render(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: List[str] = []
        lines.append("# HELP cineos_metrics_snapshot CineOS system metrics snapshot.")
        lines.append("# TYPE cineos_metrics_snapshot gauge")
        lines.append('cineos_metrics_snapshot 1')
        lines.append("")

        # Gauges
        for name, value in self._collector._gauges.items():
            safe_name = name.replace(".", "_").replace("/", "_")
            lines.append(f"# TYPE cineos_{safe_name} gauge")
            lines.append(f"cineos_{safe_name} {value}")
            lines.append("")

        # Counters
        for name, value in self._collector._counters.items():
            safe_name = name.replace(".", "_").replace("/", "_")
            lines.append(f"# TYPE cineos_{safe_name} counter")
            lines.append(f"cineos_{safe_name} {value}")
            lines.append("")

        # Histograms
        for name in self._collector._histograms:
            stats = self._collector.get_histogram_stats(name)
            safe_name = name.replace(".", "_").replace("/", "_")
            lines.append(f"# TYPE cineos_{safe_name} summary")
            lines.append(f"cineos_{safe_name}_count {stats['count']}")
            lines.append(f"cineos_{safe_name}_sum {stats['sum']:.3f}")
            lines.append(f"cineos_{safe_name}_avg {stats['avg']:.3f}")
            lines.append(f"cineos_{safe_name}_min {stats['min']:.3f}")
            lines.append(f"cineos_{safe_name}_max {stats['max']:.3f}")
            lines.append(f"cineos_{safe_name}_p50 {stats['p50']:.3f}")
            lines.append(f"cineos_{safe_name}_p90 {stats['p90']:.3f}")
            lines.append(f"cineos_{safe_name}_p99 {stats['p99']:.3f}")
            lines.append("")

        # Timestamp
        lines.append(f"# HELP cineos_export_timestamp_unix Timestamp of last export")
        lines.append("# TYPE cineos_export_timestamp_unix gauge")
        lines.append(f"cineos_export_timestamp_unix {time.time():.3f}")
        lines.append("")

        return "\n".join(lines)

    async def handle_http_request(self, path: str = "/metrics") -> Tuple[int, str, str]:
        """Minimal HTTP handler for /metrics endpoint.

        Returns (status_code, content_type, body).
        """
        if path == "/metrics":
            body = self.render()
            return 200, "text/plain; version=0.0.4; charset=utf-8", body
        return 404, "text/plain", "Not Found"
