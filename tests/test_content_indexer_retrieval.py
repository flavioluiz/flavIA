"""Tests for hybrid retrieval engine combining vector and FTS search."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.catalog import ContentCatalog
from flavia.content.indexer.retrieval import (
    _catalog_doc_id,
    _get_doc_id,
    _merge_chunk_data,
    _route_doc_ids_from_catalog,
    _rrf_score,
    retrieve,
)
from flavia.content.scanner import FileEntry
from flavia.config import Settings


def _make_catalog_entry(
    *,
    path: str,
    summary: str,
    checksum_sha256: str,
    file_type: str = "text",
    category: str = "markdown",
    converted_to: str | None = ".converted/default.md",
) -> FileEntry:
    now = datetime.now(timezone.utc).isoformat()
    return FileEntry(
        path=path,
        name=Path(path).name,
        extension=Path(path).suffix,
        file_type=file_type,
        category=category,
        size_bytes=123,
        created_at=now,
        modified_at=now,
        indexed_at=now,
        checksum_sha256=checksum_sha256,
        summary=summary,
        status="current",
        converted_to=converted_to,
    )


def _write_catalog(base_dir: Path, entries: list[FileEntry]) -> None:
    catalog = ContentCatalog(base_dir)
    now = datetime.now(timezone.utc).isoformat()
    catalog.catalog_created_at = now
    catalog.catalog_updated_at = now
    catalog.files = {entry.path: entry for entry in entries}
    catalog.save(base_dir / ".flavia")


class TestRRFScore:
    """Unit tests for RRF score calculation."""

    def test_single_rank(self):
        """RRF score with one ranking: 1/(k + rank)."""
        score = _rrf_score([1], k=60)
        expected = 1.0 / (60 + 1)
        assert abs(score - expected) < 1e-9

    def test_multiple_ranks(self):
        """RRF score with multiple rankings: Σ 1/(k + rank_i)."""
        score = _rrf_score([1, 2], k=60)
        expected = 1.0 / (60 + 1) + 1.0 / (60 + 2)
        assert abs(score - expected) < 1e-9

    def test_none_rank_ignored(self):
        """None ranks are ignored in score calculation."""
        score = _rrf_score([1, None], k=60)
        expected = 1.0 / (60 + 1)
        assert abs(score - expected) < 1e-9

    def test_all_none_ranks(self):
        """All None ranks result in zero score."""
        score = _rrf_score([None, None], k=60)
        assert score == 0.0

    def test_empty_ranks(self):
        """Empty ranks list results in zero score."""
        score = _rrf_score([], k=60)
        assert score == 0.0

    def test_custom_k(self):
        """RRF score respects custom k value."""
        score_k60 = _rrf_score([1], k=60)
        score_k120 = _rrf_score([1], k=120)
        # Both should be positive but k=120 should give smaller score
        assert score_k60 > score_k120 > 0.0

    def test_higher_rank_lower_score(self):
        """Higher rank positions get lower contribution scores."""
        score_rank1 = _rrf_score([1], k=60)
        score_rank2 = _rrf_score([2], k=60)
        assert score_rank1 > score_rank2


class TestGetDocId:
    """Unit tests for getting doc_id from search results."""

    def test_get_doc_id_from_vector_results(self):
        """Extract doc_id from vector search results."""
        vector_results = [
            {"chunk_id": "c1", "doc_id": "doc1"},
            {"chunk_id": "c2", "doc_id": "doc2"},
        ]
        fts_results = []

        doc_id = _get_doc_id("c1", vector_results, fts_results)
        assert doc_id == "doc1"

    def test_get_doc_id_from_fts_results(self):
        """Extract doc_id from FTS results when not in vector."""
        vector_results = [{"chunk_id": "c1", "doc_id": "doc1"}]
        fts_results = [{"chunk_id": "c2", "doc_id": "doc2"}]

        doc_id = _get_doc_id("c2", vector_results, fts_results)
        assert doc_id == "doc2"

    def test_get_doc_id_prefers_vector(self):
        """Prefer vector results when chunk exists in both."""
        vector_results = [{"chunk_id": "c1", "doc_id": "doc_from_vector"}]
        fts_results = [{"chunk_id": "c1", "doc_id": "doc_from_fts"}]

        doc_id = _get_doc_id("c1", vector_results, fts_results)
        assert doc_id == "doc_from_vector"

    def test_get_doc_id_not_found(self):
        """Return empty string when chunk not found."""
        doc_id = _get_doc_id("nonexistent", [], [])
        assert doc_id == ""


class TestMergeChunkData:
    """Unit tests for merging vector and FTS result data."""

    def test_merge_from_vector_result(self):
        """Merge uses all metadata from vector result."""
        vector_results = [{
            "chunk_id": "c1",
            "doc_id": "doc1",
            "modality": "text",
            "heading_path": ["section"],
            "doc_name": "example.pdf",
            "file_type": "pdf",
            "locator": {"line_start": 1},
            "converted_path": "/path/to/converted",
        }]
        fts_results = [{
            "chunk_id": "c1",
            "text": "Example text",
        }]

        result = _merge_chunk_data("c1", 0.5, 1, 2, vector_results, fts_results)

        assert result["chunk_id"] == "c1"
        assert result["doc_id"] == "doc1"
        assert result["modality"] == "text"
        assert result["heading_path"] == ["section"]
        assert result["doc_name"] == "example.pdf"
        assert result["file_type"] == "pdf"
        assert result["locator"] == {"line_start": 1}
        assert result["converted_path"] == "/path/to/converted"
        assert result["text"] == "Example text"
        assert result["score"] == 0.5
        assert result["vector_rank"] == 1
        assert result["fts_rank"] == 2

    def test_merge_fallback_to_fts_metadata(self):
        """Fall back to FTS metadata if vector result missing."""
        vector_results = []
        fts_results = [{
            "chunk_id": "c1",
            "doc_id": "doc1",
            "modality": "text",
            "heading_path": ["section"],
            "text": "Example text",
        }]

        result = _merge_chunk_data("c1", 0.5, None, 1, vector_results, fts_results)

        assert result["doc_id"] == "doc1"
        assert result["modality"] == "text"
        assert result["heading_path"] == ["section"]
        assert result["text"] == "Example text"

    def test_merge_empty_text_fallback(self):
        """Use empty string for text if not in FTS results."""
        vector_results = [{
            "chunk_id": "c1",
            "doc_id": "doc1",
            "modality": "text",
            "heading_path": [],
            "doc_name": "doc",
            "file_type": "txt",
            "locator": {},
            "converted_path": "",
        }]
        fts_results = []

        result = _merge_chunk_data("c1", 0.5, 1, None, vector_results, fts_results)

        assert result["text"] == ""


class TestEmptyFilterReturnsEmpty:
    """Test that empty doc_ids_filter returns empty results."""

    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_empty_filter_returns_empty_list(self, mock_get_client):
        """Empty doc_ids_filter=[] returns [] without querying."""
        settings = Settings()
        base_dir = Path("/tmp")

        results = retrieve(
            "question",
            base_dir,
            settings,
            doc_ids_filter=[],
        )

        assert results == []
        # Should not call embedding client
        mock_get_client.assert_not_called()


class TestInputValidation:
    """Test retrieval input validation edge cases."""

    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_blank_question_returns_empty_without_queries(self, mock_get_client):
        """Empty/whitespace question should return [] and skip expensive calls."""
        settings = Settings()
        base_dir = Path("/tmp")

        assert retrieve("", base_dir, settings) == []
        assert retrieve("   ", base_dir, settings) == []
        mock_get_client.assert_not_called()

    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_non_positive_top_k_returns_empty(self, mock_get_client):
        """top_k <= 0 should return [] and skip all searches."""
        settings = Settings()
        base_dir = Path("/tmp")

        assert retrieve("question", base_dir, settings, top_k=0) == []
        assert retrieve("question", base_dir, settings, top_k=-5) == []
        mock_get_client.assert_not_called()


class TestVectorStoreLifecycle:
    """Tests for conditional VectorStore usage in retrieval."""

    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    def test_fts_only_non_video_does_not_open_vector_store(
        self,
        mock_vs,
        mock_fts,
        mock_get_client,
    ):
        """FTS-only text results should not require opening VectorStore."""
        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = [
            {
                "chunk_id": "chunk_1",
                "doc_id": "doc_1",
                "modality": "text",
                "heading_path": ["Section"],
                "text": "only fts text",
            }
        ]
        mock_fts.return_value = mock_fts_instance

        settings = Settings()
        results = retrieve(
            "question",
            Path("/tmp"),
            settings,
            vector_k=0,
            fts_k=10,
            expand_video_temporal=True,
        )

        assert len(results) == 1
        assert results[0]["chunk_id"] == "chunk_1"
        mock_vs.assert_not_called()
        mock_get_client.assert_not_called()


class TestCatalogRouterStageA:
    """Tests for Stage A catalog routing behavior."""

    def test_catalog_router_ignores_entries_without_converted_content(self, tmp_path: Path):
        """Stage A should only route documents that can produce indexed chunks."""
        converted_entry = _make_catalog_entry(
            path="docs/converted.md",
            summary="quantum entanglement notes",
            checksum_sha256="sha_converted",
            converted_to=".converted/converted.md",
        )
        non_converted_entry = _make_catalog_entry(
            path="docs/raw.md",
            summary="quantum entanglement raw source",
            checksum_sha256="sha_raw",
            converted_to=None,
        )
        _write_catalog(tmp_path, [converted_entry, non_converted_entry])

        converted_doc_id = _catalog_doc_id(
            tmp_path,
            converted_entry.path,
            converted_entry.checksum_sha256,
        )

        routed = _route_doc_ids_from_catalog("quantum entanglement", tmp_path)

        assert routed == [converted_doc_id]

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_catalog_router_shortlists_doc_ids(self, mock_get_client, mock_vs, mock_fts, tmp_path: Path):
        """Question terms should narrow Stage-B search to routed doc_ids."""
        quantum_entry = _make_catalog_entry(
            path="docs/quantum.md",
            summary="Quantum mechanics and entanglement notes",
            checksum_sha256="sha_quantum",
        )
        cooking_entry = _make_catalog_entry(
            path="docs/cooking.md",
            summary="Italian cooking recipes and sauces",
            checksum_sha256="sha_cooking",
        )
        _write_catalog(tmp_path, [quantum_entry, cooking_entry])

        quantum_doc_id = _catalog_doc_id(tmp_path, quantum_entry.path, quantum_entry.checksum_sha256)

        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = []

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = []

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            retrieve("quantum entanglement", tmp_path, settings)

        vs_filter = mock_vs_instance.knn_search.call_args[1]["doc_ids_filter"]
        fts_filter = mock_fts_instance.search.call_args[1]["doc_ids_filter"]
        assert vs_filter == [quantum_doc_id]
        assert fts_filter == [quantum_doc_id]

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_catalog_router_intersects_explicit_scope(
        self, mock_get_client, mock_vs, mock_fts, tmp_path: Path
    ):
        """When doc_ids_filter is provided, Stage A should narrow within that scope."""
        quantum_entry = _make_catalog_entry(
            path="docs/quantum.md",
            summary="Quantum mechanics and entanglement notes",
            checksum_sha256="sha_quantum",
        )
        cooking_entry = _make_catalog_entry(
            path="docs/cooking.md",
            summary="Italian cooking recipes and sauces",
            checksum_sha256="sha_cooking",
        )
        _write_catalog(tmp_path, [quantum_entry, cooking_entry])

        quantum_doc_id = _catalog_doc_id(tmp_path, quantum_entry.path, quantum_entry.checksum_sha256)
        cooking_doc_id = _catalog_doc_id(tmp_path, cooking_entry.path, cooking_entry.checksum_sha256)

        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = []

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = []

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            retrieve(
                "cooking pasta",
                tmp_path,
                settings,
                doc_ids_filter=[quantum_doc_id, cooking_doc_id],
            )

        vs_filter = mock_vs_instance.knn_search.call_args[1]["doc_ids_filter"]
        fts_filter = mock_fts_instance.search.call_args[1]["doc_ids_filter"]
        assert vs_filter == [cooking_doc_id]
        assert fts_filter == [cooking_doc_id]

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_missing_catalog_keeps_original_scope(
        self, mock_get_client, mock_vs, mock_fts, tmp_path: Path
    ):
        """If no catalog exists, retrieval should not change doc_ids_filter."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = []

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = []

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            retrieve("question", tmp_path, settings, doc_ids_filter=None)

        vs_filter = mock_vs_instance.knn_search.call_args[1]["doc_ids_filter"]
        fts_filter = mock_fts_instance.search.call_args[1]["doc_ids_filter"]
        assert vs_filter is None
        assert fts_filter is None

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_no_catalog_match_does_not_override_explicit_scope(
        self, mock_get_client, mock_vs, mock_fts, tmp_path: Path
    ):
        """No Stage-A hit should preserve caller-provided scope."""
        entry = _make_catalog_entry(
            path="docs/quantum.md",
            summary="Quantum mechanics and entanglement notes",
            checksum_sha256="sha_quantum",
        )
        _write_catalog(tmp_path, [entry])
        scoped_doc_id = _catalog_doc_id(tmp_path, entry.path, entry.checksum_sha256)

        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = []

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = []

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            retrieve(
                "culinary fermentation",
                tmp_path,
                settings,
                doc_ids_filter=[scoped_doc_id],
            )

        vs_filter = mock_vs_instance.knn_search.call_args[1]["doc_ids_filter"]
        fts_filter = mock_fts_instance.search.call_args[1]["doc_ids_filter"]
        assert vs_filter == [scoped_doc_id]
        assert fts_filter == [scoped_doc_id]


