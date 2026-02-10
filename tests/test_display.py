"""Tests for shared CLI display helpers."""

from flavia.config.loader import ConfigPaths
from flavia.config.providers import ModelConfig, ProviderConfig, ProviderRegistry
from flavia.config.settings import Settings
from flavia.display import display_config, display_providers, display_tools


class _FakeTool:
    def __init__(self, name: str, description: str, category: str):
        self.name = name
        self.description = description
        self.category = category


class _FakeRegistry:
    def __init__(self, tools: dict[str, _FakeTool]):
        self._tools = tools

    def get_all(self) -> dict[str, _FakeTool]:
        return self._tools


def test_display_tools_plain_text_keeps_category_headers(monkeypatch, capsys):
    tools = {
        "list_files": _FakeTool("list_files", "List files", "read"),
        "query_catalog": _FakeTool("query_catalog", "Query catalog", "content"),
    }
    monkeypatch.setattr("flavia.tools.get_registry", lambda: _FakeRegistry(tools))

    display_tools(use_rich=False)

    out = capsys.readouterr().out
    assert "[READ]" in out
    assert "[CONTENT]" in out


def test_display_providers_plain_text_keeps_default_marker(capsys):
    settings = Settings(
        providers=ProviderRegistry(
            providers={
                "synthetic": ProviderConfig(
                    id="synthetic",
                    name="Synthetic",
                    api_base_url="https://api.synthetic.new/openai/v1",
                    api_key="key",
                    models=[ModelConfig(id="model-a", name="Model A", default=True)],
                )
            },
            default_provider_id="synthetic",
        )
    )

    display_providers(settings, use_rich=False)

    out = capsys.readouterr().out
    assert "(synthetic) [DEFAULT]" in out


def test_display_config_does_not_create_project_dir(tmp_path, capsys):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    settings = Settings(
        base_dir=project_dir,
        config_paths=ConfigPaths(
            local_dir=None,
            user_dir=None,
            package_dir=tmp_path / "does-not-exist",
        ),
    )

    assert not (project_dir / ".flavia").exists()

    display_config(settings, use_rich=False)

    capsys.readouterr()
    assert not (project_dir / ".flavia").exists()
