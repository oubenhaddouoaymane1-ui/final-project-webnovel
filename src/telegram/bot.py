"""Telegram bot for receiving novels and delivering videos"""
import logging
from pathlib import Path
from typing import Dict, Any

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from src.config import load_config
from src.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


class NovelTelegramBot:
    """Telegram bot for the Novel to Video pipeline"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bot_token = config["telegram"]["bot_token"]
        self.application = None
        self.orchestrator = PipelineOrchestrator(config)
        self._active_projects: Dict[int, str] = {}  # chat_id -> project_id

    async def start(self):
        """Start the bot"""
        self.application = Application.builder().token(self.bot_token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("Bot started successfully")

    async def stop(self):
        """Stop the bot gracefully"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🎬 Novel to Cinematic Video Pipeline\n\n"
            "Send me a novel (as a .txt file) and I'll convert it into a professional "
            "cinematic anime/manhwa style video.\n\n"
            "Use /help for more information."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📖 How to use:\n\n"
            "1. Send me a novel as a .txt file\n"
            "2. I'll analyze it and generate a video\n"
            "3. You'll receive progress updates\n"
            "4. Download your cinematic video\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/status - Check processing status"
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        project_id = self._active_projects.get(update.message.chat_id)
        if project_id:
            await update.message.reply_text(
                f"⏳ Processing in progress.\nProject: {project_id[:12]}..."
            )
        else:
            await update.message.reply_text("✅ Ready. Send me a .txt novel to get started!")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document uploads"""
        document = update.message.document

        # Check file type
        if not document.file_name.endswith(".txt"):
            await update.message.reply_text("⚠️ Please send a .txt file containing the novel.")
            return

        # Check file size
        max_size = self.config["telegram"]["max_file_size"]
        if document.file_size > max_size:
            await update.message.reply_text(
                f"⚠️ File too large ({document.file_size // 1024 // 1024}MB). "
                f"Maximum is {max_size // 1024 // 1024}MB."
            )
            return

        await update.message.reply_text("📥 Novel received! Starting processing pipeline...")

        # Download the file
        temp_dir = Path(self.config["storage"]["temp_path"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(temp_dir / document.file_name)

        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)

        chat_id = update.message.chat_id

        # Progress callback that sends messages to Telegram
        last_update = [0.0]

        async def progress_callback(progress: float, message: str):
            # Only send update if progress changed by >= 5% or it's the final message
            if progress >= 0.99 or progress - last_update[0] >= 0.05:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message)
                    last_update[0] = progress
                except Exception as e:
                    logger.warning(f"Failed to send progress: {e}")

        # Start pipeline
        try:
            project_id = await self.orchestrator.start_pipeline(
                file_path=file_path,
                user_id=update.message.from_user.id,
                chat_id=chat_id,
                progress_callback=progress_callback,
            )
            self._active_projects[chat_id] = project_id

            # Deliver the video
            video_path = str(
                Path(self.config["storage"]["video_path"]) / f"{project_id}.mp4"
            )
            if Path(video_path).exists():
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=open(video_path, "rb"),
                    caption="🎬 Here's your cinematic video!",
                )
            else:
                # Check for any video files in output dir
                video_dir = Path(self.config["storage"]["video_path"])
                videos = list(video_dir.glob("*.mp4"))
                if videos:
                    latest = max(videos, key=lambda p: p.stat().st_mtime)
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=open(latest, "rb"),
                        caption="🎬 Here's your cinematic video!",
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ Video processing completed but output file not found. Check logs.",
                    )

            # Cleanup temp file
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                pass

            self._active_projects.pop(chat_id, None)

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Processing failed: {str(e)[:200]}",
            )
            self._active_projects.pop(chat_id, None)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        await update.message.reply_text(
            "📝 Please send me a novel as a .txt file to get started."
        )
