from pathlib import Path
import requests

from config import SEC_HEADERS
from src.filing_downloader import download_filing_html
from src.html_parser import html_to_text
from src.sec_client import validate_filing
from src.sec_http import SecAccessError, validate_html
from src.storage import atomic_write_text, load_records, start_stage, finish_stage


# Set to an integer for a bounded processing run; None processes all records.
PROCESS_LIMIT = None


def main():
    report = start_stage("processing")
    output = "data/processed_filings.json"
    try:
        filings = load_records("data/filings.json")
    except (OSError, ValueError) as error:
        return finish_stage(report, [], [{"status": "failed", "error": str(error)}], output)
    if PROCESS_LIMIT is not None:
        filings = filings[:PROCESS_LIMIT]
    records, items = [], []
    blocked = False
    for filing in filings:
        record = filing.copy()
        item = {key: filing.get(key) for key in ("company", "form", "accession_number")}
        try:
            validate_filing(filing)
            accession = filing["accession_number"]
            html_path = Path("data/raw_html") / f"{accession}.html"
            text_path = Path("data/clean_text") / f"{accession}.txt"
            html = None
            if html_path.exists():
                try:
                    html = validate_html(html_path.read_text(encoding="utf-8"))
                except (ValueError, SecAccessError):
                    print(f"Ignoring invalid cached HTML for {accession}.")
            if html is None:
                if blocked:
                    raise SecAccessError("Not requested after an SEC access denial or persistent rate limit earlier in this run.")
                html = download_filing_html(filing["filing_url"], SEC_HEADERS)
                atomic_write_text(html_path, html)
            text = html_to_text(html)
            if not text.strip():
                raise ValueError("No readable text was extracted")
            atomic_write_text(text_path, text)
            record.update(html_path=html_path.as_posix(), text_path=text_path.as_posix(),
                          text_characters=len(text), processing_status="successful", processing_error=None)
            item.update(status="successful", error=None)
            records.append(record)
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as error:
            blocked = blocked or isinstance(error, SecAccessError)
            record.update(html_path=None, text_path=None, text_characters=0,
                          processing_status="failed", processing_error=str(error))
            item.update(status="failed", error=str(error))
            print(f"{filing.get('accession_number', 'Invalid record')}: {error}")
        # Attempts include failed records even when the previous checkpoint is kept.
        item["record"] = record
        items.append(item)
    return finish_stage(report, records, items, output)


if __name__ == "__main__":
    raise SystemExit(main())
