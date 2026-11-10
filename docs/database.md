# PostgreSQL persistence

Upgrade 4 adds an explicit PostgreSQL importer for upgrade 3's validated XBRL
artifact. It does not change the existing filing dashboard to read SQL yet or
add charts; analytics and company comparisons are upgrade 5.

## Setup

Install PostgreSQL and create a **dedicated** local database, for example
`market_pulse`, owned by your local application role. The role needs permission to
create the `market_pulse` schema/tables on initial migration and read/write them
for imports. PostgreSQL 18.6 was verified. No hosted database is provisioned.
See [official Windows downloads](https://www.postgresql.org/download/windows/).

Install the updated [hash-locked runtime](reproducibility.md). Set your actual
connection string only in your local environment, using the placeholders below
as a guide. `.env.example` is a reference, not an automatically loaded config.
Never commit a real password or print the connection string in reports.

```powershell
python -m pip install --require-hashes -r requirements.txt
$env:DATABASE_URL = "postgresql://market_pulse:YOUR_PASSWORD@localhost:5432/market_pulse"
python database.py migrate
python database.py import
python database.py status
```

Use a URL-encoded password in a URI, or a properly quoted libpq connection string.
For hosted services, follow their TLS requirements. The CLI has a connection
timeout and returns 1 on failure; it does not log credentials or raw database
exception text. It reads `data/financial_facts.json` by default, or use
`python database.py import --input path/to/financial_facts.json`.

The importer also needs the original raw snapshot files under
`data/xbrl_snapshots/`. Transfer the artifact and corresponding snapshots together
when moving machines. It never downloads missing sources during import.

### Managed Windows driver fallback

The normal Psycopg binary wheel includes its client library. On the verification
machine, Windows Application Control blocked the wheel's native extension.
Psycopg's supported pure-Python implementation was verified with the official EDB
PostgreSQL client library instead. If you encounter the same restriction, set:

```powershell
$env:PG_LIBPQ_DIR = "C:/Program Files/PostgreSQL/18/bin"
python database.py status
```

Use your actual trusted PostgreSQL installation directory. This selects Python
mode unless `PSYCOPG_IMPL` was already explicitly set, and adjusts DLL search only
inside the Python process. It does not change Windows policy or machine-wide PATH.
The versioned package lock still includes both driver packages; the selected
implementation is recorded in the verification report.

The fresh verification environment installed all 39 locked packages and passed
all 22 database-specific checks. Its full 104-test run had one existing dashboard
failure because Windows Application Control blocked a Pandas native extension.
The complete 104-test suite passed in the established verified environment.
This OS-level fresh-environment limitation is recorded, not reported as a passing
clean-environment dashboard check; no security policy was changed.

## Schema

Migration SQL is in `migrations/`, scoped to the `market_pulse` schema. Other
schemas are not modified. Migrations run in a transaction under an advisory lock,
with lock/statement timeouts. Applied versions/checksums live in
`schema_migrations`. Re-running is safe; edited or unknown applied migrations are
refused. Add a new numbered migration instead of changing an applied file.
Automatic downgrade/destructive rollback migrations are not provided.

| Table/view | Purpose |
|---|---|
| companies | Stable CIK identity and first-imported display labels |
| snapshots | Immutable content identity and external raw-file/source locations |
| filings | Periodic source filing accession, date, form and SEC link |
| financial_facts | Immutable content-addressed source candidates; exact PostgreSQL NUMERIC values |
| datasets | Exact input-file SHA-256, requested window and first successful import time |
| dataset_companies | Snapshot retrieval, coverage, policy and generating-code identity for each company in a dataset |
| dataset_facts | Source candidates belonging to each dataset/company |
| observations | Dataset-specific selected/ambiguous/unsupported exact-period observations |
| ingestion_runs | One audit entry per import attempt, including repeat imports and failure classes |
| latest_company_datasets | Chooses the latest permitted as-of date per company, then source retrieval time and deterministic import ordering |
| current_financial_facts | Selected observations from those datasets, with values, periods and source provenance |

The database stores periodic filing references behind the financial facts. It
does not yet import the separate narrative 8-K browser records or filing text.
Missing metrics remain in coverage JSON; ambiguous/unsupported observations remain
queryable but do not enter the selected-facts view. Period labels retain upgrade
3's duration semantics; do not mistake TTM values for fiscal-year totals.

## Import guarantees and limits

Before business writes, the importer verifies snapshot paths/checksums/CIKs and
reconstructs each company record from its raw source using the supported policy.
A changed amount, selection, policy, coverage or incompatible schema is rejected.
The generating pipeline identity is retained as provenance, not replaced with the
current importer's version. All company records must use one history window.

One database transaction publishes the entire dataset. Source candidates and
filing identities are immutable through this importer. Repeated file imports
reuse the same dataset and facts; each attempt still gets a distinct audit run.
A conflicting filing identity fails the import rather than rewriting history.
Parameterised SQL carries values; the LLM never supplies database statements.
Concurrent imports are serialised with a schema-specific advisory lock.

On an exception, business writes roll back together and the attempt is marked
failed separately. A process crash/disconnection can leave a run marked running;
inspect server state before retrying. Retrying a committed input does not duplicate
business records. A connection failure may also prevent the final audit update.
Importing an older as-of dataset cannot replace a newer one in the current view.
Same-day snapshots prefer later retrieval times. This is a selection policy,
not proof of economic restatement or completeness. A newer dataset can have a
narrower history window; inspect its explicit window and coverage before analysis.
Company display-label changes require a later explicit policy; identifiers remain
CIKs. Database owners can still alter data outside the importer.

Raw snapshots remain outside PostgreSQL. Back up both database and raw files.
Do not treat retained JSON as a PostgreSQL backup. Example manual backup/restore
for a local installation (using its CLI authentication configuration):

```powershell
pg_dump -Fc -f data/market-pulse.dump market_pulse
createdb market_pulse_restore
pg_restore --no-owner --dbname=market_pulse_restore data/market-pulse.dump
```

Choose a new empty restore database, check restore errors, verify counts and
source links, and only then change the application connection. PostgreSQL upgrades,
remote deployment, automated backups and hosted operations are outside this branch.

## Verification

The normal test command runs unit checks and explicitly skips real database tests
when no test connection is configured. To include them:

```powershell
$env:MARKET_PULSE_TEST_DATABASE_URL = "postgresql://TEST_ROLE:TEST_PASSWORD@localhost:5432/TEST_DATABASE"
python -B -m unittest discover -s tests -v
```

Use a disposable local test database. Integration tests create uniquely named
`mp_test_<uuid>` schemas and drop **only those schemas** during cleanup; the role
needs schema creation permission. Tests cover real migrations/checksums,
NUMERIC precision, source links, missing/ambiguous values, complete transaction
rollback, repeated/concurrent imports and older-snapshot ordering. A synthetic
fixture's annual filing accession was corrected to differ from its quarterly
filing; one accession must not claim two different filing dates.

The full cached five-company artifact was separately loaded twice. Counts and
bounded evidence are recorded in [postgres-storage-v1.json](../reports/postgres-storage-v1.json).
An isolated official EDB binary cluster was used under ignored `data/postgres-test/`
with password authentication on localhost port 55439. It is a verification setup,
not a registered Windows service or production deployment. The server is stopped
at the end of verification; its files are retained locally and never committed.
