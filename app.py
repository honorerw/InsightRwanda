"""InsightRwanda Streamlit entry point.

Run from the repository root with::

    streamlit run app.py

The navigation is explicit so that page availability does not depend on
automatic file discovery. Pages read only reviewed project metadata unless a
user opens the geographic reference page and selects a known boundary file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from insightrwanda.ui.theme import inject_global_styles


st.set_page_config(
    page_title="InsightRwanda",
    page_icon=":material/insights:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_styles()

pages = {
    "Main Dashboard": [
        st.Page("app_pages/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("app_pages/financial_inclusion.py", title="Financial Inclusion", icon=":material/account_balance:"),
        st.Page("app_pages/poverty_insights.py", title="Poverty Insights", icon=":material/monitoring:"),
        st.Page("app_pages/geographic_analysis.py", title="Geographic Analysis", icon=":material/map:"),
    ],
    "Data Management": [
        st.Page("app_pages/dataset_registry.py", title="Dataset Registry", icon=":material/storage:"),
        st.Page("app_pages/source_inventory.py", title="Source Inventory", icon=":material/inventory_2:"),
        st.Page("app_pages/data_quality.py", title="Data Quality", icon=":material/fact_check:"),
        st.Page("app_pages/codebooks_variables.py", title="Codebooks & Variables", icon=":material/menu_book:"),
    ],
    "Research & Analytics": [
        st.Page("app_pages/indicator_catalogue.py", title="Indicator Catalogue", icon=":material/list_alt:"),
        st.Page("app_pages/variable_mapping.py", title="Variable Mapping", icon=":material/account_tree:"),
        st.Page("app_pages/statistical_analysis.py", title="Statistical Analysis", icon=":material/query_stats:"),
        st.Page("app_pages/research_methodology.py", title="Research Methodology", icon=":material/biotech:"),
    ],
    "Governance & Reports": [
        st.Page("app_pages/research_readiness.py", title="Research Readiness", icon=":material/verified:"),
        st.Page("app_pages/reports_exports.py", title="Reports & Exports", icon=":material/file_export:"),
        st.Page("app_pages/evidence_provenance.py", title="Evidence & Provenance", icon=":material/source:"),
        st.Page("app_pages/methodology_sources.py", title="Methodology & Sources", icon=":material/policy:"),
    ],
}

with st.sidebar:
    st.markdown(
        "<div class='sidebar-brand'><strong>Insight</strong>Rwanda</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sidebar-tagline'>Evidence-led policy intelligence</div>"
        "<div class='sidebar-context'>"
        "<div class='sidebar-kicker'>NISR 2026 Big Data Hackathon</div>"
        "<div class='sidebar-track'>Financial Inclusion &amp; Poverty Reduction</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sidebar-note'><span class='status-dot'></span>"
        "Foundation mode<br><small>Verified indicators are not yet available.</small></div>",
        unsafe_allow_html=True,
    )

navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()
