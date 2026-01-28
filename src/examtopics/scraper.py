"""Scraper for ExamTopics exam questions using httpx and selectolax."""

import asyncio
import json
import re
from enum import Enum
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

from examtopics.models import Choice, Discussion, Exam, Question, VotedAnswer


class LoadingMode(str, Enum):
    """Question loading modes."""

    PAGINATED = "paginated"  # Default: 50 questions per page
    BULK = "bulk"  # Load all via custom-view
    RANGE = "range"  # Load in batches via range filter
    AUTO = "auto"  # Try bulk -> range -> paginated


console = Console()

# Pattern to match embedded JSON vote data
VOTE_JSON_PATTERN = re.compile(r'\[{"voted_answers".*?\}\]')
# Pattern to match choice lines that got concatenated (e.g., "A.Some text...B.Other text")
CHOICE_CONCAT_PATTERN = re.compile(r"[A-F]\.[A-Z][^.]*?(?=[A-F]\.|Reveal Solution|$)")
# Pattern to match UI elements that got concatenated
UI_ELEMENTS_PATTERN = re.compile(r"Reveal Solution.*$", re.DOTALL)


class ExamTopicsScraper:
    """Scraper for ExamTopics website."""

    BASE_URL = "https://www.examtopics.com"
    QUESTIONS_PER_PAGE = 50
    DEFAULT_BATCH_SIZE = 100

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

    def _build_custom_view_url(self, provider: str, exam_code: str) -> str:
        """Build URL for custom-view page."""
        return f"{self.BASE_URL}/exams/{provider}/{exam_code}/custom-view/"

    def _extract_csrf_token(self, html: str) -> str | None:
        """Extract CSRF token from page HTML."""
        match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
        return match.group(1) if match else None

    def _clean_question_text(self, text: str) -> str:
        """Clean question text by removing embedded vote JSON and concatenated choices."""
        # Remove embedded JSON vote data
        text = VOTE_JSON_PATTERN.sub("", text)

        # Remove UI elements like "Reveal SolutionHide SolutionDiscussion..."
        text = UI_ELEMENTS_PATTERN.sub("", text)

        # Remove concatenated choice options (A.xxx B.xxx C.xxx D.xxx)
        # Find where choices start - typically "A." followed by capital letter
        choice_start = re.search(r"[A-F]\.[A-Z]", text)
        if choice_start:
            text = text[: choice_start.start()]

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
                if (
                    full_text
                    and full_text[0].isalpha()
                    and len(full_text) > 1
                    and full_text[1] == "."
                ):
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
                    text = full_text[len(label) + 1 :].strip()
                else:
                    text = full_text
                # Remove "Most Voted" badge text if present
                text = re.sub(r"\s*Most Voted\s*$", "", text).strip()

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

    def _parse_question_id(self, card: Any) -> int | None:
        """Extract question ID from card's data-id attribute."""
        question_body = card.css_first(".question-body")
        if question_body:
            qid = question_body.attributes.get("data-id")
            if qid:
                return int(qid)
        return None

    async def _fetch_discussion(
        self,
        client: httpx.AsyncClient,
        question_id: int,
    ) -> str | None:
        """Fetch discussion HTML for a question."""
        url = f"{self.BASE_URL}/ajax/discussion/exam-question/{question_id}/"
        headers = {
            **self.headers,
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
        except Exception:
            pass
        return None

    def _parse_discussions(self, html: str) -> list[Discussion]:
        """Parse discussions from HTML response."""
        tree = HTMLParser(html)
        discussions = []

        # Only parse top-level comment containers (direct children, not nested replies)
        for comment in tree.css(".comment-container"):
            # Check if this is a top-level comment (not inside comment-replies)
            parent = comment.parent
            if parent and "comment-replies" in (parent.attributes.get("class") or ""):
                continue
            discussion = self._parse_single_discussion(comment)
            if discussion:
                discussions.append(discussion)

        return discussions

    def _parse_single_discussion(self, comment: Any) -> Discussion | None:
        """Parse a single discussion comment (recursive for replies)."""
        comment_id = int(comment.attributes.get("data-comment-id", 0))
        if not comment_id:
            return None

        username_elem = comment.css_first(".comment-username")
        username = username_elem.text(strip=True) if username_elem else "Unknown"

        date_elem = comment.css_first(".comment-date")
        date = date_elem.attributes.get("title", "") if date_elem else ""
        date_relative = date_elem.text(strip=True) if date_elem else ""

        selected_answer = None
        answer_elem = comment.css_first(".comment-selected-answers strong")
        if answer_elem:
            selected_answer = answer_elem.text(strip=True)

        content_elem = comment.css_first(".comment-content")
        content = content_elem.text(strip=True) if content_elem else ""

        upvote_elem = comment.css_first(".upvote-count")
        upvotes = 0
        if upvote_elem:
            upvote_text = upvote_elem.text(strip=True)
            if upvote_text.isdigit():
                upvotes = int(upvote_text)

        badge_elem = comment.css_first(".badge-primary")
        badge_text = badge_elem.text(strip=True) if badge_elem else ""
        is_highly_voted = "Highly Voted" in badge_text
        is_most_recent = "Most Recent" in badge_text

        # Recursively parse replies (only direct children)
        replies = []
        replies_container = comment.css_first(".comment-replies")
        if replies_container:
            # Get direct children only by iterating
            for child in replies_container.iter():
                if (
                    child.tag == "div"
                    and "comment-container" in (child.attributes.get("class") or "")
                ):
                    reply_discussion = self._parse_single_discussion(child)
                    if reply_discussion:
                        replies.append(reply_discussion)

        return Discussion(
            comment_id=comment_id,
            username=username,
            date=date,
            date_relative=date_relative,
            selected_answer=selected_answer,
            content=content,
            upvotes=upvotes,
            is_highly_voted=is_highly_voted,
            is_most_recent=is_most_recent,
            replies=replies,
        )

    def _parse_question(
        self, card: Any, base_number: int, index: int
    ) -> Question | None:
        """Parse a single question from a card element."""
        # Get question number from card header
        # Note: "text-white" is on the same element as "card-header", not a child
        number_elem = card.css_first(".question-number, .card-header")
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
        topic_elem = card.css_first(".question-title-topic, .question-topic")
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

        # Parse question ID for discussion fetching
        question_id = self._parse_question_id(card)

        return Question(
            number=number,
            topic=topic,
            question_id=question_id,
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

    async def _fetch_custom_view_page(
        self, client: httpx.AsyncClient, provider: str, exam_code: str
    ) -> tuple[str, str | None]:
        """Fetch custom-view page and extract CSRF token.

        Returns:
            Tuple of (html_content, csrf_token)
        """
        url = self._build_custom_view_url(provider, exam_code)
        response = await client.get(url, headers=self.headers)
        response.raise_for_status()
        csrf_token = self._extract_csrf_token(response.text)
        return response.text, csrf_token

    async def _post_custom_view(
        self,
        client: httpx.AsyncClient,
        provider: str,
        exam_code: str,
        csrf_token: str,
        questions_per_page: int,
        range_from: int | None = None,
        range_to: int | None = None,
    ) -> httpx.Response:
        """POST to custom-view to load questions with specific settings.

        Args:
            client: HTTP client
            provider: Exam provider
            exam_code: Exam code
            csrf_token: CSRF token from the page
            questions_per_page: Number of questions to load per page
            range_from: Start of question range (optional)
            range_to: End of question range (optional)

        Returns:
            HTTP response
        """
        url = self._build_custom_view_url(provider, exam_code)
        data = {
            "csrfmiddlewaretoken": csrf_token,
            "questions-per-page": str(questions_per_page),
        }
        if range_from is not None and range_to is not None:
            data["question-range-on"] = "on"
            data["from-input"] = str(range_from)
            data["to-input"] = str(range_to)

        headers = {
            **self.headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.BASE_URL,
            "Referer": url,
        }

        response = await client.post(
            url, data=data, headers=headers, follow_redirects=True
        )
        return response

    def _parse_custom_view(self, html: str) -> list[Question]:
        """Parse all questions from custom-view HTML (no page numbering)."""
        tree = HTMLParser(html)
        questions = []

        # Find all question cards
        cards = tree.css(".exam-question-card, .question-card, .card.exam-question")

        for i, card in enumerate(cards):
            question = self._parse_question(card, 1, i)
            if question:
                questions.append(question)

        return questions

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

    async def _scrape_bulk(
        self,
        client: httpx.AsyncClient,
        provider: str,
        exam_code: str,
        total_questions: int,
    ) -> list[Question] | None:
        """Try to load all questions in one bulk request via custom-view.

        Returns:
            List of questions if successful, None if bulk loading failed
        """
        console.print("[cyan]Attempting bulk loading via custom-view...[/cyan]")

        try:
            # Fetch custom-view page to get CSRF token
            _, csrf_token = await self._fetch_custom_view_page(
                client, provider, exam_code
            )
            if not csrf_token:
                console.print(
                    "[yellow]Could not extract CSRF token for bulk loading[/yellow]"
                )
                return None

            # POST with total questions and range filter
            # Server requires range parameters for large question counts
            response = await self._post_custom_view(
                client,
                provider,
                exam_code,
                csrf_token,
                total_questions,
                range_from=1,
                range_to=total_questions,
            )

            if response.status_code != 200:
                console.print(
                    f"[yellow]Bulk loading returned status {response.status_code}[/yellow]"
                )
                return None

            questions = self._parse_custom_view(response.text)

            # Verify we got a reasonable number of questions
            if len(questions) < total_questions * 0.9:  # Allow 10% tolerance
                console.print(
                    f"[yellow]Bulk loading returned only {len(questions)}/{total_questions} questions[/yellow]"
                )
                return None

            console.print(
                f"[green]Bulk loading successful: {len(questions)} questions[/green]"
            )
            return questions

        except Exception as e:
            console.print(f"[yellow]Bulk loading failed: {e}[/yellow]")
            return None

    async def _scrape_range(
        self,
        client: httpx.AsyncClient,
        provider: str,
        exam_code: str,
        total_questions: int,
        batch_size: int,
    ) -> list[Question] | None:
        """Load questions in batches using range filter via custom-view.

        Returns:
            List of questions if successful, None if range loading failed
        """
        console.print(
            f"[cyan]Attempting range loading (batch size: {batch_size})...[/cyan]"
        )
        all_questions: list[Question] = []

        try:
            num_batches = (total_questions + batch_size - 1) // batch_size

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Loading batches...", total=num_batches)

                for batch_idx in range(num_batches):
                    range_from = batch_idx * batch_size + 1
                    range_to = min((batch_idx + 1) * batch_size, total_questions)

                    # Get fresh CSRF token for each batch
                    _, csrf_token = await self._fetch_custom_view_page(
                        client, provider, exam_code
                    )
                    if not csrf_token:
                        console.print("[yellow]Could not extract CSRF token[/yellow]")
                        return None

                    await asyncio.sleep(self.delay)

                    response = await self._post_custom_view(
                        client,
                        provider,
                        exam_code,
                        csrf_token,
                        batch_size,
                        range_from,
                        range_to,
                    )

                    if response.status_code != 200:
                        console.print(
                            f"[yellow]Range batch {batch_idx + 1} returned status {response.status_code}[/yellow]"
                        )
                        return None

                    questions = self._parse_custom_view(response.text)
                    if not questions:
                        console.print(
                            f"[yellow]Range batch {batch_idx + 1} returned no questions[/yellow]"
                        )
                        return None

                    all_questions.extend(questions)
                    progress.update(task, advance=1)

            console.print(
                f"[green]Range loading successful: {len(all_questions)} questions[/green]"
            )
            return all_questions

        except Exception as e:
            console.print(f"[yellow]Range loading failed: {e}[/yellow]")
            return None

    async def _scrape_paginated(
        self,
        client: httpx.AsyncClient,
        provider: str,
        exam_code: str,
        total_questions: int,
        first_page_html: str,
    ) -> list[Question]:
        """Load questions using traditional pagination (50 per page)."""
        console.print("[cyan]Using paginated loading (50 questions per page)...[/cyan]")

        total_pages = (
            total_questions + self.QUESTIONS_PER_PAGE - 1
        ) // self.QUESTIONS_PER_PAGE

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
                    await asyncio.sleep(self.delay)
                    questions = await self.scrape_page(
                        client, provider, exam_code, page
                    )
                    if not questions:
                        break
                    all_questions.extend(questions)
                    progress.update(task, advance=1)

        return all_questions

    async def scrape_exam(
        self,
        provider: str,
        exam_code: str,
        mode: LoadingMode = LoadingMode.PAGINATED,
        batch_size: int | None = None,
        include_discussions: bool = False,
    ) -> Exam:
        """Scrape an entire exam with all questions.

        Args:
            provider: Exam provider (e.g., "amazon", "microsoft")
            exam_code: Exam code slug (e.g., "aws-certified-devops-engineer-professional-dop-c02")
            mode: Loading mode (paginated, bulk, range, auto)
            batch_size: Batch size for range mode (default: 100)
            include_discussions: Whether to fetch discussion comments (slower)

        Returns:
            Exam object with all questions
        """
        if batch_size is None:
            batch_size = self.DEFAULT_BATCH_SIZE

        # Use longer timeout for bulk/range modes
        timeout = 120.0 if mode in (LoadingMode.BULK, LoadingMode.AUTO) else 30.0

        async with httpx.AsyncClient(cookies=self.cookies, timeout=timeout) as client:
            # Fetch first page to get metadata
            url = self._build_url(provider, exam_code, 1)
            console.print(f"[cyan]Fetching exam info from {url}...[/cyan]")

            response = await client.get(url, headers=self.headers)
            response.raise_for_status()

            first_page_html = response.text
            total_questions = self._get_total_questions(first_page_html)
            exam_title = self._get_exam_title(first_page_html)

            if total_questions == 0:
                first_questions = self._parse_page(first_page_html, 1)
                total_questions = len(first_questions) * 10
                console.print(
                    f"[yellow]Could not determine total questions, estimated: {total_questions}[/yellow]"
                )

            total_pages = (
                total_questions + self.QUESTIONS_PER_PAGE - 1
            ) // self.QUESTIONS_PER_PAGE

            # Display mode-appropriate message
            if mode == LoadingMode.PAGINATED:
                console.print(
                    f"[green]Found {total_questions} questions ({total_pages} pages)[/green]"
                )
            elif mode == LoadingMode.BULK:
                console.print(
                    f"[green]Found {total_questions} questions (will load all at once)[/green]"
                )
            elif mode == LoadingMode.RANGE:
                num_batches = (total_questions + batch_size - 1) // batch_size
                console.print(
                    f"[green]Found {total_questions} questions ({num_batches} batches of {batch_size})[/green]"
                )
            elif mode == LoadingMode.AUTO:
                console.print(f"[green]Found {total_questions} questions[/green]")

            console.print(f"[blue]Loading mode: {mode.value}[/blue]")

            all_questions: list[Question] = []

            if mode == LoadingMode.BULK:
                result = await self._scrape_bulk(
                    client, provider, exam_code, total_questions
                )
                if result:
                    all_questions = result
                else:
                    console.print(
                        "[yellow]Bulk loading failed, falling back to paginated[/yellow]"
                    )
                    all_questions = await self._scrape_paginated(
                        client, provider, exam_code, total_questions, first_page_html
                    )

            elif mode == LoadingMode.RANGE:
                result = await self._scrape_range(
                    client, provider, exam_code, total_questions, batch_size
                )
                if result:
                    all_questions = result
                else:
                    console.print(
                        "[yellow]Range loading failed, falling back to paginated[/yellow]"
                    )
                    all_questions = await self._scrape_paginated(
                        client, provider, exam_code, total_questions, first_page_html
                    )

            elif mode == LoadingMode.AUTO:
                # Try bulk first
                result = await self._scrape_bulk(
                    client, provider, exam_code, total_questions
                )
                if result:
                    all_questions = result
                else:
                    # Try range next
                    result = await self._scrape_range(
                        client, provider, exam_code, total_questions, batch_size
                    )
                    if result:
                        all_questions = result
                    else:
                        # Fall back to paginated
                        console.print(
                            "[yellow]Falling back to paginated loading[/yellow]"
                        )
                        all_questions = await self._scrape_paginated(
                            client,
                            provider,
                            exam_code,
                            total_questions,
                            first_page_html,
                        )

            else:  # PAGINATED (default)
                all_questions = await self._scrape_paginated(
                    client, provider, exam_code, total_questions, first_page_html
                )

            # Sort questions by number
            all_questions.sort(key=lambda q: q.number)

            console.print(
                f"[green]Successfully scraped {len(all_questions)} questions[/green]"
            )

            # Fetch discussions if requested
            if include_discussions:
                questions_with_ids = [
                    q for q in all_questions if q.question_id is not None
                ]
                if questions_with_ids:
                    console.print(
                        f"[cyan]Fetching discussions for {len(questions_with_ids)} questions...[/cyan]"
                    )

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task(
                            "[cyan]Fetching discussions...",
                            total=len(questions_with_ids),
                        )

                        for question in questions_with_ids:
                            await asyncio.sleep(self.delay)
                            html = await self._fetch_discussion(
                                client, question.question_id
                            )
                            if html:
                                question.discussions = self._parse_discussions(html)
                            progress.update(task, advance=1)

                    total_discussions = sum(len(q.discussions) for q in all_questions)
                    console.print(
                        f"[green]Fetched {total_discussions} discussions[/green]"
                    )
                else:
                    console.print(
                        "[yellow]No question IDs found for discussion fetching[/yellow]"
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
