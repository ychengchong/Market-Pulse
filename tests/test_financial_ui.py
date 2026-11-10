"""Exercise chart rendering, filter changes and failure isolation with synthetic data."""
from datetime import datetime, timezone
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from test_database import DatasetWorkspace, ROOT
from test_analytics import dataset, row
from src.storage import save_filings_to_json


class FinancialUITests(DatasetWorkspace):
    def data(self):
        data=dataset(row("revenue","100",start="2024-01-01",end="2024-12-31",kind="year_duration"),
            row("net_income","20",start="2024-01-01",end="2024-12-31",kind="year_duration"),
            row("revenue","120"),row("net_income","30"),
            annual=[("2024-01-01","2024-12-31")])
        data["companies"][0].update(name="Invented Company",as_of="2025-12-31",
            retrieved_at=datetime(2026,1,1,tzinfo=timezone.utc),dataset_id="synthetic",snapshot_id="synthetic")
        for source in data["observations"]:
            source.update(filed="2025-08-01",form="10-Q",tag="Synthetic",source_url="https://www.sec.gov/")
        return data

    def test_financial_charts_and_quarterly_filter(self):
        save_filings_to_json([],"data/summaries.json")
        with patch("src.financial_ui.connection_string",return_value="synthetic"), \
             patch("src.analytics.load_financials",return_value=self.data()):
            app=AppTest.from_file(str(ROOT/"dashboard.py"),default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.sidebar.selectbox),0)
            self.assertEqual(app.metric[2].value,"20.0%")
            self.assertGreaterEqual(len(app.get("vega_lite_chart")),3)
            app.segmented_control(key="financial_mode").set_value("Quarterly").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[2].value,"25.0%")
            app.multiselect(key="compare_companies").set_value([]).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Choose companies" in item.value for item in app.info))
            app.session_state["main_view"]="Filings"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.sidebar.selectbox),0)
            self.assertEqual(app.selectbox(key="filing_company").value,"All")
            self.assertEqual(app.selectbox(key="filing_form").value,"All")
            app.session_state["main_view"]="Company comparison"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.sidebar.selectbox),0)

    def test_database_failure_keeps_filings_available_without_secret_output(self):
        save_filings_to_json([],"data/summaries.json")
        with patch("src.financial_ui.connection_string",return_value="synthetic"), \
             patch("src.analytics.load_financials",side_effect=ValueError("private-password")):
            app=AppTest.from_file(str(ROOT/"dashboard.py"),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.error),2)
        self.assertNotIn("private-password"," ".join(item.value for item in app.error))
        app.session_state["main_view"]="Filings"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.error),0)
        self.assertEqual([m.value for m in app.metric],["0","0","0"])
