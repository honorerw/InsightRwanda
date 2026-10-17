"""Global visual system for the Streamlit application."""

from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    """Inject the shared visual system without replacing Streamlit controls.

    Streamlit's supported ``client.toolbarMode`` setting handles framework
    chrome. The CSS below is limited to application-owned classes plus the
    stable page container so navigation, toolbar, charts, and widgets remain
    available and usable.
    """

    st.markdown(
        """
        <style>
        :root {
          --ir-navy: #102a43;
          --ir-blue: #1769aa;
          --ir-cyan: #1ca6b7;
          --ir-ink: #102a43;
          --ir-muted: #52606d;
          --ir-line: #d9e2ec;
          --ir-surface: #ffffff;
          --ir-soft: #f5f8fb;
          --ir-warning: #8a5a00;
          --ir-danger: #a33a3a;
          --ir-success: #147d64;
        }
        .stApp {
          background: #f7f9fc;
          color: var(--ir-ink);
          font-family: "Inter", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
          -webkit-font-smoothing: antialiased;
          text-rendering: optimizeLegibility;
        }
        .stApp ::selection { background: rgba(28, 166, 183, 0.22); }
        .stApp ::-webkit-scrollbar { width: 10px; height: 10px; }
        .stApp ::-webkit-scrollbar-thumb { background: #c3d0dc; border-radius: 999px; border: 2px solid #f7f9fc; }
        .stApp ::-webkit-scrollbar-thumb:hover { background: #a9bacc; }
        .stApp ::-webkit-scrollbar-track { background: transparent; }
        .block-container { box-sizing: border-box; max-width: 1360px; min-width: 0; padding: clamp(1.15rem, 2.5vh, 1.9rem) clamp(1rem, 3vw, 2.5rem) 3rem; }
        h1, h2, h3 { color: var(--ir-navy); letter-spacing: -0.018em; }
        h1 { font-size: clamp(1.8rem, 3.2vw, 2.7rem); font-weight: 760; line-height: 1.08; }
        h2 { font-size: clamp(1.25rem, 2vw, 1.65rem); margin: 1.35rem 0 0.35rem; }
        h3 { font-size: 1.08rem; line-height: 1.25; }
        .app-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem 1rem; margin: 0 0 1.35rem; padding: 0.1rem 0 0.2rem; }
        .app-brand { display: inline-flex; align-items: center; gap: 0.55rem; color: var(--ir-navy); font-size: 1.02rem; font-weight: 780; letter-spacing: -0.01em; }
        .app-header-meta { display: inline-flex; align-items: center; gap: 0.7rem; color: var(--ir-muted); font-size: 0.78rem; }
        .header-status { border: 1px solid #efd9a8; border-radius: 999px; color: var(--ir-warning); background: #fff8e7; font-weight: 700; padding: 0.28rem 0.62rem; }
        .page-heading { min-width: 0; max-width: 1000px; margin-bottom: 1.35rem; }
        .eyebrow, .section-kicker { color: var(--ir-blue); font-size: 0.7rem; font-weight: 780; letter-spacing: 0.12em; text-transform: uppercase; }
        .eyebrow { margin-bottom: 0.5rem; }
        .page-title { max-width: 100%; margin: 0; overflow-wrap: anywhere; }
        .hero-copy { max-width: 820px; color: var(--ir-muted); font-size: 1rem; line-height: 1.55; margin: 0.65rem 0 0; overflow-wrap: anywhere; }
        .section-kicker { margin: 0 0 0.35rem; }
        .section-description { max-width: 900px; color: var(--ir-muted); line-height: 1.55; margin: 0 0 1rem; overflow-wrap: anywhere; }
        .status-pill { display: inline-flex; align-items: center; gap: 0.4rem; border: 1px solid #b8dce2; background: #edfafd; color: #0d6572; border-radius: 999px; font-size: 0.76rem; font-weight: 700; line-height: 1.2; padding: 0.32rem 0.68rem; }
        .status-pill.blocked { border-color: #efd9a8; background: #fff8e7; color: var(--ir-warning); }
        .status-pill.neutral { border-color: var(--ir-line); background: var(--ir-soft); color: var(--ir-muted); }
        .status-row { margin: -0.15rem 0 1.15rem; }
        .metric-card, .workflow-card, .domain-card, .empty-state, .source-card { border: 1px solid var(--ir-line); background: var(--ir-surface); border-radius: 0.7rem; padding: 1.05rem 1.1rem; min-height: 100%; box-shadow: 0 1px 2px rgba(16, 42, 67, 0.05), 0 6px 18px rgba(16, 42, 67, 0.05); transition: box-shadow 160ms ease, transform 160ms ease, border-color 160ms ease; }
        .metric-card:hover, .workflow-card:hover, .domain-card:hover, .source-card:hover { border-color: #b8ddde; box-shadow: 0 2px 4px rgba(16, 42, 67, 0.06), 0 10px 26px rgba(16, 42, 67, 0.09); transform: translateY(-1px); }
        .metric-card { min-height: 7.5rem; min-width: 0; position: relative; overflow: hidden; }
        .metric-card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 3px; background: linear-gradient(90deg, var(--ir-blue), var(--ir-cyan)); opacity: 0.85; }
        .metric-label { color: var(--ir-muted); font-size: 0.7rem; font-weight: 780; line-height: 1.3; text-transform: uppercase; letter-spacing: 0.07em; }
        .metric-value { color: var(--ir-navy); font-size: clamp(1.45rem, 2.4vw, 1.9rem); font-weight: 780; line-height: 1.1; margin: 0.45rem 0 0.35rem; overflow-wrap: anywhere; }
        .metric-note { color: var(--ir-muted); font-size: 0.8rem; line-height: 1.4; margin-top: auto; }
        .workflow-number { color: var(--ir-cyan); font-size: 0.75rem; font-weight: 800; letter-spacing: 0.08em; }
        .workflow-card h3, .domain-card h3 { margin: 0.35rem 0; }
        .workflow-card p, .domain-card p { color: var(--ir-muted); font-size: 0.88rem; line-height: 1.5; margin-bottom: 0; }
        .empty-state { border-left: 4px solid var(--ir-cyan); background: #fbfdfe; }
        .empty-state h3 { margin: 0 0 0.45rem; }
        .empty-state p { color: var(--ir-muted); line-height: 1.5; margin: 0; }
        .stMarkdown, [data-testid="stCaptionContainer"], [data-testid="stAlert"] { min-width: 0; overflow-wrap: anywhere; }
        [data-testid="stAlert"] { border-radius: 0.65rem; line-height: 1.5; }
        [data-testid="stExpander"] { min-width: 0; border-color: var(--ir-line); border-radius: 0.6rem; }
        [data-testid="stExpander"] summary { white-space: normal; overflow-wrap: anywhere; }
        [data-testid="stExpander"] details > div { min-width: 0; }
        [data-testid="stDataFrame"] { box-sizing: border-box; width: 100%; max-width: 100%; min-width: 0; border: 1px solid var(--ir-line); border-radius: 0.7rem; overflow: hidden; box-shadow: 0 1px 2px rgba(16, 42, 67, 0.04); }
        [data-testid="stDataFrame"] [role="columnheader"] { color: var(--ir-navy); font-weight: 700; font-size: 0.78rem; letter-spacing: 0.03em; }
        [data-testid="stDataFrame"] [data-testid="stDataFrameGrid"] { font-size: 0.82rem; }
        [data-testid="stPlotlyChart"], [data-testid="stMetric"] { box-sizing: border-box; max-width: 100%; min-width: 0; }
        [data-testid="stHorizontalBlock"] { min-width: 0; }
        [data-testid="column"] { box-sizing: border-box; min-width: 0 !important; }
        hr { margin: 1.65rem 0; border-color: var(--ir-line); }
        h1, h2, h3, p, li { overflow-wrap: anywhere; }
        .sidebar-brand { display: flex; align-items: center; gap: 0.55rem; color: var(--ir-navy); font-size: 1.1rem; }
        .sidebar-tagline { color: var(--ir-muted); font-size: 0.78rem; line-height: 1.35; margin: 0.35rem 0 0.9rem; }
        .sidebar-context { border-top: 1px solid var(--ir-line); border-bottom: 1px solid var(--ir-line); padding: 0.75rem 0; margin-bottom: 0.9rem; }
        .sidebar-kicker { color: var(--ir-blue); font-size: 0.68rem; font-weight: 780; letter-spacing: 0.08em; line-height: 1.35; text-transform: uppercase; }
        .sidebar-track { color: var(--ir-muted); font-size: 0.78rem; line-height: 1.4; margin-top: 0.28rem; }
        .sidebar-note { border: 1px solid #cce9ed; background: #f1fbfc; border-radius: 0.55rem; padding: 0.7rem 0.8rem; color: #0d6572; font-size: 0.82rem; line-height: 1.45; }
        .sidebar-note small { color: #52606d; }
        .status-dot { display: inline-block; width: 0.45rem; height: 0.45rem; border-radius: 50%; background: var(--ir-cyan); margin-right: 0.35rem; vertical-align: middle; }
        [data-testid="stSidebarNav"] { padding-top: 0.25rem; }
        [data-testid="stSidebarNav"] > ul { gap: 0.12rem; }
        [data-testid="stSidebarNav"] li { margin: 0.08rem 0; }
        [data-testid="stSidebarNav"] a { border-radius: 0.45rem; min-height: 2.15rem; padding: 0.35rem 0.55rem; }
        [data-testid="stSidebarNav"] a:hover { background: #edfafd; color: var(--ir-navy); }
        [data-testid="stSidebarNav"] a[aria-current="page"] { background: #dff4f7; color: var(--ir-navy); font-weight: 760; box-shadow: inset 3px 0 0 var(--ir-cyan); }
        [data-testid="stSidebarNav"] [data-testid="stSidebarNavSectionHeader"] { color: var(--ir-blue); font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; margin: 0.8rem 0 0.28rem; text-transform: uppercase; }
        .indicator-id { color: var(--ir-blue); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.72rem; }
        .muted { color: var(--ir-muted); }
        [data-testid="stSidebar"] { background: linear-gradient(180deg, #fbfdfe 0%, #f3f8fa 100%); }
        [data-testid="stSidebar"] .stButton > button, .stButton > button { border-radius: 0.55rem; }
        .stButton > button:focus-visible, [data-testid="stSidebar"] input:focus-visible { outline: 2px solid rgba(28, 166, 183, 0.55); outline-offset: 1px; }
        .stDownloadButton > button { border-radius: 0.55rem; }
        @media (prefers-color-scheme: dark) {
          [data-testid="stSidebarNav"] a:hover { background: rgba(28, 166, 183, 0.16); }
          [data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(28, 166, 183, 0.22); color: #dff8fb; }
        }
        @media (max-width: 900px) {
          [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.75rem; }
          [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex: 1 1 calc(50% - 0.75rem) !important; width: auto !important; }
        }
        @media (max-width: 640px) {
          .block-container { padding: 1.15rem 0.85rem 2.25rem; }
          [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex: 1 1 100% !important; width: 100% !important; }
          .app-header { align-items: flex-start; flex-direction: column; gap: 0.55rem; margin-bottom: 1.1rem; }
          .app-header-meta { flex-wrap: wrap; }
          .page-heading { margin-bottom: 1.25rem; }
          .hero-copy { font-size: 0.93rem; }
          .status-row { margin-bottom: 0.95rem; }
          .metric-card { min-height: 0; }
          h1 { font-size: clamp(1.65rem, 8vw, 2.1rem); }
          h2 { margin-top: 1.1rem; }
          [data-testid="stDataFrame"] { overflow-x: auto; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
