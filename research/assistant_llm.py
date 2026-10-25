"""Optional AI explanation layer for Ask InsightRwanda (Phase C3).

DISABLED-BY-DEFAULT DESIGN
--------------------------
The deterministic assistant (``research.assistant``) stays the single source
of truth. This module can only let a model *reword* an answer that was
already assembled from verified evidence. It never computes statistics,
never picks alternative figures, never invents citations, and can never
change gate decisions — those belong to ``research.estimation``,
``research.catalog`` and ``research.indicators`` alone.

No provider is approved yet, so:

  - ``get_configured_provider()`` returns ``None`` unconditionally.
  - ``refine_answer()`` is a strict no-op (returns the deterministic answer).
  - No network access, no API key, no provider dependency is needed.

Numeric fidelity is enforced in code, not by prompt. ``refine_answer`` will
hand back the deterministic answer whenever:

  - the model wording is missing, malformed, or too long;
  - any protected token changes: figures, percentages, denominators,
    intervals, indicator IDs, page citations;
  - the provider raises any of the ``ProviderError`` subclasses (timeout,
    rate limit, missing credentials, unusable response, outage);
  - the deterministic answer is a refusal, fallback, or otherwise not
    evidence-bearing (refusals are never reworded, so a user question
    cannot use this layer to erode evidence restrictions).

Permitted model input (ONLY these strings):
  1. the user's question,
  2. the already-assembled deterministic answer,
  3. the approved static guidance text (REWRITE_GUIDANCE below),
  4. nothing else — ever: no row-level records, no DataFrames, no personal
     identifiers, no file paths, no exception traces, no secrets.

Source references are never sent to (or produced by) a model; they stay on
the ``AssistantAnswer`` untouched and are attached unchanged to the final
response.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Protocol

from research.assistant import AssistantAnswer

__all__ = [
    "ExplanationPayload",
    "ExplanationProvider",
    "ProviderError",
    "ProviderTimeout",
    "ProviderRateLimited",
    "ProviderInvalidResponse",
    "REWRITE_GUIDANCE",
    "MAX_WORDING_CHARS",
    "build_explanation_payload",
    "wording_preserves_evidence",
    "get_configured_provider",
    "refine_answer",
]

# Kinds whose answers are evidence-bearing and may be offered for rewording.
# Refusals ("injection"/"privacy"), no-evidence fallbacks and engine-side
# empty/over-long responses are never sent to any model on any path.
_REWORDABLE_KINDS = frozenset({
    "explain_indicator",
    "estimate_provenance",
    "limitations",
    "identity",
    "poverty_blockers",
    "checks",
    "source_evidence",
    "page_narrative",
})

MAX_WORDING_CHARS = 4_000

REWRITE_GUIDANCE = (
    "You are the plain-English editor for the Ask InsightRwanda assistant. "
    "Rewrite the verified answer below so it reads naturally while keeping the "
    "same structure and length. STRICT RULES: keep every figure, percentage, "
    "count, ratio, interval, indicator ID and 'Page NN' citation exactly as "
    "written; keep every hesitation about withheld estimates, missing official "
    "statistics and documented limitations in meaning; add no new statistic, "
    "claim, source or citation; never draw on outside knowledge; never turn a "
    "withheld or refused passage into an answer. Output only the reworded "
    "answer text."
)


class ProviderError(Exception):
    """Base class: any provider failure. Users never see these details."""


class ProviderTimeout(ProviderError):
    """The provider did not answer within the approved request timeout."""


class ProviderRateLimited(ProviderError):
    """The provider's rate limit or quota was hit."""


class ProviderInvalidResponse(ProviderError):
    """The provider's response was unusable (malformed, empty, wrong shape)."""


@dataclass(frozen=True)
class ExplanationPayload:
    """The complete, closed set of what a model may ever receive."""

    question: str
    verified_answer: str


class ExplanationProvider(Protocol):
    """Contract a provider adapter must satisfy once one is approved.

    Implementations MUST:
      - enforce an explicit request timeout (raising ProviderTimeout),
      - translate rate-limit/quota responses into ProviderRateLimited,
      - translate unusable responses into ProviderInvalidResponse,
      - fold credential/API-key failures into ProviderError,
      - never log question content, answers or credentials,
      - make no background or prefetch calls (explicit user requests only),
      - never widen the payload (the permitted input set is closed).
    """

    name: str

    def explain(self, payload: ExplanationPayload) -> str:
        """Return the reworded text, or raise a ProviderError subclass."""
        ...


