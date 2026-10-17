"""Generic indicator calculations with explicit denominator and weight rules.

These functions calculate only from caller-supplied masks and weights. They do
not infer variable meaning from names and do not establish publication or
representativeness. Results contain aggregate counts and metadata only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from insightrwanda.data.errors import IndicatorBlockedError, IndicatorDefinitionError


CALCULABLE_DEFINITION_STATUSES = {"officially_documented", "derived_from_verified_variables"}


def _validate_mask(name: str, series: pd.Series) -> None:
    if not isinstance(series, pd.Series):
        raise IndicatorDefinitionError(f"{name} must be a pandas Series of boolean values.")
    if not pd.api.types.is_bool_dtype(series):
        raise IndicatorDefinitionError(f"{name} must have boolean dtype; no implicit value recoding is applied.")


def _validate_alignment(left: pd.Series, right: pd.Series, right_name: str) -> None:
    if len(left) != len(right) or not left.index.equals(right.index):
        raise IndicatorDefinitionError(f"The numerator and {right_name} must have identical indexes and lengths.")


def _base_result(
    *,
    indicator_id: str,
    source_authorization_status: str,
    indicator_definition_status: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "indicator_id": indicator_id,
        "indicator_definition_status": indicator_definition_status,
        "source_authorization_status": source_authorization_status,
        "eligible_for_publication": False,
        "limitations": limitations,
    }


def calculate_proportion(
    numerator: pd.Series,
    denominator: pd.Series | None = None,
    *,
    indicator_id: str = "GENERIC-PROPORTION",
    source_authorization_status: str = "unverified",
    indicator_definition_status: str = "generic_calculation_only",
) -> dict[str, Any]:
    """Calculate an unweighted proportion from explicit boolean masks.

    ``True`` in ``denominator`` marks an eligible observation. Missing values
    in either mask are excluded. A zero denominator returns ``estimate=None``
    with an explicit status instead of falling back to another calculation.
    """

    _validate_mask("numerator", numerator)
    if denominator is not None:
        _validate_mask("denominator", denominator)
        _validate_alignment(numerator, denominator, "denominator")
        eligible = denominator.fillna(False) & numerator.notna()
    else:
        eligible = numerator.notna()
    numerator_true = numerator.fillna(False) & eligible
    denominator_count = int(eligible.sum())
    numerator_count = int(numerator_true.sum())
    excluded_count = int(len(numerator) - denominator_count)
    estimate = numerator_count / denominator_count if denominator_count else None
    result = _base_result(
        indicator_id=indicator_id,
        source_authorization_status=source_authorization_status,
        indicator_definition_status=indicator_definition_status,
        limitations=[
            "This generic calculation does not establish survey design validity or representativeness.",
            "No confidence interval or variance estimate is supplied.",
        ],
    )
    result.update(
        {
            "calculation_status": "calculated" if denominator_count else "zero_denominator",
            "weighted": False,
            "numerator_count": numerator_count,
            "denominator_count": denominator_count,
            "excluded_count": excluded_count,
            "estimate": estimate,
            "percentage": estimate * 100 if estimate is not None else None,
        }
    )
    return result


def validate_weights(weights: pd.Series) -> dict[str, Any]:
    """Return aggregate weight diagnostics without returning weight values."""

    if not isinstance(weights, pd.Series):
        raise IndicatorDefinitionError("weights must be a pandas Series.")
    numeric = pd.to_numeric(weights, errors="coerce")
    values = numeric.to_numpy(dtype="float64", na_value=np.nan)
    finite = np.isfinite(values)
    missing_count = int(weights.isna().sum())
    invalid_count = int((weights.notna() & numeric.isna()).sum())
    non_finite_count = int((~finite & ~np.isnan(values)).sum())
    negative_count = int((finite & (values < 0)).sum())
    zero_count = int((finite & (values == 0)).sum())
    positive_count = int((finite & (values > 0)).sum())
    return {
        "row_count": int(len(weights)),
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "non_finite_count": non_finite_count,
        "negative_count": negative_count,
        "zero_count": zero_count,
        "positive_count": positive_count,
        "has_usable_positive_weight": positive_count > 0 and invalid_count == 0 and non_finite_count == 0 and negative_count == 0,
        "limitations": [
            "Weight validity is a structural check; the correct survey weight still requires source documentation.",
            "This check does not establish strata, clusters, replicate weights, or variance-estimation suitability.",
        ],
    }


def calculate_weighted_proportion(
    numerator: pd.Series,
    weights: pd.Series,
    denominator: pd.Series | None = None,
    *,
    indicator_id: str = "GENERIC-WEIGHTED-PROPORTION",
    source_authorization_status: str = "unverified",
    indicator_definition_status: str = "generic_calculation_only",
) -> dict[str, Any]:
    """Calculate a weighted proportion without silently falling back to unweighted.

    Rows with missing, invalid, non-finite, or negative weights are excluded
    and counted. Zero weights remain valid but contribute zero. If the resulting
    weighted denominator is zero, the estimate is ``None``.
    """

    _validate_mask("numerator", numerator)
    if not isinstance(weights, pd.Series):
        raise IndicatorDefinitionError("weights must be a pandas Series.")
    _validate_alignment(numerator, weights, "weights")
    if denominator is not None:
        _validate_mask("denominator", denominator)
        _validate_alignment(numerator, denominator, "denominator")
    diagnostics = validate_weights(weights)
    numeric = pd.to_numeric(weights, errors="coerce")
    values = numeric.to_numpy(dtype="float64", na_value=np.nan)
    valid_weight = np.isfinite(values) & (values >= 0)
    valid = numerator.notna() & valid_weight
    if denominator is not None:
        valid = valid & denominator.fillna(False)
    denominator_weight = float(numeric[valid].sum())
    numerator_weight = float(numeric[valid & numerator.fillna(False)].sum())
    estimate = numerator_weight / denominator_weight if denominator_weight > 0 else None
    result = _base_result(
        indicator_id=indicator_id,
        source_authorization_status=source_authorization_status,
        indicator_definition_status=indicator_definition_status,
        limitations=[
            "The selected weight is not validated against a survey codebook by this function.",
            "No confidence interval or design-based variance estimate is supplied.",
            "Invalid weights are excluded; there is no unweighted fallback.",
        ],
    )
    result.update(
        {
            "calculation_status": "calculated" if denominator_weight > 0 else "zero_weight_denominator",
            "weighted": True,
            "numerator_count": int((valid & numerator.fillna(False)).sum()),
            "denominator_count": int(valid.sum()),
            "excluded_count": int(len(numerator) - valid.sum()),
            "weighted_numerator": numerator_weight,
            "weighted_denominator": denominator_weight,
            "estimate": estimate,
            "percentage": estimate * 100 if estimate is not None else None,
            "weight_diagnostics": diagnostics,
        }
    )
    return result


def assert_indicator_calculable(
    definition: dict[str, Any],
    available_columns: list[str] | tuple[str, ...] | set[str],
) -> None:
    """Reject proposed or unresolved definitions before any indicator result."""

    status = definition.get("evidence_status") or definition.get("status")
    required = definition.get("required_variables")
    if status not in CALCULABLE_DEFINITION_STATUSES:
        raise IndicatorBlockedError("This indicator is blocked until its definition and evidence are verified.")
    if not isinstance(required, list) or not required:
        raise IndicatorBlockedError("This indicator has no verified required-variable mapping.")
    missing = [column for column in required if column not in set(available_columns)]
    if missing:
        raise IndicatorBlockedError("The selected source lacks verified variables required by this indicator.")

