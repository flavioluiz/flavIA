"""Telegram bot interface for flavIA."""

import logging

from flavia.config import Settings
from flavia.agent import RecursiveAgent, AgentProfile

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure logging for Telegram bot runtime."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Keep bot runtime logs focused on application-level events.
    for noisy_logger in ("httpx", "httpcore", "apscheduler", "telegram.ext"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


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
        if self.settings.telegram_allow_all_users:
            return True
        if self.settings.telegram_allowed_users:
            return user_id in self.settings.telegram_allowed_users
        if self.settings.telegram_whitelist_configured:
            return False
        # Backward-compatible default: no whitelist configured means public bot.
        return True

    async def _whoami_command(self, update, context) -> None:
        """Show IDs needed for Telegram whitelist configuration."""
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        await update.message.reply_text(
            "Telegram IDs for configuration:\n"
            f"- User ID: {user_id}\n"
            f"- Chat ID: {chat_id}\n\n"
            "Use User ID in TELEGRAM_ALLOWED_USER_IDS (comma-separated)."
        )

    async def _start_command(self, update, context) -> None:
        """Handle /start command."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else None

        if not self._is_authorized(user_id):
            await update.message.reply_text(
                "You are not authorized to use this bot.\n\n"
                f"Your User ID: {user_id}\n"
                f"Your Chat ID: {chat_id}\n\n"
                "Ask the bot owner to add your User ID to TELEGRAM_ALLOWED_USER_IDS."
            )
            return

        await update.message.reply_text(
            "Welcome to flavIA!\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/reset - Reset conversation\n"
            "/help - Show help\n\n"
            "/whoami - Show your Telegram user/chat IDs\n\n"
            f"Your User ID: {user_id}\n"
            f"Your Chat ID: {chat_id}\n\n"
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
            "Use /whoami to see your Telegram IDs.\n\n"
            "Just send a message!"
        )

    async def _handle_message(self, update, context) -> None:
        """Handle regular text messages."""
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            chat_id = update.effective_chat.id if update.effective_chat else None
            await update.message.reply_text(
                "You are not authorized.\n"
                f"User ID: {user_id}\n"
                f"Chat ID: {chat_id}"
            )
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

        if self.settings.telegram_allow_all_users:
            logger.warning("Telegram bot is running in PUBLIC mode (no whitelist).")
        elif self.settings.telegram_allowed_users:
            logger.info(
                "Telegram whitelist enabled for %d user(s).",
                len(self.settings.telegram_allowed_users),
            )
        elif self.settings.telegram_whitelist_configured:
            logger.error(
                "TELEGRAM_ALLOWED_USER_IDS was set but no valid IDs were parsed. "
                "All users will be denied."
            )
        else:
            logger.warning(
                "No TELEGRAM_ALLOWED_USER_IDS configured; bot is PUBLIC. "
                "Set TELEGRAM_ALLOWED_USER_IDS to restrict access."
            )

        logger.info("Starting Telegram bot...")

        app = self.Application.builder().token(self.settings.telegram_token).build()

        app.add_handler(self.CommandHandler("start", self._start_command))
        app.add_handler(self.CommandHandler("reset", self._reset_command))
        app.add_handler(self.CommandHandler("help", self._help_command))
        app.add_handler(self.CommandHandler("whoami", self._whoami_command))
        app.add_handler(self.MessageHandler(
            self.filters.TEXT & ~self.filters.COMMAND,
            self._handle_message
        ))

        logger.info("Bot running. Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message"])


def run_telegram_bot(settings: Settings) -> None:
    """Run the Telegram bot."""
    _configure_logging()
    bot = TelegramBot(settings)
    bot.run()
