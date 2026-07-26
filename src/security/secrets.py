"""Secret management — environment-based loading, encrypted fields, rotation, log safety."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("cineos.security.secrets")

# ---------------------------------------------------------------------------
# Log-safety: redact secrets that accidentally appear in log output
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:token|secret|key)\s*[=:]\s*['\"]?\S{8,}['\"]?", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|access[_-]?key)\s*[=:]\s*['\"]?\S{8,}['\"]?", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(?:cineos_)['\"]?\S{10,}", re.IGNORECASE),
]

_REDACTED = "***REDACTED***"


class _SafeLogFilter(logging.Filter):
    """Logging filter that redacts potential secrets from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(
                self._redact(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True

    @staticmethod
    def _redact(text: str) -> str:
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub(_REDACTED, text)
        return text


def install_log_filter() -> None:
    """Install the secret-redaction filter on the root logger."""
    root = logging.getLogger()
    for f in root.filters:
        if isinstance(f, _SafeLogFilter):
            return
    root.addFilter(_SafeLogFilter())


install_log_filter()


# ---------------------------------------------------------------------------
# Secret Manager
# ---------------------------------------------------------------------------

class SecretManager:
    """Loads secrets exclusively from environment variables.

    No secrets are stored on disk or in the database.  The manager validates
    that all required secrets are present at startup and provides typed access.
    """

    _instance: Optional["SecretManager"] = None
    _lock = threading.Lock()

    def __init__(self, required_keys: list[str] | None = None) -> None:
        self._required = required_keys or []
        self._cache: dict[str, str] = {}
        self._loaded = False
        self._rotation_versions: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    def get_instance(cls) -> "SecretManager":
        """Singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def load(self) -> None:
        """Load and validate all required secrets from environment.

        Raises ``RuntimeError`` if any required secret is missing.
        """
        self._cache.clear()

        # Core CineOS secrets
        standard_keys = [
            "POSTGRES_PASSWORD",
            "REDIS_HOST",
            "N8N_API_KEY",
            "N8N_ENCRYPTION_KEY",
            "TELEGRAM_BOT_TOKEN",
            "OPENROUTER_API_KEY",
            "HF_API_KEY",
            "COMFYUI_HOST",
            "CINEOS_API_KEY_SALT",
            "CINEOS_WEBHOOK_SECRET",
        ]

        all_keys = list(set(standard_keys + self._required))
        missing: list[str] = []

        for key in all_keys:
            value = os.environ.get(key)
            if value:
                self._cache[key] = value
            elif key in self._required:
                missing.append(key)

        if missing:
            raise RuntimeError(
                f"Missing required secrets: {', '.join(missing)}. "
                "Set them in your environment or .env file."
            )

        self._loaded = True
        logger.info(
            "Secrets loaded: %d available, %d required, %d missing",
            len(self._cache),
            len(self._required),
            len(missing),
        )

    def get(
        self,
        key: str,
        *,
        default: str | None = None,
        required: bool = False,
    ) -> str | None:
        """Retrieve a secret by key name."""
        value = self._cache.get(key) or os.environ.get(key)
        if value is None and required:
            raise RuntimeError(f"Required secret '{key}' is not set")
        return value or default

    def get_int(self, key: str, *, default: int = 0, required: bool = False) -> int:
        raw = self.get(key, required=required)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise RuntimeError(f"Secret '{key}' is not a valid integer")

    def get_bool(self, key: str, *, default: bool = False) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return raw.lower() in ("true", "1", "yes", "on")

    def list_keys(self, *, redacted: bool = True) -> dict[str, str]:
        """Return all loaded keys (values redacted by default)."""
        return {
            k: _REDACTED if redacted else v
            for k, v in {**self._cache, **{
                k: v for k, v in os.environ.items()
                if k in self._required
            }}.items()
        }

    # -- Secret rotation support ----------------------------------------------

    def record_rotation(
        self,
        key: str,
        *,
        rotated_by: str = "system",
        reason: str = "",
    ) -> None:
        """Record that a secret was rotated.  Called after env var update."""
        if key not in self._rotation_versions:
            self._rotation_versions[key] = []

        self._rotation_versions[key].append({
            "rotated_at": datetime.now(timezone.utc).isoformat(),
            "rotated_by": rotated_by,
            "reason": reason,
        })

        # Refresh cache
        new_value = os.environ.get(key)
        if new_value:
            self._cache[key] = new_value

        logger.info("Secret '%s' rotated by %s", key, rotated_by)

    def rotation_history(self, key: str) -> list[dict[str, Any]]:
        return list(self._rotation_versions.get(key, []))

    def validate_no_secrets_in_string(self, text: str) -> bool:
        """Return True if *text* does NOT contain any known secret values."""
        all_values = list(self._cache.values())
        for secret_val in all_values:
            if len(secret_val) >= 4 and secret_val in text:
                return False
        return True


# ---------------------------------------------------------------------------
# Encrypted Field
# ---------------------------------------------------------------------------

class EncryptedField:
    """Transparently encrypt/decrypt values for storage in the database.

    Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
    The encryption key is derived from the ``CINEOS_ENCRYPTION_KEY``
    environment variable via PBKDF2.
    """

    def __init__(self, env_key: str = "CINEOS_ENCRYPTION_KEY") -> None:
        raw_key = os.environ.get(env_key)
        if not raw_key:
            # Generate a ephemeral key — data won't survive restarts.
            # This is acceptable for development; production MUST set the env var.
            logger.warning(
                "%s not set — using ephemeral encryption key. "
                "Encrypted data will NOT persist across restarts.",
                env_key,
            )
            raw_key = secrets.token_hex(32)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"cineos-encrypted-field-v1",
            iterations=480_000,
        )
        derived = base64.urlsafe_b64encode(kdf.derive(raw_key.encode()))
        self._fernet = Fernet(derived)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string.  Returns a base64-encoded ciphertext token."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext token.  Returns the plaintext string."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def is_encrypted(self, value: str) -> bool:
        """Heuristic: Fernet tokens start with ``gAAAAA``."""
        return value.startswith("gAAAAA")

    def encrypt_if_needed(self, value: str) -> str:
        """Encrypt only if not already encrypted (idempotent)."""
        if self.is_encrypted(value):
            return value
        return self.encrypt(value)

    def decrypt_if_needed(self, value: str) -> str:
        """Decrypt only if encrypted (idempotent)."""
        if self.is_encrypted(value):
            return self.decrypt(value)
        return value

    def rotate_key(
        self,
        ciphertext: str,
        *,
        old_env_key: str = "CINEOS_ENCRYPTION_KEY",
        new_env_key: str = "CINEOS_ENCRYPTION_KEY",
    ) -> str:
        """Re-encrypt a value with a new key.

        Decrypts with the old key and encrypts with the new key.  Callers
        should ensure the new env var is set before invoking this.
        """
        old_kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"cineos-encrypted-field-v1",
            iterations=480_000,
        )
        old_raw = os.environ.get(old_env_key, "")
        old_derived = base64.urlsafe_b64encode(old_kdf.derive(old_raw.encode()))
        old_fernet = Fernet(old_derived)

        plaintext = old_fernet.decrypt(ciphertext.encode()).decode()

        new_raw = os.environ.get(new_env_key, "")
        if not new_raw:
            raise RuntimeError(f"New encryption key '{new_env_key}' is not set")

        new_kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"cineos-encrypted-field-v1",
            iterations=480_000,
        )
        new_derived = base64.urlsafe_b64encode(new_kdf.derive(new_raw.encode()))
        new_fernet = Fernet(new_derived)

        return new_fernet.encrypt(plaintext.encode()).decode()
