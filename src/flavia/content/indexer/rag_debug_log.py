"""Persistent RAG diagnostics log utilities."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


RAG_DEBUG_LOG_FILENAME = "rag_debug.jsonl"
RAG_DEBUG_SCHEMA_VERSION = 1


def get_rag_debug_log_path(base_dir: Path) -> Path:
    """Return project-local RAG diagnostics log path."""
    return base_dir / ".flavia" / RAG_DEBUG_LOG_FILENAME


def append_rag_debug_trace(base_dir: Path, payload: dict[str, Any]) -> Optional[str]:
    """Append a structured RAG diagnostics record to `.flavia/rag_debug.jsonl`.

    Returns trace_id when write succeeds; otherwise None.
    """
    log_path = get_rag_debug_log_path(base_dir)
    trace_id = uuid4().hex[:12]
    record = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema_version": RAG_DEBUG_SCHEMA_VERSION,
        **payload,
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return None

    return trace_id


def read_recent_rag_debug_traces(base_dir: Path, limit: int = 1) -> list[dict[str, Any]]:
    """Read the most recent diagnostics traces from log file."""
    if limit <= 0:
        return []

    log_path = get_rag_debug_log_path(base_dir)
    if not log_path.exists():
        return []

    tail: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with open(log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    tail.append(payload)
    except OSError:
        return []

    return list(tail)


def format_rag_debug_trace(trace: dict[str, Any]) -> str:
    """Format retrieval diagnostics for console inspection."""
    params = trace.get("params", {})
    counts = trace.get("counts", {})
    timings = trace.get("timings_ms", {})
    filters = trace.get("filters", {})
    mention_scope = trace.get("mention_scope", {})

    lines = ["[RAG DEBUG]"]
    lines.append(
        "params: "
        f"top_k={params.get('top_k')} "
        f"router_k={params.get('catalog_router_k')} "
        f"vector_k={params.get('vector_k')} "
        f"fts_k={params.get('fts_k')} "
        f"rrf_k={params.get('rrf_k')} "
        f"max_chunks_per_doc={params.get('max_chunks_per_doc')} "
        f"expand_video_temporal={params.get('expand_video_temporal')}"
    )
    lines.append(
        "filters: "
        f"input={filters.get('input_doc_ids_filter_count')} "
        f"effective={filters.get('effective_doc_ids_filter_count')} "
        f"routed={counts.get('routed_doc_ids')}"
    )
    lines.append(
        "hits: "
        f"vector={counts.get('vector_hits', 0)} "
        f"fts={counts.get('fts_hits', 0)} "
        f"unique={counts.get('unique_candidates', 0)} "
        f"final={counts.get('final_results', counts.get('results_before_temporal', 0))} "
        f"skipped_by_diversity={counts.get('skipped_by_doc_diversity', 0)}"
    )
    lines.append(
        "timings_ms: "
        f"router={timings.get('router', 0)} "
        f"vector={timings.get('vector', 0)} "
        f"fts={timings.get('fts', 0)} "
        f"fusion={timings.get('fusion', 0)} "
        f"temporal={timings.get('temporal', 0)} "
        f"total={timings.get('total', 0)}"
    )

    modalities = counts.get("final_modalities") or {}
    if modalities:
        modal_str = ", ".join(f"{k}={v}" for k, v in sorted(modalities.items()))
        lines.append(f"modalities: {modal_str}")
    if mention_scope:
        lines.append(
            "mention_scope: "
            f"mentions={mention_scope.get('query_mentions', [])} "
            f"unresolved={mention_scope.get('unresolved_mentions', [])} "
            f"unindexed={mention_scope.get('unindexed_mentions', [])}"
        )
        lines.append(f"effective_query: {mention_scope.get('effective_query', '')}")

    hints: list[str] = []
    if counts.get("vector_hits", 0) == 0 and counts.get("fts_hits", 0) > 0:
        hints.append("Vector recall is low; consider higher vector_k or chunk tuning.")
    if counts.get("fts_hits", 0) == 0 and counts.get("vector_hits", 0) > 0:
        hints.append("Lexical recall is low; consider higher fts_k or query wording.")
    if counts.get("routed_doc_ids") == 0:
        hints.append("Catalog router found no candidates; inspect summaries/metadata quality.")
    if counts.get("skipped_by_doc_diversity", 0) > 0:
        hints.append("Diversity cap clipped results; consider higher RAG_MAX_CHUNKS_PER_DOC.")

    if hints:
        lines.append("hints:")
        for hint in hints[:4]:
            lines.append(f"- {hint}")

    return "\n".join(lines)
