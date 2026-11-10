from config import WATCHLIST, SEC_HEADERS, WANTED_FORMS, MAX_FILINGS_PER_COMPANY
from src.sec_client import get_recent_filings
from src.sec_http import SecAccessError
from src.storage import start_stage, finish_stage
import requests


def main():
    print("MARKET PULSE - SEC FILING MONITOR")
    report = start_stage("metadata")
    all_filings, items = [], []
    blocked = False
    for company, details in WATCHLIST.items():
        item = {"company": company, "ticker": details["ticker"]}
        try:
            if blocked:
                raise SecAccessError("Not requested after an SEC access denial or persistent rate limit earlier in this run.")
            filings = get_recent_filings(company, details, SEC_HEADERS, WANTED_FORMS, MAX_FILINGS_PER_COMPANY)
            all_filings.extend(filings)
            item.update(status="successful", records=len(filings), error=None)
            print(f"{company}: {len(filings)} filings")
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            blocked = blocked or isinstance(error, SecAccessError)
            item.update(status="failed", records=0, error=str(error))
            print(f"{company}: {error}")
        items.append(item)
    return finish_stage(report, all_filings, items, "data/filings.json")


if __name__ == "__main__":
    raise SystemExit(main())
