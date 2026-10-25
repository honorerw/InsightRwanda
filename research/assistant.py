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
LLM, no network, no new dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

import pandas as pd

from research.briefs import HONESTY_STATEMENT, PAGES, build_page_brief
from research.catalog import SourceProfile, aggregate_release_allowed
from research.estimation import CONTEXT_ESTIMATES, calculate_context_estimate, official_poverty_status
from research.indicators import INDICATORS, calculate_indicator
from research.quality import QualityCheck, quality_summary

__all__ = [
    "AssistantAnswer",
    "EvidenceReference",
    "MAX_QUESTION_LENGTH",
    "answer_question",
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


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", " ".join(str(question).split())).strip()


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
            "I only answer questions about this project's evidence. I can't change calculations, "
            "bypass approval gates, unlock exports or reveal internal instructions — those controls "
            "are written into the app's code on purpose.\n"
            "Ask me about an indicator (for example FI-02), the data-quality checks, the active "
            "survey source, or why the official poverty estimate is unavailable."
        ),
        references=(_page_reference(_FALLBACK_PAGE),),
        grounded=False,
        scope="out of scope",
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
    poverty_words = ("why", "unavailable", "missing", "blocker", "gated", "not available", "no official")
    if "poverty" in low and any(word in low for word in poverty_words) and "explain" not in low:
        return "poverty_blockers"
    if re.search(r"what is insight ?rwanda|tell me about (this|the) (project|app|product|platform)", low):
        return "identity"
    if re.search(r"where (did|does|do).{0,60}(come from|derive[ds]?|from)|how (is|was|were|are).{0,60}(calculat|comput|derive)", low):
        return "estimate_provenance"
    if re.search(r"is (this|that|it|the).{0,30}official", low):
        return "estimate_provenance"
    if re.search(r"\bchecks?\b|quality|what was (checked|tested|verified)", low):
        return "checks"
    if re.search(r"what (evidence|data|indicators).{0,40}(available|support|cover)|reproducible|coverage", low):
        return "source_evidence"
    if "limitation" in low or "caveat" in low or re.search(r"what (does|do).{0,50}not (measure|include|cover|mean)", low):
        return "limitations"
    if re.search(r"\bchart\b|\bgraph\b|this (page|view)|page (show|about)", low):
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

    if kind == "identity":
        text, references = _identity_answer(frame, profile, checks)
        return AssistantAnswer(kind, text, references, applied_lens=lens_note)

    if kind == "poverty_blockers":
        text, references = _poverty_blockers(profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "checks":
        text, references = _checks_answer(checks, profile, source_label)
        return AssistantAnswer(kind, text, references)

    if kind == "source_evidence":
        text, references = _source_evidence(frame, profile, source_label)
        return AssistantAnswer(kind, text, references)

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
        return _fallback_answer()

    if kind == "limitations":
        return _fallback_answer()

    return _fallback_answer()
