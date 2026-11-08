"""Offline regression tests: real parsing, isolated files, mocked SEC transport."""
import contextlib
import io
import json
import os
import shutil
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

import main
import process_filings
import summarize_filings
from src import sec_http
from src.filing_downloader import download_filing_html
from src.sec_client import build_filing_url, get_recent_filings
from src.storage import save_filings_to_json


HEADERS = {"User-Agent": "Market Pulse contact@project.test"}
COMPANY = {"ticker": "TEST", "cik": "0000000001"}
ACCESSION = "0000000001-26-000001"
HTML = """<html><body><script>SECRET_SCRIPT</script><div hidden>SECRET_HIDDEN</div>
<div style="display:none">SECRET_STYLE</div><ix:hidden>SECRET_XBRL</ix:hidden>
<p>Item 2.02 Results of Operations and Financial Condition</p>
<p>The company reported revenue growth of 20% during the quarter as customer demand increased.</p>
<p>Item 9.01 Financial Statements and Exhibits</p></body></html>"""


def filing(accession=ACCESSION):
    return dict(company="Test", ticker="TEST", cik=COMPANY["cik"], form="8-K",
                filing_date="2026-10-30", accession_number=accession, document="report.htm",
                filing_url=build_filing_url(COMPANY["cik"], accession, "report.htm"))


def response(status=200, text=HTML, headers=None, payload=None):
    result = requests.Response()
    result.status_code = status
    result._content = text.encode()
    result.encoding = "utf-8"
    result.url = "https://www.sec.gov/example.htm"
    result.headers.update(headers or {"Content-Type": "text/html"})
    if payload is not None:
        result._content = json.dumps(payload).encode()
    return result


def submissions():
    return {"filings": {"recent": {"form": ["8-K"], "filingDate": ["2026-10-30"],
            "accessionNumber": [ACCESSION], "primaryDocument": ["report.htm"]}}}


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch("src.sec_http.time.sleep").start()
        self.addCleanup(patch.stopall)

    def test_403_is_actionable_and_not_retried(self):
        with patch("src.sec_http.requests.get", return_value=response(403)) as get:
            with self.assertRaisesRegex(sec_http.SecAccessError, "403"):
                download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 1)

    def test_rate_limit_respects_retry_after(self):
        with patch("src.sec_http.requests.get", side_effect=[
            response(429, headers={"Retry-After": "7"}), response()
        ]) as get:
            self.assertEqual(download_filing_html("https://www.sec.gov/example.htm", HEADERS), HTML)
        self.assertEqual(get.call_count, 2)
        self.sleep.assert_any_call(7.0)

    def test_long_retry_after_stops_instead_of_retrying_early(self):
        with patch("src.sec_http.requests.get", return_value=response(429, headers={"Retry-After": "120"})) as get:
            with self.assertRaisesRegex(requests.HTTPError, "rerun later"):
                download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 1)

    def test_temporary_server_failure_recovers(self):
        with patch("src.sec_http.requests.get", side_effect=[response(503), response()]) as get:
            download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 2)

    def test_persistent_rate_limit_stops_further_batch_requests(self):
        with patch("src.sec_http.requests.get", return_value=response(429)) as get:
            with self.assertRaises(sec_http.SecAccessError):
                download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 3)

    def test_connection_timeout_recovers(self):
        with patch("src.sec_http.requests.get", side_effect=[requests.Timeout("timeout"), response()]) as get:
            download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 2)

    def test_retry_budget_is_bounded(self):
        with patch("src.sec_http.requests.get", return_value=response(503)) as get:
            with self.assertRaises(requests.HTTPError):
                download_filing_html("https://www.sec.gov/example.htm", HEADERS)
        self.assertEqual(get.call_count, 3)

    def test_404_and_redirect_do_not_retry(self):
        for status in (404, 302):
            with self.subTest(status=status), patch("src.sec_http.requests.get", return_value=response(status)) as get:
                with self.assertRaises(requests.HTTPError):
                    download_filing_html("https://www.sec.gov/example.htm", HEADERS)
                self.assertEqual(get.call_count, 1)

    def test_rejects_bad_header_without_request(self):
        with patch("src.sec_http.requests.get") as get:
            with self.assertRaises(ValueError):
                download_filing_html("https://www.sec.gov/example.htm", {"User-Agent": "Unidentified"})
        get.assert_not_called()

    def test_rejects_invalid_content_and_soft_block_pages(self):
        cases = [("", {}), ("Not HTML", {}),
                 ("<html>Your Request Originates from an Undeclared Automated Tool</html>", {}),
                 (HTML, {"Content-Type": "application/pdf"})]
        for body, headers in cases:
            with self.subTest(body=body), patch("src.sec_http.requests.get", return_value=response(text=body, headers=headers)):
                with self.assertRaises((ValueError, sec_http.SecAccessError)):
                    download_filing_html("https://www.sec.gov/example.htm", HEADERS)

    def test_rejects_non_sec_destination(self):
        with patch("src.sec_http.requests.get") as get:
            with self.assertRaises(ValueError):
                download_filing_html("https://example.test/report.htm", HEADERS)
        get.assert_not_called()


