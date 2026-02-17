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
from flavia.tools.permissions import check_read_permission
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


def test_converted_access_mode_strict_blocks_direct_reads(tmp_path):
    converted = tmp_path / ".converted"
    converted.mkdir()
    target = converted / "video.md"
    target.write_text("content", encoding="utf-8")

    ctx = make_context(tmp_path)
    ctx.converted_access_mode = "strict"

    allowed, error = check_read_permission(target, ctx)
    assert not allowed
    assert "converted_access_mode: strict" in error


def test_converted_access_mode_hybrid_requires_search_chunks(tmp_path):
    converted = tmp_path / ".converted"
    converted.mkdir()
    target = converted / "video.md"
    target.write_text("content", encoding="utf-8")
    index_dir = tmp_path / ".index"
    index_dir.mkdir()
    (index_dir / "index.db").write_text("", encoding="utf-8")

    ctx = make_context(tmp_path)
    ctx.converted_access_mode = "hybrid"
    ctx.available_tools = ["search_chunks"]
    ctx.messages = []

    allowed, error = check_read_permission(target, ctx)
    assert not allowed
    assert "search_chunks" in error

    ctx.messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "search_chunks", "arguments": '{"query":"laplace"}'},
                }
            ],
        }
    ]
    allowed_after, _ = check_read_permission(target, ctx)
    assert allowed_after
