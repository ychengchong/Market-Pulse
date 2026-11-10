"""Transactional PostgreSQL persistence for verified XBRL datasets."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

# Optional supported fallback for managed Windows machines that disallow the
# wheel's native extension. No machine-wide PATH or security policy is changed.
_libpq_directory = os.environ.get("PG_LIBPQ_DIR")
_dll_handle = None
if _libpq_directory:
    _libpq_directory = str(Path(_libpq_directory).resolve(strict=True))
    os.environ["PATH"] = _libpq_directory + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("PSYCOPG_IMPL", "python")
    if os.name == "nt":
        _dll_handle = os.add_dll_directory(_libpq_directory)

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from src.xbrl import decode_snapshot, normalise_company, source_url

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = "market_pulse"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _configure(conn, schema):
    if not conn.autocommit:
        raise ValueError("Database functions require a dedicated autocommit connection")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("Invalid schema name")
    conn.execute(sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema)))


def _migrations():
    return [(path.name, path.read_text(encoding="utf-8")) for path in sorted((ROOT / "migrations").glob("[0-9]*.sql"))]


def _check_versions(conn):
    installed = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
    expected = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in _migrations()}
    if any(name not in expected or expected[name] != checksum for name, checksum in installed.items()):
        raise ValueError("Unknown or modified applied migration; restore the original migration files")
    return installed, expected


def migrate(conn, schema=DEFAULT_SCHEMA):
    _configure(conn, schema)
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute("SET LOCAL statement_timeout = '60s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (schema + ":migrations",))
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT clock_timestamp())")
        installed, expected = _check_versions(conn)
        for name, text in _migrations():
            if name not in installed:
                conn.execute(text, prepare=False)
                conn.execute("INSERT INTO schema_migrations(version, checksum) VALUES (%s,%s)", (name, expected[name]))
    return len(expected)


def validate_dataset(path):
    content = Path(path).read_bytes()
    records = json.loads(content)
    if not isinstance(records, list) or not records:
        raise ValueError("Input must be a nonempty array of company records")
    seen, window = set(), None
    for record in records:
        if not isinstance(record, dict) or record.get("schema_version") != 1:
            raise ValueError("Unsupported financial dataset schema")
        cik = record["cik"]
        expected_url = source_url(cik)
        if cik in seen:
            raise ValueError("Dataset contains duplicate companies")
        seen.add(cik)
        if window is not None and record["window"] != window:
            raise ValueError("All companies must use the same history window")
        window = record["window"]
        descriptor = record["snapshot"]
        checksum = descriptor["sha256"]
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Invalid snapshot checksum")
        snapshot_path = Path("data/xbrl_snapshots") / cik / f"{checksum}.json"
        if descriptor.get("snapshot_path") != snapshot_path.as_posix() or descriptor.get("source_url") != expected_url or descriptor.get("cik") != cik:
            raise ValueError("Snapshot provenance does not match its company")
        timestamp = datetime.fromisoformat(descriptor["fetched_at"])
        if timestamp.tzinfo is None:
            raise ValueError("Snapshot timestamp must include a timezone")
        raw = snapshot_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError("Snapshot checksum mismatch")
        expected = normalise_company(decode_snapshot(raw, cik), record["company"],
                    {"cik": cik, "ticker": record["ticker"]}, descriptor, window["start_date"], window["as_of"])
        if not isinstance(record.get("pipeline_identity"), dict):
            raise ValueError("Missing generating pipeline identity")
        expected["pipeline_identity"] = record["pipeline_identity"]
        if expected != record or record["rejected_facts"] or not any(r["status"] == "selected" for r in record["observations"]):
            raise ValueError("Dataset does not match validated source snapshots and selection policy")
    return hashlib.sha256(content).hexdigest(), records


def _insert_company(conn, dataset_id, record):
    cik, snapshot = record["cik"], record["snapshot"]
    conn.execute("INSERT INTO companies(cik,ticker,name) VALUES (%s,%s,%s) ON CONFLICT(cik) DO NOTHING", (cik, record["ticker"], record["company"]))
    conn.execute("INSERT INTO snapshots(snapshot_id,cik,source_url,local_path) VALUES (%s,%s,%s,%s) ON CONFLICT(snapshot_id) DO NOTHING",
                 (snapshot["sha256"], cik, snapshot["source_url"], snapshot["snapshot_path"]))
    conn.execute("INSERT INTO dataset_companies VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                 (dataset_id, cik, snapshot["sha256"], snapshot["fetched_at"], Jsonb(record["coverage"]), Jsonb(record["pipeline_identity"]), record["policy"], record["period_policy"]))
    for fact in record["candidates"]:
        filing = (cik, fact["accession_number"], fact["filed"], fact["form"], fact["filing_url"])
        conn.execute("INSERT INTO filings VALUES (%s,%s,%s,%s,%s) ON CONFLICT(cik,accession) DO NOTHING", filing)
        existing = conn.execute("SELECT filed,form,source_url FROM filings WHERE cik=%s AND accession=%s", filing[:2]).fetchone()
        if (existing[0].isoformat(), *existing[1:]) != filing[2:]:
            raise ValueError("Conflicting metadata for an existing filing")
        fact_id = digest(dict(cik=cik, **fact))
        conn.execute("""INSERT INTO financial_facts VALUES
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(fact_id) DO NOTHING""",
            (fact_id, cik, fact["accession_number"], fact["metric"], fact["taxonomy"], fact["tag"], fact["unit"], Decimal(fact["value"]),
             fact["start"], fact["end"], fact["period_kind"], fact["filing_fy"], fact["filing_fp"], fact["frame"]))
        conn.execute("INSERT INTO dataset_facts VALUES (%s,%s,%s)", (dataset_id, cik, fact_id))
    for observation in record["observations"]:
        key = {key: observation[key] for key in ("metric", "start", "end", "unit")}
        observation_id = digest(dict(cik=cik, **key))
        selected = digest(dict(cik=cik, **observation["selected"])) if observation["selected"] else None
        conn.execute("INSERT INTO observations VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (dataset_id, observation_id, cik, observation["metric"], observation["start"], observation["end"], observation["unit"],
             observation["period_kind"], observation["status"], selected, observation["candidate_count"]))


def import_dataset(conn, path, schema=DEFAULT_SCHEMA):
    _configure(conn, schema)
    installed, expected = _check_versions(conn)
    if installed != expected:
        raise ValueError("Run database migrations before importing")
    run_id = uuid.uuid4()
    conn.execute("INSERT INTO ingestion_runs(run_id,status) VALUES (%s,'running')", (run_id,))
    try:
        dataset_id, records = validate_dataset(path)
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("SET LOCAL statement_timeout = '60s'")
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (schema + ":import",))
            inserted = conn.execute("INSERT INTO datasets(dataset_id,source_name,start_date,as_of) VALUES (%s,%s,%s,%s) ON CONFLICT(dataset_id) DO NOTHING RETURNING dataset_id",
                        (dataset_id, Path(path).name, records[0]["window"]["start_date"], records[0]["window"]["as_of"])).fetchone()
            if inserted:
                for record in records:
                    _insert_company(conn, dataset_id, record)
            summary = dict(companies=len(records), candidates=sum(len(r["candidates"]) for r in records),
                           selected_observations=sum(o["status"] == "selected" for r in records for o in r["observations"]),
                           already_imported=not bool(inserted))
            conn.execute("UPDATE ingestion_runs SET status='success',finished_at=clock_timestamp(),dataset_id=%s,summary=%s WHERE run_id=%s",
                         (dataset_id, Jsonb(summary), run_id))
        return dict(run_id=str(run_id), dataset_id=dataset_id, **summary)
    except Exception as error:
        # Business writes roll back together. Store only the exception class,
        # never a connection string, password or untrusted database error text.
        conn.execute("UPDATE ingestion_runs SET status='failed',finished_at=clock_timestamp(),error_kind=%s WHERE run_id=%s", (type(error).__name__, run_id))
        raise


def database_status(conn, schema=DEFAULT_SCHEMA):
    _configure(conn, schema)
    return {table: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            for table in ("companies", "snapshots", "filings", "financial_facts", "datasets", "observations", "ingestion_runs", "current_financial_facts")}
