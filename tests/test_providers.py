"""Tests for provider configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from flavia.config.providers import (
    ProviderConfig,
    ProviderModelConfig,
    load_providers,
    get_provider_for_model,
    get_all_models,
)
from flavia.config.loader import get_config_paths
from flavia.config.settings import load_settings


def test_provider_model_config_creation():
    """Test ProviderModelConfig dataclass creation."""
    model = ProviderModelConfig(
        id="gpt-4o",
        name="GPT-4o",
        description="OpenAI GPT-4o",
        max_tokens=128000,
        default=True,
    )
    
    assert model.id == "gpt-4o"
    assert model.name == "GPT-4o"
    assert model.description == "OpenAI GPT-4o"
    assert model.max_tokens == 128000
    assert model.default is True


def test_provider_config_get_api_key_direct():
    """Test getting API key from direct value."""
    provider = ProviderConfig(
        name="test",
        endpoint="https://api.test.com/v1",
        api_key="direct_key",
    )
    
    assert provider.get_api_key() == "direct_key"


def test_provider_config_get_api_key_from_env(monkeypatch):
    """Test getting API key from environment variable."""
    monkeypatch.setenv("TEST_API_KEY", "env_key")
    
    provider = ProviderConfig(
        name="test",
        endpoint="https://api.test.com/v1",
        api_key_env="TEST_API_KEY",
    )
    
    assert provider.get_api_key() == "env_key"


def test_provider_config_get_api_key_prioritizes_direct():
    """Test that direct API key takes priority over environment variable."""
    with patch.dict(os.environ, {"TEST_API_KEY": "env_key"}):
        provider = ProviderConfig(
            name="test",
            endpoint="https://api.test.com/v1",
            api_key="direct_key",
            api_key_env="TEST_API_KEY",
        )
        
        assert provider.get_api_key() == "direct_key"


def test_provider_config_get_model_by_id():
    """Test getting a model by ID from provider."""
    models = [
        ProviderModelConfig(id="model-1", name="Model 1"),
        ProviderModelConfig(id="model-2", name="Model 2"),
    ]
    
    provider = ProviderConfig(
        name="test",
        endpoint="https://api.test.com/v1",
        models=models,
    )
    
    model = provider.get_model_by_id("model-2")
    assert model is not None
    assert model.id == "model-2"
    assert model.name == "Model 2"
    
    # Test non-existent model
    assert provider.get_model_by_id("model-3") is None


def test_load_providers_from_valid_file(tmp_path):
    """Test loading providers from a valid YAML file."""
    providers_file = tmp_path / "providers.yaml"
    providers_data = {
        "providers": [
            {
                "name": "synthetic",
                "endpoint": "https://api.synthetic.new/openai/v1",
                "api_key_env": "SYNTHETIC_API_KEY",
                "models": [
                    {
                        "id": "hf:moonshotai/Kimi-K2.5",
                        "name": "Kimi-K2.5",
                        "description": "Moonshot AI Kimi K2.5",
                        "max_tokens": 8192,
                        "default": True,
                    },
                    {
                        "id": "hf:zai-org/GLM-4.7",
                        "name": "GLM-4.7",
                        "max_tokens": 8192,
                    },
                ],
            },
            {
                "name": "openai",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "direct_key",
                "models": [
                    {
                        "id": "gpt-4o",
                        "name": "GPT-4o",
                        "max_tokens": 128000,
                    },
                ],
            },
        ]
    }
    
    with open(providers_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(providers_data, f)
    
    providers = load_providers(providers_file)
    
    # Check that both providers were loaded
    assert len(providers) == 2
    assert "synthetic" in providers
    assert "openai" in providers
    
    # Check synthetic provider
    synthetic = providers["synthetic"]
    assert synthetic.name == "synthetic"
    assert synthetic.endpoint == "https://api.synthetic.new/openai/v1"
    assert synthetic.api_key_env == "SYNTHETIC_API_KEY"
    assert synthetic.api_key is None
    assert len(synthetic.models) == 2
    
    # Check synthetic models
    kimi = synthetic.models[0]
    assert kimi.id == "hf:moonshotai/Kimi-K2.5"
    assert kimi.name == "Kimi-K2.5"
    assert kimi.description == "Moonshot AI Kimi K2.5"
    assert kimi.max_tokens == 8192
    assert kimi.default is True
    
    # Check openai provider
    openai = providers["openai"]
    assert openai.name == "openai"
    assert openai.api_key == "direct_key"
    assert len(openai.models) == 1


def test_load_providers_from_nonexistent_file():
    """Test loading providers from a non-existent file returns empty dict."""
    providers = load_providers(Path("/nonexistent/providers.yaml"))
    assert providers == {}


def test_load_providers_from_invalid_file(tmp_path):
    """Test loading providers from invalid YAML file returns empty dict."""
    providers_file = tmp_path / "providers.yaml"
    providers_file.write_text("invalid: yaml: content: :", encoding="utf-8")
    
    providers = load_providers(providers_file)
    assert providers == {}


def test_load_providers_from_empty_file(tmp_path):
    """Test loading providers from empty file returns empty dict."""
    providers_file = tmp_path / "providers.yaml"
    providers_file.write_text("", encoding="utf-8")
    
    providers = load_providers(providers_file)
    assert providers == {}


def test_get_provider_for_model():
    """Test finding provider for a specific model."""
    providers = {
        "synthetic": ProviderConfig(
            name="synthetic",
            endpoint="https://api.synthetic.new/openai/v1",
            models=[
                ProviderModelConfig(id="hf:moonshotai/Kimi-K2.5", name="Kimi-K2.5"),
                ProviderModelConfig(id="hf:zai-org/GLM-4.7", name="GLM-4.7"),
            ],
        ),
        "openai": ProviderConfig(
            name="openai",
            endpoint="https://api.openai.com/v1",
            models=[
                ProviderModelConfig(id="gpt-4o", name="GPT-4o"),
            ],
        ),
    }
    
    # Test finding provider for synthetic model
    provider = get_provider_for_model(providers, "hf:moonshotai/Kimi-K2.5")
    assert provider is not None
    assert provider.name == "synthetic"
    
    # Test finding provider for openai model
    provider = get_provider_for_model(providers, "gpt-4o")
    assert provider is not None
    assert provider.name == "openai"
    
    # Test non-existent model
    provider = get_provider_for_model(providers, "non-existent-model")
    assert provider is None


def test_get_all_models():
    """Test getting all models from all providers."""
    providers = {
        "synthetic": ProviderConfig(
            name="synthetic",
            endpoint="https://api.synthetic.new/openai/v1",
            models=[
                ProviderModelConfig(id="model-1", name="Model 1"),
                ProviderModelConfig(id="model-2", name="Model 2"),
            ],
        ),
        "openai": ProviderConfig(
            name="openai",
            endpoint="https://api.openai.com/v1",
            models=[
                ProviderModelConfig(id="model-3", name="Model 3"),
            ],
        ),
    }
    
    all_models = get_all_models(providers)
    
    assert len(all_models) == 3
    
    # Check that all models are present with their provider names
    model_ids = [(provider_name, model.id) for provider_name, model in all_models]
    assert ("synthetic", "model-1") in model_ids
    assert ("synthetic", "model-2") in model_ids
    assert ("openai", "model-3") in model_ids


def test_providers_priority_local_over_global(tmp_path, monkeypatch):
    """Test that local providers.yaml takes priority over global."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    
    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    
    # Create local config
    local_config = project_dir / ".flavia"
    local_config.mkdir()
    local_providers = {
        "providers": [
            {
                "name": "local_provider",
                "endpoint": "https://local.api.com/v1",
                "api_key": "local_key",
                "models": [{"id": "local-model", "name": "Local Model"}],
            }
        ]
    }
    with open(local_config / "providers.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(local_providers, f)
    
    # Create global config
    user_config = home_dir / ".config" / "flavia"
    user_config.mkdir(parents=True)
    global_providers = {
        "providers": [
            {
                "name": "global_provider",
                "endpoint": "https://global.api.com/v1",
                "api_key": "global_key",
                "models": [{"id": "global-model", "name": "Global Model"}],
            }
        ]
    }
    with open(user_config / "providers.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(global_providers, f)
    
    # Load settings and verify local takes priority
    paths = get_config_paths()
    assert paths.providers_file == local_config / "providers.yaml"
    
    providers = load_providers(paths.providers_file)
    assert "local_provider" in providers
    assert "global_provider" not in providers


def test_providers_global_when_no_local(tmp_path, monkeypatch):
    """Test that global providers.yaml is used when no local config exists."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    
    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    
    # Create only global config
    user_config = home_dir / ".config" / "flavia"
    user_config.mkdir(parents=True)
    global_providers = {
        "providers": [
            {
                "name": "global_provider",
                "endpoint": "https://global.api.com/v1",
                "api_key": "global_key",
                "models": [{"id": "global-model", "name": "Global Model"}],
            }
        ]
    }
    with open(user_config / "providers.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(global_providers, f)
    
    # Load settings and verify global is used
    paths = get_config_paths()
    assert paths.providers_file == user_config / "providers.yaml"
    
    providers = load_providers(paths.providers_file)
    assert "global_provider" in providers


def test_settings_integration_with_providers(tmp_path, monkeypatch):
    """Test that Settings properly loads and integrates provider configuration."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    
    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("TEST_API_KEY", "test_key_value")
    
    # Create local config with providers
    local_config = project_dir / ".flavia"
    local_config.mkdir()
    
    providers_data = {
        "providers": [
            {
                "name": "test_provider",
                "endpoint": "https://test.api.com/v1",
                "api_key_env": "TEST_API_KEY",
                "models": [
                    {"id": "test-model-1", "name": "Test Model 1", "max_tokens": 4096},
                    {"id": "test-model-2", "name": "Test Model 2", "max_tokens": 8192},
                ],
            }
        ]
    }
    with open(local_config / "providers.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(providers_data, f)
    
    # Load settings
    settings = load_settings()
    
    # Verify providers were loaded
    assert len(settings.providers) == 1
    assert "test_provider" in settings.providers
    
    # Verify provider details
    provider = settings.providers["test_provider"]
    assert provider.endpoint == "https://test.api.com/v1"
    assert provider.get_api_key() == "test_key_value"
    assert len(provider.models) == 2
    
    # Test get_provider_for_model
    found_provider = settings.get_provider_for_model("test-model-1")
    assert found_provider is not None
    assert found_provider.name == "test_provider"
    
    # Test get_api_config_for_model
    endpoint, api_key = settings.get_api_config_for_model("test-model-1")
    assert endpoint == "https://test.api.com/v1"
    assert api_key == "test_key_value"


def test_settings_fallback_to_legacy_when_no_provider(tmp_path, monkeypatch):
    """Test that Settings falls back to legacy config when provider not found."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    
    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("SYNTHETIC_API_KEY", "legacy_key")
    monkeypatch.setenv("API_BASE_URL", "https://legacy.api.com/v1")
    
    # Load settings without any providers configured
    settings = load_settings()
    
    # Test fallback to legacy settings for unknown model
    endpoint, api_key = settings.get_api_config_for_model("unknown-model")
    assert endpoint == "https://legacy.api.com/v1"
    assert api_key == "legacy_key"


def test_provider_without_models(tmp_path):
    """Test provider configuration without models."""
    providers_file = tmp_path / "providers.yaml"
    providers_data = {
        "providers": [
            {
                "name": "test",
                "endpoint": "https://api.test.com/v1",
                "api_key": "test_key",
            }
        ]
    }
    
    with open(providers_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(providers_data, f)
    
    providers = load_providers(providers_file)
    
    assert len(providers) == 1
    assert "test" in providers
    assert len(providers["test"].models) == 0


def test_model_default_values():
    """Test that model config uses proper defaults."""
    model = ProviderModelConfig(
        id="test-model",
        name="Test Model",
    )
    
    assert model.description == ""
    assert model.max_tokens is None
    assert model.default is False
