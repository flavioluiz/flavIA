"""Configuration module for flavIA."""

from .settings import Settings, load_settings, get_settings, reset_settings
from .loader import init_local_config, get_config_paths
from .providers import (
    ProviderConfig,
    ProviderRegistry,
    ModelConfig as ProviderModelConfig,
    load_providers_from_file,
    expand_env_vars,
)
from .bots import BotConfig, BotRegistry, BotAccessConfig

__all__ = [
    "Settings",
    "load_settings",
    "get_settings",
    "reset_settings",
    "init_local_config",
    "get_config_paths",
    "ProviderConfig",
    "ProviderRegistry",
    "ProviderModelConfig",
    "load_providers_from_file",
    "expand_env_vars",
    "BotConfig",
    "BotRegistry",
    "BotAccessConfig",
]
