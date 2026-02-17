from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from flavia.config.settings import Settings
from flavia.content.indexer import index_manager


def _console() -> Console:
    return Console(file=StringIO(), force_terminal=False, color_system=None)


def test_get_entries_to_index_resolves_paths_and_filters(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()
    (converted_dir / "current.md").write_text("ok")
    (converted_dir / "new.md").write_text("ok")
    outside_path = tmp_path.parent / "outside.md"
    outside_path.write_text("secret")

    current_entry = SimpleNamespace(converted_to=".converted/current.md", status="current")
    new_entry = SimpleNamespace(converted_to=".converted/new.md", status="new")
    missing_entry = SimpleNamespace(converted_to=".converted/missing.md", status="current")
    deleted_entry = SimpleNamespace(converted_to=".converted/current.md", status="missing")
    traversal_entry = SimpleNamespace(converted_to="../outside.md", status="current")

    catalog = SimpleNamespace(
        files={
            "a": current_entry,
            "b": new_entry,
            "c": missing_entry,
            "d": deleted_entry,
            "e": traversal_entry,
        }
    )

    all_entries = index_manager.get_entries_to_index(catalog, tmp_path, incremental=False)
    inc_entries = index_manager.get_entries_to_index(catalog, tmp_path, incremental=True)

    assert all_entries == [current_entry, new_entry]
    assert inc_entries == [new_entry]


def test_update_index_calls_catalog_update_once_and_saves(monkeypatch, tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()
    (converted_dir / "doc.md").write_text("content")

    entry = SimpleNamespace(name="doc.pdf", converted_to=".converted/doc.md", status="new")

    class FakeCatalog:
        def __init__(self):
            self.files = {"doc.pdf": entry}
            self.update_calls = 0
            self.mark_current_called = False
            self.save_path = None

        def update(self):
            self.update_calls += 1
            return {
                "counts": {"new": 1, "modified": 0, "missing": 0, "unchanged": 0},
                "new": ["doc.pdf"],
                "modified": [],
                "missing": [],
                "unchanged": [],
            }

        def mark_all_current(self):
            self.mark_current_called = True

        def save(self, path):
            self.save_path = path

    class FakeVectorStore:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get_existing_chunk_ids(self):
            return set()

        def get_chunk_ids_by_converted_paths(self, converted_paths):
            return set()

        def delete_chunks(self, chunk_ids):
            return len(chunk_ids)

        def get_stats(self):
            return {"chunk_count": 0}

    class FakeFTSIndex:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def delete_chunks(self, chunk_ids):
            return len(chunk_ids)

    catalog = FakeCatalog()
    monkeypatch.setattr(index_manager, "load_catalog", lambda _base_dir: catalog)
    monkeypatch.setattr(index_manager.vector_store, "VectorStore", FakeVectorStore)
    monkeypatch.setattr(index_manager.fts, "FTSIndex", FakeFTSIndex)
    monkeypatch.setattr(
        index_manager,
        "process_document",
        lambda *args, **kwargs: {"added": 1, "updated": 0, "skipped": 0},
    )

    result = index_manager.update_index(tmp_path, Settings(base_dir=tmp_path), _console())

    assert result["documents_processed"] == 1
    assert result["chunks_added"] == 1
    assert result["chunks_removed"] == 0
    assert catalog.update_calls == 1
    assert catalog.mark_current_called is True
    assert catalog.save_path == tmp_path / ".flavia"


def test_update_index_removes_stale_chunks_for_modified_and_missing(monkeypatch, tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()
    (converted_dir / "doc.md").write_text("content")

    modified_entry = SimpleNamespace(
        name="doc.pdf",
        converted_to=".converted/doc.md",
        status="modified",
    )
    missing_entry = SimpleNamespace(
        name="old.pdf", converted_to=".converted/old.md", status="missing"
    )

    class FakeCatalog:
        def __init__(self):
            self.files = {"doc.pdf": modified_entry, "old.pdf": missing_entry}

        def update(self):
            return {
                "counts": {"new": 0, "modified": 1, "missing": 1, "unchanged": 0},
                "new": [],
                "modified": ["doc.pdf"],
                "missing": ["old.pdf"],
                "unchanged": [],
            }

        def mark_all_current(self):
            return None

        def save(self, path):
            return None

    class FakeVectorStore:
        last = None

        def __init__(self, base_dir):
            self.base_dir = base_dir
            self.paths_seen = []
            FakeVectorStore.last = self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get_existing_chunk_ids(self):
            return {"chunk_a", "chunk_b", "chunk_c"}

        def get_chunk_ids_by_converted_paths(self, converted_paths):
            self.paths_seen = list(converted_paths)
            return {"chunk_a", "chunk_b"}

        def delete_chunks(self, chunk_ids):
            return len(chunk_ids)

        def get_stats(self):
            return {"chunk_count": 1}

    class FakeFTSIndex:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def delete_chunks(self, chunk_ids):
            return len(chunk_ids)

    monkeypatch.setattr(index_manager, "load_catalog", lambda _base_dir: FakeCatalog())
    monkeypatch.setattr(index_manager.vector_store, "VectorStore", FakeVectorStore)
    monkeypatch.setattr(index_manager.fts, "FTSIndex", FakeFTSIndex)
    monkeypatch.setattr(
        index_manager,
        "process_document",
        lambda *args, **kwargs: {"added": 0, "updated": 0, "skipped": 0},
    )

    result = index_manager.update_index(tmp_path, Settings(base_dir=tmp_path), _console())

    assert result["chunks_removed"] == 2
    assert result["documents_processed"] == 1
    assert sorted(FakeVectorStore.last.paths_seen) == [".converted/doc.md", ".converted/old.md"]
