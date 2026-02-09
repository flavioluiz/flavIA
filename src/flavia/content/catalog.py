"""Content catalog — the central index of all project files."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .scanner import DirectoryNode, FileEntry, FileScanner


CATALOG_VERSION = "1.0"
CATALOG_FILENAME = "content_catalog.json"


class ContentCatalog:
    """
    Central index of all files in a project directory.

    Supports:
    - Full scan (during --init)
    - Incremental update (--update or refresh_catalog tool)
    - Query by name, type, category, tags, or free text in summaries
    - Serialization to/from JSON in .flavia/
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()
        self.version = CATALOG_VERSION
        self.catalog_created_at: str = ""
        self.catalog_updated_at: str = ""
        self.files: dict[str, FileEntry] = {}  # keyed by relative path
        self.directory_tree: Optional[DirectoryNode] = None
        self.settings: dict = {
            "auto_convert": True,
            "auto_summarize": False,
            "ignored_patterns": [],
        }

    # ------------------------------------------------------------------
    # Build / Full Scan
    # ------------------------------------------------------------------

    def build(
        self,
        ignore_patterns: Optional[list[str]] = None,
    ) -> "ContentCatalog":
        """Perform a full scan and build the catalog from scratch."""
        scanner = FileScanner(
            self.base_dir,
            ignore_patterns=ignore_patterns or self.settings.get("ignored_patterns", []),
        )
        file_entries, dir_tree = scanner.scan()

        now = datetime.now(timezone.utc).isoformat()
        self.catalog_created_at = now
        self.catalog_updated_at = now
        self.directory_tree = dir_tree

        self.files.clear()
        for entry in file_entries:
            self.files[entry.path] = entry

        if ignore_patterns:
            self.settings["ignored_patterns"] = ignore_patterns

        return self

    # ------------------------------------------------------------------
    # Incremental Update
    # ------------------------------------------------------------------

    def update(self) -> dict:
        """
        Incremental update: detect new, modified, and missing files.

        Returns:
            Summary dict with keys: new, modified, missing, unchanged counts
            and lists of paths.
        """
        scanner = FileScanner(
            self.base_dir,
            ignore_patterns=self.settings.get("ignored_patterns", []),
        )
        current_entries, dir_tree = scanner.scan()

        # Build set of currently scanned paths
        current_paths = {e.path for e in current_entries}
        existing_paths = set(self.files.keys())

        new_paths: list[str] = []
        modified_paths: list[str] = []
        unchanged_paths: list[str] = []
        missing_paths: list[str] = []

        # Detect new and modified files
        for entry in current_entries:
            if entry.path not in existing_paths:
                # New file
                entry.status = "new"
                self.files[entry.path] = entry
                new_paths.append(entry.path)
            else:
                old_entry = self.files[entry.path]
                # Quick check: modified_at changed?
                if entry.modified_at != old_entry.modified_at:
                    # Confirm with checksum
                    if entry.checksum_sha256 != old_entry.checksum_sha256:
                        # Truly modified
                        entry.status = "modified"
                        # Preserve existing summary/tags/converted_to
                        entry.summary = None  # invalidate — needs re-summarization
                        entry.converted_to = old_entry.converted_to
                        entry.tags = old_entry.tags
                        self.files[entry.path] = entry
                        modified_paths.append(entry.path)
                    else:
                        # Timestamp changed but content didn't (e.g. touch)
                        old_entry.modified_at = entry.modified_at
                        old_entry.indexed_at = entry.indexed_at
                        old_entry.status = "current"
                        unchanged_paths.append(entry.path)
                else:
                    old_entry.status = "current"
                    unchanged_paths.append(entry.path)

        # Detect missing files
        for path in existing_paths - current_paths:
            self.files[path].status = "missing"
            missing_paths.append(path)

        # Update tree and timestamp
        self.directory_tree = dir_tree
        self.catalog_updated_at = datetime.now(timezone.utc).isoformat()

        return {
            "new": new_paths,
            "modified": modified_paths,
            "missing": missing_paths,
            "unchanged": unchanged_paths,
            "counts": {
                "new": len(new_paths),
                "modified": len(modified_paths),
                "missing": len(missing_paths),
                "unchanged": len(unchanged_paths),
            },
        }

    def remove_missing(self) -> list[str]:
        """Remove entries with status 'missing' from the catalog."""
        to_remove = [p for p, e in self.files.items() if e.status == "missing"]
        for p in to_remove:
            del self.files[p]
        return to_remove

    def mark_all_current(self) -> None:
        """Reset all file statuses to 'current' after processing."""
        for entry in self.files.values():
            if entry.status in ("new", "modified"):
                entry.status = "current"

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        name: Optional[str] = None,
        extension: Optional[str] = None,
        file_type: Optional[str] = None,
        category: Optional[str] = None,
        has_summary: Optional[bool] = None,
        has_conversion: Optional[bool] = None,
        status: Optional[str] = None,
        text_search: Optional[str] = None,
        limit: int = 50,
    ) -> list[FileEntry]:
        """
        Query the catalog with multiple filters.

        Args:
            name: Substring match on filename
            extension: Exact extension match (e.g. ".pdf")
            file_type: "text", "binary_document", "image", etc.
            category: "python", "pdf", "markdown", etc.
            has_summary: Filter by whether summary exists
            has_conversion: Filter by whether converted_to exists
            status: "current", "new", "modified", "missing"
            text_search: Substring search in path + summary + tags
            limit: Max results to return

        Returns:
            List of matching FileEntry objects
        """
        results: list[FileEntry] = []

        for entry in self.files.values():
            if name and name.lower() not in entry.name.lower():
                continue
            if extension and entry.extension != extension.lower():
                continue
            if file_type and entry.file_type != file_type:
                continue
            if category and entry.category != category:
                continue
            if has_summary is not None:
                if has_summary and not entry.summary:
                    continue
                if not has_summary and entry.summary:
                    continue
            if has_conversion is not None:
                if has_conversion and not entry.converted_to:
                    continue
                if not has_conversion and entry.converted_to:
                    continue
            if status and entry.status != status:
                continue
            if text_search:
                search_lower = text_search.lower()
                searchable = entry.path.lower()
                if entry.summary:
                    searchable += " " + entry.summary.lower()
                if entry.tags:
                    searchable += " " + " ".join(entry.tags).lower()
                if search_lower not in searchable:
                    continue

            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_files_needing_conversion(self) -> list[FileEntry]:
        """Get binary document files that have no converted version."""
        return [
            e
            for e in self.files.values()
            if e.file_type == "binary_document" and not e.converted_to and e.status != "missing"
        ]

    def get_files_needing_summary(self) -> list[FileEntry]:
        """Get text files (including converted) that have no summary."""
        return [
            e
            for e in self.files.values()
            if not e.summary and e.status != "missing" and (e.file_type == "text" or e.converted_to)
        ]

    def get_modified_files(self) -> list[FileEntry]:
        """Get files that were modified since last indexing."""
        return [e for e in self.files.values() if e.status in ("new", "modified")]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get catalog statistics."""
        active_files = [e for e in self.files.values() if e.status != "missing"]
        type_counts = Counter(e.file_type for e in active_files)
        ext_counts = Counter(e.extension for e in active_files)
        status_counts = Counter(e.status for e in self.files.values())
        total_size = sum(e.size_bytes for e in active_files)
        with_summary = sum(1 for e in active_files if e.summary)
        with_conversion = sum(1 for e in active_files if e.converted_to)

        return {
            "total_files": len(active_files),
            "total_size_bytes": total_size,
            "by_type": dict(type_counts),
            "by_extension": dict(ext_counts),
            "by_status": dict(status_counts),
            "with_summary": with_summary,
            "with_conversion": with_conversion,
        }

    # ------------------------------------------------------------------
    # Context Generation (for LLM system prompt)
    # ------------------------------------------------------------------

    def generate_context_summary(self, max_length: int = 2000) -> str:
        """
        Generate a compact text summary of the catalog for injection
        into the LLM system prompt.

        Args:
            max_length: Maximum character length of the summary.

        Returns:
            A text summary of the project content.
        """
        stats = self.get_stats()
        lines = [
            f"Project content catalog ({stats['total_files']} files, "
            f"{stats['total_size_bytes'] / 1024 / 1024:.1f} MB):",
        ]

        # File type breakdown
        if stats["by_type"]:
            type_parts = [
                f"{v} {k}" for k, v in sorted(stats["by_type"].items(), key=lambda x: -x[1])
            ]
            lines.append(f"  Types: {', '.join(type_parts)}")

        # Directory tree with summaries
        if self.directory_tree:
            lines.append("\nDirectory structure:")
            self._render_tree(self.directory_tree, lines, indent=1, max_depth=3)

        # Files with summaries (most useful for context)
        summarized = [e for e in self.files.values() if e.summary and e.status != "missing"]
        if summarized:
            lines.append("\nFile summaries:")
            for entry in sorted(summarized, key=lambda e: e.path)[:20]:
                lines.append(f"  - {entry.path}: {entry.summary}")

        result = "\n".join(lines)
        if len(result) > max_length:
            result = result[: max_length - 3] + "..."
        return result

    def _render_tree(
        self,
        node: DirectoryNode,
        lines: list[str],
        indent: int = 0,
        max_depth: int = 3,
    ) -> None:
        """Render directory tree as indented text."""
        if indent > max_depth:
            return

        prefix = "  " * indent
        summary_part = f" — {node.summary}" if node.summary else ""
        lines.append(f"{prefix}{node.name}/ ({node.file_count} files){summary_part}")

        for child in node.children:
            self._render_tree(child, lines, indent + 1, max_depth)

    # ------------------------------------------------------------------
    # Persistence (JSON)
    # ------------------------------------------------------------------

    def save(self, config_dir: Optional[Path] = None) -> Path:
        """
        Save catalog to .flavia/content_catalog.json.

        Args:
            config_dir: Directory to save into (default: base_dir/.flavia/)

        Returns:
            Path to the saved file.
        """
        if config_dir is None:
            config_dir = self.base_dir / ".flavia"

        config_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = config_dir / CATALOG_FILENAME

        data = {
            "version": self.version,
            "catalog_created_at": self.catalog_created_at,
            "catalog_updated_at": self.catalog_updated_at,
            "base_dir": str(self.base_dir),
            "settings": self.settings,
            "stats": self.get_stats(),
            "directory_tree": self.directory_tree.to_dict() if self.directory_tree else None,
            "files": [
                entry.to_dict() for entry in sorted(self.files.values(), key=lambda e: e.path)
            ],
        }

        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return catalog_path

    @classmethod
    def load(cls, config_dir: Path) -> Optional["ContentCatalog"]:
        """
        Load catalog from .flavia/content_catalog.json.

        Args:
            config_dir: The .flavia/ directory to load from.

        Returns:
            ContentCatalog instance, or None if file doesn't exist.
        """
        catalog_path = config_dir / CATALOG_FILENAME
        if not catalog_path.exists():
            return None

        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        base_dir = Path(data.get("base_dir", config_dir.parent))
        catalog = cls(base_dir)
        catalog.version = data.get("version", CATALOG_VERSION)
        catalog.catalog_created_at = data.get("catalog_created_at", "")
        catalog.catalog_updated_at = data.get("catalog_updated_at", "")
        catalog.settings = data.get("settings", catalog.settings)

        # Load directory tree
        tree_data = data.get("directory_tree")
        if tree_data:
            catalog.directory_tree = DirectoryNode.from_dict(tree_data)

        # Load file entries
        for file_data in data.get("files", []):
            entry = FileEntry.from_dict(file_data)
            catalog.files[entry.path] = entry

        return catalog

    @classmethod
    def load_or_build(
        cls,
        base_dir: Path,
        config_dir: Optional[Path] = None,
        ignore_patterns: Optional[list[str]] = None,
    ) -> "ContentCatalog":
        """
        Load existing catalog or build a new one.

        Args:
            base_dir: Project root directory.
            config_dir: .flavia/ directory (default: base_dir/.flavia/)
            ignore_patterns: File patterns to ignore during scan.

        Returns:
            ContentCatalog instance.
        """
        if config_dir is None:
            config_dir = base_dir / ".flavia"

        catalog = cls.load(config_dir)
        if catalog is not None:
            return catalog

        catalog = cls(base_dir)
        catalog.build(ignore_patterns=ignore_patterns)
        return catalog
