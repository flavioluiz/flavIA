"""Telegram bot interface for flavIA."""

import logging
from typing import Optional

from flavia.config import Settings
from flavia.agent import RecursiveAgent, AgentProfile

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot wrapper for flavIA agent."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.agents: dict[int, RecursiveAgent] = {}

        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
            self.telegram_available = True
            self.Update = Update
            self.Application = Application
            self.CommandHandler = CommandHandler
            self.MessageHandler = MessageHandler
            self.filters = filters
        except ImportError:
            self.telegram_available = False
            logger.error("python-telegram-bot not installed. Run: pip install 'flavia[telegram]'")

    def _get_or_create_agent(self, user_id: int) -> RecursiveAgent:
        """Get or create an agent for a user."""
        if user_id not in self.agents:
            if "main" in self.settings.agents_config:
                config = self.settings.agents_config["main"]
                profile = AgentProfile.from_config(config)
                if "path" not in config:
                    profile.base_dir = self.settings.base_dir
            else:
                profile = AgentProfile(
                    context="You are a helpful assistant that can read and analyze files.",
                    model=self.settings.default_model,
                    base_dir=self.settings.base_dir,
                    tools=["read_file", "list_files", "search_files", "get_file_info"],
                    subagents={},
                    name="main",
                    max_depth=self.settings.max_depth,
                )

            self.agents[user_id] = RecursiveAgent(
                settings=self.settings,
                profile=profile,
                agent_id=f"tg-{user_id}",
            )

        return self.agents[user_id]

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        if not self.settings.telegram_allowed_users:
            return True
        return user_id in self.settings.telegram_allowed_users

    async def _start_command(self, update, context) -> None:
        """Handle /start command."""
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        await update.message.reply_text(
            "Welcome to flavIA!\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/reset - Reset conversation\n"
            "/help - Show help\n\n"
            "Send me a message to start!"
        )

    async def _reset_command(self, update, context) -> None:
        """Handle /reset command."""
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        if user_id in self.agents:
            self.agents[user_id].reset()

        await update.message.reply_text("Conversation reset!")

    async def _help_command(self, update, context) -> None:
        """Handle /help command."""
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        await update.message.reply_text(
            "flavIA can help you with:\n"
            "- Reading and analyzing files\n"
            "- Searching content\n"
            "- Listing directories\n\n"
            "Just send a message!"
        )

    async def _handle_message(self, update, context) -> None:
        """Handle regular text messages."""
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("You are not authorized.")
            return

        user_message = update.message.text
        if not user_message:
            return

        await update.message.chat.send_action("typing")

        try:
            agent = self._get_or_create_agent(user_id)
            response = agent.run(user_message)

            if len(response) > 4000:
                chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text(f"Error: {str(e)[:200]}")

    def run(self) -> None:
        """Run the Telegram bot."""
        if not self.telegram_available:
            logger.error("Cannot run: python-telegram-bot not installed")
            return

        if not self.settings.telegram_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return

        logger.info("Starting Telegram bot...")

        app = self.Application.builder().token(self.settings.telegram_token).build()

        app.add_handler(self.CommandHandler("start", self._start_command))
        app.add_handler(self.CommandHandler("reset", self._reset_command))
        app.add_handler(self.CommandHandler("help", self._help_command))
        app.add_handler(self.MessageHandler(
            self.filters.TEXT & ~self.filters.COMMAND,
            self._handle_message
        ))

        logger.info("Bot running. Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message"])


def run_telegram_bot(settings: Settings) -> None:
    """Run the Telegram bot."""
    bot = TelegramBot(settings)
    bot.run()
