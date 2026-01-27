"""PDF exporter using WeasyPrint."""

from pathlib import Path

from weasyprint import HTML

from examtopics.exporters.base import BaseExporter
from examtopics.exporters.html import HTMLExporter
from examtopics.models import Exam


class PDFExporter(BaseExporter):
    """Export exam to PDF format using WeasyPrint."""

    @property
    def extension(self) -> str:
        return "pdf"

    def __init__(self, template_name: str = "exam.html.j2"):
        """Initialize PDF exporter.

        Args:
            template_name: Name of the Jinja2 template file (uses HTML template)
        """
        self.html_exporter = HTMLExporter(template_name)

    def export(self, exam: Exam, output_path: Path) -> Path:
        """Export exam to PDF file.

        Args:
            exam: Exam object to export
            output_path: Directory or file path for output

        Returns:
            Path to the created PDF file
        """
        if output_path.is_dir():
            output_path = self.get_output_path(exam, output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate HTML content first
        template = self.html_exporter.env.get_template(self.html_exporter.template_name)
        html_content = template.render(exam=exam)

        # Convert HTML to PDF
        html = HTML(string=html_content)
        html.write_pdf(output_path)

        return output_path
