"""Index manager for building, updating, and querying the retrieval index.

This module provides high-level utilities for managing the retrieval index
that combines chunking, embedding, and both vector and full-text search
indexes.
"""

import time
import sqlite3
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from ..indexer import chunker, embedder, fts, vector_store
from flavia.config import Settings
from flavia.content.catalog import ContentCatalog


def _safe_resolve(base_dir: Path, path_value: str | Path) -> Path | None:
    """Resolve path_value under base_dir, rejecting traversal/outside paths."""
    candidate = path_value if isinstance(path_value, Path) else Path(path_value)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(base_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def load_catalog(base_dir: Path) -> ContentCatalog:
    """Load catalog from base_dir/.flavia/content_catalog.json.

    Args:
        base_dir: Vault base directory.

    Returns:
        Loaded ContentCatalog, or empty catalog if not found.
    """
    catalog_path = base_dir / ".flavia" / "content_catalog.json"
    if not catalog_path.exists():
        return ContentCatalog(base_dir)

    catalog = ContentCatalog.load(base_dir / ".flavia")
    if catalog is None:
        catalog = ContentCatalog(base_dir)

    return catalog


def get_entries_to_index(
    catalog: ContentCatalog, base_dir: Path, incremental: bool = False
) -> list[Any]:
    """Get catalog entries that have converted_to files.

    Args:
        catalog: ContentCatalog instance.
        incremental: If True, only return entries with status 'new' or 'modified'.

    Returns:
        List of catalog entries with converted_to paths, filtered by status
        if incremental=True.
    """
    entries = []

    for entry in catalog.files.values():
        if not entry.converted_to:
            continue

        if entry.status == "missing":
            continue

        if incremental and entry.status not in ("new", "modified"):
            continue

        converted_path = _safe_resolve(base_dir, entry.converted_to)
        if converted_path is None or not converted_path.exists():
            continue

        entries.append(entry)

    return entries


def _stale_converted_paths(catalog: ContentCatalog, base_dir: Path) -> list[str]:
    """List converted paths whose old chunks must be purged on incremental updates."""
    base_resolved = base_dir.resolve()
    stale_paths: set[str] = set()

    for entry in catalog.files.values():
        if entry.status not in ("modified", "missing"):
            continue
        if not entry.converted_to:
            continue

        converted_path = _safe_resolve(base_dir, entry.converted_to)
        if converted_path is None:
            continue

        try:
            stale_paths.add(str(converted_path.relative_to(base_resolved)))
        except ValueError:
            stale_paths.add(str(converted_path))

    return sorted(stale_paths)


def _save_catalog_after_update(catalog: ContentCatalog, base_dir: Path, console: Console) -> None:
    """Persist catalog state after index update to keep statuses in sync."""
    try:
        catalog.mark_all_current()
        catalog.save(base_dir / ".flavia")
    except Exception as e:
        console.print(f"[yellow]Warning: failed to save updated catalog state: {e}[/yellow]")


def clear_index(base_dir: Path, console: Console) -> tuple[int, int]:
    """Clear all chunks from vector store and FTS index.

    Args:
        base_dir: Vault base directory.
        console: Rich console for output.

    Returns:
        Tuple of (chunks_deleted_from_vector, chunks_deleted_from_fts).
    """
    total_vector_deleted = 0
    total_fts_deleted = 0

    with vector_store.VectorStore(base_dir) as vs:
        existing_chunk_ids = vs.get_existing_chunk_ids()
        if existing_chunk_ids:
            deleted = vs.delete_chunks(list(existing_chunk_ids))
            total_vector_deleted = deleted
            console.print(f"[yellow]Deleted {deleted} chunks from vector store[/yellow]")

    with fts.FTSIndex(base_dir) as fts_idx:
        existing_chunk_ids = fts_idx.get_existing_chunk_ids()
        if existing_chunk_ids:
            deleted = fts_idx.delete_chunks(list(existing_chunk_ids))
            total_fts_deleted = deleted
            console.print(f"[yellow]Deleted {deleted} chunks from FTS index[/yellow]")

    return total_vector_deleted, total_fts_deleted


def process_document(
    entry,
    base_dir: Path,
    settings: Settings,
    vector_store: vector_store.VectorStore,
    fts_index: fts.FTSIndex,
    existing_chunk_ids: set[str],
    console: Console,
    show_progress: bool = True,
) -> dict[str, int]:
    """Chunk, embed, and index a single document.

    Args:
        entry: Catalog entry for the document.
        base_dir: Vault base directory.
        settings: Application settings for embedding client.
        vector_store: VectorStore instance.
        fts_index: FTSIndex instance.
        existing_chunk_ids: Set of chunk IDs already in the index.
        console: Rich console for output.
        show_progress: Whether to show progress per document.

    Returns:
        Dict with counts: chunks_added, chunks_updated, chunks_skipped.
    """
    doc_started = time.perf_counter()
    stats = {"added": 0, "updated": 0, "skipped": 0, "chunked": 0, "embed_failed": 0}

    chunks = chunker.chunk_document(
        entry,
        base_dir,
        chunk_min_tokens=settings.rag_chunk_min_tokens,
        chunk_max_tokens=settings.rag_chunk_max_tokens,
        video_window_seconds=settings.rag_video_window_seconds,
    )
    stats["chunked"] = len(chunks)
    if not chunks:
        stats["duration_ms"] = int((time.perf_counter() - doc_started) * 1000)
        return stats

    client, model = embedder.get_embedding_client(settings)

    new_chunks: list[dict[str, Any]] = []
    seen_new_chunk_ids: set[str] = set()

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")

        if not chunk_id:
            stats["skipped"] += 1
            continue
        if chunk_id in existing_chunk_ids or chunk_id in seen_new_chunk_ids:
            stats["skipped"] += 1
        else:
            new_chunks.append(chunk)
            seen_new_chunk_ids.add(chunk_id)

    if not new_chunks:
        return stats

    if show_progress:
        console.print(f"  [dim]Embedding {len(new_chunks)} chunks...[/dim]")

    embeddings = embedder.embed_chunks(new_chunks, client, model)
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in new_chunks}

    vector_items = []
    fts_chunks = []
    failed_chunk_ids: list[str] = []
    successful_chunk_ids: list[str] = []

    for chunk_id, vector, error in embeddings:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            failed_chunk_ids.append(chunk_id)
            continue
        if error or vector is None:
            failed_chunk_ids.append(chunk_id)
            continue

        source = chunk.get("source", {})
        successful_chunk_ids.append(chunk_id)

        vector_items.append(
            (
                chunk_id,
                vector,
                {
                    "doc_id": chunk.get("doc_id", ""),
                    "modality": chunk.get("modality", ""),
                    "converted_path": source.get("converted_path", ""),
                    "locator": source.get("locator", {}),
                    "heading_path": chunk.get("heading_path", []),
                    "doc_name": source.get("name", ""),
                    "file_type": source.get("file_type", ""),
                },
            )
        )

        fts_chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": chunk.get("doc_id", ""),
                "modality": chunk.get("modality", ""),
                "text": chunk.get("text", ""),
                "heading_path": chunk.get("heading_path", []),
            }
        )

    if failed_chunk_ids:
        stats["skipped"] += len(failed_chunk_ids)
        stats["embed_failed"] += len(failed_chunk_ids)
        preview = ", ".join(failed_chunk_ids[:5])
        if len(failed_chunk_ids) > 5:
            preview += f", ... (+{len(failed_chunk_ids) - 5} more)"
        console.print(
            "[yellow]Warning: failed to embed "
            f"{len(failed_chunk_ids)} chunk(s) for {entry.name}: {preview}[/yellow]"
        )

    if not vector_items:
        stats["duration_ms"] = int((time.perf_counter() - doc_started) * 1000)
        return stats

    vector_inserted, vector_updated = vector_store.upsert(vector_items)
    fts_inserted, fts_updated = fts_index.upsert(fts_chunks)
    existing_chunk_ids.update(successful_chunk_ids)

    if vector_inserted != fts_inserted or vector_updated != fts_updated:
        console.print(
            "[yellow]Warning: vector/FTS upsert counts diverged; "
            f"vector=({vector_inserted} added, {vector_updated} updated), "
            f"fts=({fts_inserted} added, {fts_updated} updated)[/yellow]"
        )

    stats["added"] = vector_inserted
    stats["updated"] = vector_updated
    stats["duration_ms"] = int((time.perf_counter() - doc_started) * 1000)

    return stats


