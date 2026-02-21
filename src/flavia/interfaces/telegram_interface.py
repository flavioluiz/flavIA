"""Telegram bot interface for flavIA."""

import logging
from typing import Optional

from flavia.config import Settings
from flavia.config.bots import BotConfig
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


class TelegramBot:
    """Telegram bot wrapper for flavIA agent."""

    def __init__(self, settings: Settings, bot_config: Optional[BotConfig] = None):
        self.settings = settings
        self.bot_config = bot_config
        self.agents: dict[int, RecursiveAgent] = {}
        self._user_agents: dict[int, str] = {}  # user_id → agent name override

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
    def _token(self) -> str:
        """Bot token: prefer bot_config over legacy settings."""
        if self.bot_config and self.bot_config.token:
            return self.bot_config.token
        return self.settings.telegram_token

    @property
    def _default_agent_name(self) -> str:
        """Default agent name: prefer bot_config over hardcoded 'main'."""
        if self.bot_config:
            return self.bot_config.default_agent
        return "main"

    def _available_agents(self) -> list[str]:
        """Return agent names this bot permits, filtered by allowed_agents."""
        all_names = list(self.settings.agents_config.keys())
        if self.bot_config and self.bot_config.allowed_agents is not None:
            return [a for a in self.bot_config.allowed_agents if a in all_names]
        return all_names

    def _get_or_create_agent(self, user_id: int) -> RecursiveAgent:
        """Get or create an agent for a user."""
        if user_id not in self.agents:
            agent_name = self._user_agents.get(user_id, self._default_agent_name)
            if agent_name in self.settings.agents_config:
                config = self.settings.agents_config[agent_name]
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
                    name=agent_name,
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
        if self.bot_config:
            access = self.bot_config.access
            if access.allow_all:
                return True
            if access.allowed_users:
                return user_id in access.allowed_users
            if access.whitelist_configured:
                return False
            # No whitelist configured in bot_config: fall through to legacy
        # Legacy settings
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

    async def _compact_command(self, update, context) -> None:
        """Handle /compact command -- compact the conversation context."""
        self._log_event(update, "command:/compact")
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

        await update.message.chat.send_action("typing")

        try:
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
            self._log_event(
                update,
                "compact",
                f"before={before_pct:.0f}% after={after_pct:.1f}%",
            )
        except Exception as e:
            self._log_event(update, "compact:error", str(e)[:200])
            await update.message.reply_text(f"Compaction failed: {str(e)[:200]}")

    async def _agents_command(self, update, context) -> None:
        """Handle /agents command — list available agents."""
        self._log_event(update, "command:/agents")
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
        self._log_event(update, "command:/agent")
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            return

        args = (context.args or []) if context else []
        current = self._user_agents.get(user_id, self._default_agent_name)

        if not args:
            await update.message.reply_text(f"Current agent: {current}")
            return

        name = args[0]

        if name not in self.settings.agents_config:
            available = self._available_agents()
            available_str = ", ".join(available) if available else "(none)"
            await update.message.reply_text(
                f"Unknown agent '{name}'. Available: {available_str}"
            )
            return

        if self.bot_config and not self.bot_config.is_agent_allowed(name):
            allowed = self.bot_config.allowed_agents or []
            allowed_str = ", ".join(allowed) if allowed else "(none)"
            await update.message.reply_text(
                f"Agent '{name}' is not allowed for this bot. Allowed: {allowed_str}"
            )
            return

        if name == current:
            await update.message.reply_text(f"Already using agent '{name}'.")
            return

        self._user_agents[user_id] = name
        if user_id in self.agents:
            del self.agents[user_id]

        await update.message.reply_text(
            f"Switched to agent '{name}'. Conversation has been reset."
        )

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
            response += _build_compaction_warning(agent)
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

        logger.info("Bot running. Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message"])


def run_telegram_bot(settings: Settings, bot_config: Optional[BotConfig] = None) -> None:
    """Run the Telegram bot."""
    _configure_logging()
    bot = TelegramBot(settings, bot_config=bot_config)
    bot.run()
