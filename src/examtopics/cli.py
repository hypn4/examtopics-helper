"""CLI interface for ExamTopics Helper using Typer."""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from examtopics import __version__
from examtopics.exporters import (
    HTMLExporter,
    MarkdownExporter,
    PDFExporter,
    PDF_AVAILABLE,
)
from examtopics.models import Exam
from examtopics.scraper import ExamTopicsScraper, LoadingMode, parse_cookie_string

load_dotenv()  # Load environment variables from .env file

app = typer.Typer(
    name="examtopics",
    help="Extract and export ExamTopics exam questions.",
    add_completion=False,
)
console = Console()


class OutputFormat(str, Enum):
    """Supported output formats."""

    html = "html"
    pdf = "pdf"
    markdown = "markdown"
    json = "json"


# Check if watchfiles is available
try:
    import watchfiles

    WATCH_AVAILABLE = True
except ImportError:
    WATCH_AVAILABLE = False


def _export_exam(
    exam_data: Exam,
    output_dir: Path,
    formats: list[OutputFormat],
    console: Console,
) -> list[tuple[str, Path]]:
    """Export exam data to the specified formats.

    Returns a list of (format_name, path) tuples for successfully exported files.
    """
    exported_files: list[tuple[str, Path]] = []

    for fmt in formats:
        try:
            if fmt == OutputFormat.html:
                exporter = HTMLExporter()
                path = exporter.export(exam_data, output_dir)
                exported_files.append(("HTML", path))

            elif fmt == OutputFormat.pdf:
                if not PDF_AVAILABLE:
                    console.print(
                        "[yellow]Warning: PDF export requires WeasyPrint system libraries.[/yellow]"
                    )
                    console.print(
                        "[yellow]Install with: brew install pango (macOS) or apt install libpango-1.0-0 (Linux)[/yellow]"
                    )
                    continue
                exporter = PDFExporter()
                path = exporter.export(exam_data, output_dir)
                exported_files.append(("PDF", path))

            elif fmt == OutputFormat.markdown:
                exporter = MarkdownExporter()
                path = exporter.export(exam_data, output_dir)
                exported_files.append(("Markdown", path))

            elif fmt == OutputFormat.json:
                json_path = (
                    output_dir / f"{exam_data.provider}_{exam_data.code}.json"
                )
                json_path.write_text(exam_data.to_json(), encoding="utf-8")
                exported_files.append(("JSON", json_path))

        except Exception as e:
            console.print(
                f"[yellow]Warning: Failed to export {fmt.value}: {e}[/yellow]"
            )

    return exported_files


