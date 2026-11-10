"""Shared financial views for PostgreSQL results and the frozen public snapshot."""
import csv
from datetime import timezone, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path

import streamlit as st
from src.db_config import connection_string

BILLION = Decimal(1_000_000_000)
LABELS = {"revenue": "Revenue", "net_income": "Net income", "operating_cash_flow": "Operating cash flow",
          "assets": "Assets", "liabilities": "Liabilities", "net_margin": "Net margin",
          "gross_margin": "Gross margin", "operating_margin": "Operating margin", "revenue_growth": "Revenue growth"}


def money(value):
    return "Unavailable" if value is None else f"${value/BILLION:,.2f}B"


def percent(value):
    return "Unavailable" if value is None else f"{value:,.1f}%"


def chart(records, x, y, series, bar=False, percent_axis=False, key=None, title=None, compact=False):
    if not any(row.get(y) is not None for row in records):
        st.info("No reported values are available for this chart and selection.")
        return
    temporal = x == "Period end"
    chart_height = 270 if compact else 340
    spec = {"data": {"values": records}, "height": chart_height,
            "autosize": {"type": "fit", "contains": "padding"},
            "mark": {"type": "bar" if bar else "line", **({} if bar else {"point": True})},
            "encoding": {
                "x": {"field": x, "type": "temporal" if temporal else "nominal", "title": None,
                      **({"axis": {"format": "%Y", "tickCount": 5, "labelAngle": 0}} if temporal else {"sort": None})},
                "y": {"field": y, "type": "quantitative", "title": "%" if percent_axis else "USD billions"},
                "color": {"field": series, "type": "nominal", "title": None},
                "tooltip": [{"field": field, "type": "quantitative" if field == y else "nominal"} for field in records[0]]},
            "config": {"view": {"stroke": None},
                       "axis": {"gridColor": "#edf1f4", "labelFontSize": 10, "titleFontSize": 10},
                       "legend": {"orient": "bottom", "direction": "horizontal", "columns": 3, "labelLimit": 140, "labelFontSize": 10}}}
    if title:
        spec["title"] = {"text": title, "anchor": "start", "fontSize": 13, "offset": 8}
    st.vega_lite_chart(spec=spec, width="stretch", height=chart_height, key=key, alt=title or f"{y} by {x}")


def source_table(periods):
    rows = []
    for period in periods:
        for metric, source in period["sources"].items():
            rows.append({"Metric": LABELS.get(metric, metric.replace("_", " ").title()),
                         "Value (USD)": str(source["value"]), "Period start": str(source["start_date"] or "Instant"),
                         "Period end": str(source["end_date"]), "Filed": str(source["filed"]),
                         "Form": source["form"], "Source tag": source["tag"], "Source": source["source_url"]})
    return rows


def render_overview(data):
    with st.container(gap="xsmall"):
        render_overview_content(data)


