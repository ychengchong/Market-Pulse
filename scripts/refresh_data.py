"""Refresh financial sources and publish them to PostgreSQL in one command."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.db_config import connection_string
from src.database import migrate, import_dataset
from src.storage import save_filings_to_json
import psycopg
from scripts import ingest_financials


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date")
    parser.add_argument("--as-of")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    report = dict(status="running", started_at=datetime.now(timezone.utc).isoformat(), stage="connection")
    output = "data/refresh_status.json"
    save_filings_to_json(report, output)
    try:
        dsn = connection_string()
        if not dsn:
            raise ValueError("Database connection is not configured")
        # Check connectivity/schema first so an unavailable database causes no SEC calls.
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10, application_name="market-pulse-refresh") as conn:
            migrate(conn)
            report["stage"] = "ingestion"
            arguments = []
            for key in ("start_date", "as_of"):
                if getattr(args, key):
                    arguments.extend(["--" + key.replace("_", "-"), getattr(args, key)])
            if args.offline:
                arguments.append("--offline")
            if ingest_financials.main(arguments) != 0:
                raise ValueError("Source ingestion did not complete")
            report["stage"] = "import"
            result = import_dataset(conn, Path("data/financial_facts.json"))
        report.update(status="success", stage="complete", result=result)
        print(f"Refreshed {result['companies']} companies; {result['selected_observations']} selected observations are in PostgreSQL.")
        return_code = 0
    except (psycopg.Error, OSError, ValueError, KeyError, TypeError, SystemExit) as error:
        report.update(status="failed", error_kind=type(error).__name__)
        print(f"Refresh stopped at {report['stage']} ({type(error).__name__}). Previous database results are preserved; check connection settings and source status.")
        return_code = 1
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_filings_to_json(report, output)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
