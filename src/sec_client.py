"""Validated SEC submissions metadata and filing identities."""
import re
from datetime import date

from src.sec_http import get_sec_response


def build_filing_url(cik, accession_number, primary_document):
    if not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik) or int(cik) == 0:
        raise ValueError("CIK must be a nonzero ten-digit string")
    if not isinstance(accession_number, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession_number):
        raise ValueError("Invalid SEC accession number")
    if (not isinstance(primary_document, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", primary_document) or ".." in primary_document):
        raise ValueError("Invalid primary document filename")
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_number.replace('-', '')}/{primary_document}")


def validate_filing(filing):
    for key in ("company", "ticker", "cik", "form", "filing_date", "accession_number", "document", "filing_url"):
        if not isinstance(filing.get(key), str) or not filing[key].strip():
            raise ValueError(f"Filing field {key} must be a nonempty string")
    if len(filing["filing_date"]) != 10:
        raise ValueError("Filing date must be YYYY-MM-DD")
    date.fromisoformat(filing["filing_date"])
    expected = build_filing_url(filing["cik"], filing["accession_number"], filing["document"])
    if filing["filing_url"] != expected:
        raise ValueError("Filing URL does not match its SEC identifiers")


def get_recent_filings(company_name, company_details, headers, wanted_forms, maximum_filings=5):
    if not isinstance(maximum_filings, int) or maximum_filings < 1:
        raise ValueError("maximum_filings must be a positive integer")
    cik = company_details["cik"]
    # Validate configuration before using it in a request URL.
    build_filing_url(cik, "0000000000-00-000001", "check.htm")
    response = get_sec_response(f"https://data.sec.gov/submissions/CIK{cik}.json", headers)
    payload = response.json()
    try:
        recent = payload["filings"]["recent"]
        columns = [recent[key] for key in ("form", "filingDate", "accessionNumber", "primaryDocument")]
    except (KeyError, TypeError) as error:
        raise ValueError("SEC submissions response is missing recent filing arrays") from error
    if any(not isinstance(column, list) for column in columns) or len({len(c) for c in columns}) != 1:
        raise ValueError("SEC recent filing arrays must have matching lengths")
    collected, seen = [], set()
    for form, filing_date, accession, document in zip(*columns):
        if not isinstance(form, str):
            raise ValueError("SEC form must be a string")
        if form not in wanted_forms:
            continue
        filing = dict(company=company_name, ticker=company_details["ticker"], cik=cik,
                      form=form, filing_date=filing_date, accession_number=accession,
                      document=document, filing_url=build_filing_url(cik, accession, document))
        validate_filing(filing)
        if accession in seen:
            continue
        seen.add(accession)
        collected.append(filing)
        if len(collected) == maximum_filings:
            break
    return collected
