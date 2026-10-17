"""Accessible Plotly views of actual readiness metadata.

These figures describe evidence-record statuses, not survey observations or
research findings. They accept only aggregate integer counts derived from the
validated readiness report.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import plotly.graph_objects as go


_STATUS_STYLE = {
    "verified": ("Verified", "#147d64"),
    "approved": ("Approved", "#1769aa"),
    "provided_unverified": ("Provided · unverified", "#c17a00"),
    "missing": ("Missing", "#a33a3a"),
    "rejected": ("Rejected", "#7b2434"),
    "not_applicable": ("Not applicable", "#52606d"),
}


def evidence_status_counts(readiness_report: dict[str, Any] | None) -> dict[str, int]:
    """Count evidence statuses from the report's actual validated item list."""

    evidence = readiness_report.get("evidence") if isinstance(readiness_report, dict) else None
    items = evidence.get("items") if isinstance(evidence, dict) else None
    if not isinstance(items, list):
        return {}
    counts: Counter[str] = Counter()
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("status"), str):
            counts[item["status"]] += 1
    return dict(counts)


def build_evidence_status_figure(readiness_report: dict[str, Any] | None) -> go.Figure | None:
    """Render a labeled status-count bar chart; never treat absent as zero."""

    counts = evidence_status_counts(readiness_report)
    known = [(key, counts[key]) for key in _STATUS_STYLE if counts.get(key, 0) > 0]
    unknown = sorted(key for key, value in counts.items() if value > 0 and key not in _STATUS_STYLE)
    if not known and not unknown:
        return None
    keys = [key for key, _ in known] + unknown
    values = [counts[key] for key in keys]
    labels = [_STATUS_STYLE[key][0] if key in _STATUS_STYLE else f"Unrecognized · {key}" for key in keys]
    colors = [_STATUS_STYLE[key][1] if key in _STATUS_STYLE else "#52606d" for key in keys]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker={"color": colors},
            text=values,
            textposition="outside",
            cliponaxis=False,
            customdata=keys,
            hovertemplate="<b>%{y}</b><br>Evidence records: %{x}<br>Status code: %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        title="Evidence register status",
        xaxis_title="Number of evidence records",
        yaxis_title="Review status",
        template="plotly_white",
        height=max(260, 66 * len(keys) + 100),
        margin={"l": 150, "r": 38, "t": 64, "b": 55},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
        showlegend=False,
    )
    figure.update_xaxes(rangemode="tozero", gridcolor="#e6edf3", automargin=True)
    figure.update_yaxes(automargin=True)
    return figure


def build_metadata_count_figure(
    counts: dict[str, Any] | None,
    *,
    title: str,
    category_axis: str,
    count_axis: str,
) -> go.Figure | None:
    """Chart non-sensitive metadata counts after strict type validation."""

    if not isinstance(counts, dict) or not counts:
        return None
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for key, value in counts.items()
    ):
        return None
    items = [(key, value) for key, value in counts.items() if value > 0]
    if not items:
        return None
    labels, values = zip(*items)
    figure = go.Figure(
        go.Bar(
            x=list(values),
            y=list(labels),
            orientation="h",
            marker={"color": "#1769aa"},
            text=list(values),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title=count_axis,
        yaxis_title=category_axis,
        template="plotly_white",
        height=max(260, 58 * len(items) + 100),
        margin={"l": 130, "r": 36, "t": 64, "b": 55},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
        showlegend=False,
    )
    figure.update_xaxes(rangemode="tozero", gridcolor="#e6edf3", automargin=True)
    figure.update_yaxes(automargin=True)
    return figure
