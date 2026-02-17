"""Tests for search_chunks tool."""

import hashlib
from pathlib import Path

from flavia.agent.context import AgentContext
from flavia.agent.profile import AgentPermissions
from flavia.content.catalog import ContentCatalog
from flavia.tools import list_available_tools
from flavia.tools.content.search_chunks import SearchChunksTool


def _make_settings_stub():
    class _Stub:
        rag_catalog_router_k = 20
        rag_vector_k = 15
        rag_fts_k = 15
        rag_rrf_k = 60
        rag_max_chunks_per_doc = 3
        rag_expand_video_temporal = True

    return _Stub()


def _make_context(base_dir: Path, permissions: AgentPermissions | None = None) -> AgentContext:
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


def _create_catalog_and_index(base_dir: Path) -> None:
    (base_dir / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    (base_dir / "lecture.mp4").write_bytes(b"fake video content")
    config_dir = base_dir / ".flavia"
    config_dir.mkdir(exist_ok=True)
    catalog = ContentCatalog(base_dir)
    catalog.build()
    catalog.save(config_dir)
    index_dir = base_dir / ".index"
    index_dir.mkdir(exist_ok=True)
    (index_dir / "index.db").write_text("", encoding="utf-8")


def test_search_chunks_registered() -> None:
    assert "search_chunks" in list_available_tools()


def test_search_chunks_validates_query_and_top_k_types(tmp_path: Path) -> None:
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)

    assert "query parameter is required" in tool.execute({"query": 123}, ctx)
    assert "query parameter is required" in tool.execute({"query": "   "}, ctx)
    assert "top_k must be an integer" in tool.execute({"query": "x", "top_k": "abc"}, ctx)
    assert "top_k must be between 1 and 100" in tool.execute({"query": "x", "top_k": 0}, ctx)


def test_search_chunks_file_type_filter_accepts_pdf_category(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)

    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)
    captured: dict[str, object] = {}

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        captured["question"] = question
        captured["base_dir"] = base_dir
        captured["settings"] = settings
        captured["doc_ids_filter"] = doc_ids_filter
        captured["top_k"] = top_k
        captured["kwargs"] = kwargs
        return [
            {
                "doc_name": "paper.pdf",
                "modality": "text",
                "heading_path": ["Section 2", "Method"],
                "locator": {"line_start": 120, "line_end": 170},
                "text": "The proposed architecture uses a transformer backbone.",
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)

    output = tool.execute({"query": "transformer backbone", "file_type_filter": "PDF"}, ctx)

    catalog = ContentCatalog.load(tmp_path / ".flavia")
    assert catalog is not None
    entry = catalog.files["paper.pdf"]
    expected_doc_id = hashlib.sha1(
        f"{tmp_path}:{entry.path}:{entry.checksum_sha256}".encode()
    ).hexdigest()

    assert captured["doc_ids_filter"] == [expected_doc_id]
    assert captured["top_k"] == 10
    assert captured["kwargs"]["vector_k"] == 15
    assert captured["kwargs"]["fts_k"] == 15
    assert "[1] paper.pdf — Section 2 > Method (lines 120–170)" in output


def test_search_chunks_formats_temporal_bundle_output(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)

    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        return [
            {
                "doc_name": "lecture.mp4",
                "modality": "video_transcript",
                "heading_path": [],
                "locator": {},
                "text": "",
                "temporal_bundle": [
                    {
                        "time_display": "00:01:05-00:01:18",
                        "modality_label": "(Audio)",
                        "text": "We then apply batch normalisation.",
                    },
                    {
                        "time_display": "00:01:12",
                        "modality_label": "(Screen)",
                        "text": "Slide: BatchNorm formula",
                    },
                ],
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)

    output = tool.execute({"query": "batch norm"}, ctx)

    assert "[1] lecture.mp4 — video transcript" in output
    assert '00:01:05-00:01:18 (Audio): "We then apply batch normalisation."' in output
    assert '00:01:12 (Screen): "Slide: BatchNorm formula"' in output


def test_search_chunks_respects_read_permissions(tmp_path: Path) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    permissions = AgentPermissions(
        read_paths=[(tmp_path / "allowed").resolve()],
        write_paths=[(tmp_path / "allowed_out").resolve()],
    )
    ctx = _make_context(tmp_path, permissions=permissions)

    result = tool.execute({"query": "anything"}, ctx)

    assert "Access denied" in result


def test_search_chunks_debug_output_includes_trace(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    ctx.rag_debug = True

    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    def _fake_retrieve(
        *,
        question,
        base_dir,
        settings,
        doc_ids_filter,
        top_k,
        debug_info,
        **kwargs,
    ):
        debug_info.update(
            {
                "params": {
                    "top_k": top_k,
                    "catalog_router_k": kwargs["catalog_router_k"],
                    "vector_k": kwargs["vector_k"],
                    "fts_k": kwargs["fts_k"],
                    "rrf_k": kwargs["rrf_k"],
                    "max_chunks_per_doc": kwargs["max_chunks_per_doc"],
                    "expand_video_temporal": kwargs["expand_video_temporal"],
                },
                "filters": {"input_doc_ids_filter_count": None, "effective_doc_ids_filter_count": None},
                "counts": {
                    "routed_doc_ids": 2,
                    "vector_hits": 4,
                    "fts_hits": 3,
                    "unique_candidates": 5,
                    "final_results": 1,
                    "skipped_by_doc_diversity": 0,
                    "final_modalities": {"text": 1},
                },
                "timings_ms": {"router": 1.0, "vector": 5.0, "fts": 2.0, "fusion": 1.0, "temporal": 0.0, "total": 9.0},
            }
        )
        return [
            {
                "doc_name": "paper.pdf",
                "modality": "text",
                "heading_path": ["Overview"],
                "locator": {"line_start": 10, "line_end": 20},
                "text": "Sample evidence.",
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)
    output = tool.execute({"query": "sample"}, ctx)
    assert "[RAG DEBUG]" in output
    assert "hits: vector=4 fts=3" in output
