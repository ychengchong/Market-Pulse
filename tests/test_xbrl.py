"""Synthetic financial-fact contracts and isolated ingestion regressions."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

import requests

import ingest_financials
from src.sec_http import SecAccessError
from src.storage import save_filings_to_json
from src.xbrl import decode_snapshot, get_snapshot, normalise_company, period_kind
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / "tests/fixtures/companyfacts.json").read_bytes()
DETAILS = {"ticker": "TEST", "cik": "0000000001"}
TAG = "RevenueFromContractWithCustomerExcludingAssessedTax"


def normalise(payload=None, as_of="2025-12-31"):
    if payload is None:
        payload = decode_snapshot(RAW, DETAILS["cik"])
    return normalise_company(payload, "Synthetic", DETAILS, {"sha256": hashlib.sha256(RAW).hexdigest()}, "2024-01-01", as_of)


def rows(payload, tag=TAG):
    return payload["facts"]["us-gaap"][tag]["units"]["USD"]


class FactTests(unittest.TestCase):
    def setUp(self):
        self.payload = decode_snapshot(RAW, DETAILS["cik"])

    def test_periods_and_units_are_explicit(self):
        record = normalise(self.payload)
        kinds = {r["period_kind"] for r in record["observations"]}
        self.assertEqual(kinds, {"year_duration", "quarter_duration", "six_month_duration", "instant"})
        self.assertEqual(record["coverage"]["operating_cash_flow"]["period_kinds"], {"six_month_duration": 1})
        self.assertTrue(all(r["unit"] == "USD" for r in record["candidates"]))

    def test_ytd_and_standalone_quarter_with_same_end_are_separate(self):
        observations = [r for r in normalise()["observations"] if r["metric"] == "revenue" and r["end"] == "2025-06-30"]
        self.assertEqual(len(observations), 2)
        self.assertEqual({r["selected"]["value"] for r in observations}, {"230", "130"})

    def test_latest_amendment_is_selected_and_previous_value_retained(self):
        original = rows(self.payload)[-1]
        amended = dict(original, val=125, filed="2025-08-15", form="10-Q/A", accn="0000000001-25-000002")
        rows(self.payload).append(amended)
        record = normalise(self.payload)
        observation = next(r for r in record["observations"] if r["metric"] == "revenue" and r["start"] == "2025-04-01")
        self.assertEqual(observation["selected"]["value"], "125")
        self.assertEqual(observation["candidate_count"], 2)
        self.assertEqual(len([r for r in record["candidates"] if r["metric"] == "revenue"]), 5)

    def test_as_of_excludes_later_amendment(self):
        rows(self.payload).append(dict(rows(self.payload)[-1], val=125, filed="2025-08-15", form="10-Q/A"))
        record = normalise(self.payload, as_of="2025-08-01")
        self.assertNotIn("125", [r["value"] for r in record["candidates"]])

    def test_conflicting_same_day_values_are_ambiguous(self):
        rows(self.payload).append(dict(rows(self.payload)[-1], val=999, accn="0000000001-25-000002"))
        observation = next(r for r in normalise(self.payload)["observations"] if r["metric"] == "revenue" and r["start"] == "2025-04-01")
        self.assertEqual(observation["status"], "ambiguous")
        self.assertIsNone(observation["selected"])

    def test_alias_conflict_is_not_resolved_by_tag_priority(self):
        self.payload["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [dict(rows(self.payload)[-1], val=999)]}}
        observation = next(r for r in normalise(self.payload)["observations"] if r["metric"] == "revenue" and r["start"] == "2025-04-01")
        self.assertEqual(observation["status"], "ambiguous")

    def test_equal_alias_values_choose_declared_tag(self):
        self.payload["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [dict(rows(self.payload)[-1])]}}
        observation = next(r for r in normalise(self.payload)["observations"] if r["metric"] == "revenue" and r["start"] == "2025-04-01")
        self.assertEqual(observation["selected"]["tag"], TAG)

    def test_missing_metric_is_not_zero(self):
        del self.payload["facts"]["us-gaap"]["Liabilities"]
        record = normalise(self.payload)
        self.assertEqual(record["coverage"]["liabilities"]["status"], "missing")
        self.assertFalse(any(r["metric"] == "liabilities" for r in record["observations"]))

    def test_currency_is_not_converted_or_mixed(self):
        concept = self.payload["facts"]["us-gaap"]["Assets"]
        concept["units"]["EUR"] = concept["units"].pop("USD")
        record = normalise(self.payload)
        self.assertEqual(record["coverage"]["assets"]["status"], "missing")
        self.assertEqual(record["excluded_counts"]["non_usd"], 1)

    def test_negative_income_is_valid(self):
        self.assertIn("-20", [r["value"] for r in normalise()["candidates"] if r["metric"] == "net_income"])

    def test_invalid_numbers_are_reported(self):
        for bad in (True, "123", float("nan")):
            with self.subTest(value=bad):
                payload = copy.deepcopy(self.payload)
                rows(payload)[-1]["val"] = bad
                self.assertEqual(len(normalise(payload)["rejected_facts"]), 1)

    def test_decimal_precision_is_preserved(self):
        payload = decode_snapshot(RAW.replace(b'"val": -20', b'"val": -20.1234567890123456789'), DETAILS["cik"])
        self.assertIn("-20.1234567890123456789", [r["value"] for r in normalise(payload)["candidates"]])

    def test_invalid_dates_and_instant_duration_are_rejected(self):
        rows(self.payload, "Assets")[0]["start"] = "2025-01-01"
        rows(self.payload)[0]["end"] = "2024-02-30"
        self.assertEqual(len(normalise(self.payload)["rejected_facts"]), 2)

    def test_fiscal_53_week_year_is_annual(self):
        kind, days = period_kind(date(2024, 1, 1), date(2025, 1, 5), "duration")
        self.assertEqual((kind, days), ("year_duration", 371))

    def test_unusual_duration_is_not_mislabelled_quarter(self):
        rows(self.payload)[-1]["start"] = "2025-06-01"
        observation = next(r for r in normalise(self.payload)["observations"] if r["metric"] == "revenue" and r["start"] == "2025-06-01")
        self.assertEqual(observation["status"], "unsupported_period")
        self.assertIsNone(observation["selected"])

    def test_filing_year_is_not_observation_year(self):
        record = normalise()
        annual = next(r for r in record["candidates"] if r["period_kind"] == "year_duration")
        self.assertEqual((annual["end"], annual["filing_fy"]), ("2024-12-31", 2025))

    def test_trailing_twelve_months_do_not_become_a_fiscal_year(self):
        row = rows(self.payload)[0]
        row.update(start="2024-07-01", end="2025-06-30", filed="2025-08-01", form="10-Q", fp="Q2")
        candidate = next(r for r in normalise(self.payload)["candidates"] if r["start"] == "2024-07-01")
        self.assertEqual(candidate["period_kind"], "year_duration")
        self.assertEqual(candidate["filing_fp"], "Q2")
        self.assertNotIn("fiscal_year", candidate)

    def test_reordering_input_facts_does_not_change_result(self):
        expected = normalise(self.payload)
        rows(self.payload).reverse()
        self.assertEqual(normalise(self.payload), expected)

    def test_exact_duplicates_are_removed_and_result_is_repeatable(self):
        expected = normalise(self.payload)
        rows(self.payload).extend(copy.deepcopy(rows(self.payload)))
        self.assertEqual(normalise(self.payload), expected)

    def test_company_identity_is_checked(self):
        with self.assertRaises(ValueError):
            decode_snapshot(RAW, "0000000002")

    def test_source_metadata_survives_selection(self):
        selected = normalise()["observations"][0]["selected"]
        for key in ("tag", "taxonomy", "accession_number", "filed", "form", "filing_url", "value"):
            self.assertIn(key, selected)


class SnapshotAndPipelineTests(unittest.TestCase):
    def setUp(self):
        self.original = Path.cwd()
        self.folder = ROOT / "data/.test-runs" / uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        os.chdir(self.folder)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        os.chdir(self.original)
        self.folder.relative_to(ROOT / "data/.test-runs")
        shutil.rmtree(self.folder)

    def download(self):
        response = requests.Response()
        response.status_code = 200
        response._content = RAW
        with patch("src.xbrl.get_sec_response", return_value=response):
            return get_snapshot(DETAILS["cik"], {}, "2026-11-09T00:00:00+00:00")

    def test_raw_bytes_are_immutable_and_offline_replay_matches(self):
        payload, descriptor = self.download()
        self.assertEqual(Path(descriptor["snapshot_path"]).read_bytes(), RAW)
        with patch("src.xbrl.get_sec_response") as network:
            replay, same = get_snapshot(DETAILS["cik"], {}, "unused", offline=True)
        network.assert_not_called()
        self.assertEqual((payload, descriptor), (replay, same))

    def test_corrupt_snapshot_is_rejected(self):
        _, descriptor = self.download()
        Path(descriptor["snapshot_path"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum"):
            get_snapshot(DETAILS["cik"], {}, "unused", offline=True)

    def test_failed_run_preserves_previous_dataset(self):
        save_filings_to_json([{"previous": True}], "data/financial_facts.json")
        with patch.object(ingest_financials, "WATCHLIST", {"Synthetic": DETAILS}), patch.object(
            ingest_financials, "get_snapshot", side_effect=ValueError("Malformed JSON")
        ):
            self.assertEqual(ingest_financials.main(["--as-of", "2025-12-31"]), 1)
        self.assertEqual(json.loads(Path("data/financial_facts.json").read_text()), [{"previous": True}])

    def test_access_denial_stops_remaining_company_requests(self):
        with patch.object(ingest_financials, "WATCHLIST", {"One": DETAILS, "Two": DETAILS}), patch.object(
            ingest_financials, "get_snapshot", side_effect=SecAccessError("403")
        ) as network:
            self.assertEqual(ingest_financials.main(["--as-of", "2025-12-31"]), 1)
        self.assertEqual(network.call_count, 1)

    def test_offline_complete_run_publishes_same_records_twice(self):
        self.download()
        with patch.object(ingest_financials, "WATCHLIST", {"Synthetic": DETAILS}), patch("src.xbrl.get_sec_response") as network:
            self.assertEqual(ingest_financials.main(["--offline", "--as-of", "2025-12-31", "--start-date", "2024-01-01"]), 0)
            first = Path("data/financial_facts.json").read_bytes()
            self.assertEqual(ingest_financials.main(["--offline", "--as-of", "2025-12-31", "--start-date", "2024-01-01"]), 0)
            self.assertEqual(Path("data/financial_facts.json").read_bytes(), first)
        network.assert_not_called()

    def test_malformed_mapped_fact_prevents_publication(self):
        payload, descriptor = self.download()
        rows(payload)[-1]["val"] = "bad"
        with patch.object(ingest_financials, "WATCHLIST", {"Synthetic": DETAILS}), patch.object(
            ingest_financials, "get_snapshot", return_value=(payload, descriptor)
        ):
            self.assertEqual(ingest_financials.main(["--as-of", "2025-12-31"]), 1)
        self.assertFalse(Path("data/financial_facts.json").exists())
        report = json.loads(Path("data/financials_status.json").read_text())
        self.assertEqual(len(report["items"][0]["rejected_facts"]), 1)


if __name__ == "__main__":
    unittest.main()
