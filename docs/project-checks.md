# Project checks

## Cheap local checks

Run the syntax command in the [README](../README.md) and `git diff --check`.
These checks need neither live SEC access nor application dependencies.

With the application dependencies installed, check imports:

```powershell
python -c "import requests, bs4, lxml, streamlit; import main, process_filings, summarize_filings"
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
measure summary quality or establish continuing live SEC availability.

## Functional verification when changing pipeline behaviour

Use synthetic metadata and HTML in a temporary working directory. Mock network
calls and waits. Check metadata filtering and URL construction; extraction of
visible text with hidden/XBRL content removed; successful and failed processing
records; source links and summary fields preserved across JSON stages; and
empty-text and missing-file handling. Run the dashboard against the resulting
summaries and inspect its company/form filters.

## Planned financial analytics gates

These gates apply when the corresponding milestone is implemented; they are
not evidence of existing test coverage.

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

## Current quality and operational gaps

Rule-based summary quality has not been measured. Before changing extraction or
ranking rules, define representative `8-K`, `10-Q`, and `10-K` cases with
human-reviewed references and report failures and fallback coverage separately.
Do not treat deterministic execution as evidence of factual completeness.

The environment has no dependency lockfile. Before claiming reproducibility,
choose a supported Python version, resolve and lock dependencies in a clean
environment, and verify installation and the offline pipeline there. Live SEC
availability requires separate verification. Checkpoint writes are atomic, but
checkpoint and run-report publication are separate operations. HTML cache identity
is still accession-based; concurrent runs and crash recovery across multiple
stages are not transactional.
