"""Frozen demo integrity, precision, offline rendering and publication boundaries."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import export_demo
from src.demo import create_snapshot, decode_snapshot, checksum
from src.analytics import build_periods
from test_database import DatasetWorkspace, ROOT
from test_analytics import dataset, row


class DemoTests(DatasetWorkspace):
    def snapshot(self):
        data=dataset(row("revenue","125.1234567890123456789"),row("net_income","25"))
        data["companies"][0].update(name="Invented",dataset_id="dataset",snapshot_id="snapshot",
            retrieved_at=datetime(2026,1,1,tzinfo=timezone.utc),start_date=date(2024,1,1),as_of=date(2025,12,31),
            local_path="private-path",password="private-password")
        for observation in data["observations"]:
            observation.update(tag="Synthetic",accession="0000000001-25-000001",filed=date(2025,8,1),form="10-Q",unit="USD",source_url="https://www.sec.gov/Archives/example.htm")
        summary=dict(company="Invented",ticker="TEST",form="8-K",filing_date="2025-08-01",event_type="other event",
            summary="Synthetic disclosure",summary_method="synthetic",source_word_count=2,
            filing_url="https://www.sec.gov/Archives/example.htm",text_path="private-path")
        return create_snapshot(data,[summary],"2026-01-02T00:00:00+00:00")

    def test_roundtrip_preserves_decimal_inputs_and_margin(self):
        envelope=self.snapshot(); data=decode_snapshot(envelope)
        p=build_periods(data["financials"],"1","Quarterly")[0]
        self.assertEqual(p["revenue"],Decimal("125.1234567890123456789"))
        self.assertEqual(p["net_margin"],Decimal(25)/Decimal("125.1234567890123456789")*100)

    def test_export_allowlist_removes_private_extra_fields(self):
        text=json.dumps(self.snapshot())
        for private in ("private-path","private-password","local_path","text_path","password"):
            self.assertNotIn(private,text)

    def test_tampering_or_schema_change_is_rejected(self):
        envelope=self.snapshot();envelope["payload"]["summaries"][0]["summary"]="changed"
        with self.assertRaises(ValueError):decode_snapshot(envelope)
        envelope=self.snapshot();envelope["schema_version"]=2
        with self.assertRaises(ValueError):decode_snapshot(envelope)

    def test_missing_values_remain_missing(self):
        envelope=self.snapshot()
        row=envelope["payload"]["financials"]["observations"][0]
        row.update(value=None,status="ambiguous",source_url=None,filed=None)
        envelope["sha256"]=checksum(envelope["payload"])
        p=build_periods(decode_snapshot(envelope)["financials"],"1","Quarterly")[0]
        self.assertIsNone(p["revenue"]);self.assertIsNone(p["net_margin"])

    def test_non_sec_link_and_nonfinite_value_are_rejected(self):
        for field,value in [("source_url","https://example.com/private"),("value","NaN")]:
            envelope=self.snapshot();envelope["payload"]["financials"]["observations"][0][field]=value
            envelope["sha256"]=checksum(envelope["payload"])
            with self.assertRaises(ValueError):decode_snapshot(envelope)

    def test_failed_export_preserves_previous_snapshot(self):
        output=Path("snapshot.json");output.write_text("previous")
        with patch.object(export_demo,"connection_string",return_value="private"), \
             patch.object(export_demo,"load_financials",side_effect=ValueError("private")):
            self.assertEqual(export_demo.main(["--output",str(output)]),1)
        self.assertEqual(output.read_text(),"previous")

    def test_demo_tabs_work_without_database_or_generated_local_data(self):
        snapshot=decode_snapshot(self.snapshot())
        Path(".streamlit").mkdir();Path(".streamlit/secrets.toml").write_text("malformed secrets deliberately")
        with patch("src.demo.load_snapshot",return_value=snapshot), \
             patch("src.financial_ui.connection_string",side_effect=AssertionError("demo read credentials")), \
             patch("src.analytics.load_financials",side_effect=AssertionError("demo contacted database")):
            app=AppTest.from_file(str(ROOT/"demo/dashboard.py"),default_timeout=30).run()
            self.assertFalse(app.exception);self.assertFalse(app.error)
            self.assertTrue(any("Snapshot demo" in n.value for n in app.markdown))
            self.assertEqual(len(app.sidebar.selectbox),0)
            app.segmented_control(key="financial_mode").set_value("Quarterly").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,"$0.00B")
            app.session_state["main_view"]="Company comparison";app.run()
            self.assertFalse(app.exception)
            app.session_state["main_view"]="Filings";app.run()
            self.assertFalse(app.exception);self.assertFalse(app.error)
            self.assertEqual(len(app.sidebar.selectbox),0)
            app.selectbox(key="filing_form").select("8-K").run()
            self.assertEqual(app.metric[2].value,"1")

    def test_missing_snapshot_is_an_explicit_error_without_db_fallback(self):
        with patch("src.demo.load_snapshot",side_effect=FileNotFoundError()), \
             patch("src.analytics.load_financials",side_effect=AssertionError("database fallback")):
            app=AppTest.from_file(str(ROOT/"demo/dashboard.py")).run()
        self.assertFalse(app.exception);self.assertEqual(len(app.error),1)
