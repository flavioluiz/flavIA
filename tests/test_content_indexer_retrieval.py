"""Tests for hybrid retrieval engine combining vector and FTS search."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.indexer.retrieval import (
    _get_doc_id,
    _merge_chunk_data,
    _rrf_score,
    retrieve,
)
from flavia.config import Settings


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