def build_index(
    base_dir: Path, settings: Settings, console: Console, force: bool = False
) -> dict[str, Any]:
    """Full rebuild: rechunk and re-embed all converted documents.

    Args:
        base_dir: Vault base directory.
        settings: Application settings.
        console: Rich console for output.
        force: Skip confirmation prompt.

    Returns:
        Dict with build statistics.
    """
    start_time = time.time()

    if not force:
        console.print(
            "[yellow]This will clear the existing index and rebuild from all converted "
            "documents.[/yellow]"
        )
        console.print("Continue? [y/N] ", end="")
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return {"cancelled": True}

        if answer not in ("y", "yes"):
            console.print("[yellow]Build cancelled.[/yellow]")
            return {"cancelled": True}

    console.print("[cyan]Loading catalog...[/cyan]")
    catalog = load_catalog(base_dir)

    if not catalog.files:
        console.print("[yellow]No files found in catalog.[/yellow]")
        return {
            "documents_processed": 0,
            "chunks_indexed": 0,
            "duration_seconds": time.time() - start_time,
        }

    entries = get_entries_to_index(catalog, base_dir, incremental=False)

    if not entries:
        console.print("[yellow]No files with converted content found.[/yellow]")
        return {
            "documents_processed": 0,
            "chunks_indexed": 0,
            "duration_seconds": time.time() - start_time,
        }

    console.print(f"[cyan]Found {len(entries)} documents with converted content[/cyan]")
    if settings.rag_debug:
        console.print(
            "[dim]RAG debug: "
            f"chunk_min_tokens={settings.rag_chunk_min_tokens}, "
            f"chunk_max_tokens={settings.rag_chunk_max_tokens}, "
            f"video_window_s={settings.rag_video_window_seconds}[/dim]"
        )

    console.print("[cyan]Clearing existing index...[/cyan]")
    clear_index(base_dir, console)

    console.print("[cyan]Building index...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing documents...", total=len(entries))

        total_chunks = 0
        total_added = 0
        total_updated = 0

        with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
            existing_chunk_ids = set()

            for entry in entries:
                progress.update(task, description=f"[cyan]Processing: {entry.name}")

                stats = process_document(
                    entry,
                    base_dir,
                    settings,
                    vs,
                    fts_idx,
                    existing_chunk_ids,
                    console,
                    show_progress=False,
                )

                total_chunks += stats["added"] + stats["updated"] + stats["skipped"]
                total_added += stats["added"]
                total_updated += stats["updated"]
                if settings.rag_debug:
                    console.print(
                        "[dim]  "
                        f"{entry.name}: chunked={stats.get('chunked', 0)}, "
                        f"added={stats['added']}, updated={stats['updated']}, "
                        f"skipped={stats['skipped']}, embed_failed={stats.get('embed_failed', 0)}, "
                        f"duration={stats.get('duration_ms', 0)}ms[/dim]"
                    )

                progress.update(task, advance=1)

    duration = time.time() - start_time

    return {
        "documents_processed": len(entries),
        "chunks_indexed": total_chunks,
        "chunks_added": total_added,
        "chunks_updated": total_updated,
        "duration_seconds": duration,
        "cancelled": False,
    }


