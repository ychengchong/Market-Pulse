# Frozen portfolio demo

This entry point serves the same three dashboard tabs from `snapshot.json`.
It needs no PostgreSQL, password, SEC contact email, AI provider or scheduler.
Visitors can change filters and graphs; source data changes only when the owner
exports and publishes a replacement. A Snapshot demo badge and company-specific
data-as-of dates distinguish this from a continuously updated application.
Company and filing-form filters, with short explanations, appear directly above
the filings. All three tabs use the full main page; there is no filter sidebar.

The snapshot currently contains five companies, 1,003 financial observations,
annual-period evidence and 25 filing highlights. It is an allowlisted export of
public company financials and summaries, about 0.6 MB. Exact decimal strings,
reporting intervals, selected/missing statuses and SEC source links are preserved.
Source dataset/snapshot identifiers remain available in Sources. The envelope
contains an export time and SHA-256 integrity check; it is not an external audit
or cryptographic signature. Raw source files and local run errors are excluded.

## Preview locally

Use the existing locked Windows environment, from the repository root:

```powershell
python -m streamlit run demo/dashboard.py
```

You can stop your local PostgreSQL service and this entry point will still work.
There is no database fallback: missing/corrupt demo data produces an explicit
error. For local PostgreSQL results, continue using `dashboard.py` at the root.

## Deploy to Streamlit Community Cloud

1. Commit and push this branch, including `demo/snapshot.json`, this entry point,
   `demo/requirements.txt`, shared `src/` code and `.streamlit/config.toml`.
   Do not include `.streamlit/secrets.toml`; it remains ignored.
2. Sign into <https://share.streamlit.io/> with GitHub and select Create app,
   then deploy from an existing repository.
3. Use repository `ychengchong/SEC-Filing-Monitor`, branch `feat/portfolio-demo`,
   **main file path `demo/dashboard.py`**.
4. In Advanced settings choose **Python 3.14**. Leave Secrets empty. Deploy.
5. Verify Financial overview, Company comparison and Filings on the resulting
   URL, including filters and Sources/CSV. Put the observed real URL in README
   as Live Demo; no placeholder deployment URL is claimed here.

Community Cloud checks the entry-point directory for dependencies before the
repository root. The Linux x86_64/CPython 3.14 hash lock here is therefore separate
from the root's Windows-specific lock. Do not choose root `dashboard.py` for this
deployment: it requires your PostgreSQL data and root runtime environment.

Official guidance: [deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[dependency file selection](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
Free apps can sleep after inactivity; visitors may need to wake the app. Free
availability and uptime are not guaranteed indefinitely. There are no paid AI
calls in this demo.

## Update only when wanted

No refresh is needed for ordinary visitors. To publish new financial data later,
with your local PostgreSQL running and configured:

```powershell
python -m scripts.refresh_data
if ($LASTEXITCODE -eq 0) { python -m scripts.export_demo }
```

To change filing highlights too, run the existing narrative pipeline successfully
before exporting. `scripts/export_demo.py` freezes the currently saved summaries; it does
not fetch or regenerate them. Check their generation/filing dates in Filings.
Run only `python -m scripts.export_demo` to freeze your existing database and summaries
without any new SEC requests. The exporter verifies the snapshot before atomic
replacement and preserves the previous export on failure.

Review the snapshot and local preview, then publish deliberately:

```powershell
git add demo/snapshot.json
git commit -m "Refresh frozen portfolio data"
git push
```

GitHub publication updates the deployed branch; loading the app does not perform
ingestion or write data. The local working tree snapshot is not a remote backup
until committed and pushed. Retain ignored raw sources and PostgreSQL backups
separately if you want to keep the full pipeline history.

## Dependency maintenance and checks

The demo runtime is pinned to Streamlit 1.67.0 and all resolved transitive versions.
Its wheels were downloaded for Linux and their hashes verified offline. This is
not evidence of a completed Linux installation or a successful hosted build; the
first cloud deployment remains a verification step. Existing Windows runtime and
summary baseline locks remain unchanged.

To deliberately regenerate the Linux lock into a new empty wheel directory:

```powershell
python -m pip download --only-binary=:all: --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 3.14 --implementation cp --abi cp314 --dest data/demo-linux-wheels-new streamlit==1.67.0
python -m scripts.lock_demo_dependencies --wheels data/demo-linux-wheels-new
```

Review dependency changes and verify a fresh Linux/hosted build before publishing.
`tests/test_demo.py` checks decimal precision, tampering, missing values, public
field allowlisting, failed-export preservation and all tabs without a database.
