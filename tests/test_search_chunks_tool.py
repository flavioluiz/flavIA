"""Tests for search_chunks tool."""

import hashlib
import json
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
    converted_dir = base_dir / ".converted"
    converted_dir.mkdir(exist_ok=True)
    (converted_dir / "paper.md").write_text("paper content", encoding="utf-8")
    (converted_dir / "lecture.md").write_text("lecture content", encoding="utf-8")
    config_dir = base_dir / ".flavia"
    config_dir.mkdir(exist_ok=True)
    catalog = ContentCatalog(base_dir)
    catalog.build()
    catalog.files["paper.pdf"].converted_to = ".converted/paper.md"
    catalog.files["lecture.mp4"].converted_to = ".converted/lecture.md"
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
    assert "[C-test-0001] paper.pdf — Section 2 > Method (lines 120–170)" in output


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

    assert "[C-test-0001] lecture.mp4 — video transcript" in output
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


def test_search_chunks_debug_persists_trace_without_injecting_output(tmp_path: Path, monkeypatch) -> None:
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
    assert "[RAG DEBUG]" not in output
    assert "Sample evidence." in output

    log_path = tmp_path / ".flavia" / "rag_debug.jsonl"
    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["query_raw"] == "sample"
    assert payload["query_effective"] == "sample"
    assert payload["trace"]["counts"]["vector_hits"] == 4


def test_search_chunks_persists_citation_entries(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)

    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        return [
            {
                "chunk_id": "chunk-1",
                "doc_name": "paper.pdf",
                "modality": "text",
                "heading_path": ["Overview"],
                "locator": {"line_start": 10, "line_end": 20},
                "text": "Sample evidence.",
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)
    output = tool.execute({"query": "sample"}, ctx)
    assert "[C-test-0001]" in output

    citation_log = tmp_path / ".flavia" / "rag_citations.jsonl"
    assert citation_log.exists()
    lines = [line for line in citation_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["citation_id"] == "C-test-0001"
    assert payload["doc_name"] == "paper.pdf"


def test_search_chunks_scopes_by_at_file_reference(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    captured: dict[str, object] = {}

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        captured["question"] = question
        captured["doc_ids_filter"] = doc_ids_filter
        captured["kwargs"] = kwargs
        return [
            {
                "doc_name": "paper.pdf",
                "modality": "text",
                "heading_path": ["Section"],
                "locator": {"line_start": 1, "line_end": 2},
                "text": "Scoped chunk.",
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)
    output = tool.execute({"query": "@paper.pdf transformer backbone"}, ctx)

    catalog = ContentCatalog.load(tmp_path / ".flavia")
    assert catalog is not None
    entry = catalog.files["paper.pdf"]
    expected_doc_id = hashlib.sha1(
        f"{tmp_path}:{entry.path}:{entry.checksum_sha256}".encode()
    ).hexdigest()

    assert captured["question"] == "transformer backbone"
    assert captured["doc_ids_filter"] == [expected_doc_id]
    assert captured["kwargs"]["preserve_doc_scope"] is True
    assert "[C-test-0001] paper.pdf — Section (lines 1–2)" in output


def test_search_chunks_at_file_intersects_with_filters(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)
    monkeypatch.setattr("flavia.content.indexer.retrieve", lambda **_: [])

    result = tool.execute(
        {"query": "@paper.pdf transformer backbone", "file_type_filter": "video"},
        ctx,
    )
    assert "No documents remain after combining @file references" in result


def test_search_chunks_reports_unknown_at_file_reference(tmp_path: Path, monkeypatch) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)
    monkeypatch.setattr("flavia.content.indexer.retrieve", lambda **_: [])

    result = tool.execute({"query": "@missing_document.pdf details"}, ctx)
    assert "No indexed documents match the @file references" in result


def test_search_chunks_auto_enables_exhaustive_mode_for_checklist_queries(
    tmp_path: Path, monkeypatch
) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    captured: dict[str, object] = {}

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        captured["top_k"] = top_k
        captured["kwargs"] = kwargs
        return [
            {
                "doc_name": "paper.pdf",
                "modality": "text",
                "heading_path": ["Checklist"],
                "locator": {"line_start": 1, "line_end": 2},
                "text": "Item list.",
            }
        ]

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)
    output = tool.execute({"query": "procure todos os itens e subitens, sem descrições"}, ctx)

    assert captured["top_k"] >= 30
    assert captured["kwargs"]["retrieval_mode"] == "exhaustive"
    assert captured["kwargs"]["vector_k"] >= 30
    assert captured["kwargs"]["fts_k"] >= 30
    assert "Checklist" in output


def test_search_chunks_rejects_invalid_retrieval_mode(tmp_path: Path) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)

    result = tool.execute({"query": "x", "retrieval_mode": "invalid"}, ctx)
    assert "retrieval_mode must be 'balanced' or 'exhaustive'" in result


def test_search_chunks_exhaustive_backfills_missing_docs_in_multi_doc_scope(
    tmp_path: Path, monkeypatch
) -> None:
    _create_catalog_and_index(tmp_path)
    tool = SearchChunksTool()
    ctx = _make_context(tmp_path)
    monkeypatch.setattr("flavia.config.settings.get_settings", _make_settings_stub)

    catalog = ContentCatalog.load(tmp_path / ".flavia")
    assert catalog is not None
    paper_entry = catalog.files["paper.pdf"]
    lecture_entry = catalog.files["lecture.mp4"]
    paper_doc_id = hashlib.sha1(
        f"{tmp_path}:{paper_entry.path}:{paper_entry.checksum_sha256}".encode()
    ).hexdigest()
    lecture_doc_id = hashlib.sha1(
        f"{tmp_path}:{lecture_entry.path}:{lecture_entry.checksum_sha256}".encode()
    ).hexdigest()

    calls: list[dict[str, object]] = []

    def _fake_retrieve(*, question, base_dir, settings, doc_ids_filter, top_k, **kwargs):
        calls.append(
            {
                "doc_ids_filter": doc_ids_filter,
                "top_k": top_k,
                "catalog_router_k": kwargs.get("catalog_router_k"),
            }
        )
        if isinstance(doc_ids_filter, list) and len(doc_ids_filter) == 2:
            return [
                {
                    "chunk_id": "paper-1",
                    "doc_id": paper_doc_id,
                    "doc_name": "paper.pdf",
                    "modality": "text",
                    "heading_path": ["Expected"],
                    "locator": {"line_start": 10, "line_end": 12},
                    "text": "Expected criteria excerpt.",
                }
            ]
        if doc_ids_filter == [lecture_doc_id]:
            return [
                {
                    "chunk_id": "lecture-1",
                    "doc_id": lecture_doc_id,
                    "doc_name": "lecture.mp4",
                    "modality": "video_transcript",
                    "heading_path": [],
                    "locator": {},
                    "text": "Submitted evidence excerpt.",
                }
            ]
        return []

    monkeypatch.setattr("flavia.content.indexer.retrieve", _fake_retrieve)
    output = tool.execute(
        {
            "query": "@paper.pdf @lecture.mp4 compare item by item",
            "retrieval_mode": "exhaustive",
        },
        ctx,
    )

    assert any(call.get("doc_ids_filter") == [lecture_doc_id] for call in calls)
    assert "[C-test-0001] paper.pdf" in output
    assert "lecture.mp4" in output
