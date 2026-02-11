"""Tests for CLI TAB completion helpers."""

from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.interfaces import cli_interface


def test_command_completion_suggests_agent_command():
    settings = Settings()

    candidates = cli_interface._completion_candidates("/ag", "/ag", settings)

    assert "/agent " in candidates


def test_agent_argument_completion_lists_available_agents(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        agents_config={
            "main": {
                "context": "Main",
                "tools": [],
                "subagents": {
                    "reviewer": {"context": "Review", "tools": []},
                    "summarizer": {"context": "Summary", "tools": []},
                },
            }
        },
    )

    candidates = cli_interface._completion_candidates("re", "/agent re", settings)

    assert candidates == ["reviewer"]


def test_provider_argument_completion_lists_provider_ids():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                ),
                "openrouter": ProviderConfig(
                    id="openrouter",
                    name="OpenRouter",
                    api_base_url="https://openrouter.ai/api/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="openai/gpt-4o-mini", name="GPT-4o Mini", default=True)],
                ),
            },
            default_provider_id="openai",
        )
    )

    candidates = cli_interface._completion_candidates("open", "/provider-test open", settings)

    assert candidates == ["openai", "openrouter"]


def test_model_argument_completion_uses_provider_prefixed_refs_only():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                ),
            },
            default_provider_id="openai",
        )
    )

    candidates = cli_interface._completion_candidates("openai", "/model openai", settings)

    assert "openai:gpt-4o" in candidates
    assert "gpt-4o" not in candidates


def test_model_argument_completion_matches_by_model_id_with_prefixed_output():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                ),
            },
            default_provider_id="openai",
        )
    )

    candidates = cli_interface._completion_candidates("gpt", "/model gpt", settings)

    assert "openai:gpt-4o" in candidates
    assert "gpt-4o" not in candidates


def test_model_argument_completion_does_not_suggest_numeric_indexes():
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "openai": ProviderConfig(
                    id="openai",
                    name="OpenAI",
                    api_base_url="https://api.openai.com/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="gpt-4o", name="GPT-4o", default=True)],
                ),
            },
            default_provider_id="openai",
        )
    )

    candidates = cli_interface._completion_candidates("0", "/model 0", settings)

    assert candidates == []
    assert "0" not in candidates
    assert "openai:gpt-4o" not in candidates


def test_path_completion_suggests_files_and_directories(tmp_path):
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    settings = Settings(base_dir=tmp_path)

    candidates = cli_interface._completion_candidates("n", "n", settings)
    dir_candidates = cli_interface._completion_candidates("do", "do", settings)

    assert "notes.md" in candidates
    assert "docs/" in dir_candidates


def test_at_path_completion_suggests_mention_style_paths(tmp_path):
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    settings = Settings(base_dir=tmp_path)

    file_candidates = cli_interface._completion_candidates("@n", "@n", settings)
    dir_candidates = cli_interface._completion_candidates("@do", "@do", settings)

    assert "@notes.md" in file_candidates
    assert "@docs/" in dir_candidates