def update_index(base_dir: Path, settings: Settings, console: Console) -> dict[str, Any]:
    """Incremental update: only new/modified docs detected by checksum.

    Args:
        base_dir: Vault base directory.
        settings: Application settings.
        console: Rich console for output.

    Returns:
        Dict with update statistics.
    """
    start_time = time.time()

    console.print("[cyan]Loading catalog...[/cyan]")
    catalog = load_catalog(base_dir)

    if not catalog.files:
        console.print("[yellow]No files found in catalog.[/yellow]")
        return {
            "documents_processed": 0,
            "chunks_added": 0,
            "chunks_updated": 0,
            "chunks_removed": 0,
            "duration_seconds": time.time() - start_time,
        }

    console.print("[cyan]Checking for new or modified files...[/cyan]")
    update_summary = catalog.update()

    new_count = update_summary["counts"]["new"]
    modified_count = update_summary["counts"]["modified"]
    missing_count = update_summary["counts"]["missing"]

    if new_count > 0:
        console.print(f"[green]New documents: {new_count}[/green]")
    if modified_count > 0:
        console.print(f"[yellow]Modified documents: {modified_count}[/yellow]")
    if missing_count > 0:
        console.print(f"[red]Missing documents: {missing_count}[/red]")

    entries = get_entries_to_index(catalog, base_dir, incremental=True)

    chunks_removed = 0

    with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
        existing_chunk_ids = vs.get_existing_chunk_ids()

        stale_paths = _stale_converted_paths(catalog, base_dir)
        if stale_paths:
            stale_chunk_ids = vs.get_chunk_ids_by_converted_paths(stale_paths)
            if stale_chunk_ids:
                deleted_vector = vs.delete_chunks(list(stale_chunk_ids))
                deleted_fts = fts_idx.delete_chunks(list(stale_chunk_ids))
                chunks_removed = max(deleted_vector, deleted_fts)
                existing_chunk_ids.difference_update(stale_chunk_ids)
                console.print(
                    f"[yellow]Removed {chunks_removed} stale chunks for modified/missing "
                    "files[/yellow]"
                )

        if not entries:
            console.print("[green]No new or modified documents to index.[/green]")
            vs_stats = vs.get_stats()
            _save_catalog_after_update(catalog, base_dir, console)
            return {
                "documents_processed": 0,
                "chunks_added": 0,
                "chunks_updated": 0,
                "chunks_removed": chunks_removed,
                "chunk_count": vs_stats["chunk_count"],
                "duration_seconds": time.time() - start_time,
            }

        console.print(f"[cyan]Found {len(entries)} documents to process[/cyan]")
        if settings.rag_debug:
            console.print(
                "[dim]RAG debug: "
                f"chunk_min_tokens={settings.rag_chunk_min_tokens}, "
                f"chunk_max_tokens={settings.rag_chunk_max_tokens}, "
                f"video_window_s={settings.rag_video_window_seconds}[/dim]"
            )
        console.print("[cyan]Updating index...[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Processing documents...", total=len(entries))

            total_added = 0
            total_updated = 0

            for entry in entries:
                progress.update(task, description=f"[cyan]Processing: {entry.name}")

                stats = process_document(
                    entry,
                    base_dir,
                    settings,
                    vs,
                    fts_idx,
                    existing_chunk_ids,
                    console,
                    show_progress=False,
                )

                total_added += stats["added"]
                total_updated += stats["updated"]
                if settings.rag_debug:
                    console.print(
                        "[dim]  "
                        f"{entry.name}: chunked={stats.get('chunked', 0)}, "
                        f"added={stats['added']}, updated={stats['updated']}, "
                        f"skipped={stats['skipped']}, embed_failed={stats.get('embed_failed', 0)}, "
                        f"duration={stats.get('duration_ms', 0)}ms[/dim]"
                    )

                progress.update(task, advance=1)

    _save_catalog_after_update(catalog, base_dir, console)

    return {
        "documents_processed": len(entries),
        "chunks_added": total_added,
        "chunks_updated": total_updated,
        "chunks_removed": chunks_removed,
        "duration_seconds": time.time() - start_time,
    }


