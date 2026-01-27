"""Scraper for ExamTopics exam questions using httpx and selectolax."""

import asyncio
import json
import re
from typing import Any

import httpx
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from selectolax.parser import HTMLParser

from examtopics.models import Choice, Exam, Question, VotedAnswer

console = Console()

# Pattern to match embedded JSON vote data
VOTE_JSON_PATTERN = re.compile(r'\[{"voted_answers".*?\}\]')
# Pattern to match choice lines that got concatenated (e.g., "A.Some text...B.Other text")
CHOICE_CONCAT_PATTERN = re.compile(r'[A-F]\.[A-Z][^.]*?(?=[A-F]\.|Reveal Solution|$)')
# Pattern to match UI elements that got concatenated
UI_ELEMENTS_PATTERN = re.compile(r'Reveal Solution.*$', re.DOTALL)


class ExamTopicsScraper:
    """Scraper for ExamTopics website."""

    BASE_URL = "https://www.examtopics.com"
    QUESTIONS_PER_PAGE = 50

    def __init__(self, cookies: dict[str, str], delay: float = 1.0):
        """Initialize scraper with session cookies.

        Args:
            cookies: Dictionary of cookies (must include session cookie)
            delay: Delay between requests in seconds
        """
        self.cookies = cookies
        self.delay = delay
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _build_url(self, provider: str, exam_code: str, page: int) -> str:
        """Build URL for a specific exam page."""
        return f"{self.BASE_URL}/exams/{provider}/{exam_code}/view/{page}/"

    def _clean_question_text(self, text: str) -> str:
        """Clean question text by removing embedded vote JSON and concatenated choices."""
        # Remove embedded JSON vote data
        text = VOTE_JSON_PATTERN.sub('', text)

        # Remove UI elements like "Reveal SolutionHide SolutionDiscussion..."
        text = UI_ELEMENTS_PATTERN.sub('', text)

        # Remove concatenated choice options (A.xxx B.xxx C.xxx D.xxx)
        # Find where choices start - typically "A." followed by capital letter
        choice_start = re.search(r'[A-F]\.[A-Z]', text)
        if choice_start:
            text = text[:choice_start.start()]

        return text.strip()

    def _parse_choices(self, card: Any) -> list[Choice]:
        """Parse answer choices from a question card."""
        choices = []
        seen_labels: set[str] = set()  # Prevent duplicate choices
        choice_elements = card.css(".multi-choice-item, .question-choices-container li")

        for elem in choice_elements:
            # Get the label (A, B, C, D...)
            label_elem = elem.css_first(".multi-choice-letter")
            if label_elem:
                label = label_elem.text(strip=True).rstrip(".")
            else:
                # Alternative format
                full_text = elem.text(strip=True)
                if full_text and full_text[0].isalpha() and len(full_text) > 1 and full_text[1] == ".":
                    label = full_text[0]
                else:
                    continue

            # Get the choice text - check for image first (some questions use images)
            img_elem = elem.css_first("img")
            image_url: str | None = None
            if img_elem:
                # Image-based choice: store image URL separately
                image_url = img_elem.attributes.get("src", "")
                img_title = img_elem.attributes.get("title", "")
                text = img_title or "Image"  # Fallback text for non-HTML formats
            else:
                # Text-based choice: text is directly in element (not in .multi-choice-txt)
                # Get full text and remove the label part
                full_text = elem.text(strip=True)
                if full_text.startswith(f"{label}."):
                    text = full_text[len(label) + 1:].strip()
                else:
                    text = full_text
                # Remove "Most Voted" badge text if present
                text = re.sub(r'\s*Most Voted\s*$', '', text).strip()

            if label and text and label not in seen_labels:
                seen_labels.add(label)
                choices.append(Choice(label=label, text=text, image_url=image_url))

        return choices

    def _parse_correct_answer(self, card: Any) -> str:
        """Parse the correct answer from a question card."""
        # Look for the revealed answer element
        answer_elem = card.css_first(".question-answer .correct-answer")
        if answer_elem:
            answer_text = answer_elem.text(strip=True)
            # Extract just the letter(s) - e.g., "Correct Answer: A" -> "A"
            match = re.search(r"[A-Z]+(?:\s*,\s*[A-Z]+)*$", answer_text)
            if match:
                return match.group().replace(" ", "").replace(",", "")

        # Alternative: look in hidden answer element
        hidden_answer = card.css_first(".question-answer")
        if hidden_answer:
            text = hidden_answer.text(strip=True)
            match = re.search(r"Correct Answer[:\s]+([A-Z]+(?:\s*,\s*[A-Z]+)*)", text)
            if match:
                return match.group(1).replace(" ", "").replace(",", "")

        return ""

    def _parse_community_votes(self, card: Any) -> list[VotedAnswer]:
        """Parse community voting data from a question card."""
        votes = []

        # Look for vote data in script tag
        script_tags = card.css("script[type='application/json']")
        for script in script_tags:
            try:
                data = json.loads(script.text())
                if isinstance(data, dict) and "voted_answers" in data:
                    vote_data = data["voted_answers"]
                    total_votes = sum(v.get("count", 0) for v in vote_data.values())
                    max_votes = 0
                    max_answer = ""

                    for answer, info in vote_data.items():
                        count = info.get("count", 0)
                        if count > max_votes:
                            max_votes = count
                            max_answer = answer

                    for answer, info in vote_data.items():
                        count = info.get("count", 0)
                        percentage = (
                            (count / total_votes * 100) if total_votes > 0 else 0
                        )
                        votes.append(
                            VotedAnswer(
                                answer=answer,
                                vote_count=count,
                                vote_percentage=round(percentage, 1),
                                is_most_voted=(answer == max_answer),
                            )
                        )
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        # Sort by vote count descending
        votes.sort(key=lambda x: x.vote_count, reverse=True)
        return votes

    def _parse_discussion_count(self, card: Any) -> int:
        """Parse discussion/comment count from a question card."""
        discussion_elem = card.css_first(".discussion-count, .comment-count")
        if discussion_elem:
            text = discussion_elem.text(strip=True)
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
        return 0

    def _parse_question(
        self, card: Any, base_number: int, index: int
    ) -> Question | None:
        """Parse a single question from a card element."""
        # Get question number
        number_elem = card.css_first(".question-number, .card-header .text-white")
        if number_elem:
            text = number_elem.text(strip=True)
            match = re.search(r"Question\s*#?\s*(\d+)", text, re.IGNORECASE)
            if match:
                number = int(match.group(1))
            else:
                number = base_number + index
        else:
            number = base_number + index

        # Get topic number
        topic = None
        topic_elem = card.css_first(".question-topic")
        if topic_elem:
            text = topic_elem.text(strip=True)
            match = re.search(r"Topic\s*#?\s*(\d+)", text, re.IGNORECASE)
            if match:
                topic = int(match.group(1))

        # Get question text
        question_body = card.css_first(".question-body, .card-text")
        if not question_body:
            return None

        raw_text = question_body.text(strip=True)
        if not raw_text:
            return None

        # Clean the question text (remove embedded JSON votes, choices, UI elements)
        question_text = self._clean_question_text(raw_text)

        # Parse choices
        choices = self._parse_choices(card)
        if not choices:
            # Debug: show what selectors found for troubleshooting
            multi_choice = card.css(".multi-choice-item")
            container_li = card.css(".question-choices-container li")
            console.print(
                f"[yellow]Warning: No choices found for question {number} "
                f"(multi-choice: {len(multi_choice)}, container-li: {len(container_li)})[/yellow]"
            )
            return None

        # Parse correct answer
        correct_answer = self._parse_correct_answer(card)

        # Parse community votes
        community_votes = self._parse_community_votes(card)

        # Parse discussion count
        discussion_count = self._parse_discussion_count(card)

        return Question(
            number=number,
            topic=topic,
            text=question_text,
            choices=choices,
            correct_answer=correct_answer,
            community_votes=community_votes,
            discussion_count=discussion_count,
        )

    def _parse_page(self, html: str, page_number: int) -> list[Question]:
        """Parse all questions from a page HTML."""
        tree = HTMLParser(html)
        questions = []

        # Find all question cards
        cards = tree.css(".exam-question-card, .question-card, .card.exam-question")

        base_number = (page_number - 1) * self.QUESTIONS_PER_PAGE + 1

        for i, card in enumerate(cards):
            question = self._parse_question(card, base_number, i)
            if question:
                questions.append(question)

        return questions

    def _get_total_questions(self, html: str) -> int:
        """Extract total question count from page HTML."""
        # Pattern 1: "out of X questions" (most reliable)
        match = re.search(r"out of\s+(\d+)\s+questions", html, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Pattern 2: "X Questions & Answers"
        match = re.search(r"(\d+)\s*Questions?\s*&\s*Answers", html, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return 0

    def _get_exam_title(self, html: str) -> str:
        """Extract exam title from page HTML."""
        tree = HTMLParser(html)

        # Look for exam title in header
        title_elem = tree.css_first(".exam-title, h1.exam-name, .card-header h1")
        if title_elem:
            return title_elem.text(strip=True)

        # Fallback to page title
        title_elem = tree.css_first("title")
        if title_elem:
            text = title_elem.text(strip=True)
            # Remove "ExamTopics" suffix
            return re.sub(r"\s*[-|]\s*ExamTopics.*$", "", text).strip()

        return ""

    async def scrape_page(
        self, client: httpx.AsyncClient, provider: str, exam_code: str, page: int
    ) -> list[Question]:
        """Scrape a single page of questions."""
        url = self._build_url(provider, exam_code, page)
        response = await client.get(url, headers=self.headers)
        if response.status_code == 404:
            return []  # Page does not exist
        response.raise_for_status()
        return self._parse_page(response.text, page)

    async def scrape_exam(self, provider: str, exam_code: str) -> Exam:
        """Scrape an entire exam with all questions.

        Args:
            provider: Exam provider (e.g., "amazon", "microsoft")
            exam_code: Exam code slug (e.g., "aws-certified-devops-engineer-professional-dop-c02")

        Returns:
            Exam object with all questions
        """
        async with httpx.AsyncClient(cookies=self.cookies, timeout=30.0) as client:
            # Fetch first page to get metadata
            url = self._build_url(provider, exam_code, 1)
            console.print(f"[cyan]Fetching exam info from {url}...[/cyan]")

            response = await client.get(url, headers=self.headers)
            response.raise_for_status()

            first_page_html = response.text
            total_questions = self._get_total_questions(first_page_html)
            exam_title = self._get_exam_title(first_page_html)

            if total_questions == 0:
                # Estimate from first page
                first_questions = self._parse_page(first_page_html, 1)
                total_questions = len(first_questions) * 10  # Rough estimate
                console.print(
                    f"[yellow]Could not determine total questions, estimated: {total_questions}[/yellow]"
                )

            total_pages = (
                total_questions + self.QUESTIONS_PER_PAGE - 1
            ) // self.QUESTIONS_PER_PAGE
            console.print(
                f"[green]Found {total_questions} questions across {total_pages} pages[/green]"
            )

            # Parse first page
            all_questions = self._parse_page(first_page_html, 1)

            # Fetch remaining pages with progress bar
            if total_pages > 1:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        "[cyan]Scraping pages...", total=total_pages - 1
                    )

                    for page in range(2, total_pages + 1):
                        await asyncio.sleep(self.delay)  # Rate limiting
                        questions = await self.scrape_page(
                            client, provider, exam_code, page
                        )
                        if not questions:  # Page doesn't exist, stop loop
                            break
                        all_questions.extend(questions)
                        progress.update(task, advance=1)

            # Sort questions by number
            all_questions.sort(key=lambda q: q.number)

            console.print(
                f"[green]Successfully scraped {len(all_questions)} questions[/green]"
            )

            return Exam(
                provider=provider,
                code=exam_code,
                title=exam_title or f"{provider} - {exam_code}",
                total_questions=len(all_questions),
                questions=all_questions,
            )


def parse_cookie_string(cookie_string: str) -> dict[str, str]:
    """Parse a cookie string (from browser) into a dictionary.

    Args:
        cookie_string: Cookie string in format "name1=value1; name2=value2"

    Returns:
        Dictionary of cookie names to values
    """
    cookies = {}
    for item in cookie_string.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies
