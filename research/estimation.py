"""Estimation layer: interval estimates and the official-poverty unlock contract.

This module adds two honest capabilities the dashboard and tests can share:

1. Weighted nonparametric bootstrap interval estimates for indicators.
   Resampling is over the loaded households, keeping each row's supplied
   `hh_wt`. The interval captures resampling variability only. Without
   PSU/strata/variance documentation this is NOT a survey-design standard
   error, and every result says so.

2. Income-band context estimates built from the embedded Stata band labels
   (N11a_lbl / N12a_lbl). These are descriptive financial-context estimates.
   They are NOT poverty: no poverty line, welfare aggregate or equivalence
   scale exists in the workspace.

3. `official_poverty_status()`, the machine-checkable contract that lists
   exactly which inputs are still missing before an official poverty
   estimation can run. Povert-py inputs never guessed: they must be passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data_pipeline import INCOME_BAND_ANNUAL, INCOME_BAND_MONTHLY
from .indicators import IndicatorDefinition, indicator_value

BOOTSTRAP_NOTE = (
    "Interval from a weighted nonparametric bootstrap over the loaded records "
    "(resampling households with replacement). It is NOT a survey-design "
    "standard error: no PSU/strata/variance documentation was supplied."
)

MONTHLY_INCOME = "n11"
ANNUAL_INCOME = "n12"

CONTEXT_ESTIMATES: dict[str, IndicatorDefinition] = {
    "EI-01": IndicatorDefinition(
        "EI-01", "Low personal income band (monthly)",
        "Among respondents reporting a substantive monthly personal income band, the share in the two lowest bands "
        "combined (1,000 Rwf or less; 1,001-3,000 Rwf).",
        "Share of respondents with a substantive n11 band", "Respondents with n11 in 1..15 or 16",
        "n11 in 1..16 is substantive; 99 (Don't know/Refused) and missing values are excluded.",
        (MONTHLY_INCOME,),
        "Weighted mean of n11 in {1, 2} using hh_wt.",
        "Verified against the embedded N11a_lbl band labels; project-calculated, not a poverty rate.",
        ("Income is self-reported and band-coded; irregular/seasonal reporters are in the denominator, "
         "not the numerator.", "This is a financial-context statistic, not a poverty headcount."),
    ),
    "EI-02": IndicatorDefinition(
        "EI-02", "Irregular or seasonal income (monthly)",
        "Among respondents reporting a substantive monthly personal income band, the share reporting irregular/seasonal income (band 16).",
        "Share of respondents with a substantive n11 band", "Respondents with n11 in 1..16",
        "n11 in 1..16 is substantive; 99 and missing values are excluded.",
        (MONTHLY_INCOME,),
        "Weighted mean of n11 == 16 using hh_wt.",
        "Verified against the embedded N11a_lbl band labels; project-calculated.",
        ("Irregular income is common in agriculture; treat as structural, not purely a poverty signal.",
         "Band 16 carries zero responses in the supplied file; a 0.0% result is structural, not evidence of zero irregular income."),
    ),
    "EI-03": IndicatorDefinition(
        "EI-03", "Low annual income band",
        "Among respondents reporting a substantive annual total income band, the share in the two lowest bands combined "
        "(12,000 Rwf or less; 12,001-15,000 Rwf).",
        "Share of respondents with a substantive n12 band", "Respondents with n12 in 1..14",
        "n12 in 1..14 is substantive; 99 (Don't know/Refused) and missing values are excluded.",
        (ANNUAL_INCOME,),
        "Weighted mean of n12 in {1, 2} using hh_wt.",
        "Verified against the embedded N12a_lbl band labels; project-calculated, not a poverty rate.",
        ("Annual bands are self-reported; the denominator excludes don't-know/refusal responses.",),
    ),
}


@dataclass(frozen=True)
class IntervalEstimate:
    estimate: float
    low: float
    high: float
    n_boot: int
    seed: int
    note: str


@dataclass(frozen=True)
class OfficialPovertyStatus:
    ready: bool
    missing: tuple[str, ...]
    supplied: dict[str, str] = field(default_factory=dict)


def weighted_bootstrap_ci(
    frame: pd.DataFrame,
    indicator_id: str,
    n_boot: int = 400,
    seed: int = 42,
    confidence: float = 0.95,
) -> IntervalEstimate:
    """Weighted bootstrap interval for an indicator estimate.

    Resamples the loaded records with replacement (households travel with
    their supplied `hh_wt`), recomputes the exact indicator estimator in each
    replicate and returns the percentile interval. Deterministic per (seed,
    n_boot). Raises for unknown indicators or missing required columns.
    """

    values = indicator_value(frame, indicator_id).to_numpy(dtype=float)
    weights = frame["hh_wt"]
    valid = (~np.isnan(values)) & weights.notna().to_numpy() & (weights > 0).to_numpy() & np.isfinite(weights).to_numpy()
    clean_values = values[valid]
    clean_weights = weights[valid].to_numpy(dtype=float)
    if clean_values.size == 0:
        return IntervalEstimate(float("nan"), float("nan"), float("nan"), 0, seed, BOOTSTRAP_NOTE)

    rng = np.random.default_rng(seed)
    estimates = np.empty(n_boot, dtype=float)
    n = clean_values.size
    weight_sum = clean_weights.sum()
    for replicate in range(n_boot):
        picks = rng.integers(0, n, size=n)
        estimates[replicate] = np.average(
            clean_values[picks], weights=clean_weights[picks] * n / weight_sum
        )
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(estimates, [alpha, 1.0 - alpha])
    return IntervalEstimate(
        estimate=float(np.average(clean_values, weights=clean_weights)),
        low=float(lower),
        high=float(upper),
        n_boot=n_boot,
        seed=seed,
        note=BOOTSTRAP_NOTE,
    )


def indicator_value_for(frame: pd.DataFrame, definition: IndicatorDefinition) -> pd.Series:
    """Build the 0/1/NaN series used by a CONTEXT_ESTIMATE definition."""

    column = definition.source_variables[0]
    allowed = set(range(1, 17)) if column == MONTHLY_INCOME else set(range(1, 15))
    values = frame[column].where(frame[column].isin(allowed))
    if definition.indicator_id == "EI-01":
        return values.isin([1, 2]).astype(float).mask(values.isna())
    if definition.indicator_id == "EI-02":
        return values.eq(16).astype(float).mask(values.isna())
    if definition.indicator_id == "EI-03":
        return values.isin([1, 2]).astype(float).mask(values.isna())
    raise KeyError(f"Unknown context estimate: {definition.indicator_id}")


def calculate_context_estimate(frame: pd.DataFrame, estimate_id: str) -> dict[str, object]:
    """Weighted point estimate + visible denominator for an EI estimate."""

    definition = CONTEXT_ESTIMATES[estimate_id]
    required = set(definition.source_variables) | {"hh_wt"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Context estimate {estimate_id} is missing columns: {', '.join(missing)}")
    values = indicator_value_for(frame, definition)
    weights = frame["hh_wt"]
    valid = values.notna() & weights.notna() & weights.gt(0) & np.isfinite(weights)
    total = weights[valid].sum()
    if not valid.any():
        return {
            "definition": definition, "estimate": float("nan"), "weight_sum": 0.0,
            "weight_populations": {band: 0.0 for band in ["low bands", "substantive total"]},
        }
    weights = weights[valid].astype(float)
    clean = values[valid].astype(float)
    numerator_w = (weights * clean).sum()
    return {
        "definition": definition,
        "estimate": float(numerator_w / total),
        "weight_sum": float(total),
        "numerator_weight": float(numerator_w),
    }


def context_weight_distribution(frame: pd.DataFrame, column: str) -> pd.Series:
    """Weighted band distribution for display, keeping every band's weight visible."""

    allowed = set(range(1, 17)) if column == MONTHLY_INCOME else set(range(1, 15))
    values = frame[column].where(frame[column].isin(allowed))
    weights = frame["hh_wt"]
    valid = values.notna() & weights.notna() & weights.gt(0) & np.isfinite(weights)
    if not valid.any():
        return pd.Series(dtype=float)
    grouped = weights[valid].groupby(values[valid]).sum()
    labels = INCOME_BAND_MONTHLY if column == MONTHLY_INCOME else INCOME_BAND_ANNUAL
    return grouped.rename(index=labels)


