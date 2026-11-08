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

Next in the agreed sequence: reproducibility and the reviewed evaluation baseline,
then the XBRL-to-PostgreSQL analytics path before adding an LLM.

The supplied development-duration estimates are planning suggestions, not
committed delivery dates. No paid provider or external deployment is selected.

## Agreed upgrade order

This is the agreed implementation sequence. Upgrade 1 has an implementation
and verification described above; the remaining upgrades are planned. The three
milestones above group the same work.

1. **Reliable ingestion:** diagnose SEC download failures, validate responses,
   expose per-filing failures and prevent failed runs from silently replacing
   useful outputs with empty results.
2. **Reproducibility and baseline:** lock dependencies, create a small reviewed
   filing evaluation set and preserve rule-based outputs for comparison.
3. **Structured financial ingestion:** ingest XBRL company facts with source,
   unit and period provenance; validate tag mappings, fiscal calendars,
   amendments and standalone-quarter versus year-to-date semantics.
4. **PostgreSQL persistence:** store companies, filings, financial facts and
   processing status with relationships and repeatable, duplicate-safe loads.
   Retain source files with recorded locations and identities.
5. **Financial analytics:** implement controlled SQL/Python KPIs, trends and
   company comparisons in Streamlit, including clear missing-data handling.
6. **LLM narrative extraction:** retain deterministic HTML cleaning; extract
   events, risks, management explanations and entities into a validated schema
   with supporting passages and source locations. Compare accuracy, completeness,
   evidence support, cost and latency against the rule-based baseline.
7. **Filing retrieval:** build section-aware, source-linked chunks, embeddings
   and one vector store (pgvector or Chroma). Evaluate retrieval before generation.
8. **Cited research assistant:** answer narrative questions using retrieved
   evidence, citations and explicit abstention when support is insufficient.
   This query-time capability is distinct from ingestion-time extraction.
9. **Integrated routing:** route numerical, narrative and mixed questions to
   approved analytics functions, retrieval or both. Compose calculated figures
   and evidence-backed explanations without unrestricted LLM-generated SQL.
10. **Packaging and complete verification:** finish Dashboard, Ask AI and Company
    comparison tabs; introduce FastAPI at the service boundary and Docker for
    repeatable startup. Verify persistence, recovery and end-to-end correctness,
    extraction, retrieval, citation quality, cost and latency.

Keep deterministic parsing, XBRL validation and arithmetic where appropriate.
LLM extraction is an agreed upgrade for narrative understanding, not a blanket
replacement for reliable code. Model/provider and vector-store selections remain
open; this plan does not authorise paid runs or external deployment.

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