def render_overview_content(data):
    from src.analytics import build_periods
    company_col, mode_col, period_col, tools_col = st.columns([1.2, 1, 1.5, 1.1], gap="small", vertical_alignment="center")
    companies = {company["ticker"]: company for company in data["companies"]}
    ticker = company_col.selectbox("Company", list(companies), format_func=lambda t: f"{companies[t]['name']} ({t})", key="financial_company", label_visibility="collapsed", help="Company shown in all four charts and KPI cards.")
    mode = mode_col.segmented_control("Reporting periods", ["Annual", "Quarterly"], default="Annual", required=True, key="financial_mode", label_visibility="collapsed", help="Annual-report periods or directly reported quarters.")
    company = companies[ticker]
    periods = build_periods(data, company["cik"], mode)
    if not periods:
        st.info("No supported revenue-anchored periods are available for this company and reporting mode.")
        return
    years = sorted({p["end_date"].year for p in periods})
    toolbar = tools_col.container(horizontal=True, gap="xsmall")
    with toolbar:
        with st.popover("Years", icon=":material/filter_list:"):
            selected_years = st.multiselect("Period end years", years, default=years, key="financial_years_"+ticker+mode)
    visible = [p for p in periods if p["end_date"].year in selected_years]
    if not visible:
        st.info("Select at least one period-end year.")
        return
    labels = {i: f"{p['start_date']} to {p['end_date']}" for i,p in enumerate(visible)}
    selected = period_col.selectbox("Period for KPI cards", list(labels), index=len(labels)-1, format_func=labels.get, key="financial_period_"+ticker+mode, label_visibility="collapsed", help="Exact reporting interval used by the KPI cards. Charts show all selected years.")
    current = visible[selected]
    with toolbar:
        source_panel = st.popover("Sources", icon=":material/description:")
    cols = st.columns(4, gap="small")
    cols[0].metric("Revenue", money(current["revenue"]), border=True, help="Revenue YoY: " + percent(current["revenue_growth"]))
    cols[1].metric("Net income", money(current["net_income"]), border=True)
    cols[2].metric("Net margin", percent(current["net_margin"]), border=True)
    cols[3].metric("Operating cash flow", money(current["operating_cash_flow"]), border=True)
    note = f"{mode} · USD billions · Data as of {company['as_of']} · Revenue YoY: {percent(current['revenue_growth'])}"
    if current["issues"]:
        note += " · Unavailable: " + ", ".join(LABELS.get(m,m.replace('_',' ')) for m in current["issues"])
    st.caption(note)
    left, right = st.columns(2, gap="medium")
    with left:
        chart([{"Period end": str(p["end_date"]), "Period start": str(p["start_date"]), "Series": LABELS[m],
                "Amount": float(p[m]/BILLION) if p[m] is not None else None}
               for p in visible for m in ("revenue","net_income")], "Period end", "Amount", "Series", key="income_chart", title="Revenue and net income", compact=True)
    with right:
        chart([{"Period end": str(p["end_date"]), "Series": LABELS[m], "Margin": float(p[m]) if p[m] is not None else None}
               for p in visible for m in ("net_margin","operating_margin","gross_margin")],
              "Period end", "Margin", "Series", percent_axis=True, key="margin_chart", title="Profit margins", compact=True)
    left, right = st.columns(2, gap="medium")
    with left:
        chart([{"Period end": str(p["end_date"]), "Series": "Operating cash flow", "Amount": float(p["operating_cash_flow"]/BILLION) if p["operating_cash_flow"] is not None else None}
               for p in visible], "Period end", "Amount", "Series", bar=True, key="cash_chart", title="Operating cash flow", compact=True)
    with right:
        chart([{"Period end": str(p["end_date"]), "Series": LABELS[m], "Amount": float(p[m]/BILLION) if p[m] is not None else None}
               for p in visible for m in ("assets","liabilities")], "Period end", "Amount", "Series", key="balance_chart", title="Assets and liabilities", compact=True)
    with source_panel:
        st.caption("Snapshot retrieved " + company["retrieved_at"].astimezone(timezone(timedelta(hours=8))).strftime("%d %b %Y, %H:%M SGT"))
        st.write("Annual mode requires annual-report revenue evidence. Quarterly mode uses directly reported quarter-length facts; cumulative six-/nine-month totals are excluded. No quarter or Q4 is derived by subtraction. Missing values are never filled with zero. Lines connect available reported periods.")
        st.write("Net margin = net income / revenue; operating margin = operating income / revenue; gross margin = gross profit / revenue. Ratios use matching intervals and a positive denominator. Revenue growth requires a unique prior period approximately one year earlier with compatible duration.")
        if current["growth_source"]:
            st.caption(f"Revenue growth comparison: {current['growth_source'][0]} to {current['growth_source'][1]}")
        rows = source_table([current])
        st.dataframe(rows, hide_index=True, column_config={"Source": st.column_config.LinkColumn("SEC filing")})
        if rows:
            buffer=io.StringIO(); writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            st.download_button("Download source values (CSV)",buffer.getvalue(),file_name=ticker.lower()+"-financial-sources.csv",mime="text/csv")
        st.caption(f"Dataset: {company['dataset_id']} | Snapshot: {company['snapshot_id']}")


