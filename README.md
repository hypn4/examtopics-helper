# ExamTopics Helper

Extract and export ExamTopics exam questions to HTML, PDF, and Markdown formats.

## Quick Start (Pre-built Binary)

Download a pre-built binary from [GitHub Releases](https://github.com/hypn4/examtopics-helper/releases) — no Python installation required.

### Download

| Platform | Binary |
|----------|--------|
| macOS | `examtopics-macos` |
| Windows | `examtopics-windows.exe` |
| Linux | `examtopics-linux` |

### Run

**macOS / Linux:**

```bash
# Make executable
chmod +x examtopics-macos  # or examtopics-linux

# Run
./examtopics-macos extract --exam "amazon/dop-c02" --cookie "..."
```

**Windows:**

```powershell
.\examtopics-windows.exe extract --exam "amazon/dop-c02" --cookie "..."
```

> **Note:** All CLI options below work the same way — just replace `examtopics` with the binary name (e.g., `./examtopics-macos`).

---

## Installation (From Source)

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

### (Optional) Watch Mode

For template development with auto-reload:

```bash
uv sync --extra watch
```

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

# Include discussion comments (slower)
examtopics extract \
  --exam "amazon/dop-c02" \
  --cookie "..." \
  --discussions
```

> **Note:** `--discussions` 옵션은 질문당 추가 API 요청이 필요하므로 추출 시간이 더 걸립니다.

### Loading Modes

The scraper supports multiple loading strategies to handle different exam configurations:

| Mode | Description | Best For |
|------|-------------|----------|
| `paginated` | Load 50 questions per page (default) | Most reliable, works with all exams |
| `bulk` | Load all questions at once via custom-view | Fast, but may not work on all exams |
| `range` | Load in batches using question range filter | Large exams, configurable batch size |
| `auto` | Try bulk → range → paginated automatically | Recommended for best performance |

```bash
# Use auto mode (recommended) - tries fastest method first
examtopics extract \
  --exam "amazon/dop-c02" \
  --cookie "..." \
  --mode auto

# Use bulk mode for faster extraction
examtopics extract \
  --exam "amazon/dop-c02" \
  --cookie "..." \
  --mode bulk

# Use range mode with custom batch size
examtopics extract \
  --exam "amazon/dop-c02" \
  --cookie "..." \
  --mode range \
  --batch-size 50
```

You can also set the mode via environment variables:

```bash
# In .env file
EXAMTOPICS_MODE="auto"
EXAMTOPICS_BATCH_SIZE="100"
```

### Get Exam Info

```bash
# Check exam details without downloading
examtopics info \
  --exam "amazon/dop-c02" \
  --cookie "..."
```

### Re-render from JSON

If you've already extracted an exam and only want to re-render with updated templates:

```bash
# Re-render existing JSON to HTML
examtopics render \
  --input output/amazon_dop-c02.json \
  --format html

# Watch mode: auto re-render on template changes (for development)
examtopics render \
  --input output/amazon_dop-c02.json \
  --format html \
  --watch
```

> **Note:** Watch mode requires the `watch` extra: `uv sync --extra watch`

## Output Formats

| Format | Description |
|--------|-------------|
| **HTML** | Styled webpage with questions, choices, and answers |
| **PDF** | Print-ready PDF document (requires system libraries) |
| **Markdown** | Plain text markdown for notes/Obsidian |
| **JSON** | Raw structured data for custom processing |

## HTML Output Features

The generated HTML file includes interactive features:

| Feature | Description |
|---------|-------------|
| **TOC Sidebar** | Question list sidebar for quick navigation |
| **Hide/Show Answers** | Global toggle in sidebar + individual toggle per question |
| **Hide/Show Discussions** | Global toggle in sidebar + individual toggle per question |
| **State Persistence** | Toggle states saved to localStorage, persists across page reloads |

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
- **weasyprint** - HTML to PDF (optional)
- **jinja2** - Templating
- **watchfiles** - File change monitoring (optional)

## License

MIT
