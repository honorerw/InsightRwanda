"""End-to-end workflow and release-safety audit.

This module composes the existing Phase 12--17 authorities.  It is an audit
and reporting layer, not a second readiness evaluator: it never turns a
passed software check into analytical or publication eligibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from insightrwanda.data.errors import IndicatorBlockedError
from insightrwanda.data.paths import resolve_derived_output_path
from insightrwanda.analytics.phase12 import build_phase12_status
from insightrwanda.analytics.phase13 import build_phase13_status
from insightrwanda.analytics.phase14 import build_phase14_status, evaluate_phase14_readiness
from insightrwanda.analytics.readiness import evaluate_indicator_readiness
from insightrwanda.analytics.validation import contains_forbidden_raw_keys, validate_result_integrity
from insightrwanda.analytics.insights import build_verified_insight
from insightrwanda.analytics.reproducibility import build_phase20_status
from insightrwanda.data.registry import get_dataset, resolve_dataset_path
from insightrwanda.data.errors import DataPathError


WORKFLOW_STAGES: tuple[dict[str, Any], ...] = (
    {"stage_id": "dataset_registration", "label": "Dataset registration and inventory", "authority": "registry and inventory snapshot"},
    {"stage_id": "source_identity_authorization", "label": "Source provenance, release, and authorization", "authority": "central readiness evaluator"},
    {"stage_id": "definition_mapping_methodology", "label": "Definition, codebook, mappings, and methodology", "authority": "central readiness evaluator"},
    {"stage_id": "geographic_resource_verification", "label": "Geographic resource verification", "authority": "central readiness evaluator and geographic validator"},
    {"stage_id": "quality_and_survey_validation", "label": "Data quality and survey methodology", "authority": "Phase 14/15 validation and central readiness"},
    {"stage_id": "analytical_execution", "label": "Eligible analytical execution", "authority": "Phase 14 calculation gate"},
    {"stage_id": "result_lineage_and_integrity", "label": "Result lineage and integrity", "authority": "Phase 15 result-integrity validation"},
    {"stage_id": "statistical_validation", "label": "Statistical validation and quality assurance", "authority": "Phase 15 validation reports"},
    {"stage_id": "reproducibility_and_audit", "label": "Reproducibility manifest and audit trail", "authority": "Phase 20 reproducibility validator"},
    {"stage_id": "disclosure_and_publication", "label": "Disclosure and publication eligibility", "authority": "central publication gate and Phase 17 insight gate"},
    {"stage_id": "approved_presentation", "label": "Approved result presentation and release", "authority": "Phase 17 visualization gate"},
    {"stage_id": "readiness_consistency", "label": "Central and reported readiness consistency", "authority": "central evaluator and research-readiness report"},
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _stage(
    stage_id: str,
    status: str,
    *,
    blocker_ids: Iterable[str] = (),
    next_actions: Iterable[str] = (),
    explanation: str,
    scope: str = "analysis",
    evidence: Iterable[str] = (),
) -> dict[str, Any]:
    definition = next(item for item in WORKFLOW_STAGES if item["stage_id"] == stage_id)
    return {
        "stage_id": stage_id,
        "label": definition["label"],
        "authority": definition["authority"],
        "status": status,
        "scope": scope,
        "blocker_ids": _unique(blocker_ids),
        "next_actions": _unique(next_actions),
        "explanation": explanation,
        "evidence_references": _unique(evidence),
    }


def _readiness_blockers(readiness: dict[str, Any] | None, allowed: Iterable[str] | None = None) -> list[str]:
    if not isinstance(readiness, dict):
        return []
    values = [str(item) for item in readiness.get("blocked_checks", []) if item]
    if allowed is None:
        return _unique(values)
    allowed_set = set(allowed)
    return _unique(item for item in values if item in allowed_set)


def _readiness_actions(readiness: dict[str, Any] | None) -> list[str]:
    return _unique(readiness.get("messages", []) if isinstance(readiness, dict) else ())


def _source_record(source_verification: dict[str, Any] | None, dataset_id: str) -> dict[str, Any] | None:
    return next(
        (
            item for item in (source_verification or {}).get("sources", [])
            if isinstance(item, dict) and item.get("dataset_id") == dataset_id
        ),
        None,
    )


def _lineage_blockers(
    result: dict[str, Any],
    *,
    dataset: dict[str, Any] | None,
    definition: dict[str, Any] | None,
    source: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    if dataset is None or result.get("dataset_id") != dataset.get("dataset_id"):
        blockers.append("result_dataset_mismatch")
    expected_releases = _unique(
        value for value in (
            dataset.get("dataset_version") if isinstance(dataset, dict) else None,
            source.get("release_version") if isinstance(source, dict) else None,
        )
    )
    if expected_releases and result.get("dataset_release") not in expected_releases:
        blockers.append("result_release_mismatch")
    if definition is None or result.get("indicator_id") != definition.get("indicator_id"):
        blockers.append("result_indicator_mismatch")
    if definition is None or result.get("definition_version") != definition.get("definition_version"):
        blockers.append("result_definition_version_mismatch")
    provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    if provenance.get("dataset_id") not in (None, result.get("dataset_id")):
        blockers.append("provenance_dataset_contradiction")
    if provenance.get("dataset_release") not in (None, result.get("dataset_release")):
        blockers.append("provenance_release_contradiction")
    if provenance.get("indicator_id") not in (None, result.get("indicator_id")):
        blockers.append("provenance_indicator_contradiction")
    return _unique(blockers)


def _geographic_readiness(
    *,
    project_root: str | Path,
    definition: dict[str, Any] | None,
    dataset: dict[str, Any] | None,
    source: dict[str, Any] | None,
    geographic_resource_status: str | None,
    geographic_resource_publication_status: str | None,
) -> dict[str, Any]:
    if not isinstance(definition, dict) or not isinstance(dataset, dict):
        return {"analysis_eligible": False, "blocked_checks": ["geographic_inputs"]}
    source_available = False
    source_path_approved = False
    try:
        source_path = resolve_dataset_path(dataset, project_root=project_root)
        source_path_approved = True
        source_available = source_path.is_file()
    except (DataPathError, OSError, ValueError):
        pass
    result = evaluate_indicator_readiness(
        definition,
        dataset,
        available_columns=dataset.get("verified_schema_columns") if isinstance(dataset.get("verified_schema_columns"), list) else None,
        requested_geography=True,
        require_research_evidence=True,
        require_data_quality=True,
        require_calculation_specification=True,
        require_mapping_evidence=True,
        source_verification=source,
        source_available=source_available,
        source_path_approved=source_path_approved,
        strict_calculation=True,
        calculation_specification=definition.get("calculation_specification"),
        survey_design=dataset.get("survey_design"),
        geographic_resource_status=geographic_resource_status,
        geographic_resource_publication_status=geographic_resource_publication_status,
        schema_validated=False,
    )
    return result.as_dict()


def build_phase18_status(
    project_root: str | Path,
    registry: dict[str, dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    evidence: dict[str, Any] | None,
    source_verification: dict[str, Any] | None,
    *,
    inventory: dict[str, Any] | None = None,
    geographic_resources: list[dict[str, Any]] | None = None,
    dataset_id: str = "finscope_2024_rwanda_csv",
    indicator_id: str = "FI-ACCESS-001",
    result: dict[str, Any] | None = None,
    intended_use: str = "public_display",
    geographic_requested: bool = False,
    geographic_result: dict[str, Any] | None = None,
    reproducibility_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit workflow transitions using the existing centralized decisions."""

    # This module is the composition layer of the analytics package, so the
    # research-readiness report is imported here instead of at module level.
    # A module-level import would create a circular import through
    # insightrwanda.analytics.__init__ when data.research_readiness (or
    # data.inventory) is imported first.
    from insightrwanda.data.research_readiness import (
        build_research_readiness_report,
        verify_inventory_snapshot,
    )

    root = Path(project_root).resolve()
    dataset = get_dataset(registry, dataset_id)
    definition = catalogue.get(indicator_id)
    source = _source_record(source_verification, dataset_id)
    inventory_state = verify_inventory_snapshot(inventory, project_root=root)
    report = build_research_readiness_report(
        root,
        inventory=inventory,
        registry=registry,
        catalogue=catalogue,
        evidence=evidence,
        source_verification=source_verification,
        geographic_resources=geographic_resources or [],
    )
    phase12 = build_phase12_status(registry, catalogue, project_root=root, dataset_id=dataset_id, indicator_id=indicator_id)
    phase13 = build_phase13_status(root, registry, catalogue, evidence, source_verification, dataset_id=dataset_id, indicator_id=indicator_id)
    phase14 = build_phase14_status(root, registry, catalogue, source_verification, dataset_id=dataset_id, indicator_id=indicator_id)
    phase14_readiness = phase14.get("readiness") if isinstance(phase14.get("readiness"), dict) else {}
    # A metadata-only Phase 14 status deliberately leaves schema validation
    # unperformed. When auditing an existing aggregate result, re-run the same
    # central evaluator with the registered, already documented schema; this
    # still inspects metadata only and cannot authorize a result on its own.
    if isinstance(result, dict) and isinstance(dataset, dict) and isinstance(definition, dict):
        calculation_readiness = evaluate_phase14_readiness(
            project_root=root,
            definition=definition,
            dataset=dataset,
            source_verification=source_verification,
            available_columns=dataset.get("verified_schema_columns") if isinstance(dataset.get("verified_schema_columns"), list) else None,
            schema_validated=True,
        ).as_dict()
        phase14_readiness = calculation_readiness
    stages: list[dict[str, Any]] = []

    if dataset is None:
        stages.append(_stage("dataset_registration", "blocked", blocker_ids=("dataset_registered",), next_actions=("Register the exact dataset ID before using the controlled workflow.",), explanation="The requested dataset is not in the registry."))
    else:
        inventory_blockers = [] if inventory_state.get("status") == "current" else ["inventory_snapshot"]
        stages.append(_stage(
            "dataset_registration",
            "pass" if not inventory_blockers else "blocked",
            blocker_ids=inventory_blockers,
            next_actions=("Refresh the approved source inventory before relying on file presence." if inventory_blockers else "None recorded.",),
            explanation="The dataset is registered and its inventory snapshot is current." if not inventory_blockers else "The dataset is registered, but the inventory snapshot is not current.",
        ))

    source_checks = ("dataset_authorization", "source_provenance", "dataset_documentation", "license_or_terms", "source_reference_review", "source_release_identity", "source_document_review", "source_access_authorization", "source_analysis_approval", "source_file_availability", "approved_registered_path", "release_match", "permitted_use")
    source_blockers = _readiness_blockers(phase14_readiness, source_checks)
    stages.append(_stage(
        "source_identity_authorization",
        "pass" if dataset is not None and not source_blockers else "blocked",
        blocker_ids=source_blockers or (("dataset_registered",) if dataset is None else ()),
        next_actions=_readiness_actions(phase14_readiness) or ("Record verified provenance, exact release identity, authorization, and permitted use.",),
        explanation="Source identity and authorization prerequisites are satisfied." if dataset is not None and not source_blockers else "Source identity, authorization, or permitted-use prerequisites remain unresolved.",
        evidence=((source or {}).get("source_id"),) if source else (),
    ))

    definition_checks = ("calculation_specification", "verified_variable_mappings", "mapping_evidence", "definition_review", "approved_definition_and_methodology", "required_columns", "value_semantics", "questionnaire_and_codebook_review", "documented_schema", "eligibility_and_missingness_rules", "complete_definition_review", "calculation_specification_approval")
    definition_blockers = _readiness_blockers(phase14_readiness, definition_checks)
    stages.append(_stage(
        "definition_mapping_methodology",
        "pass" if definition is not None and not definition_blockers else "blocked",
        blocker_ids=definition_blockers or (("indicator_definition_missing",) if definition is None else ()),
        next_actions=_readiness_actions(phase14_readiness) or ("Complete the exact-release indicator definition, mappings, and approved calculation specification.",),
        explanation="The versioned definition, mappings, and methodology are ready." if definition is not None and not definition_blockers else "The indicator definition, mappings, or methodology is not ready.",
        scope="analysis",
    ))

    if geographic_requested:
        resource_ids = {item.get("resource_id") for item in geographic_resources or [] if isinstance(item, dict)}
        resource_status = "verified" if any(item.get("verification_status") == "verified" for item in geographic_resources or [] if isinstance(item, dict)) else "missing"
        geo_readiness = _geographic_readiness(
            project_root=root,
            definition=definition,
            dataset=dataset,
            source=source,
            geographic_resource_status=resource_status,
            geographic_resource_publication_status="approved" if any(item.get("publication_status") == "approved" for item in geographic_resources or [] if isinstance(item, dict)) else "missing",
        )
        geo_blockers = _readiness_blockers(geo_readiness)
        stages.append(_stage(
            "geographic_resource_verification",
            "pass" if resource_status == "verified" and not geo_blockers else "blocked",
            blocker_ids=geo_blockers or (("geographic_resource_verified",) if resource_status != "verified" else ()),
            next_actions=_readiness_actions(geo_readiness) or ("Verify an official, release-matched geographic resource and identifiers.",),
            explanation="Geographic prerequisites are verified." if resource_status == "verified" and not geo_blockers else "Geographic analysis is requested but its resource or central geography prerequisites are unresolved.",
            scope="geography",
            evidence=resource_ids,
        ))
    else:
        stages.append(_stage("geographic_resource_verification", "not_applicable", explanation="Geographic resources are not required for this non-geographic indicator workflow.", scope="geography"))

    quality_checks = ("data_quality_acceptance", "survey_weight_and_design", "survey_design_supported", "weight_variable_and_interpretation", "variance_estimation_supported")
    quality_blockers = _readiness_blockers(phase14_readiness, quality_checks)
    stages.append(_stage(
        "quality_and_survey_validation",
        "pass" if not quality_blockers else "blocked",
        blocker_ids=quality_blockers,
        next_actions=_readiness_actions(phase14_readiness) or ("Complete approved data-quality and survey-design validation.",),
        explanation="Data-quality and survey-method prerequisites are satisfied." if not quality_blockers else "Data-quality or survey-method prerequisites remain unresolved.",
    ))

    if result is None:
        analytical_blockers = _unique([*phase14.get("blocker_ids", []), "analytical_result_missing"])
        stages.append(_stage("analytical_execution", "blocked", blocker_ids=analytical_blockers, next_actions=("Resolve central analytical prerequisites before executing the calculation.",), explanation="No eligible aggregate result is available; no calculation was executed."))
    elif (
        phase14_readiness.get("analysis_eligible") is not True
        or result.get("calculation_status") != "calculated"
        or (result.get("readiness") or {}).get("analysis_eligible") is not True
    ):
        result_gate = "result_central_analytical_eligibility" if (result.get("readiness") or {}).get("analysis_eligible") is not True else "central_analytical_eligibility"
        stages.append(_stage("analytical_execution", "blocked", blocker_ids=_unique([*phase14.get("blocker_ids", []), result_gate]), next_actions=("The supplied result cannot override the current central analytical decision.",), explanation="The supplied result is not accepted because its recorded or current central readiness is not analytically eligible."))
    else:
        stages.append(_stage("analytical_execution", "pass", explanation="The supplied aggregate result is calculated under an analytically eligible central decision."))

    if result is None:
        stages.append(_stage("result_lineage_and_integrity", "not_run", explanation="Result integrity and lineage checks have not run because no result is available."))
        stages.append(_stage("statistical_validation", "not_run", explanation="Statistical validation has not run because no result is available."))
        stages.append(_stage("disclosure_and_publication", "blocked", blocker_ids=("analytical_result_missing",), next_actions=("Produce an eligible aggregate before disclosure and publication review.",), explanation="Publication cannot be reviewed without an eligible result."))
    else:
        integrity = validate_result_integrity(result)
        lineage = _lineage_blockers(result, dataset=dataset, definition=definition, source=source)
        integrity_blockers = list(lineage)
        if not integrity.calculation_allowed:
            integrity_blockers.append("result_integrity")
        if result.get("data_classification") == "synthetic_test_data":
            integrity_blockers.append("synthetic_result_not_for_real_research")
        stages.append(_stage(
            "result_lineage_and_integrity",
            "pass" if not integrity_blockers else "blocked",
            blocker_ids=integrity_blockers,
            next_actions=("Repair contradictory lineage or aggregate provenance before accepting the result.",) if integrity_blockers else ("None recorded.",),
            explanation="Result provenance, lineage, and aggregate integrity are valid." if not integrity_blockers else "The result has missing, contradictory, synthetic, or invalid lineage/integrity metadata.",
            evidence=((result.get("provenance") or {}).get("mapping_evidence_references") or []),
        ))
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        validation_blockers = []
        if (result.get("quality_validation") or {}).get("status") != "pass":
            validation_blockers.append("quality_validation")
        if any((validation.get(name) or {}).get("status") != "pass" for name in ("input_validation", "result_integrity")):
            validation_blockers.append("calculation_validation")
        stages.append(_stage(
            "statistical_validation",
            "pass" if not validation_blockers else "blocked",
            blocker_ids=validation_blockers,
            next_actions=("Run and pass the approved Phase 15 validation checks before release.",) if validation_blockers else ("None recorded.",),
            explanation="The supplied result carries passing statistical and quality-validation reports." if not validation_blockers else "Statistical or quality-validation reports are missing or failing.",
        ))
        insight = build_verified_insight(result, definition, intended_use=intended_use)
        publication_blockers = list(insight.get("blocker_ids", [])) if insight.get("status") != "verified" else []
        stages.append(_stage(
            "disclosure_and_publication",
            "pass" if not publication_blockers else "blocked",
            blocker_ids=publication_blockers,
            next_actions=insight.get("next_actions") or ("Complete separate disclosure and publication review.",),
            explanation="The result is eligible for the requested presentation use." if not publication_blockers else "The result is not eligible for the requested disclosure/publication use.",
            scope="publication",
        ))

    if geographic_requested and geographic_result is None:
        stages.append(_stage("approved_presentation", "blocked", blocker_ids=("geographic_result_missing",), next_actions=("Complete and approve the geographic aggregate and join before presentation.",), explanation="A requested geographic presentation has no approved geographic result.", scope="publication"))
    elif geographic_requested and isinstance(geographic_result, dict):
        geographic_blockers = []
        if geographic_result.get("status") != "validated":
            geographic_blockers.append("geographic_result_validation")
        if geographic_result.get("analysis_eligible") is not True:
            geographic_blockers.append("central_analytical_eligibility")
        if (geographic_result.get("join_validation") or {}).get("status") != "validated":
            geographic_blockers.append("geographic_join_validation")
        if (geographic_result.get("area_validation") or {}).get("status") != "pass":
            geographic_blockers.append("geographic_area_validation")
        stages.append(_stage("approved_presentation", "pass" if not geographic_blockers else "blocked", blocker_ids=geographic_blockers, next_actions=("Resolve geographic validation and publication gates.",) if geographic_blockers else ("None recorded.",), explanation="The geographic result is validated for presentation." if not geographic_blockers else "The geographic result is not validated for presentation.", scope="publication"))
    elif result is None:
        stages.append(_stage("approved_presentation", "blocked", blocker_ids=("analytical_result_missing",), next_actions=("No result can be presented.",), explanation="No aggregate result is available for presentation.", scope="publication"))
    else:
        insight = build_verified_insight(result, definition, intended_use=intended_use)
        presentation_blockers = list(insight.get("blocker_ids", [])) if insight.get("status") != "verified" else []
        stages.append(_stage("approved_presentation", "pass" if not presentation_blockers else "blocked", blocker_ids=presentation_blockers, next_actions=insight.get("next_actions") or ("None recorded.",), explanation="The aggregate result is approved for the requested presentation use." if not presentation_blockers else "The result cannot be presented for the requested use.", scope="publication"))

    central_analysis = phase14_readiness.get("analysis_eligible") is True
    central_publication = phase14_readiness.get("publication_eligible") is True
    phase20 = build_phase20_status(
        manifest=reproducibility_manifest,
        result=result,
        expected_lineage={
            "dataset_id": dataset.get("dataset_id") if isinstance(dataset, dict) else None,
            "dataset_release": (dataset or {}).get("dataset_version") if isinstance(dataset, dict) else None,
            "indicator_id": definition.get("indicator_id") if isinstance(definition, dict) else None,
            "definition_version": definition.get("definition_version") if isinstance(definition, dict) else None,
        },
        current_eligibility={
            "analysis_eligible": central_analysis,
            "publication_eligible": central_publication,
        },
        geographic_required=geographic_requested,
        publication_requested=intended_use == "public_display",
    )
    reproducibility_blockers = list(phase20.get("blocker_ids", []))
    stages.append(_stage(
        "reproducibility_and_audit",
        "pass" if phase20.get("status") == "verified" else "blocked",
        blocker_ids=reproducibility_blockers,
        next_actions=("None recorded.",) if not reproducibility_blockers else ("Create and validate a manifest from an eligible aggregate; revalidate changed inputs before relying on the result.",),
        explanation="The result has a verified reproducibility manifest and traceable integrity." if phase20.get("status") == "verified" else "Reproducibility is not verified; a manifest, result integrity, lineage, or current eligibility prerequisite is missing.",
        scope="governance",
    ))
    report_indicator = next((item for item in report.get("indicators", []) if isinstance(item, dict) and item.get("indicator_id") == indicator_id), None)
    consistency_blockers: list[str] = []
    if report_indicator is not None and bool(report_indicator.get("analytical_eligibility")) != central_analysis:
        consistency_blockers.append("readiness_report_analysis_mismatch")
    if report_indicator is not None and bool(report_indicator.get("publication_eligibility")) != central_publication:
        consistency_blockers.append("readiness_report_publication_mismatch")
    stages.append(_stage(
        "readiness_consistency",
        "pass" if not consistency_blockers else "blocked",
        blocker_ids=consistency_blockers,
        next_actions=("Reconcile the readiness report with the central evaluator before release.",) if consistency_blockers else ("None recorded.",),
        explanation="The indicator-level readiness report agrees with the central evaluator." if not consistency_blockers else "The indicator-level readiness report disagrees with the central evaluator.",
        scope="governance",
    ))

    blocker_ids = _unique(item for stage in stages for item in stage.get("blocker_ids", []))
    all_complete = all(stage["status"] in {"pass", "not_applicable"} for stage in stages)
    return {
        "phase": 18,
        "audit_type": "end_to_end_workflow_readiness",
        "status": "ready" if all_complete and not blocker_ids else "blocked",
        "dataset_id": dataset_id,
        "indicator_id": indicator_id,
        "intended_use": intended_use,
        "analytical_eligibility": central_analysis,
        "publication_eligibility": central_publication,
        "release_eligible": all_complete and not blocker_ids,
        "reproducibility": phase20,
        "blocker_ids": blocker_ids,
        "stages": stages,
        "lineage": {
            "dataset_id": result.get("dataset_id") if isinstance(result, dict) else dataset_id,
            "dataset_release": result.get("dataset_release") if isinstance(result, dict) else None,
            "indicator_id": result.get("indicator_id") if isinstance(result, dict) else indicator_id,
            "definition_version": result.get("definition_version") if isinstance(result, dict) else (definition or {}).get("definition_version"),
            "result_present": isinstance(result, dict),
            "raw_records_included": bool(result and result.get("raw_records_included")) if isinstance(result, dict) else False,
        },
        "report_metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "inventory_status": inventory_state.get("status"),
            "central_readiness_source": "evaluate_indicator_readiness via Phase 14",
            "source_data_loaded": False,
        },
        "raw_records_included": False,
        "data_classification": "metadata_only",
        "result_artifact_written": False,
    }


