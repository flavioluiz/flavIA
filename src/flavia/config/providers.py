"""Provider configuration for multiple LLM backends."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ModelConfig:
    """Configuration for a single model within a provider."""

    id: str
    name: str
    max_tokens: int = 128000
    default: bool = False
    description: str = ""


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    id: str
    name: str
    api_base_url: str
    api_key: str  # Resolved value
    api_key_env_var: Optional[str] = None  # Original variable name (for display)
    headers: dict[str, str] = field(default_factory=dict)
    models: list[ModelConfig] = field(default_factory=list)

    def get_model_by_id(self, model_id: str) -> Optional[ModelConfig]:
        """Get a model by its ID."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def get_default_model(self) -> Optional[ModelConfig]:
        """Get the default model for this provider."""
        for model in self.models:
            if model.default:
                return model
        return self.models[0] if self.models else None


@dataclass
class ProviderRegistry:
    """Registry of all configured providers."""

    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider_id: Optional[str] = None

    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get a provider by ID."""
        return self.providers.get(provider_id)

    def get_default_provider(self) -> Optional[ProviderConfig]:
        """Get the default provider."""
        if self.default_provider_id and self.default_provider_id in self.providers:
            return self.providers[self.default_provider_id]
        # Fall back to first provider
        if self.providers:
            return next(iter(self.providers.values()))
        return None

    def resolve_model(
        self, model_ref: str | int
    ) -> tuple[Optional[ProviderConfig], Optional[ModelConfig]]:
        """
        Resolve a model reference to provider and model.

        Formats:
        - "provider:model_id" -> Direct lookup
        - "model_id" -> Search across all providers
        - int -> Index in combined model list (backward compatible)

        Returns:
            Tuple of (ProviderConfig, ModelConfig) or (None, None) if not found
        """
        if isinstance(model_ref, int):
            return self._resolve_by_index(model_ref)

        # Check for provider:model_id format
        if ":" in model_ref:
            parts = model_ref.split(":", 1)
            # Handle cases like "hf:model" vs "provider:model_id"
            # If the first part is a known provider, treat it as provider:model
            if parts[0] in self.providers:
                provider = self.providers[parts[0]]
                model = provider.get_model_by_id(parts[1])
                if model:
                    return provider, model
                # Model not found in specified provider
                return provider, None

        # Search for model across all providers (including full model_ref like "hf:model")
        for provider in self.providers.values():
            model = provider.get_model_by_id(model_ref)
            if model:
                return provider, model

        # Not found, return default provider with None model
        return self.get_default_provider(), None

    def _resolve_by_index(
        self, index: int
    ) -> tuple[Optional[ProviderConfig], Optional[ModelConfig]]:
        """Resolve model by index in combined model list."""
        current_index = 0
        for provider in self.providers.values():
            for model in provider.models:
                if current_index == index:
                    return provider, model
                current_index += 1
        return self.get_default_provider(), None

    def get_all_models(self) -> list[tuple[ProviderConfig, ModelConfig]]:
        """Get all models across all providers."""
        models = []
        for provider in self.providers.values():
            for model in provider.models:
                models.append((provider, model))
        return models

    def get_model_count(self) -> int:
        """Get total number of models across all providers."""
        return sum(len(p.models) for p in self.providers.values())


def expand_env_vars(value: str) -> tuple[str, Optional[str]]:
    """
    Expand environment variable references in a string.

    Handles ${VAR_NAME} syntax.

    Args:
        value: String potentially containing ${VAR_NAME} references

    Returns:
        Tuple of (resolved_value, original_var_name or None if no var)
    """
    if not value:
        return value, None

    # Match ${VAR_NAME} pattern
    pattern = r"\$\{([^}]+)\}"
    match = re.search(pattern, value)

    if not match:
        return value, None

    var_name = match.group(1)
    env_value = os.getenv(var_name, "")

    # Replace all occurrences
    resolved = re.sub(pattern, lambda m: os.getenv(m.group(1), ""), value)

    return resolved, var_name


def load_provider_config(data: dict[str, Any], provider_id: str) -> ProviderConfig:
    """Load a single provider configuration from parsed YAML data."""
    name = data.get("name", provider_id)
    api_base_url = data.get("api_base_url", "")

    # Resolve API key
    api_key_raw = data.get("api_key", "")
    api_key, api_key_env_var = expand_env_vars(api_key_raw)

    # Resolve headers
    headers: dict[str, str] = {}
    for header_name, header_value in data.get("headers", {}).items():
        resolved, _ = expand_env_vars(header_value)
        headers[header_name] = resolved

    # Load models
    models: list[ModelConfig] = []
    for model_data in data.get("models", []):
        models.append(
            ModelConfig(
                id=model_data["id"],
                name=model_data.get("name", model_data["id"]),
                max_tokens=model_data.get("max_tokens", 128000),
                default=model_data.get("default", False),
                description=model_data.get("description", ""),
            )
        )

    return ProviderConfig(
        id=provider_id,
        name=name,
        api_base_url=api_base_url,
        api_key=api_key,
        api_key_env_var=api_key_env_var,
        headers=headers,
        models=models,
    )


def load_providers_from_file(file_path: Path) -> ProviderRegistry:
    """
    Load providers from a YAML file.

    Args:
        file_path: Path to providers.yaml file

    Returns:
        ProviderRegistry with loaded providers
    """
    if not file_path.exists():
        return ProviderRegistry()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return ProviderRegistry()

    providers: dict[str, ProviderConfig] = {}

    for provider_id, provider_data in data.get("providers", {}).items():
        providers[provider_id] = load_provider_config(provider_data, provider_id)

    default_provider = data.get("default_provider")

    return ProviderRegistry(providers=providers, default_provider_id=default_provider)


def create_fallback_provider(
    api_key: str, api_base_url: str, default_model: str
) -> ProviderConfig:
    """
    Create a fallback provider from environment variables.

    Used for backward compatibility when no providers.yaml exists.
    """
    return ProviderConfig(
        id="default",
        name="Default",
        api_base_url=api_base_url,
        api_key=api_key,
        api_key_env_var="SYNTHETIC_API_KEY",
        headers={},
        models=[
            ModelConfig(
                id=default_model,
                name=default_model.split(":")[-1] if ":" in default_model else default_model,
                default=True,
            )
        ],
    )


def merge_providers(*registries: ProviderRegistry) -> ProviderRegistry:
    """
    Merge multiple provider registries.

    Later registries take precedence for providers with the same ID.
    The last non-None default_provider_id is used.
    """
    merged_providers: dict[str, ProviderConfig] = {}
    default_provider_id: Optional[str] = None

    for registry in registries:
        for provider_id, provider in registry.providers.items():
            merged_providers[provider_id] = provider

        if registry.default_provider_id:
            default_provider_id = registry.default_provider_id

    return ProviderRegistry(providers=merged_providers, default_provider_id=default_provider_id)
