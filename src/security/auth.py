"""Authentication module — API keys, bearer tokens, webhooks, rate limiting, idempotency."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import asyncpg
import redis.asyncio as redis
from fastapi import HTTPException, Request, status


class AuthScheme(str, Enum):
    API_KEY = "api_key"
    BEARER = "bearer"


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

@dataclass
class _APIKeyRecord:
    key_id: str
    key_hash: str
    scopes: list[str]
    rate_limit: int
    active: bool
    expires_at: Optional[datetime] = None


class APIKeyAuth:
    """X-API-Key header authentication backed by asyncpg."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        header: str = "X-API-Key",
        *,
        hash_iterations: int = 100_000,
    ) -> None:
        self._pool = pool
        self._header = header
        self._hash_iterations = hash_iterations
        self._cache: dict[str, tuple[float, _APIKeyRecord]] = {}
        self._cache_ttl = 300.0  # seconds

    # -- helpers --------------------------------------------------------------

    def _hash_key(self, raw_key: str) -> str:
        salt = os.environ.get("CINEOS_API_KEY_SALT", "")
        return hashlib.pbkdf2_hmac(
            "sha256",
            raw_key.encode(),
            salt.encode(),
            self._hash_iterations,
        ).hex()

    def _get_key_id_prefix(self, raw_key: str) -> str:
        return raw_key[:8] if len(raw_key) >= 8 else raw_key

    # -- public API -----------------------------------------------------------

    async def create_key(
        self,
        *,
        scopes: list[str] | None = None,
        rate_limit: int = 60,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate and persist a new API key. Returns dict with *plaintext* key."""
        raw_key = "cineos_" + secrets.token_urlsafe(32)
        key_id = self._get_key_id_prefix(raw_key)
        key_hash = self._hash_key(raw_key)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cineos_core.api_keys
                    (key_id, key_hash, scopes, rate_limit, active, expires_at, created_at)
                VALUES ($1, $2, $3, $4, TRUE, $5, NOW())
                """,
                key_id,
                key_hash,
                scopes or ["read"],
                rate_limit,
                expires_at,
            )

        return {
            "key_id": key_id,
            "key": raw_key,
            "scopes": scopes or ["read"],
            "rate_limit": rate_limit,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

    async def revoke_key(self, key_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE cineos_core.api_keys SET active = FALSE WHERE key_id = $1",
                key_id,
            )
        self._cache.pop(key_id, None)

    async def authenticate(self, request: Request) -> _APIKeyRecord:
        """Validate the X-API-Key header and return the key record.

        Raises ``HTTPException(401)`` on failure.
        """
        raw_key = request.headers.get(self._header)
        if not raw_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Missing {self._header} header",
            )

        key_id = self._get_key_id_prefix(raw_key)
        record = await self._get_record(key_id)

        if record is None:
            # Constant-time comparison against dummy hash to prevent timing attacks
            _dummy = hashlib.sha256(b"").hexdigest()
            hmac.compare_digest(self._hash_key(raw_key), _dummy)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        if not record.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is revoked",
            )

        if record.expires_at and record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
            )

        if not hmac.compare_digest(self._hash_key(raw_key), record.key_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return record

    async def _get_record(self, key_id: str) -> Optional[_APIKeyRecord]:
        now = time.monotonic()
        cached = self._cache.get(key_id)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT key_id, key_hash, scopes, rate_limit, active, expires_at
                FROM cineos_core.api_keys
                WHERE key_id = $1
                """,
                key_id,
            )

        if row is None:
            return None

        record = _APIKeyRecord(
            key_id=row["key_id"],
            key_hash=row["key_hash"],
            scopes=row["scopes"],
            rate_limit=row["rate_limit"],
            active=row["active"],
            expires_at=row["expires_at"],
        )
        self._cache[key_id] = (now, record)
        return record

    def require_scopes(self, record: _APIKeyRecord, required: list[str]) -> None:
        """Raise 403 if *record* lacks any of *required* scopes."""
        if not set(required).issubset(set(record.scopes)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {set(required) - set(record.scopes)}",
            )


# ---------------------------------------------------------------------------
# Bearer Token Authentication
# ---------------------------------------------------------------------------

class BearerTokenAuth:
    """JWT-like bearer token authentication.

    Tokens are opaque strings managed by an external identity provider or the
    API key system above.  This class validates them against a Redis allowlist
    and/or a database lookup.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        redis_client: redis.Redis | None = None,
        header: str = "Authorization",
    ) -> None:
        self._pool = pool
        self._redis = redis_client
        self._header = header
        self._revoked_prefix = "cineos:auth:revoked:"

    async def create_session(
        self,
        *,
        user_id: str,
        scopes: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Issue a new bearer token."""
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cineos_core.auth_sessions
                    (token_hash, user_id, scopes, active, expires_at, created_at)
                VALUES ($1, $2, $3, TRUE, NOW() + ($4 || ' seconds')::INTERVAL, NOW())
                """,
                token_hash,
                user_id,
                scopes or ["read"],
                str(ttl_seconds),
            )

        if self._redis:
            await self._redis.setex(
                f"cineos:auth:session:{token_hash}",
                ttl_seconds,
                user_id,
            )

        return {
            "token": token,
            "user_id": user_id,
            "scopes": scopes or ["read"],
            "expires_in": ttl_seconds,
        }

    async def revoke_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE cineos_core.auth_sessions SET active = FALSE WHERE token_hash = $1",
                token_hash,
            )
        if self._redis:
            await self._redis.delete(f"cineos:auth:session:{token_hash}")
            await self._redis.setex(f"{self._revoked_prefix}{token_hash}", 86400, "1")

    async def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate bearer token.  Returns session dict with *user_id* and *scopes*."""
        auth_header = request.headers.get(self._header)
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed Authorization header",
            )

        token = auth_header[7:]
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Check revocation via Redis first
        if self._redis:
            if await self._redis.exists(f"{self._revoked_prefix}{token_hash}"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT token_hash, user_id, scopes, active, expires_at
                FROM cineos_core.auth_sessions
                WHERE token_hash = $1
                """,
                token_hash,
            )

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            )

        if not row["active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
            )

        if row["expires_at"] and row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )

        return {
            "user_id": row["user_id"],
            "scopes": row["scopes"],
            "token_hash": token_hash,
        }


