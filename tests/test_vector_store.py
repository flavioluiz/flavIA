"""Tests for the vector store module."""

from importlib.util import find_spec
from pathlib import Path

import pytest

from flavia.content.indexer.vector_store import VectorStore

SQLITE_VEC_AVAILABLE = find_spec("sqlite_vec") is not None

# Skip all tests if sqlite-vec is not installed
pytestmark = pytest.mark.skipif(
    not SQLITE_VEC_AVAILABLE,
    reason="sqlite-vec not installed (pip install sqlite-vec)",
)


class TestVectorStoreInit:
    """Tests for VectorStore initialization."""

    def test_creates_index_directory(self, tmp_path: Path):
        """Should create .index directory if it doesn't exist."""
        with VectorStore(tmp_path) as store:
            # Trigger connection to create DB
            store._get_connection()
            assert (tmp_path / ".index").exists()
            assert (tmp_path / ".index" / "index.db").exists()

    def test_creates_schema(self, tmp_path: Path):
        """Should create chunks_vec and chunks_meta tables."""
        with VectorStore(tmp_path) as store:
            conn = store._get_connection()

            # Check chunks_meta table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_meta'"
            )
            assert cursor.fetchone() is not None

            # Check chunks_vec virtual table exists
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
            )
            assert cursor.fetchone() is not None

    def test_uses_explicit_db_path(self, tmp_path: Path):
        """Should use explicit db_path if provided."""
        custom_path = tmp_path / "custom" / "vectors.db"
        custom_path.parent.mkdir(parents=True)

        with VectorStore(tmp_path, db_path=custom_path) as store:
            store.upsert([("test", [0.1] * 768, {"doc_id": "d1", "modality": "text"})])

        assert custom_path.exists()

    def test_creates_parent_for_explicit_db_path(self, tmp_path: Path):
        """Should create parent directories for explicit db_path automatically."""
        custom_path = tmp_path / "nested" / "dir" / "vectors.db"

        with VectorStore(tmp_path, db_path=custom_path) as store:
            store._get_connection()

        assert custom_path.exists()


class TestUpsert:
    """Tests for VectorStore.upsert method."""

    def test_inserts_new_chunks(self, tmp_path: Path):
        """Should insert new chunks with their vectors and metadata."""
        with VectorStore(tmp_path) as store:
            items = [
                (
                    "chunk_1",
                    [0.1] * 768,
                    {
                        "doc_id": "doc_1",
                        "modality": "text",
                        "converted_path": ".converted/doc.md",
                        "locator": {"line_start": 10, "line_end": 20},
                        "heading_path": ["Section 1"],
                        "doc_name": "doc.pdf",
                        "file_type": "pdf",
                    },
                ),
            ]
            inserted, updated = store.upsert(items)

            assert inserted == 1
            assert updated == 0

            # Verify metadata stored
            conn = store._get_connection()
            cursor = conn.execute(
                "SELECT * FROM chunks_meta WHERE chunk_id = ?", ("chunk_1",)
            )
            row = cursor.fetchone()
            assert row["doc_id"] == "doc_1"
            assert row["modality"] == "text"
            assert row["doc_name"] == "doc.pdf"

    def test_updates_existing_chunks(self, tmp_path: Path):
        """Should update existing chunks (idempotent upsert)."""
        with VectorStore(tmp_path) as store:
            # Insert initial
            items = [
                ("chunk_1", [0.1] * 768, {"doc_id": "doc_1", "modality": "text"}),
            ]
            inserted1, updated1 = store.upsert(items)
            assert inserted1 == 1
            assert updated1 == 0

            # Upsert again with different metadata
            items = [
                ("chunk_1", [0.2] * 768, {"doc_id": "doc_1", "modality": "text_v2"}),
            ]
            inserted2, updated2 = store.upsert(items)
            assert inserted2 == 0
            assert updated2 == 1

            # Verify updated
            conn = store._get_connection()
            cursor = conn.execute(
                "SELECT modality FROM chunks_meta WHERE chunk_id = ?", ("chunk_1",)
            )
            assert cursor.fetchone()["modality"] == "text_v2"

    def test_idempotent_rerun(self, tmp_path: Path):
        """Re-running with same corpus should insert 0 new vectors."""
        with VectorStore(tmp_path) as store:
            items = [
                ("c1", [0.1] * 768, {"doc_id": "d1", "modality": "text"}),
                ("c2", [0.2] * 768, {"doc_id": "d1", "modality": "text"}),
            ]

            # First run
            inserted1, _ = store.upsert(items)
            assert inserted1 == 2

            # Second run with same items
            inserted2, updated2 = store.upsert(items)
            assert inserted2 == 0
            assert updated2 == 2


