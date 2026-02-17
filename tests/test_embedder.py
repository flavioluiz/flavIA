"""Tests for the embedder module."""

import math
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.indexer.embedder import (
    DEFAULT_BATCH_SIZE,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    _format_chunk_for_embedding,
    _l2_normalize,
    embed_chunks,
    embed_query,
    get_embedding_client,
)


class TestL2Normalize:
    """Tests for _l2_normalize function."""

    def test_normalizes_to_unit_length(self):
        """Normalized vector should have L2 norm of 1.0."""
        vector = [3.0, 4.0]
        result = _l2_normalize(vector)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 0.0001

    def test_preserves_direction(self):
        """Normalization should preserve the direction ratio."""
        vector = [3.0, 4.0]
        result = _l2_normalize(vector)
        # Original ratio is 3:4, should be preserved
        assert abs(result[0] / result[1] - 0.75) < 0.0001

    def test_handles_zero_vector(self):
        """Zero vector should remain zero vector."""
        vector = [0.0, 0.0, 0.0]
        result = _l2_normalize(vector)
        assert result == [0.0, 0.0, 0.0]

    def test_normalizes_high_dimensional_vector(self):
        """Should handle 768-dimensional vectors correctly."""
        vector = [1.0] * 768
        result = _l2_normalize(vector)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 0.0001
        assert len(result) == 768

    def test_norm_verification(self):
        """Verify L2 norm is in [0.99, 1.01] range."""
        # Test with various vectors
        test_vectors = [
            [1.0, 2.0, 3.0],
            [-1.0, 0.5, 2.0],
            [0.001, 0.002, 0.003],
            [100.0, 200.0, 300.0],
        ]
        for vec in test_vectors:
            result = _l2_normalize(vec)
            norm = math.sqrt(sum(x * x for x in result))
            assert 0.99 <= norm <= 1.01, f"Norm {norm} out of range for {vec}"


class TestFormatChunkForEmbedding:
    """Tests for _format_chunk_for_embedding function."""

    def test_formats_all_fields(self):
        """Should include doc name, file type, section, and text."""
        chunk = {
            "source": {
                "name": "paper.pdf",
                "file_type": "pdf",
            },
            "heading_path": ["Section 1", "Introduction"],
            "text": "This is the chunk text.",
        }
        result = _format_chunk_for_embedding(chunk)
        assert "[doc: paper.pdf]" in result
        assert "[type: pdf]" in result
        assert "[section: Section 1 > Introduction]" in result
        assert "This is the chunk text." in result

    def test_handles_empty_heading_path(self):
        """Should work without heading path."""
        chunk = {
            "source": {
                "name": "notes.md",
                "file_type": "text",
            },
            "heading_path": [],
            "text": "Some content.",
        }
        result = _format_chunk_for_embedding(chunk)
        assert "[doc: notes.md]" in result
        assert "[type: text]" in result
        assert "[section:" not in result
        assert "Some content." in result

    def test_handles_missing_source_fields(self):
        """Should gracefully handle missing source fields."""
        chunk = {
            "source": {},
            "heading_path": [],
            "text": "Just text.",
        }
        result = _format_chunk_for_embedding(chunk)
        assert result == "Just text."

    def test_handles_missing_source(self):
        """Should handle completely missing source."""
        chunk = {
            "text": "Only text here.",
        }
        result = _format_chunk_for_embedding(chunk)
        assert result == "Only text here."


