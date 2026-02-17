"""Hybrid retrieval combining vector and FTS search with RRF fusion.

This module implements Reciprocal Rank Fusion (RRF) to combine results from
semantic (vector) search and full-text search into a unified ranking.
"""

from pathlib import Path
from typing import Any, Optional

from flavia.config import Settings

from .embedder import embed_query, get_embedding_client
from .fts import FTSIndex
from .vector_store import VectorStore


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
        result.update({
            "doc_id": v_data["doc_id"],
            "modality": v_data["modality"],
            "heading_path": v_data["heading_path"],
            "doc_name": v_data["doc_name"],
            "file_type": v_data["file_type"],
            "locator": v_data["locator"],
            "converted_path": v_data["converted_path"],
        })

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
    vector_k: int = 15,
    fts_k: int = 15,
    rrf_k: int = 60,
    max_chunks_per_doc: int = 3,
) -> list[dict[str, Any]]:
    """Hybrid retrieval combining vector and FTS search with RRF fusion.

    Performs semantic (vector) and full-text (FTS) searches, then
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
        vector_k: Number of vector search results before fusion (default 15).
        fts_k: Number of FTS results before fusion (default 15).
        rrf_k: RRF constant k (default 60).
        max_chunks_per_doc: Maximum chunks from same document (default 3).

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

    Raises:
        RuntimeError: If query embedding fails.
        ValueError: If embedding client cannot be initialized.
    """
    # Handle invalid/empty inputs early
    if top_k <= 0:
        return []
    if not question or not question.strip():
        return []

    # Handle empty filter case
    if doc_ids_filter is not None and len(doc_ids_filter) == 0:
        return []

    vector_results: list[dict[str, Any]] = []
    fts_results: list[dict[str, Any]] = []

    # Run vector search only when requested
    if vector_k > 0:
        client, model = get_embedding_client(settings)
        query_vec = embed_query(question, client, model)
        with VectorStore(base_dir) as vs:
            vector_results = vs.knn_search(query_vec, k=vector_k, doc_ids_filter=doc_ids_filter)

    # Run FTS search only when requested
    if fts_k > 0:
        with FTSIndex(base_dir) as fts:
            fts_results = fts.search(question, k=fts_k, doc_ids_filter=doc_ids_filter)

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
            result = _merge_chunk_data(chunk_id, rrf, v_rank, f_rank, vector_results, fts_results)
            results.append(result)

        # Stop when we have enough results
        if len(results) >= top_k:
            break

    return results
