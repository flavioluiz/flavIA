"""Tests for content conversion/fetch tools."""

from pathlib import Path

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.content.catalog import ContentCatalog
from flavia.content.scanner import FileEntry
from flavia.tools.content._conversion_helpers import parse_bool_arg
from flavia.tools.content.fetch_online_source import FetchOnlineSourceTool


def _make_context(base_dir: Path) -> AgentContext:
    return AgentContext(
        agent_id="test",
        name="test",
        current_depth=0,
        max_depth=3,
        parent_id=None,
        base_dir=base_dir,
        available_tools=[],
        subagents={},
        model_id="test-model",
        messages=[],
        permissions=AgentPermissions(),
    )


def _create_catalog(base_dir: Path) -> Path:
    config_dir = base_dir / ".flavia"
    config_dir.mkdir(exist_ok=True)
    catalog = ContentCatalog(base_dir)
    catalog.build()
    catalog.save(config_dir)
    return config_dir


def _find_online_entry(catalog: ContentCatalog, source_url: str) -> FileEntry | None:
    return next((e for e in catalog.files.values() if e.source_url == source_url), None)


def test_fetch_online_source_persists_new_entry_when_dependencies_missing(tmp_path, monkeypatch):
    class _DepsMissingConverter:
        is_implemented = True

        @staticmethod
        def check_dependencies():
            return False, ["fake-online-dependency"]

        @staticmethod
        def get_metadata(_source_url: str):
            return {"title": "Example"}

    from flavia.content.converters import converter_registry

    monkeypatch.setattr(
        converter_registry,
        "get_for_source",
        lambda _source_type: _DepsMissingConverter(),
    )

    config_dir = _create_catalog(tmp_path)
    ctx = _make_context(tmp_path)
    tool = FetchOnlineSourceTool()
    url = "https://example.com/article"

    result = tool.execute({"source_url": url, "source_type": "webpage"}, ctx)

    assert "Missing dependencies" in result

    persisted = ContentCatalog.load(config_dir)
    assert persisted is not None
    entry = _find_online_entry(persisted, url)
    assert entry is not None
    assert entry.fetch_status == "pending"
    assert entry.source_type == "webpage"


def test_fetch_online_source_persists_entry_when_converter_not_implemented(
    tmp_path, monkeypatch
):
    class _NotImplementedConverter:
        is_implemented = False

        @staticmethod
        def get_metadata(_source_url: str):
            return {"title": "Example"}

    from flavia.content.converters import converter_registry

    monkeypatch.setattr(
        converter_registry,
        "get_for_source",
        lambda _source_type: _NotImplementedConverter(),
    )

    config_dir = _create_catalog(tmp_path)
    ctx = _make_context(tmp_path)
    tool = FetchOnlineSourceTool()
    url = "https://example.com/not-implemented"

    result = tool.execute({"source_url": url, "source_type": "webpage"}, ctx)

    assert "not yet implemented" in result

    persisted = ContentCatalog.load(config_dir)
    assert persisted is not None
    entry = _find_online_entry(persisted, url)
    assert entry is not None
    assert entry.fetch_status == "not_implemented"
    assert entry.source_type == "webpage"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("", False),
    ],
)
def test_parse_bool_arg_handles_string_inputs(raw, expected):
    assert parse_bool_arg(raw, default=False) is expected
