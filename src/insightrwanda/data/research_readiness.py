"""Safe source-verification and research-readiness metadata.

This module inspects paths and existing metadata only. It never loads tabular
source records, extracts document text, or changes authorization decisions.
"""

from __future__ import annotations

import os
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .paths import _is_relative_to
from .validation import validate_geojson_structure
from .geography import summarize_geographic_resources
from .errors import SchemaValidationError
from .evidence import actionable_evidence_items, summarize_evidence
from .source_verification import build_researcher_action_plan, summarize_access_checklist, summarize_source_verification
from insightrwanda.analytics.mappings import summarize_mapping_records
from insightrwanda.analytics.readiness import evaluate_indicator_readiness


DOCUMENTATION_REQUIREMENTS = (
    "codebook_or_data_dictionary",
    "questionnaire",
    "survey_design_and_weight_documentation",
    "license_or_data_use_terms",
    "geographic_crosswalk",
)


def _current_data_snapshot(project_root: str | Path) -> tuple[tuple[str, ...], int]:
    """Return regular data-file paths and skipped symlink count deterministically."""

    root = Path(project_root).expanduser().resolve()
    data_root = (root / "data").resolve()
    if not data_root.is_dir():
        return (), 0

    paths: list[str] = []
    skipped_symlinks = 0
    for directory, directories, filenames in os.walk(data_root, followlinks=False):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for name in sorted(directories):
            candidate = directory_path / name
            if candidate.is_symlink():
                skipped_symlinks += 1
            else:
                kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(filenames):
            candidate = directory_path / name
            if candidate.is_symlink():
                skipped_symlinks += 1
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if resolved.is_file() and _is_relative_to(resolved, data_root):
                paths.append(candidate.relative_to(root).as_posix())
    return tuple(sorted(paths)), skipped_symlinks


def current_data_file_paths(project_root: str | Path) -> tuple[str, ...]:
    """Return only regular files currently present below the approved data root."""

    paths, _ = _current_data_snapshot(project_root)
    return paths


