"""Phase 14: first verified indicator calculation boundary.

This module is deliberately conservative.  It evaluates the existing central
readiness service before touching observation values, accepts only explicit
boolean masks built from reviewed mappings, and returns aggregate metadata.
Blocked runs have no numeric result and cannot be persisted as calculation
result artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from insightrwanda.data.errors import DataPathError, IndicatorBlockedError, IndicatorDefinitionError
from insightrwanda.data.paths import resolve_derived_output_path
from insightrwanda.data.registry import get_dataset, resolve_dataset_path

from .indicators import calculate_weighted_proportion, validate_weights
from .readiness import ReadinessResult, evaluate_indicator_readiness
from .validation import contains_forbidden_raw_keys, validate_calculation_inputs, validate_result_integrity


CALCULATION_CODE_VERSION = "insightrwanda-phase14-v1"
SUPPORTED_METHODS = {"proportion", "weighted_proportion"}
BLOCKER_ACTIONS = {
    "dataset_registered": "Select an existing dataset ID from the validated registry.",
    "approved_registered_path": "Resolve the registered source only inside data/ and obtain the authorized release through the approved channel.",
    "release_match": "Match the local file, source record, and indicator definition to the same exact release identifier.",
    "permitted_use": "Record reviewed terms that explicitly permit this analytical purpose.",
    "questionnaire_and_codebook_review": "Obtain and independently review the exact-release questionnaire and codebook.",
    "documented_schema": "Record the exact codebook schema and validate the authorized input against it.",
    "eligibility_and_missingness_rules": "Document the target population, exclusions, valid responses, and all missing/refused/not-applicable rules.",
    "complete_definition_review": "Resolve every required indicator-definition review field for the exact target release.",
    "calculation_specification_approval": "Obtain approval for the indicator- and dataset-specific formula and calculation specification.",
    "central_analytical_eligibility": "Complete the central evidence review and record analytical eligibility.",
    "source_file_availability": "Place the authorized release at its registered path below data/ and refresh metadata.",
    "dataset_authorization": "Obtain written project-specific permission for analysis; catalogue visibility is not authorization.",
    "source_provenance": "Record verified provenance for the exact local source file.",
    "dataset_documentation": "Review and link the release-specific documentation in the dataset metadata.",
    "license_or_terms": "Record and review the applicable license or data-use terms.",
    "source_reference_review": "Review an authoritative source reference for the exact release.",
    "source_release_identity": "Match the local file identity to the documented source release.",
    "source_document_review": "Review the exact-release source documents and record the review.",
    "source_access_authorization": "Record source-matrix access authorization for this project.",
    "source_analysis_approval": "Record the separate dataset-specific analytical approval.",
    "calculation_specification": "Complete the numerator, denominator, missing-value, and calculation rules.",
    "data_quality_acceptance": "Run aggregate quality checks and record reviewer acceptance.",
    "verified_variable_mappings": "Independently verify every required variable against the exact-release codebook.",
    "mapping_evidence": "Provide a complete verified codebook-backed mapping for every required variable.",
    "definition_review": "Resolve every FI-ACCESS-001 definition-review field against the target release.",
    "approved_definition_and_methodology": "Obtain approved definition and methodology evidence.",
    "required_columns": "Validate that every required source variable is present in the approved input schema.",
    "value_semantics": "Verify response coding and missing-value semantics in the codebook.",
    "survey_weight_and_design": "Document the applicable weight, sampling design, and estimation guidance.",
    "weight_variable_and_interpretation": "Document the exact weight variable and its interpretation, then validate its presence.",
    "survey_design_supported": "Obtain approved survey-design guidance and support the approved point-estimation method.",
    "variance_estimation_supported": "Implement or approve a design-based variance method before requesting uncertainty intervals.",
    "publication_permission": "Keep publication permission as a separate disclosure and terms review.",
    "unregistered_dataset": "Register the selected dataset with its source identity and permitted-use metadata before calculation.",
    "input_schema": "Supply a validated tabular input with the documented exact-release schema.",
    "input_masks": "Create explicit boolean numerator and denominator masks from the verified mapping; do not infer coding.",
    "inconsistent_numerator_denominator": "Resolve numerator rows that fall outside the approved denominator.",
    "invalid_or_missing_weights": "Resolve invalid or missing weights for eligible observations; no unweighted fallback is allowed.",
    "duplicate_observations": "Review and resolve duplicate observations under the approved duplicate policy.",
    "zero_eligible_denominator": "Review eligibility and source data; no estimate exists when the eligible denominator is zero.",
    "zero_weight_denominator": "Review the approved weight and eligible population; no estimate exists when weighted denominator is zero.",
}


@dataclass(frozen=True)
class Phase14Outcome:
    """Serializable aggregate calculation decision/result."""

    status: str
    calculation_status: str
    indicator_id: str | None
    definition_version: str | None
    dataset_id: str | None
    dataset_release: str | None
    estimate: float | None
    percentage: float | None
    numerator_definition: str | None
    denominator_definition: str | None
    eligible_observation_count: int | None
    weighted_denominator: float | None
    standard_error: float | None
    confidence_interval: dict[str, float] | None
    missingness_summary: dict[str, int]
    quality_validation: dict[str, Any]
    limitations: tuple[str, ...]
    provenance: dict[str, Any]
    reproducibility: dict[str, Any]
    disclosure_status: str
    publication_status: str
    blocker_ids: tuple[str, ...] = ()
    blockers: tuple[dict[str, str], ...] = ()
    next_actions: tuple[str, ...] = ()
    readiness: dict[str, Any] | None = None
    result_artifact_written: bool = False
    raw_records_included: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "calculation_status": self.calculation_status,
            "analysis_eligible": bool(self.readiness and self.readiness.get("analysis_eligible")),
            "publication_eligible": bool(self.readiness and self.readiness.get("publication_eligible")),
            "eligible_for_requested_purpose": bool(self.readiness and self.readiness.get("eligible_for_requested_purpose")),
            "indicator_id": self.indicator_id,
            "definition_version": self.definition_version,
            "dataset_id": self.dataset_id,
            "dataset_release": self.dataset_release,
            "estimate": self.estimate,
            "percentage": self.percentage,
            "numerator_definition": self.numerator_definition,
            "denominator_definition": self.denominator_definition,
            "eligible_observation_count": self.eligible_observation_count,
            "weighted_denominator": self.weighted_denominator,
            "standard_error": self.standard_error,
            "confidence_interval": self.confidence_interval,
            "missingness_summary": dict(self.missingness_summary),
            "quality_validation": dict(self.quality_validation),
            "limitations": list(self.limitations),
            "provenance": dict(self.provenance),
            "reproducibility": dict(self.reproducibility),
            "disclosure_status": self.disclosure_status,
            "publication_status": self.publication_status,
            "blocker_ids": list(self.blocker_ids),
            "blockers": [dict(item) for item in self.blockers],
            "next_actions": list(self.next_actions),
            "readiness": self.readiness,
            "result": None,
            "result_artifact_written": self.result_artifact_written,
            "raw_records_included": self.raw_records_included,
        }


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_record(source_verification: dict[str, Any] | None, dataset_id: str | None) -> dict[str, Any] | None:
    if not isinstance(source_verification, dict) or not dataset_id:
        return None
    return next(
        (
            item
            for item in source_verification.get("sources", [])
            if isinstance(item, dict) and item.get("dataset_id") == dataset_id
        ),
        None,
    )


def _blocker_rows(readiness: ReadinessResult | None, extra: Iterable[tuple[str, str]] = ()) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    if readiness is not None:
        for identifier, message in zip(readiness.blocked_checks, readiness.messages):
            rows.append(
                {
                    "identifier": identifier,
                    "message": message,
                    "next_action": BLOCKER_ACTIONS.get(identifier, "Review the central readiness record and resolve this prerequisite."),
                }
            )
    rows.extend(
        {
            "identifier": identifier,
            "message": message,
            "next_action": BLOCKER_ACTIONS.get(identifier, "Review the calculation specification and source documentation."),
        }
        for identifier, message in extra
    )
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if row["identifier"] not in seen:
            unique.append(row)
            seen.add(row["identifier"])
    return tuple(unique)


def _base_outcome(
    *,
    definition: dict[str, Any] | None,
    dataset: dict[str, Any] | None,
    source: dict[str, Any] | None,
    readiness: ReadinessResult | None,
    blockers: tuple[dict[str, str], ...] = (),
    calculation_status: str = "blocked",
    quality_validation: dict[str, Any] | None = None,
    missingness_summary: dict[str, int] | None = None,
    readiness_override: dict[str, Any] | None = None,
) -> Phase14Outcome:
    blocker_ids = tuple(item["identifier"] for item in blockers)
    release = (dataset or {}).get("dataset_version") or (source or {}).get("release_version")
    return Phase14Outcome(
        status="blocked" if calculation_status != "calculated" else "calculated",
        calculation_status=calculation_status,
        indicator_id=(definition or {}).get("indicator_id"),
        definition_version=(definition or {}).get("definition_version"),
        dataset_id=(dataset or {}).get("dataset_id"),
        dataset_release=release,
        estimate=None,
        percentage=None,
        numerator_definition=(definition or {}).get("numerator_definition"),
        denominator_definition=(definition or {}).get("denominator_definition"),
        eligible_observation_count=None,
        weighted_denominator=None,
        standard_error=None,
        confidence_interval=None,
        missingness_summary=missingness_summary or {},
        quality_validation=quality_validation or {"status": "not_run"},
        limitations=tuple((definition or {}).get("interpretation_cautions") or ()),
        provenance={
            "dataset_id": (dataset or {}).get("dataset_id"),
            "dataset_release": release,
            "indicator_id": (definition or {}).get("indicator_id"),
            "definition_evidence_references": [
                item.get("evidence_reference")
                for item in (definition or {}).get("mapping_records", [])
                if isinstance(item, dict) and item.get("evidence_reference")
            ],
            "source_documentation_references": list((dataset or {}).get("documentation_references") or []),
            "calculated_at_utc": None,
        },
        reproducibility={"code_version": CALCULATION_CODE_VERSION},
        disclosure_status="not_reviewed",
        publication_status="not_approved",
        blocker_ids=blocker_ids,
        blockers=blockers,
        next_actions=tuple(dict.fromkeys(item["next_action"] for item in blockers)),
        readiness=readiness_override if readiness_override is not None else (readiness.as_dict() if readiness else None),
        result_artifact_written=False,
        raw_records_included=False,
    )


def evaluate_phase14_readiness(
    *,
    project_root: str | Path,
    definition: dict[str, Any] | None,
    dataset: dict[str, Any] | None,
    source_verification: dict[str, Any] | None,
    available_columns: Iterable[str] | None = None,
    schema_validated: bool = False,
    publication_requested: bool = False,
    requested_processing_purpose: str = "analysis",
) -> ReadinessResult:
    """Run the hard pre-calculation gate without inspecting observation values."""

    source = _source_record(source_verification, (dataset or {}).get("dataset_id"))
    path_approved = False
    source_available = False
    if isinstance(dataset, dict):
        try:
            path = resolve_dataset_path(dataset, project_root=project_root)
            path_approved = True
            source_available = path.is_file()
        except (DataPathError, OSError, ValueError):
            pass
    if not isinstance(definition, dict):
        definition = {}
    return evaluate_indicator_readiness(
        definition,
        dataset,
        available_columns=available_columns,
        publication_requested=publication_requested,
        require_research_evidence=True,
        require_data_quality=True,
        require_calculation_specification=True,
        require_mapping_evidence=True,
        source_verification=source,
        source_available=source_available,
        strict_calculation=True,
        calculation_specification=definition.get("calculation_specification"),
        survey_design=(dataset or {}).get("survey_design") if isinstance(dataset, dict) else None,
        requested_processing_purpose=requested_processing_purpose,
        source_path_approved=path_approved,
        schema_validated=schema_validated,
    )


def build_phase14_status(
    project_root: str | Path,
    registry: dict[str, dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    source_verification: dict[str, Any] | None,
    *,
    dataset_id: str = "finscope_2024_rwanda_csv",
    indicator_id: str = "FI-ACCESS-001",
) -> dict[str, Any]:
    """Build a metadata-only Phase 14 decision; never load source rows."""

    dataset = get_dataset(registry, dataset_id)
    definition = catalogue.get(indicator_id)
    source = _source_record(source_verification, dataset_id)
    if dataset is None:
        blockers = _blocker_rows(None, [("dataset_registered", "The requested dataset is not registered.")])
        return _base_outcome(definition=definition, dataset=None, source=source, readiness=None, blockers=blockers).as_dict()
    readiness = evaluate_phase14_readiness(
        project_root=project_root,
        definition=definition,
        dataset=dataset,
        source_verification=source_verification,
        available_columns=dataset.get("verified_schema_columns") if isinstance(dataset.get("verified_schema_columns"), list) else None,
        schema_validated=False,
    )
    blockers = _blocker_rows(readiness)
    outcome = _base_outcome(
        definition=definition,
        dataset=dataset,
        source=source,
        readiness=readiness,
        blockers=blockers,
    )
    return outcome.as_dict()


def _validate_masks_and_frame(
    frame: pd.DataFrame,
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    weights: pd.Series | None,
    required_columns: Iterable[str],
    duplicate_policy: str,
    weight_required: bool,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    quality: dict[str, Any] = {
        "status": "passed",
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "duplicate_row_count": int(frame.duplicated(keep=False).sum()),
        "required_columns_present": all(str(column) in frame.columns for column in required_columns),
    }
    missingness = {
        "numerator_missing": int(numerator.isna().sum()),
        "denominator_missing": int(denominator.isna().sum()),
        "weight_missing": int(weights.isna().sum()) if weights is not None else 0,
    }
    blockers: list[tuple[str, str]] = []
    if not quality["required_columns_present"]:
        blockers.append(("input_schema", "The validated input is missing one or more required variables."))
    if not isinstance(numerator, pd.Series) or not isinstance(denominator, pd.Series):
        blockers.append(("input_masks", "Numerator and denominator must be explicit pandas boolean Series."))
        return quality, blockers
    if not pd.api.types.is_bool_dtype(numerator) or not pd.api.types.is_bool_dtype(denominator):
        blockers.append(("input_masks", "Numerator and denominator must use boolean dtype; no value recoding is performed."))
    if not numerator.index.equals(denominator.index) or not numerator.index.equals(frame.index):
        blockers.append(("input_masks", "Input frame, numerator, and denominator indexes must align exactly."))
    if weights is not None and (not weights.index.equals(frame.index) or not weights.index.equals(denominator.index)):
        blockers.append(("invalid_or_missing_weights", "The supplied weight index does not align with the validated input."))
    if bool((numerator.fillna(False) & ~denominator.fillna(False)).any()):
        blockers.append(("inconsistent_numerator_denominator", "At least one numerator observation is outside the approved denominator."))
    if duplicate_policy == "reject" and quality["duplicate_row_count"]:
        blockers.append(("duplicate_observations", "Duplicate observations are present and the approved policy rejects them."))
    if weight_required:
        if weights is None:
            blockers.append(("invalid_or_missing_weights", "The approved weighted calculation requires a supplied weight Series."))
        else:
            diagnostics = validate_weights(weights)
            quality["weight_diagnostics"] = diagnostics
            eligible = denominator.fillna(False)
            # Use the same finite/non-negative rule as the calculation helper.
            values = pd.to_numeric(weights, errors="coerce").to_numpy(dtype="float64", na_value=float("nan"))
            import numpy as np

            bad = (~np.isfinite(values) | (values < 0)) & eligible.to_numpy(dtype=bool)
            if bool(bad.any()):
                blockers.append(("invalid_or_missing_weights", "Eligible observations contain missing, invalid, non-finite, or negative weights."))
    if blockers:
        quality["status"] = "failed"
    return quality, blockers


def calculate_verified_indicator(
    *,
    project_root: str | Path,
    definition: dict[str, Any],
    dataset: dict[str, Any],
    source_verification: dict[str, Any] | None,
    input_data: pd.DataFrame,
    numerator: pd.Series,
    denominator: pd.Series,
    weights: pd.Series | None = None,
    publication_requested: bool = False,
    allow_synthetic_test_data: bool = False,
) -> dict[str, Any]:
    """Calculate one approved indicator after the complete central preflight.

    The caller supplies masks created from the verified mapping.  This function
    never guesses source response codes or variable semantics.
    """

    if not isinstance(input_data, pd.DataFrame):
        blockers = _blocker_rows(None, [("input_schema", "The input must be a validated pandas DataFrame.")])
        return _base_outcome(definition=definition, dataset=dataset, source=_source_record(source_verification, dataset.get("dataset_id")), readiness=None, blockers=blockers).as_dict()
    # Only column metadata is passed to the evaluator.  Observation values are
    # not touched until the evaluator returns eligible.
    readiness = evaluate_phase14_readiness(
        project_root=project_root,
        definition=definition,
        dataset=dataset,
        source_verification=source_verification,
        available_columns=[str(column) for column in input_data.columns],
        schema_validated=True,
        publication_requested=publication_requested,
    )
    if not readiness.eligible_for_requested_purpose:
        publication_blockers = []
        if publication_requested:
            publication_blockers = [
                (identifier, "The requested output is not publication-eligible under the separate disclosure and permission gate.")
                for identifier in readiness.publication_blocked_checks
            ]
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=_blocker_rows(readiness, publication_blockers),
        ).as_dict()

    specification = definition.get("calculation_specification") or {}
    required_variables = definition.get("required_variables") or []
    method = specification.get("method")
    weight_required = method == "weighted_proportion"
    validation = validate_calculation_inputs(
        readiness_eligible=True,
        frame=input_data,
        numerator=numerator,
        denominator=denominator,
        weights=weights,
        required_columns=required_variables,
        method=method,
        duplicate_policy=str(specification.get("duplicate_policy", "reject")),
        missing_value_treatment=definition.get("missing_value_treatment"),
        rounding_digits=specification.get("rounding_digits"),
        confidence_interval_requested=bool(specification.get("confidence_interval_requested")),
        variance_supported=bool(
            (dataset.get("survey_design") or {}).get("variance_estimation_supported") is True
            and (dataset.get("survey_design") or {}).get("variance_method") in {"linearization", "replicate_weights", "taylor_linearization"}
        ),
    )
    quality = validation.as_dict()
    input_blockers = [
        (
            "zero_eligible_denominator" if check["check_id"] == "eligible_denominator"
            else "zero_weight_denominator" if check["check_id"] == "weight_denominator_consistency"
            else check["check_id"],
            check["explanation"],
        )
        for check in quality["checks"]
        if check["status"] in {"fail", "blocked"}
    ]
    missingness = {
        "numerator_missing": int(numerator.isna().sum()) if isinstance(numerator, pd.Series) else 0,
        "denominator_missing": int(denominator.isna().sum()) if isinstance(denominator, pd.Series) else 0,
        "weight_missing": int(weights.isna().sum()) if isinstance(weights, pd.Series) else 0,
    }
    if input_blockers:
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=_blocker_rows(None, input_blockers),
            quality_validation=quality,
            calculation_status=(
                "zero_eligible_denominator"
                if "zero_eligible_denominator" in {identifier for identifier, _ in input_blockers}
                else "zero_weight_denominator"
                if "zero_weight_denominator" in {identifier for identifier, _ in input_blockers}
                else "blocked"
            ),
            missingness_summary=missingness,
        ).as_dict()

    eligible = denominator.fillna(False)
    eligible_count = int(eligible.sum())
    if eligible_count == 0:
        blockers = _blocker_rows(None, [("zero_eligible_denominator", "The approved eligible denominator contains zero observations.")])
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=blockers,
            calculation_status="zero_eligible_denominator",
            quality_validation=quality,
            missingness_summary=missingness,
        ).as_dict()

    if method not in SUPPORTED_METHODS:
        blockers = _blocker_rows(None, [("calculation_specification_approval", "The approved calculation method is not supported by the Phase 14 implementation.")])
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=blockers,
            quality_validation=quality,
            missingness_summary=missingness,
        ).as_dict()

    if specification.get("confidence_interval_requested"):
        # No CI/SE implementation is claimed here.  Complex-survey inference
        # must not silently fall back to an SRS formula.
        blockers = _blocker_rows(None, [("variance_estimation_supported", "Confidence intervals were requested but no approved design-based variance implementation is available.")])
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=blockers,
            quality_validation=quality,
            missingness_summary=missingness,
        ).as_dict()

    try:
        if method == "weighted_proportion":
            calculation = calculate_weighted_proportion(
                numerator,
                weights,
                denominator,
                indicator_id=str(definition.get("indicator_id")),
                source_authorization_status="synthetic_test" if allow_synthetic_test_data else str(dataset.get("authorization_status")),
                indicator_definition_status=str(definition.get("status")),
            )
        else:
            from .indicators import calculate_proportion

            calculation = calculate_proportion(
                numerator,
                denominator,
                indicator_id=str(definition.get("indicator_id")),
                source_authorization_status="synthetic_test" if allow_synthetic_test_data else str(dataset.get("authorization_status")),
                indicator_definition_status=str(definition.get("status")),
            )
    except (IndicatorDefinitionError, TypeError, ValueError):
        blockers = _blocker_rows(None, [("input_masks", "The supplied masks or weights failed the approved calculation validation.")])
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=blockers,
            quality_validation=quality,
            missingness_summary=missingness,
        ).as_dict()
    if calculation.get("calculation_status") != "calculated":
        identifier = "zero_weight_denominator" if method == "weighted_proportion" else "zero_eligible_denominator"
        blockers = _blocker_rows(None, [(identifier, "The calculation produced no valid denominator; no estimate was created.")])
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=_source_record(source_verification, dataset.get("dataset_id")),
            readiness=readiness,
            blockers=blockers,
            calculation_status=calculation.get("calculation_status", "blocked"),
            quality_validation=quality,
            missingness_summary=missingness,
        ).as_dict()

    source = _source_record(source_verification, dataset.get("dataset_id"))
    release = dataset.get("dataset_version") or (source or {}).get("release_version")
    weighted_denominator = None
    if method == "weighted_proportion" and specification.get("weighted_denominator_allowed") is True:
        weighted_denominator = float(calculation.get("weighted_denominator"))
    result = {
        "status": "calculated",
        "calculation_status": "calculated",
        "indicator_id": definition.get("indicator_id"),
        "definition_version": definition.get("definition_version"),
        "dataset_id": dataset.get("dataset_id"),
        "dataset_release": release,
        "estimate": float(calculation.get("estimate")),
        "percentage": float(calculation.get("percentage")),
        "reported_estimate": round(float(calculation.get("estimate")), int(specification.get("rounding_digits"))),
        "reported_percentage": round(float(calculation.get("percentage")), int(specification.get("rounding_digits"))),
        "numerator_definition": definition.get("numerator_definition"),
        "denominator_definition": definition.get("denominator_definition"),
        "eligible_observation_count": int(calculation.get("denominator_count", 0)),
        "weighted_denominator": weighted_denominator,
        "standard_error": None,
        "confidence_interval": None,
        "missingness_summary": missingness,
        "quality_validation": quality,
        "limitations": list(dict.fromkeys([
            *list(definition.get("interpretation_cautions") or []),
            "No confidence interval or standard error is reported because the approved Phase 14 implementation has no design-based variance estimator.",
            "Publication and disclosure approval remain separate from analytical eligibility.",
        ])),
        "provenance": {
            "dataset_id": dataset.get("dataset_id"),
            "dataset_release": release,
            "indicator_id": definition.get("indicator_id"),
            "definition_evidence_references": [
                item.get("evidence_reference")
                for item in definition.get("mapping_records", [])
                if isinstance(item, dict) and item.get("evidence_reference")
            ],
            "definition_review_evidence_references": [
                item.get("evidence_reference")
                for item in (definition.get("definition_review", {}).get("fields", []) if isinstance(definition.get("definition_review"), dict) else [])
                if isinstance(item, dict) and item.get("evidence_reference")
            ],
            "mapping_evidence_references": [
                item.get("codebook_reference")
                for item in definition.get("mapping_records", [])
                if isinstance(item, dict) and item.get("codebook_reference")
            ],
            "calculation_specification_evidence_references": list(specification.get("evidence_references") or []),
            "input_file_sha256": dataset.get("integrity_sha256"),
            "calculated_at_utc": _now_utc(),
        },
        "reproducibility": {
            "code_version": CALCULATION_CODE_VERSION,
            "calculation_specification_version": specification.get("version"),
            "survey_design_method": (dataset.get("survey_design") or {}).get("sampling_design"),
            "variance_method": (dataset.get("survey_design") or {}).get("variance_method"),
            "uncertainty_status": "not_requested",
            "rounding_digits": specification.get("rounding_digits"),
        },
        "disclosure_status": "not_reviewed",
        "publication_status": "not_approved",
        "blocker_ids": [],
        "blockers": [],
        "next_actions": ["Complete separate disclosure and publication review before releasing this aggregate."],
        "readiness": readiness.as_dict(),
        "result_artifact_written": False,
        "raw_records_included": False,
        "data_classification": "synthetic_test_data" if allow_synthetic_test_data else "authorized_aggregate",
    }
    integrity = validate_result_integrity(result)
    result["validation"] = {
        "input_validation": validation.as_dict(),
        "result_integrity": integrity.as_dict(),
    }
    if not integrity.calculation_allowed:
        blockers = _blocker_rows(
            None,
            [
                (check["check_id"], check["explanation"])
                for check in integrity.as_dict()["checks"]
                if check["status"] in {"fail", "blocked"}
            ],
        )
        return _base_outcome(
            definition=definition,
            dataset=dataset,
            source=source,
            readiness=readiness,
            blockers=blockers,
            quality_validation=result["validation"],
            missingness_summary=missingness,
        ).as_dict()
    return result


def save_calculation_result(
    result: dict[str, Any],
    *,
    project_root: str | Path,
    output_path: str | Path = "artifacts/phase14_result.json",
) -> Path:
    """Persist only a successful aggregate result, never a blocked outcome."""

    if not isinstance(result, dict):
        raise IndicatorBlockedError("Only a structured aggregate result may be persisted.")
    if (
        result.get("data_classification") in {"synthetic_test_data", "synthetic_test_only"}
        or result.get("is_synthetic") is True
    ) and (Path(project_root).resolve() / "data" / "metadata" / "dataset_registry.json").is_file():
        raise IndicatorBlockedError("Synthetic test results cannot be persisted as research result artifacts.")
    if result.get("calculation_status") != "calculated" or result.get("raw_records_included"):
        raise IndicatorBlockedError("Only a successful aggregate result without raw records may be persisted.")
    integrity = validate_result_integrity(result)
    if not integrity.calculation_allowed:
        raise IndicatorBlockedError("The aggregate result is missing required provenance or contains unsafe fields.")
    output = resolve_derived_output_path(output_path, project_root=project_root)
    safe_result = dict(result)
    safe_result["result_artifact_written"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(safe_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def load_saved_calculation_result(project_root: str | Path, *, path: str | Path = "artifacts/phase14_result.json") -> dict[str, Any] | None:
    """Read a saved aggregate result only when its integrity is still valid."""

    try:
        result_path = resolve_derived_output_path(path, project_root=project_root)
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (DataPathError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(document, dict) or document.get("calculation_status") != "calculated":
        return None
    if contains_forbidden_raw_keys(document):
        return None
    if not validate_result_integrity(document).calculation_allowed:
        return None
    return document


# Descriptive public aliases for callers that refer to the phase objective.
calculate_first_verified_indicator = calculate_verified_indicator
build_first_verified_indicator_status = build_phase14_status

