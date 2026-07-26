"""Telegram bot bridge to n8n webhooks for CineOS"""
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)


class CineOSTelegramBridge:
    """Telegram bot that bridges to n8n webhooks"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bot_token = config["telegram"]["bot_token"]
        self.n8n_webhook_base = config.get("n8n", {}).get("webhook_url", "http://localhost:5678/webhook")
        self.application = None
        self._active_projects: Dict[int, str] = {}  # chat_id -> project_id
        self._progress_messages: Dict[int, int] = {}  # chat_id -> last_message_id

    async def start(self):
        """Start the bot"""
        self.application = Application.builder().token(self.bot_token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("CineOS Telegram Bridge started")

    async def stop(self):
        """Stop the bot gracefully"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    async def _call_n8n_webhook(self, webhook_path: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Call an n8n webhook and return the response"""
        url = f"{self.n8n_webhook_base}/{webhook_path}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=data)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout calling n8n webhook: {webhook_path}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling n8n webhook {webhook_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error calling n8n webhook {webhook_path}: {e}")
            return None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🎬 Welcome to CineOS!\n\n"
            "Send me a novel (.txt file) and I'll create a cinematic video.\n\n"
            "Commands:\n"
            "/status - Check project status\n"
            "/cancel - Cancel current project\n"
            "/help - Show this help"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📖 How to use:\n\n"
            "1. Send me a .txt file with your novel\n"
            "2. Wait for processing\n"
            "3. Receive your cinematic video\n\n"
            "Limits: 50-500,000 words, UTF-8 text\n\n"
            "Commands:\n"
            "/status - Check project status\n"
            "/cancel - Cancel current project"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        chat_id = update.message.chat_id

        # Check if user has an active project
        project_id = self._active_projects.get(chat_id)
        if not project_id:
            await update.message.reply_text("✅ No active projects. Send me a novel to get started!")
            return

        # Query status via n8n webhook
        result = await self._call_n8n_webhook("telegram_intake", {
            "action": "status",
            "chat_id": chat_id,
            "project_id": project_id
        })

        if result and result.get("status") == "success":
            project = result.get("project", {})
            state = project.get("current_state", "unknown")
            progress = project.get("progress", 0.0)
            title = project.get("title", "Untitled")

            await update.message.reply_text(
                f"📊 Project: {title}\n"
                f"State: {state}\n"
                f"Progress: {progress * 100:.1f}%"
            )
        else:
            await update.message.reply_text(
                f"📊 Active project: {project_id[:12]}...\n"
                "Status check temporarily unavailable."
            )

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        chat_id = update.message.chat_id
        project_id = self._active_projects.get(chat_id)

        if not project_id:
            await update.message.reply_text("❌ No active project to cancel.")
            return

        # Call cancel webhook
        result = await self._call_n8n_webhook("telegram_intake", {
            "action": "cancel",
            "chat_id": chat_id,
            "project_id": project_id
        })

        if result and result.get("status") == "success":
            await update.message.reply_text(f"❌ Project cancelled: {project_id[:12]}...")
            self._active_projects.pop(chat_id, None)
        else:
            await update.message.reply_text("⚠️ Cancel request sent. Please wait for confirmation.")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document uploads"""
        document = update.message.document
        chat_id = update.message.chat_id

        # Check file type
        if not document.file_name.endswith(".txt"):
            await update.message.reply_text("⚠️ Please send a .txt file containing the novel.")
            return

        # Check file size (50MB max)
        max_size = 50 * 1024 * 1024
        if document.file_size > max_size:
            await update.message.reply_text(
                f"⚠️ File too large ({document.file_size // 1024 // 1024}MB). "
                f"Maximum is 50MB."
            )
            return

        # Check if user already has an active project
        if chat_id in self._active_projects:
            await update.message.reply_text(
                "⚠️ You already have an active project. "
                "Use /cancel to cancel it before starting a new one."
            )
            return

        await update.message.reply_text("📥 Novel received! Starting processing...")

        # Download the file
        temp_dir = Path(self.config.get("storage", {}).get("temp_path", "temp"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(temp_dir / document.file_name)

        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)

        # Read the file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except UnicodeDecodeError:
            await update.message.reply_text("⚠️ File encoding error. Please send a UTF-8 encoded .txt file.")
            Path(file_path).unlink(missing_ok=True)
            return

        # Call telegram_intake webhook to create project
        result = await self._call_n8n_webhook("telegram_intake", {
            "action": "intake",
            "chat_id": chat_id,
            "user_id": update.message.from_user.id,
            "file_name": document.file_name,
            "raw_text": raw_text,
            "word_count": len(raw_text.split())
        })

        # Cleanup temp file
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass

        if result and result.get("status") == "success":
            project_id = result.get("project_id")
            self._active_projects[chat_id] = project_id

            await update.message.reply_text(
                f"✅ Project created!\n\n"
                f"ID: {project_id[:12]}...\n"
                f"Words: {len(raw_text.split()):,}\n\n"
                f"Processing has begun. Use /status to check progress."
            )

            # Trigger orchestrator
            await self._call_n8n_webhook("orchestrator", {
                "project_id": project_id,
                "trigger_event": "project_created"
            })
        else:
            await update.message.reply_text(
                "❌ Failed to create project. Please try again later."
            )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        await update.message.reply_text(
            "📝 Please send me a novel as a .txt file to get started."
        )

    async def send_video(self, chat_id: int, video_path: str, caption: str = ""):
        """Send a video file to a Telegram chat.

        Args:
            chat_id: Telegram chat ID to send the video to.
            video_path: Path to the video file on disk.
            caption: Optional caption text for the video.
        """
        if not self.application or not self.application.bot:
            logger.error("Cannot send_video: bot not initialized")
            return False

        try:
            from telegram import InputFile
            video_file = Path(video_path)
            if not video_file.exists():
                logger.error(f"Video file not found: {video_path}")
                return False

            max_size_mb = 50
            file_size_mb = video_file.stat().st_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                logger.warning(f"Video too large ({file_size_mb:.1f}MB > {max_size_mb}MB), splitting not implemented")
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Video is {file_size_mb:.1f}MB — exceeds Telegram {max_size_mb}MB limit."
                )
                return False

            with open(video_path, "rb") as vf:
                await self.application.bot.send_video(
                    chat_id=chat_id,
                    video=InputFile(vf),
                    caption=caption or f"🎬 Your cinematic video is ready!",
                    read_timeout=120,
                    write_timeout=120,
                )

            logger.info(f"Video sent to chat {chat_id}: {video_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to send video to chat {chat_id}: {e}")
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Failed to send video: {e}"
                )
            except Exception:
                pass
            return False

    async def send_progress(self, chat_id: int, message: str, update_id: Optional[int] = None):
        """Send or update a progress message in a chat."""
        if not self.application or not self.application.bot:
            return

        try:
            if update_id:
                await self.application.bot.edit_message_text(
                    chat_id=chat_id, message_id=update_id, text=message
                )
            else:
                msg = await self.application.bot.send_message(chat_id=chat_id, text=message)
                self._progress_messages[chat_id] = msg.message_id
        except Exception as e:
            logger.warning(f"Failed to send progress to chat {chat_id}: {e}")


def create_bridge(config: Dict[str, Any]) -> CineOSTelegramBridge:
    """Factory function to create the bridge"""
    return CineOSTelegramBridge(config)
