"""Conservative normalisation of SEC entity-wide US-GAAP company facts."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from src.sec_http import get_sec_response
from src.storage import atomic_write_bytes, save_filings_to_json

SCHEMA_VERSION = 1
METRICS = {
    "revenue": ("duration", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")),
    "net_income": ("duration", ("NetIncomeLoss",)),
    "gross_profit": ("duration", ("GrossProfit",)),
    "operating_income": ("duration", ("OperatingIncomeLoss",)),
    "assets": ("instant", ("Assets",)),
    "liabilities": ("instant", ("Liabilities",)),
    "operating_cash_flow": ("duration", ("NetCashProvidedByUsedInOperatingActivities",)),
}
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Expected an ISO YYYY-MM-DD date")
    return date.fromisoformat(value)


def source_url(cik):
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik) or int(cik) == 0:
        raise ValueError("CIK must be a nonzero ten-digit string")
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def decode_snapshot(content, cik):
    payload = json.loads(content, parse_float=Decimal)
    if (not isinstance(payload, dict) or type(payload.get("cik")) is not int
            or payload["cik"] != int(cik) or not isinstance(payload.get("facts"), dict)):
        raise ValueError("SEC companyfacts identity or facts object is invalid")
    if not isinstance(payload["facts"].get("us-gaap", {}), dict):
        raise ValueError("Invalid US-GAAP facts object")
    return payload


def get_snapshot(cik, headers, fetched_at, offline=False):
    """Keep exact response bytes under immutable content-addressed names."""
    url = source_url(cik)
    folder = Path("data/xbrl_snapshots") / cik
    pointer = folder / "latest.json"
    if offline:
        descriptor = json.loads(pointer.read_text(encoding="utf-8"))
        digest = descriptor["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid snapshot hash")
        if descriptor.get("source_url") != url or descriptor.get("cik") != cik:
            raise ValueError("Snapshot descriptor identity mismatch")
        content = (folder / f"{digest}.json").read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Snapshot checksum mismatch")
        payload = decode_snapshot(content, cik)
        return payload, descriptor
    response = get_sec_response(url, headers)
    content = response.content
    payload = decode_snapshot(content, cik)
    digest = hashlib.sha256(content).hexdigest()
    path = folder / f"{digest}.json"
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Immutable snapshot has been modified")
    else:
        atomic_write_bytes(path, content)
    descriptor = dict(cik=cik, source_url=url, sha256=digest,
                      snapshot_path=path.as_posix(), fetched_at=fetched_at)
    save_filings_to_json(descriptor, pointer)
    return payload, descriptor


def period_kind(start, end, expected):
    if expected == "instant":
        if start is not None:
            raise ValueError("An instant balance-sheet fact must not have a start date")
        return "instant", None
    if start is None:
        raise ValueError("A duration fact requires a start date")
    days = (end - start).days + 1
    if days <= 0:
        raise ValueError("Period ends before it starts")
    for label, low, high in (("quarter_duration", 70, 110), ("six_month_duration", 150, 210),
                             ("nine_month_duration", 240, 300), ("year_duration", 330, 400)):
        if low <= days <= high:
            return label, days
    return "other_duration", days


def normalise_company(payload, company, details, snapshot, start_date, as_of):
    since, cutoff = iso_date(start_date), iso_date(as_of)
    if since > cutoff:
        raise ValueError("start-date must be on or before as-of")
    cik = details["cik"]
    if type(payload.get("cik")) is not int or payload["cik"] != int(cik):
        raise ValueError("Company facts CIK does not match configuration")
    facts = payload["facts"].get("us-gaap", {})
    candidates, rejected, excluded = [], [], Counter()
    for metric, (expected, tags) in METRICS.items():
        for tag in tags:
            concept = facts.get(tag)
            if concept is None:
                continue
            if not isinstance(concept, dict) or not isinstance(concept.get("units"), dict):
                rejected.append(dict(metric=metric, tag=tag, error="Invalid concept units"))
                continue
            for unit, rows in concept["units"].items():
                if not isinstance(rows, list):
                    rejected.append(dict(metric=metric, tag=tag, error="Unit facts must be an array"))
                    continue
                if unit != "USD":
                    excluded["non_usd"] += len(rows)
                    continue
                for row in rows:
                    try:
                        if not isinstance(row, dict):
                            raise ValueError("Fact must be an object")
                        if row.get("form") not in FORMS:
                            excluded["unsupported_form"] += 1
                            continue
                        filed, end = iso_date(row["filed"]), iso_date(row["end"])
                        if filed > cutoff or end < since:
                            excluded["outside_window"] += 1
                            continue
                        if end > filed:
                            raise ValueError("Fact period ends after filing date")
                        start = iso_date(row["start"]) if "start" in row else None
                        kind, days = period_kind(start, end, expected)
                        accession = row["accn"]
                        if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                            raise ValueError("Invalid accession")
                        value = row["val"]
                        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
                            raise ValueError("Fact value must be a finite JSON number")
                        number = Decimal(value)
                        if not number.is_finite():
                            raise ValueError("Fact value must be finite")
                        amount = "0" if number == 0 else format(number, "f")
                        if "." in amount:
                            amount = amount.rstrip("0").rstrip(".")
                        # Filing FY/FP are provenance, not labels for comparative observations.
                        candidate = dict(metric=metric, taxonomy="us-gaap", tag=tag, unit=unit,
                            value=amount, start=start.isoformat() if start else None, end=end.isoformat(),
                            period_kind=kind, duration_days=days, filed=filed.isoformat(), form=row["form"],
                            accession_number=accession, filing_fy=row.get("fy"), filing_fp=row.get("fp"),
                            frame=row.get("frame"),
                            filing_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html")
                        candidates.append(candidate)
                    except (KeyError, ValueError, TypeError) as error:
                        rejected.append(dict(metric=metric, tag=tag, accession_number=row.get("accn") if isinstance(row, dict) else None,
                                             error=str(error)))
    # Collapse exact repeats, retain every distinct source candidate for audit.
    unique = {json.dumps(row, sort_keys=True): row for row in candidates}
    candidates = sorted(unique.values(), key=lambda r: (r["metric"], r["end"], r["start"] or "", r["filed"], r["tag"], r["accession_number"], r["value"]))
    groups = defaultdict(list)
    for candidate in candidates:
        groups[(candidate["metric"], candidate["start"], candidate["end"], candidate["unit"])].append(candidate)
    observations = []
    for (metric, start, end, unit), rows in sorted(groups.items(), key=lambda pair: tuple(v or "" for v in pair[0])):
        newest = max(row["filed"] for row in rows)
        latest = [row for row in rows if row["filed"] == newest]
        status = "selected"
        if rows[0]["period_kind"] == "other_duration":
            status = "unsupported_period"
        elif len({row["value"] for row in latest}) > 1:
            status = "ambiguous"
        tags = METRICS[metric][1]
        chosen = min(latest, key=lambda row: (tags.index(row["tag"]), row["accession_number"], json.dumps(row, sort_keys=True))) if status == "selected" else None
        observations.append(dict(metric=metric, start=start, end=end, unit=unit,
                                 period_kind=rows[0]["period_kind"], status=status, selected=chosen,
                                 candidate_count=len(rows)))
    coverage = {}
    for metric in METRICS:
        rows = [row for row in observations if row["metric"] == metric]
        selected = [row for row in rows if row["status"] == "selected"]
        coverage[metric] = dict(status="available" if selected else "missing", selected_periods=len(selected),
            ambiguous_periods=sum(row["status"] == "ambiguous" for row in rows),
            period_kinds=dict(Counter(row["period_kind"] for row in selected)))
    return dict(schema_version=SCHEMA_VERSION, company=company, ticker=details["ticker"], cik=cik,
        snapshot=snapshot, window=dict(start_date=start_date, as_of=as_of, period_filter="end_date"),
        policy="latest_filed_by_exact_period_v1", period_policy="day_count_buckets_not_fiscal_labels_v1",
        candidates=candidates, observations=observations,
        coverage=coverage, rejected_facts=rejected, excluded_counts=dict(excluded))
