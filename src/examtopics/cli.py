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
from examtopics.scraper import ExamTopicsScraper, parse_cookie_string

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
    console.print(
        Panel(
            f"[bold]Provider:[/bold] {provider}\n"
            f"[bold]Exam Code:[/bold] {exam_code}\n"
            f"[bold]Output:[/bold] {output_dir.absolute()}\n"
            f"[bold]Formats:[/bold] {', '.join(f.value for f in formats)}",
            title="ExamTopics Extractor",
            border_style="blue",
        )
    )

    # Create scraper and run
    scraper = ExamTopicsScraper(cookies=cookies, delay=delay)

    try:
        exam_data = asyncio.run(scraper.scrape_exam(provider, exam_code))
    except Exception as e:
        console.print(f"[red]Error scraping exam: {e}[/red]")
        raise typer.Exit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export to requested formats
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
                json_path = output_dir / f"{provider}_{exam_code}.json"
                json_path.write_text(exam_data.to_json(), encoding="utf-8")
                exported_files.append(("JSON", json_path))

        except Exception as e:
            console.print(
                f"[yellow]Warning: Failed to export {fmt.value}: {e}[/yellow]"
            )

    # Show results
    if exported_files:
        table = Table(title="Exported Files", show_header=True)
        table.add_column("Format", style="cyan")
        table.add_column("Path", style="green")

        for fmt_name, path in exported_files:
            table.add_row(fmt_name, str(path))

        console.print()
        console.print(table)
        console.print(
            f"\n[green]Successfully exported {len(exam_data.questions)} questions![/green]"
        )
    else:
        console.print("[red]No files were exported[/red]")
        raise typer.Exit(1)


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
