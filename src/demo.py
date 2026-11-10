"""Portable public snapshots. Loading needs neither database drivers nor secrets."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "demo/snapshot.json"
COMPANY_FIELDS = ("cik", "ticker", "name", "dataset_id", "snapshot_id", "retrieved_at", "start_date", "as_of")
OBSERVATION_FIELDS = ("cik", "metric", "value", "start_date", "end_date", "period_kind", "status", "tag", "accession", "filed", "form", "source_url", "unit")
SUMMARY_FIELDS = ("company", "ticker", "form", "filing_date", "event_type", "summary", "summary_method", "source_word_count", "filing_url")


def checksum(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def public_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "www.sec.gov" or parsed.username or parsed.password:
        raise ValueError("Snapshot source must be an official SEC HTTPS link")


def create_snapshot(financials, summaries, exported_at, summaries_updated_at=None):
    """Allowlist public fields; never serialize a DSN, local path or run error."""
    def public_rows(rows, fields):
        return [{key: str(row[key]) if isinstance(row[key], (date, datetime, Decimal)) else row[key]
                 for key in fields} for row in rows]
    payload = dict(exported_at=exported_at, summaries_updated_at=summaries_updated_at,
        financials=dict(companies=public_rows(financials["companies"], COMPANY_FIELDS),
            observations=public_rows(financials["observations"], OBSERVATION_FIELDS),
            annual_support=public_rows(financials["annual_support"], ("cik", "start_date", "end_date"))),
        summaries=public_rows(summaries, SUMMARY_FIELDS))
    envelope = dict(schema_version=1, sha256=checksum(payload), payload=payload)
    decode_snapshot(envelope)  # Refuse invalid snapshots before replacing anything.
    return envelope


def decode_snapshot(envelope):
    if envelope.get("schema_version") != 1 or checksum(envelope["payload"]) != envelope.get("sha256"):
        raise ValueError("Unsupported or corrupted demo snapshot")
    payload = envelope["payload"]
    datetime.fromisoformat(payload["exported_at"])
    if payload.get("summaries_updated_at") is not None:
        datetime.fromisoformat(payload["summaries_updated_at"])
    # Detach decoded objects; callers must not mutate the original export.
    data = json.loads(json.dumps(payload))
    financials = data["financials"]
    if not financials["companies"] or not financials["observations"] or not data["summaries"]:
        raise ValueError("A demo requires financial data and filing summaries")
    ciks = set()
    for company in financials["companies"]:
        if set(company) != set(COMPANY_FIELDS) or not all(isinstance(v, str) for v in company.values()):
            raise ValueError("Invalid public company fields")
        if company["cik"] in ciks:
            raise ValueError("Duplicate demo company")
        ciks.add(company["cik"])
        company["retrieved_at"] = datetime.fromisoformat(company["retrieved_at"])
        if company["retrieved_at"].tzinfo is None:
            raise ValueError("Snapshot retrieval needs a timezone")
        for field in ("start_date", "as_of"):
            company[field] = date.fromisoformat(company[field])
    identities = set()
    for observation in financials["observations"]:
        if set(observation) != set(OBSERVATION_FIELDS) or observation["cik"] not in ciks or observation["unit"] != "USD":
            raise ValueError("Invalid public observation fields")
        for field in ("start_date", "end_date", "filed"):
            if observation[field] is not None:
                observation[field] = date.fromisoformat(observation[field])
        identity = tuple(observation[k] for k in ("cik", "metric", "start_date", "end_date", "period_kind", "unit"))
        if identity in identities or observation["end_date"] is None:
            raise ValueError("Duplicate or undated demo observation")
        identities.add(identity)
        if observation["status"] == "selected":
            if not isinstance(observation["value"], str):
                raise ValueError("Selected amounts must be exact decimal strings")
            observation["value"] = Decimal(observation["value"])
            if not observation["value"].is_finite() or not observation["filed"]:
                raise ValueError("Invalid selected value")
            public_url(observation["source_url"])
        elif observation["status"] in {"ambiguous", "unsupported"} and observation["value"] is None:
            pass
        else:
            raise ValueError("Invalid observation status or value")
    for support in financials["annual_support"]:
        if set(support) != {"cik", "start_date", "end_date"} or support["cik"] not in ciks:
            raise ValueError("Invalid annual support")
        for field in ("start_date", "end_date"):
            support[field] = date.fromisoformat(support[field])
    for summary in data["summaries"]:
        if set(summary) != set(SUMMARY_FIELDS) or type(summary["source_word_count"]) is not int:
            raise ValueError("Invalid public summary fields")
        if summary["source_word_count"] < 0 or not all(isinstance(summary[k], str) for k in SUMMARY_FIELDS if k != "source_word_count"):
            raise ValueError("Invalid summary values")
        date.fromisoformat(summary["filing_date"])
        public_url(summary["filing_url"])
    financials["demo_exported_at"] = data["exported_at"]
    return data


def load_snapshot(path=DEFAULT_SNAPSHOT):
    path = Path(path)
    if path.stat().st_size > 8_000_000:
        raise ValueError("Demo snapshot exceeds the bounded public export size")
    return decode_snapshot(json.loads(path.read_text(encoding="utf-8")))
