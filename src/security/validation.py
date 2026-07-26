"""Input validation — request schemas, sanitisation, file-type checks, prompt safety."""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, UploadFile, status
from jsonschema import Draft7Validator, ValidationError

logger = logging.getLogger("cineos.security.validation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SQL_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|GRANT|REVOKE)\b)", re.IGNORECASE),
    re.compile(r"(--|;|'|\"|\bOR\b\s+\b\d+\b\s*=\s*\b\d+\b)", re.IGNORECASE),
    re.compile(r"(\/\*|\*\/|xp_cmdshell|sp_executesql)", re.IGNORECASE),
    re.compile(r"(\bWAITFOR\b\s+\bDELAY\b)", re.IGNORECASE),
    re.compile(r"(\bBENCHMARK\b\s*\(|\bSLEEP\b\s*\()", re.IGNORECASE),
]

_XSS_PATTERNS: list[re.Pattern] = [
    re.compile(r"<\s*script[\s>]", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"<\s*(iframe|object|embed|form|input|button|link|meta|base)\b", re.IGNORECASE),
    re.compile(r"data\s*:\s*text/html", re.IGNORECASE),
    re.compile(r"<\s*svg\s+onload", re.IGNORECASE),
]

_PATH_TRAVERSAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.\.[\/\\]"),
    re.compile(r"%2e%2e[\/\\]", re.IGNORECASE),
    re.compile(r"\.\.%2f", re.IGNORECASE),
    re.compile(r"\.\.%5c", re.IGNORECASE),
]

_ALLOWED_UPLOAD_EXTENSIONS: dict[str, set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"},
    "video": {".mp4", ".webm", ".avi", ".mov", ".mkv"},
    "document": {".txt", ".md", ".json", ".csv", ".pdf"},
}

_MAX_FILE_SIZES: dict[str, int] = {
    "image": 20 * 1024 * 1024,       # 20 MB
    "audio": 100 * 1024 * 1024,      # 100 MB
    "video": 500 * 1024 * 1024,      # 500 MB
    "document": 10 * 1024 * 1024,    # 10 MB
}


# ---------------------------------------------------------------------------
# Request Validator
# ---------------------------------------------------------------------------

