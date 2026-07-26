"""Structured logging for CineOS pipeline execution."""
from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Context variables for propagating IDs ─────────────────────────

_workflow_id: ContextVar[Optional[str]] = ContextVar("workflow_id", default=None)
_execution_id: ContextVar[Optional[str]] = ContextVar("execution_id", default=None)
_project_id: ContextVar[Optional[str]] = ContextVar("project_id", default=None)
_scene_id: ContextVar[Optional[str]] = ContextVar("scene_id", default=None)
_shot_id: ContextVar[Optional[str]] = ContextVar("shot_id", default=None)
_worker_id: ContextVar[Optional[str]] = ContextVar("worker_id", default=None)


def get_trace_ids() -> Dict[str, Optional[str]]:
    """Return all currently active context IDs."""
    return {
        "workflow_id": _workflow_id.get(),
        "execution_id": _execution_id.get(),
        "project_id": _project_id.get(),
        "scene_id": _scene_id.get(),
        "shot_id": _shot_id.get(),
        "worker_id": _worker_id.get(),
    }


@dataclass
class LogEntry:
    """Structured log entry with full pipeline context."""
    timestamp: str
    level: str
    message: str
    workflow: Optional[str] = None
    execution_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    shot_id: Optional[str] = None
    worker_id: Optional[str] = None
    state: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    logger_name: str = ""
    line: Optional[int] = None
    function: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON for structured log output."""
        data = asdict(self)
        data = {k: v for k, v in data.items() if v is not None}
        return json.dumps(data, default=str, ensure_ascii=False)

    def to_flat_dict(self) -> Dict[str, Any]:
        """Return a flat dictionary representation."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


class StructuredJSONFormatter(logging.Formatter):
    """Logging formatter that outputs LogEntry JSON."""

    def format(self, record: logging.LogRecord) -> str:
        caller_frame = record.exc_info[2] if record.exc_info else None
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            level=record.levelname,
            message=record.getMessage(),
            project_id=_project_id.get(),
            scene_id=_scene_id.get(),
            shot_id=_shot_id.get(),
            worker_id=_worker_id.get(),
            execution_id=_execution_id.get(),
            logger_name=record.name,
            line=record.lineno,
            function=record.funcName,
            metadata=getattr(record, "structured_meta", {}),
        )
        return entry.to_json()