def _print_export_results(
    exported_files: list[tuple[str, Path]],
    question_count: int,
    console: Console,
) -> None:
    """Print a table of exported files."""
    if exported_files:
        table = Table(title="Exported Files", show_header=True)
        table.add_column("Format", style="cyan")
        table.add_column("Path", style="green")

        for fmt_name, path in exported_files:
            table.add_row(fmt_name, str(path))

        console.print()
        console.print(table)
        console.print(
            f"\n[green]Successfully exported {question_count} questions![/green]"
        )


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"examtopics-helper v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """ExamTopics Helper - Extract and export exam questions."""
    pass


@app.command()
def extract(
    exam: Annotated[
        str,
        typer.Option(
            "--exam",
            "-e",
            help="Exam path: provider/exam-code (e.g., amazon/aws-certified-devops-engineer-professional-dop-c02)",
        ),
    ],
    cookie: Annotated[
        Optional[str],
        typer.Option(
            "--cookie",
            "-c",
            envvar="EXAMTOPICS_COOKIE",
            help="Session cookie string (or set EXAMTOPICS_COOKIE env var)",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            envvar="EXAMTOPICS_OUTPUT",
            help="Output directory for generated files (or set EXAMTOPICS_OUTPUT env var)",
        ),
    ] = Path("output"),
    formats: Annotated[
        Optional[list[OutputFormat]],
        typer.Option(
            "--format",
            "-f",
            envvar="EXAMTOPICS_FORMAT",
            help="Output formats: html, pdf, markdown, json (or set EXAMTOPICS_FORMAT env var)",
        ),
    ] = None,
    delay: Annotated[
        float,
        typer.Option(
            "--delay",
            "-d",
            envvar="EXAMTOPICS_DELAY",
            help="Delay between page requests in seconds (or set EXAMTOPICS_DELAY env var)",
        ),
    ] = 1.0,
    mode: Annotated[
        LoadingMode,
        typer.Option(
            "--mode",
            "-m",
            envvar="EXAMTOPICS_MODE",
            help="Loading mode: paginated (default), bulk, range, or auto (or set EXAMTOPICS_MODE env var)",
        ),
    ] = LoadingMode.PAGINATED,
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            "-b",
            envvar="EXAMTOPICS_BATCH_SIZE",
            help="Batch size for range mode (or set EXAMTOPICS_BATCH_SIZE env var)",
        ),
    ] = 100,
    include_discussions: Annotated[
        bool,
        typer.Option(
            "--discussions",
            envvar="EXAMTOPICS_DISCUSSIONS",
            help="Include discussion comments (slower, requires additional requests)",
        ),
    ] = False,
) -> None:
    """Extract exam questions from ExamTopics and export to various formats.

    Example:
        examtopics extract --exam "amazon/dop-c02" --cookie "session=xxx" -f html -f pdf
    """
    # Parse exam path
    parts = exam.strip("/").split("/")
    if len(parts) != 2:
        console.print(
            "[red]Error: Exam path must be in format 'provider/exam-code'[/red]"
        )
        raise typer.Exit(1)

    provider, exam_code = parts

    # Default to all formats if none specified
    if not formats:
        formats = [OutputFormat.html, OutputFormat.markdown, OutputFormat.json]
        if PDF_AVAILABLE:
            formats.insert(1, OutputFormat.pdf)

    # Parse cookies
    if not cookie:
        console.print(
            "[red]Error: Cookie required. Use --cookie or set EXAMTOPICS_COOKIE env var[/red]"
        )
        raise typer.Exit(1)

    cookies = parse_cookie_string(cookie)
    if not cookies:
        console.print("[red]Error: Invalid cookie string[/red]")
        raise typer.Exit(1)

    # Show configuration
    mode_info = f"{mode.value}"
    if mode == LoadingMode.RANGE:
        mode_info += f" (batch size: {batch_size})"
    elif mode == LoadingMode.AUTO:
        mode_info += " (will try bulk → range → paginated)"

    console.print(
        Panel(
            f"[bold]Provider:[/bold] {provider}\n"
            f"[bold]Exam Code:[/bold] {exam_code}\n"
            f"[bold]Output:[/bold] {output_dir.absolute()}\n"
            f"[bold]Formats:[/bold] {', '.join(f.value for f in formats)}\n"
            f"[bold]Mode:[/bold] {mode_info}\n"
            f"[bold]Delay:[/bold] {delay}s\n"
            f"[bold]Discussions:[/bold] {'Yes' if include_discussions else 'No'}",
            title="ExamTopics Extractor",
            border_style="blue",
        )
    )

    # Create scraper and run
    scraper = ExamTopicsScraper(cookies=cookies, delay=delay)

    try:
        exam_data = asyncio.run(
            scraper.scrape_exam(
                provider,
                exam_code,
                mode=mode,
                batch_size=batch_size,
                include_discussions=include_discussions,
            )
        )
    except Exception as e:
        console.print(f"[red]Error scraping exam: {e}[/red]")
        raise typer.Exit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export to requested formats
    exported_files = _export_exam(exam_data, output_dir, formats, console)

    # Show results
    if exported_files:
        _print_export_results(exported_files, len(exam_data.questions), console)
    else:
        console.print("[red]No files were exported[/red]")
        raise typer.Exit(1)


@app.command()
def render(
    input_file: Annotated[
        Path,
        typer.Option(
            "--input",
            "-i",
            help="Path to JSON file from previous extraction",
        ),
    ],
    output_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output directory (default: same as input file)",
        ),
    ] = None,
    formats: Annotated[
        Optional[list[OutputFormat]],
        typer.Option(
            "--format",
            "-f",
            help="Output formats: html, pdf, markdown (can be specified multiple times)",
        ),
    ] = None,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="Watch template files and re-render on changes",
        ),
    ] = False,
) -> None:
    """Re-render exam from existing JSON file without scraping.

    Useful when you only want to modify the template and regenerate output
    without re-scraping the exam data.

    Example:
        examtopics render -i output/amazon_dop-c02.json -f html
        examtopics render -i output/amazon_dop-c02.json -f html --watch
    """
    # Validate input file
    if not input_file.exists():
        console.print(f"[red]Error: Input file not found: {input_file}[/red]")
        raise typer.Exit(1)

    if not input_file.suffix == ".json":
        console.print("[red]Error: Input file must be a JSON file[/red]")
        raise typer.Exit(1)

    # Default output directory to input file's directory
    if output_dir is None:
        output_dir = input_file.parent

    # Default to HTML if no formats specified
    if not formats:
        formats = [OutputFormat.html]

    # Filter out JSON format as it doesn't make sense for render
    formats = [f for f in formats if f != OutputFormat.json]
    if not formats:
        console.print(
            "[yellow]Warning: JSON format is not applicable for render command. Use html, pdf, or markdown.[/yellow]"
        )
        raise typer.Exit(1)

    # Load exam data from JSON
    try:
        exam_data = Exam.from_json_file(input_file)
    except Exception as e:
        console.print(f"[red]Error loading JSON file: {e}[/red]")
        raise typer.Exit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Show configuration
    console.print(
        Panel(
            f"[bold]Input:[/bold] {input_file}\n"
            f"[bold]Output:[/bold] {output_dir.absolute()}\n"
            f"[bold]Formats:[/bold] {', '.join(f.value for f in formats)}\n"
            f"[bold]Watch:[/bold] {'Yes' if watch else 'No'}\n"
            f"[bold]Exam:[/bold] {exam_data.title}\n"
            f"[bold]Questions:[/bold] {len(exam_data.questions)}",
            title="ExamTopics Renderer",
            border_style="blue",
        )
    )

    # Initial render
    exported_files = _export_exam(exam_data, output_dir, formats, console)

    if exported_files:
        _print_export_results(exported_files, len(exam_data.questions), console)
    else:
        console.print("[red]No files were exported[/red]")
        raise typer.Exit(1)

    # Watch mode
    if watch:
        if not WATCH_AVAILABLE:
            console.print(
                "[red]Error: Watch mode requires watchfiles package.[/red]"
            )
            console.print(
                "[yellow]Install with: uv pip install examtopics-helper[watch][/yellow]"
            )
            raise typer.Exit(1)

        # Get template directory
        template_dir = Path(__file__).parent / "templates"

        console.print(
            f"\n[cyan]Watching for template changes in {template_dir}...[/cyan]"
        )
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            for changes in watchfiles.watch(template_dir):
                changed_files = [str(Path(c[1]).name) for c in changes]
                console.print(
                    f"[cyan]Template changed: {', '.join(changed_files)}[/cyan]"
                )
                console.print("[cyan]Re-rendering...[/cyan]")

                exported_files = _export_exam(exam_data, output_dir, formats, console)
                if exported_files:
                    _print_export_results(
                        exported_files, len(exam_data.questions), console
                    )
                else:
                    console.print("[yellow]Warning: No files were exported[/yellow]")
        except KeyboardInterrupt:
            console.print("\n[green]Watch mode stopped.[/green]")


@app.command()
def info(
    exam: Annotated[
        str,
        typer.Option(
            "--exam",
            "-e",
            help="Exam path: provider/exam-code",
        ),
    ],
    cookie: Annotated[
        Optional[str],
        typer.Option(
            "--cookie",
            "-c",
            envvar="EXAMTOPICS_COOKIE",
            help="Session cookie string (or set EXAMTOPICS_COOKIE env var)",
        ),
    ] = None,
) -> None:
    """Show information about an exam without extracting questions."""
    parts = exam.strip("/").split("/")
    if len(parts) != 2:
        console.print(
            "[red]Error: Exam path must be in format 'provider/exam-code'[/red]"
        )
        raise typer.Exit(1)

    provider, exam_code = parts

    if not cookie:
        console.print(
            "[red]Error: Cookie required. Use --cookie or set EXAMTOPICS_COOKIE env var[/red]"
        )
        raise typer.Exit(1)

    cookies = parse_cookie_string(cookie)
    if not cookies:
        console.print("[red]Error: Invalid cookie string[/red]")
        raise typer.Exit(1)

    scraper = ExamTopicsScraper(cookies=cookies)

    try:
        # Just fetch first page for info
        import httpx

        url = scraper._build_url(provider, exam_code, 1)
        console.print(f"[cyan]Fetching info from {url}...[/cyan]")

        with httpx.Client(cookies=cookies, timeout=30.0) as client:
            response = client.get(url, headers=scraper.headers)
            response.raise_for_status()

            total = scraper._get_total_questions(response.text)
            title = scraper._get_exam_title(response.text)

            console.print(
                Panel(
                    f"[bold]Title:[/bold] {title}\n"
                    f"[bold]Provider:[/bold] {provider}\n"
                    f"[bold]Exam Code:[/bold] {exam_code}\n"
                    f"[bold]Total Questions:[/bold] {total}\n"
                    f"[bold]Pages:[/bold] {(total + 49) // 50}",
                    title="Exam Information",
                    border_style="green",
                )
            )

    except Exception as e:
        console.print(f"[red]Error fetching exam info: {e}[/red]")
        raise typer.Exit(1)


def cli() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli()
