"""Bot configuration for multiple messaging platform instances."""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .providers import expand_env_vars


@dataclass
class BotAccessConfig:
    """Access control settings for a bot."""

    allowed_users: list[int] = field(default_factory=list)
    allow_all: bool = False
    # True when access.allowed_users is explicitly configured in YAML/env.
    allowed_users_configured: bool = False

    @property
    def whitelist_configured(self) -> bool:
        """True if an explicit user whitelist was provided."""
        return self.allowed_users_configured or bool(self.allowed_users)


@dataclass
class BotConfig:
    """Configuration for a single bot instance."""

    id: str
    platform: str  # e.g. "telegram", "whatsapp", "web"
    token: str  # Resolved token value
    token_env_var: Optional[str] = None  # Original ${VAR} name (for display)
    default_agent: str = "main"
    # None means all agents are permitted; a list restricts to those names.
    allowed_agents: Optional[list[str]] = None
    access: BotAccessConfig = field(default_factory=BotAccessConfig)

    def is_agent_allowed(self, agent_name: str) -> bool:
        """Return True if the given agent name is allowed for this bot."""
        if self.allowed_agents is None:
            return True
        return agent_name in self.allowed_agents


@dataclass
class BotRegistry:
    """Registry of all configured bot instances."""

    bots: dict[str, BotConfig] = field(default_factory=dict)

    def get_bot(self, bot_id: str) -> Optional[BotConfig]:
        """Get a bot by its ID."""
        return self.bots.get(bot_id)

    def get_bots_by_platform(self, platform: str) -> list[BotConfig]:
        """Get all bots for a given platform."""
        return [b for b in self.bots.values() if b.platform == platform]

    def get_telegram_bots(self) -> list[BotConfig]:
        """Get all Telegram bots."""
        return self.get_bots_by_platform("telegram")

    def get_first_telegram_bot(self) -> Optional[BotConfig]:
        """Get the first configured Telegram bot, or None."""
        tg = self.get_telegram_bots()
        return tg[0] if tg else None


def _parse_allowed_agents(value: Any) -> Optional[list[str]]:
    """
    Parse the allowed_agents field.

    - Omitted or "all" → None (unrestricted)
    - A list of strings → that list
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == "all":
        return None
    if isinstance(value, list):
        return [str(a) for a in value if a]
    return None


def _parse_allowed_users(value: Any) -> list[int]:
    """Parse allowed_users into a list[int], skipping invalid entries."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]

    parsed: list[int] = []
    for item in items:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean values safely from YAML-friendly inputs."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def load_bot_config(data: dict[str, Any], bot_id: str) -> BotConfig:
    """Load a single bot configuration from parsed YAML data."""
    platform = str(data.get("platform", "telegram"))
    token_raw = str(data.get("token", ""))
    token, token_env_var = expand_env_vars(token_raw)
    default_agent = str(data.get("default_agent", "main"))
    allowed_agents = _parse_allowed_agents(data.get("allowed_agents"))

    access_data = data.get("access", {})
    if not isinstance(access_data, dict):
        access_data = {}
    allowed_users_configured = "allowed_users" in access_data
    allowed_users_raw = access_data.get("allowed_users")
    allowed_users = _parse_allowed_users(allowed_users_raw)
    access = BotAccessConfig(
        allowed_users=allowed_users,
        allow_all=_parse_bool(access_data.get("allow_all", False), default=False),
        allowed_users_configured=allowed_users_configured,
    )

    return BotConfig(
        id=bot_id,
        platform=platform,
        token=token,
        token_env_var=token_env_var,
        default_agent=default_agent,
        allowed_agents=allowed_agents,
        access=access,
    )


def load_bots_from_file(file_path: Path) -> BotRegistry:
    """
    Load bots from a YAML file.

    Args:
        file_path: Path to bots.yaml

    Returns:
        BotRegistry with loaded bots (empty if file missing or invalid)
    """
    if not file_path.exists():
        return BotRegistry()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return BotRegistry()

    if not isinstance(data, dict):
        return BotRegistry()

    bots_data = data.get("bots") or {}
    if not isinstance(bots_data, dict):
        return BotRegistry()

    bots: dict[str, BotConfig] = {}
    for bot_id, bot_data in bots_data.items():
        if not isinstance(bot_data, dict):
            continue
        try:
            bots[str(bot_id)] = load_bot_config(bot_data, str(bot_id))
        except Exception:
            continue

    return BotRegistry(bots=bots)


def create_fallback_telegram_bot(
    token: str,
    allowed_users: list[int],
    allow_all: bool,
    whitelist_configured: bool = False,
) -> BotConfig:
    """
    Create a BotConfig from legacy environment variables.

    Used for backward compatibility when no bots.yaml exists.
    """
    return BotConfig(
        id="default",
        platform="telegram",
        token=token,
        token_env_var="TELEGRAM_BOT_TOKEN",
        default_agent="main",
        allowed_agents=None,
        access=BotAccessConfig(
            allowed_users=allowed_users,
            allow_all=allow_all,
            allowed_users_configured=whitelist_configured,
        ),
    )


def merge_bot_registries(*registries: BotRegistry) -> BotRegistry:
    """
    Merge multiple bot registries.

    Later registries take precedence for bots with the same ID.
    """
    merged: dict[str, BotConfig] = {}
    for reg in registries:
        merged.update(reg.bots)
    return BotRegistry(bots=merged)
