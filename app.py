from __future__ import annotations

import base64
import html
import os
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research.catalog import SourceProfile, aggregate_release_allowed, build_source_profile
from research.spss_pipeline import (
    SPSS_SOURCE_ID,
    build_spss_profile,
    enrich_spss_analysis_data as pipeline_enrich_spss_data,
    load_spss_analysis_data as pipeline_load_spss_data,
)
from research.data_pipeline import (
    ANALYSIS_COLUMNS as PIPELINE_COLUMNS,
    aggregate_weighted_measure,
    enrich_analysis_data as pipeline_enrich_analysis_data,
    filter_analysis_data as pipeline_filter_analysis_data,
    load_analysis_data as pipeline_load_analysis_data,
)
from research.modeling import (
    ModelRecord,
    holdout_artifacts,
    predict_priority,
    pr_curve,
    subgroup_performance,
    threshold_metrics,
    train_final_model,
)
from research.briefs import (
    LENS_PREFIXES,
)
from research.indicators import INDICATORS, calculate_by_group, calculate_indicator
from research.joint import (
    MEASURES,
    SOURCE_LABELS as JOINT_SOURCE_LABELS,
    TARGETS,
    build_joint_frame,
    comparison_note,
    evaluate_transport,
    linkage_audit,
    pooled_estimates,
    wave_note,
    weighted_correlation,
)
from research.quality import QualityCheck, quality_summary, run_quality_checks
from research.assistant import AssistantChart, MAX_QUESTION_LENGTH, answer_question, answer_with_chart
from research.assistant_llm import (
    answer_general_with_status,
    get_configured_provider,
    refine_answer_with_status,
)


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta"
LOGO_PATH = APP_DIR / "assets" / "insight_rwanda_logo.png"
SPSS_PATH = APP_DIR / "data" / "Rwanda FinScope 2020_Final Data.sav"

COMBINED_SOURCE_ID = "insightrwanda_combined"
COMBINED_LABEL = "Combined dataset · FinScope 2024 (master) + FinScope 2020 (SPSS)"
COMBINED_LABEL_SHORT = "FinScope Rwanda · 2024 & 2020 waves"

# Survey-year lens. Both waves are documented by their supplied release names:
# the master file is the FinScope 2024 wave; the SPSS file is the FinScope 2020
# wave (fieldwork September-November 2019).
YEAR_ALL = "All years"
YEAR_2020 = "2020 · FinScope 2020"
YEAR_2024 = "2024 · FinScope 2024"
YEAR_OPTIONS = (YEAR_ALL, YEAR_2020, YEAR_2024)
YEAR_SHORT = {YEAR_ALL: "All years", YEAR_2020: "2020 wave", YEAR_2024: "2024 wave"}


def active_year() -> str:
    """The sidebar's survey-year choice ('All years' before the widget renders)."""

    year = st.session_state.get("survey_year", YEAR_ALL)
    return year if year in YEAR_OPTIONS else YEAR_ALL


def apply_year_filter(frame: pd.DataFrame, choice: str) -> pd.DataFrame:
    """Keep records from the chosen survey wave ('All years' keeps everything)."""

    if choice == YEAR_2020:
        return frame[frame["survey_year"].eq(2020)]
    if choice == YEAR_2024:
        return frame[frame["survey_year"].eq(2024)]
    return frame

