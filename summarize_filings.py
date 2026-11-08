from pathlib import Path

from src.summarizer import create_summary
from src.storage import load_records, start_stage, finish_stage


def main():
    report = start_stage("summaries")
    output = "data/summaries.json"
    try:
        filings = load_records("data/processed_filings.json")
    except (OSError, ValueError) as error:
        return finish_stage(report, [], [{"status": "failed", "error": str(error)}], output)
    summaries, items = [], []
    for filing in filings:
        item = {key: filing.get(key) for key in ("company", "form", "accession_number")}
        try:
            if filing.get("processing_status") != "successful":
                raise ValueError(f"Processing failed: {filing.get('processing_error') or 'unknown error'}")
            text = Path(filing["text_path"]).read_text(encoding="utf-8")
            if not text.strip():
                raise ValueError("The processed filing contains no readable text")
            result = create_summary(text, form=filing["form"])
            record = {key: filing[key] for key in (
                "company", "ticker", "cik", "form", "filing_date", "accession_number", "filing_url"
            )}
            record.update(result)
            summaries.append(record)
            item.update(status="successful", error=None)
        except (OSError, ValueError, KeyError, TypeError) as error:
            item.update(status="failed", error=str(error))
            print(f"{filing.get('accession_number', 'Invalid record')}: {error}")
        items.append(item)
    return finish_stage(report, summaries, items, output)


if __name__ == "__main__":
    raise SystemExit(main())
