"""Embed chunks and queries for semantic retrieval.

This module provides functions to embed document chunks and search queries
using the Synthetic provider's embedding API (hf:nomic-ai/nomic-embed-text-v1.5).
All vectors are L2-normalized before storage for cosine similarity via dot product.
"""

import math
import time
from typing import Callable, Iterator, Optional

import httpx
from openai import OpenAI

from flavia.config import Settings

# Constants
EMBEDDING_MODEL = "hf:nomic-ai/nomic-embed-text-v1.5"
EMBEDDING_DIMENSION = 768
DEFAULT_BATCH_SIZE = 64
MAX_RETRIES = 3


def _create_openai_client(
    api_key: str,
    base_url: str,
    headers: Optional[dict[str, str]] = None,
) -> OpenAI:
    """Create an OpenAI client with compatibility fallback."""
    kwargs = {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": httpx.Timeout(120.0, connect=10.0),
    }
    if headers:
        kwargs["default_headers"] = headers

    try:
        return OpenAI(**kwargs)
    except TypeError as exc:
        exc_str = str(exc)
        if (
            "proxies" not in exc_str
            and "default_headers" not in exc_str
            and "timeout" not in exc_str
        ):
            raise

        # Fallback for SDK/httpx incompatibilities.
        fallback_kwargs = {k: v for k, v in kwargs.items() if k != "default_headers"}
        return OpenAI(
            **fallback_kwargs,
            http_client=httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers=headers if headers else None,
            ),
        )


def _l2_normalize(vector: list[float]) -> list[float]:
    """Normalize a vector to unit length (L2 norm).

    Args:
        vector: Input vector as list of floats.

    Returns:
        L2-normalized vector. Returns zero vector if input has zero magnitude.
    """
    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude == 0:
        return vector
    return [x / magnitude for x in vector]


def _format_chunk_for_embedding(chunk: dict) -> str:
    """Format a chunk dict into the embedding input string.

    Uses the format: [doc: {name}] [type: {file_type}] [section: {section}]\\n{text}

    Args:
        chunk: Chunk dict with 'source', 'heading_path', and 'text' keys.

    Returns:
        Formatted string for embedding.
    """
    source = chunk.get("source", {})
    name = source.get("name", "")
    file_type = source.get("file_type", "")
    heading_path = chunk.get("heading_path", [])
    section = " > ".join(heading_path) if heading_path else ""
    text = chunk.get("text", "")

    parts = []
    if name:
        parts.append(f"[doc: {name}]")
    if file_type:
        parts.append(f"[type: {file_type}]")
    if section:
        parts.append(f"[section: {section}]")

    header = " ".join(parts)
    if header:
        return f"{header}\n{text}"
    return text


