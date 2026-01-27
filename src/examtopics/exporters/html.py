"""HTML exporter using Jinja2 templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader, select_autoescape

from examtopics.exporters.base import BaseExporter
from examtopics.models import Exam


class HTMLExporter(BaseExporter):
    """Export exam to HTML format."""

    @property
    def extension(self) -> str:
        return "html"

    def __init__(self, template_name: str = "exam.html.j2"):
        """Initialize HTML exporter.

        Args:
            template_name: Name of the Jinja2 template file
        """
        self.template_name = template_name
        # Try package loader first, fall back to file loader
        try:
            self.env = Environment(
                loader=PackageLoader("examtopics", "templates"),
                autoescape=select_autoescape(["html", "xml"]),
            )
        except Exception:
            # Fallback to file system loader
            template_dir = Path(__file__).parent.parent / "templates"
            self.env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(["html", "xml"]),
            )

    def export(self, exam: Exam, output_path: Path) -> Path:
        """Export exam to HTML file.

        Args:
            exam: Exam object to export
            output_path: Directory or file path for output

        Returns:
            Path to the created HTML file
        """
        if output_path.is_dir():
            output_path = self.get_output_path(exam, output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        template = self.env.get_template(self.template_name)
        html_content = template.render(exam=exam)

        output_path.write_text(html_content, encoding="utf-8")
        return output_path
