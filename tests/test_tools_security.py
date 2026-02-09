"""Security-oriented tests for filesystem tools."""

import os
from pathlib import Path
import tempfile

import pytest

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.content.catalog import ContentCatalog
from flavia.tools.content.get_summary import GetSummaryTool
from flavia.tools.content.query_catalog import QueryCatalogTool
from flavia.tools.content.refresh_catalog import RefreshCatalogTool
from flavia.tools.read.search_files import SearchFilesTool
from flavia.tools.setup.convert_pdfs import ConvertPdfsTool


def make_context(base_dir: Path, permissions: AgentPermissions | None = None) -> AgentContext:
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
        permissions=permissions or AgentPermissions(),
    )


def test_convert_pdfs_blocks_input_path_traversal(tmp_path):
    tool = ConvertPdfsTool()
    ctx = make_context(tmp_path)

    outside_dir = Path(tempfile.mkdtemp())
    outside_pdf = outside_dir / "outside.pdf"
    outside_pdf.write_text("dummy", encoding="utf-8")

    result = tool.execute({"pdf_files": [str(outside_pdf)]}, ctx)
    assert "Access denied" in result


def test_convert_pdfs_blocks_output_path_traversal(tmp_path):
    tool = ConvertPdfsTool()
    ctx = make_context(tmp_path)

    (tmp_path / "inside.pdf").write_text("dummy", encoding="utf-8")

    result = tool.execute(
        {"pdf_files": ["inside.pdf"], "output_dir": "../leak"},
        ctx,
    )
    assert "Write access denied" in result


def test_search_files_skips_symlink_targets_outside_base_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "local.txt").write_text("no secrets here", encoding="utf-8")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("TOP_SECRET_TOKEN", encoding="utf-8")

    symlink_path = project_dir / "link.txt"
    try:
        os.symlink(outside_file, symlink_path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")

    tool = SearchFilesTool()
    ctx = make_context(project_dir)

    result = tool.execute(
        {"pattern": "TOP_SECRET_TOKEN", "path": ".", "file_pattern": "*.txt"},
        ctx,
    )

    assert "No matches found" in result
    assert "link.txt" not in result


def test_convert_pdfs_respects_write_permissions(tmp_path):
    tool = ConvertPdfsTool()
    permissions = AgentPermissions(
        read_paths=[tmp_path.resolve()],
        write_paths=[(tmp_path / "allowed_out").resolve()],
    )
    ctx = make_context(tmp_path, permissions=permissions)

    result = tool.execute(
        {"pdf_files": ["inside.pdf"], "output_dir": "blocked_out"},
        ctx,
    )

    assert "Write access denied" in result


def _create_catalog(base_dir: Path) -> None:
    (base_dir / "notes.md").write_text("# Notes", encoding="utf-8")
    config_dir = base_dir / ".flavia"
    config_dir.mkdir(exist_ok=True)
    catalog = ContentCatalog(base_dir)
    catalog.build()
    catalog.save(config_dir)


def test_refresh_catalog_blocks_when_read_not_allowed(tmp_path):
    _create_catalog(tmp_path)
    tool = RefreshCatalogTool()
    permissions = AgentPermissions(
        read_paths=[(tmp_path / "allowed").resolve()],
        write_paths=[(tmp_path / "allowed").resolve()],
    )
    ctx = make_context(tmp_path, permissions=permissions)

    result = tool.execute({}, ctx)
    assert "Access denied" in result


def test_refresh_catalog_blocks_when_catalog_write_not_allowed(tmp_path):
    _create_catalog(tmp_path)
    tool = RefreshCatalogTool()
    permissions = AgentPermissions(
        read_paths=[tmp_path.resolve()],
        write_paths=[(tmp_path / "allowed_out").resolve()],
    )
    ctx = make_context(tmp_path, permissions=permissions)

    result = tool.execute({}, ctx)
    assert "Write access denied" in result


def test_query_catalog_respects_read_permissions(tmp_path):
    _create_catalog(tmp_path)
    tool = QueryCatalogTool()
    permissions = AgentPermissions(
        read_paths=[(tmp_path / "allowed").resolve()],
        write_paths=[(tmp_path / "allowed_out").resolve()],
    )
    ctx = make_context(tmp_path, permissions=permissions)

    result = tool.execute({}, ctx)
    assert "Access denied" in result


def test_get_catalog_summary_respects_read_permissions(tmp_path):
    _create_catalog(tmp_path)
    tool = GetSummaryTool()
    permissions = AgentPermissions(
        read_paths=[(tmp_path / "allowed").resolve()],
        write_paths=[(tmp_path / "allowed_out").resolve()],
    )
    ctx = make_context(tmp_path, permissions=permissions)

    result = tool.execute({}, ctx)
    assert "Access denied" in result
