"""FastAPI middleware — security headers, request logging, rate limiting, request IDs, IP whitelist."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger("cineos.security.middleware")


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------

class SecurityMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every response.

    Headers:
        - Content-Security-Policy
        - Strict-Transport-Security (HSTS)
        - X-Content-Type-Options
        - X-Frame-Options
        - X-XSS-Protection
        - Referrer-Policy
        - Permissions-Policy
        - Cache-Control (no-store for API)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        csp: str | None = None,
        hsts_max_age: int = 31_536_000,
        frame_options: str = "DENY",
        referrer_policy: str = "strict-origin-when-cross-origin",
    ) -> None:
        super().__init__(app)
        self._csp = csp or (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        self._hsts_max_age = hsts_max_age
        self._frame_options = frame_options
        self._referrer_policy = referrer_policy

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        response.headers["Content-Security-Policy"] = self._csp
        response.headers["Strict-Transport-Security"] = (
            f"max-age={self._hsts_max_age}; includeSubDomains; preload"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = self._frame_options
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = self._referrer_policy
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"

        return response


# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and duration."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        log_request_body: bool = False,
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._log_body = log_request_body
        self._exclude = exclude_paths or {"/health", "/metrics", "/favicon.ico"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self._exclude:
            return await call_next(request)

        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", None) or "-"
        client_ip = request.client.host if request.client else "-"

        body_info = ""
        if self._log_body and request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.body()
                body_info = f" body_size={len(body)}"
            except Exception:
                body_info = " body_size=unknown"

        logger.info(
            "request_started method=%s path=%s client=%s request_id=%s%s",
            request.method,
            request.url.path,
            client_ip,
            request_id,
            body_info,
        )

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_completed method=%s path=%s status=%d duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response


# ---------------------------------------------------------------------------
# Rate Limit Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limits incoming requests using the ``RateLimiter`` from auth module."""

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: "RateLimiter",
        *,
        default_rate: int = 60,
        default_burst: int = 10,
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        from .auth import RateLimiter as _RL
        self._limiter = rate_limiter
        self._default_rate = default_rate
        self._default_burst = default_burst
        self._exclude = exclude_paths or {"/health", "/metrics"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self._exclude:
            return await call_next(request)

        identifier = self._client_identifier(request)
        result = await self._limiter.check(
            identifier,
            rate=self._default_rate,
            burst=self._default_burst,
        )

        if not result["allowed"]:
            logger.warning(
                "rate_limit_exceeded identifier=%s path=%s retry_after=%d",
                identifier,
                request.url.path,
                result["retry_after"],
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after_seconds": result["retry_after"],
                    "limit": result["limit"],
                },
                headers={
                    "Retry-After": str(result["retry_after"]),
                    "X-RateLimit-Limit": str(result["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result["retry_after"]),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result["limit"])
        response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
        return response

    @staticmethod
    def _client_identifier(request: Request) -> str:
        # Prefer forwarded IP from reverse proxy, fall back to direct client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Request ID Middleware
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attaches a unique request ID to every request and response.

    If the client supplies ``X-Request-ID``, it is preserved (for trace
    correlation).  Otherwise a new UUID4 is generated.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header: str = "X-Request-ID",
    ) -> None:
        super().__init__(app)
        self._header = header

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(self._header) or str(uuid.uuid4())

        # Validate format (UUID or alphanumeric with hyphens, max 128 chars)
        if len(request_id) > 128 or not all(
            c.isalnum() or c in "-_" for c in request_id
        ):
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self._header] = request_id
        return response


# ---------------------------------------------------------------------------
# IP Whitelist Middleware
# ---------------------------------------------------------------------------

class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Optional IP whitelisting middleware.

    When enabled, only requests from whitelisted IPs (or CIDR ranges) are
    allowed through.  All other requests receive ``403 Forbidden``.

    Set ``CINEOS_IP_WHITELIST`` env var to a comma-separated list of IPs/CIDRs
    to enable.  If unset, this middleware is a no-op.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        whitelist: list[str] | None = None,
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._whitelist = whitelist or self._load_from_env()
        self._exclude = exclude_paths or set()

    @staticmethod
    def _load_from_env() -> list[str]:
        raw = os.environ.get("CINEOS_IP_WHITELIST", "")
        if not raw:
            return []
        return [ip.strip() for ip in raw.split(",") if ip.strip()]

    @staticmethod
    def _ip_in_cidr(ip: str, cidr: str) -> bool:
        """Simple IP-in-CIDR check using stdlib only."""
        import ipaddress
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return False

    def _is_allowed(self, ip: str) -> bool:
        if not self._whitelist:
            return True  # no whitelist = allow all
        for entry in self._whitelist:
            if "/" in entry:
                if self._ip_in_cidr(ip, entry):
                    return True
            else:
                if ip == entry:
                    return True
        return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self._exclude:
            return await call_next(request)

        client_ip = request.client.host if request.client else None
        if client_ip and not self._is_allowed(client_ip):
            logger.warning(
                "ip_blocked ip=%s path=%s",
                client_ip,
                request.url.path,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Access denied from this IP address"},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Convenience: register all middleware at once
# ---------------------------------------------------------------------------

def register_security_middleware(
    app: FastAPI,
    *,
    rate_limiter: "RateLimiter | None" = None,
    ip_whitelist: list[str] | None = None,
) -> None:
    """Register the full CineOS security middleware stack on a FastAPI app.

    Order matters: middleware is executed in reverse registration order, so
    the *last* registered middleware runs *first* on requests.

    Registration order (executes bottom-up):
        1. IPWhitelistMiddleware   (outermost — blocks bad IPs early)
        2. RateLimitMiddleware
        3. RequestLoggingMiddleware
        4. SecurityMiddleware      (headers)
        5. RequestIdMiddleware     (innermost — ID is available to all others)
    """
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    if rate_limiter:
        app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=rate_limiter,
        )

    if ip_whitelist:
        app.add_middleware(
            IPWhitelistMiddleware,
            whitelist=ip_whitelist,
        )
