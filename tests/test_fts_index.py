"""Tests for the FTS index module."""

from pathlib import Path

import pytest

from flavia.content.indexer.fts import FTSIndex


def _make_chunk(chunk_id, doc_id="d1", modality="text", text="", heading_path=None):
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "modality": modality,
        "text": text,
        "heading_path": heading_path or [],
    }


class TestFTSIndexInit:
    """Tests for FTSIndex initialization."""

    def test_creates_index_directory(self, tmp_path: Path):
        """Should create .index directory if it doesn't exist."""
        with FTSIndex(tmp_path) as idx:
            idx._get_connection()
            assert (tmp_path / ".index").exists()
            assert (tmp_path / ".index" / "index.db").exists()

    def test_creates_fts_schema(self, tmp_path: Path):
        """Should create chunks_fts virtual table."""
        with FTSIndex(tmp_path) as idx:
            conn = idx._get_connection()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
            )
            assert cursor.fetchone() is not None

    def test_uses_explicit_db_path(self, tmp_path: Path):
        """Should use explicit db_path if provided."""
        custom_path = tmp_path / "custom" / "search.db"
        custom_path.parent.mkdir(parents=True)

        with FTSIndex(tmp_path, db_path=custom_path) as idx:
            idx.upsert([_make_chunk("c1", text="hello world")])

        assert custom_path.exists()


class TestUpsert:
    """Tests for FTSIndex.upsert method."""

    def test_inserts_new_chunks(self, tmp_path: Path):
        """Should insert new chunks and return correct counts."""
        with FTSIndex(tmp_path) as idx:
            chunks = [
                _make_chunk("c1", text="HTTP protocol specification"),
                _make_chunk("c2", text="TCP connection handling"),
            ]
            inserted, updated = idx.upsert(chunks)

            assert inserted == 2
            assert updated == 0

    def test_updates_existing_chunks(self, tmp_path: Path):
        """Should re-insert (delete+insert) existing chunks."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([_make_chunk("c1", text="original text")])

            inserted, updated = idx.upsert([_make_chunk("c1", text="updated text")])
            assert inserted == 0
            assert updated == 1

            # Verify the text was actually updated
            results = idx.search("updated")
            assert len(results) == 1
            assert results[0]["text"] == "updated text"

    def test_idempotent_rerun(self, tmp_path: Path):
        """Re-running with the same corpus should report 0 inserts, N updates."""
        with FTSIndex(tmp_path) as idx:
            chunks = [
                _make_chunk("c1", text="foo bar"),
                _make_chunk("c2", text="baz qux"),
            ]
            inserted1, _ = idx.upsert(chunks)
            assert inserted1 == 2

            inserted2, updated2 = idx.upsert(chunks)
            assert inserted2 == 0
            assert updated2 == 2

    def test_stores_heading_path_as_string(self, tmp_path: Path):
        """Heading path list should be stored as ' > '-delimited string."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert(
                [_make_chunk("c1", text="content", heading_path=["Chapter 1", "Section A"])]
            )
            conn = idx._get_connection()
            row = conn.execute(
                "SELECT heading_path FROM chunks_fts WHERE chunk_id = 'c1'"
            ).fetchone()
            assert row["heading_path"] == "Chapter 1 > Section A"

    def test_repeated_chunk_id_in_same_batch_keeps_last_version(self, tmp_path: Path):
        """Repeated chunk IDs in one batch should not create duplicate rows."""
        with FTSIndex(tmp_path) as idx:
            inserted, updated = idx.upsert(
                [
                    _make_chunk("c1", text="first version"),
                    _make_chunk("c1", text="second version"),
                ]
            )

            assert inserted == 1
            assert updated == 1
            assert idx.get_existing_chunk_ids() == {"c1"}
            results = idx.search("second")
            assert len(results) == 1
            assert results[0]["text"] == "second version"


