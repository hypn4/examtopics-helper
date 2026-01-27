"""Exporters for various output formats."""

from examtopics.exporters.base import BaseExporter
from examtopics.exporters.html import HTMLExporter
from examtopics.exporters.markdown import MarkdownExporter

# PDF exporter requires WeasyPrint which needs system libraries (pango, gobject, etc.)
try:
    from examtopics.exporters.pdf import PDFExporter

    PDF_AVAILABLE = True
except (ImportError, OSError):
    PDFExporter = None  # type: ignore
    PDF_AVAILABLE = False

__all__ = [
    "BaseExporter",
    "HTMLExporter",
    "MarkdownExporter",
    "PDFExporter",
    "PDF_AVAILABLE",
]
