"""Tool for semantic search across document chunks using hybrid retrieval."""

import hashlib
from typing import TYPE_CHECKING, Any, Optional

from ..base import BaseTool, ToolParameter, ToolSchema
from ..permissions import check_read_permission

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


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
                    description="Semantic search query describing what you're looking for",
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
                    raw = f"{base_dir}:{entry.path}:{entry.checksum_sha256}"
                    doc_id = hashlib.sha1(raw.encode()).hexdigest()
                    doc_ids_filter.append(doc_id)

            if not doc_ids_filter and (file_type_filter or doc_name_filter):
                return "No documents match the specified filters."

            if not doc_ids_filter:
                doc_ids_filter = None

        settings = get_settings()

        try:
            results = retrieve(
                question=query,
                base_dir=base_dir,
                settings=settings,
                doc_ids_filter=doc_ids_filter,
                top_k=top_k,
            )
        except Exception as e:
            return f"Error during retrieval: {e}"

        if not results:
            return f"No results found for query: '{query}'"

        formatted_results = self._format_results(results)
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
