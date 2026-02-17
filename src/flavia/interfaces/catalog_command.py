"""Interactive catalog command for browsing and managing content."""

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from flavia.config import Settings
from flavia.content.catalog import ContentCatalog
from flavia.setup.prompt_utils import q_select

console = Console()


def run_catalog_command(settings: Settings) -> bool:
    """
    Run the interactive catalog browser.

    Args:
        settings: Current settings with base_dir.

    Returns:
        True if catalog was loaded successfully, False otherwise.
    """
    config_dir = settings.base_dir / ".flavia"

    catalog = ContentCatalog.load(config_dir)
    if catalog is None:
        console.print("[yellow]No catalog found. Run `flavia --init` to create one.[/yellow]")
        return False

    while True:
        choice = _print_catalog_menu()

        if choice == "1":
            _show_overview(catalog)
        elif choice == "2":
            _browse_files(catalog)
        elif choice == "3":
            _search_catalog(catalog)
        elif choice == "4":
            _show_summaries(catalog)
        elif choice == "5":
            _manage_online_sources(catalog, config_dir, settings)
        elif choice == "6":
            _add_online_source(catalog, config_dir, settings)
        elif choice == "7":
            _manage_pdf_files(catalog, config_dir, settings)
        elif choice == "8":
            _manage_office_files(catalog, config_dir, settings)
        elif choice == "9":
            _manage_image_files(catalog, config_dir, settings)
        elif choice == "10":
            _manage_media_files(catalog, config_dir, settings)
        elif choice in ("q", "Q", ""):
            break
        else:
            console.print("[red]Invalid choice. Try again.[/red]")

    return True


def _print_catalog_menu() -> str:
    """Print the main catalog menu and get user choice."""
    console.print("\n[bold cyan]Content Catalog[/bold cyan]")
    console.print("=" * 40)

    try:
        import questionary

        menu_choices = [
            questionary.Choice(title="Overview / Statistics", value="1"),
            questionary.Choice(title="Browse Files (tree view)", value="2"),
            questionary.Choice(title="Search", value="3"),
            questionary.Choice(title="View Summaries", value="4"),
            questionary.Choice(title="Online Sources", value="5"),
            questionary.Choice(title="Add Online Source", value="6"),
            questionary.Choice(title="PDF Files", value="7"),
            questionary.Choice(title="Office Documents", value="8"),
            questionary.Choice(title="Image Files", value="9"),
            questionary.Choice(title="Audio/Video Files", value="10"),
            questionary.Choice(title="Back to chat", value="q"),
        ]
    except ImportError:
        menu_choices = [
            "Overview / Statistics",
            "Browse Files (tree view)",
            "Search",
            "View Summaries",
            "Online Sources",
            "Add Online Source",
            "PDF Files",
            "Office Documents",
            "Image Files",
            "Audio/Video Files",
            "Back to chat",
        ]

    choice = q_select("Select option:", choices=menu_choices, default="1")

    if choice is None:
        return "q"

    # Map title back to value if needed
    title_to_value = {
        "Overview / Statistics": "1",
        "Browse Files (tree view)": "2",
        "Search": "3",
        "View Summaries": "4",
        "Online Sources": "5",
        "Add Online Source": "6",
        "PDF Files": "7",
        "Office Documents": "8",
        "Image Files": "9",
        "Audio/Video Files": "10",
        "Back to chat": "q",
    }

    return title_to_value.get(choice, choice)


def _show_overview(catalog: ContentCatalog) -> None:
    """Display catalog overview with statistics."""
    stats = catalog.get_stats()

    console.print("\n[bold]Catalog Overview[/bold]")

    # General stats table
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="cyan")

    table.add_row("Total files", str(stats["total_files"]))
    table.add_row(
        "Total size",
        f"{stats['total_size_bytes'] / 1024 / 1024:.2f} MB",
    )
    table.add_row("With summaries", str(stats["with_summary"]))
    table.add_row("With conversions", str(stats["with_conversion"]))
    table.add_row("Online sources", str(stats.get("online_sources", 0)))

    console.print(table)

    # File types breakdown
    if stats["by_type"]:
        console.print("\n[bold]By Type:[/bold]")
        type_table = Table(show_header=True, box=None)
        type_table.add_column("Type", style="dim")
        type_table.add_column("Count", style="cyan", justify="right")

        for file_type, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            type_table.add_row(file_type, str(count))
        console.print(type_table)

    # Top extensions
    if stats["by_extension"]:
        console.print("\n[bold]Top Extensions:[/bold]")
        ext_items = sorted(stats["by_extension"].items(), key=lambda x: -x[1])[:10]
        ext_table = Table(show_header=True, box=None)
        ext_table.add_column("Extension", style="dim")
        ext_table.add_column("Count", style="cyan", justify="right")

        for ext, count in ext_items:
            ext_table.add_row(ext or "(none)", str(count))
        console.print(ext_table)

    # Online sources breakdown
    if stats.get("by_source_type"):
        console.print("\n[bold]Online Sources by Type:[/bold]")
        src_table = Table(show_header=True, box=None)
        src_table.add_column("Source Type", style="dim")
        src_table.add_column("Count", style="cyan", justify="right")

        for src_type, count in sorted(stats["by_source_type"].items(), key=lambda x: -x[1]):
            src_table.add_row(src_type, str(count))
        console.print(src_table)


def _browse_files(catalog: ContentCatalog) -> None:
    """Display files in a tree view."""
    if not catalog.directory_tree:
        console.print("[yellow]No directory structure available.[/yellow]")
        return

    console.print("\n[bold]Directory Structure[/bold]")

    tree = Tree(
        f"[bold]{catalog.directory_tree.name}[/bold] ({catalog.directory_tree.file_count} files)"
    )

    def add_node(parent_tree: Tree, node) -> None:
        for child in node.children:
            summary_part = f" - {child.summary}" if child.summary else ""
            branch = parent_tree.add(
                f"[cyan]{child.name}/[/cyan] ({child.file_count}){summary_part}"
            )
            add_node(branch, child)

    add_node(tree, catalog.directory_tree)
    console.print(tree)


