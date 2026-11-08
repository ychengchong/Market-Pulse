# Project brief

Market Pulse's goal is an integrated financial analytics and AI research
platform for exploring company performance and researching SEC disclosures.
It supports a portfolio spanning data analytics, applied AI engineering and
fintech through one application and repository.

The target application has three Streamlit tabs: Dashboard, Ask AI, and Company
comparison. Numerical answers come from validated structured facts and controlled
SQL/Python calculations. Narrative explanations come from retrieved filing
passages with citations. Mixed questions combine both evidence sources.

The configured watchlist in `config.py` remains authoritative. The older
three-company example in the supplied proposal does not replace it.

## Current baseline

Implemented: metadata collection, filing HTML downloads, text extraction,
deterministic rule-based highlights, JSON checkpoints and a Streamlit filing
browser. PostgreSQL analytics, XBRL fact ingestion, embeddings, retrieval,
LLM answers and query routing are not implemented yet. Current extractive
highlights remain the baseline for future comparisons.

## Delivery milestones

| Order | Deliverable | Acceptance evidence |
|---|---|---|
| 1. Financial analytics | Ingest SEC XBRL company facts; validate and normalise annual/quarterly metrics; load PostgreSQL; expose SQL KPIs, trends and company comparisons in Streamlit. | Trace displayed values to source facts and filings. Verify revenue, net income, assets, liabilities and cash flow against reviewed cases. Demonstrate repeatable loads without duplicates and explicit missing/ambiguous values. |
| 2. Research assistant | Parse filing sections, chunk text, embed/index it in pgvector or Chroma, retrieve passages and generate cited answers. | Evaluate retrieval separately from answers. Review citations and groundedness on representative questions, including missing evidence and conflicting or amended disclosures. |
| 3. Integration | Route numerical, narrative and mixed questions to controlled analytics functions, retrieval or both; add FastAPI and Docker packaging once the core paths work. | Demonstrate numerical provenance and narrative citations in one answer; evaluate routing and failure handling; verify a documented local startup and persistence workflow. |

Upgrade 1 implementation adds bounded SEC requests, validation, atomic checkpoints,
per-item run reports, explicit dashboard warnings and offline regression tests.
A live probe successfully retrieved metadata and one filing without changing
existing data; this is bounded evidence, not a guarantee of future availability.
Historical 403 failures indicate access denial; their exact earlier cause was not
proven. The current identifying header was already configured before this upgrade.

Upgrade 2 adds a complete wheel-hash dependency lock, a verified clean Windows
CPython environment and a reproducible 15-case development baseline with preserved
before/after predictions. The Nvidia MD&A and Amazon 8-K table-of-contents
selection defects are corrected; the original 12-case baseline is also retained.
References are agent-reviewed; independent human review is pending.
The filing browser now groups each company's 8-Ks into one card with dated entries,
newest-first ordering, separate source links and expandable long summaries. Periodic
10-Q/10-K reports remain individual cards; counts still represent filings. The UI
also includes a short product introduction, filter guidance and filing-type
explanations, bordered metrics, active-filter context, an explicit no-match
message and collapsible update details with Singapore timestamps. Failure and
staleness warnings remain visible.
See [evaluation scope](../evals/README.md) and [results](../reports/README.md).

Next in the agreed sequence: structured XBRL ingestion, then PostgreSQL analytics
before adding an LLM.

The supplied development-duration estimates are planning suggestions, not
committed delivery dates. No paid provider or external deployment is selected.

## Agreed upgrade order

This table is the current implementation roadmap. Keep the original upgrade
numbers and branch names; exhibit ingestion is an additional prerequisite before
upgrade 6. Upgrade 1 is implemented and merged. Upgrade 2 and the filing-browser
layout improvements are implemented locally on its branch and are not yet
committed or pushed. The remaining rows describe planned capabilities.

Main goal: **AI-Powered Financial Analytics & Research Platform**.
Integration branch name, if used: `feat/financial-research-platform`; this document
does not claim that branch has been created.

