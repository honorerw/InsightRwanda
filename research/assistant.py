"""Ask InsightRwanda — deterministic, offline-first assistant core.

Answers supported questions using ONLY:
  - the project's indicator/estimation definitions (`research.indicators`,
    `research.estimation`),
  - live verified numerical results from the same tested analytical functions
    the dashboard uses (`calculate_indicator`, `calculate_context_estimate`),
  - canonical governance contracts (`official_poverty_status`,
    `aggregate_release_allowed`),
  - approved per-page narratives (`research.briefs`) and the honesty statement.

The core is Streamlit-free and state-free: the caller supplies the active
frame, source profile, quality checks, human-readable source label, applied
lens note and page context as explicit arguments. Unknown questions get an
honest fallback; restricted and injection-shaped requests are refused. No
network, no new dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

import pandas as pd

from research.briefs import HONESTY_STATEMENT, PAGES, build_page_brief
from research.catalog import SourceProfile, aggregate_release_allowed
from research.estimation import CONTEXT_ESTIMATES, calculate_context_estimate, official_poverty_status
from research.indicators import INDICATORS, calculate_indicator, calculate_by_group
from research.quality import QualityCheck, quality_summary

__all__ = [
    "AssistantAnswer",
    "AssistantChart",
    "EvidenceReference",
    "MAX_QUESTION_LENGTH",
    "answer_question",
    "answer_with_chart",
    "resolve_indicator",
]

MAX_QUESTION_LENGTH = 600

_FALLBACK_PAGE = "Methods & sources"
_PAGE_NUMBERS = {page: f"Page {index + 1:02d} · {page}" for index, page in enumerate(PAGES)}


@dataclass(frozen=True)
class EvidenceReference:
    """One pointer to material actually used to build an answer."""

    identifier: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class AssistantAnswer:
    """Structured assistant response: answer text plus provenance."""

    question_kind: str
    answer: str
    references: tuple[EvidenceReference, ...]
    grounded: bool = True
    numeric_verified: bool = False
    scope: str = "project evidence"
    applied_lens: str = ""


# Simple-English restatements of the approved definitions. These are worded
# summaries of what each indicator means — never numbers.
_SIMPLER: dict[str, str] = {
    "FI-01": "the person currently uses at least one formal financial channel — a bank, digital bank, micro-finance or other non-bank institution, mobile money, or an Umurenge SACCO.",
    "FI-02": "the person currently uses a mobile-money operator (for example sending, receiving or paying with mobile money).",
    "FI-03": "the person says they have set aside emergency or rainy-day money.",
    "FI-04": "the person says that raising 56,000 Rwf within the next month would be very or somewhat difficult.",
    "FI-05": "the person says their income does not cover living costs — monthly or more often.",
    "FI-06": "the person reports having access to the internet.",
    "EI-01": "among people who report a monthly personal income band, this is the share in the two lowest bands (1,000 Rwf or less, or 1,001–3,000 Rwf).",
    "EI-02": "among people who report a monthly personal income band, this is the share reporting irregular or seasonal income.",
    "EI-03": "among people who report an annual total income band, this is the share in the two lowest bands (12,000 Rwf or less, or 12,001–15,000 Rwf).",
}

# Keyword aliases per indicator, used to resolve ordinary-language questions.
_ALIASES: dict[str, tuple[str, ...]] = {
    "FI-01": ("fi-01", "active formal", "formal financial access", "formal access", "formal channel", "financial inclusion"),
    "FI-02": ("fi-02", "mobile money", "mobile-money"),
    "FI-03": ("fi-03", "emergency fund", "emergency saving", "rainy-day", "rainy day"),
    "FI-04": ("fi-04", "emergency money", "56,000", "raising 56", "difficult to raise"),
    "FI-05": ("fi-05", "income pressure", "income does not cover", "cover living costs", "cover costs"),
    "FI-06": ("fi-06", "internet access", "internet"),
    "EI-01": ("ei-01", "low personal income", "monthly income band", "lowest monthly income"),
    "EI-02": ("ei-02", "irregular income", "seasonal income"),
    "EI-03": ("ei-03", "low annual income", "annual income band"),
}

_PAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "Overview": ("overview", "home", "national picture"),
    "Financial inclusion": ("financial inclusion", "financial-inclusion"),
    "Poverty insights": ("poverty insights", "poverty page", "poverty context"),
    "Geographic insights": ("geographic", "regional", "province"),
    "Resilience lab": ("resilience lab", "resilience bands", "resilience mix"),
    "Predictive insights": ("predictive insights", "predictive page", "model readout"),
    "Data quality": ("data quality", "quality page"),
    "Data explorer": ("data explorer", "explorer", "aggregate summary"),
    "Methods & sources": ("methods", "methodology", "sources"),
    "About the build": ("about the build", "about page", "product thesis"),
}

_INJECTION_PATTERNS = (
    r"ignore (all )?(previous|prior|above|earlier) (instructions|prompts|rules)",
    r"disregard (all )?(previous|prior|above|earlier)",
    r"(system|developer|internal) (prompt|instruction|message)",
    r"reveal|print|show (your |the )?(system ?prompt|instructions|rules)",
    r"(bypass|override|unlock|disable|switch off|turn off).{0,24}(gate|approval|control|lock|restriction|check)",
    r"pretend (you are|to be)|act as (if|an?|the)|role[- ]?play|jailbreak|developer mode",
    r"(you are now|new instructions|replace your rules)",
)

_PRIVACY_PATTERNS = (
    r"(household|respondent)( |-)?(keys?|ids?|identifiers)",
    r"list (all )?(households|respondents|individuals|people|persons|records|rows)",
    r"(names|identities|details|list) of (the )?(households|respondents|individuals|people|persons)",
    r"raw (household|survey|record|row|data|data set|dataset|export)",
    r"household[- ]level (records|data|export|rows|file)",
    r"(phone|telephone|contact) numbers?",
    r"personally identifiable|pii\b|identities? of",
    r"export the (raw|household|survey|source|dataset)",
    r"one row per (household|person|individual|respondent)",
    r"give me (the )?(row|record|observation)s? (for|of|with)",
)

# Words that make a broad word ("quality", "evidence", "calculated") refer to
# this project rather than to general knowledge. Broad categories are gated on
# these so an ordinary question still reaches the general-knowledge layer even
# when it happens to contain a project-ish keyword.
_PROJECT_TERMS = re.compile(
    r"\b(?:insightrwanda|finscope|financial inclusion|survey|dataset|data set|"
    r"dashboard|indicator|catalog|methodolog|questionnaire|variable|household|"
    r"fi-\d{2}|ei-\d{2})\b"
)
_THIS_REFERENCE = re.compile(
    r"\b(?:this|that|these|those)\s+"
    r"(?:percentage|number|figure|share|rate|estimate|statistic|indicator|"
    r"chart|graph|page|view|dashboard|data|source)s?\b"
)
_GREETING = re.compile(
    r"^(?:hi|hello|hey|hiya|howdy|yo|greetings|good\s+(?:morning|afternoon|evening|day))"
    r"(?:\s+(?:there|everyone|all|team|folks))?[\s!.,?]*$"
)


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", " ".join(str(question).split())).strip()


# --- Verified inline charts --------------------------------------------------
# Charts are built from the same tested calculation functions as every
# dashboard figure (weighted_mean / calculate_by_group). A chart is an
# honest re-presentation of verified numbers, never a new analysis.

_GROUP_COLUMNS: dict[str, str] = {
    "province": "province",
    "district": "district",
    "urban": "setting",
    "rural": "setting",
}
_GROUP_LABELS: dict[str, str] = {
    "province": "province",
    "district": "district",
    "setting": "urban/rural setting",
}


@dataclass(frozen=True)
class AssistantChart:
    """One verified group breakdown, rendered as a bar chart by the app."""

    indicator_id: str
    title: str
    group_label: str
    note: str
    rows: tuple[tuple[str, float], ...]  # (group label, weighted share 0..1)
    counts: tuple[tuple[str, int, int], ...]  # (group, numerator n, valid n)


def chart_request(question: str, indicator_hint: str = "") -> tuple[str, str] | None:
    """Detect a chart/breakdown request and resolve it to (indicator id, group).

    Returns ``None`` unless the question explicitly asks for a chart/graph/plot
    (or "show … by province/urban/rural"), resolves to an FI indicator, and the
    requested group column name is one the core can compute. Restricted
    requests never reach decision logic here: the caller still runs the full
    answer path, which refuses them.
    """

    text = _normalize(question).lower()
    chart_words = re.search(
        r"\b(charts?|graphs?|plots?|visual(s|ise|ize|ased|ized)?|bar chart|breakdown|comparison|compare)\b",
        text,
    )
    by_group = re.search(r"\bby\b", text) is not None and re.search(
        r"\b(province|district|urban|rural)\b", text
    )
    if chart_words is None and not by_group:
        return None
    indicator_id = resolve_indicator(question, indicator_hint)
    if indicator_id is None or indicator_id not in INDICATORS:
        return None
    match = re.search(r"\bby\s+(province|district|urban|urban and rural|urban/rural|rural)\b", text)
    group_word = match.group(1) if match else None
    if group_word is None:
        mixed = re.search(r"\b(urban and rural|urban/rural)\b", text)
        if mixed:
            group_word = "urban"
        else:
            for word in _GROUP_COLUMNS:
                if re.search(rf"\b{word}\b", text):
                    group_word = word
                    break
    if group_word is None:
        # A chart without a named group defaults to the province breakdown.
        group_word = "province"
    column = _GROUP_COLUMNS.get(group_word)
    if column is None:
        return None
    return indicator_id, column


def chart_for_indicator(
    frame: pd.DataFrame | None,
    indicator_id: str,
    group_column: str,
) -> AssistantChart | None:
    """Compute a verified group breakdown, or ``None`` when not reproducible."""

    if frame is None:
        return None
    definition = INDICATORS[indicator_id]
    try:
        table = calculate_by_group(frame, indicator_id, group_column)
    except (KeyError, ValueError):
        return None
    chart_rows: list[tuple[str, float]] = []
    chart_counts: list[tuple[str, int, int]] = []
    table = table[table["denominator_n"].gt(0) & table["estimate"].notna()]
    for row in table.itertuples(index=False):
        name = "Unknown" if row.group is None or (isinstance(row.group, float) and pd.isna(row.group)) else str(row.group)
        chart_rows.append((name, float(row.estimate)))
        chart_counts.append((name, int(row.numerator_n), int(row.denominator_n)))
    if not chart_rows:
        return None
    chart_rows.sort(key=lambda item: item[1], reverse=True)
    order = {name: index for index, (name, _share) in enumerate(chart_rows)}
    chart_counts.sort(key=lambda item: order.get(item[0], 999))
    limitation = definition.limitations[0] if definition.limitations else ""
    return AssistantChart(
        indicator_id=indicator_id,
        title=f"{indicator_id} · {definition.title} by {_GROUP_LABELS[group_column]}",
        group_label=_GROUP_LABELS[group_column],
        note=limitation,
        rows=tuple(chart_rows),
        counts=tuple(chart_counts),
    )


def answer_with_chart(
    question: str,
    *,
    frame: pd.DataFrame | None = None,
    profile: SourceProfile | None = None,
    source_label: str = "",
    lens_note: str = "",
    indicator_hint: str = "",
) -> tuple[AssistantAnswer, AssistantChart | None] | None:
    """Build the verified text answer plus chart data for a chart request.

    Returns ``None`` when the question is not a chart request (the caller then
    uses ``answer_question`` unchanged — refusals, fallbacks and general mode
    all stay on their normal paths). The text itself carries no figures: the
    numbers live in the chart and its table, computed live from the active
    records with the same tested household-weight functions the dashboard uses.
    """

    request = chart_request(question, indicator_hint)
    if request is None:
        return None
    indicator_id, group_column = request
    definition = INDICATORS[indicator_id]
    chart = chart_for_indicator(frame, indicator_id, group_column)
    if chart is None:
        parts = [
            f"I can draw a bar chart of a verified financial-inclusion indicator "
            f"(FI-01…FI-06) by province, district, or urban/rural setting.",
            f"This one is not reproducible on the active survey source, so no chart is "
            f"shown: {indicator_id} needs columns that have no label-verified "
            f"counterpart there. It is withheld rather than approximated.",
        ]
        references = (
            EvidenceReference(definition.indicator_id, definition.title, definition.unit),
            _page_reference("Financial inclusion"),
            _page_reference("Methods & sources"),
        )
        return AssistantAnswer(
            question_kind="chart_unavailable",
            answer="\n".join(parts),
            references=references,
            grounded=False,
            scope="project evidence",
        ), None
    parts = [
        f"{chart.title} — weighted share of valid respondents in each {chart.group_label}.",
        f"{_lens_prefix(lens_note)}The bars come from the same tested household-weight "
        f"calculation the dashboard uses; the numbers sit on the bars and in the table "
        f"beneath the chart.",
    ]
    references = [
        EvidenceReference(definition.indicator_id, definition.title, definition.unit),
        _page_reference("Financial inclusion"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
        parts.append(f"Source: {_dataset_line(profile, source_label)}.")
    if chart.note:
        parts.append(f"Keep in mind: {chart.note}")
        references.append(EvidenceReference(f"{indicator_id} limitation", chart.note))
    return AssistantAnswer(
        question_kind="chart",
        answer="\n".join(parts),
        references=tuple(references),
        grounded=True,
        numeric_verified=False,
        scope="project evidence",
        applied_lens=lens_note,
    ), chart


def resolve_indicator(question: str, hint: str = "") -> str | None:
    """Map free text (plus an optional active-indicator hint) to an indicator id.

    Explicit mentions win; an unresolvable "this indicator" falls back to the
    caller-provided hint (the active page context).
    """

    text = _normalize(question).lower()
    hint_id = _normalize(hint).upper() if hint else None
    probe = re.search(r"\b(fi|ei)-\d{2}\b", text)
    if probe:
        candidate = probe.group(0).upper()
        if candidate in INDICATORS or candidate in CONTEXT_ESTIMATES:
            return candidate
    best: tuple[int, str] | None = None
    for indicator_id, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in text and (best is None or len(alias) > best[0]):
                best = (len(alias), indicator_id)
    if best:
        # An explicit id-style probe never reaches here (handled above).
        return best[1]
    if hint_id and re.search(r"\b(this|it|that one)\b", text) and (
        hint_id in INDICATORS or hint_id in CONTEXT_ESTIMATES
    ):
        # "this indicator" / pronoun follow-ups resolve to the active page's indicator.
        return hint_id
    return None


def _page_from_text(text: str) -> str | None:
    low = _normalize(text).lower()
    hits = [page for page, aliases in _PAGE_ALIASES.items() for alias in aliases if alias in low]
    return hits[0] if len(set(hits)) == 1 else None


def _dataset_reference(profile: SourceProfile | None, source_label: str) -> EvidenceReference | None:
    if profile is not None:
        detail = f"{profile.format} · {profile.rows:,} records"
        return EvidenceReference(profile.source_id, source_label or "Active survey source", detail)
    if source_label:
        return EvidenceReference("source-profile-not-loaded", source_label, "Profile not loaded")
    return None


def _page_reference(page: str) -> EvidenceReference:
    return EvidenceReference(page, "Dashboard page", _PAGE_NUMBERS.get(page, page))


def _dataset_line(profile: SourceProfile | None, source_label: str) -> str:
    if profile is not None:
        return f"{source_label or profile.format} ({profile.source_id}, {profile.format})"
    return source_label or "the active survey source"


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


def _lens_prefix(lens_note: str) -> str:
    return f"Applied lens: {lens_note}. " if lens_note else ""


def _live_fi_result(frame: pd.DataFrame, indicator_id: str) -> tuple[object | None, str | None]:
    """Compute an FI estimate with the tested function, or explain why not."""

    try:
        return calculate_indicator(frame, indicator_id), None
    except (KeyError, ValueError) as exc:
        message = str(exc)
        if "missing" in message.lower() or "absent" in message.lower() or "needs" in message.lower():
            return None, (
                "This estimate is not reproducible on the active survey source: the columns it "
                "needs have no label-verified counterpart there. The dashboard withholds it "
                "rather than approximating it."
            )
        return None, None


def _explain_indicator(
    indicator_id: str,
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
    lens_note: str,
) -> tuple[str, tuple[EvidenceReference, ...], bool]:
    if indicator_id in INDICATORS:
        definition = INDICATORS[indicator_id]
        page = "Financial inclusion"
    else:
        definition = CONTEXT_ESTIMATES[indicator_id]
        page = "Poverty insights"
    parts: list[str] = [
        f"{definition.indicator_id} · {definition.title}. "
        f"In simple terms: {_SIMPLER.get(definition.indicator_id, definition.definition)}",
        f"Definition used in code: {definition.definition}",
        f"How it is calculated: {definition.method} Population: {definition.population}. "
        f"Valid-response rule: {definition.valid_response_rule}",
    ]
    references = [
        EvidenceReference(definition.indicator_id, definition.title, definition.unit),
        _page_reference(page),
    ]
    numeric = False
    if frame is not None:
        if indicator_id in INDICATORS:
            result, unavailable = _live_fi_result(frame, indicator_id)
            if result is not None:
                parts.append(
                    f"{_lens_prefix(lens_note)}From the loaded records, weighted with the survey's "
                    f"household weight: {_format_share(result.estimate)} "
                    f"({result.numerator_n:,} of {result.denominator_n:,} respondents)."
                )
                if result.note:
                    parts.append(f"Note: {result.note}")
                numeric = True
            elif unavailable:
                parts.append(unavailable)
        else:
            try:
                context = calculate_context_estimate(frame, indicator_id)
            except (KeyError, ValueError):
                parts.append(
                    "This estimate is not reproducible on the active survey source: its income-band "
                    "column has no label-verified counterpart there. It is withheld rather than "
                    "approximated."
                )
            else:
                parts.append(
                    f"{_lens_prefix(lens_note)}From the loaded records, weighted with the survey's "
                    f"household weight: {_format_share(context['estimate'])}. "
                    "This is a financial-context statistic, not a poverty headcount."
                )
                numeric = True
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
        parts.append(f"Source: {_dataset_line(profile, source_label)}.")
    verified = definition.verification
    parts.append(f"Verification: {verified}")
    limitations = definition.limitations
    if limitations:
        parts.append("Keep in mind: " + " ".join(limitations))
        for limit in limitations:
            references.append(EvidenceReference(f"{definition.indicator_id} limitation", limit))
    return "\n".join(parts), tuple(references), numeric


def _income_expenses_answer(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
    lens_note: str,
) -> tuple[str, tuple[EvidenceReference, ...], bool]:
    """Answer broad income/expenses questions from the approved context measures."""

    parts = [
        "In this project, income and expenses are represented mainly through income pressure: "
        "whether reported income covers living costs monthly or more often.",
        "The dashboard also reports self-reported monthly personal income and annual income bands as context.",
    ]
    references = [
        EvidenceReference("FI-05", INDICATORS["FI-05"].title, INDICATORS["FI-05"].unit),
        _page_reference("Poverty insights"),
    ]
    numeric = False
    if frame is not None:
        pressure, _unavailable = _live_fi_result(frame, "FI-05")
        if pressure is not None:
            parts.append(
                f"{_lens_prefix(lens_note)}Income pressure is {_format_share(pressure.estimate)} "
                f"({pressure.numerator_n:,} of {pressure.denominator_n:,} valid respondents)."
            )
            numeric = True
        for estimate_id in ("EI-01", "EI-02", "EI-03"):
            try:
                context = calculate_context_estimate(frame, estimate_id)
            except (KeyError, ValueError):
                continue
            definition = CONTEXT_ESTIMATES[estimate_id]
            parts.append(f"{definition.title}: {_format_share(context['estimate'])}.")
            references.append(EvidenceReference(estimate_id, definition.title, definition.unit))
            numeric = True
    parts.append(
        "The supplied analytical slice does not contain a complete household expenditure or "
        "consumption aggregate. These are financial-context measures, not an official poverty rate "
        "or poverty gap."
    )
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
        parts.append(f"Source: {_dataset_line(profile, source_label)}.")
    return "\n".join(parts), tuple(references), numeric


def _provenance(
    indicator_id: str,
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
    lens_note: str,
) -> tuple[str, tuple[EvidenceReference, ...], bool]:
    definition = INDICATORS.get(indicator_id) or CONTEXT_ESTIMATES.get(indicator_id)
    if definition is None:
        return "", (), False
    page = "Financial inclusion" if indicator_id in INDICATORS else "Poverty insights"
    parts = [
        f"{definition.indicator_id} · {definition.title} is computed directly from the loaded "
        f"survey records: {definition.method}",
        f"It reads {', '.join(definition.source_variables)} with the valid-response rule: "
        f"{definition.valid_response_rule}",
        f"Which survey question(s): {', '.join(definition.source_variables)}. "
        f"Verified: {definition.verification}",
        "The number shown on the dashboard is this same project-calculated estimate — it is not "
        "an official published statistic, and no survey-design standard error is attached "
        "(no PSU/strata/variance documentation was supplied).",
    ]
    references = [
        EvidenceReference(definition.indicator_id, definition.title, definition.method),
        _page_reference(page),
    ]
    numeric = False
    if frame is not None:
        if indicator_id in INDICATORS:
            result, unavailable = _live_fi_result(frame, indicator_id)
            if result is not None:
                parts.append(
                    f"{_lens_prefix(lens_note)}At the current lens it equals "
                    f"{_format_share(result.estimate)} ({result.numerator_n:,} of "
                    f"{result.denominator_n:,} respondents)."
                )
                numeric = True
            elif unavailable:
                parts.append(unavailable)
        else:
            try:
                context = calculate_context_estimate(frame, indicator_id)
            except (KeyError, ValueError):
                parts.append(
                    "This estimate is not reproducible on the active survey source: its income-band "
                    "column has no label-verified counterpart there. It is withheld rather than "
                    "approximated."
                )
            else:
                parts.append(
                    f"{_lens_prefix(lens_note)}At the current lens it equals "
                    f"{_format_share(context['estimate'])}."
                )
                numeric = True
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
        parts.append(f"Source: {_dataset_line(profile, source_label)}.")
    for limit in definition.limitations:
        references.append(EvidenceReference(f"{definition.indicator_id} limitation", limit))
    return "\n".join(parts), tuple(references), numeric


def _poverty_blockers(profile: SourceProfile | None, source_label: str) -> tuple[str, tuple[EvidenceReference, ...]]:
    status = official_poverty_status()
    blockers = "\n".join(f"  · {blocker}" for blocker in status.missing)
    parts = [
        "There is no official poverty estimate in this project, and the app will not guess one.",
        "An official estimate is contract-locked in code. It would run only when every one of "
        "these inputs is supplied by a data steward — none of them is supplied today:",
        blockers,
        "Nothing is inferred or defaulted while any input is missing. What the app does offer is "
        "clearly-labelled context: weighted income-band statistics (EI-01…EI-03), which are "
        "financial-context descriptions, not poverty headcounts.",
    ]
    references = (
        EvidenceReference("Official-poverty contract", "official_poverty_status()", "Six required inputs; none supplied"),
        _page_reference("Poverty insights"),
    )
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references = (*references, dataset)
    return "\n".join(parts), references


def _indicator_catalog_answer(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    """List the approved indicators and their definitions — no figures invented."""

    parts = [
        "The dashboard reports six financial-inclusion indicators, each defined in the "
        "project's indicator catalogue and computed only from the loaded survey records:",
    ]
    for definition in INDICATORS.values():
        parts.append(f"  · {definition.indicator_id} · {definition.title}: {definition.definition}")
    parts.append(
        "Three income-context statistics are reported alongside them: "
        + "; ".join(f"{definition.indicator_id} · {definition.title}" for definition in CONTEXT_ESTIMATES.values())
        + ". They are financial-context descriptions, not a poverty headcount."
    )
    if frame is not None:
        withheld: list[str] = []
        for indicator_id in INDICATORS:
            try:
                calculate_indicator(frame, indicator_id)
            except (KeyError, ValueError):
                withheld.append(indicator_id)
        for estimate_id in CONTEXT_ESTIMATES:
            try:
                calculate_context_estimate(frame, estimate_id)
            except (KeyError, ValueError):
                withheld.append(estimate_id)
        if withheld:
            parts.append(
                "Not reproducible on the active source (no label-verified counterpart): "
                + ", ".join(withheld)
                + " — withheld rather than approximated."
            )
        else:
            parts.append("All nine are reproducible on the active source.")
    parts.append(
        "Every figure is a weighted share using the survey's household weight; its numerator "
        "and denominator accompany the answer, and no value is borrowed from outside the "
        "supplied files."
    )
    references = [
        EvidenceReference("Indicator catalogue", "Approved FI and EI definitions",
                          "6 FI indicators · 3 income-context statistics"),
        _page_reference("Financial inclusion"),
        _page_reference("Poverty insights"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
    return "\n".join(parts), tuple(references)


def _indicator_methods_answer(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    """Explain the shared calculation method using only the documented definitions."""

    parts = [
        "The reported indicators are not copied from a published table and are not produced "
        "by a model: each one is computed in the app from the loaded survey records.",
        "Method for every share: take the indicator's yes/no condition, keep only records whose "
        "response is valid under that indicator's documented rule, then compute a weighted mean "
        "using the survey's household weight (hh_wt). Numerator and denominator counts are "
        "reported with the estimate. Invalid codes and missing values are excluded — never "
        "imputed or treated as “No”.",
        "Per-indicator method, exactly as written in the project's indicator catalogue:",
    ]
    for definition in INDICATORS.values():
        parts.append(f"  · {definition.indicator_id}: {definition.method}")
    for definition in CONTEXT_ESTIMATES.values():
        parts.append(
            f"  · {definition.indicator_id}: {definition.method} "
            "This is income context, not a poverty headcount."
        )
    parts.append(
        "Survey-design standard errors are not produced: no PSU/strata/variance documentation "
        "was supplied, so no interval is presented as a design-based confidence interval."
    )
    references = [
        EvidenceReference("Indicator catalogue", "Approved calculation methods",
                          "Weighted shares from the loaded records"),
        _page_reference("Financial inclusion"),
        _page_reference("Poverty insights"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
    if frame is None:
        parts.append("No active source is loaded in this conversation, so no figure is quoted here.")
    return "\n".join(parts), tuple(references)


def _quality_limitations_answer(
    checks: Sequence[QualityCheck] | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    """State exactly what the executed checks do and do not establish."""

    if not checks:
        return (
            "No quality checks are loaded in this conversation, so I cannot describe their "
            "limitations without inventing them. Open Data quality (Page 07) with an active "
            "source and ask again."
        ), (_page_reference("Data quality"),)
    summary = quality_summary(list(checks))
    counts = ", ".join(f"{summary.get(grade, 0)} {grade}" for grade in ("PASS", "WARN", "FAIL", "INFO"))
    parts = [
        f"{len(checks)} quality checks ran on the loaded records ({counts}).",
        "They verify structure and coding integrity: required columns, record counts, key "
        "behaviour, survey weights, geographic codes and value ranges. They do not certify "
        "representativeness, fieldwork quality, non-response bias or official statistical "
        "publication.",
        "Missing or invalid responses are measured and excluded; they are never imputed or "
        "silently recoded.",
    ]
    problems = [check for check in checks if check.status in {"WARN", "FAIL"}]
    if problems:
        listed = "; ".join(
            f"{check.check_id} ({check.status}): {check.finding.rstrip('.')}" for check in problems[:4]
        )
        parts.append(f"Checks raising a warning or failure on this view: {listed}.")
    else:
        parts.append(
            "No check raised a warning or failure on this view — which is still not a "
            "representativeness or publication certificate. Informational checks (for example "
            "measured missingness) carry no verdict."
        )
    parts.append(
        "Cross-cutting limitation: no PSU/strata/variance documentation was supplied, so no "
        "figure carries a survey-design standard error or a design-based confidence interval."
    )
    references = [
        EvidenceReference("Data quality checks", f"{len(checks)} executed checks", counts),
        _page_reference("Data quality"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
    return "\n".join(parts), tuple(references)


def _verification_answer(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    checks: Sequence[QualityCheck] | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    """Separate what is verified in code from what still needs a data steward."""

    parts = [
        "Verification status, stated plainly — verified evidence first, open items second.",
        "Verified in code: the six financial-inclusion definitions are matched to embedded "
        "Stata variable labels, apply their documented valid-response rules, and report the "
        "numerator and denominator behind every share. These are project-calculated "
        "descriptive statistics, not official published rates.",
        "Requires further verification before any of it can be treated as an official finding:",
        "  · Survey-design uncertainty — no PSU/strata/variance documentation was supplied, so "
        "no standard error is claimed; the interval on the Poverty page comes from a weighted "
        "bootstrap over the loaded records, not a design-based calculation.",
        "  · Official poverty estimate — all six contract inputs are missing (documented "
        "poverty line, poverty concept, verified welfare aggregate, variance documentation, "
        "authorization record and publication approval), so no poverty rate is produced.",
    ]
    if profile is not None:
        parts.append(
            f"  · Authorization and publication — {profile.authorization_status}; "
            f"{profile.publication_status}"
        )
    if checks:
        non_pass = [check for check in checks if check.status != "PASS"]
        if non_pass:
            listed = "; ".join(f"{check.check_id} ({check.status})" for check in non_pass[:4])
            parts.append(f"  · Data-quality checks needing attention — {listed}.")
        else:
            parts.append("  · Data-quality checks — none failed on this view; scope limits still apply.")
    else:
        parts.append("  · Data-quality checks — none loaded, so no verification of structure is available here.")
    if frame is not None:
        withheld: list[str] = []
        for indicator_id in INDICATORS:
            try:
                calculate_indicator(frame, indicator_id)
            except (KeyError, ValueError):
                withheld.append(indicator_id)
        for estimate_id in CONTEXT_ESTIMATES:
            try:
                calculate_context_estimate(frame, estimate_id)
            except (KeyError, ValueError):
                withheld.append(estimate_id)
        if withheld:
            parts.append(
                "  · Source coverage — not reproducible here without a label-verified "
                "counterpart: " + ", ".join(withheld) + " (withheld, not approximated)."
            )
    parts.append(
        "No answer from this assistant is an official NISR conclusion; treat everything here "
        "as project evidence awaiting the approvals above."
    )
    references = [
        EvidenceReference("Official-poverty contract", "official_poverty_status()", "Six required inputs; none supplied"),
        EvidenceReference("Data quality checks", "Structure and coding verification", source_label or "Active source"),
        _page_reference("Data quality"),
        _page_reference("Methods & sources"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None and all(dataset.identifier != ref.identifier for ref in references):
        references.append(dataset)
    return "\n".join(parts), tuple(references)


def _checks_answer(
    checks: Sequence[QualityCheck] | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    if not checks:
        return (
            "No quality checks are loaded in this conversation, so I cannot describe them "
            "without inventing them. Open Data quality (Page 07) with an active source and ask again."
        ), (_page_reference("Data quality"),)
    summary = quality_summary(list(checks))
    total = len(checks)
    counts = ", ".join(f"{summary.get(grade, 0)} {grade}" for grade in ("PASS", "WARN", "FAIL", "INFO"))
    parts = [f"{total} quality checks were run on the loaded records ({counts})."]
    non_pass = [check for check in checks if check.status != "PASS"]
    if non_pass:
        listed = "; ".join(f"{check.check_id} ({check.status}): {check.finding}" for check in non_pass[:4])
        parts.append(f"Notable non-PASS checks: {listed}.")
    else:
        parts.append("All checks passed on this view.")
    parts.append(
        "These checks describe data structure and coding integrity. They do not certify "
        "representativeness, fieldwork quality, or official statistical publication."
    )
    references = [
        EvidenceReference("Data quality checks", f"{total} executed checks", f"{counts}"),
        _page_reference("Data quality"),
    ]
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
    return "\n".join(parts), tuple(references)


def _source_evidence(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    if profile is None:
        return (
            "No source profile is loaded in this conversation, so I cannot make claims about "
            "the file. Load a survey source in the app and ask again, or read Methods & sources (Page 09)."
        ), (_page_reference("Methods & sources"),)
    parts = [
        f"Active source: {source_label or profile.format} — id {profile.source_id}, "
        f"{profile.format}, {profile.rows:,} records, analysis version {profile.analysis_version}.",
        f"Authorization status: {profile.authorization_status} Publication status: {profile.publication_status}",
        f"Analysis status: {profile.analysis_status}",
    ]
    if frame is not None:
        reproducible: list[str] = []
        withheld: list[str] = []
        for indicator_id in INDICATORS:
            try:
                calculate_indicator(frame, indicator_id)
                reproducible.append(indicator_id)
            except (KeyError, ValueError):
                withheld.append(indicator_id)
        context_reproducible: list[str] = []
        for estimate_id in CONTEXT_ESTIMATES:
            try:
                calculate_context_estimate(frame, estimate_id)
                context_reproducible.append(estimate_id)
            except (KeyError, ValueError):
                withheld.append(estimate_id)
        solved = ", ".join((*reproducible, *context_reproducible)) or "none"
        parts.append(f"Indicators reproducible on this source: {solved}.")
        if withheld:
            parts.append(
                "Withheld on this source (no label-verified counterpart): "
                + ", ".join(withheld)
                + " — nothing is imputed or substituted for them."
            )
    gate = aggregate_release_allowed(profile)
    parts.append(
        "Aggregate export in the Data explorer is gated in code and currently "
        f"{'open' if gate else 'closed'}: {profile.publication_status}"
    )
    parts.append(HONESTY_STATEMENT)
    references = [
        EvidenceReference(profile.source_id, source_label or "Active survey source",
                          f"{profile.format} · {profile.rows:,} records"),
        _page_reference("Methods & sources"),
    ]
    return "\n".join(parts), tuple(references)


def _page_narrative(
    page: str,
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    checks: Sequence[QualityCheck] | None,
) -> tuple[str, tuple[EvidenceReference, ...]] | None:
    if frame is None:
        return None
    try:
        brief = build_page_brief(page, frame, profile, checks)
    except (ValueError, KeyError):
        return None
    text = f"{brief.title}. {brief.narrative} Caution: {brief.caution}"
    references = [_page_reference(page)]
    dataset = _dataset_reference(profile, "")
    if dataset is not None:
        references.append(dataset)
    references.append(EvidenceReference("Honesty statement", HONESTY_STATEMENT))
    return text, tuple(references)


def _identity_answer(
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    checks: Sequence[QualityCheck] | None,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    parts = [
        "InsightRwanda is a research-analytics prototype for the NISR 2026 Big Data Hackathon. "
        "It turns the supplied survey files into weighted, rule-based indicators across ten dashboard "
        "pages, and every figure is traceable to its indicator definition, denominator and source "
        "variables.",
        "Its core thesis: account access is not resilience — the gap between formal financial access "
        "and household shock absorption is what the lens explores.",
    ]
    narrative = _page_narrative("About the build", frame, profile, checks)
    if narrative is not None:
        text, references = narrative
        parts.append(f"From the project brief: {text}")
    else:
        parts.append(HONESTY_STATEMENT)
        references = (EvidenceReference("Honesty statement", HONESTY_STATEMENT), _page_reference("About the build"))
    return "\n".join(parts), tuple(references)


def _limitations_answer(
    indicator_id: str,
    frame: pd.DataFrame | None,
    profile: SourceProfile | None,
    source_label: str,
) -> tuple[str, tuple[EvidenceReference, ...]]:
    definition = INDICATORS.get(indicator_id) or CONTEXT_ESTIMATES.get(indicator_id)
    if definition is None:
        return "", ()
    lines = [f"Documented limitations of {definition.indicator_id} · {definition.title}:"]
    for limit in definition.limitations:
        lines.append(f"  · {limit}")
    lines.append(
        "Cross-cutting: no PSU/strata/variance documentation was supplied, so no survey-design "
        "standard error accompanies any estimate."
    )
    references = [
        EvidenceReference(definition.indicator_id, definition.title, definition.unit),
    ]
    if frame is not None and indicator_id in INDICATORS:
        result, _unavailable = _live_fi_result(frame, indicator_id)
        if result is not None and result.note:
            lines.append(f"Active-source note: {result.note}")
    dataset = _dataset_reference(profile, source_label)
    if dataset is not None:
        references.append(dataset)
    return "\n".join(lines), tuple(references)


def _refusal(kind: str, question_text: str) -> AssistantAnswer:
    if kind == "privacy":
        return AssistantAnswer(
            question_kind=kind,
            answer=(
                "I can't help with that. This assistant works with approved aggregate statistics "
                "only — it never lists households, reveals identities or exports row-level "
                "records, and it will not bypass disclosure controls. Household-level and "
                "personal information is not part of what the project publishes."
            ),
            references=(
                EvidenceReference("Disclosure boundary", HONESTY_STATEMENT),
                _page_reference("About the build"),
            ),
            grounded=False,
            scope="out of scope",
        )
    return AssistantAnswer(
        question_kind=kind,
        answer=(
            "I can answer ordinary questions, but I can't change calculations, bypass approval "
            "gates, unlock exports or reveal internal instructions — those controls are written "
            "into the app's code on purpose.\n"
            "Ask me about an indicator (for example FI-02), the data-quality checks, the active "
            "survey source, why the official poverty estimate is unavailable, or any general "
            "topic outside this project."
        ),
        references=(_page_reference(_FALLBACK_PAGE),),
        grounded=False,
        scope="out of scope",
    )


def _greeting_answer() -> AssistantAnswer:
    return AssistantAnswer(
        question_kind="greeting",
        answer=(
            "Hello! I'm the InsightRwanda evidence assistant. I can explain what the project is, "
            "any indicator (FI-01…FI-06 or EI-01…EI-03) in simple English, where a dashboard "
            "number comes from, the documented limitations of an estimate, the data-quality "
            "checks, the active survey source's evidence, and why no official poverty estimate "
            "exists.\n"
            "Ask a short question — for example: “What does FI-02 mean in simple English?”"
        ),
        references=(_page_reference(_FALLBACK_PAGE),),
        grounded=False,
        scope="general explanation",
    )


def _fallback_answer() -> AssistantAnswer:
    return AssistantAnswer(
        question_kind="fallback",
        answer=(
            "I don't have verified evidence for that question, and I won't improvise one. "
            "I can explain: what InsightRwanda is, an indicator (FI-01…FI-06 or EI-01…EI-03) in "
            "simple English, where a dashboard number comes from, the documented limitations of an "
            "estimate, the data-quality checks, the active survey source's evidence, and why no "
            "official poverty estimate exists.\n"
            "Try rephrasing with an indicator id, or open Methods & sources (Page 09) for the full "
            "methodology trail."
        ),
        references=(_page_reference(_FALLBACK_PAGE),),
        grounded=False,
        scope="general explanation",
    )


def _too_long() -> AssistantAnswer:
    return AssistantAnswer(
        question_kind="too_long",
        answer=(
            "That question is too long for me to read reliably. Please break it into a short, "
            "focused question — for example: “Why is there no official poverty rate?”."
        ),
        references=(),
        grounded=False,
        scope="general explanation",
    )


def _empty_answer() -> AssistantAnswer:
    return AssistantAnswer(
        question_kind="empty",
        answer="Please type a question — for example: “What does FI-02 mean in simple English?”.",
        references=(),
        grounded=False,
        scope="general explanation",
    )


def _classify(text: str) -> str:
    low = text.lower()
    if any(re.search(pattern, low) for pattern in _INJECTION_PATTERNS):
        return "injection"
    if any(re.search(pattern, low) for pattern in _PRIVACY_PATTERNS):
        return "privacy"
    if _GREETING.match(low):
        return "greeting"
    project_context = _PROJECT_TERMS.search(low) is not None
    if re.search(
        r"quality.{0,40}(limitation|caveat|weakness|problem|issue)|"
        r"(limitation|caveat).{0,30}quality",
        low,
    ) and (project_context or "data quality" in low):
        return "quality_limitations"
    if re.search(
        r"(require|required|need|needs|pending).{0,30}(further |more )?(verification|validation|confirm)|"
        r"(unverified|not (yet )?verified|without verification)|which findings|"
        r"what (still )?needs? (to be )?(verif|check|confirm)",
        low,
    ):
        return "verification_status"
    if "indicators" in low and re.search(
        r"\b(list|available|all|which|what are|explain|describe|show)\b", low
    ) and (project_context or "available" in low or "all indicators" in low):
        return "indicator_catalog"
    poverty_words = ("why", "unavailable", "missing", "blocker", "gated", "not available", "no official")
    if (
        "poverty" in low
        and any(word in low for word in poverty_words)
        and "explain" not in low
        and (project_context or "official" in low)
    ):
        return "poverty_blockers"
    if re.search(r"what is insight ?rwanda|tell me about (this|the) (project|app|product|platform)", low):
        return "identity"
    if re.search(r"\b(income|earnings)\b", low) and re.search(
        r"\b(expenses?|expenditure|costs?|spend(?:ing)?|money left|living costs)\b", low
    ):
        return "income_expenses"
    if re.search(
        r"where (did|does|do).{0,60}(come from|derive[ds]?|from)|"
        r"how (is|was|were|are).{0,60}(calculat|comput|derive)",
        low,
    ) and (project_context or _THIS_REFERENCE.search(low) or "reported" in low):
        return "estimate_provenance"
    if re.search(r"is (this|that|it|the).{0,30}official", low):
        return "estimate_provenance"
    if re.search(r"\bchecks?\b|quality|what was (checked|tested|verified)", low) and (
        project_context
        or re.search(
            r"checks? (were|was) (performed|run|done)|"
            r"checks? (do|does|did) (you|this|the (app|project|dashboard|source|survey))|"
            r"data quality (check|limitation|issue|problem)|"
            r"quality (control|assurance)",
            low,
        )
    ):
        return "checks"
    if re.search(
        r"what (evidence|data|indicators).{0,40}(available|support|cover)|"
        r"reproducible|coverage",
        low,
    ) and project_context:
        return "source_evidence"
    if "limitation" in low or "caveat" in low or re.search(r"what (does|do).{0,50}not (measure|include|cover|mean)", low):
        return "limitations"
    if re.search(
        r"this (page|view|chart|graph)|page (show|about)|"
        r"what (does|is) (the|this).{0,30}(page|view)",
        low,
    ):
        return "page_narrative"
    return "unknown"


def answer_question(
    question: str,
    *,
    frame: pd.DataFrame | None = None,
    profile: SourceProfile | None = None,
    checks: Sequence[QualityCheck] | None = None,
    source_label: str = "",
    lens_note: str = "",
    page: str = "",
    indicator_hint: str = "",
) -> AssistantAnswer:
    """Answer a question from approved definitions plus live verified results.

    Parameters
    ----------
    question:
        Raw user text. Treated strictly as a question — never as instructions.
    frame:
        The active, loaded, enriched view (already filtered by the app's lens).
        Numbers are computed by the same tested functions the dashboard uses.
    profile:
        The active ``SourceProfile``; drives source identity, capability and
        governance wording. Optional — answers degrade honestly when absent.
    checks:
        Executed quality checks from ``run_quality_checks``; optional.
    source_label:
        Human-readable label of the active source (e.g. as shown in the UI).
    lens_note:
        Description of the applied filter lens, echoed on numeric answers.
    page:
        The dashboard page the user is on, used for "this page/chart" wording.
    indicator_hint:
        The indicator most relevant to the current page state, used for
        "this indicator" wording.
    """

    raw = _normalize(question)
    if not raw:
        return _empty_answer()
    if len(raw) > MAX_QUESTION_LENGTH:
        return _too_long()
    question = raw

    kind = _classify(question)
    if kind == "injection":
        return _refusal("injection", question)
    if kind == "privacy":
        return _refusal("privacy", question)

    if kind == "greeting":
        return _greeting_answer()

    if kind == "identity":
        text, references = _identity_answer(frame, profile, checks)
        return AssistantAnswer(kind, text, references, applied_lens=lens_note)

    if kind == "poverty_blockers":
        text, references = _poverty_blockers(profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "quality_limitations":
        text, references = _quality_limitations_answer(checks, profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "verification_status":
        text, references = _verification_answer(frame, profile, checks, source_label)
        return AssistantAnswer(kind, text, references, applied_lens=lens_note)

    if kind == "indicator_catalog":
        text, references = _indicator_catalog_answer(frame, profile, source_label)
        return AssistantAnswer(kind, text, references, applied_lens=lens_note)

    if kind == "checks":
        text, references = _checks_answer(checks, profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "source_evidence":
        text, references = _source_evidence(frame, profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "income_expenses":
        text, references, numeric = _income_expenses_answer(
            frame, profile, source_label, lens_note
        )
        return AssistantAnswer(kind, text, references, numeric_verified=numeric, applied_lens=lens_note)

    if kind == "page_narrative":
        # Page questions win over alias matching ("the Financial inclusion page" is
        # a page question, not a request to redefine FI-01).
        target = _page_from_text(question) or (page if page in PAGES else None)
        rendered = _page_narrative(target, frame, profile, checks) if target else None
        if rendered is not None:
            text, references = rendered
            return AssistantAnswer(kind, text, references)
        return _fallback_answer()

    if indicator_ref := resolve_indicator(question, indicator_hint):
        low = question.lower()
        if kind == "estimate_provenance" or "come from" in low:
            text, references, numeric = _provenance(indicator_ref, frame, profile, source_label, lens_note)
            return AssistantAnswer(kind, text, references, numeric_verified=numeric)
        if kind == "limitations" or "limitation" in low:
            text, references = _limitations_answer(indicator_ref, frame, profile, source_label)
            return AssistantAnswer(kind, text, references)
        text, references, numeric = _explain_indicator(indicator_ref, frame, profile, source_label, lens_note)
        return AssistantAnswer(
            "explain_indicator" if kind == "unknown" else kind,
            text, references, numeric_verified=numeric,
        )

    if kind == "estimate_provenance":
        # No single indicator is named: explain the shared method honestly rather
        # than pretending to trace one specific figure.
        text, references = _indicator_methods_answer(frame, profile, source_label)
        return AssistantAnswer("indicator_methods", text, references, applied_lens=lens_note)

    if kind == "limitations":
        return _fallback_answer()

    return _fallback_answer()