class TestKnnSearch:
    """Tests for VectorStore.knn_search method."""

    def test_returns_nearest_neighbors(self, tmp_path: Path):
        """Should return k nearest neighbors sorted by distance."""
        with VectorStore(tmp_path) as store:
            # Insert vectors with distinct patterns
            items = [
                ("close", [1.0] + [0.0] * 767, {"doc_id": "d1", "modality": "text"}),
                ("far", [0.0] * 767 + [1.0], {"doc_id": "d2", "modality": "text"}),
                ("medium", [0.5] + [0.0] * 766 + [0.5], {"doc_id": "d3", "modality": "text"}),
            ]
            store.upsert(items)

            # Query vector similar to "close"
            query_vec = [0.9] + [0.0] * 767
            results = store.knn_search(query_vec, k=3)

            assert len(results) == 3
            # First result should be "close" (most similar)
            assert results[0]["chunk_id"] == "close"

    def test_respects_doc_ids_filter(self, tmp_path: Path):
        """Should filter results by doc_ids when specified."""
        with VectorStore(tmp_path) as store:
            items = [
                ("c1", [1.0] + [0.0] * 767, {"doc_id": "doc_a", "modality": "text"}),
                ("c2", [0.9] + [0.0] * 767, {"doc_id": "doc_b", "modality": "text"}),
                ("c3", [0.8] + [0.0] * 767, {"doc_id": "doc_a", "modality": "text"}),
            ]
            store.upsert(items)

            query_vec = [1.0] + [0.0] * 767
            results = store.knn_search(query_vec, k=10, doc_ids_filter=["doc_a"])

            assert all(r["doc_id"] == "doc_a" for r in results)
            assert len(results) == 2

    def test_doc_filter_returns_results_even_when_not_in_global_top_k(self, tmp_path: Path):
        """Should return nearest in filtered docs, not empty due global-top-k truncation."""
        with VectorStore(tmp_path) as store:
            items = [
                ("close_1", [1.0] + [0.0] * 767, {"doc_id": "doc_a", "modality": "text"}),
                ("close_2", [1.0] + [0.0] * 767, {"doc_id": "doc_b", "modality": "text"}),
                ("close_3", [1.0] + [0.0] * 767, {"doc_id": "doc_c", "modality": "text"}),
                (
                    "far_filtered",
                    [0.0, 1.0] + [0.0] * 766,
                    {"doc_id": "doc_filtered", "modality": "text"},
                ),
            ]
            store.upsert(items)

            query_vec = [1.0] + [0.0] * 767
            results = store.knn_search(query_vec, k=1, doc_ids_filter=["doc_filtered"])

            assert len(results) == 1
            assert results[0]["chunk_id"] == "far_filtered"
            assert results[0]["doc_id"] == "doc_filtered"

    def test_returns_metadata(self, tmp_path: Path):
        """Should include all metadata fields in results."""
        with VectorStore(tmp_path) as store:
            items = [
                (
                    "c1",
                    [1.0] + [0.0] * 767,
                    {
                        "doc_id": "doc_1",
                        "modality": "video_transcript",
                        "converted_path": ".converted/video.md",
                        "locator": {"time_start": "00:01:00", "time_end": "00:02:00"},
                        "heading_path": ["Chapter 1", "Section A"],
                        "doc_name": "lecture.mp4",
                        "file_type": "video",
                    },
                ),
            ]
            store.upsert(items)

            results = store.knn_search([1.0] + [0.0] * 767, k=1)

            assert len(results) == 1
            result = results[0]
            assert result["chunk_id"] == "c1"
            assert result["doc_id"] == "doc_1"
            assert result["modality"] == "video_transcript"
            assert result["converted_path"] == ".converted/video.md"
            assert result["locator"]["time_start"] == "00:01:00"
            assert result["heading_path"] == ["Chapter 1", "Section A"]
            assert result["doc_name"] == "lecture.mp4"
            assert result["file_type"] == "video"
            assert "distance" in result