| Order | Upgrade and scope | Branch | State |
|---|---|---|---|
| 1 | Reliable SEC ingestion: bounded retries, response/cache validation, atomic checkpoints, preserved outputs on failure, per-item reports and freshness warnings. | `fix/sec-ingestion-reliability` | Implemented and merged |
| 2 | Reproducibility and baseline: pinned/hash-locked environment, clean-install verification, versioned inputs/references/results, MD&A and 8-K TOC fixes. Includes the requested grouped 8-K display improvement. | `chore/reproducibility-and-baseline` | Implemented locally; human reference review pending |
| 3 | Structured XBRL ingestion: financial facts with source/unit/period provenance; tag mappings, fiscal calendars, amendments and quarter/YTD validation. Define the historical coverage needed for useful annual/quarterly analysis. | `feat/xbrl-ingestion` | Planned; next numbered upgrade |
| 4 | PostgreSQL storage: companies, filings, selected facts and processing status; source-file identities, relationships, migrations and duplicate-safe loads. | `feat/postgres-storage` | Planned |
| 5 | Financial analytics: controlled SQL/Python KPIs, trends, comparable periods, missing-data handling and company comparisons in Streamlit. | `feat/financial-analytics` | Planned |
| 5a | Exhibit ingestion: discover relevant filing attachments, download/validate/extract them, and retain parent-filing and exhibit source links. Include earnings-release exhibits such as 99.1; do not fetch every attachment blindly. | `feat/exhibit-ingestion` | Planned; separate enhancement before 6 |
| 6 | LLM narrative extraction: schema-validated events, risks, explanations and entities with supporting evidence; compare against rules for accuracy, completeness, citations, cost and latency. Address page labels, disconnected text and proper 10-K section handling. | `feat/llm-extraction` | Planned |
| 7 | Filing retrieval: section-aware source-linked chunks, embeddings and one chosen vector store (pgvector or Chroma); evaluate retrieval separately. | `feat/filing-retrieval` | Planned |
| 8 | Cited research assistant: narrative financial Q&A from retrieved evidence with citations, missing-evidence handling and abstention. | `feat/cited-research-assistant` | Planned |
| 9 | Query routing: numerical questions to approved analytics functions, narrative questions to retrieval, mixed questions to both; compose calculations and evidence-backed explanations. | `feat/query-routing` | Planned |
| 10 | Complete application: Dashboard, Ask AI and Company comparison tabs, FastAPI service boundary, Docker startup/persistence, failure/recovery checks and end-to-end evaluation. | `feat/platform-packaging` | Planned |

The watchlist remains Nvidia, Microsoft, Alphabet, Amazon and Apple, with its
actual identifiers and settings maintained only in `config.py`. The current
five-filings-per-company selection is across all enabled forms; it does not
ensure annual/quarterly coverage for every company. Choose explicit historical
and form coverage during upgrade 3 rather than treating the current sample as a
complete financial history.

Upgrade 2's evaluation set is development data. Before claiming LLM improvement,
obtain human review and introduce separate confirmation cases. A passing small
baseline is not evidence that all full filings have high-quality summaries.

Keep deterministic parsing, XBRL validation and arithmetic where appropriate.
LLM extraction is an agreed upgrade for narrative understanding, not a blanket
replacement for reliable code. Model/provider and vector-store selections remain
open; this plan does not authorise paid runs or external deployment.

## Recorded follow-up gaps

- **Exhibit ingestion:** the downloader currently retrieves only each filing's
  primary document. Apple earnings 8-Ks can therefore yield an announcement rather
  than financial results because the earnings release is in Exhibit 99.1. Add
  relevant-exhibit discovery, download, validation and source linkage as a separate
  ingestion enhancement before upgrade 6. This is outside branch 2; an LLM cannot
  recover attachments that were never ingested.
- **Narrative quality (upgrade 6):** Apple 10-Q output can retain forward-looking
  warnings, page labels and disconnected highlights. Improve and evaluate evidence
  selection with LLM narrative extraction. The branch-2 fixes change section
  selection only, not sentence ranking or semantic quality.
- **Resolved in branch 2:** Amazon's three observed unavailable 8-K summaries came
  from selecting contents entries rather than body disclosures. This is covered
  by the expanded development suite and section-boundary regression tests. Earnings
  announcements may still be short until exhibits are ingested.

## Data and evaluation

Sources are SEC submissions metadata, 10-K/10-Q/8-K filing HTML and, in the
target pipeline, structured XBRL financial facts. Preserve source snapshots,
accession numbers, reporting periods, filing dates, units and transformation
identity so results can be checked against the original disclosure. Generated
bulk data stays outside Git; use small synthetic or sanitised test fixtures.

Financial validation must distinguish instant from duration facts, standalone
quarters from year-to-date totals, annual from quarterly periods, fiscal-year
differences, amended/restated values and alternative accounting tags. Missing
values must not become zero. Compare companies only on explicitly aligned units
and periods, and label any differences.

The example mixed question is: how did a company's gross margin change between
two fiscal years, and what explains it? Calculate each margin and its
percentage-point change from validated facts, retrieve relevant explanations,
and cite both numerical sources and narrative evidence. If inputs or explanations
are unavailable, state the gap instead of inventing an answer.

Evaluation cases should cover the configured companies and filing forms. Keep
development and final confirmation cases separate. Numerical tolerances,
retrieval/answer-quality thresholds, latency/cost budgets, historical coverage
and retention policy remain to be agreed before release claims. See
[project checks](project-checks.md) for planned validation gates.

## Operating assumptions

- The current scripts run in order from the repository root, with one operator.
- Configure an identifying SEC contact header before fetching live data.
- Current checkpoints are local files; database and vector persistence are planned.
- Keep raw source snapshots and expose failed or missing records to the operator.
- Use allowlisted, parameterised analytical queries or controlled functions;
  do not execute unrestricted LLM-generated SQL.
- Treat filing content as data, including text retrieved into an LLM prompt.
- Model training, stock-price prediction, automated trading and investment
  recommendations are outside the platform's current scope.

Check commands and verification gaps live in [project checks](project-checks.md).
