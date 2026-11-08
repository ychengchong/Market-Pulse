import json
from pathlib import Path

import streamlit as st


SUMMARIES_FILE = Path("data/summaries.json")

st.set_page_config(
    page_title="Market Pulse",
    page_icon="📈",
    layout="wide"
)

st.title("Market Pulse")
st.write("SEC filing event monitor and summarisation pipeline")

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
        timestamp = report.get("finished_at", report.get("started_at", "unknown time"))
        if not report.get("output_updated"):
            st.warning(
                f"{stage.title()} run: {report.get('status', 'unknown')} ({timestamp}). "
                "Its checkpoint was not confirmed updated; displayed results may be from an older run."
            )
        else:
            st.caption(f"{stage.title()}: updated {report.get('records', 0)} records at {timestamp}")
        failures = [item for item in report.get("items", []) if item.get("status") == "failed"]
        if failures:
            with st.expander(f"{stage.title()} failures ({len(failures)})"):
                st.dataframe([
                    {key: item.get(key, "") for key in ("company", "accession_number", "error")}
                    for item in failures
                ], hide_index=True)
    except (OSError, ValueError, TypeError, AttributeError):
        st.warning(f"Unable to read {stage} run status; data freshness is unknown.")

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

selected_company = st.sidebar.selectbox(
    "Company",
    ["All"] + companies
)

selected_form = st.sidebar.selectbox(
    "Filing form",
    ["All"] + forms
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
    len(companies)
)

column2.metric(
    "Total summaries",
    len(summaries)
)

column3.metric(
    "Visible records",
    len(filtered_summaries)
)

st.divider()

for item in filtered_summaries:
    with st.container(border=True):
        st.subheader(
            f"{item['company']} ({item['ticker']}) - "
            f"{item['form']}"
        )

        st.caption(
            f"Filed: {item['filing_date']} | "
            f"Event type: {item['event_type']}"
        )

        st.write(item["summary"])

        st.caption(
            f"Method: {item['summary_method']} | "
            f"Source words: {item['source_word_count']:,}"
        )

        st.markdown(
            f"[Open the official SEC filing]"
            f"({item['filing_url']})"
        )