def get_configured_provider() -> ExplanationProvider | None:
    """Return the active provider, or None while the feature stays disabled.

    No provider, model, API key or budget has been approved, so this returns
    None unconditionally. Once a provider has been explicitly approved and a
    minimal adapter is written, the contract here must stay: read credentials
    from the environment (never from code, never in logs), keep returning
    None whenever credentials are absent so the fully-working deterministic
    mode remains the default, and enable nothing without approval.
    """

    return None


def build_explanation_payload(
    question: str,
    verified_answer: str,
) -> ExplanationPayload:
    """Assemble the closed, smallest permitted payload; nothing else is sent."""

    return ExplanationPayload(question=str(question), verified_answer=str(verified_answer))


def _protected_tokens(answer_text: str) -> frozenset[str]:
    """Every token a wording must preserve, extracted from the whole answer.

    Numbers are captured as maximal digit runs (digits plus optional decimal
    point), so the denominator '5' in '3 of 5 respondents' can never be
    satisfied by the '5' inside '62.5%', and '13,994' is one figure. Each
    percentage is additionally captured whole-with-percent-sign so a wording
    like '62.5‰' or '62.5 percentage points' cannot silently replace '62.5%'.
    Indicator IDs (``FI-01``/``EI-03``), named governance citations and page
    citations are captured as-is. Interval endpoints (``40.0%``-``45.0%``)
    are protected individually through these runs.
    """

    # Grouped counts read as one figure ("13,994" -> "13994"); extracting from
    # the comma-normalised text keeps '56' from becoming a phantom standalone
    # token alongside '56000'.
    normalized = answer_text.replace(",", "")
    tokens: set[str] = set()
    tokens.update(re.findall(r"\b(?:FI|EI)-\d{2}\b", normalized))
    tokens.update(re.findall(
        r"\b(?:Official-poverty contract|Honesty statement|Disclosure boundary)\b",
        normalized,
    ))
    tokens.update(re.findall(r"\bPage \d{2}\b", normalized))
    tokens.update(re.findall(r"\b\d+(?:\.\d+)?%", normalized))
    tokens.update(re.findall(r"(?<!\d)(?<!\d\.)\d+(?:\.\d+)?(?!\d)(?!\.\d)", normalized))
    return frozenset(t for t in tokens if t)


def wording_preserves_evidence(verified_answer: str, wording: str) -> bool:
    """Fail-closed numeric and citation guard for a candidate wording.

    Every protected token from the deterministic answer must appear verbatim
    in the model wording (commas inside numbers are normalised — '13,994' and
    '13994' describe the same figure; nothing else is forgiven). Each needle
    must stand as its own number: '56' does not satisfy a wording that only
    contains '56000', and any unexplained drift fails closed.
    """

    if not isinstance(wording, str):
        return False
    wording = wording.strip()
    if not wording:
        return False
    if len(wording) > MAX_WORDING_CHARS:
        return False
    normalized_wording = wording.replace(",", "")
    for token in _protected_tokens(verified_answer):
        needle = token.replace(",", "")
        if not needle or not any(ch.isdigit() for ch in needle):
            continue
        pattern = r"(?<!\d)(?<!\d\.)" + re.escape(needle) + r"(?!\d)(?!\.\d)"
        if not re.search(pattern, normalized_wording):
            return False
    return True


def refine_answer(
    question: str,
    answer: AssistantAnswer,
    provider: ExplanationProvider | None,
) -> AssistantAnswer:
    """Offer the evidence-bearing answer to a model for wording only.

    The deterministic answer always wins: on no provider, any provider
    failure, any wording that alters protected evidence, and on uncertainty,
    the original answer — with its original references — is returned.
    """

    if provider is None:
        return answer
    # Refusals, fallbacks and anything without verified ground stay untouched
    # and never reach a model — injection-shaped or privacy-adjacent questions
    # cannot leverage this layer.
    if not answer.grounded or answer.question_kind not in _REWORDABLE_KINDS:
        return answer
    payload = build_explanation_payload(question, answer.answer)
    try:
        wording = provider.explain(payload)
    except ProviderError:
        # Missing credentials, timeouts, rate limits, malformed responses and
        # outages all fall back silently; provider errors are never shown.
        return answer
    except Exception:  # a provider broke its contract — fail closed
        return answer
    if not wording_preserves_evidence(answer.answer, wording):
        return answer
    return dataclasses.replace(answer, answer=wording)
