"""Semantic retrieval & RAG pipeline for flavIA (Area 11).

Public API (grows as tasks are completed):
  build_index(base_dir, settings)   — Task 11.7+ (not yet implemented)
  update_index(base_dir, settings)  — Task 11.7+ (not yet implemented)
  retrieve(question, base_dir, ...) — Task 11.4 ✓

Currently implemented:
  chunker.chunk_document(entry, base_dir) — Task 11.1 ✓
  embedder.embed_chunks(...), embed_query(...) — Task 11.2 ✓
  vector_store.VectorStore — Task 11.2 ✓
  fts.FTSIndex — Task 11.3 ✓
"""

from .chunker import chunk_document, chunk_text_document, chunk_video_document
from .embedder import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    embed_chunks,
    embed_query,
    get_embedding_client,
)
from .fts import FTSIndex
from .retrieval import retrieve
from .vector_store import VectorStore

__all__ = [
    # Chunker (11.1)
    "chunk_document",
    "chunk_text_document",
    "chunk_video_document",
    # Embedder (11.2)
    "embed_chunks",
    "embed_query",
    "get_embedding_client",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    # Vector Store (11.2)
    "VectorStore",
    # FTS Index (11.3)
    "FTSIndex",
    # Hybrid Retrieval (11.4)
    "retrieve",
]
