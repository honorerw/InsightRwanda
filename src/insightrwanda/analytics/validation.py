"""Statistical validation and result-integrity checks for Phase 14.

This module validates inputs and aggregate metadata; it does not calculate an
indicator or grant analytical/publication eligibility.  It deliberately keeps
raw records out of all returned structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .indicators import validate_weights


CHECK_STATUSES = {"pass", "fail", "blocked", "not_applicable", "not_run"}
RAW_KEYS = {
    "records",
    "rows",
    "raw_records",
    "source_records",
    "input_data",
    "dataframe",
    "joined",
    "geometry",
    "coordinates",
    "household_id",
    "person_id",
    "respondent_id",
}


def contains_forbidden_raw_keys(value: Any) -> bool:
    """Return whether an aggregate artifact contains row-level payloads."""

    if isinstance(value, dict):
        if RAW_KEYS.intersection(value):
            return True
        return any(contains_forbidden_raw_keys(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_forbidden_raw_keys(item) for item in value)
    return False


@dataclass(frozen=True)
class ValidationCheck:
    """One stable, display-safe validation outcome."""

    check_id: str
    description: str
    status: str
    evidence_or_input_required: str
    explanation: str
    prevents_analytical_eligibility: bool
    corrective_action: str

    def __post_init__(self) -> None:
        if self.status not in CHECK_STATUSES:
            raise ValueError(f"Unsupported validation status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "status": self.status,
            "evidence_or_input_required": self.evidence_or_input_required,
            "explanation": self.explanation,
            "prevents_analytical_eligibility": self.prevents_analytical_eligibility,
            "corrective_action": self.corrective_action,
        }


@dataclass(frozen=True)
class ValidationReport:
    """Aggregate QA report that cannot override central readiness."""

    status: str
    calculation_allowed: bool
    checks: tuple[ValidationCheck, ...]
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "calculation_allowed": self.calculation_allowed,
            "checks": [check.as_dict() for check in self.checks],
            "summary": dict(self.summary),
        }


def _check(
    check_id: str,
    description: str,
    status: str,
    evidence_or_input_required: str,
    explanation: str,
    prevents_analytical_eligibility: bool,
    corrective_action: str,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        description=description,
        status=status,
        evidence_or_input_required=evidence_or_input_required,
        explanation=explanation,
        prevents_analytical_eligibility=prevents_analytical_eligibility,
        corrective_action=corrective_action,
    )


def _report(checks: Iterable[ValidationCheck], *, calculation_allowed: bool) -> ValidationReport:
    items = tuple(checks)
    statuses = {status: sum(item.status == status for item in items) for status in CHECK_STATUSES}
    if any(item.status == "blocked" for item in items):
        status = "blocked"
    elif any(item.status == "fail" for item in items):
        status = "fail"
    elif not items or all(item.status == "not_run" for item in items):
        status = "not_run"
    else:
        status = "pass"
    return ValidationReport(
        status=status,
        calculation_allowed=calculation_allowed and status == "pass",
        checks=items,
        summary={"check_count": len(items), "status_counts": statuses},
    )


def _not_run_checks() -> tuple[ValidationCheck, ...]:
    return (
        _check(
            "input_schema",
            "Required columns and documented schema",
            "not_run",
            "An analytically eligible validated input frame",
            "Input validation did not run because central analytical readiness is false.",
            True,
            "Resolve the central readiness blockers before supplying observations.",
        ),
        _check(
            "calculation_inputs",
            "Masks, exclusions, missingness, duplicates, and weights",
            "not_run",
            "An analytically eligible validated input frame and approved specification",
            "Input quality checks did not run because central analytical readiness is false.",
            True,
            "Resolve the central readiness blockers before running quality checks.",
        ),
    )


def validate_calculation_inputs(
    *,
    readiness_eligible: bool,
    frame: pd.DataFrame | None,
    numerator: pd.Series | None,
    denominator: pd.Series | None,
    weights: pd.Series | None,
    required_columns: Iterable[str],
    method: str | None,
    duplicate_policy: str,
    missing_value_treatment: str | None,
    rounding_digits: int | None,
    confidence_interval_requested: bool = False,
    variance_supported: bool = False,
) -> ValidationReport:
    """Validate one input set without calculating a production estimate.

    ``readiness_eligible`` is supplied by the central evaluator.  A false
    value blocks this report and leaves observation-level checks unperformed.
    """

    if not readiness_eligible:
        return _report(
            (
                _check(
                    "central_readiness",
                    "Central analytical eligibility",
                    "blocked",
                    "The central readiness evaluator",
                    "The selected dataset or indicator is not analytically eligible.",
                    True,
                    "Resolve the central readiness blockers; this QA layer cannot override them.",
                ),
                *_not_run_checks(),
            ),
            calculation_allowed=False,
        )

    checks: list[ValidationCheck] = []
    if not isinstance(frame, pd.DataFrame):
        checks.append(_check("input_schema", "Required columns and documented schema", "fail", "A pandas DataFrame", "The input is not a supported tabular frame.", True, "Supply the validated tabular input."))
        return _report(checks, calculation_allowed=False)

    required = [str(column) for column in required_columns]
    columns_present = all(column in {str(item) for item in frame.columns} for column in required)
    checks.append(
        _check(
            "input_schema",
            "Required columns and documented schema",
            "pass" if columns_present else "fail",
            ", ".join(required) or "The documented schema",
            "All required columns are present." if columns_present else "One or more required columns are absent.",
            not columns_present,
            "Match the input schema to the reviewed codebook and calculation specification.",
        )
    )

    if not isinstance(numerator, pd.Series) or not isinstance(denominator, pd.Series):
        checks.append(_check("input_masks", "Boolean numerator and denominator masks", "fail", "Boolean pandas Series aligned to the input frame", "Numerator and denominator are not pandas Series.", True, "Construct explicit boolean masks from verified response coding."))
        return _report(checks, calculation_allowed=False)
    aligned = numerator.index.equals(denominator.index) and numerator.index.equals(frame.index)
    boolean = pd.api.types.is_bool_dtype(numerator) and pd.api.types.is_bool_dtype(denominator)
    checks.append(_check("input_masks", "Boolean numerator and denominator masks", "pass" if aligned and boolean else "fail", "Boolean pandas Series aligned to the input frame", "Masks are boolean and index-aligned." if aligned and boolean else "Masks are not boolean or are not index-aligned.", True, "Construct explicit boolean masks with the input index."))

    if not boolean or not aligned:
        return _report(checks, calculation_allowed=False)

    numerator_true_outside = bool((numerator.fillna(False) & ~denominator.fillna(False)).any())
    checks.append(_check("inconsistent_numerator_denominator", "Numerator is contained by denominator", "fail" if numerator_true_outside else "pass", "Explicit numerator and denominator masks", "Numerator observations occur outside the denominator." if numerator_true_outside else "Every affirmative numerator observation is eligible for the denominator.", True, "Resolve numerator and denominator eligibility boundaries."))

    duplicate_count = int(frame.duplicated(keep=False).sum())
    duplicate_fail = duplicate_policy == "reject" and duplicate_count > 0
    duplicate_status = "fail" if duplicate_fail else "pass"
    checks.append(_check("duplicate_observations", "Duplicate handling", duplicate_status, "Approved duplicate policy", f"Duplicate row count is {duplicate_count}; policy is '{duplicate_policy}'.", duplicate_fail, "Resolve duplicates or obtain an approved duplicate policy."))

    missing_count = int(numerator.isna().sum() + denominator.isna().sum())
    missing_documented = isinstance(missing_value_treatment, str) and bool(missing_value_treatment.strip())
    checks.append(_check("missing_response_handling", "Missing, refused, and not-applicable response treatment", "pass" if missing_documented else "blocked", "Documented missing-value treatment", f"{missing_count} mask values are missing and the treatment is documented." if missing_documented else "Missing-value treatment is not documented.", not missing_documented, "Document each missing, refused, and not-applicable response rule."))

    if method == "weighted_proportion":
        if weights is None or not weights.index.equals(frame.index):
            checks.append(_check("invalid_or_missing_weights", "Weight validity", "fail", "An aligned numeric weight Series", "The weighted method has no aligned weight input.", True, "Supply the documented weight variable aligned to the input."))
        else:
            diagnostics = validate_weights(weights)
            values = pd.to_numeric(weights, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
            eligible = denominator.fillna(False).to_numpy(dtype=bool)
            eligible_bad = (~np.isfinite(values) | (values < 0)) & eligible
            weight_fail = bool(eligible_bad.any())
            checks.append(_check("invalid_or_missing_weights", "Weight validity", "fail" if weight_fail else "pass", "Documented non-negative finite weights for eligible observations", "Eligible weights are finite and non-negative." if not weight_fail else "Eligible observations contain missing, non-finite, invalid, or negative weights.", True, "Resolve eligible weight values; no unweighted fallback is permitted."))
            checks.append(_check("weight_diagnostics", "Aggregate weight diagnostics", "pass", "Weight diagnostics without raw values", f"Positive={diagnostics['positive_count']}, zero={diagnostics['zero_count']}, missing={diagnostics['missing_count']}, invalid={diagnostics['invalid_count']}.", False, "Review weight diagnostics against the exact-release documentation."))
            finite_status = "fail" if bool((~np.isfinite(values) & eligible).any()) else "pass"
            checks.append(_check("non_finite_values", "Non-finite numeric values", finite_status, "Finite numeric weights for eligible observations", "No non-finite eligible weights were found." if finite_status == "pass" else "At least one eligible weight is NaN or infinite.", finite_status == "fail", "Resolve non-finite eligible weights before calculation."))
            weighted_denominator = float(values[eligible & np.isfinite(values) & (values >= 0)].sum())
            checks.append(_check("weight_denominator_consistency", "Weighted denominator consistency", "fail" if weighted_denominator <= 0 and denominator.fillna(False).any() else "pass", "A positive weighted denominator for eligible observations", f"The aggregate eligible weight sum is {weighted_denominator}.", weighted_denominator <= 0 and denominator.fillna(False).any(), "Review the approved weight and eligible population; no weighted estimate exists for a zero weighted denominator."))
    else:
        checks.append(_check("invalid_or_missing_weights", "Weight validity", "not_applicable", "An approved weighted calculation method", "Weights are not used by the approved unweighted method.", False, "No action required unless the approved method changes."))

    denominator_count = int(denominator.fillna(False).sum())
    checks.append(_check("eligible_denominator", "Eligible denominator", "fail" if denominator_count == 0 else "pass", "An explicit denominator mask", f"Eligible denominator count is {denominator_count}.", denominator_count == 0, "Review eligibility and missingness; no estimate exists for a zero denominator."))

    if method != "weighted_proportion":
        checks.append(_check("non_finite_values", "Non-finite numeric values", "not_applicable", "Numeric input values used by the approved method", "Non-finite weights are not applicable to the approved unweighted method.", False, "Review non-finite values if the approved method uses numeric inputs."))

    if isinstance(rounding_digits, bool) or not isinstance(rounding_digits, int) or rounding_digits < 0:
        checks.append(_check("precision_and_rounding", "Precision and rounding metadata", "fail", "A non-negative integer rounding specification", "The rounding specification is invalid.", True, "Record an approved non-negative integer rounding rule."))
    else:
        checks.append(_check("precision_and_rounding", "Precision and rounding metadata", "pass", "An approved rounding specification", f"Results may be reported using {rounding_digits} decimal places.", False, "No action required."))

    if confidence_interval_requested:
        checks.append(_check("variance_method_support", "Design-based variance method", "pass" if variance_supported else "blocked", "Approved design-based variance method and required inputs", "The requested uncertainty method is supported." if variance_supported else "Confidence intervals or standard errors were requested without supported design-based variance estimation.", not variance_supported, "Implement or approve the documented complex-survey variance method before reporting uncertainty."))
    else:
        checks.append(_check("variance_method_support", "Design-based variance method", "not_applicable", "A specification requesting uncertainty", "Uncertainty was not requested; no standard error or confidence interval is calculated.", False, "No action required."))

    failed = any(item.status in {"fail", "blocked"} for item in checks)
    return _report(checks, calculation_allowed=not failed)


def validate_result_integrity(result: dict[str, Any]) -> ValidationReport:
    """Check the aggregate result schema and provenance without raw records."""

    if not isinstance(result, dict):
        return _report((_check("result_integrity", "Aggregate result integrity", "fail", "An aggregate result mapping", "The result is not a mapping.", True, "Return only the structured aggregate result."),), calculation_allowed=False)
    forbidden = contains_forbidden_raw_keys(result) or result.get("raw_records_included") is True
    required = {
        "dataset_id": result.get("dataset_id"),
        "dataset_release": result.get("dataset_release"),
        "indicator_id": result.get("indicator_id"),
        "definition_version": result.get("definition_version"),
        "readiness": result.get("readiness"),
        "provenance": result.get("provenance"),
        "reproducibility": result.get("reproducibility"),
        "quality_validation": result.get("quality_validation"),
        "limitations": result.get("limitations"),
        "disclosure_status": result.get("disclosure_status"),
        "publication_status": result.get("publication_status"),
    }
    missing = [field for field, value in required.items() if value in (None, "", [])]
    provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    reproducibility = result.get("reproducibility") if isinstance(result.get("reproducibility"), dict) else {}
    provenance_fields = {
        "mapping_evidence_references": provenance.get("mapping_evidence_references"),
        "calculation_specification_evidence_references": provenance.get("calculation_specification_evidence_references"),
        "input_file_sha256": provenance.get("input_file_sha256"),
        "calculated_at_utc": provenance.get("calculated_at_utc"),
    }
    missing.extend(field for field, value in provenance_fields.items() if value in (None, "", []))
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    if readiness.get("analysis_eligible") is not True:
        missing.append("central_analytical_eligibility")
    missing.extend(
        field
        for field in (
            "code_version",
            "calculation_specification_version",
            "survey_design_method",
            "variance_method",
            "uncertainty_status",
        )
        if not reproducibility.get(field)
    )
    if forbidden or missing:
        explanation = "Raw-record or row-level fields are present." if forbidden else "Required aggregate provenance fields are missing: " + ", ".join(missing)
        return _report((_check("result_integrity", "Aggregate result integrity", "fail", "Aggregate-only result with complete provenance", explanation, True, "Remove raw fields and populate the required stable provenance metadata."),), calculation_allowed=False)
    return _report((_check("result_integrity", "Aggregate result integrity", "pass", "Aggregate-only result with complete provenance", "The result contains required provenance and no raw-record fields.", False, "No action required."),), calculation_allowed=True)

