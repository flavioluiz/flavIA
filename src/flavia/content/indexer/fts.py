"""Full-text search index using SQLite FTS5.

This module provides the FTSIndex class for exact-term full-text search
using SQLite FTS5 with BM25 ranking. Shares the same index.db as VectorStore.
"""

import sqlite3
from pathlib import Path
from typing import Any, Optional


class FTSIndex:
    """Store and search text chunks using SQLite FTS5.

    The index maintains a single FTS5 virtual table:
    - chunks_fts: FTS5 virtual table with BM25 ranking

    Designed for exact-term matching of codes, IDs, and acronyms (e.g.
    RFC-2616, ATP-123) while also supporting Porter stemming for natural
    language queries.

    Usage:
        with FTSIndex(vault_dir) as index:
            index.upsert(chunks)
            results = index.search("RFC-2616", k=10)
    """

    def __init__(
        self,
        base_dir: Path,
        db_path: Optional[Path] = None,
    ):
        """Initialize the FTS index.

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

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
        return self._conn

    def _ensure_schema(self) -> None:
        """Create the FTS5 virtual table if it doesn't exist."""
        conn = self._conn
        if conn is None:
            return

        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                doc_id   UNINDEXED,
                modality UNINDEXED,
                text,
                heading_path,
                tokenize = 'porter unicode61'
            )
            """
        )

        conn.commit()

    def upsert(self, chunks: list[dict]) -> tuple[int, int]:
        """Insert or update chunks in the FTS index.

        FTS5 does not support UPDATE, so existing chunks are deleted then
        re-inserted.

        Args:
            chunks: List of chunk dicts with keys: chunk_id, doc_id, modality,
                    text, heading_path (list[str]).

        Returns:
            Tuple of (inserted_count, updated_count).
        """
        conn = self._get_connection()
        inserted = 0
        updated = 0

        existing_ids = self.get_existing_chunk_ids()

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "")
            doc_id = chunk.get("doc_id", "")
            modality = chunk.get("modality", "")
            text = chunk.get("text", "")
            heading_path = chunk.get("heading_path", [])

            # Convert heading_path list to " > "-delimited string for FTS
            heading_str = " > ".join(heading_path) if heading_path else ""

            if chunk_id in existing_ids:
                # FTS5 doesn't support UPDATE: delete then insert
                conn.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,)
                )
                conn.execute(
                    "INSERT INTO chunks_fts (chunk_id, doc_id, modality, text, heading_path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, doc_id, modality, text, heading_str),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO chunks_fts (chunk_id, doc_id, modality, text, heading_path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, doc_id, modality, text, heading_str),
                )
                inserted += 1
                existing_ids.add(chunk_id)

        conn.commit()
        return inserted, updated

    def search(
        self,
        query: str,
        k: int = 10,
        doc_ids_filter: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Search for chunks matching the query using FTS5 BM25 ranking.

        Wraps the query in double quotes for exact-term matching. This ensures
        codes, IDs, and acronyms like RFC-2616 or ATP-123 are matched exactly.

        Args:
            query: Search query string.
            k: Maximum number of results to return.
            doc_ids_filter: Optional list of doc_ids to restrict search to.

        Returns:
            List of dicts with keys: chunk_id, doc_id, modality, text,
            heading_path (list[str]), bm25_score (float, negative, lower = better).
        """
        if not query or not query.strip():
            return []
        if k <= 0:
            return []
        if doc_ids_filter is not None and len(doc_ids_filter) == 0:
            return []

        conn = self._get_connection()

        # Wrap in double quotes for exact-term matching, escaping any
        # internal double quotes by doubling them (FTS5 quoting convention)
        escaped = query.replace('"', '""')
        fts_query = f'"{escaped}"'

        if doc_ids_filter:
            placeholders = ",".join("?" * len(doc_ids_filter))
            cursor = conn.execute(
                f"""
                SELECT chunk_id, doc_id, modality, text, heading_path,
                       bm25(chunks_fts) AS bm25_score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                  AND doc_id IN ({placeholders})
                ORDER BY bm25_score
                LIMIT ?
                """,
                (fts_query, *doc_ids_filter, k),
            )
        else:
            cursor = conn.execute(
                """
                SELECT chunk_id, doc_id, modality, text, heading_path,
                       bm25(chunks_fts) AS bm25_score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY bm25_score
                LIMIT ?
                """,
                (fts_query, k),
            )

        results = []
        for row in cursor:
            heading_str = row["heading_path"] or ""
            heading_path = [h for h in heading_str.split(" > ") if h] if heading_str else []

            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "modality": row["modality"],
                    "text": row["text"],
                    "heading_path": heading_path,
                    "bm25_score": row["bm25_score"],
                }
            )

        return results

    def get_existing_chunk_ids(self) -> set[str]:
        """Get all chunk IDs currently in the index.

        Returns:
            Set of chunk_id strings.
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT chunk_id FROM chunks_fts")
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
            cursor = conn.execute(
                "DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,)
            )
            deleted += cursor.rowcount

        conn.commit()
        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the FTS index.

        Returns:
            Dict with keys: chunk_count, doc_count, modalities,
            db_size_bytes.
        """
        conn = self._get_connection()

        cursor = conn.execute("SELECT COUNT(*) AS cnt FROM chunks_fts")
        chunk_count = cursor.fetchone()["cnt"]

        cursor = conn.execute("SELECT COUNT(DISTINCT doc_id) AS cnt FROM chunks_fts")
        doc_count = cursor.fetchone()["cnt"]

        cursor = conn.execute("SELECT DISTINCT modality FROM chunks_fts")
        modalities = [row["modality"] for row in cursor]

        db_size = 0
        if self.db_path.exists():
            db_size = self.db_path.stat().st_size

        return {
            "chunk_count": chunk_count,
            "doc_count": doc_count,
            "modalities": modalities,
            "db_size_bytes": db_size,
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "FTSIndex":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
