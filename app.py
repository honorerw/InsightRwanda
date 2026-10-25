from __future__ import annotations

import html
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
    PROVINCES,
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
from research.estimation import (
    BOOTSTRAP_NOTE,
    CONTEXT_ESTIMATES,
    calculate_context_estimate,
    context_weight_distribution,
    official_poverty_status,
    weighted_bootstrap_ci,
)
from research.briefs import (
    LENS_PREFIXES,
    brief_filenames,
    build_page_brief,
    render_brief_pdf,
    render_brief_png,
)
from research.indicators import INDICATORS, calculate_by_group, calculate_indicator
from research.quality import QualityCheck, quality_summary, run_quality_checks
from research.assistant import AssistantAnswer, answer_question
from research.assistant_llm import get_configured_provider, refine_answer


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "dataset.dta"
SPSS_PATH = APP_DIR / "data" / "Rwanda FinScope 2020_Final Data.sav"

SOURCE_OPTIONS = (
    ("master", "dataset.dta (master) · 13,994 households"),
    ("spss", "FinScope 2020 SPSS · 12,480 respondents"),
)
SOURCE_LABELS = {
    "master": "Master Stata survey · 13,994 households",
    "spss": "FinScope 2020 survey · 12,480 respondents",
}
SOURCE_SOURCE_IDs = {"master": "supplied_dataset_dta", "spss": SPSS_SOURCE_ID}


def active_source() -> str:
    return st.session_state.get("analysis_source", "master")

