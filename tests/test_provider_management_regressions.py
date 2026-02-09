"""Regression tests for provider model management flows."""

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.setup.provider_wizard import (
    _models_source_for_provider,
    _search_models,
    manage_provider_models,
)


def _build_settings(models: list[ModelConfig]) -> Settings:
    provider = ProviderConfig(
        id="openai",
        name="OpenAI",
        api_base_url="https://api.openai.com/v1",
        api_key="test-key",
        models=models,
    )
    return Settings(
        providers=ProviderRegistry(
            providers={"openai": provider},
            default_provider_id="openai",
        )
    )


def test_manage_provider_add_model_handles_empty_model_list(monkeypatch):
    settings = _build_settings([])
    choices = iter(["a", "s"])
    saved: dict[str, object] = {}

    def _save_changes(_settings, _provider_id, provider):
        saved["models"] = list(provider.models)
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.Prompt.ask",
        lambda *args, **kwargs: next(choices),
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._add_custom_model",
        lambda: {"id": "gpt-4o", "name": "GPT-4o", "default": True},
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._save_provider_changes",
        _save_changes,
    )

    assert manage_provider_models(settings, "openai") is True
    assert len(saved["models"]) == 1
    assert isinstance(saved["models"][0], ModelConfig)
    assert saved["models"][0].id == "gpt-4o"
    assert saved["models"][0].default is True


def test_manage_provider_merge_fetch_keeps_model_objects(monkeypatch):
    settings = _build_settings([ModelConfig(id="gpt-4o", name="GPT-4o", default=True)])
    choices = iter(["f", "merge", "s"])
    saved: dict[str, object] = {}

    def _save_changes(_settings, _provider_id, provider):
        saved["models"] = list(provider.models)
        return True

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.Prompt.ask",
        lambda *args, **kwargs: next(choices),
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._fetch_models_for_provider",
        lambda _provider: [
            {"id": "gpt-4.1", "name": "GPT-4.1", "default": True},
            {"id": "gpt-4o", "name": "GPT-4o"},
        ],
    )
    monkeypatch.setattr(
        "flavia.setup.provider_wizard._save_provider_changes",
        _save_changes,
    )

    assert manage_provider_models(settings, "openai") is True
    assert len(saved["models"]) == 2
    assert all(isinstance(model, ModelConfig) for model in saved["models"])
    assert {model.id for model in saved["models"]} == {"gpt-4o", "gpt-4.1"}
    assert sum(1 for model in saved["models"] if model.default) == 1


def test_search_models_select_all_returns_all_matches(monkeypatch):
    models = [{"id": f"model-{idx}", "name": f"Model {idx}"} for idx in range(25)]
    answers = iter(["model", "a"])

    monkeypatch.setattr(
        "flavia.setup.provider_wizard.Prompt.ask",
        lambda *args, **kwargs: next(answers),
    )

    selected = _search_models(models)

    assert len(selected) == 25


def test_models_source_for_provider_prefers_existing_configured_models():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "synthetic": ProviderConfig(
                    id="synthetic",
                    name="Synthetic",
                    api_base_url="https://api.synthetic.new/openai/v1",
                    api_key="test-key",
                    models=[
                        ModelConfig(id="hf:deepseek-ai/DeepSeek-V3", name="DeepSeek-V3", default=True),
                        ModelConfig(id="hf:Qwen/Qwen3-235B-A22B-Instruct-2507", name="Qwen3-235B"),
                    ],
                )
            },
            default_provider_id="synthetic",
        )
    )

    models = _models_source_for_provider("synthetic", settings=settings)

    assert [m["id"] for m in models] == [
        "hf:deepseek-ai/DeepSeek-V3",
        "hf:Qwen/Qwen3-235B-A22B-Instruct-2507",
    ]
    assert models[0]["default"] is True