def _safe_inventory_paths(inventory: dict[str, Any] | None, project_root: str | Path) -> tuple[set[str], int]:
    if not isinstance(inventory, dict) or not isinstance(inventory.get("files"), list):
        return set(), 0
    root = Path(project_root).expanduser().resolve()
    data_root = (root / "data").resolve()
    paths: set[str] = set()
    invalid_count = 0
    for record in inventory["files"]:
        if not isinstance(record, dict) or not isinstance(record.get("relative_path"), str):
            invalid_count += 1
            continue
        relative = Path(record["relative_path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            invalid_count += 1
            continue
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            invalid_count += 1
            continue
        if not _is_relative_to(resolved, data_root):
            invalid_count += 1
            continue
        paths.add(relative.as_posix())
    return paths, invalid_count


def verify_inventory_snapshot(
    inventory: dict[str, Any] | None, *, project_root: str | Path
) -> dict[str, Any]:
    """Compare safe inventory paths with the current data tree.

    This is a low-cost freshness check. It does not hash or open source files,
    so the inventory generator remains the explicit operation for checksum and
    structural metadata collection.
    """

    current_paths, skipped_symlink_count = _current_data_snapshot(project_root)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("files"), list):
        return {
            "status": "missing_or_malformed",
            "indexed_file_count": 0,
            "current_file_count": len(current_paths),
            "missing_indexed_file_count": 0,
            "unindexed_file_count": len(current_paths),
            "invalid_record_count": 0,
            "skipped_symlink_count": skipped_symlink_count,
            "inventory_fingerprint": None,
        }

    indexed_paths, invalid_count = _safe_inventory_paths(inventory, project_root)
    current_set = set(current_paths)
    return {
        "status": (
            "current"
            if not invalid_count and indexed_paths == current_set
            else "stale"
        ),
        "indexed_file_count": len(indexed_paths),
        "current_file_count": len(current_set),
        "missing_indexed_file_count": len(indexed_paths - current_set),
        "unindexed_file_count": len(current_set - indexed_paths),
        "invalid_record_count": invalid_count,
        "skipped_symlink_count": skipped_symlink_count,
        "inventory_fingerprint": inventory.get("inventory_fingerprint"),
    }


def classify_data_path(relative_path: str) -> str:
    """Classify a path without inspecting its contents."""

    path = PurePosixPath(relative_path)
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    suffix = path.suffix.lower()
    if "metadata" in parts:
        return "metadata"
    if "geo" in parts and suffix in {".geojson", ".json", ".gpkg", ".shp"}:
        return "geographic_boundary"
    if any(token in name for token in ("codebook", "dictionary", "questionnaire")):
        return "source_documentation"
    if any(token in name for token in ("sampling", "sample", "survey_design", "weight", "methodology", "technical")):
        return "source_documentation"
    if any(token in name for token in ("license", "licence", "terms", "agreement")):
        return "source_documentation"
    if suffix in {".pdf", ".doc", ".docx", ".odt"}:
        return "source_documentation"
    if suffix in {".csv", ".dta", ".sav", ".sas7bdat", ".xls", ".xlsx"}:
        return "tabular_source"
    return "other"


def _documentation_kind(relative_path: str) -> str | None:
    path = PurePosixPath(relative_path)
    name = path.name.lower()
    if any(token in name for token in ("codebook", "dictionary")):
        return "codebook_or_data_dictionary"
    if "questionnaire" in name:
        return "questionnaire"
    if any(token in name for token in ("sampling", "sample", "survey_design", "weight", "methodology", "technical")):
        return "survey_design_and_weight_documentation"
    if any(token in name for token in ("license", "licence", "terms", "agreement")):
        return "license_or_data_use_terms"
    return None


def _reference_exists(project_root: Path, reference: str) -> bool:
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return False
    resolved = (project_root / candidate).resolve(strict=False)
    data_root = (project_root / "data").resolve()
    if not _is_relative_to(resolved, data_root):
        return False
    return resolved.is_file() or resolved.is_dir()


def _documentation_summary(project_root: Path, current_paths: Iterable[str]) -> dict[str, Any]:
    counts = Counter(classify_data_path(path) for path in current_paths)
    documentation_counts = Counter(
        kind
        for path in current_paths
        if (kind := _documentation_kind(path)) is not None
    )
    requirements = {
        requirement: ("present_unverified" if documentation_counts.get(requirement, 0) else "missing")
        for requirement in DOCUMENTATION_REQUIREMENTS
    }
    return {
        "category_counts": dict(sorted(counts.items())),
        "documentation_file_count": counts.get("source_documentation", 0),
        "boundary_file_count": counts.get("geographic_boundary", 0),
        "documentation_kind_counts": dict(sorted(documentation_counts.items())),
        "requirements": requirements,
    }


def _registered_source_present(source_path: Any, current_paths: set[str]) -> bool:
    """Match registry paths relative to data/ to inventory paths relative to root."""

    if not isinstance(source_path, str) or not source_path.strip():
        return False
    normalized = Path(source_path).as_posix()
    return normalized in current_paths or (Path("data") / Path(source_path)).as_posix() in current_paths


def _geographic_asset_summary(project_root: Path, current_paths: Iterable[str]) -> dict[str, Any]:
    """Validate supported boundary containers without retaining geometries."""

    assets: list[dict[str, Any]] = []
    root = project_root.resolve()
    for relative_path in sorted(current_paths):
        if classify_data_path(relative_path) != "geographic_boundary":
            continue
        suffix = PurePosixPath(relative_path).suffix.lower()
        asset: dict[str, Any] = {
            "relative_path": relative_path,
            "format": suffix.lstrip(".") or "unknown",
            "structural_status": "not_validated",
        }
        if suffix == ".geojson":
            try:
                document = json.loads((root / relative_path).read_text(encoding="utf-8"))
                structure = validate_geojson_structure(document)
                asset.update(
                    {
                        "structural_status": "valid",
                        "feature_count": structure["feature_count"],
                    }
                )
            except (OSError, UnicodeError, ValueError, SchemaValidationError):
                asset["structural_status"] = "invalid"
        assets.append(asset)
    return {
        "asset_count": len(assets),
        "valid_asset_count": sum(asset["structural_status"] == "valid" for asset in assets),
        "invalid_asset_count": sum(asset["structural_status"] == "invalid" for asset in assets),
        "assets": assets,
    }


def _dataset_readiness(dataset: dict[str, Any], current_paths: set[str]) -> dict[str, Any]:
    source_path = dataset.get("source_path")
    present = _registered_source_present(source_path, current_paths)
    return {
        "dataset_id": dataset.get("dataset_id"),
        "display_name": dataset.get("display_name"),
        "source_presence": "discovered" if present else "missing",
        "provenance_status": dataset.get("provenance_status", "unverified"),
        "authorization_status": dataset.get("authorization_status", "unverified"),
        "documentation_status": dataset.get("documentation_status", "missing_or_unverified"),
        "license_status": dataset.get("license_status", "unverified"),
        "integrity_status": "recorded" if dataset.get("integrity_sha256") else "not_recorded",
        "data_quality_status": dataset.get("data_quality_status", "unverified"),
        "survey_design_status": dataset.get("survey_design_status", "unverified"),
        "survey_weight_status": dataset.get("survey_weight_status", "unverified"),
        "geography_status": dataset.get("geography_status", "unverified"),
        "geographic_crosswalk_status": dataset.get("geographic_crosswalk_status", "unverified"),
        "geographic_variable": dataset.get("geographic_variable"),
        "geographic_level": dataset.get("geographic_level"),
        "geographic_boundary_release": dataset.get("geographic_boundary_release"),
        "analytical_eligibility": dataset.get("analytical_eligibility") is True,
        "publication_eligibility": dataset.get("eligible_for_publication") is True,
        "outstanding_requirements": list(dataset.get("outstanding_verification_requirements") or []),
    }


def _indicator_readiness(
    indicator: dict[str, Any],
    project_root: Path,
    *,
    mapping_row: dict[str, Any] | None = None,
    registry: dict[str, dict[str, Any]] | None = None,
    source_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    references = indicator.get("source_documentation") or []
    reference_paths = [
        item.get("path")
        for item in references
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    reference_status = "missing" if not reference_paths else (
        "present_unverified" if all(_reference_exists(project_root, path) for path in reference_paths)
        else "missing_or_unverified"
    )
    mapping_verified = (mapping_row or {}).get("mapping_status") == "verified"
    mapping_blockers = list((mapping_row or {}).get("blockers") or [])
    registered = registry or {}
    candidates = indicator.get("source_dataset_candidates") or []
    candidate_datasets = []
    for dataset in registered.values():
        dataset_names = {str(dataset.get("dataset_id", "")).casefold(), str(dataset.get("display_name", "")).casefold()}
        if any(str(candidate).casefold() in name or name in str(candidate).casefold() for candidate in candidates for name in dataset_names if candidate and name):
            candidate_datasets.append(dataset)
    if not candidate_datasets:
        candidate_datasets = [None]
    readiness_results = []
    for dataset in candidate_datasets:
        source_record = next(
            (item for item in (source_records or []) if dataset and item.get("dataset_id") == dataset.get("dataset_id")),
            None,
        )
        readiness_results.append(
            evaluate_indicator_readiness(
                indicator,
                dataset,
                available_columns=(
                    dataset.get("verified_schema_columns")
                    if isinstance(dataset, dict) and isinstance(dataset.get("verified_schema_columns"), list)
                    else None
                ),
                require_research_evidence=True,
                require_data_quality=True,
                require_calculation_specification=True,
                require_mapping_evidence=True,
                requested_geography=indicator.get("indicator_id") == "GEO-COMP-001",
                source_verification=source_record,
                source_available=bool(
                    dataset
                    and isinstance(dataset.get("source_path"), str)
                    and _registered_source_present(dataset.get("source_path"), set(current_data_file_paths(project_root)))
                ),
            )
        )
    analysis_eligible = any(result.analysis_eligible for result in readiness_results)
    publication_eligible = any(result.publication_eligible for result in readiness_results)
    methodology_approved = any(
        "approved_definition_and_methodology" in result.passed_checks
        for result in readiness_results
    )
    blockers = list(indicator.get("review_blockers") or [])
    if not mapping_verified:
        blockers.extend(mapping_blockers or ["verified codebook mapping"])
    if not methodology_approved:
        blockers.append("approved indicator methodology")
    return {
        "indicator_id": indicator.get("indicator_id"),
        "display_name": indicator.get("display_name"),
        "catalogue_status": indicator.get("status", "unavailable"),
        "mapping_status": "verified" if mapping_verified else "unverified",
        "source_documentation_status": reference_status,
        "methodology_status": "approved" if methodology_approved else "blocked",
        "analytical_eligibility": analysis_eligible,
        "publication_eligibility": publication_eligible,
        "blockers": list(dict.fromkeys([*(str(item) for item in blockers), *(message for result in readiness_results if not result.analysis_eligible for message in result.messages)])),
        "mapping_blockers": mapping_blockers,
    }


def build_research_readiness_report(
    project_root: str | Path,
    *,
    inventory: dict[str, Any] | None,
    registry: dict[str, dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    evidence: dict[str, Any] | None = None,
    source_verification: dict[str, Any] | None = None,
    geographic_resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a safe, deterministic readiness report from metadata and paths."""

    root = Path(project_root).expanduser().resolve()
    current_paths = set(current_data_file_paths(root))
    inventory_status = verify_inventory_snapshot(inventory, project_root=root)
    documentation = _documentation_summary(root, sorted(current_paths))
    geographic_assets = _geographic_asset_summary(root, current_paths)
    geographic_resources_summary = summarize_geographic_resources(
        geographic_resources or [],
        project_root=root,
    )
    datasets = [_dataset_readiness(dataset, current_paths) for dataset in registry.values()]
    evidence_items = (
        [item for item in evidence.get("items", []) if isinstance(item, dict)]
        if isinstance(evidence, dict)
        else []
    )
    evidence_summary = summarize_evidence(evidence_items)
    evidence_blockers = actionable_evidence_items(evidence_items)
    source_records = (
        [item for item in source_verification.get("sources", []) if isinstance(item, dict)]
        if isinstance(source_verification, dict)
        else []
    )
    source_summary = summarize_source_verification(source_records)
    source_summary["access_checklist"] = summarize_access_checklist(source_records, evidence_items)
    documented_codebook_references: set[str] = set()
    for dataset in registry.values():
        for reference in dataset.get("documentation_references", []) or []:
            if isinstance(reference, str) and reference.strip():
                documented_codebook_references.add(reference.split("#", 1)[0])
    for indicator in catalogue.values():
        for reference in indicator.get("source_documentation", []) or []:
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                documented_codebook_references.add(reference["path"].split("#", 1)[0])
            elif isinstance(reference, str) and reference.strip():
                documented_codebook_references.add(reference.split("#", 1)[0])
    for source in source_records:
        for reference in source.get("documentation_references", []) or []:
            if isinstance(reference, str) and reference.strip():
                documented_codebook_references.add(reference.split("#", 1)[0])
    mapping_summary = summarize_mapping_records(
        catalogue,
        dataset_ids=registry.keys(),
        codebook_references=documented_codebook_references,
    )
    evidence_by_indicator = {
        item.get("related_indicator_id"): item
        for item in evidence_items
        if item.get("category") == "variable_mapping" and item.get("related_indicator_id")
    }
    for row in mapping_summary.get("rows", []):
        evidence_item = evidence_by_indicator.get(row.get("indicator_id"))
        if evidence_item:
            row["evidence_blockers"] = [
                {
                    "evidence_id": evidence_item.get("evidence_id"),
                    "status": evidence_item.get("status"),
                    "why_it_matters": evidence_item.get("reason_for_blocking"),
                    "next_action": evidence_item.get("next_action"),
                    "blocks": evidence_item.get("blocks", []),
                }
            ]
        else:
            row["evidence_blockers"] = []
    mapping_rows_by_id = {
        row.get("indicator_id"): row
        for row in mapping_summary.get("rows", [])
        if isinstance(row, dict)
    }
    indicators = [
        _indicator_readiness(
            indicator,
            root,
            mapping_row=mapping_rows_by_id.get(indicator.get("indicator_id")),
            registry=registry,
            source_records=source_records,
        )
        for indicator in catalogue.values()
    ]
    action_plan = build_researcher_action_plan(evidence_items, source_records)
    evidence_references = sorted(
        {
            str(item["evidence_reference"])
            for item in evidence_items
            if isinstance(item.get("evidence_reference"), str) and item["evidence_reference"]
        }
    )

    all_authorized = bool(datasets) and all(
        item["authorization_status"] in {"authorized_for_analysis", "authorized_for_analysis_and_publication"}
        for item in datasets
    )
    all_provenance = bool(datasets) and all(item["provenance_status"] == "verified" for item in datasets)
    all_design = bool(datasets) and all(
        dataset.get("survey_design_status", "unverified") in {"verified", "approved"}
        for dataset in registry.values()
    )
    geographic_status = (
        "missing"
        if not geographic_assets["asset_count"] and not geographic_resources_summary["resource_count"]
        else "invalid"
        if geographic_assets["invalid_asset_count"]
        else "registered_unverified"
        if not geographic_resources_summary["verified_resource_count"]
        else "available_unverified"
        if not geographic_assets["asset_count"]
        else "available_unverified"
    )
    missing_documentation = [
        requirement
        for requirement, status in documentation["requirements"].items()
        if status == "missing"
    ]
    requirements = [
        {
            "requirement": "inventory_snapshot",
            "status": "verified" if inventory_status["status"] == "current" else inventory_status["status"],
            "next_action": "Regenerate the source inventory after confirming the approved data scope." if inventory_status["status"] != "current" else "None recorded.",
        },
        {
            "requirement": "source_provenance",
            "status": "verified" if all_provenance else "unverified",
            "next_action": "Record documentary provenance for every registered dataset." if not all_provenance else "None recorded.",
        },
        {
            "requirement": "authorization",
            "status": "verified" if all_authorized else "unverified",
            "next_action": "Record written authorization and permitted processing purpose." if not all_authorized else "None recorded.",
        },
        {
            "requirement": "documentation",
            "status": "present_unverified" if documentation["documentation_file_count"] else "missing",
            "next_action": (
                "Provide the missing documentation: " + ", ".join(missing_documentation) + "."
                if missing_documentation
                else "Review documents and link them to datasets."
            ),
        },
        {
            "requirement": "indicator_mappings",
            "status": "verified" if indicators and all(item["mapping_status"] == "verified" for item in indicators) else "unverified",
            "next_action": "Verify variable names, response coding, denominators, and questionnaire references." if not indicators or any(item["mapping_status"] != "verified" for item in indicators) else "None recorded.",
        },
        {
            "requirement": "indicator_methodology",
            "status": "verified" if indicators and all(item["methodology_status"] == "approved" for item in indicators) else "blocked",
            "next_action": "Obtain domain approval for definitions, populations, exclusions, and missing-value treatment." if not indicators or any(item["methodology_status"] != "approved" for item in indicators) else "None recorded.",
        },
        {
            "requirement": "survey_design_and_weights",
            "status": "verified" if all_design else "unverified",
            "next_action": "Document dataset-specific weights, strata, clusters, and variance methods." if not all_design else "None recorded.",
        },
        {
            "requirement": "geographic_assets",
            "status": geographic_status,
            "next_action": (
                "Provide a reviewed boundary asset and provenance metadata."
                if geographic_status == "missing"
                else "Repair invalid geographic structure before review."
                if geographic_status == "invalid"
                else "Validate source, vintage, identifiers, and licensing."
            ),
        },
        {
            "requirement": "geographic_crosswalk",
            "status": "verified" if any(
                dataset.get("geography_status") in {"verified", "approved"}
                and dataset.get("geographic_crosswalk_status") in {"verified", "approved"}
                and dataset.get("geographic_variable")
                for dataset in registry.values()
            ) else "missing",
            "next_action": "None recorded." if any(
                dataset.get("geography_status") in {"verified", "approved"}
                and dataset.get("geographic_crosswalk_status") in {"verified", "approved"}
                and dataset.get("geographic_variable")
                for dataset in registry.values()
            ) else "Document compatible geographic identifiers and an approved crosswalk before joining data.",
        },
        {
            "requirement": "publication_permission",
            "status": "verified" if all(
                item["publication_eligibility"] for item in datasets
            ) and bool(datasets) else "blocked",
            "next_action": "Record a separate publication and disclosure-risk decision." if not datasets or not all(item["publication_eligibility"] for item in datasets) else "None recorded.",
        },
    ]
    blocked = [item for item in requirements if item["status"] != "verified"]
    return {
        "report_version": 2,
        "overall_status": "ready" if not blocked and not evidence_blockers else "blocked",
        "inventory": inventory_status,
        "documentation": documentation,
        "geographic_assets": geographic_assets,
        "geographic_resources": geographic_resources_summary,
        "datasets": datasets,
        "indicators": indicators,
        "requirements": requirements,
        "ready_requirements": [item["requirement"] for item in requirements if item["status"] == "verified"],
        "blocked_requirements": [item["requirement"] for item in blocked],
        "evidence": {
            "status": "loaded" if isinstance(evidence, dict) else "unavailable",
            "register_version": evidence.get("evidence_register_version") if isinstance(evidence, dict) else None,
            "summary": evidence_summary,
            "items": evidence_items,
            "blockers": evidence_blockers,
            "references": evidence_references,
        },
        "source_verification": {
            "status": "loaded" if isinstance(source_verification, dict) else "unavailable",
            "summary": source_summary,
            "sources": source_records,
            "access_checklist": source_summary["access_checklist"],
        },
        "mapping_summary": mapping_summary,
        "researcher_action_plan": action_plan,
        "report_metadata": {
            "runtime_generation": "computed from the current metadata and approved data-path snapshot",
            "source_inventory_generated_at_utc": (
                inventory.get("generated_at_utc")
                if isinstance(inventory, dict) and isinstance(inventory.get("generated_at_utc"), str)
                else None
            ),
            "source_references": ["data/metadata/dataset_registry.json", "data/metadata/indicator_catalogue.json", "data/metadata/evidence_register.json"],
        },
        "analytical_eligibility": False,
        "publication_eligibility": False,
    }
