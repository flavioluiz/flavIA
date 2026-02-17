"""Tool for semantic search across document chunks using hybrid retrieval."""

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_read_permission
from flavia.content.indexer.rag_debug_log import append_rag_debug_trace

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


_DOC_MENTION_QUOTED_PATTERN = re.compile(r'(?<![A-Za-z0-9])@(?:"([^"]+)"|\'([^\']+)\')')
_DOC_MENTION_BARE_PATTERN = re.compile(r'(?<![A-Za-z0-9])@([^\s@"\']+)')
_MENTION_TRAILING_PUNCT = ".,;:!?)]}"
_EXHAUSTIVE_QUERY_PATTERNS = (
    "todos os itens",
    "todos os subitens",
    "item por item",
    "subitem por subitem",
    "sem descrições",
    "sem descricoes",
    "sem descrição",
    "sem descricao",
    "lista completa",
    "apenas lista",
    "somente lista",
    "sem detalhes",
    "compare",
    "comparar",
    "comparação",
    "comparacao",
    "versus",
    "expected x",
    "esperado x",
    "enviado x",
    "all items",
    "all subitems",
    "item by item",
    "subitem by subitem",
    "without descriptions",
    "list only",
    "comparison",
)


def _catalog_doc_id(base_dir: Path, path: str, checksum: str) -> str:
    """Derive doc_id from catalog entry fields."""
    raw = f"{base_dir}:{path}:{checksum}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _normalize_ref(value: str) -> str:
    """Normalize a user or catalog reference for robust matching."""
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lower().strip("/")


def _extract_doc_mentions(query: str) -> tuple[str, list[str]]:
    """Extract @file mentions and return (query_without_mentions, mentions)."""
    mentions: list[str] = []
    seen_keys: set[str] = set()

    def _add_mention(raw_token: str) -> None:
        token = raw_token.strip()
        if not token:
            return
        key = _normalize_ref(token)
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        mentions.append(token)

    def _quoted_replacer(match: re.Match[str]) -> str:
        token = match.group(1) or match.group(2) or ""
        _add_mention(token)
        return " "

    stripped = _DOC_MENTION_QUOTED_PATTERN.sub(_quoted_replacer, query)

    def _bare_replacer(match: re.Match[str]) -> str:
        token = (match.group(1) or "").rstrip(_MENTION_TRAILING_PUNCT).strip()
        _add_mention(token)
        return " "

    stripped = _DOC_MENTION_BARE_PATTERN.sub(_bare_replacer, stripped)
    stripped = " ".join(stripped.split())
    return stripped, mentions


def _entry_matches_mention(entry: Any, normalized_mention: str) -> bool:
    """Return True when a mention matches an original or converted reference."""
    if not normalized_mention:
        return False

    path_value = _normalize_ref(getattr(entry, "path", ""))
    name_value = _normalize_ref(getattr(entry, "name", ""))
    converted_value = _normalize_ref(getattr(entry, "converted_to", "") or "")

    candidates: set[str] = {path_value, name_value}
    suffix_candidates: list[str] = [path_value]

    if converted_value:
        candidates.add(converted_value)
        suffix_candidates.append(converted_value)

    frame_descriptions = getattr(entry, "frame_descriptions", []) or []
    for frame_path in frame_descriptions:
        frame_norm = _normalize_ref(str(frame_path))
        if frame_norm:
            candidates.add(frame_norm)
            suffix_candidates.append(frame_norm)

    for raw_candidate in (getattr(entry, "path", ""), getattr(entry, "name", "")):
        stem = Path(str(raw_candidate)).stem
        if stem:
            candidates.add(_normalize_ref(stem))

    if normalized_mention in candidates:
        return True

    for candidate in suffix_candidates:
        if candidate.endswith(f"/{normalized_mention}"):
            return True
    return False


