"""Fetch and validate financial facts independently of the narrative pipeline."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import platform

import requests

from config import SEC_HEADERS, WATCHLIST
from src.sec_http import SecAccessError
from src.storage import finish_stage, start_stage
from src.xbrl import get_snapshot, iso_date, normalise_company


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    parser.add_argument("--as-of", default=today.isoformat(), help="Exclude facts filed after this YYYY-MM-DD date (default: today in Singapore)")
    parser.add_argument("--start-date", help="Include periods ending on/after this date (default: January 1 five years before as-of)")
    parser.add_argument("--offline", action="store_true", help="Replay locally saved snapshots; make no network requests")
    args = parser.parse_args(argv)
    try:
        cutoff = iso_date(args.as_of)
        since = args.start_date or f"{cutoff.year - 5:04d}-01-01"
        if iso_date(since) > cutoff:
            raise ValueError("start-date must be on or before as-of")
    except ValueError as error:
        parser.error(str(error))
    report = start_stage("financials")
    root = Path(__file__).resolve().parents[1]
    identity = dict(
        python=platform.python_version(), requests=requests.__version__,
        code_sha256={name: hashlib.sha256((root / name).read_text(encoding="utf-8").encode()).hexdigest()
                     for name in ("scripts/ingest_financials.py", "src/xbrl.py", "src/sec_http.py", "src/storage.py")},
        requirements_sha256=hashlib.sha256((root / "requirements.txt").read_text(encoding="utf-8").encode()).hexdigest()
    )
    report.update(start_date=since, as_of=args.as_of, mode="offline" if args.offline else "live", pipeline_identity=identity)
    records, items = [], []
    blocked = False
    for company, details in WATCHLIST.items():
        item = dict(company=company, ticker=details["ticker"])
        try:
            if blocked and not args.offline:
                raise SecAccessError("Not requested after an SEC access denial or persistent rate limit earlier in this run.")
            payload, snapshot = get_snapshot(details["cik"], SEC_HEADERS, report["started_at"], offline=args.offline)
            record = normalise_company(payload, company, details, snapshot, since, args.as_of)
            record["pipeline_identity"] = identity
            item.update(snapshot=snapshot, coverage=record["coverage"],
                        rejected_facts=record["rejected_facts"], excluded_counts=record["excluded_counts"])
            if record["rejected_facts"]:
                raise ValueError(f"{len(record['rejected_facts'])} malformed mapped USD facts; see financials_status.json")
            count = sum(row["status"] == "selected" for row in record["observations"])
            if not count:
                raise ValueError("No selectable financial facts in the requested window")
            records.append(record)
            item.update(status="successful", error=None, selected_periods=count)
            missing = [metric for metric, coverage in record["coverage"].items() if coverage["status"] != "available"]
            print(f"{company}: {count} selected observations; unavailable metrics: {', '.join(missing) or 'none'}")
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as error:
            blocked = blocked or isinstance(error, SecAccessError)
            item.update(status="failed", error=str(error))
            print(f"{company}: {error}")
        items.append(item)
    return finish_stage(report, records, items, "data/financial_facts.json")


if __name__ == "__main__":
    raise SystemExit(main())
