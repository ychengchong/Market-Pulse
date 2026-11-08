import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st


SUMMARIES_FILE = Path("data/summaries.json")

st.set_page_config(
    page_title="Market Pulse",
    page_icon="📈",
    layout="wide"
)

st.title("Market Pulse")
st.write(
    "Follow company updates through SEC filings. Market Pulse brings recent disclosures "
    "into one place, with short highlights and links to the original documents."
)
st.caption("Use the filters to focus your reading. Open a source filing for the full context.")


def display_time(value):
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone(timedelta(hours=8))).strftime("%d %b %Y, %H:%M SGT")
    except (ValueError, TypeError):
        return "time unavailable"


stage_labels = {"metadata": "Filing list", "processing": "Filing text", "summaries": "Summaries"}
update_details = []

run_reports = {}
for stage in ("metadata", "processing", "summaries"):
    status_path = Path(f"data/{stage}_status.json")
    if not status_path.exists():
        continue
    try:
        report = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Expected a status record")
        run_reports[stage] = report
        timestamp = display_time(report.get("finished_at", report.get("started_at")))
        if not report.get("output_updated"):
            st.warning(
                f"{stage_labels[stage]} update: {report.get('status', 'unknown')} ({timestamp}). "
                "The update was not confirmed complete; displayed results may be from an older run."
            )
        else:
            update_details.append(f"{stage_labels[stage]}: {report.get('records', 0)} records updated {timestamp}")
        failures = [item for item in report.get("items", []) if item.get("status") == "failed"]
        if failures:
            with st.expander(f"{stage.title()} failures ({len(failures)})"):
                st.dataframe([
                    {key: item.get(key, "") for key in ("company", "accession_number", "error")}
                    for item in failures
                ], hide_index=True)
    except (OSError, ValueError, TypeError, AttributeError):
        st.warning(f"Unable to read {stage} run status; data freshness is unknown.")

if update_details:
    summary_report = run_reports.get("summaries", {})
    if summary_report.get("output_updated"):
        st.caption(f"Summaries updated {display_time(summary_report.get('finished_at'))}")
    with st.expander("Data updates"):
        for detail in update_details:
            st.caption(detail)

for upstream, downstream in (("metadata", "processing"), ("processing", "summaries")):
    source = run_reports.get(upstream, {})
    consumer = run_reports.get(downstream, {})
    finished = source.get("finished_at", "")
    started = consumer.get("started_at", "")
    if source.get("output_updated") and isinstance(finished, str) and isinstance(started, str) and finished > started:
        st.warning(f"{upstream.title()} has newer results. Rerun {downstream} before treating downstream results as current.")

if not SUMMARIES_FILE.exists():
    st.error(
        "data/summaries.json was not found. "
        "Run the pipeline scripts first."
    )
    st.stop()

try:
    with SUMMARIES_FILE.open("r", encoding="utf-8") as json_file:
        summaries = json.load(json_file)
    required = {"company", "ticker", "form", "filing_date", "event_type", "summary",
                "summary_method", "source_word_count", "filing_url"}
    if not isinstance(summaries, list) or any(
        not isinstance(item, dict) or not required <= item.keys()
        or not isinstance(item["source_word_count"], int)
        or any(not isinstance(item[key], str) for key in required - {"source_word_count"})
        for item in summaries
    ):
        raise ValueError("Invalid summary records")
except (OSError, ValueError):
    st.error("Saved summaries could not be read. Check the pipeline status and regenerate the summaries.")
    st.stop()

if not summaries:
    st.warning("No summaries are available. Run the pipeline and review any ingestion failures above.")

companies = sorted({
    item["company"]
    for item in summaries
})

forms = sorted({
    item["form"]
    for item in summaries
})

st.sidebar.header("Explore filings")
st.sidebar.caption("Combine the two filters to narrow the saved results.")

selected_company = st.sidebar.selectbox(
    "Company",
    ["All"] + companies,
    help="Show one company's filings, or choose All to browse every company."
)
st.sidebar.caption("Company selects whose disclosures you see.")

selected_form = st.sidebar.selectbox(
    "Filing form",
    ["All"] + forms,
    help="Choose a report type. All includes every available filing form."
)
st.sidebar.caption("Filing form selects the kind of report. Choose All to include every type.")
st.sidebar.divider()
st.sidebar.markdown("**Filing types at a glance**")
st.sidebar.markdown(
    "**8-K** ? Company events and announcements\n\n"
    "**10-Q** ? Quarterly financial report\n\n"
    "**10-K** ? Annual financial report"
)

filtered_summaries = []

for item in summaries:
    company_matches = (
        selected_company == "All"
        or item["company"] == selected_company
    )

    form_matches = (
        selected_form == "All"
        or item["form"] == selected_form
    )

    if company_matches and form_matches:
        filtered_summaries.append(item)

column1, column2, column3 = st.columns(3)

column1.metric(
    "Companies monitored",
    len(companies),
    border=True
)

column2.metric(
    "Saved summaries",
    len(summaries),
    border=True
)

column3.metric(
    "Matching filings",
    len(filtered_summaries),
    border=True
)

st.divider()
st.header("Filings")
company_label = "All companies" if selected_company == "All" else selected_company
form_label = "All forms" if selected_form == "All" else selected_form
st.caption(f"Showing {len(filtered_summaries)} of {len(summaries)} saved filings | {company_label} | {form_label}")
if summaries and not filtered_summaries:
    st.info("No filings match these filters. Choose All for company or filing form to broaden the results.")


def render_filing(item, compact=False):
    st.caption(f"Filed: {item['filing_date']} | Event type: {item['event_type']}")
    summary = item["summary"]
    if compact and len(summary) > 450:
        preview = summary[:450].rsplit(" ", 1)[0].rstrip()
        st.write(preview + "\u2026")
        with st.expander("Read full summary"):
            st.write(summary)
    else:
        st.write(summary)
    st.caption(
        f"Method: {item['summary_method']} | "
        f"Source words: {item['source_word_count']:,}"
    )
    st.markdown(f"[Open the official SEC filing]({item['filing_url']})")


# Group only the filtered 8-K entries; periodic reports remain individual cards.
cards = {}
for index, item in enumerate(filtered_summaries):
    key = ("8-K", item["company"], item["ticker"]) if item["form"] == "8-K" else ("report", index)
    cards.setdefault(key, []).append(item)

for entries in cards.values():
    item = entries[0]
    with st.container(border=True):
        if item["form"] == "8-K":
            st.subheader(f"{item['company']} ({item['ticker']}) - Recent 8-K events")
            ordered = sorted(entries, key=lambda record: record["filing_date"], reverse=True)
            for index, event in enumerate(ordered):
                if index:
                    st.divider()
                render_filing(event, compact=True)
        else:
            st.subheader(f"{item['company']} ({item['ticker']}) - {item['form']}")
            render_filing(item)