class MetadataTests(unittest.TestCase):
    def test_valid_metadata_and_url(self):
        with patch("src.sec_client.get_sec_response", return_value=response(payload=submissions())):
            records = get_recent_filings("Test", COMPANY, HEADERS, {"8-K"})
        self.assertEqual(records, [filing()])

    def test_mismatched_arrays_are_not_silently_truncated(self):
        payload = submissions()
        payload["filings"]["recent"]["filingDate"] = []
        with patch("src.sec_client.get_sec_response", return_value=response(payload=payload)):
            with self.assertRaisesRegex(ValueError, "matching lengths"):
                get_recent_filings("Test", COMPANY, HEADERS, {"8-K"})

    def test_non_json_response_fails(self):
        with patch("src.sec_client.get_sec_response", return_value=response(text="<html>block</html>")):
            with self.assertRaises(ValueError):
                get_recent_filings("Test", COMPANY, HEADERS, {"8-K"})

    def test_unsafe_document_cannot_become_a_url(self):
        for name in ("../report.htm", "report/other.htm", "report\\other.htm"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_filing_url(COMPANY["cik"], ACCESSION, name)

    def test_duplicate_metadata_is_deduplicated(self):
        payload = submissions()
        for values in payload["filings"]["recent"].values():
            values.extend(values[:])
        with patch("src.sec_client.get_sec_response", return_value=response(payload=payload)):
            self.assertEqual(len(get_recent_filings("Test", COMPANY, HEADERS, {"8-K"})), 1)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.original = Path.cwd()
        self.temporary = self.original / "data" / ".test-runs" / uuid.uuid4().hex
        self.temporary.mkdir(parents=True)
        os.chdir(self.temporary)
        self.addCleanup(self.cleanup)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def cleanup(self):
        os.chdir(self.original)
        self.temporary.relative_to(self.original / "data" / ".test-runs")
        shutil.rmtree(self.temporary)

    def read(self, name):
        return json.loads(Path(name).read_text(encoding="utf-8"))

    def seed(self):
        save_filings_to_json([filing()])

    def test_complete_offline_pipeline_with_real_parser(self):
        with patch.object(main, "WATCHLIST", {"Test": COMPANY}), patch.object(main, "get_recent_filings", return_value=[filing()]):
            self.assertEqual(main.main(), 0)
        with patch.object(process_filings, "download_filing_html", return_value=HTML):
            self.assertEqual(process_filings.main(), 0)
        self.assertEqual(summarize_filings.main(), 0)
        text = next(Path("data/clean_text").glob("*.txt")).read_text()
        self.assertNotIn("SECRET", text)
        summary = self.read("data/summaries.json")[0]
        self.assertEqual(summary["filing_url"], filing()["filing_url"])
        self.assertEqual(summary["event_type"], "earnings/results")
        for stage in ("metadata", "processing", "summaries"):
            self.assertTrue(self.read(f"data/{stage}_status.json")["output_updated"])

    def test_failed_metadata_preserves_existing_bytes(self):
        self.seed()
        before = Path("data/filings.json").read_bytes()
        with patch.object(main, "get_recent_filings", side_effect=requests.Timeout("timeout")):
            self.assertEqual(main.main(), 1)
        self.assertEqual(Path("data/filings.json").read_bytes(), before)
        self.assertEqual(self.read("data/metadata_status.json")["failed"], len(main.WATCHLIST))

    def test_partial_metadata_does_not_publish_mixed_snapshot(self):
        self.seed()
        before = Path("data/filings.json").read_bytes()
        with patch.object(main, "WATCHLIST", {"One": COMPANY, "Two": COMPANY}), patch.object(
            main, "get_recent_filings", side_effect=[[filing()], ValueError("Invalid response")]
        ):
            self.assertEqual(main.main(), 1)
        self.assertEqual(Path("data/filings.json").read_bytes(), before)
        self.assertEqual(self.read("data/metadata_status.json")["status"], "partial")

    def test_access_denial_stops_remaining_network_requests(self):
        with patch.object(main, "get_recent_filings", side_effect=sec_http.SecAccessError("403")) as get:
            self.assertEqual(main.main(), 1)
        self.assertEqual(get.call_count, 1)

    def test_failed_processing_preserves_checkpoint_and_reports_filing(self):
        self.seed()
        save_filings_to_json([{"previous": True}], "data/processed_filings.json")
        before = Path("data/processed_filings.json").read_bytes()
        with patch.object(process_filings, "download_filing_html", side_effect=sec_http.SecAccessError("403")):
            self.assertEqual(process_filings.main(), 1)
        self.assertEqual(Path("data/processed_filings.json").read_bytes(), before)
        item = self.read("data/processing_status.json")["items"][0]
        self.assertEqual(item["accession_number"], ACCESSION)
        self.assertEqual(item["record"]["processing_status"], "failed")
        self.assertFalse(Path(f"data/raw_html/{ACCESSION}.html").exists())

    def test_invalid_cached_block_page_is_refetched(self):
        self.seed()
        cached = Path(f"data/raw_html/{ACCESSION}.html")
        cached.parent.mkdir(parents=True)
        cached.write_text("<html>Request Rate Threshold Exceeded</html>")
        with patch.object(process_filings, "download_filing_html", return_value=HTML) as get:
            self.assertEqual(process_filings.main(), 0)
        get.assert_called_once()
        self.assertEqual(cached.read_text(), HTML)

    def test_valid_cache_does_not_need_network(self):
        self.seed()
        cached = Path(f"data/raw_html/{ACCESSION}.html")
        cached.parent.mkdir(parents=True)
        cached.write_text(HTML)
        with patch.object(process_filings, "download_filing_html") as get:
            self.assertEqual(process_filings.main(), 0)
        get.assert_not_called()

    def test_partial_processing_preserves_complete_checkpoint(self):
        save_filings_to_json([filing(), filing("0000000001-26-000002")])
        save_filings_to_json([{"previous": True}], "data/processed_filings.json")
        with patch.object(process_filings, "download_filing_html", side_effect=[HTML, requests.Timeout("timeout")]):
            self.assertEqual(process_filings.main(), 1)
        self.assertEqual(self.read("data/processed_filings.json"), [{"previous": True}])
        report = self.read("data/processing_status.json")
        self.assertEqual((report["status"], report["records"], report["failed"]), ("partial", 1, 1))

    def test_access_denial_still_allows_valid_cached_filings(self):
        second = "0000000001-26-000002"
        save_filings_to_json([filing(), filing(second)])
        cached = Path(f"data/raw_html/{second}.html")
        cached.parent.mkdir(parents=True)
        cached.write_text(HTML)
        with patch.object(process_filings, "download_filing_html", side_effect=sec_http.SecAccessError("403")) as get:
            self.assertEqual(process_filings.main(), 1)
        get.assert_called_once()
        self.assertEqual(self.read("data/processing_status.json")["records"], 1)

    def test_empty_processed_input_cannot_erase_summaries(self):
        save_filings_to_json([], "data/processed_filings.json")
        save_filings_to_json([{"previous": True}], "data/summaries.json")
        self.assertEqual(summarize_filings.main(), 1)
        self.assertEqual(self.read("data/summaries.json"), [{"previous": True}])

    def test_dashboard_displays_failures_and_empty_state(self):
        from streamlit.testing.v1 import AppTest

        save_filings_to_json([], "data/summaries.json")
        save_filings_to_json({"status": "failed", "output_updated": False, "items": [
            {"status": "failed", "company": "Test", "accession_number": ACCESSION, "error": "HTTP 403"}
        ]}, "data/processing_status.json")
        app = AppTest.from_file(str(self.original / "dashboard.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.warning), 2)
        self.assertTrue(any("older run" in warning.value for warning in app.warning))
        self.assertEqual(len(app.dataframe), 1)

    def test_dashboard_filters_successful_pipeline_results(self):
        from streamlit.testing.v1 import AppTest

        self.seed()
        with patch.object(process_filings, "download_filing_html", return_value=HTML):
            self.assertEqual(process_filings.main(), 0)
        self.assertEqual(summarize_filings.main(), 0)
        app = AppTest.from_file(str(self.original / "dashboard.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        app.sidebar.selectbox[0].select("Test").run()
        app.sidebar.selectbox[1].select("8-K").run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["1", "1", "1"])

    def test_dashboard_handles_corrupt_json(self):
        from streamlit.testing.v1 import AppTest

        Path("data").mkdir()
        Path("data/summaries.json").write_text("{broken")
        app = AppTest.from_file(str(self.original / "dashboard.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.error), 1)

    def test_dashboard_warns_when_downstream_is_older(self):
        from streamlit.testing.v1 import AppTest

        save_filings_to_json([], "data/summaries.json")
        save_filings_to_json({"status": "success", "output_updated": True,
                             "finished_at": "2026-11-08T10:00:00+00:00", "items": []},
                            "data/metadata_status.json")
        app = AppTest.from_file(str(self.original / "dashboard.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("newer results" in warning.value for warning in app.warning))

    def test_failed_summaries_preserve_existing_bytes(self):
        save_filings_to_json([dict(filing(), processing_status="failed", processing_error="403")], "data/processed_filings.json")
        save_filings_to_json([{"previous": True}], "data/summaries.json")
        before = Path("data/summaries.json").read_bytes()
        self.assertEqual(summarize_filings.main(), 1)
        self.assertEqual(Path("data/summaries.json").read_bytes(), before)
        self.assertEqual(self.read("data/summaries_status.json")["failed"], 1)

    def test_missing_text_preserves_summaries(self):
        save_filings_to_json([dict(filing(), processing_status="successful", text_path="missing.txt")], "data/processed_filings.json")
        save_filings_to_json([{"previous": True}], "data/summaries.json")
        self.assertEqual(summarize_filings.main(), 1)
        self.assertEqual(self.read("data/summaries.json"), [{"previous": True}])

    def test_empty_metadata_is_reported_and_preserved(self):
        self.seed()
        with patch.object(main, "get_recent_filings", return_value=[]):
            self.assertEqual(main.main(), 1)
        self.assertEqual(self.read("data/filings.json"), [filing()])
        self.assertEqual(self.read("data/metadata_status.json")["status"], "empty")

    def test_invalid_input_records_do_not_publish(self):
        Path("data").mkdir()
        Path("data/filings.json").write_text('{}')
        self.assertEqual(process_filings.main(), 1)
        self.assertFalse(Path("data/processed_filings.json").exists())

    def test_atomic_replace_failure_keeps_previous_file_and_cleans_temp(self):
        self.seed()
        before = Path("data/filings.json").read_bytes()
        with patch("src.storage.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                save_filings_to_json([])
        self.assertEqual(Path("data/filings.json").read_bytes(), before)
        self.assertFalse(list(Path("data").glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
