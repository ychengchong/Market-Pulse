"""Atomic local checkpoints and explicit per-stage run reports."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def atomic_write_bytes(file_path, content):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_text(file_path, text):
    atomic_write_bytes(file_path, text.encode("utf-8"))


def save_filings_to_json(filings, file_path="data/filings.json"):
    atomic_write_text(file_path, json.dumps(filings, indent=2, ensure_ascii=False))


def load_records(file_path):
    with Path(file_path).open(encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError(f"{file_path} must contain an array of records")
    return records


def start_stage(stage):
    report = {
        "stage": stage, "status": "running", "output_updated": False,
        "started_at": datetime.now(timezone.utc).isoformat(), "items": []
    }
    save_filings_to_json(report, f"data/{stage}_status.json")
    return report


def finish_stage(report, records, items, output_file):
    """Publish only a complete nonempty batch; always retain attempt details."""
    failed = sum(item["status"] == "failed" for item in items)
    report.update(
        status=("partial" if records else "failed") if failed else
               ("success" if records else "empty"),
        finished_at=datetime.now(timezone.utc).isoformat(),
        attempted=len(items), failed=failed, records=len(records), items=items,
        output_file=str(output_file), output_updated=False
    )
    status_path = f"data/{report['stage']}_status.json"
    # Record the attempt before replacing the checkpoint. If interrupted, the
    # dashboard conservatively treats its freshness as unconfirmed.
    save_filings_to_json(report, status_path)
    if records and not failed:
        save_filings_to_json(records, output_file)
        report["output_updated"] = True
        save_filings_to_json(report, status_path)
        print(f"Saved {len(records)} records to {output_file}")
        return 0
    print(f"{report['stage']}: {report['status']}; previous {output_file} preserved.")
    return 1
