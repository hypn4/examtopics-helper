# ExamTopics Helper

Extract and export ExamTopics exam questions to HTML, PDF, and Markdown formats.

## Installation

```bash
# Clone the repository
git clone https://github.com/hypn4/examtopics-helper.git
cd examtopics-helper

# Install with uv
uv sync
```

### (Optional) PDF Export

PDF export requires WeasyPrint and system libraries:

```bash
# 1. Install system dependencies first
# macOS
brew install pango

# Ubuntu/Debian
sudo apt install libpango-1.0-0 libpangocairo-1.0-0

# 2. Install with PDF support
uv sync --extra pdf
```

#### Troubleshooting (Apple Silicon Mac)

If you see `WeasyPrint could not import some external libraries` even after installing pango, you need to set the library path:

```bash
# Option 1: Set for current session
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

# Option 2: Add to ~/.zshrc for permanent fix
echo 'export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"' >> ~/.zshrc
source ~/.zshrc
```

This is needed because Homebrew on Apple Silicon installs libraries to `/opt/homebrew/lib` instead of `/usr/local/lib`.

## Usage

### Get Session Cookie

1. Log in to ExamTopics in your browser
2. Open DevTools (F12) → Network tab
3. Navigate to any exam page
4. Find any request to `examtopics.com` and copy the `Cookie` header

**Required cookies:**

| Cookie | Purpose |
|--------|---------|
| `sessionid` | Django session (login authentication) |
| `cf_clearance` | Cloudflare bot protection |
| `csrftoken` | Django CSRF protection |

You only need these three cookies. Analytics cookies (`_ga`, `_gid`, `_fbp`, etc.) are not required.

### Using Environment Variables

You can store your session cookie in a `.env` file to avoid passing it on every command:

```bash
# Copy .env.example and fill in your cookies
cp .env.example .env
```

Example `.env` file:

```
EXAMTOPICS_COOKIE="sessionid=abc123xyz; cf_clearance=xxxx-xxxxx-xxxxx; csrftoken=yyyy"
```

The CLI automatically loads `.env` from the current directory. You can still override with `--cookie`:

```bash
# Uses EXAMTOPICS_COOKIE from .env
examtopics extract --exam "amazon/dop-c02"

# Override with CLI option
examtopics extract --exam "amazon/dop-c02" --cookie "session=different"
```

### Extract Exam Questions

```bash
# Basic usage - exports to HTML, Markdown, and JSON
examtopics extract \
  --exam "amazon/aws-certified-devops-engineer-professional-dop-c02" \
  --cookie "session=xxx; cf_clearance=yyy"

# Specify output formats
examtopics extract \
  --exam "amazon/dop-c02" \
  --cookie "..." \
  --format html \
  --format markdown

# Custom output directory
examtopics extract \
  --exam "microsoft/az-104" \
  --cookie "..." \
  --output ./my-exams

# Adjust request delay (default: 1.0s)
examtopics extract \
  --exam "google/cloud-digital-leader" \
  --cookie "..." \
  --delay 2.0
```

### Get Exam Info

```bash
# Check exam details without downloading
examtopics info \
  --exam "amazon/dop-c02" \
  --cookie "..."
```

## Output Formats

| Format | Description |
|--------|-------------|
| **HTML** | Styled webpage with questions, choices, and answers |
| **PDF** | Print-ready PDF document (requires system libraries) |
| **Markdown** | Plain text markdown for notes/Obsidian |
| **JSON** | Raw structured data for custom processing |

## Project Structure

```
examtopics-helper/
├── src/examtopics/
│   ├── cli.py          # Typer CLI
│   ├── models.py       # Pydantic data models
│   ├── scraper.py      # HTTP scraping logic
│   ├── exporters/      # Output format handlers
│   └── templates/      # Jinja2 templates
├── output/             # Generated files
└── pyproject.toml
```

## Libraries Used

- **httpx** - Async HTTP client
- **selectolax** - Fast HTML parsing
- **pydantic** - Data validation
- **typer** - CLI framework
- **rich** - Terminal output
- **weasyprint** - HTML to PDF
- **jinja2** - Templating

## License

MIT