class TestSearch:
    """Tests for FTSIndex.search method."""

    def test_returns_matching_chunks(self, tmp_path: Path):
        """Should return chunks whose text matches the query."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", text="Python programming language"),
                _make_chunk("c2", text="Java virtual machine"),
            ])

            results = idx.search("Python")
            assert len(results) == 1
            assert results[0]["chunk_id"] == "c1"

    def test_bm25_ranking(self, tmp_path: Path):
        """Results should be ordered by BM25 score (lower = better match)."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", text="HTTP HTTP HTTP repeated many times"),
                _make_chunk("c2", text="HTTP once in a long document with many other words"),
            ])

            results = idx.search("HTTP")
            assert len(results) == 2
            # All scores should be negative (BM25 convention)
            for r in results:
                assert r["bm25_score"] < 0

    def test_respects_k_limit(self, tmp_path: Path):
        """Should return at most k results."""
        with FTSIndex(tmp_path) as idx:
            for i in range(10):
                idx.upsert([_make_chunk(f"c{i}", text=f"network protocol document {i}")])

            results = idx.search("network", k=3)
            assert len(results) <= 3

    def test_respects_doc_ids_filter(self, tmp_path: Path):
        """Should restrict results to the specified doc_ids."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", doc_id="doc_a", text="security vulnerability exploit"),
                _make_chunk("c2", doc_id="doc_b", text="security best practices"),
                _make_chunk("c3", doc_id="doc_a", text="security audit report"),
            ])

            results = idx.search("security", doc_ids_filter=["doc_a"])
            assert all(r["doc_id"] == "doc_a" for r in results)
            assert len(results) == 2

    def test_exact_term_matching(self, tmp_path: Path):
        """Should match exact codes, IDs, and acronyms like RFC-2616."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", text="RFC-2616 defines HTTP/1.1 protocol"),
                _make_chunk("c2", text="ATP-123 is a ticket identifier"),
                _make_chunk("c3", text="unrelated content about databases"),
            ])

            results_rfc = idx.search("RFC-2616")
            assert len(results_rfc) == 1
            assert results_rfc[0]["chunk_id"] == "c1"

            results_atp = idx.search("ATP-123")
            assert len(results_atp) == 1
            assert results_atp[0]["chunk_id"] == "c2"

    def test_porter_stemming(self, tmp_path: Path):
        """Porter tokenizer should match stemmed forms (running -> run)."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", text="the process is running smoothly"),
            ])

            # Stemmed query should match
            results = idx.search("run")
            assert len(results) >= 1
            assert results[0]["chunk_id"] == "c1"

    def test_empty_query_returns_empty(self, tmp_path: Path):
        """Empty or whitespace query should return empty list."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([_make_chunk("c1", text="some content")])

            assert idx.search("") == []
            assert idx.search("   ") == []

    def test_non_positive_k_returns_empty(self, tmp_path: Path):
        """k <= 0 should return no results."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([_make_chunk("c1", text="network protocol")])

            assert idx.search("network", k=0) == []
            assert idx.search("network", k=-1) == []

    def test_empty_doc_ids_filter_returns_empty(self, tmp_path: Path):
        """Explicit empty doc_ids_filter should return no results."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([_make_chunk("c1", doc_id="doc_a", text="security audit")])

            assert idx.search("security", doc_ids_filter=[]) == []

    def test_handles_special_characters(self, tmp_path: Path):
        """Should handle queries with special characters without raising."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([_make_chunk("c1", text="foo bar baz")])

            # These should not raise exceptions
            results = idx.search('test "quoted"')
            assert isinstance(results, list)

            results = idx.search("test * wildcard")
            assert isinstance(results, list)

    def test_heading_path_reconstructed_as_list(self, tmp_path: Path):
        """heading_path in results should be a list, not a string."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk(
                    "c1",
                    text="section content",
                    heading_path=["Part I", "Chapter 2"],
                )
            ])

            results = idx.search("section")
            assert len(results) == 1
            assert results[0]["heading_path"] == ["Part I", "Chapter 2"]


class TestGetExistingChunkIds:
    """Tests for FTSIndex.get_existing_chunk_ids method."""

    def test_returns_all_ids(self, tmp_path: Path):
        """Should return all chunk IDs in the index."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("id_1", text="alpha"),
                _make_chunk("id_2", text="beta"),
                _make_chunk("id_3", text="gamma"),
            ])

            ids = idx.get_existing_chunk_ids()
            assert ids == {"id_1", "id_2", "id_3"}

    def test_returns_empty_set_when_empty(self, tmp_path: Path):
        """Should return empty set for empty index."""
        with FTSIndex(tmp_path) as idx:
            assert idx.get_existing_chunk_ids() == set()


class TestDeleteChunks:
    """Tests for FTSIndex.delete_chunks method."""

    def test_deletes_specified_chunks(self, tmp_path: Path):
        """Should delete the requested chunks and return count."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", text="alpha"),
                _make_chunk("c2", text="beta"),
                _make_chunk("c3", text="gamma"),
            ])

            deleted = idx.delete_chunks(["c1", "c3"])
            assert deleted == 2
            assert idx.get_existing_chunk_ids() == {"c2"}

    def test_returns_zero_for_nonexistent(self, tmp_path: Path):
        """Should return 0 when deleting non-existent IDs."""
        with FTSIndex(tmp_path) as idx:
            deleted = idx.delete_chunks(["does_not_exist"])
            assert deleted == 0

    def test_handles_empty_list(self, tmp_path: Path):
        """Should handle empty list gracefully."""
        with FTSIndex(tmp_path) as idx:
            assert idx.delete_chunks([]) == 0


class TestGetStats:
    """Tests for FTSIndex.get_stats method."""

    def test_returns_correct_counts(self, tmp_path: Path):
        """Should return correct chunk count, doc count, and modalities."""
        with FTSIndex(tmp_path) as idx:
            idx.upsert([
                _make_chunk("c1", doc_id="doc_1", modality="text", text="foo"),
                _make_chunk("c2", doc_id="doc_1", modality="text", text="bar"),
                _make_chunk("c3", doc_id="doc_2", modality="video_transcript", text="baz"),
            ])

            stats = idx.get_stats()

            assert stats["chunk_count"] == 3
            assert stats["doc_count"] == 2
            assert set(stats["modalities"]) == {"text", "video_transcript"}
            assert stats["db_size_bytes"] > 0

    def test_returns_zeros_when_empty(self, tmp_path: Path):
        """Should return zeros for empty index."""
        with FTSIndex(tmp_path) as idx:
            stats = idx.get_stats()
            assert stats["chunk_count"] == 0
            assert stats["doc_count"] == 0
            assert stats["modalities"] == []


class TestContextManager:
    """Tests for context manager protocol."""

    def test_closes_connection_on_exit(self, tmp_path: Path):
        """Should close connection when exiting context."""
        idx = FTSIndex(tmp_path)
        with idx:
            idx._get_connection()
            assert idx._conn is not None

        assert idx._conn is None

    def test_closes_on_exception(self, tmp_path: Path):
        """Should close connection even on exception."""
        idx = FTSIndex(tmp_path)
        try:
            with idx:
                idx._get_connection()
                raise ValueError("test error")
        except ValueError:
            pass

        assert idx._conn is None
