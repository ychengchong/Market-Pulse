"""Shared dashboard layout for local PostgreSQL and the portable snapshot demo."""
import streamlit as st
from src.ui.financial_ui import render_financials
from src.ui.filing_ui import render_filings


def render_app(demo=None):
    st.set_page_config(page_title="Market Pulse", page_icon=":material/monitoring:", layout="wide")
    with st.container(gap="xsmall"):
        brand, about = st.columns([9, 1], vertical_alignment="center")
        brand.markdown("### Market Pulse" + (" :gray-badge[Snapshot demo]" if demo is not None else ""))
        with about.popover("About", icon=":material/info:", width="stretch"):
            st.write("Explore company performance through SEC financial data, company comparisons and source-linked filing highlights.")
            st.caption("Reported financial results, not a live stock-price feed. Company and report-type filters are on the Filings page.")
            if demo is not None:
                st.caption(f"Frozen portfolio demo exported {demo['exported_at']}. Financial source cutoffs are shown per company. Updates are manual.")
        financial_tab, comparison_tab, filing_tab = st.tabs(
            ["Financial overview", "Company comparison", "Filings"], key="main_view", on_change="rerun")
        if filing_tab.open:
            with filing_tab:
                render_filings(frozen_summaries=demo["summaries"] if demo is not None else None,
                               frozen_at=demo["exported_at"] if demo is not None else None,
                               summaries_updated_at=demo.get("summaries_updated_at") if demo is not None else None)
        else:
            render_financials(financial_tab, comparison_tab,
                              frozen_data=demo["financials"] if demo is not None else None)
