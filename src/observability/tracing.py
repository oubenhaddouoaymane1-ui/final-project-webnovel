"""Request tracing for CineOS pipeline execution."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Context variable for the active trace ─────────────────────────

_trace_context: ContextVar[Optional[TraceContext]] = ContextVar("trace_context", default=None)


def get_current_trace() -> Optional[TraceContext]:
    """Get the currently active trace context, if any."""
    return _trace_context.get()


def get_current_span() -> Optional[Span]:
    """Get the currently active span, if any."""
    ctx = _trace_context.get()
    return ctx.active_span if ctx else None


def generate_trace_id() -> str:
    """Generate a new unique trace ID."""
    return str(uuid.uuid4())


def generate_span_id() -> str:
    """Generate a new unique span ID."""
    return uuid.uuid4().hex[:16]


@dataclass
class Span:
    """Represents a single unit of work within a trace.

    Tracks start/end times, status, attributes, and parent-child
    relationships.
    """
    span_id: str
    trace_id: str
    operation_name: str
    parent_span_id: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    _finished: bool = False

    def __post_init__(self) -> None:
        if self.start_time == 0.0:
            self.start_time = time.time()

    def finish(self, status: str = "ok", **attributes: Any) -> None:
        """Mark this span as finished."""
        if self._finished:
            return
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 3)
        self.status = status
        self.attributes.update(attributes)
        self._finished = True

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        self.attributes[key] = value

    def add_event(self, name: str, **attributes: Any) -> None:
        """Record an event within this span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **attributes,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "operation_name": self.operation_name,
            "parent_span_id": self.parent_span_id,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class TraceContext:
    """Propagates trace and span IDs through workflow execution.

    Each TraceContext owns a trace_id and a stack of spans representing
    the current call depth. Use context manager syntax for automatic
    span lifecycle management.
    """
    trace_id: str = ""
    spans: List[Span] = field(default_factory=list)
    _db_pool: Any = None
    _finished: bool = False

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = generate_trace_id()

    @property
    def active_span(self) -> Optional[Span]:
        """Return the current active (unfinished) span."""
        for span in reversed(self.spans):
            if not span._finished:
                return span
        return None

    @property
    def root_span(self) -> Optional[Span]:
        """Return the root (first) span of this trace."""
        return self.spans[0] if self.spans else None

    def start_span(self, operation_name: str, parent_span_id: Optional[str] = None, **attributes: Any) -> Span:
        """Create and activate a new child span."""
        parent = parent_span_id or (self.active_span.span_id if self.active_span else None)
        span = Span(
            span_id=generate_span_id(),
            trace_id=self.trace_id,
            operation_name=operation_name,
            parent_span_id=parent,
            attributes=attributes,
        )
        self.spans.append(span)
        return span

    def finish_span(self, span: Span, status: str = "ok", **attributes: Any) -> None:
        """Finish a specific span."""
        span.finish(status=status, **attributes)

    async def finish(self, status: str = "ok") -> None:
        """Finish the entire trace, closing any open spans and flushing to DB."""
        if self._finished:
            return
        for span in self.spans:
            if not span._finished:
                span.finish(status=status)
        self._finished = True
        await self._flush_to_db()

    async def _flush_to_db(self) -> None:
        """Write all spans to the cineos_audit.traces table."""
        if not self._db_pool or not self.spans:
            return
        try:
            async with self._db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO cineos_audit.traces
                        (trace_id, span_id, parent_span_id, operation_name,
                         start_time, end_time, duration_ms, status, attributes)
                    VALUES ($1, $2, $3, $4, to_timestamp($5), to_timestamp($6), $7, $8, $9)
                    ON CONFLICT (trace_id, span_id) DO NOTHING
                    """,
                    [
                        (
                            s.trace_id,
                            s.span_id,
                            s.parent_span_id,
                            s.operation_name,
                            s.start_time,
                            s.end_time if s.end_time else time.time(),
                            s.duration_ms,
                            s.status,
                            __import__("json").dumps(s.attributes, default=str),
                        )
                        for s in self.spans
                    ],
                )
            logger.debug(
                "Flushed %d spans for trace %s to database",
                len(self.spans),
                self.trace_id[:8],
            )
        except Exception as exc:
            logger.error("Failed to flush traces to DB: %s", exc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


class Tracer:
    """Creates and manages traces and spans for pipeline operations.

    Central entry point for instrumentation. Holds a reference to the
    database pool for persistence and manages the lifecycle of
    TraceContext objects.
    """

    def __init__(self, db_pool: Any = None) -> None:
        self._db_pool = db_pool
        self._active_traces: Dict[str, TraceContext] = {}

    async def start_trace(self, trace_id: Optional[str] = None, **root_attrs: Any) -> TraceContext:
        """Start a new trace and set it as the active context."""
        ctx = TraceContext(trace_id=trace_id or generate_trace_id(), _db_pool=self._db_pool)
        self._active_traces[ctx.trace_id] = ctx
        _trace_context.set(ctx)

        if root_attrs:
            ctx.start_span("root", **root_attrs)
        else:
            ctx.start_span("root")

        logger.debug("Trace started: %s", ctx.trace_id[:8])
        return ctx

    async def end_trace(self, trace_id: Optional[str] = None, status: str = "ok") -> Optional[TraceContext]:
        """End a trace and flush to the database."""
        ctx = _trace_context.get()
        if trace_id and trace_id in self._active_traces:
            ctx = self._active_traces.pop(trace_id)
        elif ctx:
            self._active_traces.pop(ctx.trace_id, None)

        if ctx:
            await ctx.finish(status=status)
            _trace_context.set(None)
            logger.debug("Trace ended: %s (status=%s)", ctx.trace_id[:8], status)
        return ctx

    def span(self, operation_name: str, **attributes: Any) -> _SpanContextManager:
        """Create a child span with context manager support.

        Usage:
            tracer = Tracer(db_pool=pool)
            ctx = await tracer.start_trace()
            with tracer.span("intake", project_id="abc"):
                await do_intake()
        """
        return _SpanContextManager(self, operation_name, attributes)

    def _start_span(self, operation_name: str, attributes: Dict[str, Any]) -> Span:
        """Internal: start a new span on the active trace."""
        ctx = _trace_context.get()
        if ctx is None:
            raise RuntimeError("No active trace context. Call start_trace() first.")
        return ctx.start_span(operation_name, **attributes)

    def _finish_span(self, span: Span, status: str = "ok", **attributes: Any) -> None:
        """Internal: finish a span on the active trace."""
        span.finish(status=status, **attributes)

    def get_trace(self, trace_id: str) -> Optional[TraceContext]:
        """Retrieve a trace context by ID."""
        return self._active_traces.get(trace_id)

    def list_traces(self) -> List[Dict[str, Any]]:
        """List all active traces."""
        return [
            {"trace_id": ctx.trace_id, "span_count": len(ctx.spans)}
            for ctx in self._active_traces.values()
        ]


class _SpanContextManager:
    """Context manager for automatic span lifecycle management."""

    def __init__(self, tracer: Tracer, operation_name: str, attributes: Dict[str, Any]) -> None:
        self._tracer = tracer
        self._operation_name = operation_name
        self._attributes = attributes
        self._span: Optional[Span] = None

    def __enter__(self) -> Span:
        self._span = self._tracer._start_span(self._operation_name, self._attributes)
        return self._span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is None:
            return
        if exc_val is not None:
            self._span.add_event("error", error=str(exc_val), error_type=type(exc_val).__name__)
            self._tracer._finish_span(self._span, status="error", error=str(exc_val))
        else:
            self._tracer._finish_span(self._span, status="ok")

    async def __aenter__(self) -> Span:
        self._span = self._tracer._start_span(self._operation_name, self._attributes)
        return self._span

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is None:
            return
        if exc_val is not None:
            self._span.add_event("error", error=str(exc_val), error_type=type(exc_val).__name__)
            self._tracer._finish_span(self._span, status="error", error=str(exc_val))
        else:
            self._tracer._finish_span(self._span, status="ok")