# ---------------------------------------------------------------------------
# Webhook Signature Validator
# ---------------------------------------------------------------------------

class WebhookSignatureValidator:
    """HMAC-SHA256 webhook signature validation (e.g. Stripe / n8n style)."""

    def __init__(
        self,
        secret_env_var: str = "CINEOS_WEBHOOK_SECRET",
        signature_header: str = "X-Webhook-Signature",
        tolerance_seconds: int = 300,
    ) -> None:
        self._secret_env_var = secret_env_var
        self._signature_header = signature_header
        self._tolerance = tolerance_seconds

    @property
    def _secret(self) -> bytes:
        secret = os.environ.get(self._secret_env_var)
        if not secret:
            raise RuntimeError(
                f"Webhook secret not configured — set {self._secret_env_var}"
            )
        return secret.encode()

    def _compute(self, payload: bytes, timestamp: str) -> str:
        signed_payload = f"{timestamp}.{payload.decode('utf-8', errors='replace')}"
        return hmac.new(
            self._secret,
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def validate(self, request: Request, body: bytes) -> dict[str, Any]:
        """Validate the webhook signature.

        Expected header format: ``<timestamp>.<hex-signature>`` or
        ``sha256=<hex-signature>`` with a separate ``X-Webhook-Timestamp`` header.

        Returns a dict with validation metadata on success.
        Raises ``HTTPException(401)`` on failure.
        """
        sig_header = request.headers.get(self._signature_header, "")
        timestamp = request.headers.get("X-Webhook-Timestamp", "")

        # Format 1: combined "timestamp.signature"
        if "." in sig_header:
            parts = sig_header.split(".", 1)
            timestamp = parts[0]
            expected_sig = parts[1]
        # Format 2: "sha256=<hex>" with separate timestamp
        elif sig_header.startswith("sha256="):
            expected_sig = sig_header[7:]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed webhook signature",
            )

        # Timestamp tolerance check
        if timestamp:
            try:
                ts = float(timestamp)
                if abs(time.time() - ts) > self._tolerance:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Webhook timestamp outside tolerance window",
                    )
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook timestamp",
                )

        computed = self._compute(body, timestamp)

        if not hmac.compare_digest(computed, expected_sig):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        return {"valid": True, "timestamp": timestamp}


