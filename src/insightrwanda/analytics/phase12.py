"""Controlled Phase 12 intake and candidate-indicator gate.

The default audit is metadata-only. File bytes are inspected only after the
registered dataset independently records verified provenance, documentation,
terms, authorization, and analytical eligibility.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from insightrwanda.data.paths import resolve_approved_data_path
from insightrwanda.data.registry import get_dataset
from insightrwanda.data.errors import DataLoaderError, DataPathError


ANALYSIS_AUTHORIZATIONS = {"authorized_for_analysis", "authorized_for_analysis_and_publication"}
VERIFIED = {"verified", "approved", "documented"}


def inspect_registered_dataset(
    registry: dict[str, dict[str, Any]], dataset_id: str | None, *, project_root: str | Path
) -> dict[str, Any]:
    """Safely inspect an explicitly registered source; never inspect unauthorized bytes."""

    dataset = get_dataset(registry, dataset_id)
    if dataset is None:
        return {"status": "blocked", "dataset_id": dataset_id, "requirements": ["Select an existing registered dataset ID."]}
    try:
        resolve_approved_data_path(Path("data") / str(dataset.get("source_path", "")), project_root=project_root)
        source_present = True
    except (DataPathError, DataLoaderError, OSError, ValueError):
        source_present = False
    gates = {
        "provenance_status": (dataset.get("provenance_status") == "verified", "Review an authoritative release record and match it to this exact source."),
        "documentation_status": (dataset.get("documentation_status") in VERIFIED, "Obtain and review the release-specific questionnaire, codebook, and technical documentation."),
        "codebook_status": (dataset.get("codebook_status") in VERIFIED, "A reviewer must verify the codebook for this exact release and record the evidence reference."),
        "documented_schema": (isinstance(dataset.get("verified_schema_columns"), list) and bool(dataset.get("verified_schema_columns")), "Record the exact expected columns from the reviewed release-specific codebook before schema validation."),
        "license_status": (dataset.get("license_status") in VERIFIED, "Record the applicable license or signed data-use terms."),
        "authorization_status": (dataset.get("authorization_status") in ANALYSIS_AUTHORIZATIONS, "Obtain written permission from the data owner for the stated analytical purpose."),
        "analytical_eligibility": (dataset.get("analytical_eligibility") is True, "A designated reviewer must record analytical eligibility after evidence review."),
    }
    requirements = [action for passed, action in gates.values() if not passed]
    if not source_present:
        requirements.insert(0, "The registered source file is absent from its approved data/ path; obtain it only through authorized channels.")
    if requirements:
        return {"status": "blocked", "dataset_id": dataset_id, "requirements": requirements, "file_inspected": False}
    try:
        path = resolve_approved_data_path(Path("data") / str(dataset.get("source_path", "")), project_root=project_root)
        if dataset.get("file_format", "").lower() != "csv":
            return {"status": "blocked", "dataset_id": dataset_id, "requirements": ["Authorized intake currently supports a reviewed CSV header only."], "file_inspected": False}
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            columns = next(csv.reader(source), [])
        expected = dataset.get("verified_schema_columns")
        schema_matches = isinstance(expected, list) and set(map(str, expected)) == set(map(str, columns))
        result = {
            "status": "inspected" if schema_matches else "blocked", "dataset_id": dataset_id, "file_inspected": True,
            "file_format": "csv", "file_size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(), "schema_columns": columns,
            "records_read": 0, "schema_validation": "passed" if schema_matches else "failed",
        }
        if not schema_matches:
            result["requirements"] = ["The observed header does not match the verified codebook schema; a reviewer must resolve the discrepancy before analysis."]
        return result
    except (DataPathError, DataLoaderError, OSError, UnicodeError, ValueError):
        return {"status": "blocked", "dataset_id": dataset_id, "requirements": ["The registered source is missing or could not be safely resolved below data/."], "file_inspected": False}


def build_phase12_status(
    registry: dict[str, dict[str, Any]], catalogue: dict[str, dict[str, Any]], *, project_root: str | Path,
    dataset_id: str | None = None, indicator_id: str = "FI-ACCESS-001",
) -> dict[str, Any]:
    """Build precise current blockers without opening source datasets."""

    preferred_id = dataset_id or "finscope_2024_rwanda_csv"
    dataset = get_dataset(registry, preferred_id)
    if dataset is None:
        dataset = next(iter(registry.values()), None)
    intake = inspect_registered_dataset(registry, dataset.get("dataset_id") if dataset else None, project_root=project_root)
    indicator = catalogue.get(indicator_id)
    indicator_blockers = []
    if indicator is None:
        indicator_blockers.append("FI-ACCESS-001 is not present in the current catalogue; select a documented candidate after review.")
    else:
        if indicator_id == "FI-ACCESS-001" and dataset and dataset.get("dataset_id") != "finscope_2024_rwanda_csv":
            indicator_blockers.append("FI-ACCESS-001 is currently documented only as a FinScope candidate; no evidence establishes conceptual fit to this selected dataset. Review the selected release independently before mapping.")
        if indicator.get("status") not in {"officially_documented", "derived_from_verified_variables"}:
            indicator_blockers.append("Indicator definition is still proposed; domain reviewer must approve the population and construct.")
        if not indicator.get("required_variables"):
            indicator_blockers.append("No required variables or independently verified codebook mappings are recorded; review the authorized release codebook and map each variable, coding, universe, and missing-value rule.")
        if not indicator.get("numerator_definition") or not indicator.get("denominator_definition"):
            indicator_blockers.append("Numerator and eligible denominator are unspecified; approve the exact definition and response categories from the questionnaire/codebook.")
        if not indicator.get("survey_weight_requirements"):
            indicator_blockers.append("Weighting requirements are not specified; review official weights and sampling design before selecting an estimator.")
    if dataset:
        if dataset.get("survey_weight_status") not in VERIFIED:
            indicator_blockers.append("The dataset's analysis weight is not verified; obtain codebook/technical documentation identifying the correct population weight. This blocks an estimate, not just geographic breakdowns.")
        if dataset.get("survey_design_status") not in VERIFIED:
            indicator_blockers.append("Strata, clusters, and variance-estimation guidance are not verified; review the technical report before claiming representative estimates or uncertainty.")
        if dataset.get("data_quality_status") not in VERIFIED | {"passed"}:
            indicator_blockers.append("No indicator-specific data-quality acceptance is recorded; run approved aggregate validation after authorized intake and have a reviewer accept it.")
    blockers = list(intake.get("requirements", []))
    blockers.extend(indicator_blockers)
    if not any("written permission" in item.lower() for item in blockers):
        blockers.append("Manual confirmation: the official catalogue offers a separate microdata access workflow; confirm approval and terms for this project before access or analysis.")
    blocker_details = []
    for item in blockers:
        affected_areas = ["analysis", "publication"]
        if any(term in item.lower() for term in ("source file", "provenance", "authorization", "permission", "survey design", "geographic")):
            affected_areas.append("geography")
        blocker_details.append({
            "requirement": item,
            "why_it_matters": "Required to establish source identity, analytical validity, or permitted use without substituting assumptions.",
            "affected_dataset_id": dataset.get("dataset_id") if dataset else None,
            "affected_indicator_id": indicator_id if indicator else None,
            "needed_evidence_or_confirmation": item,
            "next_action": item,
            "blocks": affected_areas,
        })
    return {
        "phase": 12,
        "status": "blocked" if blockers else "ready_for_review",
        "selected_dataset_id": dataset_id,
        "target_dataset_id": dataset.get("dataset_id") if dataset else None,
        "dataset_intake": intake,
        "candidate_indicator_id": indicator_id if indicator else None,
        "candidate_selection_status": "blocked" if indicator_blockers else "pending_manual_approval",
        "candidate_blockers": indicator_blockers,
        "blockers": blockers,
        "blocker_details": blocker_details,
        "analysis_eligible": False,
        "publication_eligible": False,
        "indicator_calculated": False,
        "result": None,
        "next_actions": [
            "Request the release-specific FinScope microdata through the official catalogue process and retain the approval/terms decision.",
            "Place any authorized source only in the approved controlled data directory and update the registry with verified provenance and permitted purpose.",
            "Obtain and manually review the release-matched codebook, questionnaire, weighting, sample-design, and geographic documentation.",
            "Have a domain reviewer verify the FI-ACCESS-001 population, coding, missingness, numerator, denominator, and exact mappings; then run authorized quality checks.",
            "Recompute readiness and obtain a separate disclosure/publication approval before releasing aggregates.",
        ],
        "raw_records_included": False,
    }