def official_poverty_status(
    poverty_line_rwf: float | None = None,
    poverty_concept: str | None = None,
    welfare_aggregate: pd.Series | None = None,
    variance_documentation: str | None = None,
    authorization: str | None = None,
    publication_approval: str | None = None,
) -> OfficialPovertyStatus:
    """Code-enforced contract for running an official poverty estimation.

    Returns the exact list of missing inputs. Nothing is inferred, defaulted
    or guessed: an official estimate runs only when every required input is
    explicitly provided here by a data steward.
    """

    supplied: dict[str, str] = {}
    missing: list[str] = []
    if poverty_line_rwf is None:
        missing.append("Documented poverty line (Rwf, per adult equivalent)")
    else:
        supplied["poverty_line_rwf"] = f"{poverty_line_rwf:,.0f}"
    if not poverty_concept:
        missing.append("Documented poverty concept (national or international definition)")
    else:
        supplied["poverty_concept"] = poverty_concept
    if welfare_aggregate is None:
        missing.append("Verified household welfare aggregate series")
    else:
        supplied["welfare_aggregate"] = f"supplied ({len(welfare_aggregate)} records)"
    if not variance_documentation:
        missing.append("Survey variance documentation (strata/PSU/variance method)")
    else:
        supplied["variance_documentation"] = variance_documentation
    if not authorization:
        missing.append("Authorization record from a data steward")
    else:
        supplied["authorization"] = authorization
    if not publication_approval:
        missing.append("Publication approval for public release")
    else:
        supplied["publication_approval"] = publication_approval
    return OfficialPovertyStatus(ready=not missing, missing=tuple(missing), supplied=supplied)