def _search_catalog(catalog: ContentCatalog) -> None:
    """Interactive search in the catalog."""
    console.print("\n[bold]Search Catalog[/bold]")
    console.print("[dim]Search by name, extension, type, or text in summaries[/dim]")

    try:
        query = console.input("[bold]Search query:[/bold] ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not query:
        return

    # Try different search strategies
    results = []

    # Search by name
    results.extend(catalog.query(name=query, limit=20))

    # Search by text in summaries
    text_results = catalog.query(text_search=query, limit=20)
    for r in text_results:
        if r not in results:
            results.append(r)

    # Search by extension if query looks like one
    if query.startswith(".") or len(query) <= 4:
        ext = query if query.startswith(".") else f".{query}"
        ext_results = catalog.query(extension=ext, limit=20)
        for r in ext_results:
            if r not in results:
                results.append(r)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results)} result(s):[/bold]")

    table = Table(show_header=True)
    table.add_column("Path", style="cyan", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("Size", justify="right")
    table.add_column("Summary", max_width=40)

    for entry in results[:20]:
        size_str = _format_size(entry.size_bytes)
        summary = (entry.summary or "")[:40]
        if len(entry.summary or "") > 40:
            summary += "..."
        table.add_row(entry.path, entry.file_type, size_str, summary)

    console.print(table)


def _quality_badge(quality: str | None) -> str:
    """Return a colored quality badge string."""
    if quality == "good":
        return "[green]● good[/green]"
    elif quality == "partial":
        return "[yellow]● partial[/yellow]"
    elif quality == "poor":
        return "[red]● poor[/red]"
    else:
        return "[dim]● unknown[/dim]"


def _show_summaries(catalog: ContentCatalog) -> None:
    """Display files that have summaries."""
    files_with_summary = [e for e in catalog.files.values() if e.summary and e.status != "missing"]

    if not files_with_summary:
        console.print("[yellow]No files have summaries yet.[/yellow]")
        return

    console.print(f"\n[bold]Files with Summaries ({len(files_with_summary)}):[/bold]")

    for entry in sorted(files_with_summary, key=lambda e: e.path)[:30]:
        badge = _quality_badge(entry.extraction_quality)
        console.print(f"\n[cyan]{entry.path}[/cyan]  {badge}")
        console.print(Panel(entry.summary, expand=False))


def _manage_online_sources(
    catalog: ContentCatalog,
    config_dir: Path,
    settings: Settings,
) -> None:
    """Interactive online source manager with fetch, view, and delete support."""
    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    while True:
        online_sources = catalog.get_online_sources()

        if not online_sources:
            console.print("[yellow]No online sources in catalog.[/yellow]")
            return

        console.print(f"\n[bold]Online Sources ({len(online_sources)})[/bold]")

        table = Table(show_header=True)
        table.add_column("#", style="dim", justify="right")
        table.add_column("Type", style="dim")
        table.add_column("URL", style="cyan", max_width=50)
        table.add_column("Status")
        table.add_column("Title", max_width=30)

        for i, entry in enumerate(online_sources, 1):
            title = entry.source_metadata.get("title", entry.name)[:30]
            url = (entry.source_url or "")[:50]
            if len(entry.source_url or "") > 50:
                url += "..."
            status_style = {
                "completed": "[green]completed[/green]",
                "pending": "[yellow]pending[/yellow]",
                "failed": "[red]failed[/red]",
                "not_implemented": "[dim]not implemented[/dim]",
            }.get(entry.fetch_status, entry.fetch_status)
            table.add_row(str(i), entry.source_type, url, status_style, title)

        console.print(table)

        # Stats line
        pending = sum(1 for e in online_sources if e.fetch_status == "pending")
        completed = sum(1 for e in online_sources if e.fetch_status == "completed")
        failed = sum(1 for e in online_sources if e.fetch_status == "failed")
        console.print(
            f"\n[dim]Pending: {pending} | Completed: {completed} | Failed: {failed}[/dim]"
        )

        # Build source selection menu
        try:
            import questionary

            source_choices = [
                questionary.Choice(
                    title=f"[{e.source_type}] {e.source_metadata.get('title', e.source_url or e.name)[:60]}",
                    value=e.path,
                )
                for e in online_sources
            ]
            source_choices.append(questionary.Choice(title="Back", value="__back__"))
        except ImportError:
            source_choices = [
                f"[{e.source_type}] {e.source_metadata.get('title', e.source_url or e.name)[:60]}"
                for e in online_sources
            ] + ["Back"]

        selected = q_select("Select a source:", choices=source_choices)
        if selected in (None, "__back__", "Back"):
            break

        # Map selection to entry (handle both value and title-based selection)
        entry = catalog.files.get(selected)
        if entry is None:
            # Fallback: match by title
            for e in online_sources:
                label = f"[{e.source_type}] {e.source_metadata.get('title', e.source_url or e.name)[:60]}"
                if selected == label:
                    entry = e
                    break
        if entry is None:
            continue

        # Show entry details and action menu
        _show_online_entry_details(entry, base_dir)
        _online_source_action_menu(entry, catalog, config_dir, base_dir, converted_dir, settings)


def _show_online_entry_details(entry, base_dir: Path) -> None:
    """Show details for a selected online source entry."""
    console.print(f"\n[bold cyan]{entry.source_metadata.get('title', entry.name)}[/bold cyan]")

    converted_exists = False
    if entry.converted_to:
        converted_path = (base_dir / entry.converted_to).resolve()
        try:
            converted_path.relative_to(base_dir.resolve())
            converted_exists = converted_path.exists()
        except ValueError:
            converted_exists = False

    status_style = {
        "completed": "[green]completed[/green]",
        "pending": "[yellow]pending[/yellow]",
        "failed": "[red]failed[/red]",
        "not_implemented": "[dim]not implemented[/dim]",
    }.get(entry.fetch_status, entry.fetch_status)

    details = Table(show_header=False, box=None)
    details.add_column("Field", style="dim")
    details.add_column("Value")
    details.add_row("Source type", entry.source_type)
    details.add_row("URL", entry.source_url or "[dim](none)[/dim]")
    details.add_row("Fetch status", status_style)
    details.add_row("Converted file", entry.converted_to or "[dim](none)[/dim]")
    details.add_row("Content exists", "[green]yes[/green]" if converted_exists else "[dim]no[/dim]")
    details.add_row("Summary", "[green]yes[/green]" if entry.summary else "[dim]no[/dim]")

    # Source-specific metadata
    meta = entry.source_metadata
    if entry.source_type == "youtube":
        channel = meta.get("channel", "")
        if channel:
            details.add_row("Channel", channel)
        duration = meta.get("duration", "")
        if duration:
            details.add_row("Duration", duration)
        upload_date = meta.get("upload_date", "")
        if upload_date:
            if len(upload_date) == 8 and upload_date.isdigit():
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            details.add_row("Upload date", upload_date)
        view_count = meta.get("view_count")
        if view_count is not None:
            details.add_row("Views", f"{view_count:,}")
    elif entry.source_type == "webpage":
        author = meta.get("author", "")
        if author:
            details.add_row("Author", author)
        date = meta.get("date", "")
        if date:
            details.add_row("Date", date)
        domain = meta.get("domain", "")
        if domain:
            details.add_row("Domain", domain)

    console.print(details)

    if entry.summary:
        console.print(Panel(entry.summary, title="Summary", expand=False))


def _online_source_action_menu(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
    base_dir: Path,
    converted_dir: Path,
    settings: Settings,
) -> None:
    """Show action menu for a selected online source."""
    is_youtube = entry.source_type == "youtube"
    has_content = bool(entry.converted_to)

    # Build action list
    try:
        import questionary as _q

        action_choices = []
        if entry.fetch_status in ("pending", "failed"):
            action_choices.append(_q.Choice(title="Fetch content", value="fetch"))
        if has_content:
            action_choices.append(_q.Choice(title="View content", value="view"))
            action_choices.append(_q.Choice(title="Re-fetch content", value="refetch"))
            action_choices.append(_q.Choice(title="Summarize / Re-summarize", value="summarize"))
        else:
            if entry.fetch_status == "completed":
                # Content was fetched before but file might be missing
                action_choices.append(_q.Choice(title="Re-fetch content", value="refetch"))
        if is_youtube:
            action_choices.append(
                _q.Choice(title="Download & describe thumbnail", value="thumbnail")
            )
            if has_content:
                action_choices.append(
                    _q.Choice(title="Extract & describe visual frames", value="extract_frames")
                )
                if entry.frame_descriptions:
                    action_choices.append(
                        _q.Choice(title="View frame descriptions", value="view_frames")
                    )
        action_choices.append(_q.Choice(title="View metadata", value="metadata"))
        action_choices.append(_q.Choice(title="Refresh metadata", value="refresh_meta"))
        action_choices.append(_q.Choice(title="Delete source", value="delete"))
        action_choices.append(_q.Choice(title="Back", value="back"))
    except ImportError:
        action_choices = []
        if entry.fetch_status in ("pending", "failed"):
            action_choices.append("Fetch content")
        if has_content:
            action_choices.extend(["View content", "Re-fetch content", "Summarize / Re-summarize"])
        else:
            if entry.fetch_status == "completed":
                action_choices.append("Re-fetch content")
        if is_youtube:
            action_choices.append("Download & describe thumbnail")
            if has_content:
                action_choices.append("Extract & describe visual frames")
                if entry.frame_descriptions:
                    action_choices.append("View frame descriptions")
        action_choices.extend(["View metadata", "Refresh metadata", "Delete source", "Back"])

    action = q_select("Action:", choices=action_choices)

    if action in (None, "back", "Back"):
        return

    # --- Fetch content ----------------------------------------------------
    if action in ("fetch", "Fetch content", "refetch", "Re-fetch content"):
        _fetch_online_source(entry, catalog, config_dir, base_dir, converted_dir, settings)

    # --- View content -----------------------------------------------------
    elif action in ("view", "View content"):
        _view_online_content(entry, base_dir)

    # --- Summarize --------------------------------------------------------
    elif action in ("summarize", "Summarize / Re-summarize"):
        if not entry.converted_to:
            console.print("[yellow]No content available. Fetch first.[/yellow]")
            return
        _offer_resummarization_with_quality(entry, base_dir, settings, ask_confirmation=False)
        catalog.save(config_dir)
        console.print("[dim]Catalog saved.[/dim]")

    # --- Thumbnail (YouTube only) -----------------------------------------
    elif action in ("thumbnail", "Download & describe thumbnail"):
        _fetch_youtube_thumbnail(entry, catalog, config_dir, base_dir, converted_dir, settings)

    # --- YouTube frame extraction ------------------------------------------
    elif action in ("extract_frames", "Extract & describe visual frames"):
        _extract_youtube_frames(entry, catalog, config_dir, base_dir, converted_dir, settings)

    elif action in ("view_frames", "View frame descriptions"):
        _view_frame_descriptions(entry, base_dir)

    # --- View metadata ----------------------------------------------------
    elif action in ("metadata", "View metadata"):
        _view_online_metadata(entry)

    # --- Refresh metadata -------------------------------------------------
    elif action in ("refresh_meta", "Refresh metadata"):
        _refresh_online_metadata(entry, catalog, config_dir)

    # --- Delete source ----------------------------------------------------
    elif action in ("delete", "Delete source"):
        _delete_online_source(entry, catalog, config_dir, base_dir)


def _fetch_online_source(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
    base_dir: Path,
    converted_dir: Path,
    settings: Settings,
) -> None:
    """Fetch and convert an online source."""
    from flavia.content.converters import converter_registry

    source_url = entry.source_url
    if not source_url:
        console.print("[red]No URL available for this source.[/red]")
        return

    converter = converter_registry.get_for_source(entry.source_type)
    if converter is None:
        console.print(f"[red]No converter found for source type: {entry.source_type}[/red]")
        return

    if not converter.is_implemented:
        console.print(
            f"[yellow]Converter for '{entry.source_type}' is not yet implemented.[/yellow]"
        )
        return

    # Check dependencies
    deps_ok, missing = converter.check_dependencies()
    if not deps_ok:
        console.print(
            f"[red]Missing dependencies: {', '.join(missing)}.[/red]\n"
            f"[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    console.print(f"[dim]Fetching content from {source_url}...[/dim]")

    try:
        output_dir = converted_dir / "_online" / entry.source_type
        result_path = converter.fetch_and_convert(source_url, output_dir)

        if result_path and result_path.exists():
            try:
                entry.converted_to = str(result_path.relative_to(base_dir))
            except ValueError:
                entry.converted_to = str(result_path)
            entry.fetch_status = "completed"
            console.print(f"[green]Content fetched successfully:[/green] {entry.converted_to}")

            if _prompt_yes_no("View content now?", "Yes", "No"):
                _view_online_content(entry, base_dir)

            # Offer summarization
            if _prompt_yes_no("Summarize now?", "Yes", "No"):
                _offer_resummarization_with_quality(
                    entry, base_dir, settings, ask_confirmation=False
                )

            catalog.save(config_dir)
            console.print("[dim]Catalog saved.[/dim]")
        else:
            entry.fetch_status = "failed"
            console.print("[red]Fetch failed. No content was retrieved.[/red]")
            catalog.save(config_dir)

    except Exception as e:
        entry.fetch_status = "failed"
        console.print(f"[red]Fetch failed: {e}[/red]")
        catalog.save(config_dir)


def _view_online_content(entry, base_dir: Path) -> None:
    """View fetched online source content."""
    if not entry.converted_to:
        console.print("[yellow]No content available. Fetch first.[/yellow]")
        return

    content_path = (base_dir / entry.converted_to).resolve()
    try:
        content_path.relative_to(base_dir.resolve())
    except ValueError:
        console.print("[red]Blocked unsafe path outside project directory.[/red]")
        return

    if not content_path.exists():
        console.print("[yellow]Content file not found. Try re-fetching.[/yellow]")
        return

    try:
        content = content_path.read_text(encoding="utf-8")
        title = entry.source_metadata.get("title", entry.name)
        console.print(Panel(content, title=f"Content: {title}", expand=False))
    except Exception as e:
        console.print(f"[red]Failed to read content: {e}[/red]")


def _fetch_youtube_thumbnail(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
    base_dir: Path,
    converted_dir: Path,
    settings: Settings,
) -> None:
    """Download and describe a YouTube video thumbnail."""
    from flavia.content.converters.online.youtube import YouTubeConverter

    source_url = entry.source_url
    if not source_url:
        console.print("[red]No URL available.[/red]")
        return

    converter = YouTubeConverter()

    # Check dependencies
    deps_ok, missing = converter.check_dependencies()
    if not deps_ok:
        console.print(
            f"[red]Missing dependencies: {', '.join(missing)}.[/red]\n"
            f"[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    if not converter._has_yt_dlp():
        console.print(
            "[red]Missing dependency: yt-dlp.[/red]\n"
            "[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    console.print("[dim]Downloading and describing thumbnail...[/dim]")

    output_dir = converted_dir / "_online" / "youtube"
    result = converter.download_and_describe_thumbnail(source_url, output_dir)

    if result is None:
        console.print("[red]Thumbnail download or description failed.[/red]")
        return

    md_path, description = result
    console.print(f"[green]Thumbnail described:[/green] {md_path.name}")
    console.print(Panel(description, title="Thumbnail Description", expand=False))

    # Store reference in metadata
    try:
        thumb_rel = str(md_path.relative_to(base_dir))
    except ValueError:
        thumb_rel = str(md_path)
    entry.source_metadata["thumbnail_description_file"] = thumb_rel

    catalog.save(config_dir)
    console.print("[dim]Catalog saved.[/dim]")


def _extract_youtube_frames(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
    base_dir: Path,
    converted_dir: Path,
    settings: Settings,
) -> None:
    """Download YouTube video and extract/describe sampled visual frames."""
    from flavia.content.converters.online.youtube import YouTubeConverter

    source_url = entry.source_url
    if not source_url:
        console.print("[red]No URL available.[/red]")
        return

    if not entry.converted_to:
        console.print("[yellow]No transcript/content found. Fetch content first.[/yellow]")
        return

    transcript_path = (base_dir / entry.converted_to).resolve()
    try:
        transcript_path.relative_to(base_dir.resolve())
    except ValueError:
        console.print("[red]Blocked unsafe path outside project directory.[/red]")
        return

    if not transcript_path.exists():
        console.print("[yellow]Transcript/content file not found. Re-fetch first.[/yellow]")
        return

    transcript = transcript_path.read_text(encoding="utf-8")

    converter = YouTubeConverter()
    deps_ok, missing = converter.check_dependencies()
    if not deps_ok:
        console.print(
            f"[red]Missing dependencies: {', '.join(missing)}.[/red]\n"
            "[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    if not converter._has_yt_dlp():
        console.print(
            "[red]Missing dependency: yt-dlp.[/red]\n"
            "[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    output_dir = converted_dir / "_online" / "youtube"
    console.print(
        "[dim]Downloading video and extracting/describing visual frames "
        "(uses vision LLM and can consume tokens)...[/dim]"
    )
    description_files, description_timestamps = converter.extract_and_describe_frames(
        source_url=source_url,
        transcript=transcript,
        base_output_dir=output_dir,
        settings=settings,
    )

    if not description_files:
        console.print(
            "[yellow]No frame descriptions generated. "
            "Video may be too short, transcript may lack timestamps, or download failed.[/yellow]"
        )
        return

    for i, (desc_file_path, timestamp) in enumerate(
        zip(description_files, description_timestamps), 1
    ):
        console.print(
            f"  [dim]Frame {i}/{len(description_files)} at timestamp "
            f"{timestamp:.1f}s: {desc_file_path.name}[/dim]"
        )

    console.print(f"[green]Generated {len(description_files)} frame descriptions[/green]")

    frame_description_paths = []
    for desc_path in description_files:
        try:
            frame_description_paths.append(str(desc_path.relative_to(base_dir)))
        except ValueError:
            frame_description_paths.append(str(desc_path))

    entry.frame_descriptions = frame_description_paths

    if _prompt_yes_no("View frame descriptions now?", "Yes", "No"):
        _view_frame_descriptions(entry, base_dir)

    catalog.save(config_dir)
    console.print("[dim]Catalog saved.[/dim]")


def _view_online_metadata(entry) -> None:
    """Display metadata for an online source."""
    meta = entry.source_metadata
    if not meta:
        console.print("[yellow]No metadata available.[/yellow]")
        return

    console.print(f"\n[bold]Metadata for {entry.source_type} source[/bold]")

    meta_table = Table(show_header=False, box=None)
    meta_table.add_column("Key", style="dim")
    meta_table.add_column("Value")

    for key, value in sorted(meta.items()):
        if key == "status":
            continue
        val_str = str(value)
        if len(val_str) > 200:
            val_str = val_str[:200] + "..."
        meta_table.add_row(key, val_str)

    console.print(meta_table)


def _refresh_online_metadata(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
) -> None:
    """Re-fetch metadata for an online source."""
    from flavia.content.converters import converter_registry

    source_url = entry.source_url
    if not source_url:
        console.print("[red]No URL available.[/red]")
        return

    converter = converter_registry.get_for_source(entry.source_type)
    if converter is None or not converter.is_implemented:
        console.print("[yellow]Converter not available for metadata refresh.[/yellow]")
        return

    deps_ok, missing = converter.check_dependencies()
    if not deps_ok:
        console.print(
            f"[red]Missing dependencies: {', '.join(missing)}.[/red]\n"
            f"[dim]Install with: pip install 'flavia[online]'[/dim]"
        )
        return

    console.print("[dim]Refreshing metadata...[/dim]")

    try:
        new_meta = converter.get_metadata(source_url)
        if new_meta and new_meta.get("status") != "error":
            # Preserve any extra keys we added (like thumbnail_description_file)
            preserved_keys = {"thumbnail_description_file"}
            for key in preserved_keys:
                if key in entry.source_metadata:
                    new_meta[key] = entry.source_metadata[key]

            entry.source_metadata = new_meta
            entry.name = new_meta.get("title", entry.name)
            console.print("[green]Metadata refreshed.[/green]")
            _view_online_metadata(entry)
            catalog.save(config_dir)
            console.print("[dim]Catalog saved.[/dim]")
        else:
            msg = new_meta.get("message", "Unknown error") if new_meta else "No metadata returned"
            console.print(f"[red]Metadata refresh failed: {msg}[/red]")
    except Exception as e:
        console.print(f"[red]Metadata refresh failed: {e}[/red]")


def _delete_online_source(
    entry,
    catalog: ContentCatalog,
    config_dir: Path,
    base_dir: Path,
) -> None:
    """Delete an online source from the catalog and optionally remove converted files."""
    title = entry.source_metadata.get("title", entry.source_url or entry.name)
    console.print(f"\n[yellow]Delete source: {title}[/yellow]")

    if not _prompt_yes_no("Are you sure you want to delete this source?", "Yes, delete", "No"):
        return

    # Optionally delete converted content file
    if entry.converted_to:
        content_path = (base_dir / entry.converted_to).resolve()
        try:
            content_path.relative_to(base_dir.resolve())
            if content_path.exists():
                if _prompt_yes_no("Also delete the converted content file?", "Yes", "No"):
                    content_path.unlink(missing_ok=True)
                    console.print(f"[dim]Deleted: {entry.converted_to}[/dim]")
        except ValueError:
            pass

    # Remove from catalog
    if entry.path in catalog.files:
        del catalog.files[entry.path]
        console.print("[green]Source removed from catalog.[/green]")
        catalog.save(config_dir)
        console.print("[dim]Catalog saved.[/dim]")


def _add_online_source(
    catalog: ContentCatalog,
    config_dir: Path,
    settings: Settings,
) -> None:
    """Add a new online source to the catalog with optional immediate fetch."""
    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    console.print("\n[bold]Add Online Source[/bold]")
    console.print("[dim]Supported: YouTube videos, web pages (any HTTP/HTTPS URL)[/dim]")

    try:
        url = console.input("[bold]URL:[/bold] ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not url:
        return

    # Validate URL format
    if not url.startswith(("http://", "https://")):
        console.print("[red]Invalid URL. Must start with http:// or https://[/red]")
        return

    console.print("[dim]Detecting source type and fetching metadata...[/dim]")
    entry = catalog.add_online_source(url)

    if entry is None:
        console.print("[red]Could not add source. Unsupported URL type.[/red]")
        return

    console.print(f"\n[green]Added {entry.source_type} source:[/green]")
    console.print(f"  Title: {entry.source_metadata.get('title', '(unknown)')}")
    console.print(f"  Path: {entry.path}")
    console.print(f"  Status: {entry.fetch_status}")

    # Save catalog immediately
    catalog.save(config_dir)

    # Offer immediate fetch if converter is implemented
    if entry.fetch_status == "pending":
        if _prompt_yes_no("Fetch content now?", "Yes", "No"):
            _fetch_online_source(entry, catalog, config_dir, base_dir, converted_dir, settings)
    elif entry.fetch_status == "not_implemented":
        console.print(
            "\n[yellow]This source type converter is not yet fully implemented. "
            "The URL has been saved for future processing.[/yellow]"
        )

    console.print("[dim]Catalog saved.[/dim]")


def _manage_pdf_files(catalog: ContentCatalog, config_dir: Path, settings: Settings) -> None:
    """Interactive PDF file manager with OCR support."""
    import os

    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    pdf_files = [e for e in catalog.files.values() if e.category == "pdf" and e.status != "missing"]

    if not pdf_files:
        console.print("[yellow]No PDF files in catalog.[/yellow]")
        return

    while True:
        console.print(f"\n[bold]PDF Files ({len(pdf_files)})[/bold]")

        table = Table(show_header=True)
        table.add_column("Path", style="cyan", max_width=50)
        table.add_column("Converted", style="dim")
        table.add_column("Quality")
        table.add_column("Size", justify="right")

        for entry in sorted(pdf_files, key=lambda e: e.path):
            converted = "[green]yes[/green]" if entry.converted_to else "[dim]no[/dim]"
            badge = _quality_badge(entry.extraction_quality)
            table.add_row(entry.path, converted, badge, _format_size(entry.size_bytes))

        console.print(table)

        try:
            import questionary

            pdf_choices = [
                questionary.Choice(title=e.path, value=e.path)
                for e in sorted(pdf_files, key=lambda e: e.path)
            ]
            pdf_choices.append(questionary.Choice(title="Back", value="__back__"))
        except ImportError:
            pdf_choices = [e.path for e in sorted(pdf_files, key=lambda e: e.path)] + ["Back"]

        selected = q_select("Select a PDF:", choices=pdf_choices)
        if selected in (None, "__back__", "Back"):
            break

        entry = catalog.files.get(selected)
        if entry is None:
            break

        _show_pdf_entry_details(entry, base_dir, settings)

        # Action menu
        try:
            import questionary as _q

            action_choices = [
                _q.Choice(title="Run full OCR (Mistral API)", value="ocr"),
                _q.Choice(title="Extract text (simple)", value="simple"),
                _q.Choice(title="Re-run summary/quality (no extraction)", value="resummarize"),
                _q.Choice(title="Back", value="back"),
            ]
        except ImportError:
            action_choices = [
                "Run full OCR (Mistral API)",
                "Extract text (simple)",
                "Re-run summary/quality (no extraction)",
                "Back",
            ]

        action = q_select("Action:", choices=action_choices)

        if action in (None, "back", "Back"):
            continue

        source = (base_dir / entry.path).resolve()
        try:
            source.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                "[red]Blocked unsafe path outside project directory in catalog entry.[/red]"
            )
            continue

        if action in ("ocr", "Run full OCR (Mistral API)"):
            from flavia.content.converters.mistral_key_manager import get_mistral_api_key

            api_key = get_mistral_api_key(interactive=True)
            if not api_key:
                console.print(
                    "[red]MISTRAL_API_KEY is required for OCR. Please provide it to continue.[/red]"
                )
                continue

            console.print(f"[dim]Running Mistral OCR on {entry.path}...[/dim]")
            from flavia.content.converters.mistral_ocr_converter import MistralOcrConverter

            result_path = MistralOcrConverter().convert(source, converted_dir)
            if result_path:
                try:
                    entry.converted_to = str(result_path.relative_to(base_dir))
                except ValueError:
                    entry.converted_to = str(result_path)
                console.print(f"[green]OCR complete:[/green] {entry.converted_to}")
                _offer_resummarization_with_quality(entry, base_dir, settings)

                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print("[red]OCR failed. Check MISTRAL_API_KEY and mistralai package.[/red]")

        elif action in ("simple", "Extract text (simple)"):
            console.print(f"[dim]Extracting text from {entry.path}...[/dim]")
            from flavia.content.converters import PdfConverter

            result_path = PdfConverter().convert(source, converted_dir)
            if result_path:
                try:
                    entry.converted_to = str(result_path.relative_to(base_dir))
                except ValueError:
                    entry.converted_to = str(result_path)
                console.print(f"[green]Extraction complete:[/green] {entry.converted_to}")
                _offer_resummarization_with_quality(entry, base_dir, settings)
                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print("[red]Extraction failed.[/red]")

        elif action in ("resummarize", "Re-run summary/quality (no extraction)"):
            if not entry.converted_to:
                console.print(
                    "[yellow]No converted text found. Run OCR or text extraction first.[/yellow]"
                )
                continue

            _offer_resummarization_with_quality(
                entry,
                base_dir,
                settings,
                ask_confirmation=False,
            )
            catalog.save(config_dir)
            console.print("[dim]Catalog saved.[/dim]")


def _manage_office_files(catalog: ContentCatalog, config_dir: Path, settings: Settings) -> None:
    """Interactive Office document manager with conversion support."""
    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    # Categories for Office documents
    office_categories = {"word", "spreadsheet", "presentation", "document"}

    office_files = [
        e
        for e in catalog.files.values()
        if e.category in office_categories and e.status != "missing"
    ]

    if not office_files:
        console.print("[yellow]No Office documents in catalog.[/yellow]")
        return

    while True:
        console.print(f"\n[bold]Office Documents ({len(office_files)})[/bold]")

        table = Table(show_header=True)
        table.add_column("Path", style="cyan", max_width=50)
        table.add_column("Type", style="dim")
        table.add_column("Converted", style="dim")
        table.add_column("Quality")
        table.add_column("Size", justify="right")

        for entry in sorted(office_files, key=lambda e: e.path):
            converted = "[green]yes[/green]" if entry.converted_to else "[dim]no[/dim]"
            badge = _quality_badge(entry.extraction_quality)
            doc_type = entry.category or "unknown"
            table.add_row(entry.path, doc_type, converted, badge, _format_size(entry.size_bytes))

        console.print(table)

        try:
            import questionary

            office_choices = [
                questionary.Choice(title=e.path, value=e.path)
                for e in sorted(office_files, key=lambda e: e.path)
            ]
            office_choices.append(questionary.Choice(title="Back", value="__back__"))
        except ImportError:
            office_choices = [e.path for e in sorted(office_files, key=lambda e: e.path)] + ["Back"]

        selected = q_select("Select an Office document:", choices=office_choices)
        if selected in (None, "__back__", "Back"):
            break

        entry = catalog.files.get(selected)
        if entry is None:
            break

        _show_office_entry_details(entry, base_dir, settings)

        # Action menu
        try:
            import questionary as _q

            action_choices = [
                _q.Choice(title="Extract text / Convert to Markdown", value="convert"),
                _q.Choice(title="Re-run summary/quality (no extraction)", value="resummarize"),
                _q.Choice(title="Back", value="back"),
            ]
        except ImportError:
            action_choices = [
                "Extract text / Convert to Markdown",
                "Re-run summary/quality (no extraction)",
                "Back",
            ]

        action = q_select("Action:", choices=action_choices)

        if action in (None, "back", "Back"):
            continue

        source = (base_dir / entry.path).resolve()
        try:
            source.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                "[red]Blocked unsafe path outside project directory in catalog entry.[/red]"
            )
            continue

        if action in ("convert", "Extract text / Convert to Markdown"):
            console.print(f"[dim]Converting {entry.path}...[/dim]")
            from flavia.content.converters import OfficeConverter

            converter = OfficeConverter()

            # Check dependencies
            deps_ok, missing = converter.check_dependencies()
            if not deps_ok:
                console.print(
                    f"[red]Missing dependencies: {', '.join(missing)}. "
                    f"Install with: pip install {' '.join(missing)}[/red]"
                )
                continue

            result_path = converter.convert(source, converted_dir)
            if result_path:
                try:
                    entry.converted_to = str(result_path.relative_to(base_dir))
                except ValueError:
                    entry.converted_to = str(result_path)
                console.print(f"[green]Conversion complete:[/green] {entry.converted_to}")
                _offer_resummarization_with_quality(entry, base_dir, settings)
                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print("[red]Conversion failed.[/red]")

        elif action in ("resummarize", "Re-run summary/quality (no extraction)"):
            if not entry.converted_to:
                console.print("[yellow]No converted text found. Run extraction first.[/yellow]")
                continue

            _offer_resummarization_with_quality(
                entry,
                base_dir,
                settings,
                ask_confirmation=False,
            )
            catalog.save(config_dir)
            console.print("[dim]Catalog saved.[/dim]")


def _manage_image_files(catalog: ContentCatalog, config_dir: Path, settings: Settings) -> None:
    """Interactive image file manager with vision-based description generation."""
    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    image_files = [
        e for e in catalog.files.values() if e.file_type == "image" and e.status != "missing"
    ]

    if not image_files:
        console.print("[yellow]No image files in catalog.[/yellow]")
        return

    while True:
        console.print(f"\n[bold]Image Files ({len(image_files)})[/bold]")

        table = Table(show_header=True)
        table.add_column("Path", style="cyan", max_width=50)
        table.add_column("Format", style="dim")
        table.add_column("Described", style="dim")
        table.add_column("Size", justify="right")

        for entry in sorted(image_files, key=lambda e: e.path):
            described = "[green]yes[/green]" if entry.converted_to else "[dim]no[/dim]"
            ext = Path(entry.path).suffix.lstrip(".").upper()
            table.add_row(entry.path, ext, described, _format_size(entry.size_bytes))

        console.print(table)

        try:
            import questionary

            image_choices = [
                questionary.Choice(title=e.path, value=e.path)
                for e in sorted(image_files, key=lambda e: e.path)
            ]
            image_choices.append(questionary.Choice(title="Back", value="__back__"))
        except ImportError:
            image_choices = [e.path for e in sorted(image_files, key=lambda e: e.path)] + ["Back"]

        selected = q_select("Select an image:", choices=image_choices)
        if selected in (None, "__back__", "Back"):
            break

        entry = catalog.files.get(selected)
        if entry is None:
            break

        _show_image_entry_details(entry, base_dir, settings)

        # Action menu
        try:
            import questionary as _q

            action_choices = [
                _q.Choice(title="Generate description (vision LLM)", value="generate"),
                _q.Choice(title="Re-generate description", value="regenerate"),
                _q.Choice(title="View description", value="view"),
                _q.Choice(title="Change vision model", value="change_model"),
                _q.Choice(title="Back", value="back"),
            ]
        except ImportError:
            action_choices = [
                "Generate description (vision LLM)",
                "Re-generate description",
                "View description",
                "Change vision model",
                "Back",
            ]

        action = q_select("Action:", choices=action_choices)

        if action in (None, "back", "Back"):
            continue

        source = (base_dir / entry.path).resolve()
        try:
            source.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                "[red]Blocked unsafe path outside project directory in catalog entry.[/red]"
            )
            continue

        if action in (
            "generate",
            "Generate description (vision LLM)",
            "regenerate",
            "Re-generate description",
        ):
            if action in ("regenerate", "Re-generate description") and not entry.converted_to:
                console.print(
                    "[yellow]No existing description to regenerate. Generating new one.[/yellow]"
                )

            console.print(f"[dim]Analyzing image {entry.path} with vision model...[/dim]")
            from flavia.content.converters import ImageConverter

            converter = ImageConverter(settings)
            result_path = converter.convert(source, converted_dir)

            if result_path:
                try:
                    entry.converted_to = str(result_path.relative_to(base_dir))
                except ValueError:
                    entry.converted_to = str(result_path)
                console.print(f"[green]Description generated:[/green] {entry.converted_to}")

                # Offer to view the description
                if _prompt_yes_no("View the generated description?", "Yes", "No"):
                    _view_image_description(entry, base_dir)

                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print(
                    "[red]Description generation failed. Check vision model configuration.[/red]"
                )
                _suggest_vision_model_change(settings)

        elif action in ("view", "View description"):
            if not entry.converted_to:
                console.print("[yellow]No description available. Generate one first.[/yellow]")
                continue
            _view_image_description(entry, base_dir)

        elif action in ("change_model", "Change vision model"):
            _select_vision_model(settings)


def _manage_media_files(catalog: ContentCatalog, config_dir: Path, settings: Settings) -> None:
    """Interactive audio/video manager with transcription support."""
    base_dir = config_dir.parent
    converted_dir = base_dir / ".converted"

    media_files = [
        e
        for e in catalog.files.values()
        if e.file_type in {"audio", "video"} and e.status != "missing"
    ]

    if not media_files:
        console.print("[yellow]No audio/video files in catalog.[/yellow]")
        return

    while True:
        console.print(f"\n[bold]Audio/Video Files ({len(media_files)})[/bold]")

        table = Table(show_header=True)
        table.add_column("Path", style="cyan", max_width=50)
        table.add_column("Type", style="dim")
        table.add_column("Format", style="dim")
        table.add_column("Transcribed", style="dim")
        table.add_column("Quality")
        table.add_column("Size", justify="right")

        for entry in sorted(media_files, key=lambda e: e.path):
            transcribed = "[green]yes[/green]" if entry.converted_to else "[dim]no[/dim]"
            media_type = entry.file_type
            fmt = Path(entry.path).suffix.lstrip(".").upper()
            table.add_row(
                entry.path,
                media_type,
                fmt or (entry.category or "unknown"),
                transcribed,
                _quality_badge(entry.extraction_quality),
                _format_size(entry.size_bytes),
            )

        console.print(table)

        try:
            import questionary

            media_choices = [
                questionary.Choice(title=e.path, value=e.path)
                for e in sorted(media_files, key=lambda e: e.path)
            ]
            media_choices.append(questionary.Choice(title="Back", value="__back__"))
        except ImportError:
            media_choices = [e.path for e in sorted(media_files, key=lambda e: e.path)] + ["Back"]

        selected = q_select("Select an audio/video file:", choices=media_choices)
        if selected in (None, "__back__", "Back"):
            break

        entry = catalog.files.get(selected)
        if entry is None:
            break

        _show_media_entry_details(entry, base_dir, settings)

        try:
            import questionary as _q

            action_choices = [
                _q.Choice(title="Transcribe", value="transcribe"),
                _q.Choice(title="Re-transcribe", value="retranscribe"),
                _q.Choice(title="View transcript", value="view"),
                _q.Choice(title="Extract & describe visual frames", value="extract_frames"),
                _q.Choice(title="View frame descriptions", value="view_frames"),
                _q.Choice(title="Re-run summary/quality (no extraction)", value="resummarize"),
                _q.Choice(title="Back", value="back"),
            ]
        except ImportError:
            action_choices = [
                "Transcribe",
                "Re-transcribe",
                "View transcript",
                "Extract & describe visual frames",
                "View frame descriptions",
                "Re-run summary/quality (no extraction)",
                "Back",
            ]

        action = q_select("Action:", choices=action_choices)
        if action in (None, "back", "Back"):
            continue

        if action in ("view", "View transcript"):
            _view_transcription(entry, base_dir)
            continue

        if action in ("view_frames", "View frame descriptions"):
            _view_frame_descriptions(entry, base_dir)
            continue

        source = (base_dir / entry.path).resolve()
        try:
            source.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                "[red]Blocked unsafe path outside project directory in catalog entry.[/red]"
            )
            continue

        if action in ("transcribe", "Transcribe", "retranscribe", "Re-transcribe"):
            if action in ("retranscribe", "Re-transcribe") and not entry.converted_to:
                console.print(
                    "[yellow]No existing transcript found. Running first transcription.[/yellow]"
                )

            if entry.file_type == "audio":
                from flavia.content.converters import AudioConverter

                converter = AudioConverter()
            else:
                from flavia.content.converters import VideoConverter

                converter = VideoConverter()

            deps_ok, missing = converter.check_dependencies()
            if not deps_ok:
                console.print(
                    f"[red]Missing dependencies: {', '.join(missing)}. "
                    f"Install with: pip install {' '.join(missing)}[/red]"
                )
                continue

            console.print(f"[dim]Transcribing {entry.path}...[/dim]")
            result_path = converter.convert(source, converted_dir)
            if result_path:
                try:
                    entry.converted_to = str(result_path.relative_to(base_dir))
                except ValueError:
                    entry.converted_to = str(result_path)
                console.print(f"[green]Transcription complete:[/green] {entry.converted_to}")

                if _prompt_yes_no("View transcript now?", "Yes", "No"):
                    _view_transcription(entry, base_dir)

                _offer_resummarization_with_quality(entry, base_dir, settings)
                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print(
                    "[red]Transcription failed. Check MISTRAL_API_KEY, mistralai package, "
                    "and ffmpeg (for video files).[/red]"
                )

        elif action in ("extract_frames", "Extract & describe visual frames"):
            if entry.file_type != "video":
                console.print(
                    "[yellow]Visual frame extraction is only available for video files.[/yellow]"
                )
                continue

            if not entry.converted_to:
                console.print("[yellow]No transcript found. Run transcription first.[/yellow]")
                continue

            from flavia.content.converters import VideoConverter

            console.print(
                "[dim]Extracting and describing visual frames (uses vision LLM and can consume tokens)...[/dim]"
            )
            converter = VideoConverter(settings)

            transcript_path = (base_dir / entry.converted_to).resolve()
            try:
                transcript_path.relative_to(base_dir.resolve())
            except ValueError:
                console.print("[red]Blocked unsafe path outside project directory.[/red]")
                continue

            if not transcript_path.exists():
                console.print("[yellow]Transcript file not found.[/yellow]")
                continue

            transcript = transcript_path.read_text(encoding="utf-8")
            description_files, description_timestamps = converter.extract_and_describe_frames(
                transcript=transcript,
                video_path=source,
                base_output_dir=converted_dir,
            )

            if description_files:
                for i, (desc_file_path, timestamp) in enumerate(
                    zip(description_files, description_timestamps), 1
                ):
                    console.print(
                        f"  [dim]Frame {i}/{len(description_files)} at timestamp "
                        f"{timestamp:.1f}s: {desc_file_path.name}[/dim]"
                    )

                console.print(
                    f"[green]Generated {len(description_files)} frame descriptions[/green]"
                )

                frame_description_paths = []
                for desc_path in description_files:
                    try:
                        frame_description_paths.append(str(desc_path.relative_to(base_dir)))
                    except ValueError:
                        frame_description_paths.append(str(desc_path))

                entry.frame_descriptions = frame_description_paths

                if _prompt_yes_no("View frame descriptions now?", "Yes", "No"):
                    _view_frame_descriptions(entry, base_dir)

                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print(
                    "[yellow]No frame descriptions generated. "
                    "Video may be too short or transcript may not have timestamps.[/yellow]"
                )

        elif action in ("resummarize", "Re-run summary/quality (no extraction)"):
            if not entry.converted_to:
                console.print("[yellow]No transcript found. Run transcription first.[/yellow]")
                continue

            _offer_resummarization_with_quality(
                entry,
                base_dir,
                settings,
                ask_confirmation=False,
            )
            catalog.save(config_dir)
            console.print("[dim]Catalog saved.[/dim]")


def _show_image_entry_details(entry, base_dir: Path, settings: Settings) -> None:
    """Show selected image file details including description status."""
    from flavia.content.converters.image_converter import DEFAULT_VISION_MODEL

    console.print(f"\n[bold cyan]{entry.path}[/bold cyan]")

    converted_exists = False
    if entry.converted_to:
        converted_path = (base_dir / entry.converted_to).resolve()
        try:
            converted_path.relative_to(base_dir.resolve())
            converted_exists = converted_path.exists()
        except ValueError:
            converted_exists = False

    # Get current vision model
    vision_model = getattr(settings, "image_vision_model", None) or DEFAULT_VISION_MODEL

    details = Table(show_header=False, box=None)
    details.add_column("Field", style="dim")
    details.add_column("Value")
    details.add_row("Format", Path(entry.path).suffix.lstrip(".").upper())
    details.add_row("Size", _format_size(entry.size_bytes))
    details.add_row("Description file", entry.converted_to or "[dim](none)[/dim]")
    details.add_row(
        "Description exists", "[green]yes[/green]" if converted_exists else "[dim]no[/dim]"
    )
    details.add_row("Vision model", f"[cyan]{vision_model}[/cyan]")
    console.print(details)


def _show_media_entry_details(entry, base_dir: Path, settings: Settings) -> None:
    """Show selected audio/video details including transcription/summary status."""
    console.print(
        f"\n[bold cyan]{entry.path}[/bold cyan]  {_quality_badge(entry.extraction_quality)}"
    )

    converted_exists = False
    if entry.converted_to:
        converted_path = (base_dir / entry.converted_to).resolve()
        try:
            converted_path.relative_to(base_dir.resolve())
            converted_exists = converted_path.exists()
        except ValueError:
            converted_exists = False

    try:
        summary_model_ref = _get_summary_model_ref(settings)
        provider, model_id = settings.resolve_model_with_provider(summary_model_ref)
    except Exception:
        provider, model_id = None, str(_get_summary_model_ref(settings))
    provider_id = getattr(provider, "id", None) if provider else None
    active_model_ref = f"{provider_id}:{model_id}" if provider_id else str(model_id)

    details = Table(show_header=False, box=None)
    details.add_column("Field", style="dim")
    details.add_column("Value")
    details.add_row("Media type", entry.file_type)
    details.add_row("Format", Path(entry.path).suffix.lstrip(".").upper())
    details.add_row("Size", _format_size(entry.size_bytes))
    details.add_row("Transcript file", entry.converted_to or "[dim](none)[/dim]")
    details.add_row(
        "Transcript exists", "[green]yes[/green]" if converted_exists else "[dim]no[/dim]"
    )
    details.add_row(
        "Frame descriptions",
        (
            f"[green]{len(entry.frame_descriptions)}[/green]"
            if entry.frame_descriptions
            else "[dim]no[/dim]"
        ),
    )
    details.add_row("Summary", "[green]yes[/green]" if entry.summary else "[dim]no[/dim]")
    details.add_row("Extraction quality", _quality_badge(entry.extraction_quality))
    details.add_row("Summary model", f"[cyan]{active_model_ref}[/cyan]")
    console.print(details)

    if entry.summary:
        console.print(Panel(entry.summary, title="Summary", expand=False))
    else:
        console.print("[dim]No summary available for this file.[/dim]")


def _view_transcription(entry, base_dir: Path) -> None:
    """View generated transcript content."""
    if not entry.converted_to:
        console.print("[yellow]No transcript available.[/yellow]")
        return

    transcript_path = (base_dir / entry.converted_to).resolve()
    try:
        transcript_path.relative_to(base_dir.resolve())
    except ValueError:
        console.print("[red]Blocked unsafe path outside project directory.[/red]")
        return

    if not transcript_path.exists():
        console.print("[yellow]Transcript file not found.[/yellow]")
        return

    try:
        content = transcript_path.read_text(encoding="utf-8")
        console.print(Panel(content, title=f"Transcript: {entry.path}", expand=False))
    except Exception as e:
        console.print(f"[red]Failed to read transcript: {e}[/red]")


def _view_image_description(entry, base_dir: Path) -> None:
    """View the generated image description."""
    if not entry.converted_to:
        console.print("[yellow]No description available.[/yellow]")
        return

    desc_path = (base_dir / entry.converted_to).resolve()
    try:
        desc_path.relative_to(base_dir.resolve())
    except ValueError:
        console.print("[red]Blocked unsafe path outside project directory.[/red]")
        return

    if not desc_path.exists():
        console.print("[yellow]Description file not found.[/yellow]")
        return

    try:
        content = desc_path.read_text(encoding="utf-8")
        console.print(Panel(content, title=f"Description: {entry.path}", expand=False))
    except Exception as e:
        console.print(f"[red]Failed to read description: {e}[/red]")


def _view_frame_descriptions(entry, base_dir: Path) -> None:
    """View generated frame descriptions."""
    if not entry.frame_descriptions:
        console.print("[yellow]No frame descriptions available.[/yellow]")
        return

    console.print(f"\n[bold]Frame Descriptions ({len(entry.frame_descriptions)})[/bold]")

    for frame_desc_path_str in entry.frame_descriptions:
        frame_desc_path = (base_dir / frame_desc_path_str).resolve()
        try:
            frame_desc_path.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                f"[red]Blocked unsafe path outside project directory: {frame_desc_path_str}[/red]"
            )
            continue

        if not frame_desc_path.exists():
            console.print(
                f"[yellow]Frame description file not found: {frame_desc_path_str}[/yellow]"
            )
            continue

        try:
            content = frame_desc_path.read_text(encoding="utf-8")
            console.print(Panel(content, title=str(frame_desc_path_str), expand=False))
        except Exception as e:
            console.print(f"[red]Failed to read frame description: {e}[/red]")


def _select_vision_model(settings: Settings) -> bool:
    """Allow selecting another vision model for image analysis."""
    from flavia.content.converters.image_converter import (
        DEFAULT_VISION_MODEL,
        prompt_vision_model_selection,
    )

    selection = prompt_vision_model_selection(settings)
    if selection is None:
        return False

    settings.image_vision_model = selection
    console.print(
        f"[green]Vision model switched to:[/green] [cyan]{settings.image_vision_model}[/cyan]"
    )
    console.print("[dim]Note: This change applies to the current session only.[/dim]")
    console.print(f"[dim]To persist, set IMAGE_VISION_MODEL={selection} in your .env file.[/dim]")
    return True


def _suggest_vision_model_change(settings: Settings) -> None:
    """Suggest changing the vision model after a failure."""
    from flavia.content.converters.image_converter import DEFAULT_VISION_MODEL

    current_model = getattr(settings, "image_vision_model", None) or DEFAULT_VISION_MODEL
    console.print(f"\n[yellow]Current vision model: {current_model}[/yellow]")
    console.print("[dim]The model may not support vision or may be unavailable.[/dim]")

    if _prompt_yes_no("Would you like to select a different vision model?", "Yes", "No"):
        _select_vision_model(settings)


def _show_office_entry_details(entry, base_dir: Path, settings: Settings) -> None:
    """Show selected Office document details including conversion and summary metadata."""
    console.print(
        f"\n[bold cyan]{entry.path}[/bold cyan]  {_quality_badge(entry.extraction_quality)}"
    )

    converted_exists = False
    if entry.converted_to:
        converted_path = (base_dir / entry.converted_to).resolve()
        try:
            converted_path.relative_to(base_dir.resolve())
            converted_exists = converted_path.exists()
        except ValueError:
            converted_exists = False

    try:
        summary_model_ref = _get_summary_model_ref(settings)
        provider, model_id = settings.resolve_model_with_provider(summary_model_ref)
    except Exception:
        provider, model_id = None, str(_get_summary_model_ref(settings))
    provider_id = getattr(provider, "id", None) if provider else None
    active_model_ref = f"{provider_id}:{model_id}" if provider_id else str(model_id)

    details = Table(show_header=False, box=None)
    details.add_column("Field", style="dim")
    details.add_column("Value")
    details.add_row("Document type", entry.category or "unknown")
    details.add_row("Converted file", entry.converted_to or "[dim](none)[/dim]")
    details.add_row(
        "Converted exists", "[green]yes[/green]" if converted_exists else "[dim]no[/dim]"
    )
    details.add_row("Summary", "[green]yes[/green]" if entry.summary else "[dim]no[/dim]")
    details.add_row("Extraction quality", _quality_badge(entry.extraction_quality))
    details.add_row("Summary model", f"[cyan]{active_model_ref}[/cyan]")
    console.print(details)

    if entry.summary:
        console.print(Panel(entry.summary, title="Summary", expand=False))
    else:
        console.print("[dim]No summary available for this file.[/dim]")


def _show_pdf_entry_details(entry, base_dir: Path, settings: Settings) -> None:
    """Show selected PDF details including conversion and summary metadata."""
    console.print(
        f"\n[bold cyan]{entry.path}[/bold cyan]  {_quality_badge(entry.extraction_quality)}"
    )

    converted_exists = False
    if entry.converted_to:
        converted_path = (base_dir / entry.converted_to).resolve()
        try:
            converted_path.relative_to(base_dir.resolve())
            converted_exists = converted_path.exists()
        except ValueError:
            converted_exists = False

    try:
        summary_model_ref = _get_summary_model_ref(settings)
        provider, model_id = settings.resolve_model_with_provider(summary_model_ref)
    except Exception:
        provider, model_id = None, str(_get_summary_model_ref(settings))
    provider_id = getattr(provider, "id", None) if provider else None
    active_model_ref = f"{provider_id}:{model_id}" if provider_id else str(model_id)

    details = Table(show_header=False, box=None)
    details.add_column("Field", style="dim")
    details.add_column("Value")
    details.add_row("Converted file", entry.converted_to or "[dim](none)[/dim]")
    details.add_row(
        "Converted exists", "[green]yes[/green]" if converted_exists else "[dim]no[/dim]"
    )
    details.add_row("Summary", "[green]yes[/green]" if entry.summary else "[dim]no[/dim]")
    details.add_row("Extraction quality", _quality_badge(entry.extraction_quality))
    details.add_row("Summary model", f"[cyan]{active_model_ref}[/cyan]")
    console.print(details)

    if entry.summary:
        console.print(Panel(entry.summary, title="Summary", expand=False))
    else:
        console.print("[dim]No summary available for this file.[/dim]")


def _prompt_yes_no(prompt: str, yes_title: str = "Yes", no_title: str = "No") -> bool:
    """Prompt for a yes/no choice and return True only on yes."""
    try:
        import questionary as _q

        choices = [
            _q.Choice(title=yes_title, value=True),
            _q.Choice(title=no_title, value=False),
        ]
    except ImportError:
        choices = [yes_title, no_title]

    choice = q_select(prompt, choices=choices)
    return choice in (True, yes_title, "yes", "y", "Y")


def _select_model_for_summary(settings: Settings) -> bool:
    """Allow selecting another model for summary generation in current session."""
    choices = []
    current_summary_ref = _get_summary_model_ref(settings)
    default_choice = current_summary_ref
    provider_map = getattr(getattr(settings, "providers", None), "providers", {})
    has_provider_map = isinstance(provider_map, dict) and bool(provider_map)

    if has_provider_map:
        for provider in provider_map.values():
            for model in provider.models:
                ref = f"{provider.id}:{model.id}"
                label = f"{provider.name} ({provider.id}) - {model.name} ({model.id})"
                choices.append((label, ref))

        provider, model_id = settings.resolve_model_with_provider(current_summary_ref)
        if provider:
            default_choice = f"{provider.id}:{model_id}"
    else:
        for model in settings.models:
            choices.append((f"{model.name} ({model.id})", model.id))
        default_choice = str(settings.resolve_model(current_summary_ref))

    if not choices:
        console.print("[yellow]No models available to select.[/yellow]")
        return False

    try:
        import questionary as _q

        model_choices = [_q.Choice(title=label, value=ref) for label, ref in choices]
        model_choices.append(_q.Choice(title="Cancel", value="__cancel__"))
    except ImportError:
        model_choices = [label for label, _ in choices] + ["Cancel"]

    selection = q_select(
        "Select a model for summary/quality:",
        choices=model_choices,
        default=default_choice,
    )
    if selection in (None, "__cancel__", "Cancel"):
        return False

    if selection not in {ref for _, ref in choices}:
        reverse = {label: ref for label, ref in choices}
        selection = reverse.get(selection, selection)

    settings.summary_model = str(selection)
    console.print(
        f"[green]Summary model switched to:[/green] [cyan]{settings.summary_model}[/cyan]"
    )
    return True


def _resolve_summary_runtime(
    settings: Settings,
    model_ref_override: Optional[str] = None,
) -> tuple[str, str, str, str, Optional[dict[str, str]]]:
    """Resolve active summary model and runtime credentials."""
    summary_model_ref = model_ref_override or _get_summary_model_ref(settings)
    provider, model_id = settings.resolve_model_with_provider(summary_model_ref)
    if provider:
        provider_id = getattr(provider, "id", None)
        model_ref = f"{provider_id}:{model_id}" if provider_id else str(model_id)
        headers = provider.headers if provider.headers else None
        return model_ref, model_id, provider.api_key, provider.api_base_url, headers

    return (
        str(summary_model_ref),
        model_id,
        settings.api_key,
        settings.api_base_url,
        None,
    )


def _get_summary_model_ref(settings: Settings) -> str:
    """Return summary model override when configured, else default model."""
    summary_ref = getattr(settings, "summary_model", None)
    if isinstance(summary_ref, str) and summary_ref.strip():
        return summary_ref.strip()
    return str(settings.default_model)


def _should_auto_fallback_to_instruct(call_info: dict) -> bool:
    """Return True when empty response appears caused by token-length truncation."""
    if call_info.get("status") != "empty_after_retry":
        return False
    return (
        call_info.get("first_finish_reason") == "length"
        and call_info.get("retry_finish_reason") == "length"
    )


def _find_instruct_fallback_model(settings: Settings, current_model_ref: str) -> Optional[str]:
    """Find a likely non-reasoning/instruct model candidate for summary fallback."""
    provider_map = getattr(getattr(settings, "providers", None), "providers", {})
    if not isinstance(provider_map, dict) or not provider_map:
        return None

    # Prefer switching within the same provider first.
    current_provider = None
    if ":" in current_model_ref:
        maybe_provider = current_model_ref.split(":", 1)[0]
        if maybe_provider in provider_map:
            current_provider = maybe_provider

    provider_order = []
    if current_provider:
        provider_order.append(current_provider)
    provider_order.extend(pid for pid in provider_map.keys() if pid != current_provider)

    def _score_model(model_id: str, model_name: str, model_desc: str) -> int:
        haystack = f"{model_id} {model_name} {model_desc}".lower()
        score = 0
        if "instruct" in haystack:
            score += 100
        if "reason" in haystack or "think" in haystack:
            score -= 50
        if "chat" in haystack:
            score += 10
        return score

    best_ref: Optional[str] = None
    best_score: int = -10_000
    for provider_id in provider_order:
        provider = provider_map[provider_id]
        for model in provider.models:
            ref = f"{provider.id}:{model.id}"
            if ref == current_model_ref:
                continue
            score = _score_model(model.id, model.name, model.description)
            if score > best_score:
                best_score = score
                best_ref = ref

    if best_score <= 0:
        return None
    return best_ref


def _offer_resummarization_with_quality(
    entry,
    base_dir: Path,
    settings: Settings,
    ask_confirmation: bool = True,
) -> None:
    """Optionally re-summarize a converted file and store extraction quality."""
    if ask_confirmation and not _prompt_yes_no("Re-summarize now?", "Yes", "No"):
        return

    from flavia.content.summarizer import get_last_llm_call_info, summarize_file_with_quality

    auto_fallback_used = False
    while True:
        model_ref, model_id, api_key, api_base_url, headers = _resolve_summary_runtime(settings)
        console.print(f"[dim]Summary model: {model_ref}[/dim]")

        if not api_key:
            console.print(
                "[yellow]Summary/quality skipped: no API key configured for the active model provider.[/yellow]"
            )
            if _prompt_yes_no(
                "Select another model now?",
                "Yes, choose another model",
                "No",
            ) and _select_model_for_summary(settings):
                continue
            return

        summary, quality = summarize_file_with_quality(
            entry,
            base_dir,
            api_key=api_key,
            api_base_url=api_base_url,
            model=model_id,
            headers=headers,
        )
        if summary:
            entry.summary = summary
        if quality:
            entry.extraction_quality = quality

        if summary or quality:
            console.print(
                f"[green]Re-summarized.[/green] Quality: {_quality_badge(entry.extraction_quality)}"
            )
            return

        call_info = get_last_llm_call_info()
        if not auto_fallback_used and _should_auto_fallback_to_instruct(call_info):
            fallback_model = _find_instruct_fallback_model(settings, model_ref)
            if fallback_model:
                console.print(
                    "[yellow]Detected length-capped empty output. "
                    f"Retrying automatically with instruct model [cyan]{fallback_model}[/cyan].[/yellow]"
                )
                settings.summary_model = fallback_model
                auto_fallback_used = True
                continue

        console.print(
            "[yellow]Re-summarization failed: no summary/quality returned by the LLM.[/yellow]"
        )
        if _prompt_yes_no(
            "Try another model?",
            "Yes, choose model and retry",
            "No",
        ) and _select_model_for_summary(settings):
            continue
        return


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"