def _resolve_doc_ids_from_mentions(
    mentions: list[str],
    *,
    catalog,
    base_dir: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Resolve @mentions to indexed doc_ids.

    Returns:
        resolved_doc_ids, unresolved_mentions, unindexed_mentions
    """
    resolved_doc_ids: list[str] = []
    seen_doc_ids: set[str] = set()
    unresolved: list[str] = []
    unindexed: list[str] = []

    entries = list(catalog.files.values())

    for mention in mentions:
        normalized = _normalize_ref(mention)
        matched_any = False
        matched_indexed = False

        for entry in entries:
            if entry.status == "missing":
                continue
            if not _entry_matches_mention(entry, normalized):
                continue

            matched_any = True
            if not getattr(entry, "converted_to", None):
                continue

            matched_indexed = True
            doc_id = _catalog_doc_id(base_dir, entry.path, entry.checksum_sha256)
            if doc_id not in seen_doc_ids:
                seen_doc_ids.add(doc_id)
                resolved_doc_ids.append(doc_id)

        if not matched_any:
            unresolved.append(mention)
        elif not matched_indexed:
            unindexed.append(mention)

    return resolved_doc_ids, unresolved, unindexed


def _looks_exhaustive_query(query: str) -> bool:
    """Heuristic for checklist-style extraction requests."""
    normalized = query.lower()
    return any(pattern in normalized for pattern in _EXHAUSTIVE_QUERY_PATTERNS)


def _dedupe_results_by_chunk(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate retrieval results while preserving the first occurrence order."""
    deduped: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    for item in results:
        chunk_id = str(item.get("chunk_id") or "")
        if not chunk_id:
            deduped.append(item)
            continue
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        deduped.append(item)
    return deduped


def _prioritize_doc_coverage(
    results: list[dict[str, Any]],
    *,
    scoped_doc_ids: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Prioritize at least one result per scoped document before filling remaining slots."""
    if limit <= 0:
        return []
    if not results:
        return []
    if not scoped_doc_ids:
        return _dedupe_results_by_chunk(results)[:limit]

    deduped = _dedupe_results_by_chunk(results)
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for item in deduped:
        doc_id = str(item.get("doc_id") or "")
        by_doc.setdefault(doc_id, []).append(item)

    prioritized: list[dict[str, Any]] = []
    used_chunk_ids: set[str] = set()

    for doc_id in scoped_doc_ids:
        group = by_doc.get(doc_id) or []
        if not group:
            continue
        item = group[0]
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id and chunk_id in used_chunk_ids:
            continue
        prioritized.append(item)
        if chunk_id:
            used_chunk_ids.add(chunk_id)
        if len(prioritized) >= limit:
            return prioritized[:limit]

    for item in deduped:
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id and chunk_id in used_chunk_ids:
            continue
        prioritized.append(item)
        if chunk_id:
            used_chunk_ids.add(chunk_id)
        if len(prioritized) >= limit:
            break
    return prioritized[:limit]


class SearchChunksTool(BaseTool):
    """Perform semantic search across indexed document chunks using hybrid RAG retrieval."""

    name = "search_chunks"
    description = (
        "Search document content using semantic understanding. "
        "Use this when answering questions about what documents say (facts, "
        "explanations, methods). "
        "Returns relevant passages with citations including document name and location. "
        "Hybrid search combines vector embeddings with full-text search for best results."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description=(
                        "Semantic search query describing what you're looking for. "
                        "Supports explicit file scoping with @mentions, e.g. "
                        "'@report.pdf weak points in methodology'"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="top_k",
                    type="integer",
                    description="Number of chunks to return (default: 10)",
                    required=False,
                ),
                ToolParameter(
                    name="file_type_filter",
                    type="string",
                    description=(
                        "Restrict results to specific file type (e.g., 'pdf', 'video', 'audio')"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="doc_name_filter",
                    type="string",
                    description="Restrict to documents matching this name substring",
                    required=False,
                ),
                ToolParameter(
                    name="debug",
                    type="boolean",
                    description=(
                        "Persist retrieval diagnostics to `.flavia/rag_debug.jsonl` "
                        "for out-of-band inspection (`/rag-debug last`). "
                        "Diagnostics are not injected into model context."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="retrieval_mode",
                    type="string",
                    description=(
                        "Retrieval profile: 'balanced' (default) or 'exhaustive' "
                        "(higher recall and per-document coverage)."
                    ),
                    required=False,
                    enum=["balanced", "exhaustive"],
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.config.settings import get_settings
        from flavia.content.catalog import ContentCatalog
        from flavia.content.indexer import retrieve

        base_dir = agent_context.base_dir
        config_dir = base_dir / ".flavia"
        index_dir = base_dir / ".index"

        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return "Error: query parameter is required and cannot be empty."
        query = query.strip()
        stripped_query, mentions = _extract_doc_mentions(query)
        effective_query = stripped_query or query

        top_k_raw = args.get("top_k", 10)
        if isinstance(top_k_raw, bool):
            return "Error: top_k must be an integer between 1 and 100."
        if isinstance(top_k_raw, int):
            top_k = top_k_raw
        elif isinstance(top_k_raw, str) and top_k_raw.strip().isdigit():
            top_k = int(top_k_raw.strip())
        else:
            return "Error: top_k must be an integer between 1 and 100."
        if top_k <= 0 or top_k > 100:
            return "Error: top_k must be between 1 and 100."

        file_type_filter = args.get("file_type_filter")
        if file_type_filter is not None:
            if not isinstance(file_type_filter, str):
                return "Error: file_type_filter must be a string."
            file_type_filter = file_type_filter.strip().lower() or None

        doc_name_filter = args.get("doc_name_filter")
        if doc_name_filter is not None:
            if not isinstance(doc_name_filter, str):
                return "Error: doc_name_filter must be a string."
            doc_name_filter = doc_name_filter.strip().lower() or None

        debug_raw = args.get("debug")
        if debug_raw is None:
            debug_mode = bool(getattr(agent_context, "rag_debug", False))
        elif isinstance(debug_raw, bool):
            debug_mode = debug_raw
        else:
            return "Error: debug must be true or false."

        retrieval_mode_raw = args.get("retrieval_mode")
        retrieval_mode = "balanced"
        if retrieval_mode_raw is not None:
            if not isinstance(retrieval_mode_raw, str):
                return "Error: retrieval_mode must be 'balanced' or 'exhaustive'."
            normalized_mode = retrieval_mode_raw.strip().lower()
            if normalized_mode not in {"balanced", "exhaustive"}:
                return "Error: retrieval_mode must be 'balanced' or 'exhaustive'."
            retrieval_mode = normalized_mode

        if retrieval_mode == "balanced" and _looks_exhaustive_query(query):
            retrieval_mode = "exhaustive"

        allowed_config, config_error = check_read_permission(config_dir, agent_context)
        if not allowed_config:
            return f"Error: {config_error}"

        allowed_index, index_error = check_read_permission(index_dir, agent_context)
        if not allowed_index:
            return f"Error: {index_error}"

        catalog = ContentCatalog.load(config_dir)
        if catalog is None:
            return "Error: No content catalog found. Run 'flavia --init' to build the catalog."

        db_path = index_dir / "index.db"
        if not db_path.exists():
            return (
                "Error: No vector index found. Run '/index build' to create the search index. "
                "This requires converted documents in .converted/ directory."
            )

        doc_ids_filter: Optional[list[str]] = None
        preserve_doc_scope = bool(mentions)

        if file_type_filter or doc_name_filter:
            doc_ids_filter = []
            for entry in catalog.files.values():
                if entry.status == "missing":
                    continue

                matches_filter = True

                if file_type_filter:
                    file_type_candidates = {
                        (entry.file_type or "").lower(),
                        (entry.category or "").lower(),
                        (entry.extension or "").lower().lstrip("."),
                    }
                    if file_type_filter not in file_type_candidates:
                        matches_filter = False

                if doc_name_filter:
                    if doc_name_filter not in entry.name.lower():
                        matches_filter = False

                if matches_filter:
                    doc_id = _catalog_doc_id(base_dir, entry.path, entry.checksum_sha256)
                    doc_ids_filter.append(doc_id)

            if not doc_ids_filter and (file_type_filter or doc_name_filter):
                return "No documents match the specified filters."

            if not doc_ids_filter:
                doc_ids_filter = None

        unresolved_mentions: list[str] = []
        unindexed_mentions: list[str] = []
        if mentions:
            mention_doc_ids, unresolved_mentions, unindexed_mentions = _resolve_doc_ids_from_mentions(
                mentions,
                catalog=catalog,
                base_dir=base_dir,
            )
            if not mention_doc_ids:
                unresolved_parts: list[str] = []
                if unresolved_mentions:
                    unresolved_parts.append(
                        "unknown: " + ", ".join(f"@{item}" for item in unresolved_mentions)
                    )
                if unindexed_mentions:
                    unresolved_parts.append(
                        "not indexed: " + ", ".join(f"@{item}" for item in unindexed_mentions)
                    )
                details = "; ".join(unresolved_parts) if unresolved_parts else "no matching indexed files"
                return (
                    "No indexed documents match the @file references "
                    f"({details}). Ensure files are cataloged, converted, and indexed."
                )

            if doc_ids_filter is None:
                doc_ids_filter = mention_doc_ids
            else:
                scoped = set(mention_doc_ids)
                doc_ids_filter = [doc_id for doc_id in doc_ids_filter if doc_id in scoped]
                if not doc_ids_filter:
                    return (
                        "No documents remain after combining @file references with "
                        "the provided filters."
                    )

        settings = get_settings()
        effective_top_k = top_k
        effective_router_k = settings.rag_catalog_router_k
        effective_vector_k = settings.rag_vector_k
        effective_fts_k = settings.rag_fts_k
        effective_max_chunks_per_doc = settings.rag_max_chunks_per_doc

        if retrieval_mode == "exhaustive":
            effective_top_k = max(effective_top_k, 30)
            effective_router_k = max(effective_router_k, 50)
            effective_vector_k = max(effective_vector_k, min(120, effective_top_k * 4))
            effective_fts_k = max(effective_fts_k, min(120, effective_top_k * 4))
            effective_max_chunks_per_doc = max(effective_max_chunks_per_doc, effective_top_k)

        trace: dict[str, Any] = {}
        if debug_mode and mentions:
            trace["mention_scope"] = {
                "query_mentions": [f"@{item}" for item in mentions],
                "unresolved_mentions": [f"@{item}" for item in unresolved_mentions],
                "unindexed_mentions": [f"@{item}" for item in unindexed_mentions],
                "effective_query": effective_query,
            }
        try:
            results = retrieve(
                question=effective_query,
                base_dir=base_dir,
                settings=settings,
                doc_ids_filter=doc_ids_filter,
                top_k=effective_top_k,
                catalog_router_k=effective_router_k,
                vector_k=effective_vector_k,
                fts_k=effective_fts_k,
                rrf_k=settings.rag_rrf_k,
                max_chunks_per_doc=effective_max_chunks_per_doc,
                expand_video_temporal=settings.rag_expand_video_temporal,
                retrieval_mode=retrieval_mode,
                preserve_doc_scope=preserve_doc_scope,
                debug_info=trace if debug_mode else None,
            )
        except Exception as e:
            return f"Error during retrieval: {e}"

        if (
            retrieval_mode == "exhaustive"
            and isinstance(doc_ids_filter, list)
            and len(doc_ids_filter) > 1
        ):
            covered_initial = {
                str(item.get("doc_id") or "")
                for item in results
                if item.get("doc_id")
            }
            missing_doc_ids = [doc_id for doc_id in doc_ids_filter if doc_id not in covered_initial]
            backfilled_docs: list[str] = []
            backfill_attempted = 0
            per_doc_backfill_k = max(
                4,
                min(12, max(1, effective_top_k // max(len(doc_ids_filter), 1))),
            )
            for doc_id in missing_doc_ids[:8]:
                backfill_attempted += 1
                try:
                    supplemental = retrieve(
                        question=effective_query,
                        base_dir=base_dir,
                        settings=settings,
                        doc_ids_filter=[doc_id],
                        top_k=per_doc_backfill_k,
                        catalog_router_k=0,
                        vector_k=max(effective_vector_k, per_doc_backfill_k),
                        fts_k=max(effective_fts_k, per_doc_backfill_k),
                        rrf_k=settings.rag_rrf_k,
                        max_chunks_per_doc=max(effective_max_chunks_per_doc, per_doc_backfill_k),
                        expand_video_temporal=settings.rag_expand_video_temporal,
                        retrieval_mode="exhaustive",
                        preserve_doc_scope=True,
                    )
                except Exception:
                    continue
                if supplemental:
                    backfilled_docs.append(doc_id)
                    results.extend(supplemental)

            results = _prioritize_doc_coverage(
                results,
                scoped_doc_ids=doc_ids_filter,
                limit=effective_top_k,
            )
            if debug_mode:
                trace["coverage_backfill"] = {
                    "scoped_docs": len(doc_ids_filter),
                    "covered_docs_initial": len(covered_initial),
                    "missing_docs_initial": len(missing_doc_ids),
                    "backfill_attempted": backfill_attempted,
                    "backfilled_docs": len(backfilled_docs),
                    "final_covered_docs": len(
                        {
                            str(item.get("doc_id") or "")
                            for item in results
                            if item.get("doc_id")
                        }
                    ),
                }

        if debug_mode:
            append_rag_debug_trace(
                base_dir,
                {
                    "turn_id": getattr(agent_context, "rag_turn_id", None),
                    "query_raw": query,
                    "query_effective": effective_query,
                    "top_k": top_k,
                    "file_type_filter": file_type_filter,
                    "doc_name_filter": doc_name_filter,
                    "retrieval_mode": retrieval_mode,
                    "effective_top_k": effective_top_k,
                    "effective_router_k": effective_router_k,
                    "effective_vector_k": effective_vector_k,
                    "effective_fts_k": effective_fts_k,
                    "effective_max_chunks_per_doc": effective_max_chunks_per_doc,
                    "mentions": [f"@{item}" for item in mentions],
                    "unresolved_mentions": [f"@{item}" for item in unresolved_mentions],
                    "unindexed_mentions": [f"@{item}" for item in unindexed_mentions],
                    "doc_ids_filter_count": len(doc_ids_filter) if doc_ids_filter is not None else None,
                    "preserve_doc_scope": preserve_doc_scope,
                    "trace": trace,
                },
            )

        if not results:
            return f"No results found for query: '{effective_query}'"

        formatted_results = self._format_results(results)
        if mentions and (unresolved_mentions or unindexed_mentions):
            notes: list[str] = []
            if unresolved_mentions:
                notes.append("unknown: " + ", ".join(f"@{item}" for item in unresolved_mentions))
            if unindexed_mentions:
                notes.append("not indexed: " + ", ".join(f"@{item}" for item in unindexed_mentions))
            formatted_results = f"Note: some @file references were ignored ({'; '.join(notes)}).\n\n{formatted_results}"
        return formatted_results

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """Format retrieval results as annotated context blocks with citations."""
        parts = []

        for idx, result in enumerate(results, 1):
            doc_name = result.get("doc_name", "unknown")
            modality = result.get("modality", "text")
            locator = result.get("locator", {})
            heading_path = result.get("heading_path", [])

            citation_parts = []

            citation_parts.append(doc_name)

            if modality in ("video_transcript", "video_frame"):
                citation_parts.append("video transcript" if modality == "video_transcript" else "video frame")
            elif heading_path:
                hierarchy = " > ".join(heading_path)
                citation_parts.append(hierarchy)

            line_start = locator.get("line_start")
            line_end = locator.get("line_end")
            line_annotation = ""
            if line_start is not None or line_end is not None:
                if line_start is not None and line_end is not None:
                    line_annotation = f"lines {line_start}–{line_end}"
                elif line_start is not None:
                    line_annotation = f"line {line_start}"
                else:
                    line_annotation = f"line {line_end}"

            citation = " — ".join(citation_parts)
            if line_annotation:
                citation = f"{citation} ({line_annotation})"
            parts.append(f"[{idx}] {citation}")

            temporal_bundle = result.get("temporal_bundle")

            if temporal_bundle:
                for item in temporal_bundle:
                    time_display = item.get("time_display", "")
                    modality_label = item.get("modality_label", "")
                    text = item.get("text", "").strip()
                    context_label = " ".join(
                        part for part in (time_display, modality_label) if part
                    ).strip()
                    if context_label:
                        parts.append(f'    {context_label}: "{text}"')
                    else:
                        parts.append(f'    "{text}"')
            else:
                text = result.get("text", "").strip()
                parts.append(f'    "{text}"')

            parts.append("")

        return "\n".join(parts)

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Available whenever the vector index exists."""
        index_dir = agent_context.base_dir / ".index"
        return (index_dir / "index.db").exists()