class HumanReadableFormatter(logging.Formatter):
    """Readable formatter with context IDs for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]

        parts = [
            f"{color}{ts} [{record.levelname:>7}]{reset}",
            f"({record.name})",
        ]

        pid = _project_id.get()
        if pid:
            parts.append(f"[proj:{pid[:8]}]")

        eid = _execution_id.get()
        if eid:
            parts.append(f"[exec:{eid[:8]}]")

        sid = _scene_id.get()
        if sid:
            parts.append(f"[scene:{sid[:8]}]")

        parts.append(record.getMessage())
        return " ".join(parts)


class StructuredLogger:
    """Structured JSON logger with pipeline context propagation.

    Usage:
        slog = StructuredLogger("cineos.pipeline")
        slog.info("Phase started", state="intake", duration_ms=0)
    """

    def __init__(
        self,
        name: str,
        log_dir: str = "logs",
        level: str = "INFO",
        json_output: bool = True,
        max_bytes: int = 50 * 1024 * 1024,
        backup_count: int = 10,
    ) -> None:
        self._name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper()))
        self._logger.propagate = False

        if self._logger.handlers:
            return

        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # JSON file handler with rotation
        json_handler = logging.handlers.RotatingFileHandler(
            log_path / f"{name.replace('.', '_')}.jsonl",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        json_handler.setFormatter(StructuredJSONFormatter())
        self._logger.addHandler(json_handler)

        # Human-readable console handler
        if sys.stderr.isatty() or os.environ.get("CINEOS_LOG_CONSOLE", "").lower() in ("1", "true"):
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(HumanReadableFormatter())
            self._logger.addHandler(console_handler)

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        duration_ms = kwargs.pop("duration_ms", None)
        state = kwargs.pop("state", None)
        workflow = kwargs.pop("workflow", None)

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=logging.getLevelName(level),
            message=message,
            workflow=workflow,
            execution_id=_execution_id.get(),
            project_id=_project_id.get(),
            scene_id=_scene_id.get(),
            shot_id=_shot_id.get(),
            worker_id=_worker_id.get(),
            state=state,
            duration_ms=duration_ms,
            metadata=kwargs,
        )
        record = self._logger.makeRecord(
            name=self._name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.structured_meta = entry.to_flat_dict().get("metadata", {})
        self._logger.handle(record)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)

    def phase_start(self, phase: str, project_id: Optional[str] = None, **extra: Any) -> None:
        """Log pipeline phase start with standard context."""
        if project_id:
            _project_id.set(project_id)
        self.info(
            f"Pipeline phase '{phase}' started",
            state="started",
            workflow=phase,
            **extra,
        )

    def phase_complete(self, phase: str, duration_ms: float, **extra: Any) -> None:
        """Log pipeline phase completion."""
        self.info(
            f"Pipeline phase '{phase}' completed",
            state="completed",
            duration_ms=duration_ms,
            workflow=phase,
            **extra,
        )

    def phase_failed(self, phase: str, error: str, duration_ms: float, **extra: Any) -> None:
        """Log pipeline phase failure."""
        self.error(
            f"Pipeline phase '{phase}' failed: {error}",
            state="failed",
            duration_ms=duration_ms,
            workflow=phase,
            **extra,
        )

    def state_transition(self, entity_type: str, entity_id: str, old_state: str, new_state: str, **extra: Any) -> None:
        """Log a state transition."""
        self.info(
            f"{entity_type} {entity_id[:8]}: {old_state} -> {new_state}",
            state=new_state,
            **{"entity_type": entity_type, "entity_id": entity_id, "old_state": old_state, **extra},
        )


class LogContext:
    """Context manager that propagates pipeline IDs through the call stack.

    Usage:
        with LogContext(project_id="abc-123", scene_id="def-456"):
            logger.info("This log entry carries both IDs")
            do_work()  # Any logs here also carry the IDs
    """

    def __init__(
        self,
        workflow: Optional[str] = None,
        execution_id: Optional[str] = None,
        project_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        shot_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        self._tokens: Dict[str, Any] = {}
        self._values = {
            "workflow": _workflow_id,
            "execution_id": _execution_id,
            "project_id": _project_id,
            "scene_id": _scene_id,
            "shot_id": _shot_id,
            "worker_id": _worker_id,
        }
        self._overrides = {
            "workflow": workflow,
            "execution_id": execution_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "worker_id": worker_id,
        }

    def __enter__(self) -> LogContext:
        for key, var in self._values.items():
            value = self._overrides.get(key)
            if value is not None:
                self._tokens[key] = var.set(value)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        for key, token in self._tokens.items():
            self._values[key].reset(token)
        self._tokens.clear()


class WorkflowLogger:
    """Specialized logger for n8n workflow execution tracking.

    Provides structured logging tied to a specific workflow execution,
    with timing, node tracking, and step-by-step progress logging.
    """

    def __init__(
        self,
        workflow_name: str,
        execution_id: Optional[str] = None,
        project_id: Optional[str] = None,
        log_dir: str = "logs",
    ) -> None:
        self.workflow_name = workflow_name
        self.execution_id = execution_id or str(uuid.uuid4())
        self.project_id = project_id
        self._start_time: float = 0.0
        self._node_times: Dict[str, float] = {}
        self._node_errors: Dict[str, str] = {}
        self._slog = StructuredLogger(f"cineos.workflow.{workflow_name}", log_dir=log_dir)

    def __enter__(self) -> WorkflowLogger:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val:
            self.end(success=False, error=str(exc_val))
        else:
            self.end(success=True)

    def start(self) -> None:
        """Log workflow execution start."""
        self._start_time = time.time()
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            self._slog.info(
                f"Workflow '{self.workflow_name}' execution started",
                state="started",
                workflow=self.workflow_name,
                execution_id=self.execution_id,
                project_id=self.project_id,
            )

    def node_start(self, node_name: str, node_type: str = "", **extra: Any) -> None:
        """Log individual node start within the workflow."""
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            self._slog.info(
                f"Node '{node_name}' started",
                state="node_started",
                node_name=node_name,
                node_type=node_type,
                **extra,
            )
        self._node_times[f"{node_name}_start"] = time.time()

    def node_complete(self, node_name: str, **extra: Any) -> None:
        """Log node completion with duration."""
        start = self._node_times.pop(f"{node_name}_start", self._start_time)
        duration_ms = (time.time() - start) * 1000
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            self._slog.info(
                f"Node '{node_name}' completed",
                state="node_completed",
                duration_ms=duration_ms,
                node_name=node_name,
                **extra,
            )

    def node_failed(self, node_name: str, error: str, **extra: Any) -> None:
        """Log node failure."""
        start = self._node_times.pop(f"{node_name}_start", self._start_time)
        duration_ms = (time.time() - start) * 1000
        self._node_errors[node_name] = error
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            self._slog.error(
                f"Node '{node_name}' failed: {error}",
                state="node_failed",
                duration_ms=duration_ms,
                node_name=node_name,
                error=error,
                **extra,
            )

    def end(self, success: bool = True, error: Optional[str] = None, **extra: Any) -> None:
        """Log workflow execution end."""
        total_ms = (time.time() - self._start_time) * 1000
        state = "completed" if success else "failed"
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            payload: Dict[str, Any] = {
                "state": state,
                "duration_ms": total_ms,
                "total_nodes": len(self._node_times) + len(self._node_errors),
                "failed_nodes": len(self._node_errors),
                "node_errors": self._node_errors,
                **extra,
            }
            if error:
                payload["error"] = error
            log_fn = self._slog.info if success else self._slog.error
            log_fn(
                f"Workflow '{self.workflow_name}' execution {'completed' if success else 'failed'}",
                **payload,
            )

    def log_data(self, message: str, data: Dict[str, Any], **extra: Any) -> None:
        """Log arbitrary data within workflow context."""
        with LogContext(
            workflow=self.workflow_name,
            execution_id=self.execution_id,
            project_id=self.project_id,
        ):
            self._slog.info(message, data=data, **extra)


def setup_structured_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    json_console: bool = False,
) -> None:
    """Initialize the global structured logging system.

    Replaces the basic logger setup with structured JSON output.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper()))

    for handler in list(root.handlers):
        root.removeHandler(handler)

    json_handler = logging.handlers.RotatingFileHandler(
        log_path / "cineos.jsonl",
        maxBytes=50 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    json_handler.setFormatter(StructuredJSONFormatter())
    root.addHandler(json_handler)

    if json_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(StructuredJSONFormatter())
        root.addHandler(console_handler)
    else:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(HumanReadableFormatter())
        root.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
