"""Vector store for semantic retrieval using sqlite-vec.

This module provides the VectorStore class for storing and searching
L2-normalized embedding vectors using sqlite-vec, a SQLite extension
for vector similarity search.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class VectorStore:
    """Store and search embedding vectors using sqlite-vec.

    The store maintains two tables:
    - chunks_vec: sqlite-vec virtual table for vector KNN search
    - chunks_meta: Regular table for chunk metadata (joined on chunk_id)

    Usage:
        with VectorStore(vault_dir) as store:
            store.upsert([(chunk_id, vector, metadata), ...])
            results = store.knn_search(query_vec, k=10)
    """

    def __init__(
        self,
        base_dir: Path,
        db_path: Optional[Path] = None,
    ):
        """Initialize the vector store.

        Args:
            base_dir: Vault base directory. The index will be stored in
                      base_dir/.index/index.db
            db_path: Optional explicit path to the database file.
                     If None, uses base_dir/.index/index.db
        """
        self.base_dir = Path(base_dir)
        if db_path:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.index_dir = self.base_dir / ".index"
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.index_dir / "index.db"

        self._conn: Optional[sqlite3.Connection] = None
        self._sqlite_vec_loaded = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._load_sqlite_vec(self._conn)
            self._ensure_schema()
        return self._conn

    def _load_sqlite_vec(self, conn: sqlite3.Connection) -> None:
        """Load the sqlite-vec extension.

        Strategy 1: Use sqlite_vec.load() helper (preferred)
        Strategy 2: Direct extension loading (fallback)
        """
        if self._sqlite_vec_loaded:
            return

        # Strategy 1: Use sqlite_vec.load() helper
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self._sqlite_vec_loaded = True
            return
        except ImportError:
            pass
        except Exception as e:
            # sqlite_vec module exists but load failed
            raise RuntimeError(
                f"Failed to load sqlite-vec extension: {e}\nInstall with: pip install sqlite-vec"
            ) from e

        # Strategy 2: Extension not found
        raise RuntimeError(
            "sqlite-vec extension not available.\n"
            "Install with: pip install 'flavia[rag]' or pip install sqlite-vec\n"
            "Note: macOS system Python may not support SQLite extensions. "
            "Consider using a Homebrew Python or conda environment."
        )

    def _ensure_schema(self) -> None:
        """Create the database schema if it doesn't exist."""
        conn = self._conn
        if conn is None:
            return

        # Create the vector table using sqlite-vec
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding float[768]
            )
            """
        )

        # Create metadata table for joins
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks_meta (
                chunk_id     TEXT PRIMARY KEY,
                doc_id       TEXT NOT NULL,
                modality     TEXT NOT NULL,
                converted_path TEXT,
                locator_json TEXT,
                heading_json TEXT,
                doc_name     TEXT,
                file_type    TEXT,
                indexed_at   TEXT NOT NULL
            )
            """
        )

        # Create index for doc_id filtering
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_meta_doc_id ON chunks_meta(doc_id)")

        conn.commit()

    def upsert(
        self,
        items: list[tuple[str, list[float], dict]],
    ) -> tuple[int, int]:
        """Insert or update chunks with their vectors and metadata.

        Args:
            items: List of tuples (chunk_id, vector, metadata) where:
                - chunk_id: Unique identifier for the chunk
                - vector: L2-normalized embedding vector (768 dims)
                - metadata: Dict with keys: doc_id, modality, converted_path,
                           locator (dict), heading_path (list), doc_name, file_type

        Returns:
            Tuple of (inserted_count, updated_count).
        """
        conn = self._get_connection()
        inserted = 0
        updated = 0

        for chunk_id, vector, metadata in items:
            # Check if exists
            cursor = conn.execute("SELECT 1 FROM chunks_meta WHERE chunk_id = ?", (chunk_id,))
            exists = cursor.fetchone() is not None

            now = datetime.now(timezone.utc).isoformat()

            # Prepare metadata values
            doc_id = metadata.get("doc_id", "")
            modality = metadata.get("modality", "")
            converted_path = metadata.get("converted_path", "")
            locator = metadata.get("locator", {})
            heading_path = metadata.get("heading_path", [])
            doc_name = metadata.get("doc_name", "")
            file_type = metadata.get("file_type", "")

            locator_json = json.dumps(locator) if locator else ""
            heading_json = json.dumps(heading_path) if heading_path else ""

            if exists:
                # Update vector
                conn.execute(
                    "UPDATE chunks_vec SET embedding = ? WHERE chunk_id = ?",
                    (self._serialize_vector(vector), chunk_id),
                )
                # Update metadata
                conn.execute(
                    """
                    UPDATE chunks_meta SET
                        doc_id = ?,
                        modality = ?,
                        converted_path = ?,
                        locator_json = ?,
                        heading_json = ?,
                        doc_name = ?,
                        file_type = ?,
                        indexed_at = ?
                    WHERE chunk_id = ?
                    """,
                    (
                        doc_id,
                        modality,
                        converted_path,
                        locator_json,
                        heading_json,
                        doc_name,
                        file_type,
                        now,
                        chunk_id,
                    ),
                )
                updated += 1
            else:
                # Insert vector
                conn.execute(
                    "INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                    (chunk_id, self._serialize_vector(vector)),
                )
                # Insert metadata
                conn.execute(
                    """
                    INSERT INTO chunks_meta (
                        chunk_id, doc_id, modality, converted_path,
                        locator_json, heading_json, doc_name, file_type, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        doc_id,
                        modality,
                        converted_path,
                        locator_json,
                        heading_json,
                        doc_name,
                        file_type,
                        now,
                    ),
                )
                inserted += 1

        conn.commit()
        return inserted, updated

    def _serialize_vector(self, vector: list[float]) -> bytes:
        """Serialize a vector to bytes for sqlite-vec storage."""
        import struct

        return struct.pack(f"{len(vector)}f", *vector)

    def _deserialize_vector(self, data: bytes) -> list[float]:
        """Deserialize bytes to a vector."""
        import struct

        count = len(data) // 4  # 4 bytes per float
        return list(struct.unpack(f"{count}f", data))

    def knn_search(
        self,
        query_vec: list[float],
        k: int = 10,
        doc_ids_filter: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Search for the k nearest neighbors to a query vector.

        Args:
            query_vec: Query embedding vector (L2-normalized, 768 dims).
            k: Number of results to return.
            doc_ids_filter: Optional list of doc_ids to restrict search to.
                - None: Search all documents
                - []: Return empty results (explicit empty scope)
                - ["id1", "id2"]: Search only specified documents

        Returns:
            List of dicts with keys: chunk_id, distance, doc_id, modality,
            converted_path, locator, heading_path, doc_name, file_type.
        """
        conn = self._get_connection()
        if k <= 0:
            return []

        # Handle empty filter case (consistent with FTSIndex)
        if doc_ids_filter is not None and len(doc_ids_filter) == 0:
            return []

        # Build the query with optional doc_id filter
        if doc_ids_filter:
            # sqlite-vec applies post-filtering with JOIN predicates. To preserve
            # correctness for doc_id-restricted searches, request full-kNN and then
            # apply SQL filter + LIMIT.
            total_chunks = conn.execute("SELECT COUNT(*) AS cnt FROM chunks_meta").fetchone()["cnt"]
            if total_chunks == 0:
                return []

            placeholders = ",".join("?" * len(doc_ids_filter))
            cursor = conn.execute(
                f"""
                SELECT v.chunk_id, v.distance, m.doc_id, m.modality,
                       m.converted_path, m.locator_json, m.heading_json,
                       m.doc_name, m.file_type
                FROM chunks_vec v
                JOIN chunks_meta m ON v.chunk_id = m.chunk_id
                WHERE v.embedding MATCH ? AND k = ?
                  AND m.doc_id IN ({placeholders})
                ORDER BY v.distance
                LIMIT ?
                """,
                (self._serialize_vector(query_vec), total_chunks, *doc_ids_filter, k),
            )
        else:
            cursor = conn.execute(
                """
                SELECT v.chunk_id, v.distance, m.doc_id, m.modality,
                       m.converted_path, m.locator_json, m.heading_json,
                       m.doc_name, m.file_type
                FROM chunks_vec v
                JOIN chunks_meta m ON v.chunk_id = m.chunk_id
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
                LIMIT ?
                """,
                (self._serialize_vector(query_vec), k, k),
            )

        results = []
        for row in cursor:
            locator = json.loads(row["locator_json"]) if row["locator_json"] else {}
            heading_path = json.loads(row["heading_json"]) if row["heading_json"] else []

            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "distance": row["distance"],
                    "doc_id": row["doc_id"],
                    "modality": row["modality"],
                    "converted_path": row["converted_path"],
                    "locator": locator,
                    "heading_path": heading_path,
                    "doc_name": row["doc_name"],
                    "file_type": row["file_type"],
                }
            )

        return results

    def get_existing_chunk_ids(self) -> set[str]:
        """Get all chunk IDs currently in the store.

        Returns:
            Set of chunk_id strings.
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT chunk_id FROM chunks_meta")
        return {row["chunk_id"] for row in cursor}

    def get_chunk_ids_by_converted_paths(self, converted_paths: list[str]) -> set[str]:
        """Get chunk IDs for one or more converted file paths."""
        if not converted_paths:
            return set()

        conn = self._get_connection()
        placeholders = ",".join("?" * len(converted_paths))
        cursor = conn.execute(
            f"SELECT chunk_id FROM chunks_meta WHERE converted_path IN ({placeholders})",
            tuple(converted_paths),
        )
        return {row["chunk_id"] for row in cursor}

    def delete_chunks(self, chunk_ids: list[str]) -> int:
        """Delete chunks by their IDs.

        Args:
            chunk_ids: List of chunk IDs to delete.

        Returns:
            Number of chunks deleted.
        """
        if not chunk_ids:
            return 0

        conn = self._get_connection()
        deleted = 0

        for chunk_id in chunk_ids:
            cursor = conn.execute("DELETE FROM chunks_meta WHERE chunk_id = ?", (chunk_id,))
            if cursor.rowcount > 0:
                conn.execute("DELETE FROM chunks_vec WHERE chunk_id = ?", (chunk_id,))
                deleted += 1

        conn.commit()
        return deleted

    def get_chunks_by_doc_id(
        self,
        doc_id: str,
        modalities: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Get all chunks for a specific doc_id, optionally filtered by modality.

        Args:
            doc_id: Document ID to retrieve chunks for.
            modalities: Optional list of modalities to filter by (e.g., ["video_transcript", "video_frame"]).
                      If None, returns all modalities.

        Returns:
            List of chunk dicts with keys: chunk_id, doc_id, modality, converted_path,
            locator, heading_path, doc_name, file_type, text. Results are sorted by
            time_start in locator if temporal locator is present.
        """
        conn = self._get_connection()

        if modalities:
            placeholders = ",".join("?" * len(modalities))
            cursor = conn.execute(
                f"""
                SELECT v.chunk_id, m.doc_id, m.modality, m.converted_path,
                       m.locator_json, m.heading_json, m.doc_name, m.file_type,
                       f.text
                FROM chunks_vec v
                JOIN chunks_meta m ON v.chunk_id = m.chunk_id
                JOIN chunks_fts f ON v.chunk_id = f.chunk_id
                WHERE m.doc_id = ? AND m.modality IN ({placeholders})
                ORDER BY m.chunk_id
                """,
                (doc_id, *modalities),
            )
        else:
            cursor = conn.execute(
                """
                SELECT v.chunk_id, m.doc_id, m.modality, m.converted_path,
                       m.locator_json, m.heading_json, m.doc_name, m.file_type,
                       f.text
                FROM chunks_vec v
                JOIN chunks_meta m ON v.chunk_id = m.chunk_id
                JOIN chunks_fts f ON v.chunk_id = f.chunk_id
                WHERE m.doc_id = ?
                ORDER BY m.chunk_id
                """,
                (doc_id,),
            )

        chunks = []
        for row in cursor:
            locator = json.loads(row["locator_json"]) if row["locator_json"] else {}
            heading_path = json.loads(row["heading_json"]) if row["heading_json"] else []

            chunks.append(
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "modality": row["modality"],
                    "converted_path": row["converted_path"],
                    "locator": locator,
                    "heading_path": heading_path,
                    "doc_name": row["doc_name"],
                    "file_type": row["file_type"],
                    "text": row["text"],
                }
            )

        def _get_time_start(locator: dict) -> float:
            """Extract time_start in seconds if available."""
            time_str = locator.get("time_start", "")
            if not time_str:
                return float("inf")
            try:
                parts = time_str.split(":")
                parts = [float(p) for p in parts]
                if len(parts) == 3:
                    return parts[0] * 3600 + parts[1] * 60 + parts[2]
                if len(parts) == 2:
                    return parts[0] * 60 + parts[1]
                return parts[0]
            except (ValueError, IndexError):
                return float("inf")

        chunks.sort(key=lambda c: _get_time_start(c.get("locator", {})))

        return chunks

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the vector store.

        Returns:
            Dict with keys: chunk_count, doc_count, modalities, db_size_bytes,
            last_indexed_at.
        """
        conn = self._get_connection()

        # Chunk count
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM chunks_meta")
        chunk_count = cursor.fetchone()["cnt"]

        # Doc count
        cursor = conn.execute("SELECT COUNT(DISTINCT doc_id) as cnt FROM chunks_meta")
        doc_count = cursor.fetchone()["cnt"]

        # Modalities
        cursor = conn.execute("SELECT DISTINCT modality FROM chunks_meta")
        modalities = [row["modality"] for row in cursor]

        # DB file size
        db_size = 0
        if self.db_path.exists():
            db_size = self.db_path.stat().st_size

        # Last indexed timestamp
        cursor = conn.execute("SELECT MAX(indexed_at) as last_indexed FROM chunks_meta")
        row = cursor.fetchone()
        last_indexed = row["last_indexed"] if row else None

        return {
            "chunk_count": chunk_count,
            "doc_count": doc_count,
            "modalities": modalities,
            "db_size_bytes": db_size,
            "last_indexed_at": last_indexed,
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "VectorStore":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
