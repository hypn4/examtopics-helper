"""Pydantic data models for ExamTopics questions and exams."""

from datetime import datetime

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


class Question(BaseModel):
    """A single exam question with answers and community votes."""

    number: int
    topic: int | None = None
    text: str
    choices: list[Choice]
    correct_answer: str  # Official answer (e.g., "A", "AB", "BCD")
    community_votes: list[VotedAnswer] = Field(default_factory=list)
    discussion_count: int = 0


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
