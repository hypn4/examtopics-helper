"""Pydantic data models for ExamTopics questions and exams."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class VotedAnswer(BaseModel):
    """Community vote result for an answer."""

    answer: str
    vote_count: int
    vote_percentage: float = 0.0
    is_most_voted: bool = False


class Choice(BaseModel):
    """A single choice option for a question."""

    label: str  # A, B, C, D...
    text: str  # Choice content
    image_url: str | None = None  # Image URL for image-based choices


class Discussion(BaseModel):
    """A single discussion comment."""

    comment_id: int
    username: str
    date: str  # "Sun 22 Sep 2024 14:59"
    date_relative: str  # "1 year, 4 months ago"
    selected_answer: str | None = None  # "A", "B", etc.
    content: str
    upvotes: int = 0
    is_highly_voted: bool = False
    is_most_recent: bool = False
    replies: list[Discussion] = Field(default_factory=list)


class Question(BaseModel):
    """A single exam question with answers and community votes."""

    number: int
    topic: int | None = None
    question_id: int | None = None  # ID for fetching discussions
    text: str
    choices: list[Choice]
    correct_answer: str  # Official answer (e.g., "A", "AB", "BCD")
    community_votes: list[VotedAnswer] = Field(default_factory=list)
    discussion_count: int = 0
    discussions: list[Discussion] = Field(default_factory=list)


class Exam(BaseModel):
    """Complete exam with all questions."""

    provider: str  # amazon, microsoft, google...
    code: str  # aws-certified-devops-engineer-professional-dop-c02
    title: str  # AWS Certified DevOps Engineer - Professional DOP-C02
    total_questions: int
    questions: list[Question]
    extracted_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self, indent: int = 2) -> str:
        """Export exam to JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json_file(cls, path: Path) -> "Exam":
        """Load exam from JSON file."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