# ---------------------------------------------------------------------------
# Token-Bucket Rate Limiter (Redis-backed)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Per-IP / per-key token-bucket rate limiting via Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        default_rate: int = 60,
        default_burst: int = 10,
        key_prefix: str = "cineos:ratelimit:",
    ) -> None:
        self._redis = redis_client
        self._default_rate = default_rate  # tokens per minute
        self._default_burst = default_burst
        self._key_prefix = key_prefix

    def _bucket_key(self, identifier: str) -> str:
        return f"{self._key_prefix}{identifier}"

    async def check(
        self,
        identifier: str,
        *,
        rate: int | None = None,
        burst: int | None = None,
    ) -> dict[str, Any]:
        """Attempt to consume one token.

        Returns ``{"allowed": True, "remaining": N, "retry_after": 0}``
        or ``{"allowed": False, "remaining": 0, "retry_after": N}``.
        """
        rate = rate or self._default_rate
        burst = burst or self._default_burst
        key = self._bucket_key(identifier)

        now = time.time()
        refill_interval = 60.0 / rate

        # Lua script for atomic token-bucket refill + consume
        lua = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1])
        local last_refill = tonumber(bucket[2])

        if tokens == nil then
            tokens = capacity - 1
            last_refill = now
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
            redis.call('EXPIRE', key, ttl)
            return {1, tokens, 0}
        end

        local elapsed = now - last_refill
        local refill = math.floor(elapsed * refill_rate / 60)
        if refill > 0 then
            tokens = math.min(capacity, tokens + refill)
            last_refill = now
        end

        if tokens <= 0 then
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
            redis.call('EXPIRE', key, ttl)
            local retry_after = math.ceil((1 - tokens) / refill_rate * 60)
            return {0, tokens, retry_after}
        end

        tokens = tokens - 1
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
        redis.call('EXPIRE', key, ttl)
        return {1, tokens, 0}
        """
        result = await self._redis.eval(
            lua,
            1,
            key,
            burst,
            rate,
            now,
            120,  # TTL in seconds
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        retry_after = int(result[2])

        return {
            "allowed": allowed,
            "remaining": remaining,
            "retry_after": retry_after,
            "limit": burst,
            "rate": rate,
        }

    async def remaining(self, identifier: str) -> int:
        """Return remaining tokens without consuming."""
        key = self._bucket_key(identifier)
        tokens = await self._redis.hget(key, "tokens")
        return int(tokens) if tokens else self._default_burst


# ---------------------------------------------------------------------------
# Idempotency Key Checker (Redis-backed)
# ---------------------------------------------------------------------------

class IdempotencyChecker:
    """Prevents duplicate processing of requests via idempotency keys.

    Stores a fingerprint of the request and its result in Redis.  If the same
    idempotency key is submitted again within *ttl_seconds*, the cached result
    is returned instead of re-executing the handler.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_seconds: int = 3600,
        key_prefix: str = "cineos:idempotency:",
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, idempotency_key: str) -> str:
        return f"{self._key_prefix}{idempotency_key}"

    async def check(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Return cached result if this key was already processed."""
        raw = await self._redis.get(self._key(idempotency_key))
        if raw is None:
            return None
        import json
        return json.loads(raw)

    async def store(
        self,
        idempotency_key: str,
        result: dict[str, Any],
        *,
        status_code: int = 200,
    ) -> None:
        import json
        payload = json.dumps({
            "status_code": status_code,
            "body": result,
        })
        await self._redis.setex(self._key(idempotency_key), self._ttl, payload)

    async def remove(self, idempotency_key: str) -> None:
        await self._redis.delete(self._key(idempotency_key))
