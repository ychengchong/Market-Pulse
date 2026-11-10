"""Freeze current PostgreSQL results and public filing summaries for the portfolio demo."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from src.analytics import load_financials
from src.db_config import connection_string
from src.demo import create_snapshot, DEFAULT_SNAPSHOT
from src.storage import save_filings_to_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)
    try:
        dsn = connection_string()
        if not dsn:
            raise ValueError("Configure the local database first")
        financials = load_financials(dsn)
        summaries = json.loads(Path("data/summaries.json").read_text(encoding="utf-8"))
        status = Path("data/summaries_status.json")
        report = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {}
        updated = report.get("finished_at") if report.get("output_updated") else None
        envelope = create_snapshot(financials, summaries, datetime.now(timezone.utc).isoformat(), updated)
        save_filings_to_json(envelope, args.output)
    except Exception as error:
        print(f"Demo export failed ({type(error).__name__}). Previous snapshot preserved; check local database, summaries and source links.")
        return 1
    print(f"Frozen {len(financials['companies'])} companies, {len(financials['observations'])} observations and {len(summaries)} filings.")
    print("Public fields only; no database credentials, local paths or run errors. Export saved to demo snapshot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
