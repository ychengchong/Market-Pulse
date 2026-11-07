# Project brief

Market Pulse helps a local operator browse recent SEC filings, identify the
reported event, read extractive highlights, and open the original source.
The current watchlist is configured in `config.py`.

The existing baseline is a sequential, file-based pipeline with deterministic
rules for `8-K` event sections and `10-Q` financial-result sentences. This cleanup
preserves that baseline. Training models, adding hosted providers, deploying a
service, and making investment decisions are outside this task.

## Data and evaluation

Inputs are public company submissions metadata and filing HTML from the SEC.
Metadata retains company identifiers, filing dates, accession numbers, document
names and source URLs. Downloaded HTML is retained locally; clean text and JSON
outputs can be regenerated. See [architecture](architecture.md) for state and
failure behaviour. Generated files are excluded from Git.

Functional acceptance for the baseline means that selected metadata can pass
through extraction and summarisation into the dashboard while retaining source
links and recording processing failures. No measured summary-quality threshold,
human-reviewed evaluation corpus, performance target, or retention policy has
been established. No quality improvement is claimed by repository cleanup.

## Operating assumptions

- Run scripts in order from the repository root, with a single operator.
- Configure an identifying SEC contact header before fetching live data.
- Use local files as checkpoints; no scheduler, database or live service exists.
- Review highlights against source filings, especially `10-K` fallback results.
- Future quality work needs representative form-specific references, explicit
  acceptance criteria, and separate development and final confirmation cases.

Check commands and verification gaps live in [project checks](project-checks.md).
