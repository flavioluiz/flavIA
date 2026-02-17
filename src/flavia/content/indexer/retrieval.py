"""Hybrid retrieval combining vector and FTS search with RRF fusion.

This module implements Reciprocal Rank Fusion (RRF) to combine results from
semantic (vector) search and full-text search into a unified ranking.
"""

import hashlib
import re
import sqlite3
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Optional

from flavia.config import Settings

from ..catalog import ContentCatalog
from .embedder import embed_query, get_embedding_client
from .fts import FTSIndex
from .vector_store import VectorStore
from .video_retrieval import expand_video_chunks


def _catalog_doc_id(base_dir: Path, path: str, checksum: str) -> str:
    """Reproduce chunker doc_id derivation for catalog routing."""
    raw = f"{base_dir}:{path}:{checksum}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _catalog_router_tokens(question: str) -> list[str]:
    """Extract normalized terms for catalog Stage-A routing."""
    tokens = re.findall(r"[A-Za-z0-9_-]{2,}", question.lower())
    # Preserve order while deduplicating
    return list(dict.fromkeys(tokens))


def _route_doc_ids_from_catalog(
    question: str,
    base_dir: Path,
    shortlist_k: int = 20,
    scope_doc_ids: Optional[list[str]] = None,
) -> Optional[list[str]]:
    """Stage A router: shortlist doc_ids using catalog summaries + metadata.

    Returns:
        - None: routing unavailable (e.g. catalog missing/unreadable)
        - []: routing ran but found no candidates
        - [doc_id, ...]: shortlisted candidates
    """
    if shortlist_k <= 0:
        return []

    catalog = ContentCatalog.load(base_dir / ".flavia")
    if catalog is None:
        return None

    scope = set(scope_doc_ids) if scope_doc_ids is not None else None
    rows: list[tuple[str, str]] = []
    for entry in catalog.files.values():
        if entry.status == "missing":
            continue
        # Retrieval indexes only converted sources. Skip catalog entries that
        # cannot produce chunks to avoid over-filtering Stage B to empty scopes.
        if not getattr(entry, "converted_to", None):
            continue

        doc_id = _catalog_doc_id(base_dir, entry.path, entry.checksum_sha256)
        if scope is not None and doc_id not in scope:
            continue

        content_parts = [
            entry.path,
            entry.name,
            entry.file_type,
            entry.category,
            entry.source_type,
            entry.summary or "",
            entry.extraction_quality or "",
            entry.source_url or "",
        ]
        if entry.tags:
            content_parts.append(" ".join(entry.tags))
        if entry.source_metadata:
            content_parts.extend(str(v) for v in entry.source_metadata.values())

        searchable = " ".join(p for p in content_parts if p).strip()
        if searchable:
            rows.append((doc_id, searchable))

    if not rows:
        return []

    tokens = _catalog_router_tokens(question)
    if not tokens:
        return []

    # Query terms are quoted and OR-ed to avoid FTS syntax edge cases.
    fts_query = " OR ".join(f'"{t}"' for t in tokens[:16])

    try:
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE VIRTUAL TABLE catalog_fts USING fts5(
                    doc_id UNINDEXED,
                    content,
                    tokenize = 'porter unicode61'
                )
                """
            )
            conn.executemany(
                "INSERT INTO catalog_fts (doc_id, content) VALUES (?, ?)",
                rows,
            )
            cursor = conn.execute(
                """
                SELECT doc_id, bm25(catalog_fts) AS bm25_score
                FROM catalog_fts
                WHERE catalog_fts MATCH ?
                ORDER BY bm25_score
                LIMIT ?
                """,
                (fts_query, shortlist_k),
            )

            shortlisted: list[str] = []
            seen: set[str] = set()
            for row in cursor:
                doc_id = row["doc_id"]
                if doc_id not in seen:
                    seen.add(doc_id)
                    shortlisted.append(doc_id)
            return shortlisted
    except sqlite3.Error:
        # Graceful fallback: if FTS5 is unavailable, do simple token-overlap routing.
        token_set = set(tokens)
        scored: list[tuple[int, str]] = []
        for doc_id, searchable in rows:
            doc_terms = set(re.findall(r"[A-Za-z0-9_-]{2,}", searchable.lower()))
            overlap = len(token_set & doc_terms)
            if overlap > 0:
                scored.append((overlap, doc_id))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [doc_id for _, doc_id in scored[:shortlist_k]]


def _rrf_score(ranks: list[Optional[int]], k: int = 60) -> float:
    """Calculate RRF score from multiple ranking positions.

    Reciprocal Rank Fusion formula: score(d) = Σ 1/(k + rank_i(d))

    This combines rankings from multiple sources (vector and FTS) into a
    single score. Documents ranked higher in either source get higher scores.

    Args:
        ranks: List of rank positions (1-indexed). None means not ranked
               (not found in that source).
        k: RRF constant (default 60). Higher k gives more uniform scores
           across different rank positions.

    Returns:
        RRF score (higher = better). Score of 0 means document not ranked
        in any source.
    """
    score = 0.0
    for rank in ranks:
        if rank is not None:
            score += 1.0 / (k + rank)
    return score


def _get_doc_id(chunk_id: str, vector_results: list, fts_results: list) -> str:
    """Get doc_id for a chunk from either result set.

    Args:
        chunk_id: The chunk identifier to look up.
        vector_results: Results from vector search.
        fts_results: Results from FTS search.

    Returns:
        The doc_id string, or empty string if not found (should never happen).
    """
    for r in vector_results:
        if r["chunk_id"] == chunk_id:
            return r["doc_id"]
    for r in fts_results:
        if r["chunk_id"] == chunk_id:
            return r["doc_id"]
    return ""


def _merge_chunk_data(
    chunk_id: str,
    rrf_score: float,
    vector_rank: Optional[int],
    fts_rank: Optional[int],
    vector_results: list,
    fts_results: list,
) -> dict[str, Any]:
    """Merge data from vector and FTS results into unified format.

    Prefers vector result metadata (has more fields like converted_path,
    locator, etc.) and FTS result text. If data is missing, tries the
    other source.

    Args:
        chunk_id: The chunk identifier.
        rrf_score: The RRF fusion score.
        vector_rank: Rank from vector search (1-indexed) or None.
        fts_rank: Rank from FTS search (1-indexed) or None.
        vector_results: Results from vector search.
        fts_results: Results from FTS search.

    Returns:
        Unified result dict with keys: chunk_id, doc_id, text, score,
        vector_rank, fts_rank, and metadata fields.
    """
    # Prefer vector result for metadata (has more fields)
    v_data = next((r for r in vector_results if r["chunk_id"] == chunk_id), None)
    f_data = next((r for r in fts_results if r["chunk_id"] == chunk_id), None)

    # Always return a stable schema, even for FTS-only or vector-only hits.
    result: dict[str, Any] = {
        "chunk_id": chunk_id,
        "doc_id": "",
        "text": "",
        "score": rrf_score,
        "vector_rank": vector_rank,
        "fts_rank": fts_rank,
        "modality": "",
        "heading_path": [],
        "doc_name": "",
        "file_type": "",
        "locator": {},
        "converted_path": "",
    }

    # Add metadata from vector result if available
    if v_data:
        result.update(
            {
                "doc_id": v_data["doc_id"],
                "modality": v_data["modality"],
                "heading_path": v_data["heading_path"],
                "doc_name": v_data["doc_name"],
                "file_type": v_data["file_type"],
                "locator": v_data["locator"],
                "converted_path": v_data["converted_path"],
            }
        )

    # Add text from FTS result if available
    if f_data:
        result["text"] = f_data["text"]
        # Fill in missing metadata from FTS if vector result missing
        if not result["doc_id"]:
            result["doc_id"] = f_data["doc_id"]
            result["modality"] = f_data["modality"]
            result["heading_path"] = f_data["heading_path"]

    return result


def retrieve(
    question: str,
    base_dir: Path,
    settings: Settings,
    doc_ids_filter: Optional[list[str]] = None,
    top_k: int = 10,
    catalog_router_k: int = 20,
    vector_k: int = 15,
    fts_k: int = 15,
    rrf_k: int = 60,
    max_chunks_per_doc: int = 3,
    expand_video_temporal: bool = True,
    debug_info: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Hybrid retrieval combining vector and FTS search with RRF fusion.

    Performs Stage A catalog routing, then Stage B semantic (vector) and
    full-text (FTS) searches, then
    combines results using Reciprocal Rank Fusion (RRF). Applies diversity
    filtering to limit chunks per document.

    Args:
        question: User query string.
        base_dir: Vault base directory.
        settings: Application settings (for embedding client).
        doc_ids_filter: Optional list of doc_ids to restrict search.
            - None: Search all documents (default)
            - []: Return empty results (explicit empty scope)
            - ["id1", "id2"]: Search only specified documents
        top_k: Number of final results to return (default 10).
        catalog_router_k: Stage-A catalog shortlist size in doc_ids (default 20).
        vector_k: Number of vector search results before fusion (default 15).
        fts_k: Number of FTS results before fusion (default 15).
        rrf_k: RRF constant k (default 60).
        max_chunks_per_doc: Maximum chunks from same document (default 3).
        expand_video_temporal: Whether to expand video chunks with temporal
                               evidence bundles (default True).

    Returns:
        List of result dicts with keys:
            - chunk_id: Unique chunk identifier
            - doc_id: Parent document ID
            - text: Chunk text content
            - score: RRF fusion score (higher = better)
            - vector_rank: Rank from vector search (None if not found)
            - fts_rank: Rank from FTS search (None if not found)
            - modality: Content modality
            - heading_path: Section hierarchy (list[str])
            - doc_name: Document name
            - file_type: Document type
            - locator: Position info (line numbers or timecodes)
            - converted_path: Path to converted document
            - temporal_bundle: For video chunks (video_transcript, video_frame),
                               expand temporal window with chronologically sorted
                               evidence across modalities

    Raises:
        RuntimeError: If query embedding fails.
        ValueError: If embedding client cannot be initialized.
    """
    started_at = time.perf_counter()
    trace: dict[str, Any] = {
        "question": question,
        "params": {
            "top_k": top_k,
            "catalog_router_k": catalog_router_k,
            "vector_k": vector_k,
            "fts_k": fts_k,
            "rrf_k": rrf_k,
            "max_chunks_per_doc": max_chunks_per_doc,
            "expand_video_temporal": expand_video_temporal,
        },
        "filters": {
            "input_doc_ids_filter_count": len(doc_ids_filter) if doc_ids_filter is not None else None
        },
        "counts": {},
        "timings_ms": {},
    }

    # Handle invalid/empty inputs early
    if top_k <= 0:
        trace["early_exit"] = "top_k<=0"
        trace["timings_ms"]["total"] = round((time.perf_counter() - started_at) * 1000, 2)
        if debug_info is not None:
            debug_info.update(trace)
        return []
    if not question or not question.strip():
        trace["early_exit"] = "empty_question"
        trace["timings_ms"]["total"] = round((time.perf_counter() - started_at) * 1000, 2)
        if debug_info is not None:
            debug_info.update(trace)
        return []

    # Handle empty filter case
    if doc_ids_filter is not None and len(doc_ids_filter) == 0:
        trace["early_exit"] = "empty_doc_filter"
        trace["timings_ms"]["total"] = round((time.perf_counter() - started_at) * 1000, 2)
        if debug_info is not None:
            debug_info.update(trace)
        return []

    # Stage A — Catalog router (best-effort):
    # use catalog metadata/summaries to shortlist candidate docs.
    # If it yields no candidates, keep the original filter to preserve recall.
    effective_doc_ids_filter = doc_ids_filter
    router_started = time.perf_counter()
    routed_doc_ids = _route_doc_ids_from_catalog(
        question=question,
        base_dir=base_dir,
        shortlist_k=catalog_router_k,
        scope_doc_ids=doc_ids_filter,
    )
    trace["timings_ms"]["router"] = round((time.perf_counter() - router_started) * 1000, 2)
    trace["counts"]["routed_doc_ids"] = len(routed_doc_ids) if routed_doc_ids is not None else None
    if routed_doc_ids:
        effective_doc_ids_filter = routed_doc_ids
    trace["filters"]["effective_doc_ids_filter_count"] = (
        len(effective_doc_ids_filter) if effective_doc_ids_filter is not None else None
    )

    vector_results: list[dict[str, Any]] = []
    fts_results: list[dict[str, Any]] = []

    with ExitStack() as stack:
        fts = stack.enter_context(FTSIndex(base_dir))
        vs = stack.enter_context(VectorStore(base_dir)) if vector_k > 0 else None

        # Run vector search only when requested
        if vector_k > 0 and vs is not None:
            vector_started = time.perf_counter()
            client, model = get_embedding_client(settings)
            trace["embedding_model"] = model
            query_vec = embed_query(question, client, model)
            vector_results = vs.knn_search(
                query_vec,
                k=vector_k,
                doc_ids_filter=effective_doc_ids_filter,
            )
            trace["timings_ms"]["vector"] = round((time.perf_counter() - vector_started) * 1000, 2)
        else:
            trace["timings_ms"]["vector"] = 0.0

        # Run FTS search only when requested
        if fts_k > 0:
            fts_started = time.perf_counter()
            fts_results = fts.search(
                question,
                k=fts_k,
                doc_ids_filter=effective_doc_ids_filter,
            )
            trace["timings_ms"]["fts"] = round((time.perf_counter() - fts_started) * 1000, 2)
        else:
            trace["timings_ms"]["fts"] = 0.0

        fusion_started = time.perf_counter()
        # Build rank maps (1-indexed positions)
        vector_ranks = {r["chunk_id"]: i + 1 for i, r in enumerate(vector_results)}
        fts_ranks = {r["chunk_id"]: i + 1 for i, r in enumerate(fts_results)}

        # Collect all unique chunk_ids from both searches
        all_chunk_ids = set(vector_ranks.keys()) | set(fts_ranks.keys())

        # Calculate RRF scores and collect results
        scored_chunks: list[tuple[str, float, Optional[int], Optional[int]]] = []
        for chunk_id in all_chunk_ids:
            v_rank = vector_ranks.get(chunk_id)
            f_rank = fts_ranks.get(chunk_id)
            rrf = _rrf_score([v_rank, f_rank], k=rrf_k)
            scored_chunks.append((chunk_id, rrf, v_rank, f_rank))

        # Sort by RRF score (descending) with deterministic tie-breaking.
        # Tie-break by best available rank, then chunk_id for stable output.
        scored_chunks.sort(
            key=lambda x: (
                -x[1],
                min((r for r in (x[2], x[3]) if r is not None), default=10**9),
                x[0],
            )
        )

        # Apply diversity filter (max chunks per doc) and build final results
        doc_counts: dict[str, int] = {}
        results: list[dict[str, Any]] = []
        skipped_diversity = 0

        for chunk_id, rrf, v_rank, f_rank in scored_chunks:
            # Get doc_id to apply diversity filter
            doc_id = _get_doc_id(chunk_id, vector_results, fts_results)
            if not doc_id:
                # Defensive fallback: avoid collapsing unrelated chunks into same bucket.
                doc_id = f"__unknown__:{chunk_id}"

            # Check if we've hit the limit for this document
            if doc_counts.get(doc_id, 0) < max_chunks_per_doc:
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

                # Build result with merged metadata
                result = _merge_chunk_data(
                    chunk_id, rrf, v_rank, f_rank, vector_results, fts_results
                )
                results.append(result)
            else:
                skipped_diversity += 1

            # Stop when we have enough results
            if len(results) >= top_k:
                break

        trace["timings_ms"]["fusion"] = round((time.perf_counter() - fusion_started) * 1000, 2)
        trace["counts"]["vector_hits"] = len(vector_results)
        trace["counts"]["fts_hits"] = len(fts_results)
        trace["counts"]["unique_candidates"] = len(all_chunk_ids)
        trace["counts"]["results_before_temporal"] = len(results)
        trace["counts"]["skipped_by_doc_diversity"] = skipped_diversity

        # Expand video temporal bundles if requested.
        temporal_started = time.perf_counter()
        if expand_video_temporal and any(
            r.get("modality") in ("video_transcript", "video_frame") for r in results
        ):
            if vs is not None:
                results = expand_video_chunks(results, base_dir, vs, fts)
            else:
                with VectorStore(base_dir) as temp_vs:
                    results = expand_video_chunks(results, base_dir, temp_vs, fts)
        trace["timings_ms"]["temporal"] = round((time.perf_counter() - temporal_started) * 1000, 2)
        trace["counts"]["final_results"] = len(results)
        modality_counts: dict[str, int] = {}
        for result in results:
            modality = result.get("modality") or "unknown"
            modality_counts[modality] = modality_counts.get(modality, 0) + 1
        trace["counts"]["final_modalities"] = modality_counts
        trace["timings_ms"]["total"] = round((time.perf_counter() - started_at) * 1000, 2)
        if debug_info is not None:
            debug_info.update(trace)

        return results
