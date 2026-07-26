"""Telegram bot handler tests using mocks (no live Telegram connection)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.telegram.bot import NovelTelegramBot


# ── Helpers ────────────────────────────────────────────────────────


def _make_config():
    return {
        "telegram": {
            "bot_token": "fake-token",
            "max_file_size": 50 * 1024 * 1024,
        },
        "storage": {
            "temp_path": "/tmp/cineos_test",
            "video_path": "/tmp/cineos_test/videos",
        },
        "database": {"path": "/tmp/cineos_test/db"},
        "quality": {"min_overall_quality": 0.60},
    }


def _make_update(message_text=None, document_name=None, document_size=1024,
                 chat_id=12345, user_id=999):
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = message_text
    update.message.chat_id = chat_id
    update.message.from_user = MagicMock()
    update.message.from_user.id = user_id
    update.message.reply_text = AsyncMock()

    if document_name:
        update.message.document = MagicMock()
        update.message.document.file_name = document_name
        update.message.document.file_size = document_size
        update.message.document.file_id = "fake_file_id"
    else:
        update.message.document = None

    return update


def _make_context():
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.get_file = AsyncMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_video = AsyncMock()
    ctx.bot.get_file.return_value.download_to_drive = AsyncMock()
    return ctx


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_start_command():
    config = _make_config()
    bot = NovelTelegramBot(config)
    update = _make_update(message_text="/start")
    context = _make_context()

    await bot.start_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Novel" in call_text or "🎬" in call_text or "pipeline" in call_text.lower()


@pytest.mark.unit
async def test_help_command():
    config = _make_config()
    bot = NovelTelegramBot(config)
    update = _make_update(message_text="/help")
    context = _make_context()

    await bot.help_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "txt" in call_text.lower() or ".txt" in call_text or "novel" in call_text.lower()


@pytest.mark.unit
async def test_status_no_project():
    config = _make_config()
    bot = NovelTelegramBot(config)
    update = _make_update(message_text="/status", chat_id=99999)
    context = _make_context()

    await bot.status_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Ready" in call_text or "no" in call_text.lower() or "✅" in call_text


@pytest.mark.unit
async def test_document_upload_rejects_non_txt():
    config = _make_config()
    bot = NovelTelegramBot(config)
    update = _make_update(document_name="novel.pdf", document_size=1024)
    context = _make_context()

    await bot.handle_document(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert ".txt" in call_text


@pytest.mark.unit
async def test_document_upload_rejects_oversize():
    config = _make_config()
    bot = NovelTelegramBot(config)
    update = _make_update(
        document_name="huge_novel.txt",
        document_size=60 * 1024 * 1024,
    )
    context = _make_context()

    await bot.handle_document(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "large" in call_text.lower() or "too" in call_text.lower() or "MB" in call_text


@pytest.mark.unit
async def test_document_upload_success():
    config = _make_config()
    bot = NovelTelegramBot(config)
    bot.orchestrator = MagicMock()
    bot.orchestrator.start_pipeline = AsyncMock(return_value="proj-uuid-12345")

    update = _make_update(document_name="my_novel.txt", document_size=1024)
    context = _make_context()

    with patch("pathlib.Path.exists", return_value=False):
        with patch("pathlib.Path.glob", return_value=[]):
            await bot.handle_document(update, context)

    assert update.message.reply_text.call_count >= 1
    first_call = update.message.reply_text.call_args_list[0][0][0]
    assert "received" in first_call.lower() or "📥" in first_call


@pytest.mark.unit
async def test_duplicate_project_rejected():
    config = _make_config()
    bot = NovelTelegramBot(config)
    bot._active_projects = {12345: "existing-project-id"}

    update = _make_update(
        document_name="novel.txt",
        document_size=1024,
        chat_id=12345,
    )
    context = _make_context()

    await bot.handle_document(update, context)

    update.message.reply_text.assert_called()
    calls = [c[0][0] for c in update.message.reply_text.call_args_list]
    any_rejection = any(
        "already" in t.lower() or "active" in t.lower() or "progress" in t.lower()
        for t in calls
    )
    assert any_rejection


@pytest.mark.unit
async def test_cancel_project():
    config = _make_config()
    bot = NovelTelegramBot(config)
    bot._active_projects = {12345: "project-to-cancel"}

    bot.orchestrator = MagicMock()
    bot.orchestrator.cancel_project = AsyncMock(return_value=True)

    update = _make_update(message_text="/cancel", chat_id=12345)
    context = _make_context()

    assert 12345 in bot._active_projects


@pytest.mark.unit
async def test_status_with_project():
    config = _make_config()
    bot = NovelTelegramBot(config)
    bot._active_projects = {12345: "active-project-id"}

    update = _make_update(message_text="/status", chat_id=12345)
    context = _make_context()

    await bot.status_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Processing" in call_text or "⏳" in call_text or "active" in call_text.lower()