def save_workflow_audit(
    audit: dict[str, Any],
    *,
    project_root: str | Path,
    output_path: str | Path = "artifacts/phase18_status.json",
) -> Path:
    """Persist only the metadata-only workflow audit, never a result artifact."""

    if not isinstance(audit, dict) or audit.get("audit_type") != "end_to_end_workflow_readiness":
        raise IndicatorBlockedError("Only a structured Phase 18 workflow audit may be persisted.")
    if audit.get("raw_records_included") is True or audit.get("data_classification") != "metadata_only":
        raise IndicatorBlockedError("Workflow audits may contain metadata only.")
    if contains_forbidden_raw_keys(audit):
        raise IndicatorBlockedError("Workflow audits may not contain nested row-level or geometry payloads.")
    status = audit.get("status")
    if status not in {"blocked", "ready"}:
        raise IndicatorBlockedError("Workflow audit status is unsupported.")
    blocker_ids = audit.get("blocker_ids")
    stages = audit.get("stages")
    if not isinstance(blocker_ids, list) or not all(isinstance(item, str) and item for item in blocker_ids):
        raise IndicatorBlockedError("Workflow audits require a list of stable blocker identifiers.")
    if len(blocker_ids) != len(set(blocker_ids)):
        raise IndicatorBlockedError("Workflow audit blocker identifiers must be deduplicated.")
    if not isinstance(stages, list) or not stages:
        raise IndicatorBlockedError("Workflow audits require their evaluated workflow stages.")
    expected_stage_ids = {item["stage_id"] for item in WORKFLOW_STAGES}
    stage_ids: set[str] = set()
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("stage_id"), str) or stage["stage_id"] in stage_ids:
            raise IndicatorBlockedError("Workflow audit stages must have unique identifiers.")
        if stage.get("status") not in {"pass", "blocked", "not_applicable", "not_run"}:
            raise IndicatorBlockedError("Workflow audit contains an unsupported stage status.")
        stage_ids.add(stage["stage_id"])
    if stage_ids != expected_stage_ids:
        raise IndicatorBlockedError("Workflow audit does not contain the complete known stage set.")
    expected_release_eligible = status == "ready" and not blocker_ids and all(
        stage.get("status") in {"pass", "not_applicable"} for stage in stages
    )
    if audit.get("release_eligible") is not expected_release_eligible:
        raise IndicatorBlockedError("Workflow audit release eligibility is inconsistent with its stages and blockers.")
    output = resolve_derived_output_path(output_path, project_root=project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


__all__ = ["WORKFLOW_STAGES", "build_phase18_status", "save_workflow_audit"]
