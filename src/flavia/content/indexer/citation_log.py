"""Persistent citation log utilities for retrieval evidence markers."""

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional


CITATION_LOG_FILENAME = "rag_citations.jsonl"


def get_citation_log_path(base_dir: Path) -> Path:
    """Return project-local citation log path."""
    return base_dir / ".flavia" / CITATION_LOG_FILENAME


def append_citation_entries(base_dir: Path, entries: list[dict[str, Any]]) -> int:
    """Append citation entries to `.flavia/rag_citations.jsonl`.

    Returns number of entries written.
    """
    if not entries:
        return 0

    log_path = get_citation_log_path(base_dir)
    written = 0
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            for entry in entries:
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **entry,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
    except OSError:
        return 0
    return written


def read_recent_citation_entries(
    base_dir: Path,
    limit: int = 50,
    *,
    turn_id: Optional[str] = None,
    citation_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Read recent citation entries with optional filters."""
    if limit <= 0:
        return []

    log_path = get_citation_log_path(base_dir)
    if not log_path.exists():
        return []

    tail: deque[dict[str, Any]] = deque(maxlen=limit)
    citation_filter = (citation_id or "").strip()
    turn_filter = (turn_id or "").strip()

    try:
        with open(log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if citation_filter and str(payload.get("citation_id") or "") != citation_filter:
                    continue
                if turn_filter and str(payload.get("turn_id") or "") != turn_filter:
                    continue
                tail.append(payload)
    except OSError:
        return []

    return list(tail)
