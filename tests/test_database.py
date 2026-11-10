"""Verified-input unit tests and opt-in real PostgreSQL integration tests."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

from src import database
import psycopg
from psycopg import sql
from src.storage import save_filings_to_json
from src.xbrl import decode_snapshot, normalise_company, source_url

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / "tests/fixtures/companyfacts.json").read_bytes()
TEST_DSN = os.environ.get("MARKET_PULSE_TEST_DATABASE_URL")


class DatasetWorkspace(unittest.TestCase):
    def setUp(self):
        self.original = Path.cwd()
        self.folder = ROOT / "data/.test-runs" / uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        os.chdir(self.folder)
        self.addCleanup(self.cleanup_workspace)

    def cleanup_workspace(self):
        os.chdir(self.original)
        self.folder.relative_to(ROOT / "data/.test-runs")
        shutil.rmtree(self.folder)

    def record(self, cik="0000000001", as_of="2025-12-31", raw=None):
        raw = raw or RAW.replace(b'"cik": 1', f'"cik": {int(cik)}'.encode())
        checksum = hashlib.sha256(raw).hexdigest()
        path = Path("data/xbrl_snapshots") / cik / f"{checksum}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        snapshot = dict(cik=cik, source_url=source_url(cik), sha256=checksum,
                        snapshot_path=path.as_posix(), fetched_at="2026-11-09T00:00:00+00:00")
        record = normalise_company(decode_snapshot(raw, cik), "Synthetic", {"cik": cik, "ticker": "TEST"}, snapshot, "2024-01-01", as_of)
        record["pipeline_identity"] = {"fixture": "synthetic"}
        return record

    def dataset(self, records=None, name="facts.json"):
        path = Path(name)
        save_filings_to_json(records or [self.record()], path)
        return path


class DatasetValidationTests(DatasetWorkspace):
    def test_valid_dataset_reconstructs_from_raw_snapshot(self):
        path = self.dataset()
        checksum, records = database.validate_dataset(path)
        self.assertEqual(checksum, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(len(records), 1)

    def test_changed_financial_value_is_rejected(self):
        record = self.record()
        record["candidates"][0]["value"] = "999999"
        with self.assertRaisesRegex(ValueError, "does not match"):
            database.validate_dataset(self.dataset([record]))

    def test_modified_source_snapshot_is_rejected(self):
        record = self.record()
        Path(record["snapshot"]["snapshot_path"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum"):
            database.validate_dataset(self.dataset([record]))

    def test_snapshot_path_cannot_escape_data_directory(self):
        record = self.record()
        record["snapshot"]["snapshot_path"] = "../unrelated-file"
        with self.assertRaisesRegex(ValueError, "provenance"):
            database.validate_dataset(self.dataset([record]))

    def test_duplicate_company_is_rejected(self):
        record = self.record()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            database.validate_dataset(self.dataset([record, record]))

    def test_incompatible_schema_is_rejected(self):
        record = self.record()
        record["schema_version"] = 999
        with self.assertRaisesRegex(ValueError, "schema"):
            database.validate_dataset(self.dataset([record]))

    def test_changed_selection_is_rejected(self):
        record = self.record()
        record["observations"][0]["selected"] = None
        with self.assertRaisesRegex(ValueError, "does not match"):
            database.validate_dataset(self.dataset([record]))

    def test_mixed_windows_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "same history window"):
            database.validate_dataset(self.dataset([self.record(), self.record("0000000002", as_of="2025-11-30")]))


@unittest.skipUnless(TEST_DSN, "Set MARKET_PULSE_TEST_DATABASE_URL to run real PostgreSQL checks")
class PostgresTests(DatasetWorkspace):
    def setUp(self):
        super().setUp()
        self.conn = psycopg.connect(TEST_DSN, autocommit=True, connect_timeout=10)
        self.schema = "mp_test_" + uuid.uuid4().hex
        self.addCleanup(self.cleanup_database)
        database.migrate(self.conn, self.schema)

    def cleanup_database(self):
        if not self.schema.startswith("mp_test_") or len(self.schema) != 40:
            raise AssertionError("Unsafe integration-test schema")
        self.conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.close()

    def test_migrations_are_repeatable(self):
        self.assertEqual(database.migrate(self.conn, self.schema), 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1)

    def test_migration_checksum_change_is_refused(self):
        migrations = database._migrations()
        with patch("src.database._migrations", return_value=[(migrations[0][0], migrations[0][1] + "\n-- changed")]):
            with self.assertRaisesRegex(ValueError, "modified"):
                database.migrate(self.conn, self.schema)
        self.assertEqual(database.migrate(self.conn, self.schema), 1)

    def test_repeat_import_does_not_duplicate_business_records(self):
        path = self.dataset()
        first = database.import_dataset(self.conn, path, self.schema)
        before = database.database_status(self.conn, self.schema)
        second = database.import_dataset(self.conn, path, self.schema)
        after = database.database_status(self.conn, self.schema)
        self.assertFalse(first["already_imported"])
        self.assertTrue(second["already_imported"])
        for name in before:
            if name != "ingestion_runs":
                self.assertEqual(before[name], after[name], name)
        self.assertEqual(after["ingestion_runs"], 2)

    def test_decimal_values_are_exact_in_postgres(self):
        raw = RAW.replace(b'"val": -20', b'"val": -20.1234567890123456789')
        database.import_dataset(self.conn, self.dataset([self.record(raw=raw)]), self.schema)
        value = self.conn.execute("SELECT value FROM current_financial_facts WHERE metric='net_income'").fetchone()[0]
        self.assertEqual(value, Decimal("-20.1234567890123456789"))

    def test_full_batch_rolls_back_when_second_company_fails(self):
        database.import_dataset(self.conn, self.dataset(), self.schema)
        before = database.database_status(self.conn, self.schema)
        path = self.dataset([self.record(), self.record("0000000002")], "two.json")
        original = database._insert_company
        def fail_second(conn, dataset_id, record):
            if record["cik"] == "0000000002":
                raise RuntimeError("synthetic mid-batch failure")
            return original(conn, dataset_id, record)
        with patch("src.database._insert_company", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                database.import_dataset(self.conn, path, self.schema)
        after = database.database_status(self.conn, self.schema)
        for name in before:
            if name != "ingestion_runs":
                self.assertEqual(before[name], after[name], name)
        self.assertEqual(self.conn.execute("SELECT error_kind FROM ingestion_runs WHERE status='failed'").fetchone()[0], "RuntimeError")

    def test_old_as_of_import_does_not_replace_newer_current_data(self):
        database.import_dataset(self.conn, self.dataset(), self.schema)
        database.import_dataset(self.conn, self.dataset([self.record(as_of="2025-11-30")], "old.json"), self.schema)
        self.assertEqual(self.conn.execute("SELECT DISTINCT as_of::text FROM current_financial_facts").fetchall(), [("2025-12-31",)])

    def test_ambiguous_value_is_stored_but_not_exposed_as_selected(self):
        payload = json.loads(RAW)
        rows = payload["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
        rows.append(dict(rows[-1], val=999, accn="0000000001-25-000002"))
        record = self.record(raw=json.dumps(payload).encode())
        database.import_dataset(self.conn, self.dataset([record]), self.schema)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM observations WHERE status='ambiguous'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM current_financial_facts WHERE metric='revenue' AND start_date='2025-04-01'").fetchone()[0], 0)

    def test_missing_metric_is_retained_as_missing_coverage(self):
        payload = json.loads(RAW)
        del payload["facts"]["us-gaap"]["Liabilities"]
        database.import_dataset(self.conn, self.dataset([self.record(raw=json.dumps(payload).encode())]), self.schema)
        self.assertEqual(self.conn.execute("SELECT coverage->'liabilities'->>'status' FROM dataset_companies").fetchone()[0], "missing")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM current_financial_facts WHERE metric='liabilities'").fetchone()[0], 0)

    def test_source_links_and_history_remain_queryable(self):
        record = self.record()
        database.import_dataset(self.conn, self.dataset([record]), self.schema)
        row = self.conn.execute("SELECT source_url,snapshot_id,accession FROM current_financial_facts LIMIT 1").fetchone()
        self.assertTrue(row[0].startswith("https://www.sec.gov/Archives/"))
        self.assertEqual(row[1], record["snapshot"]["sha256"])
        self.assertTrue(row[2])

    def test_company_text_is_parameterised(self):
        record = self.record()
        record["company"] = "Example'); DROP TABLE companies; --"
        database.import_dataset(self.conn, self.dataset([record]), self.schema)
        self.assertEqual(self.conn.execute("SELECT name FROM companies").fetchone()[0], record["company"])

    def test_validation_failure_is_audited_without_business_writes(self):
        record = self.record()
        record["candidates"][0]["value"] = "999"
        with self.assertRaises(ValueError):
            database.import_dataset(self.conn, self.dataset([record]), self.schema)
        counts = database.database_status(self.conn, self.schema)
        self.assertEqual((counts["companies"], counts["financial_facts"], counts["ingestion_runs"]), (0,0,1))
        self.assertEqual(self.conn.execute("SELECT status FROM ingestion_runs").fetchone()[0], "failed")

    def test_same_day_older_snapshot_does_not_replace_newer_retrieval(self):
        newer = self.record()
        newer["snapshot"]["fetched_at"] = "2026-11-09T12:00:00+00:00"
        database.import_dataset(self.conn, self.dataset([newer], "new.json"), self.schema)
        old = self.record()
        database.import_dataset(self.conn, self.dataset([old], "old.json"), self.schema)
        actual = self.conn.execute("SELECT dc.retrieved_at FROM latest_company_datasets l JOIN dataset_companies dc ON (l.cik,l.dataset_id)=(dc.cik,dc.dataset_id)").fetchone()[0]
        self.assertEqual(actual.utctimetuple().tm_hour, 12)

    def test_conflicting_existing_filing_metadata_rolls_back(self):
        database.import_dataset(self.conn, self.dataset(), self.schema)
        before = database.database_status(self.conn, self.schema)
        payload = json.loads(RAW)
        for concept in payload["facts"]["us-gaap"].values():
            for row in concept["units"]["USD"]:
                if row["accn"] == "0000000001-25-000001":
                    row["filed"] = "2025-08-02"
        path = self.dataset([self.record(raw=json.dumps(payload).encode())], "conflict.json")
        with self.assertRaisesRegex(ValueError, "Conflicting metadata"):
            database.import_dataset(self.conn, path, self.schema)
        self.assertEqual(database.database_status(self.conn, self.schema)["financial_facts"], before["financial_facts"])

    def test_concurrent_repeated_imports_do_not_duplicate_rows(self):
        path = self.dataset().resolve()
        def load():
            with psycopg.connect(TEST_DSN, autocommit=True) as conn:
                return database.import_dataset(conn, path, self.schema)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: load(), range(2)))
        self.assertEqual(sum(not r["already_imported"] for r in results), 1)
        self.assertEqual(database.database_status(self.conn, self.schema)["datasets"], 1)


if __name__ == "__main__":
    unittest.main()