class RequestValidator:
    """Validates incoming request bodies against JSON Schema (Draft 7)."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema
        self._validator = Draft7Validator(schema)

    @classmethod
    def from_file(cls, path: str | Path) -> "RequestValidator":
        with open(path, "r") as fh:
            schema = json.load(fh)
        return cls(schema)

    def validate(self, data: dict[str, Any]) -> list[str]:
        """Return a list of human-readable validation error strings.

        An empty list means the data is valid.
        """
        errors: list[str] = []
        for error in sorted(self._validator.iter_errors(data), key=lambda e: list(e.path)):
            path = ".".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"[{path}] {error.message}")
        return errors

    def validate_or_raise(self, data: dict[str, Any]) -> None:
        """Validate and raise ``HTTPException(422)`` if invalid."""
        errors = self.validate(data)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Validation failed",
                    "violations": errors,
                },
            )

    def validate_batch(
        self,
        items: list[dict[str, Any]],
    ) -> dict[int, list[str]]:
        """Validate a list of items.  Returns {index: [errors]} for invalid items."""
        results: dict[int, list[str]] = {}
        for idx, item in enumerate(items):
            errors = self.validate(item)
            if errors:
                results[idx] = errors
        return results


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

class Sanitizer:
    """General-purpose input sanitisation (SQL injection, XSS, path traversal)."""

    def __init__(
        self,
        *,
        max_length: int = 50_000,
        strip_null_bytes: bool = True,
    ) -> None:
        self._max_length = max_length
        self._strip_null_bytes = strip_null_bytes

    # -- SQL injection --------------------------------------------------------

    def detect_sql_injection(self, value: str) -> list[str]:
        """Return a list of SQL-injection pattern matches."""
        matches: list[str] = []
        for pattern in _SQL_INJECTION_PATTERNS:
            found = pattern.findall(value)
            if found:
                matches.extend(str(m) for m in found)
        return matches

    def check_sql_injection(self, value: str) -> None:
        """Raise ``HTTPException(400)`` if SQL-injection patterns are detected."""
        matches = self.detect_sql_injection(value)
        if matches:
            logger.warning("SQL injection attempt detected: patterns=%s", matches)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Potentially malicious input detected (SQL injection)",
            )

    # -- XSS -----------------------------------------------------------------

    def detect_xss(self, value: str) -> list[str]:
        matches: list[str] = []
        for pattern in _XSS_PATTERNS:
            found = pattern.findall(value)
            if found:
                matches.extend(str(m) for m in found)
        return matches

    def check_xss(self, value: str) -> None:
        matches = self.detect_xss(value)
        if matches:
            logger.warning("XSS attempt detected: patterns=%s", matches)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Potentially malicious input detected (XSS)",
            )

    # -- Path traversal -------------------------------------------------------

    def detect_path_traversal(self, value: str) -> bool:
        return any(p.search(value) for p in _PATH_TRAVERSAL_PATTERNS)

    def check_path_traversal(self, value: str) -> None:
        if self.detect_path_traversal(value):
            logger.warning("Path traversal attempt detected: value_length=%d", len(value))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Potentially malicious input detected (path traversal)",
            )

    # -- Combined sanitisation ------------------------------------------------

    def sanitize(self, value: str) -> str:
        """Apply all sanitisation steps and return the cleaned string."""
        if self._strip_null_bytes:
            value = value.replace("\x00", "")

        value = value.strip()

        if len(value) > self._max_length:
            value = value[: self._max_length]

        # Normalise unicode to prevent homoglyph attacks
        value = unicodedata.normalize("NFC", value)

        # HTML-escape dangerous characters for safe output
        value = (
            value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

        return value

    def sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively sanitise all string values in a dict."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            clean_key = self.sanitize(str(key))
            if isinstance(value, str):
                self.check_sql_injection(value)
                self.check_xss(value)
                result[clean_key] = self.sanitize(value)
            elif isinstance(value, dict):
                result[clean_key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[clean_key] = self.sanitize_list(value)
            else:
                result[clean_key] = value
        return result

    def sanitize_list(self, items: list[Any]) -> list[Any]:
        result: list[Any] = []
        for item in items:
            if isinstance(item, str):
                self.check_sql_injection(item)
                self.check_xss(item)
                result.append(self.sanitize(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            else:
                result.append(item)
        return result

    def validate_all(self, data: dict[str, Any]) -> dict[str, Any]:
        """Full pipeline: detect + sanitize.  Raises on threats, returns clean dict."""
        self.sanitize_dict(data)
        return data


# ---------------------------------------------------------------------------
# File Type Validator
# ---------------------------------------------------------------------------

class FileTypeValidator:
    """Validates uploaded file types via extension and magic bytes, and enforces size limits."""

    # Magic-byte signatures (first bytes of file)
    _MAGIC_BYTES: dict[str, list[tuple[bytes, int]]] = {
        ".jpg":  [(b"\xff\xd8\xff", 0)],
        ".jpeg": [(b"\xff\xd8\xff", 0)],
        ".png":  [(b"\x89PNG\r\n\x1a\n", 0)],
        ".gif":  [(b"GIF87a", 0), (b"GIF89a", 0)],
        ".webp": [(b"RIFF", 0)],
        ".bmp":  [(b"BM", 0)],
        ".mp3":  [(b"\xff\xfb", 0), (b"\xff\xf3", 0), (b"\xff\xf2", 0), (b"ID3", 0)],
        ".wav":  [(b"RIFF", 0)],
        ".ogg":  [(b"OggS", 0)],
        ".flac": [(b"fLaC", 0)],
        ".mp4":  [(b"\x00\x00\x00", 0)],
        ".webm": [(b"\x1a\x45\xdf\xa3", 0)],
        ".pdf":  [(b"%PDF", 0)],
    }

    def __init__(
        self,
        allowed_categories: list[str] | None = None,
        *,
        max_size_override: dict[str, int] | None = None,
    ) -> None:
        self._allowed_categories = set(allowed_categories or ["image", "audio", "video", "document"])
        self._max_sizes = {**_MAX_FILE_SIZES}
        if max_size_override:
            self._max_sizes.update(max_size_override)

    def _category_for(self, ext: str) -> Optional[str]:
        for cat, exts in _ALLOWED_UPLOAD_EXTENSIONS.items():
            if ext in exts:
                return cat
        return None

    def _allowed_extensions(self) -> set[str]:
        result: set[str] = set()
        for cat in self._allowed_categories:
            result |= _ALLOWED_UPLOAD_EXTENSIONS.get(cat, set())
        return result

    async def validate(self, file: UploadFile) -> dict[str, Any]:
        """Validate file extension, magic bytes, and size.

        Returns a dict with validation metadata on success.
        Raises ``HTTPException(400/413)`` on failure.
        """
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        # Extension check
        allowed = self._allowed_extensions()
        if ext not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '{ext}' is not allowed. Accepted: {sorted(allowed)}",
            )

        category = self._category_for(ext)

        # Read content for magic-byte + size validation
        content = await file.read()
        file_size = len(content)

        # Size check
        max_size = self._max_sizes.get(category or "document", 10 * 1024 * 1024)
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large: {file_size} bytes (max {max_size} for {category})",
            )

        # Magic-byte check (only for known extensions)
        if ext in self._MAGIC_BYTES:
            valid_signatures = self._MAGIC_BYTES[ext]
            matches = any(
                content[offset: offset + len(sig)] == sig
                for sig, offset in valid_signatures
            )
            if not matches and file_size > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File content does not match extension '{ext}' (magic byte mismatch)",
                )

        # Reset file position for downstream consumption
        await file.seek(0)

        return {
            "filename": filename,
            "extension": ext,
            "category": category,
            "size_bytes": file_size,
            "valid": True,
        }


# ---------------------------------------------------------------------------
# Prompt Sanitiser
# ---------------------------------------------------------------------------

class PromptSanitizer:
    """Sanitises LLM prompt inputs to prevent injection and abuse.

    LLM prompt injection is a distinct threat model from traditional SQL/XSS.
    This class strips control characters, enforces length limits, and blocks
    known prompt-escape sequences.
    """

    _PROMPT_ESCAPE_PATTERNS: list[re.Pattern] = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE),
        re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>", re.IGNORECASE),
        re.compile(r"###\s*(System|Instruction|Prompt)\s*:", re.IGNORECASE),
    ]

    def __init__(
        self,
        *,
        max_length: int = 10_000,
        allow_special_tokens: bool = False,
    ) -> None:
        self._max_length = max_length
        self._allow_special_tokens = allow_special_tokens

    def detect_injection(self, prompt: str) -> list[str]:
        """Return list of detected prompt-injection patterns."""
        matches: list[str] = []
        for pattern in self._PROMPT_ESCAPE_PATTERNS:
            found = pattern.findall(prompt)
            if found:
                matches.extend(str(m) for m in found)
        return matches

    def sanitize(self, prompt: str) -> str:
        """Sanitise a prompt string and return the cleaned version.

        Raises ``HTTPException(400)`` if injection is detected or input is invalid.
        """
        if not prompt or not prompt.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt must not be empty",
            )

        # Strip null bytes and control characters
        cleaned = prompt.replace("\x00", "")
        if not self._allow_special_tokens:
            cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

        # Normalise whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Length enforcement
        if len(cleaned) > self._max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt exceeds maximum length of {self._max_length} characters",
            )

        # Injection detection
        injections = self.detect_injection(cleaned)
        if injections:
            logger.warning("Prompt injection detected: patterns=%s", injections)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt contains potential injection patterns",
            )

        return cleaned

    def sanitize_batch(self, prompts: list[str]) -> list[str]:
        """Sanitise multiple prompts, returning cleaned list or raising on first error."""
        return [self.sanitize(p) for p in prompts]