st.set_page_config(
    page_title="InsightRwanda | Research Analytics",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "◒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Design system
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;600&family=Roboto:wght@400;500;600;700&display=swap');
:root {
    --ink: #17213d;
    --muted: #66718b;
    --line: #dce3ef;
    --paper: #f5f7fb;
    --card: #ffffff;
    --green: #3155d4;
    --green-dark: #172554;
    --mint: #e8edff;
    --orange: #de7c3f;
    --yellow: #e5ae2f;
    --rose: #d95362;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Roboto', Arial, Verdana, sans-serif; color: var(--ink); }
body { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
.stApp { background: var(--paper); }
header[data-testid="stHeader"] { background: transparent !important; }
footer { display: none !important; }
/* Streamlit's default sidebar-collapse chevron is removed entirely: the sidebar's
   own menu button (top of the rail) is the single collapse control. Streamlit's
   auto-collapse on narrow screens keeps showing its *expand* control, which is
   restyled below so no one is ever stranded with a closed rail. */
[data-testid="stToolbar"] [data-testid="stBaseButton-header"],
[data-testid="stToolbar"] [data-testid="stMainMenuButton"],
[data-testid="stToolbar"] [data-testid="stStatusWidget"],
[data-testid="stSidebarCollapseButton"],
#MainMenu { display: none !important; }
[data-testid="stExpandSidebarButton"] button,
[data-testid="stExpandSidebarButton"][kind] { border-radius:10px; }
[data-testid="stExpandSidebarButton"] {
  background:#eaf7f0 !important; border:1px solid #bfe6cf !important;
  box-shadow:0 2px 8px rgba(5,150,105,.12); color:#14532d !important;
  transition:background .16s ease, border-color .16s ease;
}
[data-testid="stExpandSidebarButton"] svg { fill:#059669; }
[data-testid="stExpandSidebarButton"]:hover { background:#d9f2e5 !important; border-color:#aaddc2 !important; }
[data-testid="stAppViewContainer"] { background: var(--paper); }
.block-container { max-width: 1480px; padding: 1.35rem 3.4rem 6.4rem; }
.main .block-container { animation: rise-in .35s ease-out both; }
@keyframes rise-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
/* Staggered entrances: cards cascade in while the whole page rises */
.metric-card, .chart-card, .callout, .page-intro, .filter-shell { animation: rise-in .4s ease-out both; }
.page-intro { animation-delay: .03s; }
.filter-shell { animation-delay: .09s; }
.chart-card { animation-delay: .12s; }
.metric-card[data-delay="1"] { animation-delay: .07s; }
.metric-card[data-delay="2"] { animation-delay: .14s; }
.metric-card[data-delay="3"] { animation-delay: .21s; }
/* Accessibility: honour the OS reduced-motion preference */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* Sidebar — very light mint rail beside the white workspace, WCAG-AA contrast */
[data-testid="stSidebar"] { background:#edf5f0; border-right:1px solid #d8e8dd; min-width:276px; }
/* The built-in sidebar header only hosts the (hidden) default collapse chevron and an
   empty logo spacer — a blank flex strip. Our own brand row replaces it, so remove it.
   No media query here: the hide applies at every screen size (desktop, tablet, phone). */
[data-testid="stSidebarHeader"] { display:none !important; }
/* Drop Streamlit's reserved sidebar top/bottom gaps for a tight rail everywhere */
[data-testid="stSidebarUserContent"] { padding-top:0 !important; padding-bottom:0 !important; }
[data-testid="stSidebar"] > div:first-child { padding:1.15rem .9rem 1.5rem; }
[data-testid="stSidebar"] * { color:#17213d; }
[data-testid="stSidebar"] hr { border-color:#d8e8dd; margin:1rem 0; }
.side-brand { display:flex; align-items:center; gap:.65rem; padding:.25rem .35rem 1rem; border-bottom:1px solid #d8e8dd; margin-bottom:.9rem; }
/* Custom collapse toggle (the only sidebar collapse control): quiet icon button in the rail */
[data-testid="stSidebar"] button[title="Collapse or expand the sidebar"] {
  width:100% !important; justify-content:center !important; border-radius:10px; padding:.5rem .3rem !important; }
[data-testid="stSidebar"] button[title="Collapse or expand the sidebar"]:hover { background:#e2f0e8; border-color:#cfe0d5; }
[data-testid="stSidebar"] button[title="Collapse or expand the sidebar"] svg { fill:#059669; }
.side-mark { width:48px; height:48px; flex:none; }
.side-name { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:.98rem; font-weight:600; letter-spacing:-.01em; color:#17213d; }
[data-testid="stSidebar"] .side-caption { color:#5b6f66 !important; font-size:.65rem; line-height:1.5; margin:.12rem .15rem .2rem; }
[data-testid="stSidebar"] .side-label { color:#6b8276 !important; font-family:'Roboto Mono','Courier New',monospace; text-transform:uppercase; letter-spacing:.14em; font-size:.6rem; font-weight:500; margin:1rem .35rem .45rem; padding-top:.8rem; border-top:1px solid #d8e8dd; }
[data-testid="stSidebar"] .side-label:first-of-type { margin-top:.2rem; padding-top:0; border-top:none; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] { margin:.1rem .05rem .35rem; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] label { color:#5b6f66 !important; font-size:.72rem; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div { background:#fff; border:1px solid #cfe0d5; border-radius:10px; min-height:40px; box-shadow:none; color:#17213d; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div:hover { border-color:#8fc7a8; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg { fill:#059669; }
[data-testid="stSidebar"] .stButton { width:100%; margin:.12rem 0; }
[data-testid="stSidebar"] .stButton button { width:100% !important; display:flex; align-items:center; border:1px solid transparent; border-radius:10px; background:transparent; color:#3f574d; font-size:.78rem; font-weight:600; padding:.56rem .72rem; transition:background .16s ease, border-color .16s ease, color .16s ease, transform .16s ease, box-shadow .16s ease; }
[data-testid="stSidebar"] .stButton button,
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] { justify-content:flex-start !important; text-align:left !important; }
[data-testid="stSidebar"] .stButton button p { font-size:.78rem; font-weight:600; width:100% !important; margin:0 !important; text-align:left !important; justify-content:flex-start !important; }
/* The active (primary) nav item keeps its dark-green label on the soft green pill:
   the blanket sidebar text colour would otherwise repaint the label on top of it. */
[data-testid="stSidebar"] .stButton button[kind="primary"],
[data-testid="stSidebar"] .stButton button[kind="primary"] p { color:#14532d !important; }
[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover { background:#e2f0e8; border-color:#cfe0d5; color:#17213d; }
[data-testid="stSidebar"] .stButton button[kind="secondary"]:active { transform:translateX(2px) scale(.99); }
/* Active nav item: soft green pill, rounded corners, darker text */
[data-testid="stSidebar"] .stButton button[kind="primary"] { background:#d3f1df; border-color:#bfe6cf; color:#14532d; box-shadow:0 3px 10px rgba(5,150,105,.10); }
[data-testid="stSidebar"] .stButton button[kind="primary"]:hover { background:#c3ead4; border-color:#aaddc2; color:#14532d; transform:translateX(3px); box-shadow:0 5px 14px rgba(5,150,105,.16); }
.side-card { border:1px solid #cfe0d5; background:#f6fbf8; border-radius:12px; padding:.75rem .8rem; margin:1rem .1rem 0; }
.side-card-title { font-size:.7rem; font-weight:700; color:#14532d !important; font-family:'Roboto Mono','Courier New',monospace; text-transform:uppercase; letter-spacing:.12em; }
.side-card-copy { font-size:.66rem; line-height:1.55; color:#5b6f66 !important; margin-top:.35rem; }
/* Primary action pinned near the rail's bottom edge, ahead of the profile row */
.st-key-side_actions { margin-top:1.1rem; padding-top:.85rem; border-top:1px solid #d8e8dd; }
.st-key-side_actions .stButton { width:100%; margin:.1rem 0; }
.st-key-side_actions .stButton button { width:100% !important; border-radius:10px; background:linear-gradient(145deg, #10b981, #059669); border:1px solid #059669; box-shadow:0 6px 16px rgba(5,150,105,.22); }
.st-key-side_actions .stButton button,
.st-key-side_actions .stButton button p { color:#fff !important; justify-content:center !important; text-align:center !important; font-size:.8rem; font-weight:700; padding:.6rem .75rem; }
.st-key-side_actions .stButton button:hover { filter:brightness(1.06); box-shadow:0 8px 18px rgba(5,150,105,.3); transform:translateY(-1px); }
/* Profile row: avatar, short info and dropdown indicator, opening an account menu */
.st-key-side_profile { margin-top:.85rem; }
.st-key-side_profile [data-testid="stPopover"] button { width:100%; display:flex; align-items:center; justify-content:flex-start; gap:.6rem; background:#f6fbf8; border:1px solid #cfe0d5; border-radius:12px; padding:.5rem .7rem; color:#17213d; font-size:.75rem; font-weight:600; box-shadow:none; }
.st-key-side_profile [data-testid="stPopover"] button:hover { border-color:#8fc7a8; background:#eef7f2; }
.st-key-side_profile [data-testid="stPopover"] [data-testid="stIconMaterial"] { color:#059669; }
.st-key-side_profile [data-testid="stPopover"] [data-testid="stMarkdownContainer"] p { margin:0; }
/* Filter chips: compact, removable selections under the toolbar */
.st-key-filter_chips { display:flex; flex-wrap:wrap; align-items:center; margin:-.15rem 0 .6rem; }
.st-key-filter_chips .stButton { margin:.15rem .2rem .15rem 0; }
.st-key-filter_chips .stButton button { border-radius:999px; border:1px solid #c9d8ce; background:#fff; color:#2f4a3e; font-size:.7rem; font-weight:600; padding:.3rem .68rem .3rem .52rem; box-shadow:0 1px 4px rgba(23,33,61,.05); display:flex; align-items:center; gap:.18rem; }
.st-key-filter_chips .stButton button:hover { border-color:#8fc7a8; background:#f2faf5; color:#14532d; }
.st-key-filter_chips [data-testid="stIconMaterial"] { font-size:.85rem; }

/* Masthead: elevated card with soft gradient wash and decorative sweep */
.app-header { position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between; gap:1rem;
  padding:1rem 1.35rem; border:1px solid var(--line); border-radius:18px; margin-bottom:1.55rem;
  background:linear-gradient(120deg, #f7fdf9 0%, #f5f8ff 52%, #eef3ff 100%);
  box-shadow:0 10px 30px rgba(23,33,61,.06), 0 2px 6px rgba(23,33,61,.03); }
.app-header::before { content:''; position:absolute; top:-68px; right:-52px; width:220px; height:180px; border-radius:50%;
  background:radial-gradient(closest-side, rgba(49,85,212,.10), transparent 70%); pointer-events:none; }
.app-header::after { content:''; position:absolute; bottom:-72px; left:34%; width:200px; height:150px; border-radius:50%;
  background:radial-gradient(closest-side, rgba(5,150,105,.09), transparent 70%); pointer-events:none; }
.app-header > * { position:relative; z-index:1; }
.brand { display:flex; align-items:center; gap:.85rem; }
/* Transparent-background logo: no chip, no ring, no box shadow — the artwork stands on the page. */
.brand-mark { width: 64px; height: 64px; flex:none; }
.brand-mark img, .side-mark img { width:100%; height:100%; object-fit:contain; display:block; }
.brand-name { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:1.12rem; font-weight:700; letter-spacing:-.01em; color:var(--ink); }
.brand-name span { color:var(--green); }
.brand-sub { color: var(--muted); font-size:.72rem; margin-top:.16rem; letter-spacing:.01em; }
.header-meta { display:flex; align-items:center; gap:.55rem; }
.header-chip { display:flex; flex-direction:column; gap:.1rem; border:1px solid var(--line); background:rgba(255,255,255,.8);
  border-radius:12px; padding:.42rem .7rem; box-shadow:0 2px 8px rgba(23,33,61,.04); }
.header-chip small { font-family:'Roboto Mono','Courier New',monospace; font-size:.56rem; text-transform:uppercase; letter-spacing:.14em; color:var(--muted); }
.header-chip b { font-size:.74rem; font-weight:700; color:var(--ink); white-space:nowrap; }
.live-pill { display:flex; align-items:center; gap:.42rem; border:1px solid #cbd5ff; color:var(--green-dark); background:rgba(255,255,255,.85);
  border-radius:999px; padding:.5rem .82rem; font-weight:700; font-size:.76rem; box-shadow:0 3px 10px rgba(49,85,212,.06); white-space:nowrap; }
.live-dot { width:8px; height:8px; background:#5274e6; border-radius:50%; box-shadow:0 0 0 4px #dbe2ff; animation:live-pulse 2.2s ease-in-out infinite; }
@keyframes live-pulse { 0%,100% { box-shadow:0 0 0 4px #dbe2ff; } 50% { box-shadow:0 0 0 7px rgba(219,226,255,.35); } }
@media (prefers-reduced-motion: reduce) { .live-dot { animation:none; } }

.eyebrow { font-family:'Roboto Mono','Courier New',monospace; font-size:.62rem; text-transform:uppercase; letter-spacing:.16em; color:var(--green); font-weight:500; margin: .55rem 0 .45rem; }
.page-intro { padding: .15rem 0 .2rem; }
.page-title { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:2.05rem; line-height:1.15; letter-spacing:-.015em; font-weight:600; margin:0; color:var(--ink); }
.page-lede { color:var(--muted); font-size:.92rem; line-height:1.62; max-width:680px; margin:.6rem 0 1.15rem; }
.section-title { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:1rem; font-weight:600; letter-spacing:-.005em; margin:0; }
.section-note { color:var(--muted); font-size:.75rem; margin:.25rem 0 .9rem; }
.section-head { display:flex; justify-content:space-between; align-items:flex-end; margin: 1.55rem 0 .75rem; }
.mono { font-family:'Roboto Mono','Courier New',monospace; }

.filter-shell { background:linear-gradient(135deg, #f0f3ff, #e9edfb); border:1px solid #d5dcf2; border-radius:15px; padding:.85rem 1rem .18rem; margin:.55rem 0 1.25rem; box-shadow:0 5px 18px rgba(37,56,110,.05); }
.filter-label { font-family:'Roboto Mono','Courier New',monospace; text-transform:uppercase; letter-spacing:.12em; color:var(--green-dark); font-size:.62rem; margin-bottom:.25rem; font-weight:500; }
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label { color:var(--muted); font-size:.72rem; font-weight:600; }
[data-testid="stSelectbox"] > div > div { background:#fff; border-color:#d5dcef; border-radius:10px; min-height:40px; box-shadow:0 2px 8px rgba(37,56,110,.045); }

.metric-card { background:var(--card); border:1px solid var(--line); border-radius:17px; padding:1.1rem 1.12rem 1rem; min-height:136px; box-shadow:0 7px 22px rgba(37,56,110,.055); transition:transform .18s ease, box-shadow .18s ease; }
.metric-card:hover { transform:translateY(-2px); box-shadow:0 12px 28px rgba(37,56,110,.11); }
.metric-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:.55rem; }
.metric-label { color:var(--muted); font-size:.73rem; font-weight:600; line-height:1.3; }
.metric-icon { width:29px; height:29px; border-radius:9px; display:flex; align-items:center; justify-content:center; font-size:.92rem; }
.metric-value { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:1.62rem; letter-spacing:-.01em; font-weight:600; font-variant-numeric:tabular-nums; }
.metric-foot { color:var(--muted); font-size:.68rem; margin-top:.3rem; line-height:1.35; }
.metric-card.green .metric-icon { background:#e8edff; color:var(--green); }
.metric-card.green .metric-value { color:var(--green-dark); }
.metric-card.orange .metric-icon { background:#fff0e5; color:var(--orange); }
.metric-card.orange .metric-value { color:#a95724; }
.metric-card.yellow .metric-icon { background:#fff6d8; color:#9d7a0d; }
.metric-card.yellow .metric-value { color:#8c6c06; }
.metric-card.rose .metric-icon { background:#ffeaed; color:var(--rose); }
.metric-card.rose .metric-value { color:#ac4044; }

.chart-card { background:var(--card); border:1px solid var(--line); border-radius:17px; padding:1.05rem 1.08rem .78rem; box-shadow:0 6px 22px rgba(37,56,110,.045); }
.chart-card .stPlotlyChart { margin-top:.35rem; }
.insight-card { border-radius:16px; padding:1.05rem 1.15rem; background:var(--green-dark); color:white; min-height:128px; }
.insight-kicker { color:#b7c6ff; font-family:'Roboto Mono','Courier New',monospace; text-transform:uppercase; letter-spacing:.14em; font-size:.6rem; }
.insight-text { font-family:'Roboto', Arial, Verdana, sans-serif; font-size:1.02rem; font-weight:600; line-height:1.38; margin-top:.45rem; }
.insight-foot { color:#d7defb; font-size:.7rem; line-height:1.4; margin-top:.55rem; }

.callout { border:1px solid #d1dafa; border-left:3px solid var(--green); background:#f0f3ff; border-radius:0 12px 12px 0; padding:.88rem 1rem; color:#354263; font-size:.82rem; line-height:1.55; }
.callout strong { color:var(--green-dark); }
.tag { display:inline-block; padding:.25rem .5rem; border-radius:999px; background:#eef1fb; color:var(--green-dark); font-size:.67rem; font-weight:600; margin-right:.3rem; }
.legend-row { display:flex; gap:1rem; flex-wrap:wrap; color:var(--muted); font-size:.7rem; margin:.2rem 0 .5rem; }
.legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:.28rem; }

.profile-panel { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1.15rem 1.2rem; }
.profile-row { display:flex; align-items:center; gap:.75rem; margin:.78rem 0; }
.profile-name { width:148px; font-size:.76rem; color:var(--muted); }
.profile-track { flex:1; height:9px; background:#e9edf7; border-radius:99px; overflow:hidden; }
.profile-fill { height:100%; border-radius:99px; background:linear-gradient(90deg, #3155d4, #8ca4f0); }
.profile-number { width:48px; text-align:right; font-family:'Roboto Mono','Courier New',monospace; font-size:.7rem; color:var(--green-dark); }

.stDataFrame { border:1px solid var(--line); border-radius:13px; overflow:hidden; box-shadow:0 4px 16px rgba(37,56,110,.035); }
[data-testid="stDataFrame"] { background:#fff; }
div[data-testid="stExpander"] { border-color:var(--line); border-radius:12px; background:#fff; }
.download-row { display:flex; justify-content:flex-end; margin-top:.45rem; }
button[kind="secondary"] { border-radius:9px; border-color:#cbd5ee; color:var(--green-dark); font-weight:600; }

.footer-note { color:#5f6866; font-size:.7rem; padding-top:1.7rem; border-top:1px solid var(--line); margin-top:2.5rem; line-height:1.5; }
button, [role="button"] { font-family:'Inter', 'Segoe UI', system-ui, Arial, sans-serif; }
/* Fixed positioning keeps the floating panel out of page flow, so charts,
   tables, the sidebar and the Streamlit toolbar are never pushed or hidden. */
/* Mobile navigation Menu pill — a fixed control shown only on phones, where the
   rail becomes a drawer. On desktop the element is removed from flow entirely. */
.st-key-mobile_menu_open { display:none; }
.st-key-ask_launcher { position: fixed; right: 1.4rem; bottom: 1.35rem; z-index: 1000; width: auto; }
.st-key-ask_launcher button {
  position: relative; border-radius: 999px; border: 1px solid #2443b8;
  background: #3155d4; color: #fff; font-weight: 700; font-size: .84rem;
  padding: .68rem 1.15rem; box-shadow: 0 12px 28px rgba(23,37,84,.26);
  transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
}
.st-key-ask_launcher button:hover { background: #2443b8; color: #fff; transform: translateY(-2px);
  box-shadow: 0 16px 34px rgba(23,37,84,.3); }
.st-key-ask_launcher button::after { content: ''; position: absolute; top: 7px; right: 9px;
  width: 8px; height: 8px; border-radius: 50%; background: var(--orange);
  box-shadow: 0 0 0 2px rgba(255,255,255,.85); }
.st-key-ask_launcher button:focus-visible { outline: 3px solid var(--orange) !important; outline-offset: 3px; }

.st-key-ask_panel {
  position: fixed; right: 1.4rem; bottom: 5.35rem; z-index: 1001;
  width: min(398px, calc(100vw - 2.8rem));
  /* Keep the panel's top edge below the page header on short viewports too. */
  max-height: min(calc(100vh - 14.5rem), 660px); overflow-y: auto; overflow-x: hidden;
  background: var(--card); border: 1px solid var(--line); border-radius: 18px;
  box-shadow: 0 24px 60px rgba(23,37,84,.24); padding: .85rem .9rem 1rem;
  animation: ask-in .18s ease-out both;
}
@keyframes ask-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .st-key-ask_panel { animation: none; } }
/* Notifications (top-right, transient) always draw above the assistant panel. */
[data-testid="stToastContainer"] { z-index: 1200 !important; }
.st-key-ask_panel > div { max-width: 100%; }
.st-key-ask_panel [data-testid="stVerticalBlockBorderWrapper"] { row-gap: .5rem; }
.ask-head { display: flex; gap: .55rem; align-items: flex-start; padding-right: 4.9rem; }
.ask-mark { width: 42px; height: 42px; flex: none; border-radius: 10px; }
.ask-title { font-weight: 800; font-size: .92rem; color: var(--ink); line-height: 1.3; }
.ask-subtitle { font-size: .72rem; color: var(--muted); line-height: 1.4; margin-top: .1rem; }
.st-key-ask_close { position: absolute; top: .55rem; right: .6rem; z-index: 2; width: auto; }
.st-key-ask_close button { color: var(--muted); font-size: .7rem; font-weight: 600;
  padding: .26rem .42rem; border: 1px solid var(--line); border-radius: 8px;
  background: rgba(255,255,255,.92); }
.st-key-ask_close button:hover { color: var(--ink); background: var(--paper); }
.ask-badge { font-size: .65rem; line-height: 1.45; color: #3f4a66; background: #eef3ff;
  border: 1px solid #d5defb; border-radius: 9px; padding: .4rem .55rem; }
.st-key-ask_history_zone { border: 1px solid var(--line); border-radius: 12px; background: #fbfcff;
  padding: .55rem .6rem; overflow-anchor: none; }
.st-key-ask_history_zone button[kind="secondary"] { font-size: .72rem; font-weight: 600;
  justify-content: flex-start; text-align: left; line-height: 1.35; padding: .42rem .55rem; border-radius: 9px; }
.ask-empty { margin: .15rem 0 .5rem; }
.ask-empty-title { font-weight: 700; font-size: .82rem; color: var(--ink); }
.ask-empty-copy { font-size: .72rem; color: var(--muted); line-height: 1.45; margin-top: .2rem; }
.ask-intro { font-size: .74rem; color: var(--muted); margin: 0 0 .6rem; }
.ask-q { background: var(--paper); border: 1px solid var(--line); border-radius: 10px 10px 3px 10px;
  padding: .55rem .7rem; font-size: .84rem; max-width: 92%; word-wrap: break-word; }
.ask-switch { background: #faf6ea; border: 1px dashed #cbbf8f; border-radius: 8px; padding: .45rem .65rem;
  font-size: .75rem; color: #63593a; }
.ask-state { font-size: .7rem; color: var(--muted); }
.ask-foot { font-size: .64rem; color: var(--muted); line-height: 1.4; padding-top: .15rem; }

/* Accessibility: a clearly visible keyboard-focus indicator in both color zones.
   The blue works on the light surface; the dark sidebar rail needs the mint accent instead. */
a:focus-visible, button:focus-visible, [role="button"]:focus-visible, [role="radio"]:focus-visible,
[role="option"]:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible,
summary:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--green) !important; outline-offset: 2px; }
[data-testid="stSidebar"] button:focus-visible, [data-testid="stSidebar"] input:focus-visible, [data-testid="stSidebar"] [data-testid="stSelectbox"]:focus-within { outline-color: #059669 !important; }
@media (max-width: 1100px) { .block-container { padding-left:1.5rem; padding-right:1.5rem; } }
@media (max-width: 900px) {
  .block-container { padding: .8rem 1rem 6rem; }
  .page-title { font-size:1.95rem; }
  /* Keep the live status pill at the masthead; drop only the two info chips */
  .header-chip { display:none; }
  .app-header { padding:.85rem 1.05rem; }
  .stRadio label { padding:.42rem .48rem; font-size:.73rem; }
  .metric-card { min-height:122px; }
  /* Filter bar flows two selectboxes per row instead of four cramped ones */
  .filter-shell [data-testid="stColumn"] { flex:1 1 46% !important; width:46% !important; }
  .st-key-ask_launcher { right: 1.1rem; bottom: 1.1rem; }
  .st-key-ask_panel { right: 1.1rem; bottom: 5rem; max-height: min(calc(100vh - 13rem), 640px); }
}
/* Small-screen refinement: shared layout + Overview (phones, 360–640px) */
@media (max-width: 640px) {
  /* The top strip hosts Streamlit's auto-collapse *expand* control; keep page content clear of it */
  .block-container { padding: 4.55rem .85rem 6rem; }
  .app-header { flex-wrap: wrap; align-items:flex-start; gap:.65rem; padding:.85rem .95rem; border-radius:15px; }
  .brand-mark { width:44px; height:44px; }
  .brand-mark::after { inset:-4px; }
  .brand-name { font-size:1.02rem; }
  .page-title { font-size:1.52rem; }
  .page-lede { font-size:.86rem; margin:.45rem 0 1rem; }
  .brand-sub { font-size:.66rem; }
  .metric-card { padding:.9rem .85rem .85rem; min-height:116px; }
  .metric-value { font-size:1.38rem; }
  .metric-foot { font-size:.67rem; }
  .filter-shell { padding:.7rem .7rem .1rem; }
  /* Every main-area column pair stacks full-width so charts and cards are readable.
     Sidebar columns are exempted so the rail's brand + toggle row stays on one line. */
  [data-testid="stAppViewContainer"] [data-testid="stColumn"] { flex:0 0 100% !important; width:100% !important; }
  [data-testid="stAppViewContainer"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap; row-gap:.65rem; }
  [data-testid="stSidebar"] [data-testid="stColumn"] { flex:0 0 auto !important; width:auto !important; }
  .insight-card { min-height:auto; padding:.9rem 1rem; }
  .insight-text { font-size:.92rem; }
  .chart-card { padding:.9rem .9rem .7rem; }
  .callout { font-size:.76rem; padding:.75rem .85rem; }
  .side-card { font-size:.64rem; }
  /* Phones: the rail is a hidden drawer, not a squeezed column. A Menu pill
     (fixed in the toolbar strip) opens it; the rail's own toggle or picking a
     page closes it. Streamlit's mobile auto-collapse also leaks its native
     header items (expand arrow, default logo) into the toolbar strip — the
     whole native strip is removed so the branded pill is the only control. */
  header[data-testid="stHeader"] { display:none !important; }
  [data-testid="stSidebar"] { display:none !important; }
  .st-key-mobile_menu_open { display:block !important; position:fixed; top:.55rem; left:.75rem; z-index:1000; width:auto; }
  .st-key-mobile_menu_open button { border-radius:999px; border:1px solid #bfe6cf; background:#fff; color:#14532d;
    font-weight:700; font-size:.78rem; padding:.5rem .85rem; box-shadow:0 4px 14px rgba(23,33,61,.18); gap:.3rem; }
  .st-key-mobile_menu_open button svg { fill:#059669; }
  .st-key-mobile_menu_open button:hover { background:#f2faf5; border-color:#aaddc2; }
  .st-key-ask_launcher { right: .9rem; bottom: .9rem; }
  .st-key-ask_launcher button { font-size: .8rem; padding: .62rem .95rem; }
  /* On phones the header wraps; anchor the panel below it rather than letting
     a bottom-anchored max-height creep up over the brand row. */
  .st-key-ask_panel { left: .6rem; right: .6rem; top: 16.5rem; bottom: 4.85rem; width: auto;
    max-height: none; border-radius: 16px; }
  .ask-head { padding-right: 4.4rem; }
  .ask-title { font-size: .88rem; }
  .ask-subtitle { font-size: .7rem; }
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Inspecting source metadata…")
def load_source_profile(path: str) -> SourceProfile:
    return build_source_profile(path, analytical_variables=len(PIPELINE_COLUMNS))

def weighted_rate(frame: pd.DataFrame, values: pd.Series, weights: str = "hh_wt") -> float:
    if weights not in frame:
        return float("nan")
    valid = values.notna() & frame[weights].notna() & frame[weights].gt(0) & np.isfinite(frame[weights])
    if valid.sum() == 0:
        return float("nan")
    return float(np.average(values[valid], weights=frame.loc[valid, weights]))


def weighted_coverage(frame: pd.DataFrame, valid_values: pd.Series, weights: str = "hh_wt") -> float:
    """Weighted share of rows covered by a supplied validity mask."""

    if weights not in frame:
        return float("nan")
    valid_weights = frame[weights].notna() & frame[weights].gt(0) & np.isfinite(frame[weights])
    if valid_weights.sum() == 0:
        return float("nan")
    mask = valid_values.fillna(False).astype(bool) & valid_weights
    return float(frame.loc[mask, weights].sum() / frame.loc[valid_weights, weights].sum())


def pct(value: float, decimals: int = 0) -> str:
    return "—" if pd.isna(value) else f"{value * 100:.{decimals}f}%"


# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def logo_data_uri() -> str:
    """Inline data URI for the system logo; embedded once, encoded per process."""

    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def app_header() -> None:
    st.markdown(
        f"""
        <div class="app-header">
          <div class="brand">
            <div class="brand-mark"><img src="{logo_data_uri()}" alt="InsightRwanda logo"></div>
            <div><div class="brand-name">Insight<span>Rwanda</span></div><div class="brand-sub">Financial inclusion &amp; poverty research · NISR Hackathon 2026</div></div>
          </div>
          <div class="header-meta">
            <div class="header-chip"><small>Survey</small><b>FinScope · 2024 &amp; 2020</b></div>
            <div class="header-chip"><small>Scope</small><b>National coverage</b></div>
            <div class="live-pill"><span class="live-dot"></span> Live analysis</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Mobile navigation: the fixed Menu pill sits in the toolbar strip on phones,
    # where the rail is a hidden drawer (see the phone media query in CSS above).
    # The pill styles the *button's* key wrapper, not a container: a fixed
    # container collapses to zero width (its inner block is width:100%).
    st.button(
        "Menu",
        key="mobile_menu_open",
        icon=":material/menu:",
        on_click=_open_mobile_menu,
        help="Open the navigation drawer",
    )

NAV_ICONS = {
    "Overview": ":material/dashboard:",
    "Financial inclusion": ":material/account_balance:",
    "Poverty insights": ":material/trending_down:",
    "Geographic insights": ":material/map:",
    "Resilience lab": ":material/shield:",
    "Predictive insights": ":material/query_stats:",
    "Data quality": ":material/fact_check:",
    "Data explorer": ":material/table_view:",
    "Methods & sources": ":material/menu_book:",
    "About the build": ":material/info:",
}


def _open_mobile_menu() -> None:
    st.session_state["mobile_drawer_open"] = True


def _toggle_sidebar() -> None:
    if st.session_state.pop("mobile_drawer_open", False):
        # First press with the phone drawer open only closes the drawer;
        # the desktop rail's collapsed state is left untouched.
        return
    st.session_state["sidebar_collapsed"] = not st.session_state.get("sidebar_collapsed", False)


# Icon-only rail: labels, selectors and captions hidden, icons centred.
COLLAPSED_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"] { min-width:78px !important; max-width:78px !important; }
[data-testid="stSidebar"] > div:first-child { padding:1.15rem .5rem 1.2rem; }
[data-testid="stSidebar"] .stButton { margin:.3rem 0; }
[data-testid="stSidebar"] .stButton button p { display:none !important; }
[data-testid="stSidebar"] .stButton button { justify-content:center !important; padding:.62rem .3rem; }
[data-testid="stSidebar"] .side-caption, [data-testid="stSidebar"] .side-label, [data-testid="stSidebar"] .side-card,
[data-testid="stSidebar"] [data-testid="stSelectbox"], .st-key-side_profile { display:none !important; }
/* Brand row: mark and the toggle stack vertically and centre in the narrow rail */
[data-testid="stSidebar"] .side-brand { justify-content:center; gap:0;
  border-bottom:none; border-top:none; padding-bottom:.35rem; }
[data-testid="stSidebar"] .side-brand div:nth-child(2) { display:none; }
[data-testid="stSidebar"] [data-testid="stColumn"] { flex:0 0 100% !important; width:100% !important; }
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap; row-gap:0; }
.st-key-side_actions .stButton button { padding:.62rem .3rem; }
</style>
"""


# Phones-only drawer: while the Menu pill is armed, the rail renders as a fixed
# overlay column over the page. Everything is !important because Streamlit's
# resizable handle writes inline position/width/height styles on the rail, and
# inline styles beat plain stylesheet declarations. The markdown is injected in
# the main flow (not the sidebar) so this sheet lands AFTER the base CSS in
# document order — the base phone rule hides the rail with the same !important,
# and cascade order between equally-important rules is document order.
MOBILE_DRAWER_CSS = """
<style>
@media (max-width: 640px) {
  [data-testid="stSidebar"] { display:flex !important; position:fixed !important; left:0 !important; top:0 !important;
    bottom:0 !important; width:min(310px, 86vw) !important; min-width:250px !important; max-width:86vw !important;
    height:100dvh !important; z-index:1001 !important;
    overflow-y:auto !important; overscroll-behavior:contain !important; margin:0 !important; transform:none !important;
    visibility:visible !important; opacity:1 !important;
    box-shadow:6px 0 26px rgba(23,33,61,.28), 0 0 0 1px #d8e8dd; }
}
</style>
"""


def _reset_filter(key: str, default: str) -> None:
    st.session_state[key] = default


@st.dialog("Account & data access")
def account_dialog(profile: SourceProfile) -> None:
    st.markdown(
        """
        **Workspace** — InsightRwanda research viewer (offline; no sign-in required).

        **Role** — read-only analysis. You can filter, explore and ask questions about the evidence,
        but the underlying survey records are never modified or exported raw.

        **Where numbers come from** — see *Methods & sources* for provenance and *Data quality*
        for the checks run before any number is shown.
        """
    )


@st.dialog("Assistant history")
def reset_assistant_dialog() -> None:
    st.markdown("This clears the conversation history of the offline evidence assistant. Filters and page choices are kept.")
    if st.button("Clear conversation", key="confirm_clear_ask", icon=":material/delete:", type="primary"):
        st.session_state["ask_messages"] = []
        st.session_state["ask_input"] = ""
        st.rerun()


def nav(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> str:
    """Left rail: brand + collapse toggle, survey-year scope, three labelled nav
    groups with outline icons, a primary action pinned near the bottom, and the
    profile section with its account menu."""
    nav_pages = [
        "Overview", "Financial inclusion", "Poverty insights", "Geographic insights",
        "Resilience lab", "Predictive insights", "Data quality", "Data explorer",
        "Methods & sources", "About the build",
    ]
    nav_groups = [
        ("", nav_pages[:6], ""),
        ("Governance", nav_pages[6:8], "Checks, access and data protection"),
        ("How it is built", nav_pages[8:], "Methods, sources and background"),
    ]
    numbers = {page: f"{index:02d}" for index, page in enumerate(nav_pages, start=1)}
    current = st.session_state.get("workspace_nav", "Overview")
    if current not in nav_pages:
        current = "Overview"
    with st.sidebar:
        collapsed = st.session_state.get("sidebar_collapsed", False)
        if collapsed:
            st.markdown(COLLAPSED_SIDEBAR_CSS, unsafe_allow_html=True)
        brand_cols = st.columns([1, .22], gap="small", vertical_alignment="center")
        with brand_cols[0]:
            st.markdown(
                f'<div class="side-brand"><div class="side-mark"><img src="{logo_data_uri()}" alt="InsightRwanda logo"></div>'
                '<div><div class="side-name">InsightRwanda</div><div class="side-caption">Research analytics platform</div></div></div>',
                unsafe_allow_html=True,
            )
        with brand_cols[1]:
            st.button(
                "",
                key="sidebar_collapse",
                icon=":material/menu_open:" if collapsed else ":material/menu:",
                on_click=_toggle_sidebar,
                help="Collapse or expand the sidebar",
            )
        st.selectbox(
            "Survey year",
            list(YEAR_OPTIONS),
            key="survey_year",
            help="Choose which survey wave the whole dashboard shows: 2020, 2024, or both together.",
            label_visibility="collapsed",
        )
        for group_label, group_pages, group_hint in nav_groups:
            if group_label:
                st.markdown(f'<div class="side-label">{group_label}</div>', unsafe_allow_html=True)
            if group_hint:
                st.markdown(f'<div class="side-caption">{group_hint}</div>', unsafe_allow_html=True)
            for page in group_pages:
                pressed = st.button(
                    f"{numbers[page]} · {page}",
                    key=f"nav_{numbers[page]}",
                    icon=NAV_ICONS[page],
                    type="primary" if page == current else "secondary",
                    width="stretch",
                )
                if pressed:
                    current = page
                    st.session_state["workspace_nav"] = page
                    st.session_state["mobile_drawer_open"] = False
        st.markdown(
            '<div class="side-card"><div class="side-card-title">Pages at a glance</div><div class="side-card-copy">'
            "01 Overview — headline numbers for all of Rwanda<br>"
            "02 Financial inclusion — the six verified measures<br>"
            "03 Poverty insights — what the data can and cannot say<br>"
            "04 Geographic insights — province and district comparisons<br>"
            "05 Resilience lab — who can absorb a financial shock<br>"
            "06 Predictive insights — a test model, with its limits<br>"
            "07 Data quality — checks run before numbers are shown<br>"
            "08 Data explorer — build your own summary tables<br>"
            "09 Methods &amp; sources — where each number comes from<br>"
            "10 About the build — purpose and honesty notes</div></div>",
            unsafe_allow_html=True,
        )
        with st.container(key="side_actions"):
            if st.button(
                "Ask InsightRwanda",
                key="side_ask",
                icon=":material/forum:",
                type="primary",
                width="stretch",
                help="Ask questions about the survey evidence in simple English",
            ):
                ask_insightrwanda_modal(df, profile, checks)
        with st.container(key="side_profile"):
            with st.popover("Research viewer", icon=":material/account_circle:", width="stretch"):
                st.caption("Offline workspace · no sign-in required")
                if st.button("Account & data access", key="profile_account", icon=":material/badge:", width="stretch"):
                    account_dialog(profile)
                if st.button("Clear assistant history", key="profile_clear_ask", icon=":material/delete:", width="stretch"):
                    reset_assistant_dialog()
                if st.button("Go to About the build", key="profile_about", icon=":material/info:", width="stretch"):
                    st.session_state["workspace_nav"] = "About the build"
    return current


def page_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="page-intro"><div class="eyebrow">{eyebrow}</div><h1 class="page-title">{title}</h1><p class="page-lede">{lede}</p></div>', unsafe_allow_html=True)


def filter_bar(df: pd.DataFrame, key_prefix: str = "main") -> pd.DataFrame:
    st.markdown('<div class="filter-shell"><div class="filter-label">Narrow the results</div><div class="section-note" style="margin:-.15rem 0 .45rem">Pick one area or group of people; every chart on this page updates to match. The survey year is chosen in the left sidebar and applies everywhere.</div>', unsafe_allow_html=True)
    sk = key_prefix
    c1, c2, c3, c4 = st.columns([1.05, 1.2, .9, .9])
    province_options = ["All provinces"] + sorted(df["province"].dropna().unique().tolist())
    province = c1.selectbox("Province", province_options, key=f"{sk}_province")
    pre = df if province == "All provinces" else df[df["province"].eq(province)]
    district_options = ["All districts"] + sorted(pre["district"].dropna().unique().tolist())
    district = c2.selectbox("District", district_options, key=f"{sk}_district")
    setting = c3.selectbox("Setting", ["All settings", "Urban", "Rural"], key=f"{sk}_setting")
    sex = c4.selectbox("Respondent sex", ["All respondents", "Female", "Male"], key=f"{sk}_sex")
    filtered = pipeline_filter_analysis_data(
        pre,
        district=None if district == "All districts" else district,
        setting=None if setting == "All settings" else setting,
        respondent_sex=None if sex == "All respondents" else sex,
    )
    defaults = {
        f"{sk}_province": "All provinces",
        f"{sk}_district": "All districts",
        f"{sk}_setting": "All settings",
        f"{sk}_sex": "All respondents",
    }
    chips = []
    if province != defaults[f"{sk}_province"]:
        chips.append(("Province", province, f"{sk}_province"))
    if district != defaults[f"{sk}_district"]:
        chips.append(("District", district, f"{sk}_district"))
    if setting != defaults[f"{sk}_setting"]:
        chips.append(("Setting", setting, f"{sk}_setting"))
    if sex != defaults[f"{sk}_sex"]:
        chips.append(("Respondent", sex, f"{sk}_sex"))
    if chips:
        with st.container(key="filter_chips"):
            chip_cols = st.columns(len(chips) + 1, gap="small")
            for index, (chip_label, chip_value, chip_key) in enumerate(chips):
                with chip_cols[index]:
                    st.button(
                        f"{chip_label}: {chip_value}",
                        key=f"{sk}_chip_{index}",
                        icon=":material/close:",
                        on_click=_reset_filter,
                        args=(chip_key, defaults[chip_key]),
                        help="Remove this filter",
                    )
            with chip_cols[-1]:
                st.button(
                    "Clear all filters",
                    key=f"{sk}_chip_clear",
                    icon=":material/filter_alt_off:",
                    on_click=lambda keys=chips: [_reset_filter(key, defaults[key]) for _label, _v, key in keys],
                )
    st.markdown('</div>', unsafe_allow_html=True)
    return filtered


def has_data(frame: pd.DataFrame) -> bool:
    if frame.empty:
        st.warning(
            "No records match the filters you chose.\n\n"
            "Widen one filter at a time: set the year filter (left sidebar) back to *All years* and **Province** back to *All provinces*, "
            "then adjust **District**, **Setting** and **Respondent sex** until records appear."
        )
        return False
    return True


def metric_card(label: str, value: str, foot: str, icon: str, color: str = "green", delay: int = 0) -> None:
    delay_attr = f' data-delay="{delay}"' if delay else ""
    st.markdown(
        f'<div class="metric-card {color}"{delay_attr}><div class="metric-top"><div class="metric-label">{label}</div><div class="metric-icon">{icon}</div></div><div class="metric-value">{value}</div><div class="metric-foot">{foot}</div></div>',
        unsafe_allow_html=True,
    )


def section_head(title: str, note: str = "") -> None:
    st.markdown(f'<div class="section-head"><div><div class="section-title">{title}</div><div class="section-note">{note}</div></div></div>', unsafe_allow_html=True)


def chart_theme(fig: go.Figure, height: int = 300, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=8, t=12, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Roboto, Arial, Verdana, sans-serif", color="#66718b", size=11),
        showlegend=legend,
        legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="#17213d", font_size=12, font_family="Roboto"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#dce3ef", tickfont=dict(size=10))
    fig.update_yaxes(showgrid=True, gridcolor="#e8ecf5", zeroline=False, linecolor="rgba(0,0,0,0)", tickfont=dict(size=10))
    return fig


def weighted_group(frame: pd.DataFrame, group: str, measure: str) -> pd.DataFrame:
    rows = []
    for name, subset in frame.groupby(group, dropna=False):
        values = subset[measure]
        valid = values.notna() & subset["hh_wt"].notna() & subset["hh_wt"].gt(0) & np.isfinite(subset["hh_wt"])
        rows.append({
            "group": name,
            "value": weighted_rate(subset, values),
            "numerator_n": int((values.eq(1) & valid).sum()),
            "denominator_n": int(valid.sum()),
        })
    return pd.DataFrame(rows, columns=["group", "value", "numerator_n", "denominator_n"]).sort_values("value", ascending=False)


def weighted_distribution(frame: pd.DataFrame, category: str) -> pd.Series:
    valid = frame[category].notna() & frame["hh_wt"].notna() & frame["hh_wt"].gt(0) & np.isfinite(frame["hh_wt"])
    if valid.sum() == 0:
        return pd.Series(dtype=float)
    return frame.loc[valid].groupby(category)["hh_wt"].sum()


def band_flag(frame: pd.DataFrame, band: str) -> pd.Series:
    """0/1 flag for a resilience band over scored rows only.

    Rows whose band is missing or 'Unknown' (any lens component unobserved —
    the SPSS wave carries only one of the four) are excluded from the
    denominator instead of being counted as not-in-band.
    """

    values = frame["resilience_band"]
    return values.eq(band).astype(float).mask(values.isna() | values.eq("Unknown"))


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="Fitting candidate models…")
def evaluate_model_workload(view: pd.DataFrame) -> ModelRecord | None:
    """Run the full candidate evaluation for the current lens and cache the record."""

    try:
        return train_final_model(view)
    except ValueError:
        return None


def render_model_evaluation_tab(view: pd.DataFrame) -> None:
    """Train & predict: real candidate evaluation, selected-model readout, prediction form."""

    section_head("Train a prioritisation model", "Predict the Priority resilience band from features that do not define it")
    st.caption(
        "One complete end-to-end workflow is fitted on the current filtered view: a majority-class baseline "
        "is compared with logistic regression, a decision tree and a gradient-boosted ensemble under "
        "group-stratified 5-fold cross-validation with the survey weight attached to every metric. "
        "This is a predictive association over resampled rows — no survey-design standard error and no causal claim; it must never be used as an eligibility decision on its own."
    )

    record = evaluate_model_workload(view)
    if record is None:
        st.info("This filtered view does not contain both classes with usable weights, so no honest model can be fitted here.")
        return

    left, right = st.columns([1.15, .85])
    with left:
        st.markdown('<div class="section-title">Candidate comparison, cross-validated</div><div class="section-note">5-fold group-stratified CV · weighted F1 and ROC-AUC · mean ± sd</div>', unsafe_allow_html=True)
        st.dataframe(record.fold_metrics_table, hide_index=True, width="stretch", height=150)
    with right:
        m = record.metrics
        metric_left, metric_right = st.columns(2)
        with metric_left:
            st.metric("Selected model", record.model_name)
            st.metric("Holdout weighted F1", f"{m['weighted_f1']:.3f}")
            st.metric("Holdout ROC-AUC", f"{m['roc_auc']:.3f}")
        with metric_right:
            st.metric("Base rate (weighted)", f"{m['base_rate']:.1%}")
            st.metric("Holdout precision / recall", f"{m['weighted_precision']:.3f} / {m['weighted_recall']:.3f}")
            st.metric("Brier score", f"{m['brier']:.3f}")

    top_feature = max(record.permutation_importance.items(), key=lambda item: abs(item[1])) if record.permutation_importance else None
    section_head("What the model can—and cannot—add", "A ranking aid for follow-up, not a poverty or eligibility decision")
    if top_feature is not None:
        st.markdown(
            f'<div class="callout"><strong>Observed Priority share: {m["base_rate"]:.1%}; held-out ROC-AUC: {m["roc_auc"]:.3f}.</strong> '
            f"The largest held-out permutation signal is {top_feature[0]} (AUC change {top_feature[1]:+.3f}). "
            "This tells us how well the available variables rank the observed resilience band in this sample; it does not prove that the feature causes vulnerability, forecast future poverty, or justify automatic programme decisions.</div>",
            unsafe_allow_html=True,
        )

    imp_left, imp_right = st.columns([1.1, .9])
    with imp_left:
        st.markdown('<div class="section-title">What drives the prediction</div><div class="section-note">Permutation importance on the held-out fold (AUC drop when a feature is shuffled)</div>', unsafe_allow_html=True)
        importance = pd.DataFrame({
            "Feature": list(record.permutation_importance),
            "AUC drop": [f"{v:+.4f}" for v in record.permutation_importance.values()],
        })
        fig = go.Figure(go.Bar(y=importance["Feature"], x=[float(v[1:]) for v in importance["AUC drop"]], orientation="h", marker_color="#3155d4", hovertemplate="%{y}: %{x:.4f}<extra></extra>"))
        fig.update_xaxes(tickformat=".3f")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, min(380, 56 * len(importance) + 40)), width="stretch", config={"displayModeBar": False})
    with imp_right:
        st.markdown('<div class="section-title">Calibration on the held-out fold</div><div class="section-note">Predicted vs observed Priority share per probability quantile</div>', unsafe_allow_html=True)
        st.dataframe(record.calibration_table, hide_index=True, width="stretch", height=150)
        cm = record.confusion
        st.caption(
            f"Held-out fold: {record.n_test:,} records ({record.households_test:,} unique respondent keys), unweighted confusion counts "
            f"TP {cm['tp']} · FP {cm['fp']} · TN {cm['tn']} · FN {cm['fn']}. {record.importances_note if (importance_note := getattr(record, 'importances_note', None)) else 'Permutation importance is a predictive association, not a causal effect.'}"
        )

    section_head("Predict one composed household", "Inputs missing below take the training-most-typical value for their variable")
    with st.form("priority_model_form"):
        input_left, input_right = st.columns(2)
        with input_left:
            household_size = st.number_input("Household size", min_value=1, max_value=30, value=4, step=1)
            respondent_sex = st.selectbox("Respondent sex", ["Female", "Male"])
            setting = st.selectbox("Setting", ["Rural", "Urban"])
        with input_right:
            internet_access = st.selectbox("Internet access", ["No", "Yes"])
            phone_ownership = st.selectbox("Phone ownership", ["No", "Yes"])
            mobile_money_use = st.selectbox("Mobile money use", ["No", "Yes"])
        train_and_predict = st.form_submit_button("Predict from the selected model", type="primary")

    if train_and_predict:
        prediction_values = {
            "hh_size": float(household_size),
            "b2": 2.0 if respondent_sex == "Female" else 1.0,
            "a6": 2.0 if setting == "Rural" else 1.0,
            "c14_5": 1.0 if internet_access == "Yes" else 2.0,
            "f3": 1.0 if phone_ownership == "Yes" else 2.0,
            "qf4_05": 1.0 if mobile_money_use == "Yes" else 2.0,
            "sex": respondent_sex,
            "setting": setting,
        }
        try:
            probability = predict_priority(record, prediction_values)
            st.metric("Predicted Priority-band probability", f"{probability:.1%}")
            st.caption(
                "An uncertain analytical estimate for a composed household, not a label about any existing household. "
                "The context variables not entered here are held at training-typical values."
            )
        except (ValueError, KeyError):
            st.error("Prediction could not be produced with the entered values. Check the "
                     "numbers and try again.")

    st.caption(
        f"Reproducibility: seed {record.config['seed']} · {record.config['n_splits']}-fold StratifiedGroupKFold on the respondent key · "
        f"positive class {record.config['positive_class']} · threshold {record.config['threshold']} · candidates {', '.join(record.config['candidates'])}. "
        f"Selection rule: {record.selection_rule} Target: {record.target_definition}."
    )


@st.cache_data(show_spinner="Scoring the held-out fold…")
def holdout_view(view: pd.DataFrame, record_name: str) -> pd.DataFrame:
    """Score the deterministic held-out fold (cached by lens, keyed off the record)."""

    record = evaluate_model_workload(view)
    if record is None or record.model_name != record_name:
        raise ValueError("Model record is not available for this view")
    return holdout_artifacts(view, record)


def render_threshold_tradeoff(view: pd.DataFrame, record: ModelRecord) -> None:
    """Precision/recall/F1 trade-off across decision thresholds + PR sweep."""

    section_head("Threshold trade-off", "What the model gains or loses as the Priority cutoff moves")
    st.caption(
        "The default operating threshold is 0.50. Lowering it catches more Priority households "
        "at the cost of more false alarms; raising it does the opposite. Metrics are survey-weighted "
        "on the same deterministic held-out fold."
    )
    table = holdout_view(view, record.model_name)
    curve = pr_curve(table)

    trade_left, trade_right = st.columns([1.1, .9])
    with trade_left:
        st.dataframe(threshold_metrics(table), hide_index=True, width="stretch", height=230)
        st.caption("Word of caution: pick the operating threshold from programme costs and capacity, not from the highest number alone.")
    with trade_right:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=curve["threshold"], y=curve["precision"], mode="lines+markers",
                                 name="Weighted precision", line=dict(color="#3155d4", width=3), hovertemplate="threshold %{x:.2f} · precision %{y:.2f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=curve["threshold"], y=curve["recall"], mode="lines+markers",
                                 name="Weighted recall", line=dict(color="#e5ae2f", width=3), hovertemplate="threshold %{x:.2f} · recall %{y:.2f}<extra></extra>"))
        fig.update_xaxes(tickformat=".1f", title=None)
        fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
        chart_theme(fig, 300, legend=True)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)


def render_subgroup_performance(view: pd.DataFrame, record: ModelRecord) -> None:
    """Held-out model quality by province / setting / respondent sex."""

    section_head("Subgroup model performance", "A model is only usable where it performs")
    st.caption(
        "Held-out metrics split by committee-relevant lenses. AUC is reported only where both "
        "classes are present in the subgroup; cells below 150 held-out records are flagged as "
        "low evidence. These are predictive associations on resampled rows, not subgroup effects."
    )
    table = holdout_view(view, record.model_name)
    dimension = st.selectbox(
        "Split by",
        (("Province", "province"), ("Setting", "setting"), ("Respondent sex", "sex")),
        format_func=lambda item: item[0],
        key="subgroup_dimension",
    )
    st.dataframe(subgroup_performance(table, dimension[1]), hide_index=True, width="stretch", height=280)


def render_predictive_insights(df: pd.DataFrame) -> None:
    """06 / Predictive insights: the full model readout as a first-class page."""

    page_intro(
        "06 / Predictive insights",
        "One honest predictive model, examined from every side.",
        "Candidate selection, the held-out scorecard, how the trade-off shifts with the decision threshold, and where the model performs or struggles across provinces and settings. A predictive association over resampled rows — never eligibility.",
    )
    view = filter_bar(df, "predictive")
    if not has_data(view):
        return
    if "resilience_band" not in view:
        st.markdown('<div class="callout"><strong>Not available on this wave.</strong><br>The predictive workflow trains against the resilience band, and the chosen wave does not include own-money, saving-behaviour or social-support answers. Choose the 2024 survey year in the left sidebar to run the model; nothing is imputed here.</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">The combined section below uses only outcomes that exist on both supplied files, so it runs whichever source is active.</div>', unsafe_allow_html=True)
        render_combined_prediction()
        return

    render_model_evaluation_tab(view)
    record = evaluate_model_workload(view)
    if record is None:
        return

    render_threshold_tradeoff(view, record)
    render_subgroup_performance(view, record)
    render_combined_prediction()


@st.dialog("Measure detail", width="large")
def measure_detail_dialog(view: pd.DataFrame, measure: str, label: str) -> None:
    """Click-through from a summary card: the measure broken down by province."""
    overall = weighted_rate(view, view[measure])
    st.markdown(f"**{label}: {pct(overall, 1)}** across the current lens.")
    breakdown = weighted_group(view, "province", measure)
    if breakdown.empty:
        st.info("No records match this measure in the current lens. Widen the filters and try again.")
        return
    st.dataframe(
        breakdown.assign(share=breakdown["value"].map(lambda v: pct(v, 1)))[["group", "share", "numerator_n", "denominator_n"]]
        .rename(columns={"group": "Province", "share": "Share", "numerator_n": "Yes (n)", "denominator_n": "Scored (n)"}),
        hide_index=True,
        width="stretch",
        height=min(420, 70 + 35 * len(breakdown)),
    )
    fig = go.Figure(go.Bar(x=breakdown["group"], y=breakdown["value"] * 100, marker_color="#3155d4", text=[f"{v * 100:.0f}%" for v in breakdown["value"]], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
    fig.update_xaxes(tickangle=-30)
    fig.update_yaxes(range=[0, 108], ticksuffix="%")
    st.plotly_chart(chart_theme(fig, 290), width="stretch", config={"displayModeBar": False})


def render_overview(df: pd.DataFrame) -> None:
    page_intro(
        "01 / National signal",
        "Where financial resilience is holding — and where it is not.",
        "A decision surface for Rwanda’s financial inclusion agenda. Use the lens below to move from the national picture to the households and places that need the most attention.",
    )
    view = filter_bar(df, "overview")
    if not has_data(view):
        return
    active = weighted_rate(view, view["active_access"])
    mobile = weighted_rate(view, view["mobile_money"])
    emergency = weighted_rate(view, view["emergency_fund"])
    pressure = weighted_rate(view, view["income_pressure"])

    # --- Summary cards: four equal statistic cards, each clickable to a detail view ---
    kpi_cards = [
        ("Active formal access", "active_access", pct(active), "Use a bank, SACCO or mobile-money service today · shows how far formal finance reaches", "↗", "green", 0),
        ("Mobile money", "mobile_money", pct(mobile), "Send or receive money by phone · shows today's main digital money route", "⌁", "green", 1),
        ("Emergency buffer", "emergency_fund", pct(emergency), "Have money saved for a surprise expense · shows who can absorb a shock without borrowing", "◌", "yellow", 2),
        ("Income pressure", "income_pressure", pct(pressure), "Income does not cover monthly living costs · shows who is under day-to-day strain", "!", "rose", 3),
    ]
    kpi_cols = st.columns(4)
    for col, (label, measure, value, foot, icon, color, delay) in zip(kpi_cols, kpi_cards):
        with col:
            metric_card(label, value, foot, icon, color, delay=delay)
            if st.button("Open detail", key=f"overview_detail_{measure}", icon=":material/arrow_outward:", width="stretch"):
                measure_detail_dialog(view, measure, label)
    st.markdown('<div class="legend-row">Each summary card opens a province detail view.</div>', unsafe_allow_html=True)

    # --- Chart row: vertical bar (left) and horizontal stacked bar (right) ---
    section_head("The national signal, at a glance", "Hover any bar or segment for exact values")
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Access is broad; buffers are thinner</div><div class="section-note">Share of respondents meeting each indicator</div>', unsafe_allow_html=True)
        labels_available = [("Active formal access", "active_access"), ("Mobile money", "mobile_money"), ("Own money", "owns_money"), ("Saves", "saves_regularly"), ("Emergency fund", "emergency_fund"), ("Internet access", "internet_access")]
        labels_available = [(label, m) for label, m in labels_available if m in view]
        labels = [label for label, _m in labels_available]
        measures = [m for _label, m in labels_available]
        values = [weighted_rate(view, view[m]) * 100 for m in measures]
        colors = ["#3155d4", "#0ea5e9", "#06b6d4", "#14b8a6", "#22c55e", "#16a34a"]
        fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors, text=[f"{x:.0f}%" for x in values], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
        fig.update_xaxes(tickangle=-28)
        fig.update_yaxes(range=[0, 108], ticksuffix="%", showgrid=True, gridcolor="#e8ecf5", title="Share of respondents", title_font=dict(size=10, color="#66718b"))
        st.plotly_chart(chart_theme(fig, 340), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        if "resilience_band" not in view or not view["resilience_band"].isin(["Resilient", "Watch", "Priority"]).any():
            st.markdown('<div class="section-title">Household resilience mix</div><div class="section-note">This view needs household resilience answers that the chosen wave does not include, so the mix is withheld rather than approximated.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="section-title">Resilience mix by setting</div><div class="section-note">Share of scored households in each band, urban vs rural</div>', unsafe_allow_html=True)
            band_order = ["Resilient", "Watch", "Priority"]
            band_colors = ["#3155d4", "#06b6d4", "#22c55e"]
            scored = view.loc[view["resilience_band"].isin(band_order)]
            settings_order = [s for s in ["Urban", "Rural"] if s in scored["setting"].dropna().unique()]
            fig = go.Figure()
            for band, color in zip(band_order, band_colors):
                xs, texts = [], []
                for setting in settings_order:
                    sub = scored.loc[scored["setting"].eq(setting)]
                    dist = weighted_distribution(sub, "resilience_band").reindex(band_order).fillna(0)
                    share = dist.sum() / sub["hh_wt"].sum() * 100 if sub["hh_wt"].sum() > 0 else 0.0
                    xs.append(share)
                    texts.append(f"{share:.0f}%" if share >= 9 else "")
                fig.add_trace(go.Bar(y=settings_order, x=xs, orientation="h", name=band, marker_color=color, text=texts, textposition="inside", insidetextanchor="middle", textfont=dict(color="#fff", size=11), hovertemplate="%{x:.1f}%<extra>" + band + "</extra>"))
            fig.update_layout(barmode="stack")
            fig.update_xaxes(range=[0, 100], ticksuffix="%", showgrid=True, gridcolor="#e8ecf5", title="Share of scored households", title_font=dict(size=10, color="#66718b"))
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(chart_theme(fig, 296, legend=True), width="stretch", config={"displayModeBar": False})
            resilient_flag = band_flag(view, "Resilient")
            st.markdown(f'<div class="legend-row">Nationally in this lens, <strong>{pct(weighted_rate(view, resilient_flag))}</strong> of scored households sit in the Resilient band.</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Below the fold: the opportunity map ---
    section_head("The opportunity map", "A first read for policy and programme teams")
    a, b, c = st.columns(3)
    with a:
        st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 01 · access</div><div class="insight-text">{pct(mobile)} use mobile money today.</div><div class="insight-foot">Mobile money is the clearest delivery rail for reaching households already inside the formal ecosystem.</div></div>', unsafe_allow_html=True)
    with b:
        st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 02 · resilience</div><div class="insight-text">{pct(1 - emergency)} report no emergency fund.</div><div class="insight-foot">The inclusion gap is not only account ownership; it is the ability to absorb a shock without selling assets or borrowing.</div></div>', unsafe_allow_html=True)
    with c:
        st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 03 · digital</div><div class="insight-text">{pct(1 - weighted_rate(view, view["internet_access"]))} lack internet access.</div><div class="insight-foot">Digital-first interventions need a low-bandwidth or assisted pathway to avoid excluding rural and lower-income users.</div></div>', unsafe_allow_html=True)

    both_valid = view["income_pressure"].notna() & view["emergency_fund"].notna()
    pressure_without_buffer = weighted_rate(
        view,
        (view["income_pressure"].eq(1) & view["emergency_fund"].eq(0)).astype(float).where(both_valid),
    )
    access_buffer_gap = active - emergency
    section_head("The problem in one line", "High channel access does not yet translate into household shock capacity")
    st.markdown(
        f'<div class="callout"><strong>{pct(access_buffer_gap, 0)} percentage-point access–buffer gap.</strong> '
        f"Formal access reaches {pct(active)}, while emergency-fund coverage reaches only {pct(emergency)}. "
        f"Among respondents with both answers observed, {pct(pressure_without_buffer)} report income pressure and no emergency fund. "
        "This is the operational problem the dashboard is designed to help target; it is not an official poverty classification.</div>",
        unsafe_allow_html=True,
    )



def _indicator_results(view: pd.DataFrame) -> dict[str, object | None]:
    """All six indicators where computable; None where the source cannot support a component."""

    results: dict[str, object | None] = {}
    for indicator_id in INDICATORS:
        try:
            results[indicator_id] = calculate_indicator(view, indicator_id)
        except ValueError:
            results[indicator_id] = None  # no label-verified counterpart on this source
    return results


def render_cross_source_agreement() -> None:
    """Honest agreement view between the two supplied sources (cached loads)."""

    with st.expander("How the 2024 and 2020 waves compare", expanded=False):
        st.caption(
            "The same indicator rules are applied to each wave separately. This table reports "
            "agreement between the waves — it does not merge them."
        )
        rows = []
        for indicator_id in INDICATORS:
            row = {"ID": indicator_id, "Indicator": INDICATORS[indicator_id].title}
            for tag, frame in (("2024 wave", load_master_frame()), ("2020 wave", load_spss_workload(SPSS_PATH))):
                try:
                    result = calculate_indicator(frame, indicator_id)
                    row[tag] = pct(result.estimate, 2)
                except ValueError:
                    row[tag] = "not reproducible"
            rows.append(row)
        agreement = pd.DataFrame(rows)
        agreement["Both present"] = agreement.apply(
            lambda r: r["2024 wave"] not in ("not reproducible",) and r["2020 wave"] not in ("not reproducible",), axis=1
        )
        st.dataframe(agreement, hide_index=True, width="stretch", height=260)
        st.caption("The two waves asked different people slightly different questions — treat large gaps as differences between the surveys, not as errors.")


@st.cache_data(show_spinner=False)
def load_master_frame(path: Path = DATA_PATH) -> pd.DataFrame:
    """Cached master frame for cross-source comparisons."""

    return pipeline_enrich_analysis_data(pipeline_load_analysis_data(path))


# -----------------------------------------------------------------------------
# Combined view (both supplied sources, pooled as independent samples)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="Pooling the two supplied sources…")
def joint_workload() -> tuple[pd.DataFrame, dict[str, object]]:
    """Build the pooled frame once and audit whether the files could be joined."""

    master = load_master_frame()
    spss = load_spss_workload(SPSS_PATH)
    return build_joint_frame(master, spss), linkage_audit(master, spss).to_dict()


@st.cache_data(show_spinner="Training the combined model…")
def transport_workload(target: str) -> pd.DataFrame:
    """Within-source, cross-source and pooled scores for one target."""

    joint, _audit = joint_workload()
    return evaluate_transport(joint, target)


def render_combined_relationships() -> None:
    """Pooled estimates, the source gap and the relationship matrix."""

    section_head(
        "Combined view — both waves together",
        "The same measures, computed on each wave and pooled as independent samples",
    )
    joint, _audit = joint_workload()
    st.markdown(
        '<div class="callout"><strong>Why this is pooled, not merged.</strong> '
        'The two waves surveyed different households and share no record keys, so they are '
        'analysed side by side — never joined.</div>',
        unsafe_allow_html=True,
    )

    master_label, spss_label = "2024 wave", "2020 wave"
    estimates = pooled_estimates(joint)
    c1, c2, c3 = st.columns(3)
    with c1: metric_card("Pooled records", f"{len(joint):,}", "the 2024 and 2020 waves combined", "∑", "green")
    with c2: metric_card("Shared measures", f"{len(MEASURES)}", "asked on both waves", "≡", "green", delay=1)
    with c3:
        mobile = float(estimates.loc[estimates["Measure"].eq(MEASURES["mobile_money"]), "Pooled (equal source weight)"].iloc[0])
        metric_card("Mobile money, pooled", pct(mobile), "both waves, equal weight", "⌁", "green", delay=2)

    left, right = st.columns([1.15, .85])
    with left:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Each measure, side by side</div><div class="section-note">Weighted share · the gap is the 2020 wave minus the 2024 wave</div>', unsafe_allow_html=True)
        display = estimates.copy()
        display = display.rename(columns={JOINT_SOURCE_LABELS["master"]: master_label, JOINT_SOURCE_LABELS["spss"]: spss_label, "master n": "2024 wave n", "spss n": "2020 wave n"})
        for column in (master_label, spss_label, "Pooled (equal source weight)"):
            display[column] = display[column].map(lambda value: pct(value, 1))
        display["Gap (pp)"] = display["Gap (pp)"].map(lambda value: f"{value:+.1f}" if pd.notna(value) else "—")
        st.dataframe(display, hide_index=True, width="stretch", height=300)
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        matrix = weighted_correlation(joint)
        labels = [MEASURES[column] for column in matrix.columns]
        st.markdown('<div class="section-title">How the measures move together</div><div class="section-note">Weighted Pearson correlation · both sources pooled</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Heatmap(
            z=matrix.to_numpy(), x=labels, y=labels, zmin=-1, zmax=1,
            colorscale=[[0, "#d95362"], [.5, "#f5f7fb"], [1, "#3155d4"]],
            text=[[f"{value:+.2f}" for value in row] for row in matrix.to_numpy()],
            texttemplate="%{text}", textfont=dict(size=9),
            hovertemplate="%{y} × %{x}: %{z:+.2f}<extra></extra>",
            colorbar=dict(thickness=8, len=.7, tickfont=dict(size=9)),
        ))
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, 300), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="footer-note"><strong>What a combined view can claim.</strong> {comparison_note()} '
        'Pooled figures give each supplied file equal total weight, so the larger file does not dominate. '
        'These are descriptive estimates; no survey-design standard error is available because the supplied '
        'materials include no strata/variance documentation.</div>',
        unsafe_allow_html=True,
    )


def render_combined_prediction() -> None:
    """Same non-leaking model, trained within and across both sources."""

    section_head(
        "One model, both sources — does prediction transfer?",
        "Trained on each file, then tested on the other and on both together",
    )
    target = st.selectbox(
        "Outcome to predict",
        list(TARGETS),
        format_func=lambda key: TARGETS[key],
        key="combined_target",
    )
    table = transport_workload(target)
    st.dataframe(
        table.drop(columns=["Note"]),
        hide_index=True,
        width="stretch",
        height=280,
        column_config={
            "Observed positive share": st.column_config.NumberColumn("Observed %", format="%.1f"),
            "Mean predicted": st.column_config.NumberColumn("Predicted %", format="%.1f"),
            "ROC-AUC": st.column_config.NumberColumn("ROC-AUC", format="%.3f"),
            "Brier": st.column_config.NumberColumn("Brier", format="%.3f"),
            "Base-rate Brier": st.column_config.NumberColumn("Base-rate Brier", format="%.3f"),
        },
    )
    st.markdown(
        '<div class="footer-note"><strong>How to read it.</strong> ROC-AUC asks whether the ranking '
        'transfers; Brier asks whether the probability level transfers, and the base-rate column is what '
        'a constant predictor would score. Both outcomes are highly prevalent (about 90–96% of asked '
        'respondents), so accuracy or F1 at a fixed cut-off would only restate the base rate and are '
        'deliberately not shown. Features are demographics, household size, internet access, income '
        'pressure and emergency funds; no channel that helps define the outcome is ever used. A modest '
        'AUC is the honest result here — it is not evidence that access can be targeted from these fields '
        'alone.</div>',
        unsafe_allow_html=True,
    )


def render_financial_inclusion(df: pd.DataFrame, profile: SourceProfile) -> None:
    page_intro(
        "02 / Financial inclusion",
        "Verified indicators, connected to their source variables.",
        "This page reports project-calculated estimates from the active source. Every result has a definition, denominator, source-variable mapping and limitation so a research user can reproduce or challenge it.",
    )
    view = filter_bar(df, "financial_inclusion")
    if not has_data(view):
        return
    results = _indicator_results(view)
    card_ids = ["FI-01", "FI-02", "FI-03", "FI-04"]
    cards = st.columns(4)
    card_styles = [("green", "↗"), ("green", "⌁"), ("yellow", "◌"), ("rose", "!")]
    for index, (slot, indicator_id, (color, icon)) in enumerate(zip(cards, card_ids, card_styles)):
        result = results[indicator_id]
        with slot:
            if result is None:
                metric_card(INDICATORS[indicator_id].title, "—", "not asked on this wave", "⊘", "rose", delay=index)
            else:
                metric_card(result.definition.title, pct(result.estimate), f"n={result.denominator_n:,} valid respondents", icon, color, delay=index)

    section_head("Financial inclusion evidence", "Weighted estimates from the active source · no survey-design standard errors are shown")
    available_chart = [i for i in INDICATORS if results[i] is not None]
    chart_is_empty = not available_chart
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        names = [results[i].definition.title for i in available_chart]
        values = [results[i].estimate * 100 for i in available_chart]
        colors = ["#3155d4", "#5274e6", "#e5ae2f", "#de7c3f", "#d95362", "#7182a8"]
        fig = go.Figure(go.Bar(x=values, y=names, orientation="h", marker_color=colors, text=[f"{v:.1f}%" for v in values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(range=[0, 108], ticksuffix="%")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, 350), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        selected = st.selectbox("Inspect indicator", list(INDICATORS), format_func=lambda x: f"{x} · {INDICATORS[x].title}", key="indicator_detail")
        result = results[selected]
        if result is None:
            missing_vars = ", ".join(INDICATORS[selected].source_variables)
            st.markdown(
                f'<div class="chart-card"><div class="eyebrow">{selected} · indicator card</div><div class="section-title" style="font-size:1.08rem">{INDICATORS[selected].title}</div><p class="section-note" style="font-size:.8rem;line-height:1.5">{INDICATORS[selected].definition}</p><div class="callout"><strong>Not available on this wave.</strong> The survey questions this indicator needs were not asked here, so the estimate is withheld rather than approximated or imputed.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            definition = result.definition
            st.markdown(
                f'<div class="chart-card"><div class="eyebrow">{definition.indicator_id} · indicator card</div><div class="section-title" style="font-size:1.08rem">{definition.title}</div><p class="section-note" style="font-size:.8rem;line-height:1.5">{definition.definition}</p><div class="metric-value" style="color:#172554">{pct(result.estimate, 1)}</div><div class="section-note">{result.numerator_n:,} positive records / {result.denominator_n:,} valid records · weighted population sum {result.weight_sum:,.0f}</div><div class="callout"><strong>Calculation.</strong> {definition.method}<br><br><strong>Source variables.</strong> {', '.join(definition.source_variables)}<br><br><strong>Limitation.</strong> {' '.join(definition.limitations)}</div></div>',
                unsafe_allow_html=True,
            )

    access_result = results.get("FI-01")
    buffer_result = results.get("FI-03")
    pressure_result = results.get("FI-05")
    section_head("What the indicators reveal", "The inclusion problem is a capability gap, not only a channel gap")
    interpretation_cards = []
    if access_result is not None:
        interpretation_cards.append(
            ("Reach", pct(access_result.estimate), f"{access_result.denominator_n:,} valid responses show whether formal finance currently reaches respondents.")
        )
    if access_result is not None and buffer_result is not None:
        interpretation_cards.append(
            ("Access–buffer gap", f"{(access_result.estimate - buffer_result.estimate) * 100:.0f} pp", "Formal access is much broader than emergency-fund coverage; usage should not be read as resilience.")
        )
    if pressure_result is not None:
        interpretation_cards.append(
            ("Daily pressure", pct(pressure_result.estimate), "Income-pressure responses show why households may struggle to turn access into savings capacity.")
        )
    insight_cols = st.columns(max(1, len(interpretation_cards)))
    for col, (title, value, note) in zip(insight_cols, interpretation_cards):
        with col:
            st.markdown(
                f'<div class="insight-card"><div class="insight-kicker">{title}</div><div class="insight-text">{value}</div><div class="insight-foot">{note}</div></div>',
                unsafe_allow_html=True,
            )
    st.caption(
        "Each estimate uses its own valid-response denominator. Missing or unverified responses are excluded, "
        "so differences between indicators are analytical signals rather than proof that the same respondents answered every question."
    )

    section_head("Indicator registry", "The research contract behind the dashboard")
    registry = pd.DataFrame([
        {
            "ID": definition.indicator_id,
            "Indicator": definition.title,
            "Definition": definition.definition,
            "Unit": definition.unit,
            "Valid responses": definition.valid_response_rule,
            "Source variables": ", ".join(definition.source_variables),
            "Verification": definition.verification,
        }
        for definition in INDICATORS.values()
    ])
    st.dataframe(registry, hide_index=True, width="stretch", height=315)
    registry_footnote = f'Source profile: {profile.source_variables:,} variables in the original source file · {profile.rows:,} records loaded · release and population period are not documented in the supplied materials.'
    st.markdown(f'<div class="footer-note">{registry_footnote}</div>', unsafe_allow_html=True)
    if chart_is_empty:
        st.markdown('<div class="footer-note">The active source cannot support any of the six documented indicators; the chart region above is intentionally empty rather than approximated.</div>', unsafe_allow_html=True)
    render_cross_source_agreement()
    render_combined_relationships()


def render_poverty_insights(df: pd.DataFrame, profile: SourceProfile) -> None:
    page_intro(
        "03 / Poverty insights",
        "Be explicit about what the evidence can—and cannot—support.",
        "The supplied file contains useful financial-stress and income-context questions, but this workspace does not include a documented official poverty measure, welfare aggregate, poverty line, or estimation methodology. No poverty rate is fabricated here.",
    )
    st.markdown('<div class="callout"><strong>Research status: blocked for an official poverty estimate.</strong><br>The source can support exploratory context on income pressure and emergency liquidity, but not a defensible poverty classification or poverty rate without the missing methodology and variables.</div>', unsafe_allow_html=True)
    section_head("Exact blockers", "These are actionable research dependencies, not dashboard errors")
    blockers = pd.DataFrame([
        ["Poverty concept", "No documented national/international poverty line or welfare concept is supplied."],
        ["Welfare aggregate", "The selected source slice has self-reported personal income bands, but no verified household consumption or welfare aggregate."],
        ["Survey methodology", "No sampling, strata, PSU, calibration or variance-estimation documentation is available in the workspace."],
        ["Authorization", "The file is present and inspected, but no authorization record for public poverty reporting was supplied."],
    ], columns=["Dependency", "Evidence status"])
    st.dataframe(blockers, hide_index=True, width="stretch")

    section_head("What is available as non-poverty context", "These are genuine estimates, clearly labelled as financial stress indicators")
    view = filter_bar(df, "poverty_context")
    if not has_data(view):
        return
    pressure_results = _indicator_results(view)
    pressure = pressure_results["FI-05"]
    difficulty = pressure_results["FI-04"]
    a, b = st.columns(2)
    with a:
        if pressure is None:
            metric_card("Income pressure", "—", "not asked on this wave", "⊘", "rose")
        else:
            metric_card("Income pressure", pct(pressure.estimate), "not an official poverty measure", "≈", "orange")
    with b:
        if difficulty is None:
            metric_card("Emergency money is difficult", "—", "not asked on this wave", "⊘", "rose", delay=1)
        else:
            metric_card("Emergency money is difficult", pct(difficulty.estimate), "self-reported liquidity stress", "◌", "yellow", delay=1)

    section_head("What this says about the problem", "Financial strain is visible here; poverty status is not")
    problem_lines = []
    if pressure is not None:
        problem_lines.append(
            f"<strong>{pct(pressure.estimate)}</strong> report that income does not cover living costs monthly or more often."
        )
    if difficulty is not None:
        problem_lines.append(
            f"<strong>{pct(difficulty.estimate)}</strong> say raising 56,000 Rwf within the next month would be very or somewhat difficult."
        )
    if problem_lines:
        st.markdown(
            '<div class="callout"><strong>Evidence interpretation.</strong><br>'
            + "<br>".join(problem_lines)
            + "<br><br>Read together, these measures describe limited room to absorb a shock. They can guide questions about savings, liquidity and social protection, but they do not identify who is below a poverty line, how far below it they are, or whether a household is chronically poor.</div>",
            unsafe_allow_html=True,
        )

    geo_measures = []
    if "income_pressure" in view:
        geo_measures.append(
            weighted_group(view, "province", "income_pressure")
            .rename(columns={"value": "income_pressure", "denominator_n": "pressure_n"})
        )
    if "emergency_difficult" in view:
        geo_measures.append(
            weighted_group(view, "province", "emergency_difficult")
            .rename(columns={"value": "emergency_difficult", "denominator_n": "difficulty_n"})
        )
    if geo_measures:
        section_head("Geographic context", "Where financial pressure is more concentrated — not a poverty ranking")
        pressure_geo = geo_measures[0]
        for measure_geo in geo_measures[1:]:
            pressure_geo = pressure_geo.merge(measure_geo, on="group", how="outer")
        sort_column = "income_pressure" if "income_pressure" in pressure_geo else "emergency_difficult"
        pressure_geo = pressure_geo.sort_values(sort_column, ascending=False)
        display_geo = pressure_geo.rename(columns={"group": "Province"}).copy()
        if "income_pressure" in display_geo:
            display_geo["Income pressure"] = display_geo["income_pressure"].map(pct)
        if "emergency_difficult" in display_geo:
            display_geo["Emergency money difficult"] = display_geo["emergency_difficult"].map(pct)
        columns = ["Province"]
        columns += [c for c in ("Income pressure", "Emergency money difficult") if c in display_geo]
        st.dataframe(display_geo[columns], hide_index=True, width="stretch")
        st.caption(
            "The table compares reported financial pressure across provinces. It is descriptive and weighted; "
            "it does not replace the missing poverty line, welfare aggregate or survey-design documentation."
        )


def render_regional(df: pd.DataFrame) -> None:
    page_intro(
        "04 / Geographic insights",
        "Make the geography of exclusion visible.",
        "Compare provincial signals and surface where access, digital connectivity and financial buffers diverge. The ranking is descriptive and weighted to the supplied survey design.",
    )
    view = filter_bar(df, "regional")
    if not has_data(view):
        return
    group = weighted_group(view, "province", "active_access")
    emergency = weighted_group(view, "province", "emergency_fund").rename(columns={"value": "emergency"})
    digital = weighted_group(view, "province", "internet_access").rename(columns={"value": "internet"})
    table = group.merge(emergency[["group", "emergency"]], on="group", how="left").merge(digital[["group", "internet"]], on="group", how="left")
    table["gap"] = table["value"] - table["emergency"]
    table = table.sort_values("value", ascending=True)

    l, r = st.columns([1.2, .8])
    with l:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Active access by province</div><div class="section-note">Currently use at least one formal financial channel</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Bar(y=table["group"], x=table["value"] * 100, orientation="h", marker_color="#3155d4", name="Active access", text=[f"{v:.0f}%" for v in table["value"] * 100], textposition="outside", hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(range=[0, 108], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, 340), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with r:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Three signals, one view</div><div class="section-note">Share of respondents · province comparison</div>', unsafe_allow_html=True)
        fig = go.Figure()
        for col, name, color in [("value", "Active access", "#3155d4"), ("emergency", "Emergency fund", "#e5ae2f"), ("internet", "Internet access", "#de7c3f")]:
            fig.add_trace(go.Bar(x=table["group"], y=table[col] * 100, name=name, marker_color=color, hovertemplate=f"%{{x}} · {name}: %{{y:.1f}}%<extra></extra>"))
        fig.update_layout(barmode="group")
        fig.update_yaxes(range=[0, 108], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, 340, True), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("What the geography says", "The main gap is between financial access and the ability to absorb a shock")
    lowest_access = table.iloc[0] if len(table) else None
    lowest_buffer = table.dropna(subset=["emergency"]).sort_values("emergency").iloc[0] if table["emergency"].notna().any() else None
    widest_gap = table.dropna(subset=["gap"]).sort_values("gap", ascending=False).iloc[0] if table["gap"].notna().any() else None
    geographic_signals = []
    if lowest_access is not None:
        geographic_signals.append(
            ("Lowest access", f"{lowest_access['group']} · {pct(lowest_access['value'])}", "The lowest-access province is the first place to inspect for reach and delivery barriers.")
        )
    if lowest_buffer is not None:
        geographic_signals.append(
            ("Thinnest buffer", f"{lowest_buffer['group']} · {pct(lowest_buffer['emergency'])}", "A low emergency-fund share means access expansion alone may not improve shock absorption.")
        )
    if widest_gap is not None:
        geographic_signals.append(
            ("Largest access–buffer gap", f"{widest_gap['group']} · {widest_gap['gap']:.0%}", "This is the clearest signal for pairing financial access with savings or liquidity support.")
        )
    signal_cols = st.columns(max(1, len(geographic_signals)))
    for col, (title, value, note) in zip(signal_cols, geographic_signals):
        with col:
            st.markdown(
                f'<div class="insight-card"><div class="insight-kicker">{title}</div><div class="insight-text">{value}</div><div class="insight-foot">{note}</div></div>',
                unsafe_allow_html=True,
            )
    st.caption(
        "Geographic differences are signals for targeting and investigation. They are not causal explanations, "
        "poverty classifications or proof that one province performs better because of a specific intervention."
    )

    section_head("District explorer", "Sorted by active formal access · filter the geography above to zoom in")
    district_table = weighted_group(view, "district", "active_access").rename(columns={"value": "active_access", "denominator_n": "active_n"})
    district_emergency = weighted_group(view, "district", "emergency_fund").rename(columns={"value": "emergency_fund", "denominator_n": "emergency_n"})
    district_table = district_table.merge(district_emergency, on="group", how="left").sort_values("active_access", ascending=False)
    if "income_pressure" in view:
        district_pressure = weighted_group(view, "district", "income_pressure").rename(columns={"value": "income_pressure", "denominator_n": "pressure_n"})
        district_table = district_table.merge(district_pressure, on="group", how="left")
    if "emergency_difficult" in view:
        district_difficulty = weighted_group(view, "district", "emergency_difficult").rename(columns={"value": "emergency_difficult", "denominator_n": "difficulty_n"})
        district_table = district_table.merge(district_difficulty, on="group", how="left")
    dleft, dright = st.columns([1.4, .6])
    with dleft:
        display_table = district_table.copy()
        display_table["Active access"] = display_table["active_access"].map(pct)
        display_table["Emergency fund"] = display_table["emergency_fund"].map(pct)
        if "income_pressure" in display_table:
            display_table["Income pressure"] = display_table["income_pressure"].map(pct)
        if "emergency_difficult" in display_table:
            display_table["Emergency money difficult"] = display_table["emergency_difficult"].map(pct)
        display_columns = ["group", "Active access", "Emergency fund"]
        display_columns += [column for column in ("Income pressure", "Emergency money difficult") if column in display_table]
        display_columns += ["active_n", "emergency_n"]
        st.dataframe(
            display_table[display_columns].rename(
                columns={"group": "District", "active_n": "Access n", "emergency_n": "Emergency n"}
            ),
            hide_index=True,
            width="stretch",
            height=300,
        )
    with dright:
        best = district_table.iloc[0] if len(district_table) else None
        worst = district_table.iloc[-1] if len(district_table) else None
        if best is not None and worst is not None:
            cue = (
                f"<strong>Decision cue.</strong><br><br>{best['group']} leads this filtered view on active access at "
                f"{pct(best['active_access'])}.<br><br>{worst['group']} is the lowest at "
                f"{pct(worst['active_access'])}; pair financial access expansion with a buffer-building offer."
            )
            if "income_pressure" in district_table and district_table["income_pressure"].notna().any():
                pressure_peak = district_table.loc[district_table["income_pressure"].idxmax()]
                cue += (
                    f"<br><br>{pressure_peak['group']} has the highest income pressure in this view at "
                    f"{pct(pressure_peak['income_pressure'])}; treat that as a financial-stress signal, not a poverty rate."
                )
            st.markdown(f'<div class="callout">{cue}</div>', unsafe_allow_html=True)

    if len(district_table) >= 2:
        drill_target = st.selectbox("District drill-down", ["—"] + district_table["group"].tolist(), format_func=lambda d: "Pick a district to inspect" if d == "—" else d, key="regional_drill")
        if drill_target and drill_target != "—":
            drill = district_table.loc[district_table["group"].eq(drill_target)].iloc[0]
            drill_internet = weighted_group(view, "district", "internet_access")
            drill_internet = drill_internet.loc[drill_internet["group"].eq(drill_target)]
            internet_value = float(drill_internet["value"].iloc[0]) if len(drill_internet) else float("nan")
            national_access = weighted_rate(view, view["active_access"])
            national_internet = weighted_rate(view, view["internet_access"])
            national_emergency = weighted_rate(view, view["emergency_fund"])
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                metric_card(f"{drill_target} · active access", pct(drill["active_access"]), f"national {pct(national_access)} · Δ {drill['active_access'] - national_access:+.1%}", "↗", "green")
            with c2:
                metric_card("Emergency buffer", pct(drill["emergency_fund"]), f"national {pct(national_emergency)} · Δ {drill['emergency_fund'] - national_emergency:+.1%}", "◌", "yellow", delay=1)
            with c3:
                metric_card("Internet access", pct(internet_value), f"national {pct(national_internet)} · Δ {internet_value - national_internet:+.1%}", "⌁", "orange", delay=2)
            with c4:
                metric_card("Assessed cases", f"{int(drill['active_n']):,}", "valid active-access records · missing responses excluded", "▤", "green", delay=3)
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            if "resilience_band" in view:
                dview = view[view["district"].eq(drill_target)]
                setting_split = weighted_group(dview.assign(priority=band_flag(dview, "Priority")), "setting", "priority")
                fig = go.Figure(go.Bar(x=setting_split["group"], y=setting_split["value"] * 100, marker_color=["#d95362" if s == "Rural" else "#f0a1ad" for s in setting_split["group"]], text=[f"{v:.0f}%" for v in setting_split["value"] * 100], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
                fig.update_yaxes(range=[0, max(30, float(setting_split["value"].max() * 100 + 10))], ticksuffix="%") if len(setting_split) else None
                st.markdown(f'<div class="section-title">{drill_target}: where does the priority share sit?</div><div class="section-note">Resilience Priority band share by urban / rural setting inside this district</div>', unsafe_allow_html=True)
                st.plotly_chart(chart_theme(fig, 230), width="stretch", config={"displayModeBar": False})
            else:
                st.markdown(f'<div class="section-title">{drill_target}: priority-share split</div><div class="section-note">Not available on this wave: the resilience band needs own-money, saving-behaviour and social-support answers that are absent here.</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            gap_note = f"{drill_target} sits {drill['active_access'] - national_access:+.1%} versus the national weighted mean for active access in this filtered view, and there is no gap signal designed yet to say whether buffer building or digital access would be the better first intervention."
            priority_note = f"PRIORITY band inside {drill_target} is shown above by setting." if "resilience_band" in view else "The resilience-band split is unavailable on this wave; consult page 05."
            st.markdown(f'<div class="callout"><strong>Drill-down read.</strong><br><br>{priority_note}{gap_note}</div>', unsafe_allow_html=True)


def render_resilience(df: pd.DataFrame) -> None:
    page_intro(
        "05 / Resilience lab",
        "Find the households most exposed to the next shock.",
        "The resilience lab turns survey responses into a simple, inspectable prioritisation lens. It combines emergency savings, control of money, saving behaviour and social support — without pretending to be a causal or predictive model.",
    )
    view = filter_bar(df, "resilience")
    if not has_data(view):
        return
    if "resilience_band" not in view:
        st.markdown('<div class="callout"><strong>The resilience lens is not available on this wave.</strong><br>The lens needs four observed capabilities; the chosen wave carries only the emergency-funds one. Own money, saving behaviour and a social-support contact are absent, so the Priority / Watch / Resilient band is withheld rather than approximated. Choose the 2024 survey year in the left sidebar for the full lens; the one capability this wave does support is shown below.</div>', unsafe_allow_html=True)
        difficult_available = weighted_rate(view, view["emergency_difficult"]) if "emergency_difficult" in view else None
        c1, c2 = st.columns(2)
        with c1:
            if difficult_available is None:
                metric_card("Emergency feels difficult", "—", "not asked on this wave", "⊘", "rose")
            else:
                metric_card("Emergency feels difficult", pct(difficult_available), "say raising 56,000 Rwf would be difficult (the lens component this source does support)", "◌", "orange")
        with c2:
            metric_card("Resilience band", "—", "needs all four lens capabilities · withheld", "⊘", "rose", delay=1)
        return
    risk = weighted_rate(view, band_flag(view, "Priority"))
    watch = weighted_rate(view, band_flag(view, "Watch"))
    difficult = weighted_rate(view, view["emergency_difficult"])
    stress = weighted_rate(view, view["financial_stress"])
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Priority households", pct(risk), "low on the four-component resilience lens", "!", "rose")
    with c2: metric_card("Watch list", pct(watch), "partial resilience; programme targeting can make a difference", "◐", "yellow", delay=1)
    with c3: metric_card("Emergency feels difficult", pct(difficult), "say raising 56,000 Rwf would be difficult", "◌", "orange", delay=2)
    with c4: metric_card("Financial stress", pct(stress), "agree or sometimes feel financial stress", "≈", "rose", delay=3)

    section_head("Resilience is a stack, not a single score", "Each component is shown separately so the intervention logic stays auditable")
    components = [
        ("Emergency fund", "emergency_fund", "rainy-day funds set aside"),
        ("Own money", "owns_money", "money they can use as they wish"),
        ("Saves", "saves_regularly", "save at least sometimes"),
        ("Social support", "social_safety_net", "have someone who could provide support"),
    ]
    profile, chart = st.columns([.92, 1.08])
    with profile:
        st.markdown('<div class="profile-panel"><div class="section-title">Observed capabilities</div><div class="section-note">Weighted share of respondents</div>', unsafe_allow_html=True)
        for label, col, note in components:
            value = weighted_rate(view, view[col])
            st.markdown(f'<div class="profile-row"><div class="profile-name">{label}<br><span style="font-size:.64rem">{note}</span></div><div class="profile-track"><div class="profile-fill" style="width:{max(0,min(100,value*100)):.1f}%"></div></div><div class="profile-number">{pct(value)}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with chart:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Priority share by setting</div><div class="section-note">A useful first cut for delivery design</div>', unsafe_allow_html=True)
        setting = weighted_group(view.assign(priority=band_flag(view, "Priority")), "setting", "priority")
        fig = go.Figure(go.Bar(x=setting["group"], y=setting["value"] * 100, marker_color=["#d95362" if x == "Rural" else "#f0a1ad" for x in setting["group"]], text=[f"{v:.0f}%" for v in setting["value"] * 100], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
        fig.update_yaxes(range=[0, max(30, float(setting["value"].max() * 100 + 10))], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, 245), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    component_rates = {
        label: weighted_rate(view, view[column])
        for label, column, _note in components
    }
    observed_components = {label: value for label, value in component_rates.items() if pd.notna(value)}
    weakest = min(observed_components.items(), key=lambda item: item[1]) if observed_components else None
    setting_gap = float("nan")
    setting_read = "Setting comparison is unavailable in this lens."
    if len(setting) >= 2 and setting["value"].notna().any():
        rural = setting.loc[setting["group"].eq("Rural"), "value"]
        urban = setting.loc[setting["group"].eq("Urban"), "value"]
        if len(rural) and len(urban):
            setting_gap = float(rural.iloc[0] - urban.iloc[0])
            setting_read = f"The rural–urban Priority difference is {setting_gap:+.0%} (rural minus urban)."
    section_head("What the lens identifies", "A prioritisation signal built from observed capabilities")
    if weakest is not None:
        st.markdown(
            f'<div class="callout"><strong>Weakest observed capability: {weakest[0]} at {pct(weakest[1])}.</strong> '
            f"The Priority band is {pct(risk)} and the Watch band is {pct(watch)} among scored respondents. "
            f"{setting_read} Use these results to design an offer and a delivery route; do not treat the band as a poverty label, eligibility rule or causal forecast.</div>",
            unsafe_allow_html=True,
        )

    section_head("What action could look like", "Translate signals into a practical programme conversation")
    x, y, z = st.columns(3)
    with x:
        st.markdown('<div class="chart-card"><span class="tag">Buffer</span><div class="section-title" style="margin-top:.55rem">Emergency savings nudges</div><div class="section-note">Prioritise households with no rainy-day funds and difficult access to 56,000 Rwf. Consider goal-based savings, commitment products and VUP-linked onboarding.</div></div>', unsafe_allow_html=True)
    with y:
        st.markdown('<div class="chart-card"><span class="tag">Access</span><div class="section-title" style="margin-top:.55rem">Assisted digital rails</div><div class="section-note">Use mobile money as an entry point, but pair it with USSD, agent support and clear-language financial education where internet access is limited.</div></div>', unsafe_allow_html=True)
    with z:
        st.markdown('<div class="chart-card"><span class="tag">Protection</span><div class="section-title" style="margin-top:.55rem">Shock-responsive finance</div><div class="section-note">Connect social protection and micro-insurance conversations to the shocks households report — especially when social networks are the only fallback.</div></div>', unsafe_allow_html=True)



EXPLORER_VARS = {
    "Mobile money — currently use": "mobile_money",
    "Active formal access": "active_access",
    "Emergency fund": "emergency_fund",
    "Emergency money — difficult to raise": "emergency_difficult",
    "Income pressure": "income_pressure",
    "Internet access": "internet_access",
    "Own money": "owns_money",
    "Saves at least sometimes": "saves_regularly",
    "Micro-insurance product": "microinsurance",
    "Has someone to rely on": "social_safety_net",
}


def render_explorer(df: pd.DataFrame, profile: SourceProfile | None = None) -> None:
    page_intro(
        "08 / Data explorer",
        "Keep the evidence one click away.",
        "Inspect aggregate evidence behind every headline. Pick a measure, break it down by a demographic or geographic dimension, and keep household-level records protected by default.",
    )
    view = filter_bar(df, "explorer")
    if not has_data(view):
        return
    section_head("Current analytical scope", "Know the size and geography of the evidence before reading a percentage")
    valid_weights = view["hh_wt"].notna() & view["hh_wt"].gt(0) & np.isfinite(view["hh_wt"])
    scope_cards = [
        ("Rows in lens", f"{len(view):,}", "loaded records after the active filters"),
        ("Weighted records", f"{int(valid_weights.sum()):,}", "rows with a positive, usable analysis weight"),
        ("Provinces", f"{view['province'].nunique(dropna=True):,}", "geographic groups represented"),
        ("Districts", f"{view['district'].nunique(dropna=True):,}", "district groups represented"),
    ]
    scope_cols = st.columns(4)
    for col, (label, value, note) in zip(scope_cols, scope_cards):
        with col:
            metric_card(label, value, note, "▤", "green")
    if not aggregate_release_allowed(profile):
        gate_col, why_col = st.columns([1.55, 1])
        with gate_col:
            st.markdown('<div class="callout"><strong>Aggregate explorer is governance-gated.</strong><br>No explicit authorization and disclosure/publication approval record is available for this source. The app will not produce an arbitrary filtered aggregate table or export until an authorised data steward supplies both approvals and an approved disclosure rule.</div>', unsafe_allow_html=True)
        with why_col:
            if st.button("Why is this withheld?", key="open_gate_modal"):
                explorer_gate_modal(profile)
        return
    left, right = st.columns([.7, 1.3])
    with left:
        label = st.selectbox("Measure", list(EXPLORER_VARS), key="explorer_measure")
        measure = EXPLORER_VARS[label]
        dimension = st.selectbox("Break down by", ["province", "district", "setting", "sex", "head_sex"], format_func=lambda x: {"province": "Province", "district": "District", "setting": "Setting", "sex": "Respondent sex", "head_sex": "Household-head sex"}[x], key="explorer_dimension")
        rate = weighted_rate(view, view[measure])
        st.markdown(f'<div class="metric-card green" style="margin-top:1rem"><div class="metric-top"><div class="metric-label">Selected measure</div><div class="metric-icon">◒</div></div><div class="metric-value">{pct(rate)}</div><div class="metric-foot">{label.lower()} in the filtered view</div></div>', unsafe_allow_html=True)
    with right:
        grouped = weighted_group(view, dimension, measure).sort_values("value", ascending=True)
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">{label} by {dimension.replace("_", " ")}</div><div class="section-note">Weighted share of respondents</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(y=grouped["group"], x=grouped["value"] * 100, orientation="h", marker_color="#3155d4", text=[f"{v:.0f}%" for v in grouped["value"] * 100], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(range=[0, 108], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, max(260, min(510, 35 * len(grouped) + 90))), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Aggregate evidence", f"Household-level records are withheld by default · {len(view):,} records in scope")
    aggregate = aggregate_weighted_measure(view, measure)
    if not aggregate.empty:
        aggregate["estimate"] = aggregate["estimate"].map(lambda x: pct(x, 1))
        aggregate = aggregate.rename(columns={"province": "Province", "district": "District", "setting": "Setting", "sex": "Respondent sex", "records": "Records", "weight_sum": "Weight sum", "estimate": label})
    st.dataframe(aggregate, hide_index=True, width="stretch", height=340)
    st.markdown('<div class="callout"><strong>Privacy and publication control.</strong><br>Household-level records and raw CSV export are disabled because no authorization or disclosure/publication approval record was supplied. The table above is an aggregate analytical view only.</div>', unsafe_allow_html=True)
    aggregate_csv = aggregate.to_csv(index=False).encode("utf-8") if not aggregate.empty else b""
    st.download_button("Download aggregate summary (approval required)", aggregate_csv, file_name="insightrwanda_aggregate_summary.csv", mime="text/csv", type="secondary", disabled=True if profile is None else profile.publication_status != "Approved", help="Unavailable while the source profile records no authorization and publication approval. Hovering the callout above shows the current gate state in detail.")


def render_quality(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    page_intro(
        "07 / Data quality",
        "Know what was checked before trusting a result.",
        "This is a structural and analytical-slice assessment of the supplied file. It reports evidence from checks that actually ran; it does not certify representativeness, fieldwork quality or publication readiness.",
    )
    summary = quality_summary(checks)
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Checks passed", str(summary["PASS"]), "structural or traceability checks", "✓", "green")
    with c2: metric_card("Warnings", str(summary["WARN"]), "requires review or qualification", "!", "yellow", delay=1)
    with c3: metric_card("Informational", str(summary["INFO"]), "measured, not scored", "i", "orange", delay=2)
    with c4: metric_card("Failures", str(summary["FAIL"]), "blocking structural checks", "×", "rose", delay=3)

    section_head("Executed checks", "The findings below come from the loaded source, not synthetic fixture data")
    quality_table = pd.DataFrame([
        {"Status": check.status, "Category": check.category, "Check": check.check_id, "Finding": check.finding}
        for check in checks
    ])
    st.dataframe(quality_table, hide_index=True, width="stretch", height=355)

    section_head("Core-variable missingness", "Missing responses are excluded from each indicator denominator; no imputation is performed")
    missing_cols = ["qf4_05", "e9b", "e9c", "e7", "c14_5", "b2", "a1", "a2"]
    missing_values = [(column, df[column].isna().mean() * 100) for column in missing_cols if column in df]
    left, right = st.columns([1.05, .95])
    with left:
        fig = go.Figure(go.Bar(x=[value for _, value in missing_values], y=[column for column, _ in missing_values], orientation="h", marker_color="#de7c3f", text=[f"{value:.1f}%" for _, value in missing_values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}% missing<extra></extra>"))
        fig.update_xaxes(range=[0, max(10, max((value for _, value in missing_values), default=0) + 10)], ticksuffix="%")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, 300), width="stretch", config={"displayModeBar": False})
    with right:
        st.markdown(f'<div class="callout"><strong>Scope.</strong><br><br>{profile.source_variables:,} source variables were inventoried. This dashboard loads {profile.analytical_variables:,} documented analytical variables, plus derived labels and indicators.<br><br><strong>Important.</strong><br><br>A clean load, unique key and valid codes do not prove that the survey is representative or that an official statistic can be published.</div>', unsafe_allow_html=True)

    if missing_values:
        most_missing_column, most_missing_value = max(missing_values, key=lambda item: item[1])
        section_head("What quality means for the problem", "Coverage determines which questions can be answered with confidence")
        st.markdown(
            f'<div class="callout"><strong>{most_missing_column} has the highest missingness in this analytical slice at {most_missing_value:.1f}%.</strong> '
            f"That is why every indicator reports its own valid denominator and why the dashboard does not impute a missing answer. "
            f"The current file contains {len(df):,} loaded rows, {summary['PASS']} passing checks, {summary['WARN']} warnings and {summary['FAIL']} blocking failures. "
            "These checks protect the calculation chain; they do not certify representativeness, poverty measurement or publication readiness.</div>",
            unsafe_allow_html=True,
        )

    section_head("Quality limitations", "What remains outside the executed checks")
    st.markdown('<div class="chart-card"><div class="section-note" style="font-size:.8rem;line-height:1.65">The workspace does not contain the fieldwork protocol, sample design, questionnaire version, enumerator quality controls, non-response adjustments, geographic boundary release, disclosure review, or an approved publication record. These should be supplied before an official public research release.</div></div>', unsafe_allow_html=True)


def render_methods(profile: SourceProfile, checks: list[QualityCheck]) -> None:
    page_intro(
        "09 / Methods & sources",
        "A traceable route from source file to displayed result.",
        "This page separates what is known about the supplied materials, what the application calculated, and what still needs research governance or documentation before publication.",
    )
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown(f'<div class="chart-card"><div class="eyebrow">Source profile</div><div class="section-title" style="font-size:1.12rem">Survey data · {COMBINED_LABEL}</div>', unsafe_allow_html=True)
        source_rows = [
            ["Source ID", profile.source_id], ["Format", profile.format], ["File size", f"{profile.file_size_mb:.2f} MB"],
            ["Source SHA-256", profile.source_sha256], ["Analysis version", profile.analysis_version],
            ["Rows", f"{profile.rows:,}"], ["Source variables", f"{profile.source_variables:,}"], ["Analytical slice", f"{profile.analytical_variables:,} variables"],
            ["Release / period", profile.source_release], ["Metadata", profile.metadata_status], ["Analysis", profile.analysis_status],
            ["Authorization", profile.authorization_status], ["Publication", profile.publication_status],
        ]
        st.dataframe(pd.DataFrame(source_rows, columns=["Field", "Status / value"]), hide_index=True, width="stretch", height=405)
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="chart-card"><div class="eyebrow">Evidence chain</div><div class="section-title" style="font-size:1.12rem">Five steps, one audit trail</div>', unsafe_allow_html=True)
        for no, title, copy in [
            ("01", "Inspect", "Read the original Stata metadata and confirm the supplied file is present."),
            ("02", "Load", "Read the selected source columns with explicit failure on missing variables."),
            ("03", "Validate", "Run schema, identifier, weight, code, geography and missingness checks."),
            ("04", "Calculate", "Apply the indicator definition, denominator and household weight."),
            ("05", "Explain", "Display the estimate with source variables, scope and limitations."),
        ]:
            st.markdown(f'<div style="display:flex;gap:.8rem;padding:.72rem 0;border-bottom:1px solid #e8ecf5"><div class="mono" style="color:#3155d4;font-size:.72rem;padding-top:.1rem">{no}</div><div><div style="font-weight:700;font-size:.8rem">{title}</div><div style="font-size:.73rem;color:#66718b;line-height:1.4;margin-top:.18rem">{copy}</div></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Quantitative audit snapshot", "The scale of the evidence behind the displayed numbers")
    audit_cards = [
        ("Loaded rows", f"{profile.rows:,}", "records represented in the active source profile"),
        ("Source variables", f"{profile.source_variables:,}", "variables inventoried before the analytical slice was selected"),
        ("Analytical variables", f"{profile.analytical_variables:,}", "documented fields loaded plus derived indicators"),
        ("Executed checks", f"{len(checks):,}", "quality and traceability checks recorded for this build"),
    ]
    audit_cols = st.columns(4)
    for col, (label, value, note) in zip(audit_cols, audit_cards):
        with col:
            st.markdown(
                f'<div class="insight-card"><div class="insight-kicker">{label}</div><div class="insight-text">{value}</div><div class="insight-foot">{note}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown(
        '<div class="callout"><strong>Why this matters.</strong> The pipeline makes the numbers traceable from source variables to weighted estimates, but traceability is not the same as official publication authority. The two supplied waves are retained as separate samples and are pooled only where the dashboard explicitly says so.</div>',
        unsafe_allow_html=True,
    )

    section_head("Available source materials", "What was actually found in the workspace")
    st.dataframe(pd.DataFrame({"Material": list(profile.documentation), "Use": ["Competition scope and evaluation criteria", "Embedded survey variable and value labels"]}), hide_index=True, width="stretch")
    st.markdown('<div class="callout"><strong>Governance boundary.</strong><br>The application distinguishes file existence, metadata inspection, permitted analysis, validation and public publication. The supplied workspace contains no authorization or publication approval record, so the app is suitable for internal analysis and demonstration, not an approved public statistical release.</div>', unsafe_allow_html=True)

    section_head("Indicator methodology", "Verified source mapping for the current financial-inclusion slice")
    method_rows = [{"ID": d.indicator_id, "Definition": d.definition, "Valid responses": d.valid_response_rule, "Calculation": d.method, "Limitations": " ".join(d.limitations)} for d in INDICATORS.values()]
    st.dataframe(pd.DataFrame(method_rows), hide_index=True, width="stretch", height=320)
    st.markdown(f'<div class="footer-note">Quality checks executed: {len(checks)} · source profile is cached from the supplied file · original research materials remain unchanged.</div>', unsafe_allow_html=True)


def render_about(df: pd.DataFrame) -> None:
    if LOGO_PATH.exists():
        _left_logo, _right_about = st.columns([1, 2.2], gap="medium", vertical_alignment="center")
        with _left_logo:
            st.image(str(LOGO_PATH), width=190)
    page_intro(
        "10 / About the build",
        "A competition-ready decision tool, grounded in NISR data.",
        "InsightRwanda translates a large financial-inclusion survey into a presentation-ready interface for policy teams, financial-service providers and civil-society partners.",
    )
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown('<div class="chart-card"><div class="eyebrow">The challenge</div><div class="section-title" style="font-size:1.15rem">From “who is included?” to “who can absorb a shock?”</div><p class="section-note" style="font-size:.82rem;line-height:1.6">The 2026 NISR Big Data Hackathon calls for solutions that address Financial Inclusion & Poverty Reduction with tangible value for vulnerable households, policy makers and civil society. This prototype focuses on the gap between access to a financial channel and meaningful household resilience.</p><div class="callout"><strong>Product thesis.</strong> Financial inclusion becomes more actionable when teams can see the intersection of access, buffers, digital reach, geography and household vulnerability in one place.</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="chart-card"><div class="eyebrow">What is inside</div><div class="section-title" style="font-size:1.15rem">A compact, auditable stack</div>', unsafe_allow_html=True)
        for no, title, desc in [("01", "Overview", "National signal with weighted KPI cards and the headline inclusion / resilience gap."), ("02", "Regional pulse", "Province and district comparison for targeting and delivery planning."), ("03", "Resilience lab", "Transparent composite lens and action prompts for household protection."), ("04", "Data explorer", "Inspect aggregate evidence; exports remain approval-gated.")]:
            st.markdown(f'<div style="display:flex;gap:.8rem;padding:.75rem 0;border-bottom:1px solid #e8ecf5"><div class="mono" style="color:#3155d4;font-size:.72rem;padding-top:.1rem">{no}</div><div><div style="font-weight:700;font-size:.8rem">{title}</div><div style="font-size:.73rem;color:#66718b;line-height:1.4;margin-top:.18rem">{desc}</div></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Method and transparency", "The dashboard is intentionally descriptive")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown('<div class="chart-card"><div class="section-title">Weighted estimates</div><div class="section-note">All headline rates use the survey\'s household weights, so larger areas and groups count their fair share.</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown('<div class="chart-card"><div class="section-title">Resilience lens</div><div class="section-note">The score is the mean of four binary capabilities: emergency funds, own money, saving at least sometimes and a potential social support contact. It is a prioritisation lens, not a poverty line or modelled probability.</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown('<div class="chart-card"><div class="section-title">Data integrity</div><div class="section-note">Missing responses are excluded from each indicator’s denominator. The explorer makes the filtered sample visible so users can assess coverage before interpreting a result.</div></div>', unsafe_allow_html=True)

    def about_rate(column: str) -> float:
        return weighted_rate(df, df[column]) if column in df else float("nan")

    access_rate = about_rate("active_access")
    mobile_rate = about_rate("mobile_money")
    buffer_rate = about_rate("emergency_fund")
    pressure_rate = about_rate("income_pressure")
    internet_rate = about_rate("internet_access")

    section_head("What problem the analysis shows", "Access is not the same as the ability to absorb a shock")
    problem_cards = [
        (
            "01",
            "Access can hide fragility",
            f"{pct(access_rate)} have active formal access and {pct(mobile_rate)} use mobile money, but only {pct(buffer_rate)} report an emergency fund.",
            "The main problem is not only reaching a financial channel; it is building a buffer before the next shock.",
        ),
        (
            "02",
            "Daily pressure limits resilience",
            f"{pct(pressure_rate)} report income pressure, meaning income does not cover monthly living costs.",
            "Households under regular pressure have less room to save, keep liquidity or recover after an emergency.",
        ),
        (
            "03",
            "Digital reach is uneven",
            f"{pct(1 - internet_rate)} of the active lens lacks internet access.",
            "A digital-only service can miss the people who need support most unless assisted and low-bandwidth routes remain available.",
        ),
    ]
    pcols = st.columns(3)
    for col, (number, title, signal, implication) in zip(pcols, problem_cards):
        with col:
            st.markdown(
                f'<div class="insight-card"><div class="insight-kicker">Signal {number}</div><div class="insight-text">{signal}</div><div class="insight-foot">{implication}</div></div>',
                unsafe_allow_html=True,
            )

    section_head("How the analysis is done", "From source files to a decision signal")
    analysis_steps = [
        ("01", "Load and harmonise", "Read the supplied 2024 Stata and 2020 SPSS sources, verify labels and keep them as independent samples."),
        ("02", "Measure the gap", "Calculate six financial-inclusion indicators with valid-response rules, visible denominators and household weights."),
        ("03", "Build the resilience lens", "Combine emergency funds, own money, saving behaviour and social support into an inspectable prioritisation lens."),
        ("04", "Test what can be predicted", "Evaluate a leakage-controlled model on held-out records to rank the Priority band; this is an association, not a causal or eligibility decision."),
    ]
    for number, title, description in analysis_steps:
        st.markdown(
            f'<div class="chart-card" style="display:flex;gap:1rem;align-items:flex-start;padding:.9rem 1rem;margin-bottom:.55rem"><div class="mono" style="color:#3155d4;font-size:.72rem;padding-top:.1rem">{number}</div><div><div class="section-title" style="font-size:1rem">{title}</div><div class="section-note" style="line-height:1.55">{description}</div></div></div>',
            unsafe_allow_html=True,
        )

    section_head("What this can help solve", "The dashboard supports decisions; it does not promise a solved outcome")
    solution_cards = [
        ("Build buffers", "Use emergency-fund and income-pressure signals to design savings nudges, emergency liquidity and shock-responsive finance."),
        ("Keep access inclusive", "Pair mobile-money and digital channels with agents, USSD and other assisted routes where internet access is thin."),
        ("Target action geographically", "Use province and district comparisons to place outreach, financial education and protection services where the gap is largest."),
        ("Improve the next decision", "Use the documented blockers to request the poverty line, welfare aggregate, survey-design metadata and publication approvals needed for stronger official estimates."),
    ]
    scols = st.columns(4)
    for col, (title, description) in zip(scols, solution_cards):
        with col:
            st.markdown(
                f'<div class="chart-card"><div class="section-title" style="font-size:1rem">{title}</div><div class="section-note" style="line-height:1.55">{description}</div></div>',
                unsafe_allow_html=True,
            )

    section_head("Future outlook from the evidence", "Directional scenarios, not a time-series forecast")
    st.markdown(
        '<div class="callout"><strong>Most likely if nothing changes.</strong><br>Households without emergency buffers will remain the most exposed to income shocks, and digital-first programmes will continue to leave gaps where internet access is low.</div>',
        unsafe_allow_html=True,
    )
    outlook = pd.DataFrame([
        ["If buffers expand", "The Priority share should move downward over time, because more households would have an observed capability to absorb a shock."],
        ["If access expands without buffers", "Formal usage may rise while financial fragility remains; access alone should not be treated as poverty reduction."],
        ["What the model can add", "The tested model can rank observed households by Priority likelihood for follow-up, but it cannot forecast future rates or prove that an intervention caused improvement."],
    ], columns=["Scenario", "Expected direction"])
    st.dataframe(outlook, hide_index=True, width="stretch")
    st.info("The supplied workspace contains cross-sectional survey waves, not a longitudinal outcome series. Future quantities therefore need follow-up survey waves or programme monitoring before they can be forecast numerically.")

    section_head("Hackathon alignment", "How the prototype answers the judging criteria")
    criteria = pd.DataFrame([
        ["Problem relevance", "Targets financial exclusion, poverty dynamics and household shock absorption."],
        ["Data + methodology", "Uses NISR-labelled Stata survey data, household weights and transparent indicators."],
            ["Tech innovation", "Turns the supplied survey into an interactive targeting and resilience workflow."],
        ["Usability + design", "Custom navigation, responsive layout, plain-language narrative and downloadable evidence."],
        ["Tangible impact", "Surfaces where to strengthen buffers, assisted digital access and shock-responsive finance."],
    ], columns=["Criterion", "Prototype response"])
    st.dataframe(criteria, hide_index=True, width="stretch")
    st.markdown(f'<div class="footer-note">Dataset loaded successfully: {len(df):,} rows available · selected analytical slice loaded on demand for a fast presentation experience.</div>', unsafe_allow_html=True)


def lens_signature(df: pd.DataFrame, page: str) -> str | None:
    """Human-readable description of the active analysis lens (None = page has none)."""

    prefix = LENS_PREFIXES.get(page)
    if not prefix:
        return None
    year = active_year()
    province = st.session_state.get(f"{prefix}_province", "All provinces")
    district = st.session_state.get(f"{prefix}_district", "All districts")
    setting = st.session_state.get(f"{prefix}_setting", "All settings")
    sex = st.session_state.get(f"{prefix}_sex", "All respondents")
    parts = [part for part in (
        None if year == YEAR_ALL else YEAR_SHORT.get(year, year),
        None if province == "All provinces" else province,
        None if district == "All districts" else district,
        None if setting == "All settings" else setting,
        None if sex == "All respondents" else sex,
    ) if part]
    lens_text = " · ".join(parts) if parts else "National view"
    return f"{lens_text} · {len(df):,} records"


def lens_toast(page: str, signature: str | None) -> None:
    """Surface a quiet toast when the active analysis lens changes."""

    if signature is None:
        return
    key = f"_lens_sig_seen_{page}"
    previous = st.session_state.get(key)
    st.session_state[key] = signature
    if previous is not None and previous != signature:
        st.toast(f"Lens updated — {signature}", icon="🔍")


def kpi_countup() -> None:
    """Animate the numeric part of every .metric-value from 0 to its value.

    A silent-fallback enhancement: if the browser blocks the iframe→parent
    access or prefers reduced motion, nothing happens and the static value
    remains. Uses no external libraries and never touches research logic.
    """

    st.html(
        r"""
<script>
(function () {
  var doc;
  try { doc = window.parent.document; } catch (e) { return; }
  if (!doc || (doc.matchMedia && doc.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  function parse(el) {
    var text = el.textContent || '';
    var m = text.match(/^(.*?)(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d)(.*)$/s);
    if (!m) return null;
    var target = parseFloat(m[2].replace(/,/g, ''));
    if (!isFinite(target)) return null;
    var decimals = (m[2].split('.')[1] || '').length;
    return { el: el, prefix: m[1], target: target, suffix: m[3], decimals: decimals, raw: m[2] };
  }
  function ease(t) { return 1 - Math.pow(1 - t, 3); }
  function animate(item) {
    var start = null;
    var duration = 650;
    function frame(ts) {
      if (!start) start = ts;
      var t = Math.min((ts - start) / duration, 1);
      var value = item.target * ease(t);
      var shown = value.toFixed(item.decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      item.el.textContent = item.prefix + shown + item.suffix;
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var nodes = doc.querySelectorAll('.metric-value');
  var items = [];
  for (var i = 0; i < nodes.length; i++) {
    var parsed = parse(nodes[i]);
    if (parsed) items.push(parsed);
  }
  if (!('IntersectionObserver' in window.parent)) {
    items.forEach(animate);
    return;
  }
  var observer = new window.parent.IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var found = null;
      for (var i = 0; i < items.length; i++) if (items[i].el === entry.target) found = items[i];
      if (found) { animate(found); observer.unobserve(entry.target); }
    });
  }, { threshold: 0.4 });
  items.forEach(function (item) { observer.observe(item.el); });
})();
</script>
""",
    )


def _lens_view(df: pd.DataFrame, page: str) -> pd.DataFrame:
    """Reapply the active page's filter-bar lens (without re-rendering widgets)."""

    prefix = LENS_PREFIXES.get(page)
    if not prefix:
        return df
    province = st.session_state.get(f"{prefix}_province", "All provinces")
    district = st.session_state.get(f"{prefix}_district", "All districts")
    setting = st.session_state.get(f"{prefix}_setting", "All settings")
    sex = st.session_state.get(f"{prefix}_sex", "All respondents")
    # The survey year is already applied once in main(); the lens adds only the
    # page-level geographic/demographic filters on top of it.
    pre = df
    pre = pre if province == "All provinces" else pre[pre["province"].eq(province)]
    return pipeline_filter_analysis_data(
        pre,
        district=None if district == "All districts" else district,
        setting=None if setting == "All settings" else setting,
        respondent_sex=None if sex == "All respondents" else sex,
    )


@st.dialog("Why the explorer withholds aggregates", width="large")
def explorer_gate_modal(profile: SourceProfile) -> None:
    released = aggregate_release_allowed(profile)
    st.markdown(
        f"<p class='section-note'>The gate is coded, tested software — not a disclaimer. "
        "Aggregates are released only when both the authorization record and the publication record "
        "begin with \"Approved\". Current state:</p>",
        unsafe_allow_html=True,
    )
    st.dataframe(pd.DataFrame([
        ["Authorization record", profile.authorization_status],
        ["Publication record", profile.publication_status],
        ["Gate state", "Open" if released else "Closed — household preview, raw export and aggregate tables withheld"],
    ], columns=["Requirement", "Status"]), hide_index=True, width="stretch")
    st.markdown(
        "<div class='callout'><strong>What unlocks it.</strong> An authorized data steward records both "
        "approvals plus an approved disclosure rule in the source profile. Until then, page-level "
        "evidence is shared through the one-page briefs below — aggregate-only by construction.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Close", key="modal_close_explorer"):
        return


# -----------------------------------------------------------------------------
# Ask InsightRwanda — evidence-based assistant UI
# Every number is produced by research/assistant.py from the loaded survey
# records. An optional Groq layer can only reword a verified answer after
# its figures are replaced locally; with no configured key nothing leaves the
# app and the deterministic answer is shown unchanged.
# -----------------------------------------------------------------------------
ASK_AI_STATUS: dict[str, str] = {
    "disabled": "AI-polished wording is not enabled for this panel yet, so this answer uses "
                "the verified project rules as written.",
    "blocked": "This answer was kept entirely local because its evidence is not approved for "
               "external sharing. No text from it was sent to an AI provider.",
    "rate_limited": "The AI wording service is busy right now. The verified project answer is "
                    "shown unchanged; please try again later.",
    "invalid_key": "AI-polished wording is temporarily unavailable. The verified project answer "
                   "is shown unchanged.",
    "timeout": "The AI wording service did not respond in time. The verified project answer is "
               "shown unchanged.",
    "invalid_response": "The AI wording service returned no usable text. The verified project "
                        "answer is shown unchanged.",
    "unavailable": "The AI wording service is temporarily unavailable. The verified project "
                   "answer is shown unchanged.",
    "guard_rejected": "A protective check stopped the AI wording because it altered a verified "
                      "figure. The verified project answer is shown unchanged.",
}
ASK_GENERAL_STATUS: dict[str, str] = {
    "rate_limited": "The general-knowledge service is busy right now. The offline project "
                    "answer is shown instead.",
    "invalid_key": "The general-knowledge service is temporarily unavailable. The offline "
                   "project answer is shown instead.",
    "timeout": "The general-knowledge service did not respond in time. The offline project "
               "answer is shown instead.",
    "invalid_response": "The general-knowledge service returned no usable text. The offline "
                        "project answer is shown instead.",
    "unavailable": "The general-knowledge service is temporarily unavailable. The offline "
                   "project answer is shown instead.",
    "refused": "For safety, nothing was sent to the AI service for this question. The offline "
               "project answer is shown.",
}
ASK_SUMMARY: str = (
    "Ask questions about Rwanda's financial inclusion and poverty insights."
)
ASK_PAGE_HINTS: dict[str, str] = {
    "Overview": "FI-01",
    "Financial inclusion": "FI-01",
    "Poverty insights": "EI-01",
    "Resilience lab": "FI-03",
}
ASK_HISTORY_LIMIT = 40


def ask_indicator_hint(page: str) -> str:
    """The indicator most relevant to the current page, for “this indicator” questions."""

    return ASK_PAGE_HINTS.get(page, "")


def _ask_chart_figure(chart: AssistantChart) -> go.Figure:
    """Compact bar chart for chat: verified shares, sorted highest to lowest."""

    labels = [name for name, _share in chart.rows]
    values = [share * 100 for _name, share in chart.rows]
    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        marker_color="#059669",
        text=[f"{value:.1f}%" for value in values],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=chart.title, font=dict(size=13, color="#17213d"), x=0, automargin=True),
        yaxis=dict(title="Weighted share", ticksuffix=" %", range=[0, max(values) * 1.18 + 2]),
        height=250,
        margin=dict(l=40, r=16, t=34, b=16),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=10.5, color="#17213d"),
        bargap=0.28,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#dce3ef", tickangle=0)
    fig.update_yaxes(showgrid=True, gridcolor="#e8ecf5", zeroline=False, linecolor="rgba(0,0,0,0)")
    return fig


def ask_bullets(text: str) -> str:
    """Prepare C1 answer text for chat rendering: bullets and readable line breaks."""

    rendered = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("·"):
            rendered.append(f"• {stripped[1:].strip()}")
        elif stripped:
            rendered.append(stripped)
    return "  \n".join(rendered)


def _ask_history() -> list[dict[str, object]]:
    """Conversation messages, kept in session state only (never persisted to disk)."""

    if "ask_messages" not in st.session_state or not isinstance(st.session_state["ask_messages"], list):
        st.session_state["ask_messages"] = []
    return st.session_state["ask_messages"]


def _ask_signature(lens_note: str, view: pd.DataFrame) -> str:
    """Human-readable binding between answers and the context they were computed under."""

    return f"{COMBINED_LABEL_SHORT} · {lens_note if lens_note else f'{len(view):,} records'}"


def _ask_queue(question: str | None = None) -> None:
    """Queue a question from a widget callback.

    Work happens on the next run of the assistant fragment, so the panel can
    show its loading indicator while the answer is assembled. Callbacks stay
    quick and never touch the survey records themselves. A second click while
    a question is already pending is ignored, so one send cannot become two
    provider requests.
    """

    if st.session_state.get("ask_pending"):
        return
    raw = question if question is not None else st.session_state.get("ask_input", "")
    question = str(raw or "").strip()
    if not question:
        st.session_state["ask_hint"] = "Please type a question first — every answer needs one."
        return
    if len(question) > MAX_QUESTION_LENGTH:
        st.session_state["ask_hint"] = (
            f"Please keep the question under {MAX_QUESTION_LENGTH} characters so it can be "
            "read reliably."
        )
        return
    st.session_state.pop("ask_hint", None)
    st.session_state["ask_pending"] = question


def _ask_setting(name: str) -> str:
    """Read an assistant setting from Streamlit secrets, then the environment."""

    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    if not value:
        value = os.environ.get(name, "")
    return str(value or "").strip()


def _ask_provider():
    """Return the optional Groq provider, reading the key without ever exposing it.

    Streamlit secrets are the deployment path; environment variables are the
    local fallback. Missing or malformed configuration means no provider, never
    a silent switch to another service. The provider is created once per
    session so typing in the chat does not open a new client on every rerun.
    """

    provider = st.session_state.get("ask_provider")
    if provider is not None:
        return provider
    key = _ask_setting("GROQ_API_KEY")
    if not key:
        return None
    try:
        provider = get_configured_provider(
            key,
            environ={"GROQ_MODEL": _ask_setting("GROQ_MODEL")},
        )
    except Exception:
        return None
    if provider is not None:
        st.session_state["ask_provider"] = provider
    return provider


def _ask_toggle_panel(open_panel: bool | None = None) -> None:
    """Show, hide or toggle the in-screen panel; the page itself never moves."""

    if open_panel is None:
        st.session_state["ask_open"] = not bool(st.session_state.get("ask_open", False))
    else:
        st.session_state["ask_open"] = bool(open_panel)
    st.session_state.pop("ask_pending", None)  # never leave a stale question queued


def _ask_process(
    question: str,
    df: pd.DataFrame,
    profile: SourceProfile,
    checks: list[QualityCheck],
) -> None:
    """Answer one question and append it to the session-only conversation."""

    messages = _ask_history()
    page = st.session_state.get("workspace_nav", "Overview")
    view = _lens_view(df, page)
    lens_note = lens_signature(view, page) or ""
    signature = _ask_signature(lens_note, view)
    previous = st.session_state.get("ask_context_signature")
    if previous != signature:
        # Never present numbers from an older source or filter set as current ones:
        # mark the boundary explicitly instead of silently mixing contexts.
        if messages and previous:
            messages.append({"role": "switch", "old": previous, "new": signature})
        st.session_state["ask_context_signature"] = signature
    if len(messages) >= ASK_HISTORY_LIMIT:
        del messages[: len(messages) - (ASK_HISTORY_LIMIT - 2)]
    messages.append({"role": "user", "content": question})
    # Chart requests get a verified text answer plus a live group breakdown
    # computed with the same tested functions as every dashboard figure. On
    # this path the AI wording layer is skipped entirely: the message's
    # numbers must equal the dashboard's exactly, with no rewording risk.
    pair = answer_with_chart(
        question,
        frame=view,
        profile=profile,
        source_label=COMBINED_LABEL,
        lens_note=lens_note,
        indicator_hint=ask_indicator_hint(page),
    )
    if pair is not None:
        chart_answer, chart = pair
        messages.append({
            "role": "assistant",
            "content": chart_answer.answer,
            "references": tuple(chart_answer.references),
            "numeric": False,
            "chart": chart,
        })
        st.session_state["ask_input"] = ""
        return
    try:
        answer = answer_question(
            question,
            frame=view,
            profile=profile,
            checks=checks,
            source_label=COMBINED_LABEL,
            lens_note=lens_note,
            page=page,
            indicator_hint=ask_indicator_hint(page),
        )
    except Exception:
        messages.append({
            "role": "assistant",
            "content": "That request could not be completed. Please rephrase it in a few words, "
                       "or read Methods & sources (Page 09) for the full methodology.",
            "references": (),
            "numeric": False,
        })
        st.session_state["ask_input"] = ""
        return
    # Optional Groq layers. Both stay off unless the deployment sets
    # GROQ_API_KEY. The wording layer receives only an already-grounded answer
    # whose figures have been replaced with local tokens, and any provider
    # failure or changed figure returns the deterministic text unchanged.
    # The general-knowledge layer runs only when the offline core has no
    # verified evidence: the typed question alone may then be sent (no survey
    # figure, record or identifier), the answer is labelled as model knowledge,
    # and any provider failure falls back to the deterministic answer.
    provider = _ask_provider()
    if answer.question_kind == "fallback" and provider is not None:
        general_text, general_status = answer_general_with_status(question, provider)
        messages.append({
            "role": "assistant",
            "content": general_text or answer.answer,
            "references": () if general_text else tuple(answer.references),
            "numeric": False,
            "ai_status": general_status,
            "ai_model": getattr(provider, "model", ""),
            "general": bool(general_text),
            "general_attempt": True,
        })
        st.session_state["ask_input"] = ""
        return
    refinement = refine_answer_with_status(question, answer, provider)
    messages.append({
        "role": "assistant",
        "content": refinement.answer.answer,
        "references": tuple(refinement.answer.references),
        "numeric": bool(refinement.answer.numeric_verified),
        "ai_status": refinement.status,
        "ai_model": getattr(provider, "model", "") if provider is not None else "",
        "redacted_figures": refinement.redacted_figures,
    })
    st.session_state["ask_input"] = ""


def _ask_clear() -> None:
    """Start a new conversation; nothing was ever persisted to disk."""

    st.session_state["ask_messages"] = []
    st.session_state.pop("ask_context_signature", None)
    st.session_state.pop("ask_hint", None)
    st.session_state.pop("ask_pending", None)
    st.session_state["ask_input"] = ""


def _ask_render_message(message: dict[str, object]) -> None:
    role = message.get("role")
    if role == "switch":
        old = html.escape(str(message.get("old", "")))
        new = html.escape(str(message.get("new", "")))
        st.markdown(
            f"<div class='ask-switch'>Context changed — answers above belong to "
            f"“{old}”. Answers below use “{new}”.</div>",
            unsafe_allow_html=True,
        )
        return
    with st.chat_message("user" if role == "user" else "assistant",
                         avatar=":material/person:" if role == "user" else ":material/forum:"):
        # User text is escaped: it is data to display, never markup or instructions.
        body = html.escape(str(message.get("content", ""))) if role == "user" else ask_bullets(str(message.get("content", "")))
        st.markdown(f"<div class='ask-q'>{body}</div>" if role == "user" else body, unsafe_allow_html=role == "user")
        if role != "user":
            chart = message.get("chart")
            if isinstance(chart, AssistantChart):
                st.plotly_chart(_ask_chart_figure(chart), key=f"ask_chart_{abs(hash(message.get('content', '')))}", use_container_width=True, config={"displayModeBar": False})
                counts = pd.DataFrame(
                    chart.counts, columns=[chart.group_label.capitalize(), "Weighted share", "Respondents (valid n)"]
                )
                counts["Weighted share"] = [f"{share * 100:.1f}%" for _group_name, share in chart.rows]
                with st.expander("Numbers behind this chart", expanded=False):
                    st.dataframe(counts, hide_index=True, use_container_width=True)
                st.caption("Verified: weighted with the survey's household weight on the active "
                           "source and lens, exactly like every dashboard figure. Bars sorted "
                           "highest to lowest share.")
            references = message.get("references") or ()
            if references:
                # One compact provenance line instead of a citation wall: the
                # scroll area should end on the answer, not on five captions.
                parts = []
                for reference in references:
                    label = str(reference.label)
                    if len(label) > 70:
                        label = label[:67].rstrip() + "…"
                    parts.append(f"{reference.identifier} · {label}")
                st.caption("Sources: " + " — ".join(parts))
            status = message.get("ai_status")
            if message.get("general") is True:
                st.markdown(
                    "<div class='ask-state'>General AI answer — general AI knowledge, "
                    "<strong>not</strong> from this survey's verified data. Survey figures "
                    "belong to the dashboard pages; check anything else before relying on it.</div>",
                    unsafe_allow_html=True,
                )
            elif isinstance(status, str) and message.get("general_attempt") is True and status in ASK_GENERAL_STATUS:
                st.markdown(
                    f"<div class='ask-state'>{html.escape(ASK_GENERAL_STATUS[status])}</div>",
                    unsafe_allow_html=True,
                )
            elif isinstance(status, str) and status == "reworded":
                st.markdown(
                    "<div class='ask-state'>AI-polished wording of the verified project answer — "
                    "no survey figures were sent. Check important details against the sources.</div>",
                    unsafe_allow_html=True,
                )
            elif isinstance(status, str) and status in ASK_AI_STATUS:
                st.markdown(
                    f"<div class='ask-state'>{html.escape(ASK_AI_STATUS[status])}</div>",
                    unsafe_allow_html=True,
                )
            if message.get("numeric"):
                st.markdown("<div class='ask-state'>Figures computed live from the loaded survey "
                            "records with the survey's household weight at the applied lens.</div>",
                            unsafe_allow_html=True)


@st.fragment
def ask_assistant_widget(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    with st.container(key="ask_launcher"):
        st.button(
            "Insight Assistant",
            key="ask_launch",
            icon=":material/forum:",
            help="Open the InsightRwanda AI Assistant. Answers use verified project "
                 "evidence; AI-polished wording runs only when enabled for the deployment.",
            on_click=_ask_toggle_panel,
        )
    if not st.session_state.get("ask_open", False):
        return

    provider = _ask_provider()
    badge = (
        f"Verified project evidence · answers stay local"
        if provider is None else
        f"Verified project evidence · AI wording layer active"
    )

    with st.container(key="ask_panel"):
        st.markdown(
            "<div class='ask-head'><img class='ask-mark' src='" + logo_data_uri() + "' alt='InsightRwanda logo'>"
            "<div><div class='ask-title'>InsightRwanda AI Assistant</div>"
            f"<div class='ask-subtitle'>{ASK_SUMMARY}</div></div></div>",
            unsafe_allow_html=True,
        )
        # Positioned at the panel's top-right by scoped CSS: it stays a real,
        # focusable button on every viewport instead of a clipped column label.
        st.button(
            "Close",
            key="ask_close",
            icon=":material/close:",
            type="tertiary",
            help="Close the assistant; the conversation stays in this session.",
            on_click=_ask_toggle_panel,
            args=(False,),
        )
        st.markdown(f"<div class='ask-badge'>{html.escape(badge)}</div>", unsafe_allow_html=True)
        if provider is None:
            st.caption(
                "AI-polished wording is not enabled for this panel. Answers still use the "
                "verified project evidence."
            )

        pending = st.session_state.pop("ask_pending", None)
        if pending is not None:
            with st.spinner("Checking verified project evidence and preparing the answer…"):
                _ask_process(str(pending), df, profile, checks)

        messages = _ask_history()
        with st.container(key="ask_history_zone", height=320):
            if messages:
                for message in messages:
                    _ask_render_message(message)
            else:
                st.markdown(
                    "<div class='ask-empty'><div class='ask-empty-title'>Ask about verified "
                    "insights</div><div class='ask-empty-copy'>Answers about the evidence come "
                    "from this project's approved definitions and loaded survey records. When a "
                    "question has no verified answer, it may be answered from general knowledge "
                    "and is labelled as such.</div></div>",
                    unsafe_allow_html=True,
                )

        hint = st.session_state.get("ask_hint")
        if hint:
            st.caption(f"ℹ️ {hint}")
        st.session_state.pop("ask_hint", None)

        # st.text_input commits its value exactly when Enter is pressed (or on
        # blur), so on_change submits the question on Enter. There is no
        # on_submit parameter on text_input — that exists only on chat_input.
        st.text_input(
            "Your question",
            key="ask_input",
            placeholder="Ask a question about the available insights...",
            max_chars=MAX_QUESTION_LENGTH,
            label_visibility="collapsed",
            on_change=_ask_queue,
        )
        controls = st.columns([1.4, 1])
        with controls[0]:
            st.button(
                "Send",
                key="ask_send",
                type="primary",
                width="stretch",
                help="Send your question to the evidence assistant.",
                on_click=_ask_queue,
            )
        with controls[1]:
            st.button(
                "New conversation",
                key="ask_clear",
                width="stretch",
                help="Start a new conversation. Nothing is saved to disk.",
                on_click=_ask_clear,
            )
        st.markdown(
            "<div class='ask-foot'>Do not enter personal or household-level details in your "
            "questions.</div>",
            unsafe_allow_html=True,
        )


@st.cache_data(show_spinner="Loading the SPSS source…")
def load_spss_workload(path: Path) -> pd.DataFrame:
    """Load + enrich the SPSS second source, cached like the master load."""

    frame = pipeline_enrich_spss_data(pipeline_load_spss_data(path))
    frame.attrs["source_id_key"] = "spss"
    return frame


@st.cache_data(show_spinner=False)
def load_spss_profile(path: Path) -> SourceProfile:
    return build_spss_profile(path)


@st.cache_data(show_spinner="Building the combined dataset…")
def load_combined_frame() -> pd.DataFrame:
    """One stacked analytical dataset from both supplied sources.

    The two files share no record key, so this pools them as two independent
    samples of the same survey programme on the harmonized master schema — a
    stacked union, never a join. Columns are the union of both sources: the
    FinScope 2020 wave carries NaN for master-only measures, which every
    indicator denominator excludes rather than imputes.
    """

    master = load_master_frame().copy()
    spss = load_spss_workload(SPSS_PATH).copy()
    master["source"] = "master"
    spss["source"] = "spss"
    # Survey year, documented by the supplied release names: the master file is
    # the FinScope 2024 wave; the SPSS file is the FinScope 2020 wave (fieldwork
    # September-November 2019 per official documentation).
    master["survey_year"] = pd.array([2024] * len(master), dtype="Int64")
    spss["survey_year"] = pd.array([2020] * len(spss), dtype="Int64")
    # The head's sex is not observable on the SPSS subset (B0 only records
    # whether the respondent is the head), so it stays missing there.
    spss["head_sex"] = np.nan
    combined = pd.concat([master, spss], ignore_index=True)
    # Unscored resilience rows follow the master convention: 'Unknown', which
    # the band computations exclude from their denominators.
    combined["resilience_band"] = combined["resilience_band"].fillna("Unknown")
    combined.attrs["source_id_key"] = COMBINED_SOURCE_ID
    return combined


@st.cache_data(show_spinner=False)
def load_combined_profile() -> SourceProfile:
    """Source profile for the combined pool, derived from the two source profiles."""

    master_profile = load_source_profile(str(DATA_PATH))
    spss_profile = load_spss_profile(SPSS_PATH)
    return SourceProfile(
        source_id=COMBINED_SOURCE_ID,
        path=f"{master_profile.path} + {spss_profile.path}",
        format="Stacked Stata .dta + SPSS .sav (two independent samples)",
        file_size_mb=round(master_profile.file_size_mb + spss_profile.file_size_mb, 2),
        source_sha256=f"{master_profile.source_sha256[:16]}+{spss_profile.source_sha256[:16]}",
        analysis_version=f"{master_profile.analysis_version} + {spss_profile.analysis_version}",
        rows=master_profile.rows + spss_profile.rows,
        source_variables=master_profile.source_variables + spss_profile.source_variables,
        analytical_variables=len(PIPELINE_COLUMNS),
        mapped_variables=len(PIPELINE_COLUMNS),
        source_release="Not documented in supplied materials",
        population_period="FinScope 2024 wave (master); FinScope 2020 wave (SPSS, fieldwork Sept-Nov 2019)",
        metadata_status="Both sources inspected; embedded variable and value labels available",
        analysis_status="Combined pool ready; measures absent on one file are computed on the records where they are observed",
        authorization_status="Unknown: no authorization record supplied",
        publication_status="Not approved: no disclosure/publication approval supplied",
        documentation=("2026 Hackathon Competition.pdf", "Embedded Stata and SPSS variable/value labels"),
        notes=(
            "The two files share no record key; the combined dataset stacks them as two independent samples on the harmonized variables.",
            "Measures with no counterpart on the SPSS wave (own money, saving behaviour, social support, income bands) stay missing there and are never imputed.",
            "The dashboard does not expose household-level records by default and does not publish the combined file.",
        ),
    )


def load_analysis_workload() -> tuple[pd.DataFrame, SourceProfile, list[QualityCheck]]:
    """Load the single combined dataset with its profile and executed quality checks."""

    df = load_combined_frame()
    profile = load_combined_profile()
    checks = run_quality_checks(
        df,
        source_variable_count=profile.source_variables,
        expected_columns=list(df.columns),
        row_unit="mixed household and individual respondent rows from two pooled samples",
        slice_label=f"the combined harmonized slice ({len(df.columns):,} columns)",
    )
    return df, profile, checks


def main() -> None:
    try:
        pool, profile, checks = load_analysis_workload()
    except Exception as exc:
        st.error(
            "InsightRwanda could not open its survey data, so the dashboard has nothing to show. "
            "Check that the survey files inside the project's data folder are present and readable, "
            "then restart the app.\n\n"
            f"Technical detail: {exc}"
        )
        st.stop()

    # The sidebar's Survey year scopes every page: filter the combined pool once,
    # here, so charts, tables, briefs and the assistant all share the same scope.
    df = apply_year_filter(pool, active_year())

    app_header()
    page = nav(df, profile, checks)
    # The drawer CSS is injected in the main flow AFTER nav() so its style sheet
    # lands after the base CSS in document order (cascade ties are document
    # order) — see the MOBILE_DRAWER_CSS comment for why that is load-bearing.
    if st.session_state.get("mobile_drawer_open", False):
        st.markdown(MOBILE_DRAWER_CSS, unsafe_allow_html=True)
    if page == "Overview":
        render_overview(df)
    elif page == "Financial inclusion":
        render_financial_inclusion(df, profile)
    elif page == "Poverty insights":
        render_poverty_insights(df, profile)
    elif page == "Geographic insights":
        render_regional(df)
    elif page == "Resilience lab":
        render_resilience(df)
    elif page == "Predictive insights":
        render_predictive_insights(df)
    elif page == "Data quality":
        render_quality(df, profile, checks)
    elif page == "Data explorer":
        render_explorer(df, profile)
    elif page == "Methods & sources":
        render_methods(profile, checks)
    elif page == "About the build":
        render_about(df)

    lens_toast(page, lens_signature(_lens_view(df, page), page))
    kpi_countup()
    ask_assistant_widget(df, profile, checks)


if __name__ == "__main__":
    main()
