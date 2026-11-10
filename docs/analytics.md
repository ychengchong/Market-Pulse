# Financial analytics

Upgrade 5 adds three Streamlit tabs: Financial overview, Company comparison and
Filings. The first two use PostgreSQL exclusively; the last retains the original
JSON filing browser. No AI provider, stock-price feed or new dependency is added.

## Startup and refresh

From the repository root, with the locked environment active and PostgreSQL
running, use `python configure_database.py` once. It prompts for a password,
verifies connectivity and saves the connection in ignored
`.streamlit/secrets.toml`. Defaults match the local `Market Pulse` database;
`--database`, `--user`, `--host` and `--port` support other installations.
Existing settings are not replaced without `--replace`. The file contains a
credential: keep it private and outside Git/backups intended for sharing.
Environment `DATABASE_URL` overrides the local file. These same settings are
used by the app, `database.py` and `refresh_data.py`; `.env` is not auto-loaded.

```powershell
python refresh_data.py
python -m streamlit run dashboard.py
```

The refresh checks connectivity and migrates before making SEC requests, then
calls the existing financial ingestion and verified transactional importer.
The history arguments `--start-date` and `--as-of` are forwarded unchanged.
For a repeatable replay of existing snapshots without SEC access:

```powershell
python refresh_data.py --offline --start-date 2021-01-01 --as-of 2026-11-09
```

Only a complete validated ingestion can be imported. Import failures retain
previous committed business data. Filesystem checkpoints and PostgreSQL are
separate publications: a new valid JSON checkpoint can exist even if its SQL
import fails; rerun the command to recover. `data/refresh_status.json` reports
the failed stage without database credentials. The app warns on failed or
unfinished attempts and continues using committed database results. Concurrent
refresh commands are unsupported because upstream file publication is sequential.
This command refreshes financial facts only; narrative commands remain separate.

PostgreSQL runs independently of pgAdmin. The app opens a bounded read-only,
repeatable-read transaction per Streamlit rerun. Reload or interact with the page
after an import to read the latest state. No background scheduler, automatic
monthly refresh or public deployment is installed here.

## Numerical and period contracts

- Queries choose the existing latest dataset **per company**, preserving its
  as-of date, retrieval time, raw snapshot and source filing identity. Ambiguous
  observations remain visible as missing rather than being silently dropped.
- Revenue anchors define exact duration boundaries. Annual mode requires
  annual-length revenue evidence in a 10-K/10-K/A with FY metadata, rather than
  treating every year-length (potentially TTM) fact as annual. This is an evidence
  filter, not a guarantee against all issuer tagging mistakes. Exact dates are
  displayed; FY/FP metadata is never converted into invented fiscal labels.
- Quarterly mode uses directly reported quarter-length revenue intervals. Six-
  and nine-month totals are excluded. No Q4 or standalone cash-flow quarter is
  derived by subtraction; gaps therefore remain for some companies.
- Income and cash flow must match the revenue interval exactly. Assets and
  liabilities must be instant facts on that interval's end date. Missing or
  ambiguous values remain `Unavailable`; a reported zero remains zero.
- Net, operating and gross margins are their respective profit divided by revenue
  times 100. Denominators must be positive. Negative profit is permitted.
- Revenue YoY growth is `(current / prior - 1) * 100`, requiring a unique prior
  period ending 351–379 days earlier, with duration differing by at most 7 days,
  and positive prior revenue. The prior interval is shown in calculation details.
  This supports common 52/53-week calendars without assigning fiscal quarters.
- PostgreSQL NUMERIC and Python Decimal preserve input precision for calculations.
  Charts alone convert scaled values to float; source tables/CSV retain exact
  decimal strings. Amounts are USD; charts use billions, margins use percentages.

Comparison chooses one unique reported interval per company in the selected
calendar end-year (and calendar end-quarter for quarterly mode). Multiple or zero
eligible intervals produce an unavailable entry. Different dates trigger a
warning and are shown in the table and tooltips. An optional exact-end-date
filter is stricter but does not guarantee identical period starts; inspect both
dates. These are disclosed-period comparisons, not currency-adjusted, sector-
normalised or same-fiscal-quarter investment rankings.

The current as-of cutoff and source revision policy are inherited from XBRL
ingestion. This is not a complete historical point-in-time backtesting database.
No omitted tag is inferred from an accounting identity. In the cached watchlist,
Alphabet lacks mapped gross profit; Amazon lacks mapped gross profit/liabilities.
Do not treat missing source coverage as zero economic activity.

## Verification and remaining scope

Synthetic cases independently specify expected loss/zero margins, YoY growth,
missing cash flow, TTM exclusion, exact boundaries and comparison ambiguity.
Real PostgreSQL tests verify selected/ambiguous query results and source links.
Streamlit AppTest exercises charts, reporting-mode changes, empty comparisons
and database-failure isolation. See [project checks](project-checks.md) and the
[verification record](../reports/financial-analytics-v1.json).

The dashboard was also opened against the isolated database using the cached
five-company dataset. This verifies integration and rendering; it is not an
independent accounting audit or human-reviewed financial benchmark. Portfolio
hosting and monthly scheduling remain future scope; AI upgrades are deferred.
