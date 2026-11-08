# Architecture and component contracts

## Implemented flow and boundaries

```text
SEC submissions -> main.py -> data/filings.json
SEC filing HTML + filings.json -> process_filings.py
  -> data/raw_html/<accession>.html
  -> data/clean_text/<accession>.txt
  -> data/processed_filings.json
processed_filings.json + clean text -> summarize_filings.py
  -> data/summaries.json -> dashboard.py
```

All relative paths resolve from the working directory. The scripts orchestrate
the stages; `src/` owns reusable operations. No individual component owner or
deployment record is configured.

| Capability | Implementation | Contract and failure behaviour |
|---|---|---|
| Metadata retrieval | `src/sec_client.py` | Returns records with `company`, `ticker`, `cik`, `form`, `filing_date`, `accession_number`, `document`, and `filing_url`. Dates are SEC strings; identifiers are strings. Request failures propagate; `main.py` logs them and continues to the next company. |
| Metadata storage | `src/storage.py` | Writes a UTF-8 JSON array to `data/filings.json` by default. Filesystem errors propagate. |
| HTML download | `src/filing_downloader.py` | Returns HTML text. Connection errors and timeouts are retried up to three attempts with exponential waits; HTTP failures propagate immediately. |
| Text extraction | `src/html_parser.py` | BeautifulSoup with lxml removes scripts, hidden elements and selected XBRL tags, then returns nonempty lines. The processing script treats empty output as failure. |
| Processing checkpoint | `process_filings.py` | Copies metadata and adds `html_path`, `text_path`, `text_characters`, `processing_status`, and `processing_error`. Failed records have null paths, zero characters and an error string. Records remain in the checkpoint. |
| Summary generation | `src/summarizer.py`, `summarize_filings.py` | Summary records retain source metadata except `document`, adding `event_type`, `summary`, `source_word_count`, and `summary_method`. Failed processing records and missing text files are skipped with console messages. Empty or unsuitable text produces explanatory fallback text. |
| Display | `dashboard.py` | Loads the summaries array and filters by company/form. A missing file produces a Streamlit error and stops the page. Malformed JSON or missing fields are not recovered. |

The JSON contracts are currently implicit in these implementations; they have
no schema version or formal validation. The summariser selects `8-K` rules for
that form and uses `10-Q` rules for all other supplied forms, including `10-K`.

## State, recovery and limitations

- Each stage overwrites its JSON output. Writes are not atomic, and concurrent
  runs are unsupported. There is no append-only audit history.
- Reprocessing reuses any nonempty HTML cache file with the same accession
  number, regenerates text and overwrites the processing checkpoint. Cache
  compatibility is not checked against URL, code or dependency identity.
- Metadata collection still writes an array when some or all companies fail.
  Summary output omits failed records; consult the processing checkpoint and
  console output for coverage.
- To change parsing rules, rerun processing and summarisation. To change summary
  rules, rerun summarisation. To fetch fresh HTML, deliberately remove the
  relevant local cached HTML before reprocessing.
- Preserve a copy of `data/` before replacing checkpoints if prior results must
  remain available. Restart reads files; it does not restore execution progress.
- The dashboard is local. Authentication, tenant isolation, production readiness
  gates, deployment automation and release manifests are not implemented.

## Target architecture (planned)

The delivery order and acceptance evidence live in [the project brief](problem.md).
The following components describe the target; they are not currently running.

```mermaid
flowchart TD
    SEC[SEC metadata, filings and XBRL facts] --> ETL[Python: extract, validate, transform, load]
    ETL --> SQL[PostgreSQL: normalised financial facts]
    ETL --> TEXT[Filing sections and source-linked chunks]
    TEXT --> VECTOR[Embeddings: pgvector or Chroma]
    SQL --> ANALYTICS[Controlled SQL and Python analytics]
    VECTOR --> RAG[Retrieval and cited narrative answers]
    QUERY[User question] --> ROUTER[Query router]
    ROUTER --> ANALYTICS
    ROUTER --> RAG
    ANALYTICS --> ANSWER[Evidence-backed result composition]
    RAG --> ANSWER
    ANSWER --> UI[Streamlit: Dashboard, Ask AI, Company comparison]
```

PostgreSQL is the planned home for structured analytics. The vector-store choice
remains open: pgvector can share PostgreSQL persistence, while Chroma would be
a separate store. Choose one when implementing retrieval. Provider/model choice,
embedding model and historical ingestion range are also unconfigured.

| Planned boundary | Required contract |
|---|---|
| Source ingestion | Store snapshot identity, retrieval time, source URL, CIK and accession where applicable; preserve raw payloads and report validation failures. |
| Normalised facts | Retain taxonomy/tag, unit, start/end or instant date, fiscal period, form, filing date and accession. Define selection rules for amendments, duplicate facts and tag mappings before calculating KPIs. Preserve source candidates alongside selected values. |
| Analytics | Accept validated company/metric/period inputs; use parameterised queries or allowlisted functions. Return value, unit, reporting period, formula and source identities. Refuse ambiguous or unavailable comparisons. |
| Narrative index | Retain accession, URL, section, chunk offsets and content hash. Record parser/chunking and embedding identities. Rebuild affected chunks or the index when those identities change incompatibly. |
| Retrieval and generation | Return evidence with citations. Distinguish absent evidence from retrieval/provider failure; abstain when unsupported. Retrieved prose cannot authorise tool calls or change system instructions. |
| Router and composition | Choose analytics, retrieval or both. Take numbers from analytical outputs and explanations from retrieved evidence; retain provenance through final rendering. |

Loads must be repeatable without duplicate selected facts or chunks. Keep filing
date/availability separate from reporting period for historical comparisons.
Any future point-in-time research must exclude information filed after its
cutoff. Planned evaluation must exercise these boundaries before live claims.

FastAPI and Docker are planned for the integration milestone, after the local
analytics and research paths work. Database migrations, persistence volumes,
startup checks, environment locking and recovery commands must be documented
and verified at implementation time. No deployment is implied by this design.

Dependency locking and representative quality evaluation remain future work;
see [project checks](project-checks.md).