class TestDiversityFilter:
    """Test diversity filtering (max chunks per doc)."""

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_max_chunks_per_doc(self, mock_get_client, mock_vs, mock_fts):
        """Limit chunks per document to max_chunks_per_doc."""
        # Setup mocks
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        # Create vector results: 5 chunks from doc1, 2 from doc2
        vector_results = [
            {"chunk_id": f"c{i}", "doc_id": "doc1", "modality": "text",
             "heading_path": [], "doc_name": "doc", "file_type": "txt",
             "locator": {}, "converted_path": "", "distance": i}
            for i in range(1, 6)
        ] + [
            {"chunk_id": f"c{i}", "doc_id": "doc2", "modality": "text",
             "heading_path": [], "doc_name": "doc", "file_type": "txt",
             "locator": {}, "converted_path": "", "distance": i}
            for i in range(6, 8)
        ]

        # Create FTS results (not found, so ranks will be None)
        fts_results = []

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        # Mock embed_query to return a dummy vector
        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve(
                "question",
                Path("/tmp"),
                settings,
                top_k=10,
                max_chunks_per_doc=2,
            )

        # Should have max 2 chunks from doc1 and max 2 from doc2
        doc1_chunks = [r for r in results if r["doc_id"] == "doc1"]
        doc2_chunks = [r for r in results if r["doc_id"] == "doc2"]

        assert len(doc1_chunks) <= 2
        assert len(doc2_chunks) <= 2
        assert len(results) <= 4

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_single_doc_scope_adapts_diversity_cap(self, mock_get_client, mock_vs, mock_fts):
        """Single-doc scoped retrieval should expand per-doc cap for coverage."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        vector_results = [
            {
                "chunk_id": f"c{i}",
                "doc_id": "doc_single",
                "modality": "text",
                "heading_path": [],
                "doc_name": "doc",
                "file_type": "txt",
                "locator": {},
                "converted_path": "",
                "distance": i,
            }
            for i in range(1, 7)
        ]

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = []

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve(
                "question",
                Path("/tmp"),
                settings,
                doc_ids_filter=["doc_single"],
                top_k=5,
                max_chunks_per_doc=2,
            )

        assert len(results) == 5
        assert all(r["doc_id"] == "doc_single" for r in results)


class TestRRFFusionOrdering:
    """Test that RRF fusion produces correct ordering."""

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_chunk_in_both_beats_single_source(self, mock_get_client, mock_vs, mock_fts):
        """Chunk ranked in both sources should beat single-source chunk."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        # Vector results: c1 at rank 1, c2 at rank 1
        vector_results = [
            {"chunk_id": "c1", "doc_id": "doc1", "modality": "text",
             "heading_path": [], "doc_name": "doc1", "file_type": "txt",
             "locator": {}, "converted_path": "", "distance": 0.1},
            {"chunk_id": "c2", "doc_id": "doc2", "modality": "text",
             "heading_path": [], "doc_name": "doc2", "file_type": "txt",
             "locator": {}, "converted_path": "", "distance": 0.2},
        ]

        # FTS results: c1 at rank 1 (so c1 appears in both)
        fts_results = [
            {"chunk_id": "c1", "doc_id": "doc1", "modality": "text",
             "heading_path": [], "text": "text1"},
        ]

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve(
                "question",
                Path("/tmp"),
                settings,
                top_k=10,
            )

        # c1 (in both sources) should come before c2 (only vector)
        assert results[0]["chunk_id"] == "c1"
        assert results[1]["chunk_id"] == "c2"

        # Verify scores: c1 should have higher score
        assert results[0]["score"] > results[1]["score"]

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_tie_break_is_deterministic(self, mock_get_client, mock_vs, mock_fts):
        """Equal-score ties should have deterministic ordering."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        # b_chunk appears only in vector rank1; a_chunk appears only in fts rank1.
        # Both receive the same RRF score and require tie-breaking.
        vector_results = [{
            "chunk_id": "b_chunk",
            "doc_id": "doc_b",
            "modality": "text",
            "heading_path": [],
            "doc_name": "doc_b",
            "file_type": "txt",
            "locator": {},
            "converted_path": "",
            "distance": 0.1,
        }]
        fts_results = [{
            "chunk_id": "a_chunk",
            "doc_id": "doc_a",
            "modality": "text",
            "heading_path": [],
            "text": "text_a",
        }]

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve("question", Path("/tmp"), settings, top_k=10)

        assert [r["chunk_id"] for r in results[:2]] == ["a_chunk", "b_chunk"]


class TestRetrieveIntegration:
    """Integration tests with real index structures."""

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_retrieve_returns_all_expected_fields(self, mock_get_client, mock_vs, mock_fts):
        """Verify returned results contain all expected fields."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        vector_results = [{
            "chunk_id": "chunk_001",
            "doc_id": "doc_123",
            "modality": "text",
            "heading_path": ["Introduction", "Background"],
            "doc_name": "example.pdf",
            "file_type": "pdf",
            "locator": {"line_start": 10, "line_end": 20},
            "converted_path": ".converted/example.md",
            "distance": 0.15,
        }]

        fts_results = [{
            "chunk_id": "chunk_001",
            "doc_id": "doc_123",
            "modality": "text",
            "heading_path": ["Introduction", "Background"],
            "text": "This is the chunk text content",
            "bm25_score": -1.5,
        }]

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve(
                "what is X?",
                Path("/tmp"),
                settings,
                top_k=5,
            )

        assert len(results) == 1
        result = results[0]

        # Verify all expected fields
        assert result["chunk_id"] == "chunk_001"
        assert result["doc_id"] == "doc_123"
        assert result["text"] == "This is the chunk text content"
        assert result["score"] > 0  # RRF score should be positive
        assert result["vector_rank"] == 1
        assert result["fts_rank"] == 1
        assert result["modality"] == "text"
        assert result["heading_path"] == ["Introduction", "Background"]
        assert result["doc_name"] == "example.pdf"
        assert result["file_type"] == "pdf"
        assert result["locator"] == {"line_start": 10, "line_end": 20}
        assert result["converted_path"] == ".converted/example.md"

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_fts_only_result_keeps_full_schema(self, mock_get_client, mock_vs, mock_fts):
        """FTS-only hits should still expose all documented result keys."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = []

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = [{
            "chunk_id": "chunk_fts_only",
            "doc_id": "doc_fts",
            "modality": "text",
            "heading_path": ["Section A"],
            "text": "fts-only text",
            "bm25_score": -1.0,
        }]

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve("question", Path("/tmp"), settings, top_k=5)

        assert len(results) == 1
        result = results[0]
        assert result["chunk_id"] == "chunk_fts_only"
        assert result["doc_id"] == "doc_fts"
        assert result["text"] == "fts-only text"
        assert result["modality"] == "text"
        assert result["heading_path"] == ["Section A"]
        assert result["doc_name"] == ""
        assert result["file_type"] == ""
        assert result["locator"] == {}
        assert result["converted_path"] == ""


class TestFilterSemantics:
    """Test doc_ids_filter semantics consistency."""

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_none_filter_searches_all(self, mock_get_client, mock_vs, mock_fts):
        """doc_ids_filter=None searches all documents."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        vector_results = [{"chunk_id": "c1", "doc_id": "doc1", "modality": "text",
                          "heading_path": [], "doc_name": "doc1", "file_type": "txt",
                          "locator": {}, "converted_path": ""}]
        fts_results = []

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            results = retrieve(
                "question",
                Path("/tmp"),
                settings,
                doc_ids_filter=None,  # None means search all
            )

        # Should search with doc_ids_filter=None
        mock_vs_instance.knn_search.assert_called_once()
        call_kwargs = mock_vs_instance.knn_search.call_args[1]
        assert call_kwargs["doc_ids_filter"] is None

        mock_fts_instance.search.assert_called_once()
        call_kwargs = mock_fts_instance.search.call_args[1]
        assert call_kwargs["doc_ids_filter"] is None

    @patch("flavia.content.indexer.retrieval.FTSIndex")
    @patch("flavia.content.indexer.retrieval.VectorStore")
    @patch("flavia.content.indexer.retrieval.get_embedding_client")
    def test_specific_filter_narrows_search(self, mock_get_client, mock_vs, mock_fts):
        """doc_ids_filter=["id1", "id2"] restricts search."""
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "model")

        vector_results = [{"chunk_id": "c1", "doc_id": "doc1", "modality": "text",
                          "heading_path": [], "doc_name": "doc1", "file_type": "txt",
                          "locator": {}, "converted_path": ""}]
        fts_results = []

        mock_vs_instance = MagicMock()
        mock_vs_instance.__enter__ = MagicMock(return_value=mock_vs_instance)
        mock_vs_instance.__exit__ = MagicMock(return_value=None)
        mock_vs_instance.knn_search.return_value = vector_results

        mock_fts_instance = MagicMock()
        mock_fts_instance.__enter__ = MagicMock(return_value=mock_fts_instance)
        mock_fts_instance.__exit__ = MagicMock(return_value=None)
        mock_fts_instance.search.return_value = fts_results

        mock_vs.return_value = mock_vs_instance
        mock_fts.return_value = mock_fts_instance

        with patch("flavia.content.indexer.retrieval.embed_query", return_value=[0.0] * 768):
            settings = Settings()
            doc_filter = ["doc1", "doc2"]
            results = retrieve(
                "question",
                Path("/tmp"),
                settings,
                doc_ids_filter=doc_filter,
            )

        # Should pass filter through to both indexes
        mock_vs_instance.knn_search.assert_called_once()
        call_kwargs = mock_vs_instance.knn_search.call_args[1]
        assert call_kwargs["doc_ids_filter"] == doc_filter

        mock_fts_instance.search.assert_called_once()
        call_kwargs = mock_fts_instance.search.call_args[1]
        assert call_kwargs["doc_ids_filter"] == doc_filter