def _embed_batch_with_retry(
    texts: list[str],
    chunk_ids: list[str],
    client: OpenAI,
    model: str,
    max_retries: int = MAX_RETRIES,
) -> list[tuple[str, Optional[list[float]], Optional[str]]]:
    """Embed a batch of texts with exponential backoff retry.

    Args:
        texts: List of text strings to embed.
        chunk_ids: Corresponding chunk IDs.
        client: OpenAI client configured for embeddings.
        model: Model ID to use for embeddings.
        max_retries: Maximum number of retry attempts.

    Returns:
        List of tuples (chunk_id, vector, error). Vector is None if embedding failed.
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(model=model, input=texts)
            if len(response.data) != len(chunk_ids):
                raise RuntimeError(
                    f"Embedding API returned {len(response.data)} embeddings for "
                    f"{len(chunk_ids)} inputs"
                )

            results = []
            for i, embedding_data in enumerate(response.data):
                if len(embedding_data.embedding) != EMBEDDING_DIMENSION:
                    raise RuntimeError(
                        f"Embedding dimension mismatch for {chunk_ids[i]}: "
                        f"got {len(embedding_data.embedding)}, expected {EMBEDDING_DIMENSION}"
                    )
                vector = _l2_normalize(embedding_data.embedding)
                results.append((chunk_ids[i], vector, None))
            return results
        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Don't retry on auth/permission errors
            if any(code in error_str for code in ["401", "403", "400"]):
                break

            # Retry on rate limit, server errors, connection issues
            if any(
                marker in error_str
                for marker in ["429", "500", "502", "503", "timeout", "connection"]
            ):
                if attempt < max_retries - 1:
                    sleep_time = 2**attempt
                    time.sleep(sleep_time)
                    continue

            # Unknown error, don't retry
            break

    # All retries failed, return errors for all chunks in batch
    error_msg = str(last_error) if last_error else "Unknown error"
    return [(cid, None, error_msg) for cid in chunk_ids]


def get_embedding_client(settings: Settings) -> tuple[OpenAI, str]:
    """Get an OpenAI client configured for the embedding provider.

    Resolves the embedding model via the provider registry and returns
    a configured client.

    Args:
        settings: Application settings with provider configuration.

    Returns:
        Tuple of (OpenAI client, model_id).

    Raises:
        ValueError: If no suitable provider is configured for embeddings.
    """
    provider = None

    # Prefer a dedicated Synthetic provider when configured.
    if settings.providers.providers:
        synthetic_provider = settings.providers.get_provider("synthetic")
        if synthetic_provider and synthetic_provider.api_key:
            provider = synthetic_provider
        else:
            resolved_provider, _ = settings.providers.resolve_model(EMBEDDING_MODEL)
            if resolved_provider and resolved_provider.api_key:
                provider = resolved_provider
            else:
                default_provider = settings.providers.get_default_provider()
                if default_provider and default_provider.api_key:
                    provider = default_provider

    if provider and provider.api_key:
        client = _create_openai_client(
            api_key=provider.api_key,
            base_url=provider.api_base_url,
            headers=provider.headers if provider.headers else None,
        )
        return client, EMBEDDING_MODEL

    # Fall back to legacy settings
    if settings.api_key:
        client = _create_openai_client(
            api_key=settings.api_key,
            base_url=settings.api_base_url,
        )
        return client, EMBEDDING_MODEL

    raise ValueError(
        "No API key configured for embeddings. "
        "Set SYNTHETIC_API_KEY or configure a provider in providers.yaml."
    )


def _get_default_batch_size() -> int:
    """Get default batch size from settings."""
    try:
        from flavia.config import get_settings

        return get_settings().embedder_batch_size
    except Exception:
        return DEFAULT_BATCH_SIZE


def embed_chunks(
    chunks: list[dict],
    client: OpenAI,
    model: str = EMBEDDING_MODEL,
    batch_size: Optional[int] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Iterator[tuple[str, Optional[list[float]], Optional[str]]]:
    """Embed a list of chunks in batches.

    Args:
        chunks: List of chunk dicts with 'chunk_id', 'source', 'heading_path', 'text'.
        client: OpenAI client configured for embeddings.
        model: Model ID to use for embeddings.
        batch_size: Number of chunks to embed per API call. Uses settings default if None.
        on_progress: Optional callback(processed, total) for progress reporting.

    Yields:
        Tuples of (chunk_id, vector, error) where:
        - vector is the L2-normalized embedding (768 dims) or None on failure
        - error is None on success or an error message string on failure
    """
    if batch_size is None:
        batch_size = _get_default_batch_size()

    total = len(chunks)
    processed = 0

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [_format_chunk_for_embedding(c) for c in batch]
        chunk_ids = [c["chunk_id"] for c in batch]

        results = _embed_batch_with_retry(texts, chunk_ids, client, model)

        for result in results:
            yield result
            processed += 1

        if on_progress:
            on_progress(processed, total)


def embed_query(
    query: str,
    client: OpenAI,
    model: str = EMBEDDING_MODEL,
) -> list[float]:
    """Embed a search query.

    Args:
        query: Query string to embed.
        client: OpenAI client configured for embeddings.
        model: Model ID to use for embeddings.

    Returns:
        L2-normalized embedding vector (768 dimensions).

    Raises:
        RuntimeError: If embedding fails after retries.
    """
    results = _embed_batch_with_retry([query], ["query"], client, model)
    _chunk_id, vector, error = results[0]

    if error or vector is None:
        raise RuntimeError(f"Failed to embed query: {error}")

    return vector
