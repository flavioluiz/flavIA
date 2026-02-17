"""Tests for persistent RAG diagnostics logging."""

from pathlib import Path

from flavia.content.indexer.rag_debug_log import (
    append_rag_debug_trace,
    format_rag_debug_trace,
    get_rag_debug_log_path,
    read_recent_rag_debug_traces,
)


def test_append_and_read_recent_rag_debug_traces(tmp_path: Path):
    trace_id_1 = append_rag_debug_trace(
        tmp_path,
        {
            "query_raw": "q1",
            "trace": {"counts": {"vector_hits": 1, "fts_hits": 0}, "timings_ms": {}},
        },
    )
    trace_id_2 = append_rag_debug_trace(
        tmp_path,
        {
            "query_raw": "q2",
            "trace": {"counts": {"vector_hits": 0, "fts_hits": 2}, "timings_ms": {}},
        },
    )

    assert trace_id_1
    assert trace_id_2

    log_path = get_rag_debug_log_path(tmp_path)
    assert log_path.exists()

    recent = read_recent_rag_debug_traces(tmp_path, limit=1)
    assert len(recent) == 1
    assert recent[0]["trace_id"] == trace_id_2
    assert recent[0]["query_raw"] == "q2"


def test_format_rag_debug_trace_includes_counts_and_timings():
    rendered = format_rag_debug_trace(
        {
            "params": {"top_k": 10, "catalog_router_k": 5, "vector_k": 7, "fts_k": 8, "rrf_k": 60},
            "filters": {"input_doc_ids_filter_count": 2, "effective_doc_ids_filter_count": 1},
            "counts": {
                "routed_doc_ids": 1,
                "vector_hits": 3,
                "fts_hits": 4,
                "unique_candidates": 5,
                "final_results": 2,
                "skipped_by_doc_diversity": 0,
            },
            "timings_ms": {"router": 1.0, "vector": 2.0, "fts": 3.0, "fusion": 1.0, "total": 7.0},
        }
    )
    assert "[RAG DEBUG]" in rendered
    assert "hits: vector=3 fts=4 unique=5 final=2" in rendered
    assert "timings_ms: router=1.0 vector=2.0 fts=3.0 fusion=1.0 temporal=0 total=7.0" in rendered


def test_read_recent_rag_debug_traces_can_filter_by_turn_id(tmp_path: Path):
    append_rag_debug_trace(
        tmp_path,
        {"turn_id": "turn-000001-aa", "query_raw": "q1", "trace": {"counts": {}, "timings_ms": {}}},
    )
    keep_id = append_rag_debug_trace(
        tmp_path,
        {"turn_id": "turn-000002-bb", "query_raw": "q2", "trace": {"counts": {}, "timings_ms": {}}},
    )
    append_rag_debug_trace(
        tmp_path,
        {"turn_id": "turn-000001-aa", "query_raw": "q3", "trace": {"counts": {}, "timings_ms": {}}},
    )

    filtered = read_recent_rag_debug_traces(tmp_path, limit=10, turn_id="turn-000002-bb")
    assert len(filtered) == 1
    assert filtered[0]["trace_id"] == keep_id
    assert filtered[0]["query_raw"] == "q2"