def show_index_stats(base_dir: Path, console: Console) -> None:
    """Show index statistics: chunk count, vector count, index DB size, last updated.

    Args:
        base_dir: Vault base directory.
        console: Rich console for output.
    """
    index_dir = base_dir / ".index"
    index_db_path = index_dir / "index.db"

    if not index_db_path.exists():
        console.print(
            "[red]No index found. Run /index build (or /index-build) to create one.[/red]"
        )
        return

    try:
        with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
            vs_stats = vs.get_stats()
            fts_stats = fts_idx.get_stats()

        table = Table(title="[bold]Index Statistics[/bold]", show_header=False)
        table.add_column("", justify="left")
        table.add_column("", justify="right")

        table.add_row("Vector chunks:", f"[cyan]{vs_stats['chunk_count']:,}[/cyan]")
        table.add_row("FTS chunks:", f"[cyan]{fts_stats['chunk_count']:,}[/cyan]")
        table.add_row("Documents:", f"[cyan]{vs_stats['doc_count']:,}[/cyan]")

        if vs_stats.get("last_indexed_at"):
            table.add_row("Last indexed:", f"[dim]{vs_stats['last_indexed_at']}[/dim]")

        db_size_mb = vs_stats["db_size_bytes"] / (1024 * 1024)
        table.add_row("Index size:", f"[cyan]{db_size_mb:.2f} MB[/cyan]")

        vs_modalities = ", ".join(sorted(vs_stats["modalities"]))
        if vs_modalities:
            table.add_row("Modalities:", f"[dim]{vs_modalities}[/dim]")

        table.add_row()
        table.add_row("Index location:", f"[dim]{index_db_path}[/dim]")

        console.print(table)

        if vs_stats["chunk_count"] != fts_stats["chunk_count"]:
            console.print(
                f"[yellow]Warning: Vector chunk count ({vs_stats['chunk_count']}) != "
                f"FTS chunk count ({fts_stats['chunk_count']})[/yellow]"
            )

    except Exception as e:
        console.print(f"[red]Error reading index: {e}[/red]")


