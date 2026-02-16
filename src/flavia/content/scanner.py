"""File scanner for content cataloging."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# File type classification
TEXT_EXTENSIONS = {
    # Programming languages
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".r",
    ".R",
    ".m",
    ".jl",
    ".lua",
    ".pl",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    # Markup and data
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".text",
    ".log",
    ".html",
    ".htm",
    ".xml",
    ".xhtml",
    ".svg",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".csv",
    ".tsv",
    # LaTeX and academic
    ".tex",
    ".bib",
    ".sty",
    ".cls",
    # Other text
    ".env",
    ".gitignore",
    ".dockerignore",
    ".sql",
    ".graphql",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
}

BINARY_DOCUMENT_EXTENSIONS = {
    ".pdf": "pdf",
    ".doc": "word",
    ".docx": "word",
    ".ppt": "presentation",
    ".pptx": "presentation",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".odt": "document",
    ".ods": "spreadsheet",
    ".odp": "presentation",
    ".epub": "ebook",
}

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".ico",
    ".svg",
}

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".wma",
    ".m4a",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
}

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
}

# Directories to always ignore
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".flavia",
    ".converted",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    ".tox",
    ".nox",
    "dist",
    "build",
    "egg-info",
    ".idea",
    ".vscode",
    ".DS_Store",
}

# Files to always ignore
DEFAULT_IGNORE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}


@dataclass
class FileEntry:
    """Metadata for a single file."""

    path: str  # Relative path from base_dir
    name: str  # Filename
    extension: str  # File extension (lowercase, with dot)
    file_type: str  # "text", "binary_document", "image", "audio", "video", "archive", "other"
    category: str  # More specific: "python", "pdf", "markdown", "mp3", etc.
    size_bytes: int
    created_at: str  # ISO 8601
    modified_at: str  # ISO 8601
    indexed_at: str  # ISO 8601 — when this entry was cataloged
    checksum_sha256: str  # SHA-256 hash of file content
    status: str = "current"  # "current", "new", "modified", "missing"
    converted_to: Optional[str] = None  # Path to converted text version
    summary: Optional[str] = None
    extraction_quality: Optional[str] = None  # "good", "partial", "poor", or None
    tags: list[str] = field(default_factory=list)

    # Online source fields
    source_type: str = "local"  # "local", "youtube", "webpage"
    source_url: Optional[str] = None  # URL original for online sources
    source_metadata: dict = field(default_factory=dict)  # title, duration, author, etc.
    fetch_status: str = "completed"  # "pending", "completed", "failed", "not_implemented"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "file_type": self.file_type,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "indexed_at": self.indexed_at,
            "checksum_sha256": self.checksum_sha256,
            "status": self.status,
        }
        if self.converted_to:
            d["converted_to"] = self.converted_to
        if self.summary:
            d["summary"] = self.summary
        if self.extraction_quality:
            d["extraction_quality"] = self.extraction_quality
        if self.tags:
            d["tags"] = self.tags
        # Online source fields (only serialize if not default)
        if self.source_type != "local":
            d["source_type"] = self.source_type
        if self.source_url:
            d["source_url"] = self.source_url
        if self.source_metadata:
            d["source_metadata"] = self.source_metadata
        if self.fetch_status != "completed":
            d["fetch_status"] = self.fetch_status
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FileEntry":
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            name=data["name"],
            extension=data["extension"],
            file_type=data["file_type"],
            category=data["category"],
            size_bytes=data["size_bytes"],
            created_at=data["created_at"],
            modified_at=data["modified_at"],
            indexed_at=data["indexed_at"],
            checksum_sha256=data["checksum_sha256"],
            status=data.get("status", "current"),
            converted_to=data.get("converted_to"),
            summary=data.get("summary"),
            extraction_quality=data.get("extraction_quality"),
            tags=data.get("tags", []),
            # Online source fields (backwards compatible)
            source_type=data.get("source_type", "local"),
            source_url=data.get("source_url"),
            source_metadata=data.get("source_metadata", {}),
            fetch_status=data.get("fetch_status", "completed"),
        )


@dataclass
class DirectoryNode:
    """A node in the directory tree."""

    path: str  # Relative path from base_dir
    name: str
    summary: Optional[str] = None
    file_count: int = 0
    children: list["DirectoryNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = {
            "path": self.path,
            "name": self.name,
            "file_count": self.file_count,
        }
        if self.summary:
            d["summary"] = self.summary
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DirectoryNode":
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            name=data["name"],
            summary=data.get("summary"),
            file_count=data.get("file_count", 0),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


class FileScanner:
    """Scans a directory tree and collects file metadata."""

    def __init__(
        self,
        base_dir: Path,
        ignore_dirs: Optional[set[str]] = None,
        ignore_files: Optional[set[str]] = None,
        ignore_patterns: Optional[list[str]] = None,
    ):
        self.base_dir = base_dir.resolve()
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.ignore_files = ignore_files or DEFAULT_IGNORE_FILES
        self.ignore_patterns = ignore_patterns or []

    def scan(self) -> tuple[list[FileEntry], DirectoryNode]:
        """
        Scan the base directory and return file entries and directory tree.

        Returns:
            Tuple of (list of FileEntry, root DirectoryNode)
        """
        files: list[FileEntry] = []
        root_node = self._build_directory_tree(self.base_dir, files)
        return files, root_node

    def scan_file(self, file_path: Path) -> Optional[FileEntry]:
        """Scan a single file and return its entry."""
        if not file_path.exists() or not file_path.is_file():
            return None
        return self._create_file_entry(file_path)

    def _build_directory_tree(
        self,
        directory: Path,
        files: list[FileEntry],
    ) -> DirectoryNode:
        """Recursively build directory tree and collect file entries."""
        rel_path = str(directory.relative_to(self.base_dir))
        if rel_path == ".":
            rel_path = "."

        node = DirectoryNode(
            path=rel_path,
            name=directory.name or str(self.base_dir),
        )

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return node

        file_count = 0
        for entry in entries:
            if entry.is_dir():
                if entry.name in self.ignore_dirs:
                    continue
                if self._matches_ignore_pattern(entry.name):
                    continue
                child_node = self._build_directory_tree(entry, files)
                node.children.append(child_node)
                file_count += child_node.file_count
            elif entry.is_file():
                if entry.name in self.ignore_files:
                    continue
                if self._matches_ignore_pattern(entry.name):
                    continue
                file_entry = self._create_file_entry(entry)
                if file_entry:
                    files.append(file_entry)
                    file_count += 1

        node.file_count = file_count
        return node

    def _create_file_entry(self, file_path: Path) -> Optional[FileEntry]:
        """Create a FileEntry for a single file."""
        try:
            stat = file_path.stat()
            rel_path = str(file_path.relative_to(self.base_dir))
            ext = file_path.suffix.lower()
            file_type, category = self._classify_file(ext)
            now = datetime.now(timezone.utc).isoformat()

            # Get timestamps
            created_at = datetime.fromtimestamp(
                stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime,
                tz=timezone.utc,
            ).isoformat()
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            # Compute checksum
            checksum = self._compute_checksum(file_path)

            return FileEntry(
                path=rel_path,
                name=file_path.name,
                extension=ext,
                file_type=file_type,
                category=category,
                size_bytes=stat.st_size,
                created_at=created_at,
                modified_at=modified_at,
                indexed_at=now,
                checksum_sha256=checksum,
                status="current",
            )
        except (PermissionError, OSError):
            return None

    @staticmethod
    def _classify_file(ext: str) -> tuple[str, str]:
        """Classify a file by its extension. Returns (file_type, category)."""
        if ext in TEXT_EXTENSIONS:
            # Determine specific category
            category_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".c": "c",
                ".cpp": "cpp",
                ".h": "c_header",
                ".hpp": "cpp_header",
                ".java": "java",
                ".go": "go",
                ".rs": "rust",
                ".rb": "ruby",
                ".r": "r",
                ".R": "r",
                ".m": "matlab",
                ".jl": "julia",
                ".md": "markdown",
                ".markdown": "markdown",
                ".rst": "restructuredtext",
                ".txt": "text",
                ".text": "text",
                ".log": "log",
                ".tex": "latex",
                ".bib": "bibtex",
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".toml": "toml",
                ".ini": "ini",
                ".cfg": "config",
                ".html": "html",
                ".htm": "html",
                ".xml": "xml",
                ".css": "css",
                ".scss": "scss",
                ".sql": "sql",
                ".sh": "shell",
                ".bash": "shell",
                ".zsh": "shell",
                ".csv": "csv",
                ".tsv": "tsv",
            }
            category = category_map.get(ext, "text")
            return "text", category

        if ext in BINARY_DOCUMENT_EXTENSIONS:
            return "binary_document", BINARY_DOCUMENT_EXTENSIONS[ext]

        if ext in IMAGE_EXTENSIONS:
            return "image", ext.lstrip(".")

        if ext in AUDIO_EXTENSIONS:
            return "audio", ext.lstrip(".")

        if ext in VIDEO_EXTENSIONS:
            return "video", ext.lstrip(".")

        if ext in ARCHIVE_EXTENSIONS:
            return "archive", ext.lstrip(".")

        return "other", ext.lstrip(".") if ext else "unknown"

    @staticmethod
    def _compute_checksum(file_path: Path, chunk_size: int = 8192) -> str:
        """Compute SHA-256 checksum of a file."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (PermissionError, OSError):
            return ""

    def _matches_ignore_pattern(self, name: str) -> bool:
        """Check if a name matches any ignore pattern."""
        import fnmatch

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False