class TestEmbedChunks:
    """Tests for embed_chunks function."""

    def test_yields_chunk_id_vector_error_tuples(self):
        """Should yield (chunk_id, vector, error) tuples."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.embedding = [1.0] * EMBEDDING_DIMENSION
        mock_response.data = [mock_embedding]
        mock_client.embeddings.create.return_value = mock_response

        chunks = [
            {
                "chunk_id": "abc123",
                "source": {"name": "test.pdf", "file_type": "pdf"},
                "heading_path": [],
                "text": "Test content.",
            }
        ]

        results = list(embed_chunks(chunks, mock_client))
        assert len(results) == 1
        chunk_id, vector, error = results[0]
        assert chunk_id == "abc123"
        assert vector is not None
        assert len(vector) == EMBEDDING_DIMENSION
        assert error is None

    def test_returns_error_on_api_failure(self):
        """Should return error tuple on API failure."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API error")

        chunks = [
            {
                "chunk_id": "fail123",
                "source": {},
                "heading_path": [],
                "text": "Test.",
            }
        ]

        results = list(embed_chunks(chunks, mock_client, batch_size=1))
        assert len(results) == 1
        chunk_id, vector, error = results[0]
        assert chunk_id == "fail123"
        assert vector is None
        assert "API error" in error

    def test_batching(self):
        """Should batch chunks according to batch_size."""
        mock_client = MagicMock()

        # Create response that returns embeddings for each call
        def create_response(*args, **kwargs):
            response = MagicMock()
            input_texts = kwargs.get("input", [])
            embeddings = []
            for _ in input_texts:
                emb = MagicMock()
                emb.embedding = [1.0] * EMBEDDING_DIMENSION
                embeddings.append(emb)
            response.data = embeddings
            return response

        mock_client.embeddings.create.side_effect = create_response

        # Create 5 chunks with batch_size=2
        chunks = [
            {"chunk_id": f"chunk_{i}", "source": {}, "heading_path": [], "text": f"Text {i}"}
            for i in range(5)
        ]

        results = list(embed_chunks(chunks, mock_client, batch_size=2))
        assert len(results) == 5
        # Should have made 3 API calls (2+2+1)
        assert mock_client.embeddings.create.call_count == 3

    def test_progress_callback(self):
        """Should call progress callback with processed and total counts."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.embedding = [1.0] * EMBEDDING_DIMENSION
        mock_response.data = [mock_embedding, mock_embedding]
        mock_client.embeddings.create.return_value = mock_response

        progress_calls = []

        def on_progress(processed, total):
            progress_calls.append((processed, total))

        chunks = [
            {"chunk_id": f"c{i}", "source": {}, "heading_path": [], "text": f"T{i}"}
            for i in range(4)
        ]

        list(embed_chunks(chunks, mock_client, batch_size=2, on_progress=on_progress))

        # Progress should be called after each batch
        assert (2, 4) in progress_calls
        assert (4, 4) in progress_calls

    def test_normalizes_vectors(self):
        """Should return L2-normalized vectors."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        # Non-normalized input
        mock_embedding.embedding = [3.0, 4.0] + [0.0] * (EMBEDDING_DIMENSION - 2)
        mock_response.data = [mock_embedding]
        mock_client.embeddings.create.return_value = mock_response

        chunks = [
            {"chunk_id": "norm_test", "source": {}, "heading_path": [], "text": "Test."}
        ]

        results = list(embed_chunks(chunks, mock_client))
        _, vector, _ = results[0]

        # Check L2 norm is ~1.0
        norm = math.sqrt(sum(x * x for x in vector))
        assert 0.99 <= norm <= 1.01


class TestEmbedQuery:
    """Tests for embed_query function."""

    def test_returns_normalized_vector(self):
        """Should return L2-normalized 768-dim vector."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.embedding = [1.0] * EMBEDDING_DIMENSION
        mock_response.data = [mock_embedding]
        mock_client.embeddings.create.return_value = mock_response

        result = embed_query("What is convolution?", mock_client)

        assert len(result) == EMBEDDING_DIMENSION
        norm = math.sqrt(sum(x * x for x in result))
        assert 0.99 <= norm <= 1.01

    def test_raises_on_failure(self):
        """Should raise RuntimeError on API failure."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("Connection failed")

        with pytest.raises(RuntimeError) as exc_info:
            embed_query("test query", mock_client)

        assert "Failed to embed query" in str(exc_info.value)


class TestGetEmbeddingClient:
    """Tests for get_embedding_client function."""

    def test_returns_client_and_model(self):
        """Should return (client, model_id) tuple."""
        mock_settings = MagicMock()
        mock_provider = MagicMock()
        mock_provider.api_key = "test-key"
        mock_provider.api_base_url = "https://api.test.com/v1"
        mock_settings.providers.get_default_provider.return_value = mock_provider

        with patch("flavia.content.indexer.embedder.OpenAI") as MockOpenAI:
            client, model = get_embedding_client(mock_settings)

            MockOpenAI.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.test.com/v1",
            )
            assert model == EMBEDDING_MODEL

    def test_falls_back_to_legacy_settings(self):
        """Should use legacy settings when no provider configured."""
        mock_settings = MagicMock()
        mock_settings.providers.get_default_provider.return_value = None
        mock_settings.api_key = "legacy-key"
        mock_settings.api_base_url = "https://legacy.api.com/v1"

        with patch("flavia.content.indexer.embedder.OpenAI") as MockOpenAI:
            client, model = get_embedding_client(mock_settings)

            MockOpenAI.assert_called_once_with(
                api_key="legacy-key",
                base_url="https://legacy.api.com/v1",
            )

    def test_raises_when_no_api_key(self):
        """Should raise ValueError when no API key configured."""
        mock_settings = MagicMock()
        mock_settings.providers.get_default_provider.return_value = None
        mock_settings.api_key = ""

        with pytest.raises(ValueError) as exc_info:
            get_embedding_client(mock_settings)

        assert "No API key configured" in str(exc_info.value)


class TestConstants:
    """Tests for module constants."""

    def test_embedding_model_constant(self):
        """Should have correct embedding model."""
        assert EMBEDDING_MODEL == "hf:nomic-ai/nomic-embed-text-v1.5"

    def test_embedding_dimension_constant(self):
        """Should have correct embedding dimension."""
        assert EMBEDDING_DIMENSION == 768

    def test_default_batch_size_constant(self):
        """Should have reasonable default batch size."""
        assert DEFAULT_BATCH_SIZE == 64