st.set_page_config(
    page_title="InsightRwanda | Research Analytics",
    page_icon="◒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Design system
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Lora:wght@600;700&family=JetBrains+Mono:wght@400;600&display=swap');
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
html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif; color: var(--ink); }
body { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
.stApp { background: var(--paper); }
header[data-testid="stHeader"] { background: transparent !important; }
footer { display: none !important; }
/* Streamlit renders its sidebar expand control inside the top toolbar. Hiding the
   toolbar wrapper would strand users on collapsed sidebars (mobile), so only the
   deploy button, main menu and status spinner are hidden, never the expand control. */
[data-testid="stToolbar"] [data-testid="stBaseButton-header"],
[data-testid="stToolbar"] [data-testid="stMainMenuButton"],
[data-testid="stToolbar"] [data-testid="stStatusWidget"],
#MainMenu { display: none !important; }
[data-testid="stAppViewContainer"] { background: var(--paper); }
.block-container { max-width: 1480px; padding: 1.35rem 3.4rem 4.5rem; }
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

[data-testid="stSidebar"] { background: linear-gradient(180deg, #123c36 0%, #1d5149 100%); border-right: 1px solid #2c6258; min-width: 276px; }
[data-testid="stSidebar"] > div:first-child { padding: 1.1rem .95rem 1.4rem; }
[data-testid="stSidebar"] * { color: #effaf6; }
[data-testid="stSidebar"] hr { border-color: #397368; margin: 1rem 0; }
.side-brand { display:flex; align-items:center; gap:.65rem; padding:.25rem .35rem .85rem; }
.side-mark { width:36px; height:36px; display:flex; align-items:center; justify-content:center; border-radius:11px; background:#9ce0c6; color:#123c36; font-family:'Lora', Georgia, 'Times New Roman', serif; font-weight:700; box-shadow:0 8px 22px rgba(0,0,0,.16); }
.side-name { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:1.02rem; font-weight:600; letter-spacing:-.02em; }
[data-testid="stSidebar"] .side-caption { color:#b3d8cc !important; font-size:.67rem; margin-top:.12rem; }
[data-testid="stSidebar"] .side-label { color:#9bc5b8 !important; font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; text-transform:uppercase; letter-spacing:.11em; font-size:.62rem; font-weight:600; margin:.95rem .35rem .45rem; }
[data-testid="stSidebar"] .side-label:first-of-type { margin-top:.15rem; }
[data-testid="stSidebar"] .stButton { width:100%; margin:.1rem 0; }
[data-testid="stSidebar"] .stButton button { width:100% !important; display:flex; align-items:center; gap:.55rem; justify-content:flex-start; text-align:left; border:1px solid transparent; border-radius:10px; background:transparent; color:#c8e3da; font-size:.795rem; font-weight:600; padding:.58rem .72rem; transition:background .16s ease, border-color .16s ease, color .16s ease, transform .16s ease, box-shadow .16s ease; }
[data-testid="stSidebar"] .stButton button p { font-size:.795rem; font-weight:600; }
[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover, [data-testid="stSidebar"] .stButton button[kind="primary"]:hover { background:#286358; border-color:#4c8b7d; color:#fff; }
[data-testid="stSidebar"] .stButton button[kind="secondary"]:active { transform:translateX(2px) scale(.99); }
[data-testid="stSidebar"] .stButton button[kind="primary"] { background:#9ce0c6; border-color:#bcebd5; color:#123c36; box-shadow:0 5px 14px rgba(0,0,0,.1); }
[data-testid="stSidebar"] .stButton button[kind="primary"]:hover { background:#9ce0c6; color:#123c36; transform:translateX(3px); box-shadow:0 6px 16px rgba(0,0,0,.16); }
.side-card { border:1px solid #397368; background:#205148; border-radius:12px; padding:.75rem .8rem; margin-top:.45rem; }
.side-card-title { font-size:.72rem; font-weight:700; color:#effaf6 !important; }
.side-card-copy { font-size:.67rem; line-height:1.45; color:#c0ded4 !important; margin-top:.28rem; }
.side-status { display:flex; align-items:center; gap:.4rem; font-size:.67rem; color:#c8e3da !important; margin-top:.75rem; }
.side-status-dot { width:7px; height:7px; border-radius:50%; background:#9ce0c6; box-shadow:0 0 0 4px rgba(156,224,198,.18); }
.side-footer { color:#9bc5b8 !important; font-size:.63rem; line-height:1.45; margin:.95rem .35rem 0; }

.app-header { display:flex; align-items:center; justify-content:space-between; padding: .15rem .1rem 1.15rem; border-bottom: 1px solid var(--line); margin-bottom: 1.55rem; }
.brand { display:flex; align-items:center; gap:.75rem; }
.brand-mark { width: 42px; height: 42px; border-radius: 13px; background: linear-gradient(145deg, #5274e6, #172554); color:white; display:flex; align-items:center; justify-content:center; font-family:'Lora', Georgia, 'Times New Roman', serif; font-size: 1.2rem; font-weight:700; box-shadow: 0 8px 20px rgba(49,85,212,.22); }
.brand-name { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:1.16rem; font-weight:600; letter-spacing:-.02em; }
.brand-sub { color: var(--muted); font-size:.72rem; margin-top:.12rem; }
.header-meta { display:flex; align-items:center; gap:.75rem; color:var(--muted); font-size:.77rem; }
.live-pill { display:flex; align-items:center; gap:.38rem; border:1px solid #cbd5ff; color:var(--green-dark); background:#f0f3ff; border-radius:999px; padding:.4rem .72rem; font-weight:700; box-shadow:0 3px 10px rgba(49,85,212,.06); }
.live-dot { width:7px; height:7px; background:#5274e6; border-radius:50%; box-shadow:0 0 0 4px #dbe2ff; }

.eyebrow { font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; font-size:.68rem; text-transform:uppercase; letter-spacing:.12em; color:var(--green); font-weight:500; margin: .55rem 0 .45rem; }
.page-intro { padding: .15rem 0 .2rem; }
.page-title { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:2.45rem; line-height:1.1; letter-spacing:-.03em; font-weight:600; margin:0; color:var(--ink); }
.page-lede { color:var(--muted); font-size:.98rem; line-height:1.55; max-width:720px; margin:.65rem 0 1.2rem; }
.section-title { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:1.08rem; font-weight:600; letter-spacing:-.01em; margin:0; }
.section-note { color:var(--muted); font-size:.77rem; margin:.25rem 0 .9rem; }
.section-head { display:flex; justify-content:space-between; align-items:flex-end; margin: 1.55rem 0 .75rem; }
.mono { font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; }

.filter-shell { background:linear-gradient(135deg, #f0f3ff, #e9edfb); border:1px solid #d5dcf2; border-radius:15px; padding:.85rem 1rem .18rem; margin:.55rem 0 1.25rem; box-shadow:0 5px 18px rgba(37,56,110,.05); }
.filter-label { font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; text-transform:uppercase; letter-spacing:.1em; color:var(--green-dark); font-size:.64rem; margin-bottom:.25rem; font-weight:500; }
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label { color:var(--muted); font-size:.73rem; font-weight:600; }
[data-testid="stSelectbox"] > div > div { background:#fff; border-color:#d5dcef; border-radius:10px; min-height:40px; box-shadow:0 2px 8px rgba(37,56,110,.045); }

.metric-card { background:var(--card); border:1px solid var(--line); border-radius:17px; padding:1.1rem 1.12rem 1rem; min-height:136px; box-shadow:0 7px 22px rgba(37,56,110,.055); transition:transform .18s ease, box-shadow .18s ease; }
.metric-card:hover { transform:translateY(-2px); box-shadow:0 12px 28px rgba(37,56,110,.11); }
.metric-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:.55rem; }
.metric-label { color:var(--muted); font-size:.76rem; font-weight:600; line-height:1.25; }
.metric-icon { width:29px; height:29px; border-radius:9px; display:flex; align-items:center; justify-content:center; font-size:.92rem; }
.metric-value { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:1.84rem; letter-spacing:-.025em; font-weight:600; font-variant-numeric:tabular-nums; }
.metric-foot { color:var(--muted); font-size:.7rem; margin-top:.25rem; line-height:1.25; }
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
.insight-kicker { color:#b7c6ff; font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; text-transform:uppercase; letter-spacing:.1em; font-size:.63rem; }
.insight-text { font-family:'Lora', Georgia, 'Times New Roman', serif; font-size:1.08rem; font-weight:600; line-height:1.33; margin-top:.45rem; }
.insight-foot { color:#d7defb; font-size:.7rem; line-height:1.35; margin-top:.55rem; }

.callout { border:1px solid #d1dafa; border-left:3px solid var(--green); background:#f0f3ff; border-radius:0 12px 12px 0; padding:.88rem 1rem; color:#354263; font-size:.84rem; line-height:1.5; }
.callout strong { color:var(--green-dark); }
.tag { display:inline-block; padding:.25rem .5rem; border-radius:999px; background:#eef1fb; color:var(--green-dark); font-size:.69rem; font-weight:700; margin-right:.3rem; }
.legend-row { display:flex; gap:1rem; flex-wrap:wrap; color:var(--muted); font-size:.72rem; margin:.2rem 0 .5rem; }
.legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:.28rem; }

.profile-panel { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1.15rem 1.2rem; }
.profile-row { display:flex; align-items:center; gap:.75rem; margin:.78rem 0; }
.profile-name { width:148px; font-size:.76rem; color:var(--muted); }
.profile-track { flex:1; height:9px; background:#e9edf7; border-radius:99px; overflow:hidden; }
.profile-fill { height:100%; border-radius:99px; background:linear-gradient(90deg, #3155d4, #8ca4f0); }
.profile-number { width:48px; text-align:right; font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; font-size:.72rem; color:var(--green-dark); }

.stDataFrame { border:1px solid var(--line); border-radius:13px; overflow:hidden; box-shadow:0 4px 16px rgba(37,56,110,.035); }
[data-testid="stDataFrame"] { background:#fff; }
div[data-testid="stExpander"] { border-color:var(--line); border-radius:12px; background:#fff; }
.download-row { display:flex; justify-content:flex-end; margin-top:.45rem; }
button[kind="secondary"] { border-radius:9px; border-color:#cbd5ee; color:var(--green-dark); font-weight:600; }

.footer-note { color:#5f6866; font-size:.7rem; padding-top:1.7rem; border-top:1px solid var(--line); margin-top:2.5rem; line-height:1.5; }
button, [role="button"] { font-family:'Inter', 'Segoe UI', system-ui, Arial, sans-serif; }
/* Ask InsightRwanda — header entry pill + conversation surfaces */
.st-key-ask_zone { margin: -.9rem 0 .55rem; display: flex; justify-content: flex-end; }
.st-key-ask_zone button { border-radius: 999px; font-weight: 600; font-size: .78rem; padding: .38rem 1rem; }
.ask-intro { font-size: .8rem; color: var(--muted); margin: 0 0 .6rem; }
.ask-q { background: var(--paper); border: 1px solid var(--line); border-radius: 10px 10px 3px 10px;
  padding: .55rem .7rem; font-size: .84rem; max-width: 92%; word-wrap: break-word; }
.ask-switch { background: #faf6ea; border: 1px dashed #cbbf8f; border-radius: 8px; padding: .45rem .65rem;
  font-size: .75rem; color: #63593a; }
.ask-state { font-size: .72rem; color: var(--muted); }

/* Accessibility: a clearly visible keyboard-focus indicator in both color zones.
   The blue works on the light surface; the dark sidebar rail needs the mint accent instead. */
a:focus-visible, button:focus-visible, [role="button"]:focus-visible, [role="radio"]:focus-visible,
[role="option"]:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible,
summary:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--green) !important; outline-offset: 2px; }
[data-testid="stSidebar"] button:focus-visible, [data-testid="stSidebar"] input:focus-visible { outline-color: #9ce0c6 !important; }
@media (max-width: 1100px) { .block-container { padding-left:1.5rem; padding-right:1.5rem; } }
@media (max-width: 900px) { .block-container { padding: .8rem 1rem 3rem; } .page-title { font-size:1.95rem; } .header-meta { display:none; } .stRadio label { padding:.42rem .48rem; font-size:.73rem; } .metric-card { min-height:122px; } }
/* Small-screen refinement: shared layout + Overview (phones, 360–640px) */
@media (max-width: 640px) {
  /* The top strip hosts Streamlit's sidebar expand control; keep page content clear of it */
  .block-container { padding: 4.55rem .85rem 2.6rem; }
  .app-header { flex-wrap: wrap; align-items:flex-start; gap:.3rem; }
  .brand-mark { width:36px; height:36px; border-radius:11px; font-size:1.02rem; }
  .brand-name { font-size:1.02rem; }
  .page-title { font-size:1.7rem; }
  .metric-card { padding:.9rem .85rem .85rem; min-height:116px; }
  .metric-value { font-size:1.5rem; }
  .metric-foot { font-size:.67rem; }
  .filter-shell { padding:.7rem .7rem .1rem; }
  .insight-card { min-height:auto; }
  .chart-card { padding:.9rem .9rem .7rem; }
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


def pct(value: float, decimals: int = 0) -> str:
    return "—" if pd.isna(value) else f"{value * 100:.{decimals}f}%"


# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
def app_header(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    st.markdown(
        f"""
        <div class="app-header">
          <div class="brand">
            <div class="brand-mark">◒</div>
            <div><div class="brand-name">InsightRwanda</div><div class="brand-sub">Financial inclusion &amp; poverty research · NISR Hackathon 2026</div></div>
          </div>
          <div class="header-meta"><div class="live-pill"><span class="live-dot"></span> Survey data: {SOURCE_LABELS[active_source()]}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Ask InsightRwanda — header entry point for the offline evidence assistant.
    # Main content placement keeps the sidebar's exact ten-button contract intact.
    with st.container(key="ask_zone"):
        if st.button("Ask InsightRwanda", key="ask_launch", icon=":material/forum:", help="Ask questions about the survey evidence in simple English"):
            ask_insightrwanda_modal(df, profile, checks)


def nav(df: pd.DataFrame) -> str:
    """Left rail as a coherent system: brand, three labelled nav groups with
    numbered entries matching each page's own '0N /' eyebrow, then context cards."""
    nav_pages = [
        "Overview", "Financial inclusion", "Poverty insights", "Geographic insights",
        "Resilience lab", "Predictive insights", "Data quality", "Data explorer",
        "Methods & sources", "About the build",
    ]
    nav_groups = [
        ("Evidence", nav_pages[:6], "What the survey data shows"),
        ("Governance", nav_pages[6:8], "Checks, access and data protection"),
        ("How it is built", nav_pages[8:], "Methods, sources and background"),
    ]
    numbers = {page: f"{index:02d}" for index, page in enumerate(nav_pages, start=1)}
    current = st.session_state.get("workspace_nav", "Overview")
    if current not in nav_pages:
        current = "Overview"
    current_source = st.session_state.get("analysis_source", "master")
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="side-mark">◒</div><div><div class="side-name">InsightRwanda</div><div class="side-caption">Research analytics platform</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-label">Source</div>', unsafe_allow_html=True)
        keys = [key for key, _label in SOURCE_OPTIONS]
        labels = [label for _key, label in SOURCE_OPTIONS]
        choice = st.radio(
            "Source",
            labels,
            index=keys.index(current_source) if current_source in keys else 0,
            key="analysis_source_widget",
            label_visibility="collapsed",
        )
        st.session_state["analysis_source"] = keys[labels.index(choice)]
        for group_label, group_pages, group_hint in nav_groups:
            st.markdown(f'<div class="side-label">{group_label}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="side-caption">{group_hint}</div>', unsafe_allow_html=True)
            for page in group_pages:
                pressed = st.button(
                    f"{numbers[page]} · {page}",
                    key=f"nav_{numbers[page]}",
                    type="primary" if page == current else "secondary",
                    width="stretch",
                )
                if pressed:
                    current = page
                    st.session_state["workspace_nav"] = page
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
    return current


def page_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="page-intro"><div class="eyebrow">{eyebrow}</div><h1 class="page-title">{title}</h1><p class="page-lede">{lede}</p></div>', unsafe_allow_html=True)


def filter_bar(df: pd.DataFrame, key_prefix: str = "main") -> pd.DataFrame:
    st.markdown('<div class="filter-shell"><div class="filter-label">Narrow the results</div><div class="section-note" style="margin:-.15rem 0 .45rem">Pick one area or group of people; every chart on this page updates to match.</div>', unsafe_allow_html=True)
    # Keys are scoped per source so a source switch never leaves a stale value stuck.
    tag = active_source()
    if tag == "master":
        sk = key_prefix
    else:
        sk = f"{key_prefix}_{tag}"
    c1, c2, c3, c4 = st.columns([1.05, 1.2, .9, .9])
    province_options = ["All provinces"] + sorted(PROVINCES.values())
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
    st.markdown('</div>', unsafe_allow_html=True)
    return filtered


def has_data(frame: pd.DataFrame) -> bool:
    if frame.empty:
        st.warning(
            "No records match the filters you chose.\n\n"
            "Widen one filter at a time: set **Province** back to *All provinces*, "
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
        font=dict(family="Inter, Arial, sans-serif", color="#66718b", size=11),
        showlegend=legend,
        legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="#17213d", font_size=12, font_family="Inter"),
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


def data_footer(frame: pd.DataFrame, label: str = "Filtered view") -> None:
    source_name = SOURCE_SOURCE_IDs.get(active_source(), "unknown")
    st.markdown(
        f'<div class="footer-note"><strong>{label}:</strong> {len(frame):,} records in this view · estimates are weighted with the survey\'s household weight so larger areas and groups count their fair share · survey data: <strong>{SOURCE_LABELS[active_source()]}</strong> <span class="mono">({source_name})</span>. These figures describe what the data shows; they do not prove that one thing causes another.</div>',
        unsafe_allow_html=True,
    )


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
        except (ValueError, KeyError) as error:
            st.error(f"Prediction could not be produced: {error}")

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
        st.markdown('<div class="callout"><strong>Not reproducible on the active source.</strong><br>The predictive workflow trains against the resilience band, and three of its four lens components (own money, saving behaviour, social support) have no label-verified counterpart on this source. Load the master Stata source to run the model readout; nothing is imputed here.</div>', unsafe_allow_html=True)
        data_footer(view)
        return

    render_model_evaluation_tab(view)
    record = evaluate_model_workload(view)
    if record is None:
        return

    render_threshold_tradeoff(view, record)
    render_subgroup_performance(view, record)
    data_footer(view)


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
    m1, m2, m3, m4 = st.columns(4)
    with m1: metric_card("Active formal access", pct(active), "Use a bank, SACCO or mobile-money service today · shows how far formal finance reaches", "↗", "green")
    with m2: metric_card("Mobile money", pct(mobile), "Send or receive money by phone · shows today's main digital money route", "⌁", "green", delay=1)
    with m3: metric_card("Emergency buffer", pct(emergency), "Have money saved for a surprise expense · shows who can absorb a shock without borrowing", "◌", "yellow", delay=2)
    with m4: metric_card("Income pressure", pct(pressure), "Income does not cover monthly living costs · shows who is under day-to-day strain", "!", "rose", delay=3)
    st.markdown('<div class="legend-row">Card icons: <strong>↗</strong> access · <strong>⌁</strong> digital money · <strong>◌</strong> financial buffer · <strong>!</strong> watch-out</div>', unsafe_allow_html=True)

    overview_tabs = st.tabs(["National signal", "Opportunity map"])
    with overview_tabs[0]:
        section_head("The national signal, at a glance", "Weighted household estimates · use the hover state to inspect exact values")
        left, right = st.columns([1.25, .75])
        with left:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Access is broad; buffers are thinner</div><div class="section-note">Share of respondents meeting each indicator</div>', unsafe_allow_html=True)
            labels_available = [("Active formal access", "active_access"), ("Mobile money", "mobile_money"), ("Own money", "owns_money"), ("Saves", "saves_regularly"), ("Emergency fund", "emergency_fund"), ("Internet access", "internet_access")]
            labels_available = [(label, m) for label, m in labels_available if m in view]
            labels = [label for label, _m in labels_available]
            measures = [m for _label, m in labels_available]
            values = [weighted_rate(view, view[m]) * 100 for m in measures]
            colors = ["#3155d4", "#5274e6", "#8ca4f0", "#c5d1fb", "#e5ae2f", "#de7c3f"]
            fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors, text=[f"{x:.0f}%" for x in values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
            fig.update_xaxes(range=[0, 108], ticksuffix="%", showgrid=True, gridcolor="#e8ecf5", title="Share of respondents", title_font=dict(size=10, color="#66718b"))
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(chart_theme(fig, 328), width="stretch", config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with right:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            if "resilience_band" not in view:
                st.markdown('<div class="section-title">Household resilience mix</div><div class="section-note">Not reproducible on this source: three of the four resilience-lens capabilities have no counterpart here. The mix is withheld rather than approximated.</div>', unsafe_allow_html=True)
            else:
                band_counts = weighted_distribution(view, "resilience_band").reindex(["Resilient", "Watch", "Priority"]).fillna(0)
                fig = go.Figure(go.Pie(labels=band_counts.index, values=band_counts.values, hole=.68, marker=dict(colors=["#3155d4", "#e5ae2f", "#d95362"], line=dict(color="#fff", width=3)), textinfo="none", hovertemplate="%{label}: %{percent}<extra></extra>"))
                resilient_flag = view["resilience_band"].eq("Resilient").astype(float).mask(view["resilience_band"].eq("Unknown"))
                fig.add_annotation(text=f"{pct(weighted_rate(view, resilient_flag))}<br><span style='font-size:10px;color:#66718b'>resilient</span>", x=.5, y=.5, showarrow=False, font=dict(size=20, color="#17213d", family="Lora, Georgia, serif"))
                st.plotly_chart(chart_theme(fig, 228), width="stretch", config={"displayModeBar": False})
                st.markdown('<div class="legend-row"><span><span class="legend-dot" style="background:#3155d4"></span>Resilient</span><span><span class="legend-dot" style="background:#e5ae2f"></span>Watch</span><span><span class="legend-dot" style="background:#d95362"></span>Priority</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with overview_tabs[1]:
        section_head("The opportunity map", "A first read for policy and programme teams")
        a, b, c = st.columns(3)
        with a:
            st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 01 · access</div><div class="insight-text">{pct(mobile)} use mobile money today.</div><div class="insight-foot">Mobile money is the clearest delivery rail for reaching households already inside the formal ecosystem.</div></div>', unsafe_allow_html=True)
        with b:
            st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 02 · resilience</div><div class="insight-text">{pct(1 - emergency)} report no emergency fund.</div><div class="insight-foot">The inclusion gap is not only account ownership; it is the ability to absorb a shock without selling assets or borrowing.</div></div>', unsafe_allow_html=True)
        with c:
            st.markdown(f'<div class="insight-card"><div class="insight-kicker">Signal 03 · digital</div><div class="insight-text">{pct(1 - weighted_rate(view, view["internet_access"]))} lack internet access.</div><div class="insight-foot">Digital-first interventions need a low-bandwidth or assisted pathway to avoid excluding rural and lower-income users.</div></div>', unsafe_allow_html=True)

    data_footer(view)


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

    with st.expander("Cross-source agreement — dataset.dta (master) vs FinScope 2020 SPSS", expanded=False):
        st.caption(
            "Both supplied sources are loaded through their own pipelines and the shared indicator rules are "
            "applied to each. Differences can be real (different survey questions, filters and row units) — "
            "this table reports agreement, it does not merge the sources."
        )
        rows = []
        for indicator_id in INDICATORS:
            row = {"ID": indicator_id, "Indicator": INDICATORS[indicator_id].title}
            for tag, frame in (("master", load_master_frame()), ("spss", load_spss_workload(SPSS_PATH))):
                try:
                    result = calculate_indicator(frame, indicator_id)
                    row[tag] = pct(result.estimate, 2)
                except ValueError:
                    row[tag] = "not reproducible"
            rows.append(row)
        agreement = pd.DataFrame(rows)
        agreement["Both present"] = agreement.apply(
            lambda r: r["master"] not in ("not reproducible",) and r["spss"] not in ("not reproducible",), axis=1
        )
        st.dataframe(agreement, hide_index=True, width="stretch", height=260)
        st.caption("Row unit differs between sources (household vs individual). Weights differ. Treat large gaps as source-definition findings, not as errors.")


@st.cache_data(show_spinner=False)
def load_master_frame(path: Path = DATA_PATH) -> pd.DataFrame:
    """Cached master frame for cross-source comparisons."""

    return pipeline_enrich_analysis_data(pipeline_load_analysis_data(path))


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
                metric_card(INDICATORS[indicator_id].title, "—", "not reproducible on this source", "⊘", "rose", delay=index)
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
                f'<div class="chart-card"><div class="eyebrow">{selected} · indicator card</div><div class="section-title" style="font-size:1.18rem">{INDICATORS[selected].title}</div><p class="section-note" style="font-size:.84rem;line-height:1.5">{INDICATORS[selected].definition}</p><div class="callout"><strong>Not reproducible on the active source.</strong> No variable on this source carries the label-verified semantics of the documented source variable(s) <code>{missing_vars}</code>. This is a documented scope reduction: the estimate is withheld rather than approximated or imputed.</div></div>',
                unsafe_allow_html=True,
            )
        else:
            definition = result.definition
            st.markdown(
                f'<div class="chart-card"><div class="eyebrow">{definition.indicator_id} · indicator card</div><div class="section-title" style="font-size:1.18rem">{definition.title}</div><p class="section-note" style="font-size:.84rem;line-height:1.5">{definition.definition}</p><div class="metric-value" style="color:#172554">{pct(result.estimate, 1)}</div><div class="section-note">{result.numerator_n:,} positive records / {result.denominator_n:,} valid records · weighted population sum {result.weight_sum:,.0f}</div><div class="callout"><strong>Calculation.</strong> {definition.method}<br><br><strong>Source variables.</strong> {', '.join(definition.source_variables)}<br><br><strong>Limitation.</strong> {' '.join(definition.limitations)}</div></div>',
                unsafe_allow_html=True,
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
            metric_card("Income pressure", "—", "not reproducible on this source", "⊘", "rose")
        else:
            metric_card("Income pressure", pct(pressure.estimate), "not an official poverty measure", "≈", "orange")
    with b:
        if difficulty is None:
            metric_card("Emergency money is difficult", "—", "not reproducible on this source", "⊘", "rose", delay=1)
        else:
            metric_card("Emergency money is difficult", pct(difficulty.estimate), "self-reported liquidity stress", "◌", "yellow", delay=1)

    render_estimation_section(view)
    st.markdown('<div class="footer-note">These context estimates should not be relabelled as poverty, poverty risk, or welfare status without a documented methodology. Source: supplied Stata dataset; release period not documented.</div>', unsafe_allow_html=True)


def render_estimation_section(view: pd.DataFrame) -> None:
    """Estimation layer: labelled context estimates, bootstrap intervals and the official unlock contract."""

    section_head(
        "Exploratory estimates — labelled, never official",
        "Income-band context from the embedded Stata band labels · bootstrap intervals are NOT survey-design standard errors",
    )
    context_cards = st.columns(3)
    for index, (slot, estimate_id) in enumerate(zip(context_cards, CONTEXT_ESTIMATES)):
        try:
            result = calculate_context_estimate(view, estimate_id)
        except ValueError:
            result = None
        with slot:
            if result is None:
                metric_card(CONTEXT_ESTIMATES[estimate_id].title, "—", "not reproducible on this source", "⊘", "rose")
            else:
                metric_card(
                    CONTEXT_ESTIMATES[estimate_id].title,
                    pct(result["estimate"], 1),
                    f"weighted population {result['weight_sum']:,.0f}",
                    "≡" if estimate_id == "EI-02" else "≣",
                    "orange" if estimate_id == "EI-02" else "yellow",
                    delay=index,
                )

    band_tab, interval_tab, contract_tab = st.tabs(["Income-band detail", "Bootstrap intervals", "Official estimation contract"])
    bands_available = "n11" in view and "n12" in view
    with band_tab:
        if bands_available:
            monthly = context_weight_distribution(view, "n11").sort_values(ascending=False)
            annual = context_weight_distribution(view, "n12").sort_values(ascending=False)
            st.markdown('<div class="chart-card"><div class="section-title">Monthly personal income bands</div><div class="section-note">Weighted population by band · don\'t-know/refusal excluded</div>', unsafe_allow_html=True)
            left, right = st.columns(2)
            with left:
                fig = go.Figure(go.Bar(y=monthly.index, x=monthly.values, orientation="h", marker_color="#de7c3f", text=[f"{v:,.0f}" for v in monthly.values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:,.0f}<extra>weighted pop</extra>"))
                st.plotly_chart(chart_theme(fig, 420), width="stretch", config={"displayModeBar": False})
            with right:
                fig = go.Figure(go.Bar(y=annual.index, x=annual.values, orientation="h", marker_color="#8ca4f0", text=[f"{v:,.0f}" for v in annual.values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:,.0f}<extra>weighted pop</extra>"))
                st.plotly_chart(chart_theme(fig, 420), width="stretch", config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
            caveats = " ".join(limitation for estimate_id in CONTEXT_ESTIMATES for limitation in CONTEXT_ESTIMATES[estimate_id].limitations)
            st.markdown(f'<div class="callout"><strong>Why this is not poverty.</strong><br>These bands are self-reported and band-coded; they are neither household consumption nor a welfare aggregate. They stay financial-context statistics. {caveats}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="callout"><strong>Not reproducible on the active source.</strong><br>The label-verified income-band variables (n11, n12) have no counterpart on this source, so the band distribution is withheld rather than approximated from other questions.</div>', unsafe_allow_html=True)

    with interval_tab:
        rows = []
        for indicator_id in INDICATORS:
            try:
                ci = weighted_bootstrap_ci(view, indicator_id, n_boot=300, seed=42)
            except ValueError:
                continue  # indicator not reproducible on this source
            rows.append({
                "ID": indicator_id,
                "Indicator": INDICATORS[indicator_id].title,
                "Point": ci.estimate,
                "Low (95%)": ci.low,
                "High (95%)": ci.high,
            })
        if rows:
            interval_table = pd.DataFrame(rows).set_index("ID")
            interval_table[["Point", "Low (95%)", "High (95%)"]] = interval_table[["Point", "Low (95%)", "High (95%)"]].map(lambda v: f"{v * 100:.1f}%")
            st.dataframe(interval_table, width="stretch", height=240)
            st.markdown(f'<div class="callout"><strong>Method.</strong><br>{BOOTSTRAP_NOTE}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="callout"><strong>Not reproducible on the active source.</strong><br>None of the documented indicators can be computed here, so no intervals are shown. Nothing is imputed to fill the table.</div>', unsafe_allow_html=True)

    with contract_tab:
        status = official_poverty_status()
        contract = pd.DataFrame(
            [(req, "missing — estimation blocked") for req in status.missing],
            columns=["Required input", "Status"],
        )
        st.dataframe(contract, hide_index=True, width="stretch", height=250)
        preview_col, cta_col = st.columns([1, 1.4])
        with preview_col:
            if st.button("How can this be unlocked?", key="open_poverty_modal"):
                official_poverty_contract_modal()
        with cta_col:
            st.markdown('<div class="callout"><strong>Unlock rule.</strong><br>An official poverty estimation runs only when every input above is supplied explicitly in <span class="mono">research/estimation.py::official_poverty_status</span> by an authorised data steward. Nothing is inferred or defaulted.</div>', unsafe_allow_html=True)


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

    section_head("District explorer", "Sorted by active formal access · filter the geography above to zoom in")
    district_table = weighted_group(view, "district", "active_access").rename(columns={"value": "active_access", "denominator_n": "active_n"})
    district_emergency = weighted_group(view, "district", "emergency_fund").rename(columns={"value": "emergency_fund", "denominator_n": "emergency_n"})
    district_table = district_table.merge(district_emergency, on="group", how="left").sort_values("active_access", ascending=False)
    dleft, dright = st.columns([1.4, .6])
    with dleft:
        display_table = district_table.copy()
        display_table["Active access"] = display_table["active_access"].map(pct)
        display_table["Emergency fund"] = display_table["emergency_fund"].map(pct)
        st.dataframe(display_table[["group", "Active access", "active_n", "Emergency fund", "emergency_n"]].rename(columns={"group": "District", "active_n": "Access n", "emergency_n": "Emergency n"}), hide_index=True, width="stretch", height=300)
    with dright:
        best = district_table.iloc[0] if len(district_table) else None
        worst = district_table.iloc[-1] if len(district_table) else None
        if best is not None and worst is not None:
            st.markdown(f'<div class="callout"><strong>Decision cue.</strong><br><br>{best["group"]} leads this filtered view on active access at {pct(best["active_access"])}.<br><br>{worst["group"]} is the lowest at {pct(worst["active_access"])}; pair financial access expansion with a buffer-building offer.</div>', unsafe_allow_html=True)

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
                setting_split = weighted_group(dview.assign(priority=dview["resilience_band"].eq("Priority").astype(float)), "setting", "priority")
                fig = go.Figure(go.Bar(x=setting_split["group"], y=setting_split["value"] * 100, marker_color=["#d95362" if s == "Rural" else "#f0a1ad" for s in setting_split["group"]], text=[f"{v:.0f}%" for v in setting_split["value"] * 100], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
                fig.update_yaxes(range=[0, max(30, float(setting_split["value"].max() * 100 + 10))], ticksuffix="%") if len(setting_split) else None
                st.markdown(f'<div class="section-title">{drill_target}: where does the priority share sit?</div><div class="section-note">Resilience Priority band share by urban / rural setting inside this district</div>', unsafe_allow_html=True)
                st.plotly_chart(chart_theme(fig, 230), width="stretch", config={"displayModeBar": False})
            else:
                st.markdown(f'<div class="section-title">{drill_target}: priority-share split</div><div class="section-note">Not reproducible on this source: the resilience band needs the own-money, saving-behaviour and social-support capabilities, which are absent here.</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            gap_note = f"{drill_target} sits {drill['active_access'] - national_access:+.1%} versus the national weighted mean for active access in this filtered view, and there is no gap signal designed yet to say whether buffer building or digital access would be the better first intervention."
            priority_note = f"PRIORITY band inside {drill_target} is shown above by setting." if "resilience_band" in view else "The resilience-band split is not reproducible on the active source; consult page 05 when the master Stata source is loaded."
            st.markdown(f'<div class="callout"><strong>Drill-down read.</strong><br><br>{priority_note}{gap_note}</div>', unsafe_allow_html=True)
    data_footer(view, "Regional view")


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
        st.markdown('<div class="callout"><strong>The resilience lens is not reproducible on the active source.</strong><br>The lens needs four observed capabilities; this source carries only the emergency-funds one. Own money, saving behaviour and a social-support contact have no label-verified counterpart here, so the Priority / Watch / Resilient band is withheld rather than approximated. Load the master Stata source for the full lens; the one component this source does support is shown below.</div>', unsafe_allow_html=True)
        difficult_available = weighted_rate(view, view["emergency_difficult"]) if "emergency_difficult" in view else None
        c1, c2 = st.columns(2)
        with c1:
            if difficult_available is None:
                metric_card("Emergency feels difficult", "—", "not reproducible on this source", "⊘", "rose")
            else:
                metric_card("Emergency feels difficult", pct(difficult_available), "say raising 56,000 Rwf would be difficult (the lens component this source does support)", "◌", "orange")
        with c2:
            metric_card("Resilience band", "—", "needs all four lens capabilities · withheld", "⊘", "rose", delay=1)
        data_footer(view, "Resilience view · lens withheld on this source")
        return
    risk = weighted_rate(view, view["resilience_band"].eq("Priority").astype(float))
    watch = weighted_rate(view, view["resilience_band"].eq("Watch").astype(float))
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
        setting = weighted_group(view.assign(priority=view["resilience_band"].eq("Priority").astype(float)), "setting", "priority")
        fig = go.Figure(go.Bar(x=setting["group"], y=setting["value"] * 100, marker_color=["#d95362" if x == "Rural" else "#f0a1ad" for x in setting["group"]], text=[f"{v:.0f}%" for v in setting["value"] * 100], textposition="outside", cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>"))
        fig.update_yaxes(range=[0, max(30, float(setting["value"].max() * 100 + 10))], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, 245), width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("What action could look like", "Translate signals into a practical programme conversation")
    x, y, z = st.columns(3)
    with x:
        st.markdown('<div class="chart-card"><span class="tag">Buffer</span><div class="section-title" style="margin-top:.55rem">Emergency savings nudges</div><div class="section-note">Prioritise households with no rainy-day funds and difficult access to 56,000 Rwf. Consider goal-based savings, commitment products and VUP-linked onboarding.</div></div>', unsafe_allow_html=True)
    with y:
        st.markdown('<div class="chart-card"><span class="tag">Access</span><div class="section-title" style="margin-top:.55rem">Assisted digital rails</div><div class="section-note">Use mobile money as an entry point, but pair it with USSD, agent support and clear-language financial education where internet access is limited.</div></div>', unsafe_allow_html=True)
    with z:
        st.markdown('<div class="chart-card"><span class="tag">Protection</span><div class="section-title" style="margin-top:.55rem">Shock-responsive finance</div><div class="section-note">Connect social protection and micro-insurance conversations to the shocks households report — especially when social networks are the only fallback.</div></div>', unsafe_allow_html=True)

    data_footer(view, "Resilience view")


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
    if not aggregate_release_allowed(profile):
        gate_col, why_col = st.columns([1.55, 1])
        with gate_col:
            st.markdown('<div class="callout"><strong>Aggregate explorer is governance-gated.</strong><br>No explicit authorization and disclosure/publication approval record is available for this source. The app will not produce an arbitrary filtered aggregate table or export until an authorised data steward supplies both approvals and an approved disclosure rule.</div>', unsafe_allow_html=True)
        with why_col:
            if st.button("Why is this withheld?", key="open_gate_modal"):
                explorer_gate_modal(profile)
        data_footer(view, "Explorer view · output withheld")
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
    data_footer(view, "Explorer view")


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

    section_head("Quality limitations", "What remains outside the executed checks")
    st.markdown('<div class="chart-card"><div class="section-note" style="font-size:.84rem;line-height:1.65">The workspace does not contain the fieldwork protocol, sample design, questionnaire version, enumerator quality controls, non-response adjustments, geographic boundary release, disclosure review, or an approved publication record. These should be supplied before an official public research release.</div></div>', unsafe_allow_html=True)


def render_methods(profile: SourceProfile, checks: list[QualityCheck]) -> None:
    page_intro(
        "09 / Methods & sources",
        "A traceable route from source file to displayed result.",
        "This page separates what is known about the supplied materials, what the application calculated, and what still needs research governance or documentation before publication.",
    )
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown(f'<div class="chart-card"><div class="eyebrow">Source profile</div><div class="section-title" style="font-size:1.25rem">Survey data · {SOURCE_LABELS[active_source()]}</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="chart-card"><div class="eyebrow">Evidence chain</div><div class="section-title" style="font-size:1.25rem">Five steps, one audit trail</div>', unsafe_allow_html=True)
        for no, title, copy in [
            ("01", "Inspect", "Read the original Stata metadata and confirm the supplied file is present."),
            ("02", "Load", "Read the selected source columns with explicit failure on missing variables."),
            ("03", "Validate", "Run schema, identifier, weight, code, geography and missingness checks."),
            ("04", "Calculate", "Apply the indicator definition, denominator and household weight."),
            ("05", "Explain", "Display the estimate with source variables, scope and limitations."),
        ]:
            st.markdown(f'<div style="display:flex;gap:.8rem;padding:.72rem 0;border-bottom:1px solid #e8ecf5"><div class="mono" style="color:#3155d4;font-size:.72rem;padding-top:.1rem">{no}</div><div><div style="font-weight:700;font-size:.84rem">{title}</div><div style="font-size:.73rem;color:#66718b;line-height:1.4;margin-top:.18rem">{copy}</div></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Available source materials", "What was actually found in the workspace")
    st.dataframe(pd.DataFrame({"Material": list(profile.documentation), "Use": ["Competition scope and evaluation criteria", "Embedded survey variable and value labels"]}), hide_index=True, width="stretch")
    st.markdown('<div class="callout"><strong>Governance boundary.</strong><br>The application distinguishes file existence, metadata inspection, permitted analysis, validation and public publication. The supplied workspace contains no authorization or publication approval record, so the app is suitable for internal analysis and demonstration, not an approved public statistical release.</div>', unsafe_allow_html=True)

    section_head("Indicator methodology", "Verified source mapping for the current financial-inclusion slice")
    method_rows = [{"ID": d.indicator_id, "Definition": d.definition, "Valid responses": d.valid_response_rule, "Calculation": d.method, "Limitations": " ".join(d.limitations)} for d in INDICATORS.values()]
    st.dataframe(pd.DataFrame(method_rows), hide_index=True, width="stretch", height=320)
    st.markdown(f'<div class="footer-note">Quality checks executed: {len(checks)} · source profile is cached from the supplied file · original research materials remain unchanged.</div>', unsafe_allow_html=True)


def render_about(df: pd.DataFrame) -> None:
    page_intro(
        "10 / About the build",
        "A competition-ready decision tool, grounded in NISR data.",
        "InsightRwanda translates a large financial-inclusion survey into a presentation-ready interface for policy teams, financial-service providers and civil-society partners.",
    )
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown('<div class="chart-card"><div class="eyebrow">The challenge</div><div class="section-title" style="font-size:1.3rem">From “who is included?” to “who can absorb a shock?”</div><p class="section-note" style="font-size:.86rem;line-height:1.6">The 2026 NISR Big Data Hackathon calls for solutions that address Financial Inclusion & Poverty Reduction with tangible value for vulnerable households, policy makers and civil society. This prototype focuses on the gap between access to a financial channel and meaningful household resilience.</p><div class="callout"><strong>Product thesis.</strong> Financial inclusion becomes more actionable when teams can see the intersection of access, buffers, digital reach, geography and household vulnerability in one place.</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="chart-card"><div class="eyebrow">What is inside</div><div class="section-title" style="font-size:1.3rem">A compact, auditable stack</div>', unsafe_allow_html=True)
        for no, title, desc in [("01", "Overview", "National signal with weighted KPI cards and the headline inclusion / resilience gap."), ("02", "Regional pulse", "Province and district comparison for targeting and delivery planning."), ("03", "Resilience lab", "Transparent composite lens and action prompts for household protection."), ("04", "Data explorer", "Inspect aggregate evidence; exports remain approval-gated.")]:
            st.markdown(f'<div style="display:flex;gap:.8rem;padding:.75rem 0;border-bottom:1px solid #e8ecf5"><div class="mono" style="color:#3155d4;font-size:.72rem;padding-top:.1rem">{no}</div><div><div style="font-weight:700;font-size:.84rem">{title}</div><div style="font-size:.73rem;color:#66718b;line-height:1.4;margin-top:.18rem">{desc}</div></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Method and transparency", "The dashboard is intentionally descriptive")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown('<div class="chart-card"><div class="section-title">Weighted estimates</div><div class="section-note">All headline rates use <span class="mono">hh_wt</span>, the household weight supplied in the Stata file. This improves representativeness relative to a raw row count.</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown('<div class="chart-card"><div class="section-title">Resilience lens</div><div class="section-note">The score is the mean of four binary capabilities: emergency funds, own money, saving at least sometimes and a potential social support contact. It is a prioritisation lens, not a poverty line or modelled probability.</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown('<div class="chart-card"><div class="section-title">Data integrity</div><div class="section-note">Missing responses are excluded from each indicator’s denominator. The explorer makes the filtered sample visible so users can assess coverage before interpreting a result.</div></div>', unsafe_allow_html=True)

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
    province = st.session_state.get(f"{prefix}_province", "All provinces")
    district = st.session_state.get(f"{prefix}_district", "All districts")
    setting = st.session_state.get(f"{prefix}_setting", "All settings")
    sex = st.session_state.get(f"{prefix}_sex", "All respondents")
    parts = [part for part in (
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
    pre = df if province == "All provinces" else df[df["province"].eq(province)]
    return pipeline_filter_analysis_data(
        pre,
        district=None if district == "All districts" else district,
        setting=None if setting == "All settings" else setting,
        respondent_sex=None if sex == "All respondents" else sex,
    )


@st.dialog("Official poverty estimation — unlock contract", width="large")
def official_poverty_contract_modal() -> None:
    status = official_poverty_status()
    st.markdown(
        "<p class='section-note'>A data steward unlocks the official estimate only by supplying every "
        "input below explicitly in <span class='mono'>research/estimation.py::official_poverty_status</span> "
        "— nothing is inferred or defaulted. The app blocks this on purpose: a poverty rate without a "
        "documented line, aggregate and variance method would be fabrication.</p>",
        unsafe_allow_html=True,
    )
    contract = pd.DataFrame(
        [(req, "missing — estimation blocked") for req in status.missing],
        columns=["Required input", "Status"],
    )
    if status.supplied:
        for name, value in status.supplied.items():
            contract = pd.concat([contract, pd.DataFrame([[name, f"supplied: {value}"]], columns=contract.columns)], ignore_index=True)
    st.dataframe(contract, hide_index=True, width="stretch")
    st.markdown(
        "<div class='callout'><strong>State.</strong> " + ("All six inputs supplied — estimation can run." if status.ready else f"{len(status.missing)} of 6 inputs still missing.") + "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Close", key="modal_close_poverty"):
        return


@st.dialog("Why the explorer withholds aggregates", width="large")
def explorer_gate_modal(profile: SourceProfile) -> None:
    released = aggregate_release_allowed(profile)
    st.markdown(
        f"<p class='section-note'>The gate is coded, tested software — not a disclaimer. "
        "<span class='mono'>aggregate_release_allowed()</span> returns <span class='mono'>True</span> only when both "
        "the authorization record and the publication record begin with \"Approved\". Current state:</p>",
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
# Ask InsightRwanda — offline, evidence-based assistant UI (Phase C2)
# Every number is produced by research/assistant.py from the loaded survey
# records; the UI only presents provenance. No LLM, no network, no secrets.
# -----------------------------------------------------------------------------
ASK_SUGGESTIONS: tuple[str, ...] = (
    "Why is there no official poverty estimate?",
    "Explain financial inclusion in simple English.",
    "Where does this percentage come from?",
    "What does this indicator mean?",
    "What checks were performed on the data?",
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


def _ask_signature(source_key: str, lens_note: str, view: pd.DataFrame) -> str:
    """Human-readable binding between answers and the context they were computed under."""

    return f"{SOURCE_LABELS[source_key]} · {lens_note if lens_note else f'{len(view):,} records'}"


def _ask_submit(question: str | None, df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    """Send handler (runs before the dialog fragment rerenders, so it may mutate state)."""

    question = (question if question is not None else st.session_state.get("ask_input", "") or "").strip()
    if not question:
        st.session_state["ask_hint"] = "Please type a question first — every answer needs one."
        return
    st.session_state.pop("ask_hint", None)
    messages = _ask_history()
    page = st.session_state.get("workspace_nav", "Overview")
    view = _lens_view(df, page)
    lens_note = lens_signature(view, page) or ""
    signature = _ask_signature(active_source(), lens_note, view)
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
    try:
        answer = answer_question(
            question,
            frame=view,
            profile=profile,
            checks=checks,
            source_label=SOURCE_LABELS[active_source()],
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
    # Phase C3 — optional AI explanation layer. Disabled with no approved
    # provider: get_configured_provider() is None and refine_answer returns
    # the deterministic answer unchanged, with its original references.
    answer = refine_answer(question, answer, get_configured_provider())
    messages.append({
        "role": "assistant",
        "content": answer.answer,
        "references": tuple(answer.references),
        "numeric": bool(answer.numeric_verified),
    })
    st.session_state["ask_input"] = ""


def _ask_clear() -> None:
    """Explicit conversation reset from the user."""

    st.session_state["ask_messages"] = []
    st.session_state.pop("ask_context_signature", None)
    st.session_state.pop("ask_hint", None)
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
    with st.chat_message("user" if role == "user" else "assistant", avatar="🗣" if role == "user" else "◒"):
        # User text is escaped: it is data to display, never markup or instructions.
        body = html.escape(str(message.get("content", ""))) if role == "user" else ask_bullets(str(message.get("content", "")))
        st.markdown(f"<div class='ask-q'>{body}</div>" if role == "user" else body, unsafe_allow_html=role == "user")
        if role != "user":
            references = message.get("references") or ()
            for reference in references:
                detail = f" — {reference.detail}" if reference.detail else ""
                st.caption(f"{reference.identifier} · {reference.label}{detail}")
            if message.get("numeric"):
                st.markdown("<div class='ask-state'>Figures computed live from the loaded survey "
                            "records with the survey's household weight at the applied lens.</div>",
                            unsafe_allow_html=True)


@st.dialog("Ask InsightRwanda", width="large")
def ask_insightrwanda_modal(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    st.caption(
        "Offline evidence-based assistant — answers come from this project's verified results and "
        "approved definitions, not a connected AI service. Evidence is missing or unpublished: the "
        "assistant says so instead of guessing."
    )
    messages = _ask_history()
    if not messages:
        st.markdown(
            "<div class='ask-intro'>Ask questions about the research, indicators, survey findings and "
            "methodology in simple English. Numbers come straight from the loaded records; source "
            "references appear under every answer.</div>",
            unsafe_allow_html=True,
        )

    for message in messages:
        _ask_render_message(message)

    hint = st.session_state.get("ask_hint")
    if hint:
        st.caption(f"ℹ️ {hint}")
    st.session_state.pop("ask_hint", None)

    st.pills(
        "Suggested questions",
        list(ASK_SUGGESTIONS),
        selection_mode="single",
        default=[],
        key="ask_suggestions",
        help="Tap a suggestion to ask it instantly.",
        on_change=_ask_suggestion_change,
        args=(df, profile, checks),
        wrap=True,
    )

    st.text_input("Your question", key="ask_input", placeholder="e.g. What does FI-02 mean in simple English?")
    row = st.columns([1, 1, 1])
    with row[0]:
        st.button("Send question", key="ask_send", type="primary", width="stretch",
                  on_click=_ask_submit, args=(None, df, profile, checks))
    with row[2]:
        st.button("Clear conversation", key="ask_clear", width="stretch", on_click=_ask_clear)


def _ask_suggestion_change(df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    """Suggested-question handler: submit the selected suggestion and reset the pills."""

    selected = st.session_state.get("ask_suggestions") or []
    if selected:
        _ask_submit(str(selected[0]), df, profile, checks)
    st.session_state["ask_suggestions"] = []


@st.dialog("Brief preview — what the export contains", width="large")
def brief_preview_modal(brief, names: dict[str, str]) -> None:
    st.markdown(f"<div class='eyebrow'>{brief.eyebrow} · {brief.lens_note}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='section-title'>{brief.narrative}</div><p class='section-note' style='font-size:.84rem'>{brief.caution}</p>", unsafe_allow_html=True)
    st.dataframe(
        pd.DataFrame(brief.kpis, columns=["Value", "Figure", "Detail"]),
        hide_index=True,
        width="stretch",
        height=min(460, 39 * max(len(brief.kpis), 2) + 38),
    )
    st.markdown(
        "<p class='section-note'>Use the download buttons below the preview. The brief is aggregate-only: "
        "no household records, no gated exports — safe to share with judges and partners.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Close", key="modal_close_brief"):
        return


def render_brief_export(page: str, df: pd.DataFrame, profile: SourceProfile, checks: list[QualityCheck]) -> None:
    """One non-gated, take-away brief for this page: aggregate-only PNG + one-page PDF."""

    view = _lens_view(df, page)
    context_record = evaluate_model_workload(view) if page == "Predictive insights" else None
    try:
        brief = build_page_brief(page, view, profile, checks, context_record)
    except Exception as exc:  # briefs must never break a page
        st.warning(f"Brief export unavailable for this page: {exc}")
        return
    names = brief_filenames(brief)
    pdf_bytes, png_bytes = render_brief_pdf(brief), render_brief_png(brief)
    preview_col, pdf_col, png_col = st.columns([.9, 1.05, 1.05])
    with preview_col:
        if st.button("Preview first", key="open_brief_modal"):
            brief_preview_modal(brief, names)
    with pdf_col:
        st.download_button(
            "Download one-page brief (PDF)",
            data=pdf_bytes,
            file_name=names["pdf"],
            mime="application/pdf",
            width="stretch",
        )
    with png_col:
        st.download_button(
            "Download one-page brief (PNG)",
            data=png_bytes,
            file_name=names["png"],
            mime="image/png",
            width="stretch",
        )
    st.markdown(
        '<div class="footer-note">The brief is built from aggregate values only — no household records, exports or edit of the source. It reflects the analysis lens currently selected above.</div>',
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


SPSS_EXPECTED_COLUMNS = [
    "key", "row_id", "hh_wt", "pop_wt", "hh_size", "psu", "a1", "a2", "a3", "b0", "b2",
    "c14_5", "e7", "ef9", "qf4_01", "qf4_03", "qf4_04", "qf4_05", "qf4_06",
    "e9b", "active_access", "mobile_money", "bank_use", "sacco_use",
    "emergency_fund", "internet_access", "income_pressure",
]


def load_analysis_workload() -> tuple[pd.DataFrame, SourceProfile, list[QualityCheck]]:
    """Load the active source with its profile and executed quality checks."""

    if active_source() == "spss":
        df = load_spss_workload(SPSS_PATH)
        profile = load_spss_profile(SPSS_PATH)
        checks = run_quality_checks(
            df,
            source_variable_count=profile.source_variables,
            expected_columns=SPSS_EXPECTED_COLUMNS,
            row_unit="individual respondent",
            slice_label="the documented second-source subset mapped to the master schema",
        )
    else:
        raw = pipeline_load_analysis_data(DATA_PATH)
        df = pipeline_enrich_analysis_data(raw)
        df.attrs["source_id_key"] = "master"
        profile = load_source_profile(str(DATA_PATH))
        checks = run_quality_checks(df, source_variable_count=profile.source_variables)
    return df, profile, checks


def main() -> None:
    try:
        df, profile, checks = load_analysis_workload()
    except Exception as exc:
        st.error(
            "InsightRwanda could not open its survey data, so the dashboard has nothing to show. "
            "Check that the survey files inside the project's data folder are present and readable, "
            "then restart the app.\n\n"
            f"Technical detail: {exc}"
        )
        st.stop()

    app_header(df, profile, checks)
    page = nav(df)
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

    render_brief_export(page, df, profile, checks)
    lens_toast(page, lens_signature(_lens_view(df, page), page))
    kpi_countup()


if __name__ == "__main__":
    main()