def show_index_diagnostics(base_dir: Path, settings: Settings, console: Console) -> None:
    """Show detailed RAG diagnostics for tuning and troubleshooting."""
    index_db_path = base_dir / ".index" / "index.db"
    if not index_db_path.exists():
        console.print(
            "[red]No index found. Run /index build (or /index-build) to create one.[/red]"
        )
        return

    try:
        with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
            vs_stats = vs.get_stats()
            fts_stats = fts_idx.get_stats()

        defaults = chunker.get_chunking_defaults()
        config_table = Table(title="[bold]RAG Runtime Configuration[/bold]", show_header=False)
        config_table.add_column("", justify="left")
        config_table.add_column("", justify="right")
        config_table.add_row("RAG debug mode:", f"[cyan]{bool(settings.rag_debug)}[/cyan]")
        config_table.add_row("Embedding model:", f"[cyan]{embedder.EMBEDDING_MODEL}[/cyan]")
        config_table.add_row("Embedding dimension:", f"[cyan]{embedder.EMBEDDING_DIMENSION}[/cyan]")
        config_table.add_row(
            "Chunk min/max tokens:",
            f"[cyan]{settings.rag_chunk_min_tokens}/{settings.rag_chunk_max_tokens}[/cyan]",
        )
        config_table.add_row(
            "Video window (seconds):", f"[cyan]{settings.rag_video_window_seconds}[/cyan]"
        )
        config_table.add_row(
            "Retrieval params:",
            "[cyan]"
            f"router_k={settings.rag_catalog_router_k}, "
            f"vector_k={settings.rag_vector_k}, "
            f"fts_k={settings.rag_fts_k}, "
            f"rrf_k={settings.rag_rrf_k}, "
            f"max_chunks_per_doc={settings.rag_max_chunks_per_doc}"
            "[/cyan]",
        )
        config_table.add_row(
            "Expand video temporal:",
            f"[cyan]{bool(settings.rag_expand_video_temporal)}[/cyan]",
        )
        config_table.add_row(
            "Chunk defaults (code):",
            "[dim]"
            f"{defaults['chunk_min_tokens']}-{defaults['chunk_max_tokens']} tokens, "
            f"window={defaults['video_window_seconds']}s"
            "[/dim]",
        )
        console.print(config_table)

        health_table = Table(title="[bold]Index Health[/bold]", show_header=False)
        health_table.add_column("", justify="left")
        health_table.add_column("", justify="right")
        health_table.add_row("Vector chunks:", f"[cyan]{vs_stats['chunk_count']:,}[/cyan]")
        health_table.add_row("FTS chunks:", f"[cyan]{fts_stats['chunk_count']:,}[/cyan]")
        health_table.add_row("Documents:", f"[cyan]{vs_stats['doc_count']:,}[/cyan]")
        health_table.add_row(
            "Chunk parity:",
            "[green]OK[/green]"
            if vs_stats["chunk_count"] == fts_stats["chunk_count"]
            else "[yellow]MISMATCH[/yellow]",
        )
        if vs_stats.get("last_indexed_at"):
            health_table.add_row("Last indexed:", f"[dim]{vs_stats['last_indexed_at']}[/dim]")
        console.print(health_table)

        with sqlite3.connect(index_db_path) as conn:
            conn.row_factory = sqlite3.Row
            modality_rows = conn.execute(
                """
                SELECT
                    m.modality AS modality,
                    COUNT(*) AS chunk_count,
                    AVG(LENGTH(f.text)) AS avg_chars,
                    MIN(LENGTH(f.text)) AS min_chars,
                    MAX(LENGTH(f.text)) AS max_chars
                FROM chunks_meta m
                JOIN chunks_fts f ON m.chunk_id = f.chunk_id
                GROUP BY m.modality
                ORDER BY chunk_count DESC, modality ASC
                """
            ).fetchall()

            top_doc_rows = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(doc_name, ''), '(unknown)') AS doc_name,
                    COALESCE(NULLIF(file_type, ''), '(unknown)') AS file_type,
                    COUNT(*) AS chunk_count
                FROM chunks_meta
                GROUP BY doc_name, file_type
                ORDER BY chunk_count DESC, doc_name ASC
                LIMIT 12
                """
            ).fetchall()

        if modality_rows:
            modality_table = Table(title="[bold]Chunk Distribution by Modality[/bold]")
            modality_table.add_column("Modality")
            modality_table.add_column("Chunks", justify="right")
            modality_table.add_column("Avg chars", justify="right")
            modality_table.add_column("Min chars", justify="right")
            modality_table.add_column("Max chars", justify="right")
            modality_table.add_column("Avg tokens", justify="right")
            for row in modality_rows:
                avg_chars = float(row["avg_chars"] or 0.0)
                avg_tokens = int(round(avg_chars / 4.0)) if avg_chars > 0 else 0
                modality_table.add_row(
                    str(row["modality"] or "(unknown)"),
                    f"{int(row['chunk_count']):,}",
                    f"{int(round(avg_chars)):,}",
                    f"{int(row['min_chars'] or 0):,}",
                    f"{int(row['max_chars'] or 0):,}",
                    f"{avg_tokens:,}",
                )
            console.print(modality_table)

        if top_doc_rows:
            doc_table = Table(title="[bold]Top Documents by Chunk Count[/bold]")
            doc_table.add_column("Document")
            doc_table.add_column("Type")
            doc_table.add_column("Chunks", justify="right")
            for row in top_doc_rows:
                doc_table.add_row(
                    str(row["doc_name"]),
                    str(row["file_type"]),
                    f"{int(row['chunk_count']):,}",
                )
            console.print(doc_table)

        hints: list[str] = []
        if vs_stats["chunk_count"] == 0:
            hints.append("Index is empty. Run /index build.")
        if settings.rag_chunk_min_tokens >= settings.rag_chunk_max_tokens:
            hints.append("Chunk min/max tokens are inverted or equal; review RAG_CHUNK_* envs.")
        if vs_stats["chunk_count"] != fts_stats["chunk_count"]:
            hints.append("Vector/FTS chunk counts diverge; run /index build to resync.")
        if settings.rag_vector_k == 0 and settings.rag_fts_k == 0:
            hints.append("Both RAG_VECTOR_K and RAG_FTS_K are 0; retrieval will always be empty.")

        if hints:
            console.print("[bold yellow]Tuning Hints[/bold yellow]")
            for hint in hints:
                console.print(f"- {hint}")

    except Exception as e:
        console.print(f"[red]Error reading index diagnostics: {e}[/red]")


def format_duration(seconds: float) -> str:
    """Convert seconds to human-readable duration.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string (e.g. "2m 34s", "45s").
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def display_build_results(results: dict[str, Any], console: Console) -> None:
    """Display build/update results in a formatted panel.

    Args:
        results: Results dict from build_index or update_index.
        console: Rich console for output.
    """
    if results.get("cancelled"):
        return

    duration_str = format_duration(results["duration_seconds"])

    if "chunks_indexed" in results:
        content = [
            f"Documents processed: [cyan]{results['documents_processed']}[/cyan]",
            f"Chunks indexed: [cyan]{results['chunks_indexed']:,}[/cyan]",
            f"Duration: [cyan]{duration_str}[/cyan]",
        ]
    else:
        content = [
            f"Documents processed: [cyan]{results['documents_processed']}[/cyan]",
            f"Chunks added: [cyan]{results.get('chunks_added', 0):,}[/cyan]",
            f"Chunks updated: [cyan]{results.get('chunks_updated', 0):,}[/cyan]",
            f"Chunks removed: [cyan]{results.get('chunks_removed', 0):,}[/cyan]",
            f"Duration: [cyan]{duration_str}[/cyan]",
        ]

    panel_title = (
        "[bold]Index Build[/bold]" if "chunks_indexed" in results else "[bold]Index Update[/bold]"
    )
    panel = Panel("\n".join(content), title=panel_title, border_style="green")

    console.print(panel)
