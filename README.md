# Market Pulse

Market Pulse collects SEC filing metadata for Nvidia, Microsoft, Alphabet, Amazon, and Apple,
downloads filing HTML, extracts readable text, and creates rule-based highlights
for a local Streamlit dashboard. No generative AI API key is required.

The project goal is an integrated **financial analytics and AI research
platform**: PostgreSQL-backed financial KPIs and company comparisons, plus
filing-based answers with source citations, in one Streamlit application.
Build financial analytics first, then retrieval and cited answers, then combine
them through controlled query routing. These capabilities are planned; the
current implementation is the filing monitor described below. See the
[project brief and delivery milestones](docs/problem.md) and
[target architecture](docs/architecture.md#target-architecture-planned).

## Setup

Run commands from the repository root. Create and activate a Python environment:

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install requests beautifulsoup4 lxml streamlit
```

On macOS/Linux, use `python3 -m venv .venv` and
`source .venv/bin/activate` instead. Dependencies are not yet locked; this setup
does not establish a reproducible environment. Cleanup checks used Python
3.14.5; the full application has not been verified in that environment.

Before accessing the SEC, set `SEC_HEADERS["User-Agent"]` in `config.py` to
identify your project with a genuine contact email. The same file configures
the watchlist, accepted forms (`8-K`, `10-Q`, `10-K`), and per-company limit.

## Run

```powershell
python main.py
if ($LASTEXITCODE -eq 0) { python process_filings.py }
if ($LASTEXITCODE -eq 0) { python summarize_filings.py }
python -m streamlit run dashboard.py
```

| Entry point | Purpose | Output |
|---|---|---|
| `main.py` | Retrieve recent filing metadata | `data/filings.json` |
| `process_filings.py` | Download HTML and extract text; record successes and failures | `data/raw_html/`, `data/clean_text/`, `data/processed_filings.json` |
| `summarize_filings.py` | Summarise successfully processed filings | `data/summaries.json` |
| `dashboard.py` | Filter summaries by company and form and link to SEC sources | Local Streamlit dashboard |

The commands above use PowerShell; stop on any failure when running stages
manually on other shells. A failed stage returns a nonzero exit code. The
dashboard may still be opened to inspect previous results and failure details.

The first two steps require network access for fresh data. Processing reuses
nonempty HTML files by accession number. Saved data is generated locally and
ignored by Git. To reopen existing results, run only the dashboard command.
Counts depend on available filings and processing failures; 25 is a configured
maximum for the default watchlist, not a guaranteed result.

Each stage replaces its main JSON output only after a complete nonempty successful
batch. On failures, partial batches or empty results, it preserves the previous
checkpoint and writes a status report (`data/metadata_status.json`,
`data/processing_status.json`, or `data/summaries_status.json`). The dashboard shows
run timestamps, warnings and per-company/per-filing errors. Partial successes are
recorded in reports; they are not mixed into older published checkpoints.

Requests use bounded retries for temporary failures. A 403 stops further network
requests in that stage and reports an access denial; repeated retries or changing
identities are not a remedy. Check the contact header and network access, wait
if access is rate-limited, and follow the [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
Cached HTML remains available, and invalid cached block pages are refetched.

## Repository

```text
AGENTS.md              Codex working conventions
config.py              Watchlist and request settings
main.py                Metadata collection entry point
process_filings.py     Download and text extraction entry point
summarize_filings.py   Summary generation entry point
dashboard.py           Streamlit entry point
src/                   Shared SEC, download, parsing, storage and summary code
docs/                  Project brief, architecture and verification guidance
tests/                 Offline ingestion and dashboard regression tests
```

The entry points serve different pipeline stages; reusable code lives in `src/`.
See [the project brief](docs/problem.md),
[component contracts and recovery](docs/architecture.md), and
[checks and known gaps](docs/project-checks.md).

## Checks and limitations

Check Python syntax without importing optional dependencies or creating caches:

```powershell
python -c "import ast; from pathlib import Path; files = sorted(Path('.').glob('*.py')) + sorted(Path('src').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print(f'Parsed {len(files)} Python files')"
```

Run offline regression checks after installing the application dependencies:

```powershell
python -B -m unittest discover -s tests -v
```

The suite uses mocked network responses, real HTML parsing, and Streamlit AppTest.
No dependency lockfile exists yet. Offline checks do not verify current SEC
connectivity or browser appearance. The form-aware summariser targets `8-K` and `10-Q`; `10-K` uses the
`10-Q` rules as a fallback. Highlight quality has not been evaluated against
human-reviewed references.
