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
        console.print(
            "[yellow]No catalog found. Run `flavia --init` to create one.[/yellow]"
        )
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
            _show_online_sources(catalog)
        elif choice == "6":
            _add_online_source(catalog, config_dir)
        elif choice == "7":
            _manage_pdf_files(catalog, config_dir, settings)
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

        for file_type, count in sorted(
            stats["by_type"].items(), key=lambda x: -x[1]
        ):
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

        for src_type, count in sorted(
            stats["by_source_type"].items(), key=lambda x: -x[1]
        ):
            src_table.add_row(src_type, str(count))
        console.print(src_table)


def _browse_files(catalog: ContentCatalog) -> None:
    """Display files in a tree view."""
    if not catalog.directory_tree:
        console.print("[yellow]No directory structure available.[/yellow]")
        return

    console.print("\n[bold]Directory Structure[/bold]")

    tree = Tree(
        f"[bold]{catalog.directory_tree.name}[/bold] "
        f"({catalog.directory_tree.file_count} files)"
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
    files_with_summary = [
        e for e in catalog.files.values()
        if e.summary and e.status != "missing"
    ]

    if not files_with_summary:
        console.print("[yellow]No files have summaries yet.[/yellow]")
        return

    console.print(f"\n[bold]Files with Summaries ({len(files_with_summary)}):[/bold]")

    for entry in sorted(files_with_summary, key=lambda e: e.path)[:30]:
        badge = _quality_badge(entry.extraction_quality)
        console.print(f"\n[cyan]{entry.path}[/cyan]  {badge}")
        console.print(Panel(entry.summary, expand=False))


def _show_online_sources(catalog: ContentCatalog) -> None:
    """Display online sources in the catalog."""
    online_sources = catalog.get_online_sources()

    if not online_sources:
        console.print("[yellow]No online sources in catalog.[/yellow]")
        return

    console.print(f"\n[bold]Online Sources ({len(online_sources)}):[/bold]")

    table = Table(show_header=True)
    table.add_column("Type", style="dim")
    table.add_column("URL", style="cyan", max_width=50)
    table.add_column("Status", style="yellow")
    table.add_column("Title", max_width=30)

    for entry in online_sources:
        title = entry.source_metadata.get("title", entry.name)[:30]
        url = (entry.source_url or "")[:50]
        if len(entry.source_url or "") > 50:
            url += "..."
        table.add_row(
            entry.source_type,
            url,
            entry.fetch_status,
            title,
        )

    console.print(table)

    # Show stats
    pending = sum(1 for e in online_sources if e.fetch_status == "pending")
    completed = sum(1 for e in online_sources if e.fetch_status == "completed")
    not_impl = sum(1 for e in online_sources if e.fetch_status == "not_implemented")
    failed = sum(1 for e in online_sources if e.fetch_status == "failed")

    console.print(f"\n[dim]Pending: {pending} | Completed: {completed} | "
                  f"Not Implemented: {not_impl} | Failed: {failed}[/dim]")


def _add_online_source(catalog: ContentCatalog, config_dir: Path) -> None:
    """Add a new online source to the catalog."""
    console.print("\n[bold]Add Online Source[/bold]")
    console.print("[dim]Supported: YouTube videos, web pages[/dim]")
    console.print("[yellow]Note: Actual fetching/conversion is not yet implemented.[/yellow]")

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

    entry = catalog.add_online_source(url)

    if entry is None:
        console.print("[red]Could not add source. Unsupported URL type.[/red]")
        return

    console.print(f"\n[green]Added {entry.source_type} source:[/green]")
    console.print(f"  Path: {entry.path}")
    console.print(f"  Status: {entry.fetch_status}")

    if entry.fetch_status == "not_implemented":
        console.print(
            "\n[yellow]This source type is not yet implemented. "
            "The URL has been saved for future processing.[/yellow]"
        )

    # Save catalog
    catalog.save(config_dir)
    console.print("[dim]Catalog saved.[/dim]")


def _manage_pdf_files(catalog: ContentCatalog, config_dir: Path, settings: Settings) -> None:
    """Interactive PDF file manager with OCR support."""
    import os

    pdf_files = [
        e for e in catalog.files.values()
        if e.category == "pdf" and e.status != "missing"
    ]

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

        # Show details
        console.print(f"\n[bold cyan]{entry.path}[/bold cyan]  {_quality_badge(entry.extraction_quality)}")
        if entry.summary:
            console.print(Panel(entry.summary, title="Summary", expand=False))
        if entry.converted_to:
            console.print(f"[dim]Converted to: {entry.converted_to}[/dim]")

        # Action menu
        try:
            import questionary as _q
            action_choices = [
                _q.Choice(title="Run full OCR (Mistral API)", value="ocr"),
                _q.Choice(title="Extract text (simple)", value="simple"),
                _q.Choice(title="Back", value="back"),
            ]
        except ImportError:
            action_choices = ["Run full OCR (Mistral API)", "Extract text (simple)", "Back"]

        action = q_select("Action:", choices=action_choices)

        if action in (None, "back", "Back"):
            continue

        base_dir = config_dir.parent
        converted_dir = base_dir / ".converted"
        source = (base_dir / entry.path).resolve()
        try:
            source.relative_to(base_dir.resolve())
        except ValueError:
            console.print(
                "[red]Blocked unsafe path outside project directory in catalog entry.[/red]"
            )
            continue

        if action in ("ocr", "Run full OCR (Mistral API)"):
            if not os.environ.get("MISTRAL_API_KEY"):
                console.print(
                    "[red]MISTRAL_API_KEY environment variable is not set. "
                    "Export it before running OCR.[/red]"
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

                # Offer re-summarization
                provider, model_id = settings.resolve_model_with_provider(settings.default_model)
                if provider and provider.api_key:
                    try:
                        import questionary as _q2
                        resummarize_choices = [
                            _q2.Choice(title="Yes, re-summarize with quality assessment", value="yes"),
                            _q2.Choice(title="No", value="no"),
                        ]
                    except ImportError:
                        resummarize_choices = ["Yes, re-summarize with quality assessment", "No"]

                    do_resummary = q_select("Re-summarize now?", choices=resummarize_choices)
                    if do_resummary in ("yes", "Yes, re-summarize with quality assessment"):
                        from flavia.content.summarizer import summarize_file_with_quality
                        summary, quality = summarize_file_with_quality(
                            entry,
                            base_dir,
                            api_key=provider.api_key,
                            api_base_url=provider.api_base_url,
                            model=model_id,
                            headers=provider.headers if provider.headers else None,
                        )
                        if summary:
                            entry.summary = summary
                        if quality:
                            entry.extraction_quality = quality
                        console.print(f"[green]Re-summarized.[/green] Quality: {_quality_badge(entry.extraction_quality)}")

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
                catalog.save(config_dir)
                console.print("[dim]Catalog saved.[/dim]")
            else:
                console.print("[red]Extraction failed.[/red]")


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
