"""Base exporter abstract class."""

from abc import ABC, abstractmethod
from pathlib import Path

from examtopics.models import Exam


class BaseExporter(ABC):
    """Abstract base class for exam exporters."""

    @property
    @abstractmethod
    def extension(self) -> str:
        """File extension for this exporter (e.g., 'html', 'pdf')."""
        pass

    @abstractmethod
    def export(self, exam: Exam, output_path: Path) -> Path:
        """Export exam data to a file.

        Args:
            exam: Exam object to export
            output_path: Directory or file path for output

        Returns:
            Path to the created file
        """
        pass

    def get_output_path(self, exam: Exam, output_dir: Path) -> Path:
        """Generate output file path based on exam info.

        Args:
            exam: Exam object
            output_dir: Output directory

        Returns:
            Full path for output file
        """
        filename = f"{exam.provider}_{exam.code}.{self.extension}"
        return output_dir / filename
