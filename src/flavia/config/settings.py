"""Settings management for flavIA."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

from .loader import get_config_paths, ConfigPaths
from .providers import ProviderConfig, load_providers, get_provider_for_model


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    id: str
    name: str
    description: str = ""
    default: bool = False


@dataclass
class Settings:
    """Application settings loaded from environment and config files."""

    # API settings
    api_key: str = ""
    api_base_url: str = "https://api.synthetic.new/openai/v1"

    # Paths
    base_dir: Path = field(default_factory=Path.cwd)
    config_paths: Optional[ConfigPaths] = None

    # Agent defaults
    default_model: str = "hf:moonshotai/Kimi-K2.5"
    max_depth: int = 3
    parallel_workers: int = 4

    # Telegram settings
    telegram_token: str = ""
    telegram_allowed_users: list[int] = field(default_factory=list)
    telegram_allow_all_users: bool = False
    telegram_whitelist_configured: bool = False

    # Runtime
    verbose: bool = False

    # Loaded configs
    models: list[ModelConfig] = field(default_factory=list)
    agents_config: dict[str, Any] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)

    def get_model_by_index(self, index: int) -> Optional[ModelConfig]:
        """Get model by index."""
        if 0 <= index < len(self.models):
            return self.models[index]
        return None

    def get_model_by_id(self, model_id: str) -> Optional[ModelConfig]:
        """Get model by ID."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def get_default_model(self) -> Optional[ModelConfig]:
        """Get the default model."""
        for model in self.models:
            if model.default:
                return model
        return self.models[0] if self.models else None

    def resolve_model(self, model_ref: str | int) -> str:
        """Resolve model reference (index or ID) to model ID."""
        if isinstance(model_ref, int):
            model = self.get_model_by_index(model_ref)
            return model.id if model else self.default_model
        return model_ref

    def get_provider_for_model(self, model_id: str) -> Optional[ProviderConfig]:
        """Get the provider configuration for a specific model."""
        return get_provider_for_model(self.providers, model_id)
    
    def get_api_config_for_model(self, model_id: str) -> tuple[str, str]:
        """
        Get API endpoint and key for a specific model.
        
        Returns:
            Tuple of (endpoint, api_key)
        """
        provider = self.get_provider_for_model(model_id)
        if provider:
            return provider.endpoint, provider.get_api_key()
        
        # Fallback to legacy settings
        return self.api_base_url, self.api_key


def load_models(models_file: Optional[Path]) -> list[ModelConfig]:
    """Load models from YAML file."""
    if not models_file or not models_file.exists():
        return []

    try:
        with open(models_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        models = []
        for m in data.get("models", []):
            models.append(ModelConfig(
                id=m["id"],
                name=m.get("name", m["id"]),
                description=m.get("description", ""),
                default=m.get("default", False)
            ))
        return models
    except Exception:
        return []


def load_agents_config(agents_file: Optional[Path]) -> dict[str, Any]:
    """Load agents configuration from YAML file."""
    if not agents_file or not agents_file.exists():
        return {}

    try:
        with open(agents_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_settings() -> Settings:
    """
    Load settings from all configuration sources.

    Priority (highest to lowest):
    1. Environment variables (including from .env files)
    2. Local .flavia/ directory
    3. User ~/.config/flavia/ directory
    4. Package defaults
    """
    # Discover config paths
    paths = get_config_paths()

    # Load .env file (local takes priority)
    if paths.env_file:
        load_dotenv(paths.env_file, override=True)

    # Parse Telegram access controls
    allow_all_raw = os.getenv("TELEGRAM_ALLOW_ALL_USERS", "").strip().lower()
    allow_all_users = allow_all_raw in {"1", "true", "yes", "y", "on"}

    allowed_users_env = os.getenv("TELEGRAM_ALLOWED_USER_IDS")
    allowed_users_str = (allowed_users_env or "").strip()
    whitelist_configured = bool(allowed_users_str)
    allowed_users = []
    if allowed_users_str.lower() in {"*", "all", "public"}:
        allow_all_users = True
        whitelist_configured = False
    elif allowed_users_str:
        for uid in allowed_users_str.split(","):
            uid = uid.strip()
            if not uid:
                continue
            try:
                allowed_users.append(int(uid))
            except ValueError:
                continue

    # Build settings
    settings = Settings(
        api_key=os.getenv("SYNTHETIC_API_KEY", ""),
        api_base_url=os.getenv("API_BASE_URL", "https://api.synthetic.new/openai/v1"),
        base_dir=Path.cwd(),  # Always use current directory as base
        config_paths=paths,
        default_model=os.getenv("DEFAULT_MODEL", "hf:moonshotai/Kimi-K2.5"),
        max_depth=int(os.getenv("AGENT_MAX_DEPTH", "3")),
        parallel_workers=int(os.getenv("AGENT_PARALLEL_WORKERS", "4")),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_users=allowed_users,
        telegram_allow_all_users=allow_all_users,
        telegram_whitelist_configured=whitelist_configured,
    )

    # Load providers first
    settings.providers = load_providers(paths.providers_file)
    
    # Load models and agents config
    settings.models = load_models(paths.models_file)
    settings.agents_config = load_agents_config(paths.agents_file)

    # If no models loaded, use defaults
    if not settings.models:
        settings.models = [
            ModelConfig(
                id="hf:moonshotai/Kimi-K2.5",
                name="Kimi-K2.5",
                default=True,
            )
        ]

    return settings


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Reset global settings (useful for testing or directory change)."""
    global _settings
    _settings = None
