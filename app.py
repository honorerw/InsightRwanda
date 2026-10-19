from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research.catalog import SourceProfile, aggregate_release_allowed, build_source_profile
from research.data_pipeline import (
    ANALYSIS_COLUMNS as PIPELINE_COLUMNS,
    PROVINCES,
    aggregate_weighted_measure,
    enrich_analysis_data as pipeline_enrich_analysis_data,
    filter_analysis_data as pipeline_filter_analysis_data,
    load_analysis_data as pipeline_load_analysis_data,
)
from research.indicators import INDICATORS, calculate_by_group, calculate_indicator
from research.quality import QualityCheck, quality_summary, run_quality_checks


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "dataset.dta"

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
html, body, [class*="css"] { font-family: 'Lato', 'Arial', sans-serif; color: var(--ink); }
body { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
.stApp { background: var(--paper); }
header, footer, #MainMenu, [data-testid="stToolbar"] { display: none !important; }
[data-testid="stAppViewContainer"] { background: var(--paper); }
.block-container { max-width: 1480px; padding: 1.35rem 3.4rem 4.5rem; }
.main .block-container { animation: rise-in .35s ease-out both; }
@keyframes rise-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

[data-testid="stSidebar"] { background: linear-gradient(180deg, #123c36 0%, #1d5149 100%); border-right: 1px solid #2c6258; min-width: 276px; }
[data-testid="stSidebar"] > div:first-child { padding: 1.1rem .95rem 1.4rem; }
[data-testid="stSidebar"] * { color: #effaf6; }
[data-testid="stSidebar"] hr { border-color: #397368; margin: 1rem 0; }
.side-brand { display:flex; align-items:center; gap:.65rem; padding:.25rem .35rem .85rem; }
.side-mark { width:36px; height:36px; display:flex; align-items:center; justify-content:center; border-radius:11px; background:#9ce0c6; color:#123c36; font-family:Georgia, 'Times New Roman', serif; font-weight:800; box-shadow:0 8px 22px rgba(0,0,0,.16); }
.side-name { font-family:Georgia, 'Times New Roman', serif; font-size:1rem; font-weight:700; letter-spacing:-.025em; }
[data-testid="stSidebar"] .side-caption { color:#b3d8cc !important; font-size:.67rem; margin-top:.12rem; }
[data-testid="stSidebar"] .side-label { color:#9bc5b8 !important; font-family:'DejaVu Sans Mono','Liberation Mono',monospace; text-transform:uppercase; letter-spacing:.11em; font-size:.61rem; font-weight:500; margin:.2rem .35rem .45rem; }
[data-testid="stSidebar"] .stRadio, [data-testid="stSidebar"] .stRadio > div, [data-testid="stSidebar"] .stRadio > div > div, [data-testid="stSidebar"] .stRadio [role="radiogroup"] { width:100% !important; max-width:none !important; }
[data-testid="stSidebar"] .stRadio [role="radiogroup"] { display:flex !important; flex-direction:column !important; align-items:stretch !important; }
[data-testid="stSidebar"] .stRadio label { display:flex !important; width:100% !important; max-width:none !important; align-self:stretch !important; position:relative; overflow:hidden; border:1px solid transparent; border-radius:10px; padding:.6rem .65rem; color:#c8e3da; font-size:.8rem; font-weight:600; transition:background .16s ease, border-color .16s ease, color .16s ease, transform .16s ease, box-shadow .16s ease; }
[data-testid="stSidebar"] .stRadio label:not(:has(input:checked)):hover { background:#286358; border-color:#4c8b7d; color:#fff; transform:translateX(4px); box-shadow:0 5px 14px rgba(0,0,0,.12); }
[data-testid="stSidebar"] .stRadio label:not(:has(input:checked)):active { background:#9ce0c6; border-color:#bcebd5; color:#123c36; transform:translateX(2px) scale(.98); box-shadow:inset 0 2px 5px rgba(18,60,54,.18); }
[data-testid="stSidebar"] .stRadio label:has(input:checked) { width:calc(100% + 1.9rem) !important; margin-left:-.95rem; background:#9ce0c6; border-color:#bcebd5; color:#123c36; box-shadow:0 5px 14px rgba(0,0,0,.1); }
[data-testid="stSidebar"] .stRadio label > div:first-child { display:none; }
.side-card { border:1px solid #397368; background:#205148; border-radius:12px; padding:.75rem .8rem; margin-top:.45rem; }
.side-card-title { font-size:.72rem; font-weight:700; color:#effaf6 !important; }
.side-card-copy { font-size:.67rem; line-height:1.45; color:#c0ded4 !important; margin-top:.28rem; }
.side-status { display:flex; align-items:center; gap:.4rem; font-size:.67rem; color:#c8e3da !important; margin-top:.75rem; }
.side-status-dot { width:7px; height:7px; border-radius:50%; background:#9ce0c6; box-shadow:0 0 0 4px rgba(156,224,198,.18); }
.side-footer { color:#9bc5b8 !important; font-size:.63rem; line-height:1.45; margin:.95rem .35rem 0; }

.app-header { display:flex; align-items:center; justify-content:space-between; padding: .15rem .1rem 1.15rem; border-bottom: 1px solid var(--line); margin-bottom: 1.55rem; }
.brand { display:flex; align-items:center; gap:.75rem; }
.brand-mark { width: 42px; height: 42px; border-radius: 13px; background: linear-gradient(145deg, #5274e6, #172554); color:white; display:flex; align-items:center; justify-content:center; font-family:Georgia, 'Times New Roman', serif; font-size: 1.25rem; font-weight:800; box-shadow: 0 8px 20px rgba(49,85,212,.22); }
.brand-name { font-family:Georgia, 'Times New Roman', serif; font-size:1.16rem; font-weight:700; letter-spacing:-.02em; }
.brand-sub { color: var(--muted); font-size:.72rem; margin-top:.12rem; }
.header-meta { display:flex; align-items:center; gap:.75rem; color:var(--muted); font-size:.77rem; }
.live-pill { display:flex; align-items:center; gap:.38rem; border:1px solid #cbd5ff; color:var(--green-dark); background:#f0f3ff; border-radius:999px; padding:.4rem .72rem; font-weight:700; box-shadow:0 3px 10px rgba(49,85,212,.06); }
.live-dot { width:7px; height:7px; background:#5274e6; border-radius:50%; box-shadow:0 0 0 4px #dbe2ff; }

.stRadio > div { gap: .3rem; }
.stRadio [role="radiogroup"] { gap: .25rem; }
.stRadio label { border-radius: 8px; padding: .43rem .75rem; color: var(--muted); font-size:.83rem; font-weight:600; transition:.15s ease; }
.stRadio label:hover { background: #eef1fb; color: var(--ink); }
.stRadio label:has(input:checked) { color: var(--green-dark); background: var(--mint); }
.stRadio label > div:first-child { display:none; }

.eyebrow { font-family:'DejaVu Sans Mono','Liberation Mono',monospace; font-size:.68rem; text-transform:uppercase; letter-spacing:.12em; color:var(--green); font-weight:500; margin: .55rem 0 .45rem; }
.page-intro { padding: .15rem 0 .2rem; }
.page-title { font-family:Georgia, 'Times New Roman', serif; font-size:2.55rem; line-height:1.08; letter-spacing:-.045em; font-weight:700; margin:0; color:var(--ink); }
.page-lede { color:var(--muted); font-size:.98rem; line-height:1.55; max-width:720px; margin:.65rem 0 1.2rem; }
.section-title { font-family:Georgia, 'Times New Roman', serif; font-size:1.08rem; font-weight:700; letter-spacing:-.015em; margin:0; }
.section-note { color:var(--muted); font-size:.77rem; margin:.25rem 0 .9rem; }
.section-head { display:flex; justify-content:space-between; align-items:flex-end; margin: 1.55rem 0 .75rem; }
.mono { font-family:'DejaVu Sans Mono','Liberation Mono',monospace; }

.filter-shell { background:linear-gradient(135deg, #f0f3ff, #e9edfb); border:1px solid #d5dcf2; border-radius:15px; padding:.85rem 1rem .18rem; margin:.55rem 0 1.25rem; box-shadow:0 5px 18px rgba(37,56,110,.05); }
.filter-label { font-family:'DejaVu Sans Mono','Liberation Mono',monospace; text-transform:uppercase; letter-spacing:.1em; color:var(--green-dark); font-size:.64rem; margin-bottom:.25rem; }
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label { color:var(--muted); font-size:.73rem; font-weight:600; }
[data-testid="stSelectbox"] > div > div { background:#fff; border-color:#d5dcef; border-radius:10px; min-height:40px; box-shadow:0 2px 8px rgba(37,56,110,.045); }

.metric-card { background:var(--card); border:1px solid var(--line); border-radius:17px; padding:1.1rem 1.12rem 1rem; min-height:136px; box-shadow:0 7px 22px rgba(37,56,110,.055); transition:transform .18s ease, box-shadow .18s ease; }
.metric-card:hover { transform:translateY(-2px); box-shadow:0 12px 28px rgba(37,56,110,.11); }
.metric-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:.55rem; }
.metric-label { color:var(--muted); font-size:.76rem; font-weight:600; line-height:1.25; }
.metric-icon { width:29px; height:29px; border-radius:9px; display:flex; align-items:center; justify-content:center; font-size:.92rem; }
.metric-value { font-family:Georgia, 'Times New Roman', serif; font-size:1.84rem; letter-spacing:-.04em; font-weight:700; font-variant-numeric:tabular-nums; }
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
.insight-kicker { color:#b7c6ff; font-family:'DejaVu Sans Mono','Liberation Mono',monospace; text-transform:uppercase; letter-spacing:.1em; font-size:.63rem; }
.insight-text { font-family:Georgia, 'Times New Roman', serif; font-size:1.08rem; font-weight:700; line-height:1.33; margin-top:.45rem; }
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
.profile-number { width:48px; text-align:right; font-family:'DejaVu Sans Mono','Liberation Mono',monospace; font-size:.72rem; color:var(--green-dark); }

.stDataFrame { border:1px solid var(--line); border-radius:13px; overflow:hidden; box-shadow:0 4px 16px rgba(37,56,110,.035); }
[data-testid="stDataFrame"] { background:#fff; }
div[data-testid="stExpander"] { border-color:var(--line); border-radius:12px; background:#fff; }
.download-row { display:flex; justify-content:flex-end; margin-top:.45rem; }
button[kind="secondary"] { border-radius:9px; border-color:#cbd5ee; color:var(--green-dark); font-weight:600; }

.footer-note { color:#7c8983; font-size:.7rem; padding-top:1.7rem; border-top:1px solid var(--line); margin-top:2.5rem; line-height:1.5; }
button, [role="button"] { font-family:'Lato', 'Arial', sans-serif; }
@media (max-width: 1100px) { .block-container { padding-left:1.5rem; padding-right:1.5rem; } }
@media (max-width: 900px) { .block-container { padding: .8rem 1rem 3rem; } .page-title { font-size:1.95rem; } .header-meta { display:none; } .stRadio label { padding:.42rem .48rem; font-size:.73rem; } .metric-card { min-height:122px; } }
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
def app_header() -> None:
    st.markdown(
        """
        <div class="app-header">
          <div class="brand">
            <div class="brand-mark">◒</div>
            <div><div class="brand-name">InsightRwanda</div><div class="brand-sub">Financial inclusion &amp; poverty research · NISR Hackathon 2026</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def nav(df: pd.DataFrame) -> str:
    pages = [
        "Overview", "Financial inclusion", "Poverty insights", "Geographic insights",
        "Resilience lab", "Data quality", "Data explorer", "Methods & sources",
    ]
    with st.sidebar:
        st.markdown(
            '<div class="side-brand"><div class="side-mark">◒</div><div><div class="side-name">InsightRwanda</div><div class="side-caption">Research analytics platform</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-label">Workspace</div>', unsafe_allow_html=True)
        choice = st.radio("Workspace", pages, label_visibility="collapsed", key="workspace_nav")
        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown('<div class="side-label">Dataset status</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="side-card"><div class="side-card-title">Dataset ready</div><div class="side-card-copy">The supplied Stata dataset is loaded read-only for weighted analytical work.</div><div class="side-status"><span class="side-status-dot"></span>{len(df):,} records loaded</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-card"><div class="side-card-title">Hackathon track</div><div class="side-card-copy">Track 2 · Financial Inclusion &amp; Poverty Reduction</div></div>', unsafe_allow_html=True)
        st.markdown('<div class="side-label" style="margin-top:1.1rem">Reading the dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="side-card-copy" style="padding:0 .35rem">Rates are weighted with <span class="mono">hh_wt</span>. Missing responses are excluded from each indicator. The resilience lens is descriptive, not a causal model.</div>', unsafe_allow_html=True)
        st.markdown('<div class="side-footer">Built for evidence-led decisions in Rwanda.<br>Source: supplied NISR dataset.</div>', unsafe_allow_html=True)
    return choice


def page_intro(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(f'<div class="page-intro"><div class="eyebrow">{eyebrow}</div><h1 class="page-title">{title}</h1><p class="page-lede">{lede}</p></div>', unsafe_allow_html=True)


def filter_bar(df: pd.DataFrame, key_prefix: str = "main") -> pd.DataFrame:
    st.markdown('<div class="filter-shell"><div class="filter-label">Analysis lens</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.05, 1.2, .9, .9])
    province_options = ["All provinces"] + sorted(PROVINCES.values())
    province = c1.selectbox("Province", province_options, key=f"{key_prefix}_province")
    pre = df if province == "All provinces" else df[df["province"].eq(province)]
    district_options = ["All districts"] + sorted(pre["district"].dropna().unique().tolist())
    district = c2.selectbox("District", district_options, key=f"{key_prefix}_district")
    setting = c3.selectbox("Setting", ["All settings", "Urban", "Rural"], key=f"{key_prefix}_setting")
    sex = c4.selectbox("Respondent", ["All respondents", "Female", "Male"], key=f"{key_prefix}_sex")
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
        st.warning("No records match this combination of filters. Try widening the analysis lens.")
        return False
    return True


def metric_card(label: str, value: str, foot: str, icon: str, color: str = "green") -> None:
    st.markdown(
        f'<div class="metric-card {color}"><div class="metric-top"><div class="metric-label">{label}</div><div class="metric-icon">{icon}</div></div><div class="metric-value">{value}</div><div class="metric-foot">{foot}</div></div>',
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
        font=dict(family="Lato, Arial, sans-serif", color="#66718b", size=11),
        showlegend=legend,
        legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="#17213d", font_size=12, font_family="Lato"),
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
    st.markdown(
        f'<div class="footer-note"><strong>{label}:</strong> {len(frame):,} unweighted records · weighted estimates use <span class="mono">hh_wt</span> · source: supplied NISR Stata dataset (<span class="mono">dataset.dta</span>). Figures are descriptive associations, not causal estimates.</div>',
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
MODEL_FEATURES = [
    ("Household size", "hh_size"),
    ("Respondent sex", "b2"),
    ("Setting", "a6"),
    ("Internet access", "c14_5"),
    ("Phone ownership", "f3"),
    ("Mobile money use", "qf4_05"),
]


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -35, 35)))


def train_priority_model(frame: pd.DataFrame) -> dict[str, object] | None:
    """Fit a small weighted logistic model for exploratory prioritisation."""

    target_mask = frame["resilience_band"].isin(["Priority", "Watch", "Resilient"])
    feature_columns = [column for _, column in MODEL_FEATURES if column in frame]
    if not target_mask.any() or len(feature_columns) < 3:
        return None

    model_frame = frame.loc[target_mask, feature_columns + ["resilience_band", "hh_wt"]].copy()
    target = model_frame["resilience_band"].eq("Priority").astype(float).to_numpy()
    if target.min() == target.max():
        return None

    raw_features = model_frame[feature_columns].apply(pd.to_numeric, errors="coerce")
    weights = pd.to_numeric(model_frame["hh_wt"], errors="coerce").fillna(1).clip(lower=0).to_numpy()
    weights = np.where(weights > 0, weights, 1.0)
    rng = np.random.default_rng(42)
    order = rng.permutation(len(model_frame))
    split = max(1, min(len(order) - 1, int(len(order) * .8)))
    train_idx, test_idx = order[:split], order[split:]

    medians = raw_features.iloc[train_idx].median().fillna(0)
    means = raw_features.iloc[train_idx].fillna(medians).mean()
    scales = raw_features.iloc[train_idx].fillna(medians).std().replace(0, 1).fillna(1)
    matrix = ((raw_features.fillna(medians) - means) / scales).to_numpy(dtype=float)
    train_x = np.column_stack([np.ones(len(train_idx)), matrix[train_idx]])
    test_x = np.column_stack([np.ones(len(test_idx)), matrix[test_idx]])
    train_y, test_y = target[train_idx], target[test_idx]
    train_w = weights[train_idx]

    coefficients = np.zeros(train_x.shape[1], dtype=float)
    normalizer = max(float(train_w.sum()), 1.0)
    for _ in range(500):
        probability = _sigmoid(train_x @ coefficients)
        gradient = (train_x.T @ ((probability - train_y) * train_w)) / normalizer
        gradient[1:] += .01 * coefficients[1:]
        coefficients -= .12 * gradient

    test_probability = _sigmoid(test_x @ coefficients)
    accuracy = float(np.average((test_probability >= .5) == test_y, weights=weights[test_idx])) if len(test_idx) else float("nan")
    return {
        "features": feature_columns,
        "medians": medians.to_dict(),
        "means": means.to_dict(),
        "scales": scales.to_dict(),
        "coefficients": coefficients,
        "accuracy": accuracy,
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
    }


def predict_priority_probability(model: dict[str, object], values: dict[str, float]) -> float:
    feature_columns = model["features"]
    row = np.array([
        (values.get(column, model["medians"].get(column, 0)) - model["means"].get(column, 0)) / model["scales"].get(column, 1)
        for column in feature_columns
    ], dtype=float)
    coefficients = np.asarray(model["coefficients"], dtype=float)
    return float(_sigmoid(np.array([1.0, *row]) @ coefficients))


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
    with m1: metric_card("Active formal access", pct(active), "currently use a bank, digital, MFI, mobile money or SACCO channel", "↗", "green")
    with m2: metric_card("Mobile money anchor", pct(mobile), "currently use a mobile money operator", "⌁", "green")
    with m3: metric_card("Emergency buffer", pct(emergency), "have set aside rainy-day funds", "◌", "yellow")
    with m4: metric_card("Income pressure", pct(pressure), "income does not cover living costs monthly or often", "!", "rose")

    overview_tabs = st.tabs(["National signal", "Opportunity map", "Train & predict"])
    with overview_tabs[0]:
        section_head("The national signal, at a glance", "Weighted household estimates · use the hover state to inspect exact values")
        left, right = st.columns([1.25, .75])
        with left:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Access is broad; buffers are thinner</div><div class="section-note">Share of respondents meeting each indicator</div>', unsafe_allow_html=True)
            labels = ["Active formal access", "Mobile money", "Own money", "Saves", "Emergency fund", "Internet access"]
            measures = ["active_access", "mobile_money", "owns_money", "saves_regularly", "emergency_fund", "internet_access"]
            values = [weighted_rate(view, view[m]) * 100 for m in measures]
            colors = ["#3155d4", "#5274e6", "#8ca4f0", "#c5d1fb", "#e5ae2f", "#de7c3f"]
            fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors, text=[f"{x:.0f}%" for x in values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
            fig.update_xaxes(range=[0, 108], ticksuffix="%", showgrid=True, gridcolor="#e8ecf5")
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(chart_theme(fig, 328), use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with right:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Household resilience mix</div><div class="section-note">A transparent composite of four observed capabilities</div>', unsafe_allow_html=True)
            band_counts = weighted_distribution(view, "resilience_band").reindex(["Resilient", "Watch", "Priority"]).fillna(0)
            fig = go.Figure(go.Pie(labels=band_counts.index, values=band_counts.values, hole=.68, marker=dict(colors=["#3155d4", "#e5ae2f", "#d95362"], line=dict(color="#fff", width=3)), textinfo="none", hovertemplate="%{label}: %{percent}<extra></extra>"))
            resilient_flag = view["resilience_band"].eq("Resilient").astype(float).mask(view["resilience_band"].eq("Unknown"))
            fig.add_annotation(text=f"{pct(weighted_rate(view, resilient_flag))}<br><span style='font-size:10px;color:#66718b'>resilient</span>", x=.5, y=.5, showarrow=False, font=dict(size=20, color="#17213d", family="Georgia"))
            st.plotly_chart(chart_theme(fig, 228), use_container_width=True, config={"displayModeBar": False})
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

    with overview_tabs[2]:
        section_head("Train a prioritisation model", "Estimate the likelihood that a household falls into the Priority resilience band")
        st.caption("This exploratory model is trained on the current filtered view. It is descriptive, not causal, and should not be used as an eligibility decision on its own.")
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
            train_and_predict = st.form_submit_button("Train model and predict", type="primary")

        if train_and_predict:
            model = train_priority_model(view)
            if model is None:
                st.session_state.pop("priority_model", None)
                st.session_state.pop("priority_prediction", None)
                st.error("The filtered view does not contain enough target variation to train this model.")
            else:
                prediction_values = {
                    "hh_size": float(household_size),
                    "b2": 1.0 if respondent_sex == "Male" else 2.0,
                    "a6": 1.0 if setting == "Urban" else 2.0,
                    "c14_5": 1.0 if internet_access == "Yes" else 2.0,
                    "f3": 1.0 if phone_ownership == "Yes" else 2.0,
                    "qf4_05": 1.0 if mobile_money_use == "Yes" else 2.0,
                }
                st.session_state["priority_model"] = model
                st.session_state["priority_prediction"] = predict_priority_probability(model, prediction_values)

        model = st.session_state.get("priority_model")
        prediction = st.session_state.get("priority_prediction")
        if model is not None and prediction is not None:
            result_left, result_right = st.columns(2)
            with result_left:
                st.metric("Predicted Priority probability", f"{prediction:.1%}")
            with result_right:
                st.metric("Holdout accuracy", f"{model['accuracy']:.1%}")
            st.caption(f"Trained on {model['train_rows']:,} records and evaluated on {model['test_rows']:,} held-out records using household weights.")

    data_footer(view)


def render_financial_inclusion(df: pd.DataFrame, profile: SourceProfile) -> None:
    page_intro(
        "02 / Financial inclusion",
        "Verified indicators, connected to their source variables.",
        "This page reports project-calculated estimates from the supplied Stata file. Every result has a definition, denominator, source-variable mapping and limitation so a research user can reproduce or challenge it.",
    )
    view = filter_bar(df, "financial_inclusion")
    if not has_data(view):
        return
    results = {indicator_id: calculate_indicator(view, indicator_id) for indicator_id in INDICATORS}
    card_ids = ["FI-01", "FI-02", "FI-03", "FI-04"]
    cards = st.columns(4)
    card_styles = [("green", "↗"), ("green", "⌁"), ("yellow", "◌"), ("rose", "!")]
    for slot, indicator_id, (color, icon) in zip(cards, card_ids, card_styles):
        result = results[indicator_id]
        with slot:
            metric_card(result.definition.title, pct(result.estimate), f"n={result.denominator_n:,} valid respondents", icon, color)

    section_head("Financial inclusion evidence", "Weighted estimates from the supplied source · no survey-design standard errors are shown")
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        names = [results[i].definition.title for i in INDICATORS]
        values = [results[i].estimate * 100 for i in INDICATORS]
        colors = ["#3155d4", "#5274e6", "#e5ae2f", "#de7c3f", "#d95362", "#7182a8"]
        fig = go.Figure(go.Bar(x=values, y=names, orientation="h", marker_color=colors, text=[f"{v:.1f}%" for v in values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_xaxes(range=[0, 108], ticksuffix="%")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, 350), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        selected = st.selectbox("Inspect indicator", list(INDICATORS), format_func=lambda x: f"{x} · {INDICATORS[x].title}", key="indicator_detail")
        result = results[selected]
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
    st.dataframe(registry, hide_index=True, use_container_width=True, height=315)
    st.markdown(f'<div class="footer-note">Source profile: {profile.source_variables:,} variables in the original Stata file · {profile.rows:,} records loaded · release and population period are not documented in the supplied materials.</div>', unsafe_allow_html=True)


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
    st.dataframe(blockers, hide_index=True, use_container_width=True)

    section_head("What is available as non-poverty context", "These are genuine estimates, clearly labelled as financial stress indicators")
    view = filter_bar(df, "poverty_context")
    if not has_data(view):
        return
    pressure = calculate_indicator(view, "FI-05")
    difficulty = calculate_indicator(view, "FI-04")
    a, b = st.columns(2)
    with a:
        metric_card("Income pressure", pct(pressure.estimate), "not an official poverty measure", "≈", "orange")
    with b:
        metric_card("Emergency money is difficult", pct(difficulty.estimate), "self-reported liquidity stress", "◌", "yellow")
    st.markdown('<div class="footer-note">These context indicators should not be relabelled as poverty, poverty risk, or welfare status without a documented methodology. Source: supplied Stata dataset; release period not documented.</div>', unsafe_allow_html=True)


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
        st.plotly_chart(chart_theme(fig, 340), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with r:
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Three signals, one view</div><div class="section-note">Share of respondents · province comparison</div>', unsafe_allow_html=True)
        fig = go.Figure()
        for col, name, color in [("value", "Active access", "#3155d4"), ("emergency", "Emergency fund", "#e5ae2f"), ("internet", "Internet access", "#de7c3f")]:
            fig.add_trace(go.Bar(x=table["group"], y=table[col] * 100, name=name, marker_color=color, hovertemplate=f"%{{x}} · {name}: %{{y:.1f}}%<extra></extra>"))
        fig.update_layout(barmode="group")
        fig.update_yaxes(range=[0, 108], ticksuffix="%")
        st.plotly_chart(chart_theme(fig, 340, True), use_container_width=True, config={"displayModeBar": False})
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
        st.dataframe(display_table[["group", "Active access", "active_n", "Emergency fund", "emergency_n"]].rename(columns={"group": "District", "active_n": "Access n", "emergency_n": "Emergency n"}), hide_index=True, use_container_width=True, height=300)
    with dright:
        best = district_table.iloc[0] if len(district_table) else None
        worst = district_table.iloc[-1] if len(district_table) else None
        if best is not None and worst is not None:
            st.markdown(f'<div class="callout"><strong>Decision cue.</strong><br><br>{best["group"]} leads this filtered view on active access at {pct(best["active_access"])}.<br><br>{worst["group"]} is the lowest at {pct(worst["active_access"])}; pair financial access expansion with a buffer-building offer.</div>', unsafe_allow_html=True)
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
    risk = weighted_rate(view, view["resilience_band"].eq("Priority").astype(float))
    watch = weighted_rate(view, view["resilience_band"].eq("Watch").astype(float))
    difficult = weighted_rate(view, view["emergency_difficult"])
    stress = weighted_rate(view, view["financial_stress"])
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Priority households", pct(risk), "low on the four-component resilience lens", "!", "rose")
    with c2: metric_card("Watch list", pct(watch), "partial resilience; programme targeting can make a difference", "◐", "yellow")
    with c3: metric_card("Emergency feels difficult", pct(difficult), "say raising 56,000 Rwf would be difficult", "◌", "orange")
    with c4: metric_card("Financial stress", pct(stress), "agree or sometimes feel financial stress", "≈", "rose")

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
        st.plotly_chart(chart_theme(fig, 245), use_container_width=True, config={"displayModeBar": False})
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
        "06 / Data explorer",
        "Keep the evidence one click away.",
        "Inspect aggregate evidence behind every headline. Pick a measure, break it down by a demographic or geographic dimension, and keep household-level records protected by default.",
    )
    view = filter_bar(df, "explorer")
    if not has_data(view):
        return
    if not aggregate_release_allowed(profile):
        st.markdown('<div class="callout"><strong>Aggregate explorer is governance-gated.</strong><br>No explicit authorization and disclosure/publication approval record is available for this source. The app will not produce an arbitrary filtered aggregate table or export until an authorised data steward supplies both approvals and an approved disclosure rule.</div>', unsafe_allow_html=True)
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
        st.plotly_chart(chart_theme(fig, max(260, min(510, 35 * len(grouped) + 90))), use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    section_head("Aggregate evidence", f"Household-level records are withheld by default · {len(view):,} records in scope")
    aggregate = aggregate_weighted_measure(view, measure)
    if not aggregate.empty:
        aggregate["estimate"] = aggregate["estimate"].map(lambda x: pct(x, 1))
        aggregate = aggregate.rename(columns={"province": "Province", "district": "District", "setting": "Setting", "sex": "Respondent", "records": "Records", "weight_sum": "Weight sum", "estimate": label})
    st.dataframe(aggregate, hide_index=True, use_container_width=True, height=340)
    st.markdown('<div class="callout"><strong>Privacy and publication control.</strong><br>Household-level records and raw CSV export are disabled because no authorization or disclosure/publication approval record was supplied. The table above is an aggregate analytical view only.</div>', unsafe_allow_html=True)
    aggregate_csv = aggregate.to_csv(index=False).encode("utf-8") if not aggregate.empty else b""
    st.download_button("Download aggregate summary (approval required)", aggregate_csv, file_name="insightrwanda_aggregate_summary.csv", mime="text/csv", type="secondary", disabled=True if profile is None else profile.publication_status != "Approved")
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
    with c2: metric_card("Warnings", str(summary["WARN"]), "requires review or qualification", "!", "yellow")
    with c3: metric_card("Informational", str(summary["INFO"]), "measured, not scored", "i", "orange")
    with c4: metric_card("Failures", str(summary["FAIL"]), "blocking structural checks", "×", "rose")

    section_head("Executed checks", "The findings below come from the loaded source, not synthetic fixture data")
    quality_table = pd.DataFrame([
        {"Status": check.status, "Category": check.category, "Check": check.check_id, "Finding": check.finding}
        for check in checks
    ])
    st.dataframe(quality_table, hide_index=True, use_container_width=True, height=355)

    section_head("Core-variable missingness", "Missing responses are excluded from each indicator denominator; no imputation is performed")
    missing_cols = ["qf4_05", "e9b", "e9c", "e7", "c14_5", "b2", "a1", "a2"]
    missing_values = [(column, df[column].isna().mean() * 100) for column in missing_cols if column in df]
    left, right = st.columns([1.05, .95])
    with left:
        fig = go.Figure(go.Bar(x=[value for _, value in missing_values], y=[column for column, _ in missing_values], orientation="h", marker_color="#de7c3f", text=[f"{value:.1f}%" for _, value in missing_values], textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.1f}% missing<extra></extra>"))
        fig.update_xaxes(range=[0, max(10, max((value for _, value in missing_values), default=0) + 10)], ticksuffix="%")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(chart_theme(fig, 300), use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown(f'<div class="callout"><strong>Scope.</strong><br><br>{profile.source_variables:,} source variables were inventoried. This dashboard loads {profile.analytical_variables:,} documented analytical variables, plus derived labels and indicators.<br><br><strong>Important.</strong><br><br>A clean load, unique key and valid codes do not prove that the survey is representative or that an official statistic can be published.</div>', unsafe_allow_html=True)

    section_head("Quality limitations", "What remains outside the executed checks")
    st.markdown('<div class="chart-card"><div class="section-note" style="font-size:.84rem;line-height:1.65">The workspace does not contain the fieldwork protocol, sample design, questionnaire version, enumerator quality controls, non-response adjustments, geographic boundary release, disclosure review, or an approved publication record. These should be supplied before an official public research release.</div></div>', unsafe_allow_html=True)


def render_methods(profile: SourceProfile, checks: list[QualityCheck]) -> None:
    page_intro(
        "08 / Methods & sources",
        "A traceable route from source file to displayed result.",
        "This page separates what is known about the supplied materials, what the application calculated, and what still needs research governance or documentation before publication.",
    )
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown('<div class="chart-card"><div class="eyebrow">Source profile</div><div class="section-title" style="font-size:1.25rem">Supplied Stata dataset</div>', unsafe_allow_html=True)
        source_rows = [
            ["Source ID", profile.source_id], ["Format", profile.format], ["File size", f"{profile.file_size_mb:.2f} MB"],
            ["Source SHA-256", profile.source_sha256], ["Analysis version", profile.analysis_version],
            ["Rows", f"{profile.rows:,}"], ["Source variables", f"{profile.source_variables:,}"], ["Analytical slice", f"{profile.analytical_variables:,} variables"],
            ["Release / period", profile.source_release], ["Metadata", profile.metadata_status], ["Analysis", profile.analysis_status],
            ["Authorization", profile.authorization_status], ["Publication", profile.publication_status],
        ]
        st.dataframe(pd.DataFrame(source_rows, columns=["Field", "Status / value"]), hide_index=True, use_container_width=True, height=405)
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
    st.dataframe(pd.DataFrame({"Material": list(profile.documentation), "Use": ["Competition scope and evaluation criteria", "Embedded source variable/value labels"]}), hide_index=True, use_container_width=True)
    st.markdown('<div class="callout"><strong>Governance boundary.</strong><br>The application distinguishes file existence, metadata inspection, permitted analysis, validation and public publication. The supplied workspace contains no authorization or publication approval record, so the app is suitable for internal analysis and demonstration, not an approved public statistical release.</div>', unsafe_allow_html=True)

    section_head("Indicator methodology", "Verified source mapping for the current financial-inclusion slice")
    method_rows = [{"ID": d.indicator_id, "Definition": d.definition, "Valid responses": d.valid_response_rule, "Calculation": d.method, "Limitations": " ".join(d.limitations)} for d in INDICATORS.values()]
    st.dataframe(pd.DataFrame(method_rows), hide_index=True, use_container_width=True, height=320)
    st.markdown(f'<div class="footer-note">Quality checks executed: {len(checks)} · source profile is cached from the supplied file · original research materials remain unchanged.</div>', unsafe_allow_html=True)


def render_about(df: pd.DataFrame) -> None:
    page_intro(
        "05 / About the build",
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
    st.dataframe(criteria, hide_index=True, use_container_width=True)
    st.markdown(f'<div class="footer-note">Dataset loaded successfully: {len(df):,} rows available · selected analytical slice loaded on demand for a fast presentation experience.</div>', unsafe_allow_html=True)


def main() -> None:
    try:
        raw = pipeline_load_analysis_data(DATA_PATH)
        df = pipeline_enrich_analysis_data(raw)
        profile = load_source_profile(str(DATA_PATH))
        checks = run_quality_checks(df, source_variable_count=profile.source_variables)
    except Exception as exc:
        st.error(f"The dataset could not be loaded: {exc}")
        st.stop()

    app_header()
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
    elif page == "Data quality":
        render_quality(df, profile, checks)
    elif page == "Data explorer":
        render_explorer(df, profile)
    elif page == "Methods & sources":
        render_methods(profile, checks)
    else:
        render_about(df)


if __name__ == "__main__":
    main()
