"""Central, evidence-based readiness checks for indicator use.

This service evaluates metadata only.  A successful check does not itself
approve an indicator; explicit catalogue and governance evidence must be
recorded before the service can return analytical eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .indicators import CALCULABLE_DEFINITION_STATUSES
from .mappings import validate_mapping_records


VERIFIED_MAPPING_STATUSES = {"verified_codebook_mapping", "officially_documented"}
AUTHORIZED_ANALYSIS_STATUSES = {"authorized_for_analysis", "authorized_for_analysis_and_publication"}
AUTHORIZED_PUBLICATION_STATUSES = {"authorized_for_analysis_and_publication"}
VERIFIED_STATUSES = {"verified", "approved", "documented"}


@dataclass(frozen=True)
class ReadinessResult:
    """Safe, deterministic result of the readiness evaluation."""

    status: str
    analysis_eligible: bool
    publication_eligible: bool
    eligible_for_requested_purpose: bool
    passed_checks: tuple[str, ...]
    blocked_checks: tuple[str, ...]
    publication_blocked_checks: tuple[str, ...]
    messages: tuple[str, ...]
    evidence_references: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "analysis_eligible": self.analysis_eligible,
            "publication_eligible": self.publication_eligible,
            "eligible_for_requested_purpose": self.eligible_for_requested_purpose,
            "passed_checks": list(self.passed_checks),
            "blocked_checks": list(self.blocked_checks),
            "publication_blocked_checks": list(self.publication_blocked_checks),
            "messages": list(self.messages),
            "evidence_references": list(self.evidence_references),
        }


def _add_blocked(blocked: list[str], messages: list[str], check: str, message: str) -> None:
    blocked.append(check)
    messages.append(message)


def _safe_references(definition: dict[str, Any], dataset: dict[str, Any] | None) -> tuple[str, ...]:
    references: list[str] = []
    for source in (definition.get("source_documentation", []), (dataset or {}).get("documentation_references", [])):
        if not isinstance(source, list):
            continue
        for item in source:
            if isinstance(item, str) and not item.startswith(("/", "~")):
                references.append(item)
            elif isinstance(item, dict) and isinstance(item.get("path"), str):
                path = item["path"]
                if not path.startswith(("/", "~")):
                    references.append(path)
    return tuple(dict.fromkeys(references))


def evaluate_indicator_readiness(
    definition: dict[str, Any],
    dataset: dict[str, Any] | None = None,
    *,
    available_columns: Iterable[str] | None = None,
    requested_geography: bool = False,
    publication_requested: bool = False,
    require_research_evidence: bool = False,
    require_data_quality: bool = False,
    require_calculation_specification: bool = False,
    require_mapping_evidence: bool = False,
    source_verification: dict[str, Any] | None = None,
    source_available: bool | None = None,
    allow_synthetic_test_data: bool = False,
    strict_calculation: bool = False,
    calculation_specification: dict[str, Any] | None = None,
    survey_design: dict[str, Any] | None = None,
    requested_processing_purpose: str = "analysis",
    source_path_approved: bool = False,
    schema_validated: bool = False,
    geographic_resource_status: str | None = None,
    geographic_resource_publication_status: str | None = None,
) -> ReadinessResult:
    """Evaluate analytical and publication readiness using explicit evidence.

    ``dataset=None`` means no dataset has been explicitly selected.  It never
    means "use the first dataset" and cannot satisfy an authorization check.
    """

    passed: list[str] = []
    blocked: list[str] = []
    publication_blocked: list[str] = []
    messages: list[str] = []
    columns = {str(column) for column in (available_columns or ())}

    authorization = (dataset or {}).get("authorization_status", "unverified")
    # A registry flag alone must never turn a real source into an authorized
    # synthetic dataset. Test callers must opt into this bypass explicitly.
    is_synthetic = allow_synthetic_test_data and (dataset or {}).get("is_synthetic") is True
    dataset_analytical_eligibility = (dataset or {}).get("analytical_eligibility") is True
    source_metadata = (
        source_verification
        if isinstance(source_verification, dict)
        and source_verification.get("dataset_id") == (dataset or {}).get("dataset_id")
        else {}
    )
    if (authorization in AUTHORIZED_ANALYSIS_STATUSES and dataset_analytical_eligibility) or (
        is_synthetic and authorization == "synthetic_test"
    ):
        passed.append("dataset_authorization")
    else:
        _add_blocked(
            blocked,
            messages,
            "dataset_authorization",
            "The selected dataset is not authorized for the requested analytical purpose.",
        )

    if require_research_evidence:
        governance_checks = (
            (
                "source_provenance",
                (dataset or {}).get("provenance_status") == "verified",
                "Documented source provenance is required before analytical loading.",
            ),
            (
                "dataset_documentation",
                (dataset or {}).get("documentation_status") in VERIFIED_STATUSES,
                "Reviewed dataset documentation is required before analytical loading.",
            ),
            (
                "license_or_terms",
                (dataset or {}).get("license_status") in VERIFIED_STATUSES,
                "Applicable license or data-use terms are required before analytical loading.",
            ),
        )
        for check, passed_check, message in governance_checks:
            if passed_check:
                passed.append(check)
            else:
                _add_blocked(blocked, messages, check, message)
        if not is_synthetic:
            source_checks = {
                "source_reference_review": ("source_reference_status", "verified", "An official source reference must be reviewed and release-matched."),
                "source_release_identity": ("source_information_status", "verified", "The source file must be matched to its exact official release."),
                "source_document_review": ("documentation_review_status", "verified", "Exact-release documentation must be obtained and reviewed."),
                "source_access_authorization": ("access_authorization_status", "verified", "Source-matrix access authorization is required; public discoverability is not permission."),
                "source_analysis_approval": ("analysis_approval_status", "verified", "A separate dataset-specific analysis approval is required."),
            }
            source_record = source_metadata
            for check, (field, required_status, message) in source_checks.items():
                if (dataset or {}).get("dataset_id") and source_record.get("dataset_id") == (dataset or {}).get("dataset_id") and source_record.get(field) == required_status:
                    passed.append(check)
                else:
                    _add_blocked(blocked, messages, check, message)
            if source_available is True:
                passed.append("source_file_availability")
            else:
                _add_blocked(
                    blocked,
                    messages,
                    "source_file_availability",
                    "The registered source file is missing or has not been safely confirmed inside the approved data directory.",
                )

    if require_calculation_specification:
        specification_fields = (
            "numerator_definition",
            "denominator_definition",
            "missing_value_treatment",
            "calculation_method",
        )
        if all(definition.get(field) not in (None, "", []) for field in specification_fields):
            passed.append("calculation_specification")
        else:
            _add_blocked(
                blocked,
                messages,
                "calculation_specification",
                "Approved numerator, denominator, missing-value, and calculation rules are required.",
            )

    if require_data_quality:
        quality_status = (dataset or {}).get("data_quality_status")
        if quality_status in {"verified", "approved", "passed"}:
            passed.append("data_quality_acceptance")
        else:
            _add_blocked(
                blocked,
                messages,
                "data_quality_acceptance",
                "Indicator-specific data-quality acceptance evidence is required before calculation.",
            )

    required = definition.get("required_variables")
    required_columns = [str(column) for column in required] if isinstance(required, list) else []
    legacy_mapping_verified = (
        definition.get("evidence_status") in VERIFIED_MAPPING_STATUSES
        and (dataset or {}).get("codebook_status") in VERIFIED_STATUSES
    )
    mapping_records = definition.get("mapping_records")
    mapping_record_verified = False
    if isinstance(mapping_records, list) and mapping_records:
        record_dataset_ids = {
            item.get("source_dataset_id")
            for item in mapping_records
            if isinstance(item, dict) and isinstance(item.get("source_dataset_id"), str)
        }
        try:
            documented_codebook_references = set()
            for reference in definition.get("source_documentation", []) or []:
                if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                    documented_codebook_references.add(reference["path"].split("#", 1)[0])
                elif isinstance(reference, str) and reference.strip():
                    documented_codebook_references.add(reference.split("#", 1)[0])
            for reference in (dataset or {}).get("documentation_references", []) or []:
                if isinstance(reference, str) and reference.strip():
                    documented_codebook_references.add(reference.split("#", 1)[0])
            validated_records = validate_mapping_records(
                mapping_records,
                indicator_id=str(definition.get("indicator_id", "UNNAMED")),
                dataset_ids=record_dataset_ids,
                codebook_references=documented_codebook_references,
            )
            mapped_variables = {
                record.get("source_variable")
                for record in validated_records
                if record.get("source_dataset_id") == (dataset or {}).get("dataset_id")
                and record.get("status") == "verified"
            }
            mapping_record_verified = bool(required_columns) and set(required_columns).issubset(mapped_variables)
        except Exception:
            # Invalid mapping metadata is a blocked readiness state, not an
            # authorization or analytical approval.
            mapping_record_verified = False
    # Strict calculation readiness cannot use the legacy catalogue shortcut;
    # every required variable must have a validated mapping record tied to the
    # selected dataset and reviewed release.
    mapping_verified = mapping_record_verified if strict_calculation else legacy_mapping_verified or mapping_record_verified
    if required_columns and mapping_verified:
        passed.append("verified_variable_mappings")
    else:
        _add_blocked(
            blocked,
            messages,
            "verified_variable_mappings",
            "Verified codebook mappings are missing; variable names alone are insufficient.",
        )

    if require_mapping_evidence:
        mappings = definition.get("verified_variable_mappings")
        has_full_mapping_records = isinstance(definition.get("mapping_records"), list)
        if has_full_mapping_records:
            mappings = definition.get("mapping_records")
        if not isinstance(mappings, list):
            mappings = []
        mapping_by_variable = {
            item.get("source_variable"): item
            for item in mappings
            if isinstance(item, dict) and isinstance(item.get("source_variable"), str)
        } if isinstance(mappings, list) else {}
        mapping_evidence_complete = bool(required_columns) and all(
            isinstance(mapping_by_variable.get(column), dict)
            and mapping_by_variable[column].get("status") == "verified"
            and (
                not mapping_by_variable[column].get("source_dataset_id")
                or mapping_by_variable[column].get("source_dataset_id") == (dataset or {}).get("dataset_id")
            )
            and (
                not has_full_mapping_records
                or all(
                    isinstance(mapping_by_variable[column].get(field), str)
                    and bool(mapping_by_variable[column].get(field).strip())
                    for field in (
                        "variable_meaning",
                        "codebook_reference",
                        "eligible_population",
                        "denominator_definition",
                        "missing_value_treatment",
                    )
                )
            )
            and isinstance(mapping_by_variable[column].get("evidence_reference"), str)
            and bool(mapping_by_variable[column].get("evidence_reference"))
            and (
                not has_full_mapping_records
                or isinstance(mapping_by_variable[column].get("codebook_reference"), str)
                and bool(mapping_by_variable[column].get("codebook_reference"))
            )
            and isinstance(mapping_by_variable[column].get("response_coding"), (dict, list, str))
            and bool(mapping_by_variable[column].get("response_coding"))
            for column in required_columns
        ) and (is_synthetic or has_full_mapping_records)
        if mapping_evidence_complete and not is_synthetic:
            source_docs = source_metadata.get("documentation_records", [])
            verified_codebooks = {
                str(item.get("path"))
                for item in source_docs
                if isinstance(item, dict)
                and item.get("document_type") == "codebook"
                and item.get("status") == "verified"
                and item.get("review_status") == "verified"
                and item.get("exact_release_status") == "verified"
                and item.get("release_identifier") == source_metadata.get("release_version")
            }
            mapping_evidence_complete = bool(verified_codebooks) and all(
                isinstance(mapping_by_variable.get(column), dict)
                and all(
                    isinstance(mapping_by_variable[column].get(field), str)
                    and mapping_by_variable[column][field].split("#", 1)[0] in verified_codebooks
                    for field in ("codebook_reference", "evidence_reference")
                )
                for column in required_columns
            )
        if mapping_evidence_complete:
            passed.append("mapping_evidence")
        else:
            _add_blocked(
                blocked,
                messages,
                "mapping_evidence",
                "Each required source variable needs a verified codebook-backed mapping record.",
            )

    definition_review = definition.get("definition_review")
    if isinstance(definition_review, dict):
        review_fields = definition_review.get("fields")
        target_release = definition_review.get("target_release_identifier")
        source_release = source_metadata.get("release_version")
        reviewed_documents = {
            str(item.get("path")): item
            for item in source_metadata.get("documentation_records", [])
            if isinstance(item, dict)
            and item.get("status") == "verified"
            and item.get("review_status") == "verified"
            and item.get("exact_release_status") == "verified"
            and item.get("release_identifier") == target_release
        }
        definition_review_passed = bool(target_release) and isinstance(review_fields, list) and bool(review_fields) and all(
            isinstance(item, dict)
            and item.get("status") == "verified"
            and item.get("release_identifier") == target_release
            and bool(source_release) and source_release == target_release
            and isinstance(item.get("evidence_reference"), str)
            and item.get("evidence_reference", "").split("#", 1)[0] in reviewed_documents
            and bool(item.get("reviewer"))
            and bool(item.get("review_date"))
            and bool(item.get("value"))
            for item in review_fields
        )
        if definition_review_passed:
            passed.append("definition_review")
        else:
            _add_blocked(
                blocked,
                messages,
                "definition_review",
                "Indicator definition fields require independent review against the exact target release.",
            )
    else:
        definition_review_passed = True

    definition_approved = (
        definition.get("status") in CALCULABLE_DEFINITION_STATUSES
        and definition.get("definition_approval_status") == "approved"
        and definition.get("methodology_approval_status") == "approved"
        and definition_review_passed
    )
    if definition_approved:
        passed.append("approved_definition_and_methodology")
    else:
        _add_blocked(
            blocked,
            messages,
            "approved_definition_and_methodology",
            "An approved indicator definition and methodology reference are required.",
        )

    missing_columns = [column for column in required_columns if column not in columns]
    if not missing_columns and required_columns:
        passed.append("required_columns")
    else:
        detail = (
            "Required columns cannot be confirmed until the selected source schema is documented."
            if dataset
            else "Required columns cannot be confirmed until an authorized source is selected."
        )
        if available_columns is not None and missing_columns:
            detail = "Required columns are missing from the selected source: " + ", ".join(missing_columns) + "."
        _add_blocked(blocked, messages, "required_columns", detail)

    if definition.get("value_semantics_verified") is True:
        passed.append("value_semantics")
    else:
        _add_blocked(
            blocked,
            messages,
            "value_semantics",
            "Value coding and missing-value semantics are not verified in the codebook.",
        )

    weight_required = bool(definition.get("survey_weight_requirements")) or definition.get("requires_survey_weight") is True
    if weight_required:
        weight_status = (dataset or {}).get("survey_weight_status")
        design_status = (dataset or {}).get("survey_design_status")
        weight_variable = (dataset or {}).get("survey_weight_variable")
        if weight_status in VERIFIED_STATUSES and design_status in VERIFIED_STATUSES and (
            not weight_variable or weight_variable in columns
        ):
            passed.append("survey_weight_and_design")
        else:
            _add_blocked(
                blocked,
                messages,
                "survey_weight_and_design",
                "Documented survey weights and sampling-design information are required before estimation.",
            )
    else:
        passed.append("survey_weight_and_design")

    if requested_geography:
        geography_status = (dataset or {}).get("geography_status")
        crosswalk_status = (dataset or {}).get("geographic_crosswalk_status")
        geography_variable = (dataset or {}).get("geographic_variable")
        if (
            geography_status in VERIFIED_STATUSES
            and crosswalk_status in VERIFIED_STATUSES
            and (not geography_variable or geography_variable in columns)
        ):
            passed.append("validated_geography")
        else:
            _add_blocked(
                blocked,
                messages,
                "validated_geography",
                "Geographic comparisons require a validated identifier and documented crosswalk.",
            )
        if geographic_resource_status == "verified":
            passed.append("geographic_resource_verified")
        else:
            _add_blocked(
                blocked,
                messages,
                "geographic_resource_verified",
                "An official, release-matched, structurally validated, and authorized geographic resource is required.",
            )
        if publication_requested or geographic_resource_publication_status is not None:
            if geographic_resource_publication_status in {"verified", "approved"}:
                passed.append("geographic_resource_publication")
            else:
                _add_blocked(
                    blocked,
                    messages,
                    "geographic_resource_publication",
                    "Separate publication approval for the boundary resource and intended map output is required.",
                )

    if strict_calculation:
        # These checks are intentionally in the central evaluator.  Phase 14
        # must not create a parallel approval flag that can drift from the
        # dashboard and the existing authorized loader.
        strict_checks: list[tuple[str, bool, str]] = [
            (
                "approved_registered_path",
                source_path_approved and source_available is True,
                "The selected dataset must resolve to its registered regular file below the approved data directory.",
            ),
            (
                "release_match",
                bool(
                    dataset
                    and source_metadata.get("release_version")
                    and dataset.get("dataset_version") == source_metadata.get("release_version")
                    and (
                        not isinstance(definition.get("definition_review"), dict)
                        or definition.get("definition_review", {}).get("target_release_identifier")
                        == source_metadata.get("release_version")
                    )
                ),
                "The registered dataset, source record, and indicator definition must identify the same exact release.",
            ),
            (
                "permitted_use",
                bool(
                    isinstance((dataset or {}).get("permitted_processing_purpose"), str)
                    and requested_processing_purpose
                    and requested_processing_purpose.casefold()
                    in (dataset or {}).get("permitted_processing_purpose", "").casefold()
                    and source_metadata.get("permitted_use_status") == "verified"
                ),
                "The intended processing purpose and applicable permitted-use restrictions must be documented and reviewed.",
            ),
            (
                "questionnaire_and_codebook_review",
                bool(
                    source_metadata
                    and source_metadata.get("documentation_review_status") == "verified"
                    and any(
                        isinstance(item, dict)
                        and item.get("document_type") == "questionnaire"
                        and item.get("status") == "verified"
                        and item.get("review_status") == "verified"
                        and item.get("exact_release_status") == "verified"
                        and item.get("release_identifier") == source_metadata.get("release_version")
                        for item in source_metadata.get("documentation_records", [])
                    )
                    and any(
                        isinstance(item, dict)
                        and item.get("document_type") == "codebook"
                        and item.get("status") == "verified"
                        and item.get("review_status") == "verified"
                        and item.get("exact_release_status") == "verified"
                        and item.get("release_identifier") == source_metadata.get("release_version")
                        for item in source_metadata.get("documentation_records", [])
                    )
                ),
                "The exact-release questionnaire and codebook must be reviewed before observations are used.",
            ),
            (
                "documented_schema",
                bool(
                    isinstance((dataset or {}).get("verified_schema_columns"), list)
                    and (dataset or {}).get("verified_schema_columns")
                    and schema_validated
                    and set(map(str, (dataset or {}).get("verified_schema_columns", []))) == columns
                ),
                "The expected exact-release schema must be documented and match the validated input schema.",
            ),
            (
                "eligibility_and_missingness_rules",
                bool(
                    isinstance(definition.get("eligibility_rules"), list)
                    and bool(definition.get("eligibility_rules"))
                    and isinstance(definition.get("missing_value_treatment"), str)
                    and bool(definition.get("missing_value_treatment", "").strip())
                ),
                "Eligibility, exclusion, and missing/refused/not-applicable rules must be documented.",
            ),
            (
                "complete_definition_review",
                bool(
                    isinstance(definition.get("definition_review"), dict)
                    and definition.get("definition_review", {}).get("complete") is True
                ),
                "Every required indicator-definition review field must be resolved for the target release.",
            ),
            (
                "calculation_specification_approval",
                bool(
                    isinstance(calculation_specification, dict)
                    and calculation_specification.get("status") == "approved"
                    and isinstance(calculation_specification.get("version"), str)
                    and bool(calculation_specification.get("version"))
                    and calculation_specification.get("indicator_id") == definition.get("indicator_id")
                    and calculation_specification.get("dataset_id") == (dataset or {}).get("dataset_id")
                    and calculation_specification.get("method") in {"proportion", "weighted_proportion"}
                    and isinstance(calculation_specification.get("formula"), str)
                    and bool(calculation_specification.get("formula"))
                    and isinstance(calculation_specification.get("evidence_references"), list)
                    and bool(calculation_specification.get("evidence_references"))
                    and isinstance(calculation_specification.get("rounding_digits"), int)
                    and not isinstance(calculation_specification.get("rounding_digits"), bool)
                    and calculation_specification.get("rounding_digits") >= 0
                ),
                "An approved indicator- and dataset-specific calculation specification is required.",
            ),
            (
                "central_analytical_eligibility",
                dataset_analytical_eligibility,
                "The central readiness metadata must explicitly mark the selected dataset analytically eligible after review.",
            ),
        ]
        for check, passed_check, message in strict_checks:
            if passed_check:
                passed.append(check)
            else:
                _add_blocked(blocked, messages, check, message)

        weight_required = bool(definition.get("survey_weight_requirements")) or definition.get("requires_survey_weight") is True
        weight_documented = bool(
            not weight_required
            or (
                (dataset or {}).get("survey_weight_status") in VERIFIED_STATUSES
                and isinstance((dataset or {}).get("survey_weight_variable"), str)
                and bool((dataset or {}).get("survey_weight_variable"))
                and isinstance((dataset or {}).get("survey_weight_interpretation"), str)
                and bool((dataset or {}).get("survey_weight_interpretation", "").strip())
                and (dataset or {}).get("survey_weight_variable") in columns
            )
        )
        if weight_documented:
            passed.append("weight_variable_and_interpretation")
        else:
            _add_blocked(
                blocked,
                messages,
                "weight_variable_and_interpretation",
                "The applicable weight variable and its interpretation must be documented and present in the validated schema.",
            )

        design_supported = bool(
            isinstance(survey_design, dict)
            and survey_design.get("status") == "approved"
            and isinstance(survey_design.get("sampling_design"), str)
            and bool(survey_design.get("sampling_design"))
            and isinstance(survey_design.get("variance_method"), str)
            and bool(survey_design.get("variance_method"))
            and survey_design.get("point_estimate_supported") is True
        )
        if design_supported:
            passed.append("survey_design_supported")
        else:
            _add_blocked(
                blocked,
                messages,
                "survey_design_supported",
                "Approved sampling-design and point-estimation support are required; complex-design uncertainty cannot be assumed.",
            )
        if isinstance(calculation_specification, dict) and calculation_specification.get("confidence_interval_requested"):
            uncertainty_supported = bool(
                design_supported
                and survey_design.get("variance_estimation_supported") is True
                and survey_design.get("variance_method") in {"linearization", "replicate_weights", "taylor_linearization"}
            )
            if uncertainty_supported:
                passed.append("variance_estimation_supported")
            else:
                _add_blocked(
                    blocked,
                    messages,
                    "variance_estimation_supported",
                    "The approved design does not provide a supported variance method for confidence intervals or standard errors.",
                )

    publication_authorized = (
        (dataset or {}).get("eligible_for_publication") is True
        and authorization in AUTHORIZED_PUBLICATION_STATUSES
        and definition.get("publication_status") == "eligible_for_publication"
        and (
            is_synthetic
            or source_metadata.get("publication_approval_status") == "verified"
        )
    )
    if publication_authorized:
        publication_eligible = True
        passed.append("publication_permission")
    else:
        publication_eligible = False
        publication_blocked.append("publication_permission")
        messages.append("Publication permission is not documented for this dataset and indicator.")

    analysis_eligible = not blocked
    eligible_for_requested_purpose = analysis_eligible and (not publication_requested or publication_eligible)
    return ReadinessResult(
        status=definition.get("status") if analysis_eligible else "blocked_pending_evidence",
        analysis_eligible=analysis_eligible,
        publication_eligible=publication_eligible,
        eligible_for_requested_purpose=eligible_for_requested_purpose,
        passed_checks=tuple(passed),
        blocked_checks=tuple(blocked),
        publication_blocked_checks=tuple(publication_blocked),
        # Keep positional alignment with ``blocked_checks`` so downstream
        # calculation reports can attach the exact message to each blocker.
        messages=tuple(messages),
        evidence_references=_safe_references(definition, dataset),
    )