def render_comparison(data):
    from src.analytics import build_periods, compare_companies
    st.header("Compare companies")
    tickers = [c["ticker"] for c in data["companies"]]
    chosen = st.multiselect("Companies to compare", tickers, default=tickers, key="compare_companies")
    mode = st.radio("Comparison periods", ["Annual", "Quarterly"], horizontal=True, key="compare_mode")
    all_periods = {c["ticker"]: build_periods(data,c["cik"],mode) for c in data["companies"] if c["ticker"] in chosen}
    years = sorted({p["end_date"].year for values in all_periods.values() for p in values},reverse=True)
    if not chosen or not years:
        st.info("Choose companies with available reported periods.")
        return
    common = set.intersection(*[{p["end_date"].year for p in values} for values in all_periods.values()])
    default = max(common) if common else years[0]
    year = st.selectbox("Period end year",years,index=years.index(default),key="compare_year")
    quarter = st.selectbox("Calendar quarter containing the period end",[1,2,3,4],key="compare_quarter") if mode=="Quarterly" else None
    exact = st.checkbox("Require the same exact period end date",key="compare_exact")
    exact_end = None
    if exact:
        dates = sorted({p["end_date"] for values in all_periods.values() for p in values if p["end_date"].year==year and (quarter is None or (p["end_date"].month-1)//3+1==quarter)})
        if not dates:
            st.info("No matching period end dates."); return
        exact_end=st.selectbox("Exact period end",dates,key="compare_end")
    matches = compare_companies(data,chosen,mode,year,quarter,exact_end)
    ends = {row["period"]["end_date"] for row in matches if row["period"]}
    if len(ends)>1:
        st.warning("Reporting dates differ across these companies. This compares periods ending in the selected calendar year/quarter; check the exact dates below before drawing conclusions.")
    st.caption("Fiscal year ends vary. A calendar end-year selection is not a claim that every company reports the same fiscal year.")
    field = st.selectbox("Comparison metric",["revenue","net_income","operating_cash_flow","net_margin","gross_margin","operating_margin"],format_func=LABELS.get,key="compare_metric")
    percentage=field.endswith("margin")
    chart_rows=[]; table=[]
    for row in matches:
        company,p=row["company"],row["period"]
        value=p[field] if p else None
        chart_rows.append({"Company":company["ticker"],"Series":LABELS[field],"Value":float(value if percentage else value/BILLION) if value is not None else None,
                           "Period start":str(p["start_date"]) if p else "Unavailable","Period end":str(p["end_date"]) if p else "Unavailable"})
        table.append({"Company":company["name"],"Ticker":company["ticker"],"Period start":str(p["start_date"]) if p else "Unavailable", "Period end":str(p["end_date"]) if p else "Unavailable",
                      LABELS[field]:percent(value) if percentage else money(value),"Data as of":str(company["as_of"]),
                      "Note":row["reason"] or ("No selected source value for this metric" if value is None else "Reported period")})
    chart(chart_rows,"Company","Value","Series",bar=True,percent_axis=percentage,key="comparison_chart")
    st.dataframe(table,hide_index=True)
    with st.expander("Comparison source evidence"):
        st.dataframe([dict(Company=row["company"]["ticker"],**source) for row in matches if row["period"] for source in source_table([row["period"]])],hide_index=True,column_config={"Source":st.column_config.LinkColumn("SEC filing")})


def render_financials(overview_tab, comparison_tab, frozen_data=None):
    try:
        dsn = connection_string() if frozen_data is None else None
        if frozen_data is None and not dsn:
            for tab in (overview_tab,comparison_tab):
                with tab:
                    st.info("Connect your PostgreSQL database to view financial charts. Set DATABASE_URL or add local database settings in .streamlit/secrets.toml, then run python -m scripts.refresh_data. The Filings tab remains available.")
            return
        from src.analytics import load_financials
        data = load_financials(dsn) if frozen_data is None else frozen_data
        if not data["companies"]:
            raise ValueError("No imported companies")
    except Exception:
        for tab in (overview_tab,comparison_tab):
            with tab:
                st.error("Financial data is unavailable. Check PostgreSQL and connection settings, then run python -m scripts.refresh_data. Saved filing summaries remain available in Filings.")
        return
    status=Path("data/refresh_status.json")
    if frozen_data is None and status.exists():
        try:
            report=json.loads(status.read_text(encoding="utf-8"))
            if report.get("status") != "success":
                with overview_tab:
                    st.warning("The latest financial refresh did not finish. Charts show the last successfully imported database results.")
        except (OSError,ValueError,AttributeError):
            with overview_tab:st.warning("Latest refresh status could not be read; check the data-as-of dates.")
    with overview_tab: render_overview(data)
    with comparison_tab: render_comparison(data)
