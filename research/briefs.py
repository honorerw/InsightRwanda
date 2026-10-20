"""One-page, non-gated insight briefs for each dashboard page.

Each brief is a self-contained, aggregate-only summary of one dashboard page,
rendered to PNG and single-page PDF bytes with Pillow. Briefs are built only
from values the existing research modules calculate (indicators, context
estimates, quality checks, the source profile). They contain no household
identifiers, no raw records and no gated exports, so they can be shared
freely without an authorization or publication approval.

Design rules honoured throughout:

* Every number comes from the same estimators the dashboard uses.
* Every brief repeats what its numbers cannot claim (honesty panel).
* Rendering is deterministic: no timestamps, no randomness, seeded by data.
* An official poverty estimation is never produced here; the Poverty brief
  states the open inputs instead.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from .catalog import SourceProfile, _analysis_version, aggregate_release_allowed
from .data_pipeline import PROVINCES
from .estimation import CONTEXT_ESTIMATES, calculate_context_estimate, official_poverty_status
from .indicators import INDICATORS, calculate_indicator
from .quality import QualityCheck, run_quality_checks

PAGES: tuple[str, ...] = (
    "Overview", "Financial inclusion", "Poverty insights", "Geographic insights",
    "Resilience lab", "Data quality", "Data explorer", "Methods & sources", "About the build",
)

LENS_PREFIXES: dict[str, str] = {
    "Overview": "overview",
    "Financial inclusion": "financial_inclusion",
    "Poverty insights": "poverty_context",
    "Geographic insights": "regional",
    "Resilience lab": "resilience",
    "Data explorer": "explorer",
}

HONESTY_STATEMENT = (
    "Aggregate-only brief built from the loaded records using hh_wt. No household-level "
    "records, identifiers or raw exports are included. Descriptive weighted statistics — "
    "not an official statistical publication and not a survey-design standard error."
)

NA = "n/a"


@dataclass(frozen=True)
class PageBrief:
    """One page of evidence, ready to render."""

    page: str
    eyebrow: str
    title: str
    narrative: str
    caution: str
    kpis: tuple[tuple[str, str, str], ...]
    lens_note: str
    footer_lines: tuple[str, ...]


def _weighted_mean_column(frame: pd.DataFrame, column: str) -> tuple[float, int]:
    """Weighted mean of an existing derived binary column (same rule as the app)."""

    if column not in frame:
        raise ValueError(f"Briefs require the derived column: {column}")
    values = frame[column]
    valid = values.notna() & frame["hh_wt"].notna() & frame["hh_wt"].gt(0) & np.isfinite(frame["hh_wt"])
    if valid.sum() == 0:
        return float("nan"), 0
    return float(np.average(values.loc[valid], weights=frame.loc[valid, "hh_wt"])), int(valid.sum())


def _pct(value: float, decimals: int = 1) -> str:
    return NA if pd.isna(value) else f"{value * 100:.{decimals}f}%"


def _pop(frame: pd.DataFrame) -> str:
    valid = frame["hh_wt"].notna() & frame["hh_wt"].gt(0) & np.isfinite(frame["hh_wt"])
    return f"{float(frame.loc[valid, 'hh_wt'].sum()):,.0f}" if valid.any() else "0"


def _lens(view: pd.DataFrame) -> str:
    parts: list[str] = []
    if view.attrs.get("province") is not None:
        parts.append(str(view.attrs["province"]))
    records = len(view)
    lens_text = " · ".join(parts) if parts else "National view"
    return f"{lens_text} · {records:,} records"


def _band_shares(view: pd.DataFrame) -> dict[str, float]:
    """Weighted shares of the resilience bands over scored rows."""

    valid = view["resilience_band"].notna() & view["hh_wt"].notna() & view["hh_wt"].gt(0)
    weights = view.loc[valid, "hh_wt"].astype(float)
    if not valid.any() or weights.sum() <= 0:
        return {band: float("nan") for band in ("Priority", "Watch", "Resilient")}
    grouped = view.loc[valid].groupby("resilience_band", observed=True)["hh_wt"].sum()
    total = float(grouped.sum())
    return {band: float(grouped.get(band, 0.0) / total) for band in ("Priority", "Watch", "Resilient")}


def _footer(profile: SourceProfile | None) -> tuple[str, ...]:
    if profile is None:
        return (f"Analysis version: {_analysis_version()}", "Source hash: not loaded", HONESTY_STATEMENT)
    return (
        f"Analysis version: {profile.analysis_version}",
        f"Source SHA-256: {profile.source_sha256[:24]}… · {profile.rows:,} rows · {profile.source_variables:,} source variables",
        HONESTY_STATEMENT,
    )


def _fi_rows(view: pd.DataFrame) -> list[tuple[str, str, str]]:
    return [
        (INDICATORS[iid].title, _pct(calculate_indicator(view, iid).estimate),
         f"denominator n={calculate_indicator(view, iid).denominator_n:,}")
        for iid in INDICATORS
    ]


# -----------------------------------------------------------------------------
# Page builders
# -----------------------------------------------------------------------------

def _build_overview(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    active, _ = _weighted_mean_column(view, "active_access")
    mobile, _ = _weighted_mean_column(view, "mobile_money")
    emergency, _ = _weighted_mean_column(view, "emergency_fund")
    pressure, _ = _weighted_mean_column(view, "income_pressure")
    bands = _band_shares(view)
    gap = active - emergency if not (pd.isna(active) or pd.isna(emergency)) else float("nan")
    return PageBrief(
        page="Overview",
        eyebrow="01 / National signal",
        title="Brief — National signal",
        narrative=(
            "Headline weighted rates: access to formal financial channels is broad while "
            "money set aside for shocks is thin — the access-to-buffer gap is the takeaway."
        ),
        caution=(
            "These are descriptive weighted rates. The resilience lens is a prioritisation "
            "heuristic over observed capabilities, not a poverty or welfare model."
        ),
        kpis=(
            ("Active formal access", _pct(active), "currently use at least one formal channel"),
            ("Mobile money anchor", _pct(mobile), "currently use a mobile money operator"),
            ("Emergency buffer", _pct(emergency), "have set aside rainy-day funds"),
            ("Income pressure", _pct(pressure), "income does not cover costs monthly or often"),
            ("Resilient band", _pct(bands["Resilient"]), "households scoring high on the lens"),
            ("Access–buffer gap", NA if pd.isna(gap) else f"{gap * 100:.1f} pp", "active access minus emergency buffer"),
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_financial_inclusion(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    rows = tuple(_fi_rows(view))
    return PageBrief(
        page="Financial inclusion",
        eyebrow="02 / Indicator registry",
        title="Brief — Financial inclusion indicators",
        narrative=(
            "The six verified indicators (FI-01…FI-06) with weighted estimates and the "
            "indicator-specific denominators behind each rate."
        ),
        caution=(
            "Missing, unexpected and non-substantive responses are excluded from each "
            "denominator — never counted as negative responses. Definitions are in the "
            "registry on the app page."
        ),
        kpis=rows,
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_poverty_insights(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    context_rows: list[tuple[str, str, str]] = []
    for estimate_id in CONTEXT_ESTIMATES:
        result = calculate_context_estimate(view, estimate_id)
        definition = result["definition"]
        caveat_short = "structural zero — band 16 has no responses in the file" if estimate_id == "EI-02" else (
            f"weighted population {result['weight_sum']:,.0f}"
        )
        context_rows.append((definition.title, _pct(result["estimate"]), caveat_short))
    context_rows.append(("Official poverty rate", "Blocked", f"{len(official_poverty_status().missing)} required inputs still missing"))
    pressure = _weighted_mean_column(view, "income_pressure")[0]
    difficulty = _weighted_mean_column(view, "emergency_difficult")[0]
    return PageBrief(
        page="Poverty insights",
        eyebrow="03 / Poverty insights",
        title="Brief — Financial stress & income context",
        narrative=(
            "Non-poverty context estimates: income pressure, emergency liquidity difficulty "
            "and income-band concentration from the embedded Stata band labels."
        ),
        caution=(
            "None of these figures is a poverty rate. Income bands are self-reported and "
            "band-coded — not household consumption or a welfare aggregate. EI-02's 0.0% "
            "is a structural zero, not evidence of zero irregular income. An official "
            "poverty estimate stays blocked by the six-input unlock contract."
        ),
        kpis=(
            ("Income pressure", _pct(pressure), "income does not cover costs — context, not poverty"),
            ("Emergency money difficult", _pct(difficulty), "self-reported liquidity stress"),
            *context_rows,
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_geographic(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    ordered = [name for name in PROVINCES.values() if name in set(view["province"])]
    rows: list[tuple[str, str, str]] = []
    for province in ordered:
        sub = view[view["province"].eq(province)]
        active, n = _weighted_mean_column(sub, "active_access")
        emergency, _ = _weighted_mean_column(sub, "emergency_fund")
        internet, _ = _weighted_mean_column(sub, "internet_access")
        rows.append((province, _pct(active), f"emergency {_pct(emergency)} · internet {_pct(internet)} · n={n:,}"))
    return PageBrief(
        page="Geographic insights",
        eyebrow="04 / Geographic insights",
        title="Brief — Geography of access",
        narrative=(
            "Active formal access for each supplied province, with the emergency-buffer and "
            "internet-access rates that expose where access and resilience diverge."
        ),
        caution=(
            "Province comparisons are descriptive and weighted with hh_wt. They rank where "
            "signals differ — they do not establish causality or targeting aptitude by "
            "themselves. District-level drill-down lives on the app page."
        ),
        kpis=tuple(rows) or ((NA, NA, "no province data"),),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_resilience(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    score, n = _weighted_mean_column(view, "resilience_score")
    bands = _band_shares(view)
    components = ("emergency_fund", "owns_money", "saves_regularly", "social_safety_net")
    component_rows = []
    for column in components:
        rate, component_n = _weighted_mean_column(view, column)
        component_rows.append((column.replace("_", " ").title(), _pct(rate), f"n={component_n:,}"))
    return PageBrief(
        page="Resilience lab",
        eyebrow="05 / Resilience lab",
        title="Brief — Resilience lens",
        narrative=(
            "The transparent composite: the mean of four observed capabilities, the share "
            "of households in each band, and the components kept separately."
        ),
        caution=(
            "The score is a prioritisation lens over observed capabilities — it is not a "
            "poverty line, a welfare aggregate or a modelled probability. Bands are "
            "descriptive cuts (≤0.39 Priority, 0.40–0.69 Watch, ≥0.70 Resilient)."
        ),
        kpis=(
            ("Mean resilience score", NA if pd.isna(score) else f"{score:.2f}", f"across n={n:,} scored records"),
            ("Priority band", _pct(bands["Priority"]), "resilience score ≤ 0.39"),
            ("Watch band", _pct(bands["Watch"]), "resilience score 0.40–0.69"),
            ("Resilient band", _pct(bands["Resilient"]), "resilience score ≥ 0.70"),
            *component_rows,
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_quality(view: pd.DataFrame, profile: SourceProfile | None, checks: Sequence[QualityCheck]) -> PageBrief:
    summary = {status: sum(c.status == status for c in checks) for status in ("PASS", "WARN", "FAIL", "INFO")}
    missingness = {}
    for check in checks:
        if check.check_id == "core_missingness":
            missingness = check.evidence.get("missingness", {})
    worst = max(missingness.items(), key=lambda item: item[1]) if missingness else (NA, float("nan"))
    duplicates = sum(c.evidence.get("duplicate_rows", 0) for c in checks if c.check_id == "unique_household_key")
    invalid_weights = sum(c.evidence.get("invalid_weights", 0) for c in checks if c.check_id == "household_weight")
    return PageBrief(
        page="Data quality",
        eyebrow="06 / Data quality",
        title="Brief — Checks that actually ran",
        narrative=(
            f"{len(checks)} structural and coding checks executed on the loaded slice, with "
            "the measured core-variable missingness that the dashboard never imputes."
        ),
        caution=(
            "These checks describe data structure and coding integrity. They do not certify "
            "representativeness, fieldwork quality or official statistical publication."
        ),
        kpis=(
            ("Records loaded", f"{len(view):,}", "unweighted rows in the analytical slice"),
            ("Checks executed", f"{len(checks)}", f"{summary['PASS']} PASS · {summary['WARN']} WARN · {summary['FAIL']} FAIL · {summary['INFO']} INFO"),
            ("Duplicate household keys", f"{duplicates}", "0 means the slice passes integrity"),
            ("Invalid household weights", f"{invalid_weights}", "0 means every weight is positive and finite"),
            (f"Max missingness ({worst[0]})", _pct(worst[1], 2), "measured, never imputed"),
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_explorer(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    from .catalog import aggregate_release_allowed

    released = aggregate_release_allowed(profile)
    return PageBrief(
        page="Data explorer",
        eyebrow="07 / Data explorer",
        title="Brief — Governance state",
        narrative=(
            "What the explorer would expose and what stays withheld: this brief itself is "
            "the non-gated route to page evidence."
        ),
        caution=(
            "Aggregate tables and raw exports remain disabled until an authorization record, "
            "a publication approval and an approved disclosure rule exist in the source "
            "profile. The gate is code-enforced, not a disclaimer."
        ),
        kpis=(
            ("Explorer gate", "Open" if released else "Gated", "aggregate_release_allowed()"),
            ("Records in slice", f"{len(view):,}", "loaded for weighted analytical work"),
            ("Household-level preview", "Withheld", "no authorization record supplied"),
            ("Raw CSV export", "Withheld", "no publication approval or disclosure rule"),
            ("Aggregate tables", "Withheld" if not released else "Available", "governance-gated in code"),
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_methods(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    if profile is None:
        raise ValueError("Methods brief requires the loaded source profile")
    return PageBrief(
        page="Methods & sources",
        eyebrow="08 / Methods & sources",
        title="Brief — Source profile snapshot",
        narrative=(
            "The traceable route from the supplied Stata file to displayed results: five "
            "steps — Inspect, Load, Validate, Calculate, Explain."
        ),
        caution=(
            "Analysis is permitted; publication is not. An approved public statistical "
            "release still requires authorization and disclosure review that the workspace "
            "does not contain."
        ),
        kpis=(
            ("Source format", profile.format, f"{profile.file_size_mb:.2f} MB on disk"),
            ("Rows", f"{profile.rows:,}", "households in the supplied file"),
            ("Source variables", f"{profile.source_variables:,}", "in the original Stata file"),
            ("Analytical slice", f"{profile.analytical_variables}", "documented variables used by the app"),
            ("Source SHA-256", profile.source_sha256[:24] + "…", "computed from actual file bytes"),
            ("Analysis version", profile.analysis_version, "fingerprint of the research logic"),
            ("Authorization", "Unknown", "no authorization record supplied"),
            ("Publication", "Not approved", "no disclosure/publication approval supplied"),
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


def _build_about(view: pd.DataFrame, profile: SourceProfile | None) -> PageBrief:
    active, _ = _weighted_mean_column(view, "active_access")
    emergency, _ = _weighted_mean_column(view, "emergency_fund")
    gap = active - emergency if not (pd.isna(active) or pd.isna(emergency)) else float("nan")
    released = aggregate_release_allowed(profile) if profile is not None else False
    return PageBrief(
        page="About the build",
        eyebrow="09 / About the build",
        title="Brief — Product thesis",
        narrative=(
            "“Account access is not resilience.” The prototype targets the gap between "
            "formal access and household shock absorption across access, buffers, digital "
            "reach, geography and vulnerability."
        ),
        caution=(
            "The dashboard is intentionally descriptive: weighted estimates, transparent "
            "rule-based indicators and explicitly labelled limitations — no official "
            "publication claims and no unsupervised exports."
        ),
        kpis=(
            ("Access–buffer gap", NA if pd.isna(gap) else f"{gap * 100:.1f} pp", "the headline the prototype turns into a lens"),
            ("Active formal access", _pct(active), "weighted with supplied hh_wt"),
            ("Emergency buffer", _pct(emergency), "rainy-day funds on hand"),
            ("Written into code", f"{len(PAGES)} pages", "each with an auditable rule set"),
            ("Explorer gate", "Closed" if not released else "Open", "exports approval-gated in code"),
        ),
        lens_note=_lens(view),
        footer_lines=_footer(profile),
    )


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def build_page_brief(
    page: str,
    view: pd.DataFrame,
    profile: SourceProfile | None = None,
    checks: Sequence[QualityCheck] | None = None,
) -> PageBrief:
    """Build the one-page brief for a dashboard page from a loaded, enriched view."""

    if page == "Overview":
        return _build_overview(view, profile)
    if page == "Financial inclusion":
        return _build_financial_inclusion(view, profile)
    if page == "Poverty insights":
        return _build_poverty_insights(view, profile)
    if page == "Geographic insights":
        return _build_geographic(view, profile)
    if page == "Resilience lab":
        return _build_resilience(view, profile)
    if page == "Data quality":
        return _build_quality(view, profile, checks if checks is not None else run_quality_checks(view))
    if page == "Data explorer":
        return _build_explorer(view, profile)
    if page == "Methods & sources":
        return _build_methods(view, profile)
    if page == "About the build":
        return _build_about(view, profile)
    raise ValueError(f"Unknown page for a brief: {page}")


def build_all_briefs(
    view: pd.DataFrame,
    profile: SourceProfile | None = None,
    checks: Sequence[QualityCheck] | None = None,
) -> dict[str, PageBrief]:
    return {page: build_page_brief(page, view, profile, checks) for page in PAGES}


# -----------------------------------------------------------------------------
# Rendering (Pillow)
# -----------------------------------------------------------------------------

PAGE_W, PAGE_H = 1654, 2339          # A4 @ 200 dpi
MARGIN = 84
INK = (23, 33, 61)
NAVY = (23, 33, 61)
BLUE = (49, 85, 212)
GRAY = (102, 113, 139)
LIGHT = (232, 236, 245)
PANEL = (245, 248, 254)
CAUTION_BG = (255, 243, 219)
CAUTION_EDGE = (229, 174, 47)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

_FONT_CANDIDATES_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


class _Fonts:
    def __init__(self) -> None:
        self.regular = ImageFont.truetype(_FONT_CANDIDATES[0], 20)
        self.bold = ImageFont.truetype(_FONT_CANDIDATES_BOLD[0], 20)
        self.sizes = {20: (self.regular, self.bold)}

    def get(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        if size not in self.sizes:
            self.sizes[size] = (
                ImageFont.truetype(_FONT_CANDIDATES[0], size),
                ImageFont.truetype(_FONT_CANDIDATES_BOLD[0], size),
            )
        return self.sizes[size][1 if bold else 0]

    def wrap(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
        words, lines, current = text.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]


def _draw_kpi_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, note: str, fonts: _Fonts) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=16, fill=PANEL, outline=LIGHT, width=2)
    draw.text((x0 + 28, y0 + 20), label.upper(), font=fonts.get(21, True), fill=GRAY)
    draw.text((x0 + 28, y0 + 52), value, font=fonts.get(52, True), fill=INK)
    note_width = (x1 - x0) - 56
    for offset, line in enumerate(fonts.wrap(draw, note, fonts.get(17), note_width)[:2]):
        draw.text((x0 + 28, y1 - 44 + offset * 22), line, font=fonts.get(17), fill=GRAY)


def render_brief_png(brief: PageBrief) -> bytes:
    """Render the brief to a deterministic PNG (A4 @ 200 dpi)."""

    image = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(image)
    fonts = _Fonts()

    # Header
    draw.rectangle([0, 0, PAGE_W, 240], fill=NAVY)
    draw.text((MARGIN, 44), brief.eyebrow.upper(), font=fonts.get(24), fill=(154, 171, 222))
    draw.text((MARGIN, 82), brief.title, font=fonts.get(56, True), fill="white")
    draw.rectangle([0, 240, PAGE_W, 248], fill=BLUE)

    cursor = 292

    # Lens strip
    draw.text((MARGIN, cursor), "ANALYSIS LENS", font=fonts.get(20, True), fill=BLUE)
    draw.text((MARGIN + 200, cursor), brief.lens_note, font=fonts.get(20), fill=GRAY)
    cursor += 46

    # Narrative
    narrative_lines = fonts.wrap(draw, brief.narrative, fonts.get(24, True), PAGE_W - 2 * MARGIN)
    for line in narrative_lines:
        draw.text((MARGIN, cursor), line, font=fonts.get(24, True), fill=INK)
        cursor += 34
    cursor += 22

    # KPI cards, two per row
    max_kpis = 10
    col_width = (PAGE_W - 2 * MARGIN - 24) // 2
    card_height = 170
    for index, (label, value, note) in enumerate(brief.kpis[:max_kpis]):
        col = index % 2
        row = index // 2
        x0 = MARGIN + col * (col_width + 24)
        y0 = cursor + row * (card_height + 22)
        _draw_kpi_card(draw, (x0, y0, x0 + col_width, y0 + card_height), label, value, note, fonts)
    cursor += ((min(len(brief.kpis), max_kpis) + 1) // 2) * (card_height + 22) + 22

    # Caution panel
    caution_lines = fonts.wrap(draw, brief.caution, fonts.get(21), PAGE_W - 2 * MARGIN - 72)
    panel_height = 58 + len(caution_lines) * 30 + 18
    draw.rounded_rectangle((MARGIN, cursor, PAGE_W - MARGIN, cursor + panel_height), radius=16, fill=CAUTION_BG, outline=CAUTION_EDGE, width=3)
    draw.text((MARGIN + 36, cursor + 20), "WHAT THIS BRIEF CANNOT CLAIM", font=fonts.get(20, True), fill=(146, 106, 22))
    inner = cursor + 52
    for line in caution_lines:
        draw.text((MARGIN + 36, inner), line, font=fonts.get(21), fill=INK)
        inner += 30
    cursor += panel_height + 26

    # Footer
    draw.line([(MARGIN, cursor), (PAGE_W - MARGIN, cursor)], fill=LIGHT, width=3)
    cursor += 18
    for line in brief.footer_lines:
        for wrapped in fonts.wrap(draw, line, fonts.get(17), PAGE_W - 2 * MARGIN)[:3]:
            draw.text((MARGIN, cursor), wrapped, font=fonts.get(17), fill=GRAY)
            cursor += 24

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def render_brief_pdf(brief: PageBrief) -> bytes:
    """Render the same brief as a single-page PDF."""

    png_bytes = render_brief_png(brief)
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PDF", resolution=200.0)
    return buffer.getvalue()


def brief_filenames(brief: PageBrief) -> dict[str, str]:
    """Stable file names for the brief artifacts."""

    slug = brief.page.lower().replace(" & ", "_").replace(" ", "_")
    return {"pdf": f"brief_{slug}.pdf", "png": f"brief_{slug}.png"}
