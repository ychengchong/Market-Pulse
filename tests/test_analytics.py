"""Independent arithmetic and period-alignment checks using invented values."""
from datetime import date
from decimal import Decimal
import unittest

from src.analytics import build_periods, compare_companies, ratio


def row(metric, value, start="2025-01-01", end="2025-03-31", kind="quarter_duration", status="selected"):
    return dict(cik="1", metric=metric, value=Decimal(value) if value is not None else None,
                start_date=date.fromisoformat(start) if start else None, end_date=date.fromisoformat(end),
                period_kind=kind, status=status)


def dataset(*rows, annual=()):
    return dict(companies=[dict(cik="1", ticker="TEST")], observations=list(rows),
                annual_support=[dict(cik="1", start_date=date.fromisoformat(s), end_date=date.fromisoformat(e)) for s,e in annual])


class CalculationTests(unittest.TestCase):
    def test_margin_and_loss_use_exact_decimal_inputs(self):
        data = dataset(row("revenue", "125"), row("net_income", "-25"), row("gross_profit", "50"))
        p = build_periods(data, "1", "Quarterly")[0]
        self.assertEqual(p["net_margin"], Decimal("-20"))
        self.assertEqual(p["gross_margin"], Decimal("40"))
        self.assertIsInstance(p["net_margin"], Decimal)

    def test_missing_and_nonpositive_denominators_remain_unavailable(self):
        for n,d in [(None,Decimal(1)),(Decimal(1),None),(Decimal(1),Decimal(0)),(Decimal(1),Decimal(-5))]:
            self.assertIsNone(ratio(n,d))

    def test_zero_reported_profit_is_distinct_from_missing(self):
        p = build_periods(dataset(row("revenue","100"),row("net_income","0")),"1","Quarterly")[0]
        self.assertEqual(p["net_margin"], 0)
        self.assertIsNone(p["operating_cash_flow"])

    def test_cumulative_cash_flow_is_not_used_as_quarter(self):
        p = build_periods(dataset(row("revenue","100",start="2025-04-01",end="2025-06-30"),
            row("operating_cash_flow","80",end="2025-06-30",kind="six_month_duration")),"1","Quarterly")[0]
        self.assertIsNone(p["operating_cash_flow"])

    def test_matching_end_with_wrong_start_cannot_form_margin(self):
        p=build_periods(dataset(row("revenue","100"),row("net_income","20",start="2024-04-01",kind="year_duration")),"1","Quarterly")[0]
        self.assertIsNone(p["net_margin"])

    def test_instant_values_must_match_period_end(self):
        data=dataset(row("revenue","100"),row("assets","200",start=None,kind="instant"),
                     row("liabilities","80",start=None,end="2024-12-31",kind="instant"))
        p=build_periods(data,"1","Quarterly")[0]
        self.assertEqual(p["assets"],200)
        self.assertIsNone(p["liabilities"])
        self.assertIsNone(p["liabilities_assets"])

    def test_ambiguous_source_is_not_charted(self):
        p=build_periods(dataset(row("revenue",None,status="ambiguous"),row("net_income","20")),"1","Quarterly")[0]
        self.assertIsNone(p["revenue"])
        self.assertIsNone(p["net_margin"])
        self.assertNotIn("revenue",p["sources"])

    def test_ttm_duration_requires_annual_report_support(self):
        data=dataset(row("revenue","400",start="2024-04-01",kind="year_duration"))
        self.assertEqual(build_periods(data,"1","Annual"),[])

    def test_annual_report_period_is_used_with_exact_dates(self):
        data=dataset(row("revenue","400",start="2024-04-01",kind="year_duration"),annual=[("2024-04-01","2025-03-31")])
        p=build_periods(data,"1","Annual")[0]
        self.assertEqual(p["revenue"],400)
        self.assertEqual(p["start_date"],date(2024,4,1))

    def test_year_on_year_growth_has_traceable_prior_period(self):
        data=dataset(row("revenue","100",start="2024-01-01",end="2024-03-31"),row("revenue","120"))
        p=build_periods(data,"1","Quarterly")[-1]
        self.assertEqual(p["revenue_growth"],20)
        self.assertEqual(p["growth_source"],(date(2024,1,1),date(2024,3,31)))

    def test_zero_prior_revenue_cannot_produce_growth(self):
        data=dataset(row("revenue","0",start="2024-01-01",end="2024-03-31"),row("revenue","120"))
        self.assertIsNone(build_periods(data,"1","Quarterly")[-1]["revenue_growth"])

    def test_multiple_prior_periods_do_not_produce_growth(self):
        data=dataset(row("revenue","100",start="2024-01-01",end="2024-03-31"),
                     row("revenue","101",start="2024-01-02",end="2024-04-01"),row("revenue","120"))
        self.assertIsNone(build_periods(data,"1","Quarterly")[-1]["revenue_growth"])

    def test_comparison_does_not_pick_arbitrary_quarter(self):
        data=dataset(row("revenue","100"),row("revenue","110",start="2025-04-01",end="2025-06-30"))
        self.assertIsNone(compare_companies(data,["TEST"],"Quarterly",2025)[0]["period"])
        self.assertEqual(compare_companies(data,["TEST"],"Quarterly",2025,2)[0]["period"]["revenue"],110)

    def test_exact_date_filter_can_leave_company_unavailable(self):
        data=dataset(row("revenue","100"))
        self.assertIsNone(compare_companies(data,["TEST"],"Quarterly",2025,1,date(2025,3,30))[0]["period"])

    def test_no_annual_or_q4_is_invented_from_other_periods(self):
        data=dataset(row("revenue","100"),row("revenue","450",end="2025-12-31",kind="year_duration"))
        self.assertEqual(len(build_periods(data,"1","Quarterly")),1)

