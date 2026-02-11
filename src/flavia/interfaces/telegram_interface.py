"""Telegram bot interface for flavIA."""

import logging

from flavia.config import Settings
from flavia.agent import RecursiveAgent, AgentProfile

logger = logging.getLogger(__name__)


def _build_token_footer(agent: RecursiveAgent) -> str:
    """Build compact token usage footer for Telegram messages.

    Example output::

        📊 Context: 12,450/128,000 (9.7%)
    """
    prompt_tokens = agent.last_prompt_tokens
    max_tokens = agent.max_context_tokens
    pct = agent.context_utilization * 100
    return f"\n\n\U0001f4ca Context: {prompt_tokens:,}/{max_tokens:,} ({pct:.1f}%)"


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

    def _build_help_text(self) -> str:
        """Build Telegram help text with all available commands."""
        return (
            "Welcome to flavIA Telegram mode.\n\n"
            "Commands:\n"
            "/start - Show welcome message and your IDs\n"
            "/help - Show this help\n"
            "/whoami - Show your Telegram user/chat IDs\n"
            "/reset - Reset your conversation context\n\n"
            "Capabilities:\n"
            "- Reading and analyzing files\n"
            "- Searching content\n"
            "- Listing directories\n\n"
            "Send a message to start."
        )

    def _message_preview(self, text: str, max_len: int = 120) -> str:
        """Build one-line preview for logs."""
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 3] + "..."

    def _log_event(self, update, action: str, extra: str = "") -> None:
        """Log basic Telegram event details to terminal."""
        user = update.effective_user
        chat = update.effective_chat
        user_id = user.id if user else None
        chat_id = chat.id if chat else None
        username = getattr(user, "username", None)
        full_name = getattr(user, "full_name", None)
        identity = username or full_name or "unknown"
        suffix = f" | {extra}" if extra else ""
        logger.info(
            "tg %s | chat=%s user=%s (%s)%s",
            action,
            chat_id,
            user_id,
            identity,
            suffix,
        )

    async def _whoami_command(self, update, context) -> None:
        """Show IDs needed for Telegram whitelist configuration."""
        self._log_event(update, "command:/whoami")
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
        self._log_event(update, "command:/start")
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
            self._build_help_text() + "\n\n"
            f"Your User ID: {user_id}\n"
            f"Your Chat ID: {chat_id}\n\n"
            "Use TELEGRAM_ALLOWED_USER_IDS to whitelist specific users."
        )

    async def _reset_command(self, update, context) -> None:
        """Handle /reset command."""
        self._log_event(update, "command:/reset")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        if user_id in self.agents:
            self.agents[user_id].reset()

        await update.message.reply_text("Conversation reset!")

    async def _help_command(self, update, context) -> None:
        """Handle /help command."""
        self._log_event(update, "command:/help")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        await update.message.reply_text(self._build_help_text())

    async def _handle_message(self, update, context) -> None:
        """Handle regular text messages."""
        user_id = update.effective_user.id
        user_message = update.message.text

        if not self._is_authorized(user_id):
            chat_id = update.effective_chat.id if update.effective_chat else None
            self._log_event(update, "blocked", "unauthorized user")
            await update.message.reply_text(
                f"You are not authorized.\nUser ID: {user_id}\nChat ID: {chat_id}"
            )
            return

        if not user_message:
            return

        self._log_event(
            update,
            "message:received",
            f'text="{self._message_preview(user_message)}"',
        )
        await update.message.chat.send_action("typing")

        try:
            agent = self._get_or_create_agent(user_id)
            response = agent.run(user_message)
            response += _build_token_footer(agent)
            self._log_event(
                update,
                "message:answered",
                f"chars={len(response)}",
            )

            if len(response) > 4000:
                chunks = [response[i : i + 4000] for i in range(0, len(response), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(chunk)
            else:
                await update.message.reply_text(response)

        except Exception as e:
            self._log_event(update, "message:error", str(e)[:200])
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
        app.add_handler(
            self.MessageHandler(self.filters.TEXT & ~self.filters.COMMAND, self._handle_message)
        )

        logger.info("Bot running. Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message"])


def run_telegram_bot(settings: Settings) -> None:
    """Run the Telegram bot."""
    _configure_logging()
    bot = TelegramBot(settings)
    bot.run()
