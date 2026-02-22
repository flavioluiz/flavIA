"""Telegram bot interface for flavIA."""

import logging
from pathlib import Path
from typing import Any, Optional

from flavia.agent import RecursiveAgent
from flavia.config import Settings
from flavia.config.bots import BotConfig

from .base_bot import BaseMessagingBot, BotCommand, BotResponse, SendFileAction

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


def _build_compaction_warning(agent: RecursiveAgent) -> str:
    """Build compaction warning text when context is near capacity.

    Returns an empty string if compaction is not needed.
    """
    warning_pending = getattr(agent, "compaction_warning_pending", False)
    if not warning_pending and not agent.needs_compaction:
        return ""
    prompt_tokens = agent.last_prompt_tokens
    if warning_pending:
        prompt_tokens = max(
            prompt_tokens,
            getattr(agent, "compaction_warning_prompt_tokens", prompt_tokens),
        )
    max_tokens = agent.max_context_tokens
    pct = (prompt_tokens / max_tokens * 100) if max_tokens > 0 else 0.0
    return (
        f"\n\n\u26a0 Context usage at {pct:.0f}%. "
        "Reply /compact to summarize and continue, or keep chatting."
    )


def _configure_logging() -> None:
    """Configure logging for Telegram bot runtime."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Keep bot runtime logs focused on application-level events.
    for noisy_logger in ("httpx", "httpcore", "apscheduler", "telegram.ext"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


class TelegramBot(BaseMessagingBot):
    """Telegram bot wrapper for flavIA agent."""

    def __init__(self, settings: Settings, bot_config: Optional[BotConfig] = None):
        if bot_config is None:
            from flavia.config.bots import create_fallback_telegram_bot

            bot_config = create_fallback_telegram_bot(
                token=settings.telegram_token,
                allowed_users=settings.telegram_allowed_users,
                allow_all=settings.telegram_allow_all_users,
                whitelist_configured=settings.telegram_whitelist_configured,
            )
        super().__init__(settings, bot_config)
        self._current_updates: dict[int, Any] = {}

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

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "telegram"

    @property
    def max_message_length(self) -> int:
        """Telegram API message length limit."""
        return 4096

    @property
    def _token(self) -> str:
        """Bot token: prefer bot_config over legacy settings."""
        if self.bot_config and self.bot_config.token:
            return self.bot_config.token
        return self.settings.telegram_token

    async def _send_message(self, user_id: int, message: str) -> None:
        """Send a text message using the active Telegram update context."""
        update = self._current_updates.get(user_id)
        if not update or not getattr(update, "message", None):
            raise RuntimeError("No active Telegram update context for message send.")
        await update.message.reply_text(message)

    async def _send_file(self, user_id: int, file_action: SendFileAction) -> None:
        """Send a file using the active Telegram update context."""
        update = self._current_updates.get(user_id)
        if not update or not getattr(update, "message", None):
            raise RuntimeError("No active Telegram update context for file send.")
        await self._reply_document_file(update, file_action)

    def _get_commands(self) -> list[BotCommand]:
        """Return Telegram command list including /whoami."""
        return [
            BotCommand("start", "Show welcome message and your IDs"),
            BotCommand("help", "Show this help"),
            BotCommand("whoami", "Show your Telegram user/chat IDs"),
            BotCommand("reset", "Reset your conversation context"),
            BotCommand("compact", "Summarize and compact conversation context"),
            BotCommand("agents", "List available agents", "/agents"),
            BotCommand(
                "agent",
                "Switch to a different agent (resets conversation)",
                "/agent <name>",
                ["/agent researcher", "/agent main"],
            ),
        ]

    def _build_help_text(self) -> str:
        """Build Telegram help text with full legacy command/capability details."""
        return (
            "Welcome to flavIA Telegram mode.\n\n"
            "Commands:\n"
            "/start - Show welcome message and your IDs\n"
            "/help - Show this help\n"
            "/whoami - Show your Telegram user/chat IDs\n"
            "/reset - Reset your conversation context\n"
            "/compact - Summarize and compact conversation context\n"
            "/agents - List available agents\n"
            "/agent <name> - Switch to a different agent (resets conversation)\n\n"
            "Capabilities:\n"
            "- Reading and analyzing files\n"
            "- Searching content\n"
            "- Listing directories\n\n"
            "Send a message to start."
        )

    def _agent_id_prefix(self) -> str:
        """Keep historical Telegram agent identifier prefix for compatibility."""
        return "tg"

    def _message_preview(self, text: str, max_len: int = 120) -> str:
        """Build one-line preview for logs."""
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 3] + "..."

    def _log_event_telegram(self, update, action: str, extra: str = "") -> None:
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

    async def _safe_send_typing(self, update) -> None:
        """Best-effort typing indicator that never aborts request handling."""
        try:
            await update.message.chat.send_action("typing")
        except Exception as e:
            self._log_event_telegram(update, "typing:error", str(e)[:160])

    async def _error_handler(self, update, context) -> None:
        """Application-level fallback for unhandled Telegram callback errors."""
        err = getattr(context, "error", None)
        if err is None:
            logger.error("Unhandled Telegram callback error (unknown).")
            return
        logger.error("Unhandled Telegram callback error: %s", str(err)[:300])

    async def _whoami_command(self, update, context) -> None:
        """Show IDs needed for Telegram whitelist configuration."""
        self._log_event_telegram(update, "command:/whoami")
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
        self._log_event_telegram(update, "command:/start")
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
        self._log_event_telegram(update, "command:/reset")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        self._reset_agent(user_id)
        await update.message.reply_text("Conversation reset!")

    async def _help_command(self, update, context) -> None:
        """Handle /help command."""
        self._log_event_telegram(update, "command:/help")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        await update.message.reply_text(self._build_help_text())

    async def _compact_command(self, update, context) -> None:
        """Handle /compact command -- compact the conversation context."""
        self._log_event_telegram(update, "command:/compact")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        if user_id not in self.agents:
            await update.message.reply_text("No active conversation to compact.")
            return

        agent = self.agents[user_id]
        before_pct = agent.context_utilization * 100
        before_tokens = agent.last_prompt_tokens
        max_tokens = agent.max_context_tokens

        try:
            await self._safe_send_typing(update)
            summary = agent.compact_conversation()
            if not summary:
                await update.message.reply_text("Nothing to compact (conversation is empty).")
                return

            after_pct = agent.context_utilization * 100
            after_tokens = agent.last_prompt_tokens

            summary_preview = summary[:500] + ("..." if len(summary) > 500 else "")
            reply = (
                "\u2705 Conversation compacted.\n\n"
                f"Before: {before_tokens:,}/{max_tokens:,} ({before_pct:.0f}%)\n"
                f"After: {after_tokens:,}/{max_tokens:,} ({after_pct:.1f}%)\n\n"
                f"Summary:\n{summary_preview}"
            )
            await update.message.reply_text(reply)
            self._log_event_telegram(
                update,
                "compact",
                f"before={before_pct:.0f}% after={after_pct:.1f}%",
            )
        except Exception as e:
            self._log_event_telegram(update, "compact:error", str(e)[:200])
            await update.message.reply_text(f"Compaction failed: {str(e)[:200]}")

    async def _agents_command(self, update, context) -> None:
        """Handle /agents command — list available agents."""
        self._log_event_telegram(update, "command:/agents")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        available = self._available_agents()
        if not available:
            await update.message.reply_text("No agents configured in agents.yaml.")
            return

        current = self._user_agents.get(user_id, self._default_agent_name)
        lines = []
        for name in available:
            marker = " (active)" if name == current else ""
            lines.append(f"- {name}{marker}")
        await update.message.reply_text("Available agents:\n" + "\n".join(lines))

    async def _agent_command(self, update, context) -> None:
        """Handle /agent [name] command — show or switch active agent."""
        self._log_event_telegram(update, "command:/agent")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        args = (context.args or []) if context else []
        current = self._user_agents.get(user_id, self._default_agent_name)

        if not args:
            await update.message.reply_text(f"Current agent: {current}")
            return

        name = args[0]

        if name not in self._all_agent_configs():
            available = self._available_agents()
            available_str = ", ".join(available) if available else "(none)"
            await update.message.reply_text(f"Unknown agent '{name}'. Available: {available_str}")
            return

        if self.bot_config and not self.bot_config.is_agent_allowed(name):
            allowed = self.bot_config.allowed_agents or []
            allowed_str = ", ".join(allowed) if allowed else "(none)"
            await update.message.reply_text(
                f"Agent '{name}' is not allowed for this bot. Allowed: {allowed_str}"
            )
            return

        success, message = self._switch_agent(user_id, args[0])
        await update.message.reply_text(message)

    async def _handle_message(self, update, context) -> None:
        """Handle regular text messages using base bot infrastructure."""
        user_id = update.effective_user.id
        user_message = update.message.text

        if not self._is_authorized(user_id):
            chat_id = update.effective_chat.id if update.effective_chat else None
            self._log_event_telegram(update, "blocked", "unauthorized user")
            await update.message.reply_text(
                f"You are not authorized.\nUser ID: {user_id}\nChat ID: {chat_id}"
            )
            return

        if not user_message:
            return

        self._log_event_telegram(
            update,
            "message:received",
            f'text="{self._message_preview(user_message)}"',
        )

        if not hasattr(self, "_current_updates"):
            self._current_updates = {}
        self._current_updates[user_id] = update

        try:
            await self._safe_send_typing(update)

            response = self._handle_message_common(user_id, user_message)
            agent = self.agents.get(user_id)
            full_text = response.text
            if agent:
                full_text += _build_token_footer(agent)
                full_text += _build_compaction_warning(agent)
            response = BotResponse(text=full_text, actions=response.actions)

            self._log_event_telegram(
                update,
                "message:answered",
                f"chars={len(response.text)}",
            )

            await self._send_response(user_id, response)

        except Exception as e:
            self._log_event_telegram(update, "message:error", str(e)[:200])
            logger.error(f"Error: {e}")
            try:
                await update.message.reply_text(f"Error: {str(e)[:200]}")
            except Exception as reply_error:
                self._log_event_telegram(
                    update, "message:error:reply_failed", str(reply_error)[:200]
                )
        finally:
            self._current_updates.pop(user_id, None)

    async def _reply_document_file(self, update, file_action: SendFileAction) -> None:
        """Send a file as a Telegram document (Task 10.3)."""
        path = Path(file_action.path)
        if not path.exists():
            await update.message.reply_text(f"Error: file not found: {file_action.filename}")
            return

        try:
            with open(path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=file_action.filename,
                    caption=file_action.caption or None,
                )
            self._log_event_telegram(
                update,
                "file:sent",
                f"path={file_action.path} size={path.stat().st_size}",
            )
        except Exception as e:
            self._log_event_telegram(update, "file:error", str(e)[:200])
            await update.message.reply_text(f"Error sending file: {str(e)[:200]}")

    def run(self) -> None:
        """Run the Telegram bot."""
        if not self.telegram_available:
            logger.error("Cannot run: python-telegram-bot not installed")
            return

        token = self._token
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return

        # Determine effective access settings for logging
        if self.bot_config:
            access = self.bot_config.access
            _allow_all = access.allow_all
            _allowed_users = access.allowed_users
            _whitelist_configured = access.whitelist_configured
        else:
            _allow_all = self.settings.telegram_allow_all_users
            _allowed_users = self.settings.telegram_allowed_users
            _whitelist_configured = self.settings.telegram_whitelist_configured

        if _allow_all:
            logger.warning("Telegram bot is running in PUBLIC mode (no whitelist).")
        elif _allowed_users:
            logger.info(
                "Telegram whitelist enabled for %d user(s).",
                len(_allowed_users),
            )
        elif _whitelist_configured:
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

        app = self.Application.builder().token(token).build()

        app.add_handler(self.CommandHandler("start", self._start_command))
        app.add_handler(self.CommandHandler("reset", self._reset_command))
        app.add_handler(self.CommandHandler("help", self._help_command))
        app.add_handler(self.CommandHandler("compact", self._compact_command))
        app.add_handler(self.CommandHandler("whoami", self._whoami_command))
        app.add_handler(self.CommandHandler("agents", self._agents_command))
        app.add_handler(self.CommandHandler("agent", self._agent_command))
        app.add_handler(
            self.MessageHandler(self.filters.TEXT & ~self.filters.COMMAND, self._handle_message)
        )
        app.add_error_handler(self._error_handler)

        logger.info("Bot running. Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message"])


def run_telegram_bot(settings: Settings, bot_config: Optional[BotConfig] = None) -> None:
    """Run the Telegram bot."""
    _configure_logging()
    bot = TelegramBot(settings, bot_config=bot_config)
    bot.run()
