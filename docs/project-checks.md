# Project checks

## Cheap local checks

Run the syntax command in the [README](../README.md) and `git diff --check`.
These checks need neither live SEC access nor application dependencies.

With the application dependencies installed, check imports:

```powershell
python -c "import requests, bs4, lxml, streamlit; from scripts import ingest_filings, process_filings, summarize_filings"
```

Do not import `dashboard.py` as a library: it executes the Streamlit page.
Run the committed offline ingestion regression suite with application dependencies
installed:

```powershell
python -B -m unittest discover -s tests -v
```

Tests mock SEC transport and use isolated files under ignored `data/.test-runs/`.
They cover retries, access denial, response validation, checkpoint preservation,
real HTML parsing and Streamlit behaviour through its AppTest API. They do not
establish continuing live SEC availability. Baseline evidence checks are separate
from ingestion correctness; see the evaluation guidance below.

## Functional verification when changing pipeline behaviour

Use synthetic metadata and HTML in a temporary working directory. Mock network
calls and waits. Check metadata filtering and URL construction; extraction of
visible text with hidden/XBRL content removed; successful and failed processing
records; source links and summary fields preserved across JSON stages; and
empty-text and missing-file handling. Run the dashboard against the resulting
summaries and inspect its company/form filters.

## Structured-financial ingestion checks

`tests/test_xbrl.py` uses the invented companyfacts fixture under `tests/fixtures/`
to verify source identity, precision, date/unit validation, revision conflicts,
missing metrics, quarter/cumulative separation, fiscal/TTM labelling limits,
raw snapshot integrity, deterministic replay and checkpoint preservation.
The shared storage change is also covered by the original ingestion tests.

For bounded live schema validation and a no-network replay, use the commands in
[financial-facts.md](financial-facts.md). Keep actual raw snapshots and outputs
ignored; retain small verification records in reports. The report does not claim
independent accounting review or a human-reviewed financial benchmark. Do not
call missing source tags zero or derive fiscal labels from filing FY/FP fields.

## PostgreSQL checks

See [database.md](database.md#verification) for the opt-in test connection setting.
Without it, the test runner reports database integration checks as skipped; unit
checks alone do not verify transactions or SQL. Use a disposable local database
for the real migration, duplicate/concurrent import, decimal, rollback and
source-provenance checks. The selected driver implementation and bounded cached
five-company import evidence are recorded in the database verification report.

## Financial analytics checks

`tests/test_analytics.py` checks independently specified synthetic arithmetic,
period alignment, TTM exclusion, missing/zero inputs and comparison ambiguity.
`tests/test_financial_ui.py` exercises financial chart rendering, period controls,
empty selections and database-error isolation through Streamlit AppTest.
`tests/test_refresh.py` checks fetch/import failure boundaries, credential
redaction and persistent private settings. The opt-in PostgreSQL suite also checks
analytics queries against exact selected and ambiguous stored facts.

Run the full test command above with `MARKET_PULSE_TEST_DATABASE_URL` pointing to
a disposable local database for real SQL verification. Without that setting,
database cases are skipped. See [analytics evidence](../reports/financial-analytics-v1.json).

`tests/test_demo.py` additionally verifies frozen snapshot integrity, public-field
allowlisting, exact Decimal round trips, missing inputs and all three tabs without
database settings or generated local data. A local verification compares the
frozen calculations and retained sources to PostgreSQL across every supported
annual/quarterly interval. Linux wheels are hash-checked separately; do not claim
a Linux runtime or public deployment pass from Windows-only application tests.

Further accounting review and any future quarter derivation need these gates;
they are not claims of completed human review:

- Verify metric/tag mappings with reviewed source facts across the watchlist.
  Exercise duplicate disclosures, amendments, missing tags, unit differences,
  instant/duration facts, fiscal calendars and annual versus quarterly periods.
- Derive a standalone quarter from year-to-date values only when entity, metric,
  unit and period boundaries are compatible; preserve both inputs and formula.
- Compare SQL/Python KPIs to independently reviewed reference calculations.
  Show missing or ambiguous inputs explicitly, including zero denominators.
- Load the same snapshot twice without duplicating selected facts. Verify
  transaction failure handling and historical filing-date cutoffs.

## Planned research and integration gates

- Separate retrieval relevance/coverage from citation support and answer quality.
  Include unanswerable questions, conflicting/amended filings and adversarial
  instructions embedded in source text. Review important disagreements manually.
- Record corpus snapshot, chunking, embedding, prompt and model identities.
  Detect incompatible cached artifacts. Keep reference answers out of the index.
- Check numerical, narrative and mixed routing against reviewed cases. Use
  controlled analytical functions and parameterised SQL. Trace every reported
  figure to its calculation inputs and every explanation to supporting passages.
- Verify graceful database, retrieval and provider failures, persistence after
  restart, and documented local startup before claiming integrated delivery.
- Select acceptance thresholds and evaluation budgets before running paid or
  final confirmation evaluations. Report failed cases and fallback coverage.

## Rule-based development baseline

Use the [locked environment](reproducibility.md), then run:

```powershell
python -m scripts.environment
python -m evals.run --verify reports/rule-based-baseline-v3.json
```

The suite, predeclared section-fix criteria, provenance and scoring limitations
live in [evals/README.md](../evals/README.md). Results are authoritative in the
[before/after reports](../reports/README.md). Fixture or environment changes must
not silently reuse an old baseline identity. Case errors stay in the denominator.

## Current quality and operational gaps

The 15-case baseline is agent-reviewed and contains adapted excerpts and synthetic
inputs; human review and an independent confirmation set are still pending. Exact
evidence matching tests extractive output, not the quality of paraphrased LLM
answers. Full-filing quality, exhibit coverage, proper 10-K handling,
latency/cost acceptance thresholds and human-rated completeness remain open.

Dependencies are now locked and clean-install checked for the documented Windows
CPython target. Other platforms are unverified. Live SEC availability requires
separate verification. Checkpoint writes are atomic, but checkpoint and run-report
publication are separate operations. HTML cache identity is still accession-based;
concurrent runs and crash recovery across multiple stages are not transactional.
