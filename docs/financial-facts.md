# Financial-fact ingestion

Upgrade 3 adds a separate structured-data path. It does not change the narrative
filing limit, download exhibits, create PostgreSQL tables or add financial charts.
The configured watchlist remains authoritative in `config.py`.

## Run

Use the [locked environment](reproducibility.md), from the repository root:

```powershell
python ingest_financials.py --start-date 2021-01-01 --as-of 2026-11-09
```

This makes one companyfacts request per configured company, using the existing
SEC request policy. It retains exact response body bytes under
`data/xbrl_snapshots/<cik>/<sha256>.json` and updates that company's `latest.json`
descriptor. Identical snapshots are reused; existing content-addressed snapshots
are never overwritten. Only snapshots passing JSON/CIK/root-shape validation are
saved. Download errors remain visible in the stage report.

Replay the saved snapshots without network access:

```powershell
python ingest_financials.py --offline --start-date 2021-01-01 --as-of 2026-11-09
```

The default `as-of` is today's Singapore date. The default start is January 1 five
years before the as-of year. The window includes observations **ending** on or
after start-date and excludes disclosures **filed** after as-of. This preserves
historical comparatives without pretending a filing's FY/FP labels describe each
comparative period. Invalid windows are refused before ingestion.

## Output and publication

`data/financial_facts.json` is an array of company records, each with:

- Schema and selection-policy versions, company/ticker/CIK and requested window.
- Raw snapshot digest/path, retrieval timestamp and SEC source URL.
- Generating code digests, actual Python/requests versions and dependency-lock digest.
- `candidates`: distinct validated mapped facts, including earlier disclosures.
- `observations`: exact metric/start/end/unit groups, their selection status and
  selected source candidate (or null if ambiguous/unsupported).
- `coverage`: per-metric selected counts, missing states and ambiguous counts.
- Rejection details and counts of excluded forms, currencies and dates.

Source candidates retain taxonomy/tag, exact decimal value, USD unit, start/end
(or instant date), duration, filing date, accession, form, filing FY/FP, optional
SEC frame and a link to the original filing index. Decimal values are **strings**
to preserve precision; consumers should use Decimal or database NUMERIC, not
binary floating-point for financial arithmetic.

The stage writes `data/financials_status.json`, including per-company coverage and
validation failures. Exit code 0 means a complete nonempty batch was published.
A failed company, malformed mapped fact or wholly unselectable company returns 1
and preserves the previous complete dataset. Missing individual metrics and
ambiguous periods are explicitly reported and do not invalidate otherwise usable
company data. No missing value becomes zero. Snapshot files can still be retained
for diagnosis when normalisation fails. Concurrent runs remain unsupported.

## Initial metric mapping

Only entity-wide `us-gaap` facts in **USD** are mapped. Non-USD values are counted
and excluded; there is no currency conversion. Source APIs can omit custom or
segment-specific facts, so coverage is not guaranteed for every company/metric.

| Metric | Candidate tags |
|---|---|
| Revenue | RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet |
| Net income | NetIncomeLoss |
| Gross profit | GrossProfit |
| Operating income | OperatingIncomeLoss |
| Assets | Assets |
| Liabilities | Liabilities |
| Operating cash flow | NetCashProvidedByUsedInOperatingActivities |

Mappings are an initial explicit policy, not an independently reviewed accounting
ontology. Do not add component/segment tags as substitutes for total revenue.
Validate new mappings against source financial statements before using them.

## Periods and revision policy

Only 10-K, 10-K/A, 10-Q and 10-Q/A source facts are eligible. Assets/liabilities
require instant facts; the other mapped metrics require valid duration dates.
Dates must be valid and cannot end after their filing date. Values must be finite
JSON numbers; booleans, numeric strings and malformed mapped records are rejected.

Duration labels are **day-count buckets, not verified fiscal labels**:

| Label | Inclusive days | Interpretation |
|---|---|---|
| quarter_duration | 70-110 | Approximately three months; no Q1/Q2/Q3/Q4 inferred |
| six_month_duration | 150-210 | Approximately six months; often cumulative, not a standalone quarter |
| nine_month_duration | 240-300 | Approximately nine months; often cumulative, not a standalone quarter |
| year_duration | 330-400 | Approximately twelve months; can be fiscal-year or trailing-twelve-month data |
| other_duration | Any other positive duration | Retained but not selected for analytics |

Instant values are labelled `instant`. Exact period boundaries remain the basis
for identity. A quarter and a cumulative six-month fact with the same end date
are distinct observations. Fiscal calendars may differ by company and may use
52/53-week years. Do not compare periods solely using these duration labels.

For each exact metric/start/end/unit group:

1. Retain every distinct validated source candidate and remove exact repeats.
2. Consider candidates with the latest filing date permitted by as-of, including
   amended filings and later comparative disclosures.
3. If those candidates disagree on value, mark the observation ambiguous and
   select nothing. Tag priority never overrides a numerical conflict.
4. If they agree, select deterministically using declared tag order and accession;
   all alternative candidates remain available for audit.

This does not establish that the latest disclosure is an economic restatement;
it is a latest-filed selection policy. The current companyfacts snapshot is not a
complete historical archive, so a filing-date cutoff cannot recover facts no
longer present upstream. Preserve snapshots for repeatable historical research.

Quarter-only cash flow, Q4 derivation, ratios, gross-profit derivation and
liabilities derived from assets/equity are **not** computed here. Such arithmetic
needs explicit fiscal-boundary, accounting-definition and revision compatibility
checks before analytics. Missing source tags stay missing in this branch.

## Verification and remaining work

Run `python -B -m unittest discover -s tests -v`. Synthetic fixture tests cover
precision, revisions, aliases/conflicts, missing values, currencies, dates,
quarter/cumulative separation, 53-week years, TTM semantics, immutable snapshots,
checksum failures, repeat loads and preservation of prior outputs on failure.
See [the verification record](../reports/xbrl-ingestion-v1.json) for bounded live
and offline evidence. Live checks establish API/schema coverage; they do not
independently audit every financial value against financial statements.

The validated output can now be loaded with the [PostgreSQL importer](database.md).
Financial dashboard charts and controlled calculations follow in upgrade 5. Relevant-exhibit ingestion is
still a separate prerequisite before LLM narrative extraction.

Sources: [SEC companyfacts API and scope](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
and [SEC automated access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
