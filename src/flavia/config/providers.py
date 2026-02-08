"""Provider configuration management for flavIA."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ProviderModelConfig:
    """Configuration for a model within a provider."""
    id: str
    name: str
    description: str = ""
    max_tokens: Optional[int] = None
    default: bool = False


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    endpoint: str
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    models: list[ProviderModelConfig] = field(default_factory=list)
    
    def get_api_key(self) -> str:
        """Get API key from direct value or environment variable."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            import os
            return os.getenv(self.api_key_env, "")
        return ""
    
    def get_model_by_id(self, model_id: str) -> Optional[ProviderModelConfig]:
        """Get a specific model by ID."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None


def load_providers(providers_file: Optional[Path]) -> dict[str, ProviderConfig]:
    """
    Load providers from YAML file.
    
    Args:
        providers_file: Path to providers.yaml file
        
    Returns:
        Dictionary mapping provider names to ProviderConfig objects
    """
    if not providers_file or not providers_file.exists():
        return {}
    
    try:
        with open(providers_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if not data or "providers" not in data:
            return {}
        
        providers = {}
        for provider_data in data["providers"]:
            name = provider_data["name"]
            
            # Parse models for this provider
            models = []
            for model_data in provider_data.get("models", []):
                models.append(ProviderModelConfig(
                    id=model_data["id"],
                    name=model_data.get("name", model_data["id"]),
                    description=model_data.get("description", ""),
                    max_tokens=model_data.get("max_tokens"),
                    default=model_data.get("default", False),
                ))
            
            providers[name] = ProviderConfig(
                name=name,
                endpoint=provider_data["endpoint"],
                api_key=provider_data.get("api_key"),
                api_key_env=provider_data.get("api_key_env"),
                models=models,
            )
        
        return providers
    except Exception as e:
        # Log error but don't crash
        print(f"Warning: Error loading providers file: {e}")
        return {}


def get_provider_for_model(providers: dict[str, ProviderConfig], model_id: str) -> Optional[ProviderConfig]:
    """
    Find which provider provides a specific model.
    
    Args:
        providers: Dictionary of provider configurations
        model_id: Model identifier to search for
        
    Returns:
        ProviderConfig that provides this model, or None
    """
    for provider in providers.values():
        if provider.get_model_by_id(model_id):
            return provider
    return None


def get_all_models(providers: dict[str, ProviderConfig]) -> list[tuple[str, ProviderModelConfig]]:
    """
    Get all models from all providers.
    
    Returns:
        List of (provider_name, model_config) tuples
    """
    all_models = []
    for provider_name, provider in providers.items():
        for model in provider.models:
            all_models.append((provider_name, model))
    return all_models
