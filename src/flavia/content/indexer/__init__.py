"""Semantic retrieval & RAG pipeline for flavIA (Area 11).

Public API (grows as tasks are completed):
  build_index(base_dir, settings)   — Task 11.2+ (not yet implemented)
  update_index(base_dir, settings)  — Task 11.2+ (not yet implemented)
  retrieve(question, base_dir, ...) — Task 11.4+ (not yet implemented)

Currently implemented:
  chunker.chunk_document(entry, base_dir) — Task 11.1 ✓
"""

from .chunker import chunk_document, chunk_text_document, chunk_video_document

__all__ = [
    "chunk_document",
    "chunk_text_document",
    "chunk_video_document",
]
