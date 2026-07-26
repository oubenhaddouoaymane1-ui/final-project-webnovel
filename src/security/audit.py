"""Audit logging — structured security-event recording to cineos_audit.security_events."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import asyncpg

logger = logging.getLogger("cineos.security.audit")


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    TOKEN_REFRESH = "token_refresh"
    RATE_LIMIT = "rate_limit"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_INPUT = "suspicious_input"
    SQL_INJECTION = "sql_injection"
    XSS_ATTEMPT = "xss_attempt"
    PATH_TRAVERSAL = "path_traversal"
    PROMPT_INJECTION = "prompt_injection"
    SECRET_ACCESS = "secret_access"
    SECRET_ROTATION = "secret_rotation"
    CONFIG_CHANGE = "config_change"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    IP_BLOCKED = "ip_blocked"
    FILE_UPLOAD_BLOCKED = "file_upload_blocked"
    WEBHOOK_VALIDATION_FAILED = "webhook_validation_failed"
    PERMISSION_DENIED = "permission_denied"
    DATA_EXPORT = "data_export"


# Severity mapping for convenience
_SEVERITY_MAP: dict[EventType, EventSeverity] = {
    EventType.LOGIN: EventSeverity.INFO,
    EventType.LOGOUT: EventSeverity.INFO,
    EventType.AUTH_SUCCESS: EventSeverity.INFO,
    EventType.AUTH_FAILURE: EventSeverity.WARNING,
    EventType.TOKEN_REFRESH: EventSeverity.INFO,
    EventType.RATE_LIMIT: EventSeverity.INFO,
    EventType.RATE_LIMIT_EXCEEDED: EventSeverity.WARNING,
    EventType.SUSPICIOUS_INPUT: EventSeverity.WARNING,
    EventType.SQL_INJECTION: EventSeverity.ERROR,
    EventType.XSS_ATTEMPT: EventSeverity.ERROR,
    EventType.PATH_TRAVERSAL: EventSeverity.ERROR,
    EventType.PROMPT_INJECTION: EventSeverity.ERROR,
    EventType.SECRET_ACCESS: EventSeverity.WARNING,
    EventType.SECRET_ROTATION: EventSeverity.INFO,
    EventType.CONFIG_CHANGE: EventSeverity.INFO,
    EventType.API_KEY_CREATED: EventSeverity.INFO,
    EventType.API_KEY_REVOKED: EventSeverity.INFO,
    EventType.IP_BLOCKED: EventSeverity.WARNING,
    EventType.FILE_UPLOAD_BLOCKED: EventSeverity.WARNING,
    EventType.WEBHOOK_VALIDATION_FAILED: EventSeverity.WARNING,
    EventType.PERMISSION_DENIED: EventSeverity.WARNING,
    EventType.DATA_EXPORT: EventSeverity.INFO,
}


class AuditLogger:
    """Writes structured security events to the ``cineos_audit.security_events`` table.

    Also logs to the Python logging system for console/file output and optional
    JSON-file logging.
    """

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        *,
        log_file: str | None = None,
    ) -> None:
        self._pool = pool
        self._file_logger: Optional[logging.Logger] = None
        if log_file:
            self._file_logger = self._setup_file_logger(log_file)

    @staticmethod
    def _setup_file_logger(path: str) -> logging.Logger:
        log_dir = os.path.dirname(path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_logger = logging.getLogger("cineos.security.audit.file")
        file_logger.setLevel(logging.INFO)
        file_logger.propagate = False

        handler = logging.FileHandler(path)
        handler.setFormatter(
            logging.Formatter("%(message)s")
        )
        file_logger.addHandler(handler)
        return file_logger

    async def log(
        self,
        event_type: EventType | str,
        *,
        severity: EventSeverity | str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        api_key_id: str | None = None,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Record a security event.  Returns the generated event_id."""
        if isinstance(event_type, str):
            event_type = EventType(event_type) if event_type in EventType.__members__.values() else event_type
        if isinstance(severity, str):
            severity = EventSeverity(severity)
        if severity is None:
            severity = _SEVERITY_MAP.get(EventType(event_type), EventSeverity.INFO) if isinstance(event_type, EventType) else EventSeverity.INFO

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        event_record = {
            "event_id": event_id,
            "event_type": event_type.value if isinstance(event_type, EventType) else event_type,
            "severity": severity.value if isinstance(severity, EventSeverity) else severity,
            "source_ip": source_ip,
            "user_agent": user_agent,
            "request_id": request_id,
            "api_key_id": api_key_id,
            "user_id": user_id,
            "details": details or {},
            "created_at": now.isoformat(),
        }

        # Python log output
        log_msg = (
            f"SECURITY_EVENT event_type={event_record['event_type']} "
            f"severity={event_record['severity']} "
            f"request_id={request_id or '-'} "
            f"source_ip={source_ip or '-'}"
        )

        sev = severity if isinstance(severity, EventSeverity) else EventSeverity.INFO
        if sev == EventSeverity.CRITICAL:
            logger.critical(log_msg)
        elif sev == EventSeverity.ERROR:
            logger.error(log_msg)
        elif sev == EventSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Structured JSON to file
        if self._file_logger:
            self._file_logger.info(json.dumps(event_record, default=str))

        # Database persistence
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO cineos_audit.security_events
                            (event_id, event_type, severity, source_ip, user_agent,
                             request_id, api_key_id, details, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                        """,
                        uuid.UUID(event_id),
                        event_record["event_type"],
                        event_record["severity"],
                        source_ip,
                        user_agent,
                        request_id,
                        api_key_id,
                        json.dumps(details or {}, default=str),
                        now,
                    )
            except Exception as exc:
                logger.error(
                    "Failed to persist security event to database: %s",
                    exc,
                )

        return event_id

    # -- Convenience methods for common events --------------------------------

    async def log_auth_success(
        self,
        *,
        source_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        api_key_id: str | None = None,
        user_id: str | None = None,
        method: str = "api_key",
    ) -> str:
        return await self.log(
            EventType.AUTH_SUCCESS,
            source_ip=source_ip,
            user_agent=user_agent,
            request_id=request_id,
            api_key_id=api_key_id,
            user_id=user_id,
            details={"method": method},
        )

    async def log_auth_failure(
        self,
        *,
        source_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        reason: str = "invalid_credentials",
    ) -> str:
        return await self.log(
            EventType.AUTH_FAILURE,
            source_ip=source_ip,
            user_agent=user_agent,
            request_id=request_id,
            details={"reason": reason},
        )

    async def log_rate_limit(
        self,
        *,
        source_ip: str | None = None,
        request_id: str | None = None,
        identifier: str = "",
        retry_after: int = 0,
    ) -> str:
        return await self.log(
            EventType.RATE_LIMIT_EXCEEDED,
            source_ip=source_ip,
            request_id=request_id,
            details={
                "identifier": identifier,
                "retry_after": retry_after,
            },
        )

    async def log_suspicious_input(
        self,
        *,
        source_ip: str | None = None,
        request_id: str | None = None,
        input_type: str = "",
        patterns: list[str] | None = None,
        raw_preview: str = "",
    ) -> str:
        return await self.log(
            EventType.SUSPICIOUS_INPUT,
            severity=EventSeverity.WARNING,
            source_ip=source_ip,
            request_id=request_id,
            details={
                "input_type": input_type,
                "patterns": patterns or [],
                "raw_preview": raw_preview[:200],
            },
        )

    async def log_secret_access(
        self,
        *,
        source_ip: str | None = None,
        request_id: str | None = None,
        secret_key: str = "",
        user_id: str | None = None,
        action: str = "read",
    ) -> str:
        # Never log the actual secret value
        return await self.log(
            EventType.SECRET_ACCESS,
            source_ip=source_ip,
            request_id=request_id,
            user_id=user_id,
            details={
                "secret_key": secret_key,
                "action": action,
            },
        )

    async def log_config_change(
        self,
        *,
        source_ip: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        config_key: str = "",
        old_value_redacted: str = "***",
        new_value_redacted: str = "***",
    ) -> str:
        return await self.log(
            EventType.CONFIG_CHANGE,
            source_ip=source_ip,
            request_id=request_id,
            user_id=user_id,
            details={
                "config_key": config_key,
                "old_value": old_value_redacted,
                "new_value": new_value_redacted,
            },
        )

    async def log_ip_blocked(
        self,
        *,
        source_ip: str | None = None,
        request_id: str | None = None,
        path: str = "",
    ) -> str:
        return await self.log(
            EventType.IP_BLOCKED,
            source_ip=source_ip,
            request_id=request_id,
            details={"path": path},
        )

    # -- Query helpers --------------------------------------------------------

    async def get_recent_events(
        self,
        *,
        event_type: EventType | str | None = None,
        severity: EventSeverity | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch recent security events from the database."""
        if not self._pool:
            return []

        conditions: list[str] = []
        params: list[Any] = []
        param_idx = 1

        if event_type:
            et = event_type.value if isinstance(event_type, EventType) else event_type
            conditions.append(f"event_type = ${param_idx}")
            params.append(et)
            param_idx += 1

        if severity:
            sv = severity.value if isinstance(severity, EventSeverity) else severity
            conditions.append(f"severity = ${param_idx}")
            params.append(sv)
            param_idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.extend([limit, offset])
        query = f"""
            SELECT event_id, event_type, severity, source_ip, user_agent,
                   request_id, api_key_id, details, created_at
            FROM cineos_audit.security_events
            {where}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]

    async def count_events(
        self,
        *,
        event_type: EventType | str | None = None,
        since: datetime | None = None,
    ) -> int:
        """Count security events, optionally filtered."""
        if not self._pool:
            return 0

        conditions: list[str] = []
        params: list[Any] = []
        param_idx = 1

        if event_type:
            et = event_type.value if isinstance(event_type, EventType) else event_type
            conditions.append(f"event_type = ${param_idx}")
            params.append(et)
            param_idx += 1

        if since:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(since)
            param_idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT COUNT(*) as cnt FROM cineos_audit.security_events {where}",
                *params,
            )

        return row["cnt"] if row else 0
