"""Base messaging bot abstract class for flavIA.

Provides a common interface for all messaging platforms (Telegram, WhatsApp, Web API).
Platform-specific subclasses only need to implement API communication layer.
"""

import logging
from inspect import isawaitable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from flavia.agent import AgentProfile, RecursiveAgent, SendFileAction
from flavia.config import Settings
from flavia.config.bots import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class BotCommand:
    """Metadata for a bot command."""

    name: str
    short_desc: str
    usage: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class BotResponse:
    """Wrapper for agent response that includes possible side effects.

    This provides forward compatibility with Task 10.1 (Structured Agent Responses).
    Currently wraps text responses and pending file send actions.

    Attributes:
        text: The text response (always present)
        actions: List of file send actions to execute after sending text
    """

    text: str
    actions: list[SendFileAction] = field(default_factory=list)

    @property
    def has_actions(self) -> bool:
        return len(self.actions) > 0


class BaseMessagingBot(ABC):
    """Abstract base class for all messaging platform bots.

    Defines common functionality:
    - Authentication and authorization (configurable per platform)
    - Agent lifecycle management (get/create/reset per user)
    - Message chunking for platform-specific size limits
    - Command routing (platform-agnostic command registry)
    - Structured logging

    Platform-specific subclasses need only implement:
    - API communication (receiving messages, sending responses)
    - platform-specific formatting
    - Platform-specific commands

    Args:
        settings: Application settings
        bot_config: Configuration for this bot instance
    """

    def __init__(self, settings: Settings, bot_config: BotConfig):
        self.settings = settings
        self.bot_config = bot_config
        self.agents: dict[Any, RecursiveAgent] = {}
        self._user_agents: dict[Any, str] = {}
        self.logger = logging.getLogger(f"bots.{bot_config.id}")

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Platform identifier (e.g., 'telegram', 'whatsapp', 'web')."""

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Maximum message length for this platform (per chunk)."""

    @abstractmethod
    def run(self) -> None:
        """Start the bot (blocks until Ctrl+C or equivalent interruption)."""

    @abstractmethod
    def _send_message(self, user_id: Any, message: str) -> Any:
        """Send a text message to a user.

        Platform-specific implementation.
        """

    @abstractmethod
    def _send_file(self, user_id: Any, file_action: SendFileAction) -> Any:
        """Send a file to a user.

        Platform-specific implementation (Task 10.3).
        """

    @property
    def _default_agent_name(self) -> str:
        if self.bot_config:
            return self.bot_config.default_agent
        return "main"

    def _agent_id_prefix(self) -> str:
        """Agent ID prefix used for per-platform agent instances."""
        return self.platform_name

    def _get_or_create_agent(self, user_id: Any) -> RecursiveAgent:
        """Get or create an agent for a user."""
        if user_id not in self.agents:
            agent_name = self._user_agents.get(user_id, self._default_agent_name)
            all_configs = self._all_agent_configs()
            config = all_configs.get(agent_name)

            if config:
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
                agent_id=f"{self._agent_id_prefix()}-{user_id}",
            )

        return self.agents[user_id]

    def _reset_agent(self, user_id: Any) -> None:
        """Reset the agent's conversation context for a user."""
        if user_id in self.agents:
            self.agents[user_id].reset()

    def _switch_agent(self, user_id: Any, agent_name: str) -> tuple[bool, str]:
        """Switch the active agent for a user.

        Returns:
            Tuple of (success, message)
        """
        all_configs = self._all_agent_configs()

        if agent_name not in all_configs:
            available = list(all_configs.keys())
            return (
                False,
                f"Unknown agent '{agent_name}'. Available: {', '.join(available) or '(none)'}",
            )

        if self.bot_config and not self.bot_config.is_agent_allowed(agent_name):
            allowed = self.bot_config.allowed_agents or []
            return (
                False,
                f"Agent '{agent_name}' is not allowed for this bot. Allowed: {', '.join(allowed) or '(none)'}",
            )

        current = self._user_agents.get(user_id, self._default_agent_name)
        if agent_name == current:
            return True, f"Already using agent '{agent_name}'."

        self._user_agents[user_id] = agent_name
        if user_id in self.agents:
            del self.agents[user_id]

        return True, f"Switched to agent '{agent_name}'. Conversation has been reset."

    def _all_agent_configs(self) -> dict[str, dict]:
        """Return top-level agents plus main.subagents promoted as selectable agents."""
        all_configs: dict[str, dict] = {}

        for name, cfg in self.settings.agents_config.items():
            if isinstance(cfg, dict):
                all_configs[name] = cfg

        main_cfg = self.settings.agents_config.get("main")
        if not isinstance(main_cfg, dict):
            return all_configs

        subagents = main_cfg.get("subagents", {})
        if not isinstance(subagents, dict):
            return all_configs

        for name, cfg in subagents.items():
            if not isinstance(cfg, dict):
                continue
            if name in all_configs:
                continue
            promoted = cfg.copy()
            if "model" not in promoted and "model" in main_cfg:
                promoted["model"] = main_cfg["model"]
            promoted.pop("subagents", None)
            all_configs[name] = promoted

        return all_configs

    def _available_agents(self) -> list[str]:
        """Return agent names this bot permits, filtered by allowed_agents."""
        all_configs = self._all_agent_configs()
        all_names = list(all_configs.keys())
        if self.bot_config and self.bot_config.allowed_agents is not None:
            return [a for a in self.bot_config.allowed_agents if a in all_names]
        return all_names

    def _is_authorized(self, user_id: Any) -> bool:
        """Check if user is authorized to use this bot."""
        if self.bot_config:
            access = self.bot_config.access
            if access.allow_all:
                return True
            if access.allowed_users:
                return user_id in access.allowed_users
            if access.whitelist_configured:
                return False

        if self.settings.telegram_allow_all_users:
            return True
        if self.settings.telegram_allowed_users:
            return user_id in self.settings.telegram_allowed_users
        if self.settings.telegram_whitelist_configured:
            return False

        return True

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks based on max_message_length."""
        max_len = self.max_message_length
        if len(text) <= max_len:
            return [text]
        return [text[i : i + max_len] for i in range(0, len(text), max_len)]

    def _log_event(self, user_id: Any, action: str, extra: str = "") -> None:
        """Log a structured event for this bot instance."""
        bot_logger = getattr(self, "logger", logger)
        parts = [self.platform_name, action, f"user={user_id}"]
        if extra:
            parts.append(extra)
        bot_logger.info(" | ".join(parts))

    def _get_commands(self) -> list[BotCommand]:
        """Return list of supported commands (can be overridden by subclasses)."""
        return [
            BotCommand("start", "Show welcome message and your IDs"),
            BotCommand("help", "Show this help"),
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
        """Build help text with all available commands."""
        commands = self._get_commands()
        lines = [f"Welcome to {self.platform_name.title()} mode.\n\nCommands:\n"]
        for cmd in commands:
            usage = cmd.usage or f"/{cmd.name}"
            lines.append(f"{usage} - {cmd.short_desc}")
        lines.append("\nSend a message to start.")
        return "\n".join(lines)

    def _handle_default_command(self, command: str, user_id: Any, args: str = "") -> Optional[str]:
        """Handle common commands shared across platforms.

        Returns:
            Response text, or None if command was not handled.
        """
        command = command.lower()

        if command == "reset":
            self._log_event(user_id, "command:/reset")
            self._reset_agent(user_id)
            return "Conversation reset!"

        elif command == "help":
            self._log_event(user_id, "command:/help")
            return self._build_help_text()

        elif command == "agents":
            self._log_event(user_id, "command:/agents")
            available = self._available_agents()
            if not available:
                return "No agents configured in agents.yaml."

            current = self._user_agents.get(user_id, self._default_agent_name)
            lines: list[str] = []
            for name in available:
                marker = " (active)" if name == current else ""
                lines.append(f"- {name}{marker}")
            return "Available agents:\n" + "\n".join(lines)

        elif command == "agent":
            self._log_event(user_id, "command:/agent")
            if not args:
                current = self._user_agents.get(user_id, self._default_agent_name)
                return f"Current agent: {current}"

            success, message = self._switch_agent(user_id, args.strip())
            return message

        elif command == "compact":
            self._log_event(user_id, "command:/compact")
            if user_id not in self.agents:
                return "No active conversation to compact."

            agent = self.agents[user_id]
            try:
                before_tokens = agent.last_prompt_tokens
                max_tokens = agent.max_context_tokens
                before_pct = ((before_tokens / max_tokens) * 100) if max_tokens > 0 else 0

                summary = agent.compact_conversation()
                if not summary:
                    return "Nothing to compact (conversation is empty)."

                after_tokens = agent.last_prompt_tokens
                after_pct = ((after_tokens / max_tokens) * 100) if max_tokens > 0 else 0

                summary_preview = summary[:500] + ("..." if len(summary) > 500 else "")
                return (
                    "\u2705 Conversation compacted.\n\n"
                    f"Before: {before_tokens:,}/{max_tokens:,} ({before_pct:.0f}%)\n"
                    f"After: {after_tokens:,}/{max_tokens:,} ({after_pct:.1f}%)\n\n"
                    f"Summary:\n{summary_preview}"
                )
            except Exception as e:
                self._log_event(user_id, "compact:error", str(e)[:200])
                return f"Compaction failed: {str(e)[:200]}"

        return None

    def _process_agent_response(self, user_id: Any, response_text: str) -> BotResponse:
        """Process raw agent response into BotResponse.

        Reads pending_actions from the agent's context and packages them
        into BotResponse for execution by _send_response().
        """
        agent = self.agents.get(user_id)
        actions: list[SendFileAction] = []
        if agent is not None:
            ctx = getattr(agent, "context", None)
            if ctx is not None:
                actions = list(getattr(ctx, "pending_actions", []))
        return BotResponse(text=response_text, actions=actions)

    def _handle_message_common(self, user_id: Any, message: str) -> BotResponse:
        """Common message processing flow used by all platforms.

        Returns:
            BotResponse with text + actions to execute.
        """
        self._log_event(user_id, "message:received", f"len={len(message)}")

        agent = self._get_or_create_agent(user_id)
        raw_response = agent.run(message)

        response = self._process_agent_response(user_id, raw_response)

        self._log_event(user_id, "message:processed", f"chars={len(response.text)}")
        return response

    async def _send_response(self, user_id: Any, response: BotResponse) -> None:
        """Send message with chunking and execute actions (e.g., file delivery)."""
        for chunk in self._chunk_text(response.text):
            try:
                maybe_awaitable = self._send_message(user_id, chunk)
                if isawaitable(maybe_awaitable):
                    await maybe_awaitable
            except Exception as e:
                self._log_event(user_id, "message:send_error", str(e)[:200])
                break

        for action in response.actions:
            try:
                maybe_awaitable = self._send_file(user_id, action)
                if isawaitable(maybe_awaitable):
                    await maybe_awaitable
                self._log_event(user_id, "file:sent", f"path={action.path}")
            except Exception as e:
                self._log_event(user_id, "file:error", str(e)[:200])
