"""Phase 1 — Intake: receive, validate, normalize novel text."""
from __future__ import annotations
import logging
import re
import unicodedata
from pathlib import Path

from .contracts import NovelText

logger = logging.getLogger(__name__)


class IntakeError(Exception):
    pass


async def phase1_intake(file_path: str) -> NovelText:
    """Validate and load a novel file.

    Hard gate: raises IntakeError on any validation failure.
    """
    path = Path(file_path)

    # ── Gate: file exists ──
    if not path.exists():
        raise IntakeError(f"File not found: {file_path}")

    # ── Gate: file extension ──
    if path.suffix.lower() not in (".txt", ".text"):
        raise IntakeError(f"Unsupported file type: {path.suffix}. Only .txt accepted.")

    # ── Gate: file size ──
    size = path.stat().st_size
    if size == 0:
        raise IntakeError("File is empty.")
    if size > 10_000_000:  # 10 MB
        raise IntakeError(f"File too large: {size // 1024}KB. Maximum 10MB.")

    # ── Gate: encoding ──
    raw = None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1256", "iso-8859-6"):
        try:
            raw = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if raw is None:
        raise IntakeError("Cannot detect file encoding. Save as UTF-8.")

    # ── Gate: content is readable text ──
    if len(raw.strip()) == 0:
        raise IntakeError("File contains no readable text.")

    # ── Detect language ──
    language = _detect_language(raw)

    # ── Normalize ──
    cleaned = _normalize_text(raw, language)

    # ── Gate: minimum length ──
    word_count = len(cleaned.split())
    if word_count < 50:
        raise IntakeError(f"Text too short: {word_count} words. Minimum 50 words.")

    # ── Extract title ──
    title = _extract_title(cleaned, path.stem)

    result = NovelText(
        raw=raw,
        cleaned=cleaned,
        title=title,
        word_count=word_count,
        char_count=len(cleaned),
        encoding="utf-8",
        language=language,
    )

    logger.info(
        f"Intake OK: {title} | {word_count} words | lang={language} | {len(cleaned)} chars"
    )
    return result


def _detect_language(text: str) -> str:
    sample = text[:5000]
    arabic_chars = sum(1 for c in sample if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F")
    latin_chars = sum(1 for c in sample if c.isascii() and c.isalpha())
    total = max(arabic_chars + latin_chars, 1)
    arabic_ratio = arabic_chars / total
    if arabic_ratio > 0.5:
        return "ar"
    elif arabic_ratio > 0.1:
        return "mixed"
    return "en"


def _normalize_text(text: str, language: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title(text: str, fallback: str) -> str:
    first_lines = text[:500].split("\n")
    for line in first_lines:
        line = line.strip()
        if line and len(line) < 100:
            return line
    return fallback