class TestGetExistingChunkIds:
    """Tests for VectorStore.get_existing_chunk_ids method."""

    def test_returns_all_ids(self, tmp_path: Path):
        """Should return all chunk IDs in the store."""
        with VectorStore(tmp_path) as store:
            items = [
                ("id_1", [0.1] * 768, {"doc_id": "d1", "modality": "text"}),
                ("id_2", [0.2] * 768, {"doc_id": "d1", "modality": "text"}),
                ("id_3", [0.3] * 768, {"doc_id": "d2", "modality": "text"}),
            ]
            store.upsert(items)

            ids = store.get_existing_chunk_ids()

            assert ids == {"id_1", "id_2", "id_3"}

    def test_returns_empty_set_when_empty(self, tmp_path: Path):
        """Should return empty set for empty store."""
        with VectorStore(tmp_path) as store:
            ids = store.get_existing_chunk_ids()
            assert ids == set()


class TestDeleteChunks:
    """Tests for VectorStore.delete_chunks method."""

    def test_deletes_specified_chunks(self, tmp_path: Path):
        """Should delete chunks by ID."""
        with VectorStore(tmp_path) as store:
            items = [
                ("c1", [0.1] * 768, {"doc_id": "d1", "modality": "text"}),
                ("c2", [0.2] * 768, {"doc_id": "d1", "modality": "text"}),
                ("c3", [0.3] * 768, {"doc_id": "d1", "modality": "text"}),
            ]
            store.upsert(items)

            deleted = store.delete_chunks(["c1", "c3"])

            assert deleted == 2
            remaining = store.get_existing_chunk_ids()
            assert remaining == {"c2"}

    def test_returns_zero_for_nonexistent(self, tmp_path: Path):
        """Should return 0 for non-existent chunk IDs."""
        with VectorStore(tmp_path) as store:
            deleted = store.delete_chunks(["nonexistent"])
            assert deleted == 0

    def test_handles_empty_list(self, tmp_path: Path):
        """Should handle empty list gracefully."""
        with VectorStore(tmp_path) as store:
            deleted = store.delete_chunks([])
            assert deleted == 0


class TestGetStats:
    """Tests for VectorStore.get_stats method."""

    def test_returns_correct_counts(self, tmp_path: Path):
        """Should return correct chunk and doc counts."""
        with VectorStore(tmp_path) as store:
            items = [
                ("c1", [0.1] * 768, {"doc_id": "doc_1", "modality": "text"}),
                ("c2", [0.2] * 768, {"doc_id": "doc_1", "modality": "text"}),
                ("c3", [0.3] * 768, {"doc_id": "doc_2", "modality": "video_transcript"}),
            ]
            store.upsert(items)

            stats = store.get_stats()

            assert stats["chunk_count"] == 3
            assert stats["doc_count"] == 2
            assert set(stats["modalities"]) == {"text", "video_transcript"}
            assert stats["db_size_bytes"] > 0
            assert stats["last_indexed_at"] is not None

    def test_returns_zeros_when_empty(self, tmp_path: Path):
        """Should return zeros for empty store."""
        with VectorStore(tmp_path) as store:
            stats = store.get_stats()

            assert stats["chunk_count"] == 0
            assert stats["doc_count"] == 0
            assert stats["modalities"] == []


class TestContextManager:
    """Tests for context manager protocol."""

    def test_closes_connection_on_exit(self, tmp_path: Path):
        """Should close connection when exiting context."""
        store = VectorStore(tmp_path)
        with store:
            # Force connection creation
            store._get_connection()
            assert store._conn is not None

        assert store._conn is None

    def test_closes_on_exception(self, tmp_path: Path):
        """Should close connection even on exception."""
        store = VectorStore(tmp_path)
        try:
            with store:
                store._get_connection()
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert store._conn is None
