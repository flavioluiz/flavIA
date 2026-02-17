"""Tests for retrieval citation log utilities."""

from pathlib import Path

from flavia.content.indexer.citation_log import (
    append_citation_entries,
    get_citation_log_path,
    read_recent_citation_entries,
)


def test_append_and_read_recent_citation_entries(tmp_path: Path):
    written = append_citation_entries(
        tmp_path,
        [
            {
                "citation_id": "C-main-0001",
                "turn_id": "turn-000001-aaaaaa",
                "doc_name": "a.pdf",
                "locator": {"line_start": 1, "line_end": 2},
                "excerpt": "alpha",
            },
            {
                "citation_id": "C-main-0002",
                "turn_id": "turn-000002-bbbbbb",
                "doc_name": "b.pdf",
                "locator": {"line_start": 10, "line_end": 20},
                "excerpt": "beta",
            },
        ],
    )
    assert written == 2
    assert get_citation_log_path(tmp_path).exists()

    recent = read_recent_citation_entries(tmp_path, limit=1)
    assert len(recent) == 1
    assert recent[0]["citation_id"] == "C-main-0002"


def test_read_recent_citation_entries_filters_by_turn_and_id(tmp_path: Path):
    append_citation_entries(
        tmp_path,
        [
            {
                "citation_id": "C-main-0001",
                "turn_id": "turn-000010-xxxxxx",
                "doc_name": "a.pdf",
                "locator": {},
                "excerpt": "alpha",
            },
            {
                "citation_id": "C-main-0002",
                "turn_id": "turn-000011-yyyyyy",
                "doc_name": "b.pdf",
                "locator": {},
                "excerpt": "beta",
            },
        ],
    )

    by_turn = read_recent_citation_entries(tmp_path, limit=10, turn_id="turn-000011-yyyyyy")
    assert len(by_turn) == 1
    assert by_turn[0]["citation_id"] == "C-main-0002"

    by_id = read_recent_citation_entries(tmp_path, limit=10, citation_id="C-main-0001")
    assert len(by_id) == 1
    assert by_id[0]["turn_id"] == "turn-000010-xxxxxx"
