import streamlit as st
from src.financial_ui import render_financials
from src.filing_ui import render_filings

st.set_page_config(page_title="Market Pulse", page_icon=":material/monitoring:", layout="wide")
with st.container(gap="xsmall"):
    brand, about = st.columns([9, 1], vertical_alignment="center")
    brand.markdown("### Market Pulse")
    with about.popover("About", icon=":material/info:", width="stretch"):
        st.write("Explore company performance through SEC financial data, company comparisons and source-linked filing highlights.")
        st.caption("Reported financial results, not a live stock-price feed. The sidebar filters apply to the Filings tab.")
    financial_tab, comparison_tab, filing_tab = st.tabs(
        ["Financial overview", "Company comparison", "Filings"], key="main_view", on_change="rerun")
    st.set_page_config(initial_sidebar_state="expanded" if filing_tab.open else "collapsed")
    if filing_tab.open:
        with filing_tab:
            render_filings()
    else:
        render_financials(financial_tab, comparison_tab)
