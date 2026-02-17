"""Index manager for building, updating, and querying the retrieval index.

This module provides high-level utilities for managing the retrieval index
that combines chunking, embedding, and both vector and full-text search
indexes.
"""

import time
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

from flavia.config import Settings
from flavia.content.catalog import ContentCatalog
from ..indexer import chunker, embedder, fts, vector_store


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


def get_entries_to_index(catalog: ContentCatalog, incremental: bool = False) -> list[Any]:
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

        converted_path = base_dir = Path(entry.converted_to)
        if isinstance(entry.converted_to, str):
            converted_path = base_dir = entry.converted_to

        entry_path = base_dir / entry.converted_to
        if not entry_path.exists():
            continue

        entries.append(entry)

    return entries


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
    stats = {"added": 0, "updated": 0, "skipped": 0}

    chunks = chunker.chunk_document(entry, base_dir)
    if not chunks:
        return stats

    client, model = embedder.get_embedding_client(settings)

    new_chunks = []
    chunks_to_embed = []

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")

        if chunk_id in existing_chunk_ids:
            stats["skipped"] += 1
        else:
            new_chunks.append(chunk)
            chunks_to_embed.append(chunk.get("text", ""))
            existing_chunk_ids.add(chunk_id)

    if not chunks_to_embed:
        return stats

    if show_progress:
        console.print(f"  [dim]Embedding {len(chunks_to_embed)} chunks...[/dim]")

    embeddings = embedder.embed_chunks(chunks_to_embed, client, model)

    vector_items = []
    fts_chunks = []

    for chunk, vector in zip(new_chunks, embeddings):
        chunk_id = chunk["chunk_id"]
        source = chunk.get("source", {})

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

    vector_inserted, vector_updated = vector_store.upsert(vector_items)
    fts_inserted, fts_updated = fts_index.upsert(fts_chunks)

    stats["added"] = vector_inserted
    stats["updated"] = vector_updated

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
            "[yellow]This will clear the existing index and rebuild from all converted documents.[/yellow]"
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

    entries = get_entries_to_index(catalog, incremental=False)

    if not entries:
        console.print("[yellow]No files with converted content found.[/yellow]")
        return {
            "documents_processed": 0,
            "chunks_indexed": 0,
            "duration_seconds": time.time() - start_time,
        }

    console.print(f"[cyan]Found {len(entries)} documents with converted content[/cyan]")

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

                total_chunks += sum(stats.values())
                total_added += stats["added"]
                total_updated += stats["updated"]

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
    catalog.update()

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

    entries = get_entries_to_index(catalog, incremental=True)

    if not entries:
        console.print("[green]No new or modified documents to index.[/green]")

        with vector_store.VectorStore(base_dir) as vs:
            vs_stats = vs.get_stats()
        with fts.FTSIndex(base_dir) as fts_idx:
            fts_stats = fts_idx.get_stats()

        return {
            "documents_processed": 0,
            "chunks_added": 0,
            "chunks_updated": 0,
            "chunks_removed": 0,
            "chunk_count": vs_stats["chunk_count"],
            "duration_seconds": time.time() - start_time,
        }

    console.print(f"[cyan]Found {len(entries)} documents to process[/cyan]")

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

        total_chunks = 0
        total_added = 0
        total_updated = 0

        with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
            existing_chunk_ids = vs.get_existing_chunk_ids()

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

                total_chunks += sum(stats.values())
                total_added += stats["added"]
                total_updated += stats["updated"]

                progress.update(task, advance=1)

    chunks_removed = 0

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
        console.print("[red]No index found. Run /index-build to create one.[/red]")
        return

    try:
        with vector_store.VectorStore(base_dir) as vs, fts.FTSIndex(base_dir) as fts_idx:
            vs_stats = vs.get_stats()
            fts_stats = fts_idx.get_stats()

        table = Table(title="[bold]Index Statistics[/bold]", show_header=False)
        table.add_column("", justify="left")
        table.add_column("", justify="right")

        vs_modalities = ", ".join(sorted(vs_stats["modalities"]))
        fts_modalities = ", ".join(sorted(fts_stats["modalities"]))

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

    panel = Panel(
        "\n".join(content),
        title="[bold]Index Build[/bold]",
        border_style="green",
    )

    console.print(panel)
