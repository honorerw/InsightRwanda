"""Conservative registry for datasets that may be selected by the UI.

The registry is metadata only.  It does not discover files, grant permission,
or load a selected source.  Authorization and publication fields deliberately
default to the most restrictive state when they are absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import DataPathError, DataLoaderError
from .paths import resolve_approved_data_path


REQUIRED_FIELDS = {"dataset_id", "display_name", "source_path", "file_format"}
DEFAULTS: dict[str, Any] = {
    "source_organization": None,
    "source_title": None,
    "source_url": None,
    "acquisition_date": None,
    "integrity_sha256": None,
    "dataset_version": None,
    "provenance_status": "unverified",
    "authorization_status": "unverified",
    "permitted_processing_purpose": None,
    "license_status": "unverified",
    "documentation_status": "missing_or_unverified",
    "eligible_for_publication": False,
    "analytical_eligibility": False,
    "codebook_status": "missing_or_unverified",
    "survey_weight_status": "unverified",
    "survey_weight_variable": None,
    "survey_design_status": "unverified",
    "data_quality_status": "unverified",
    "geography_status": "unverified",
    "geographic_crosswalk_status": "unverified",
    "geographic_variable": None,
    "geographic_join_method": None,
    "geographic_level": None,
    "geographic_coverage": None,
    "geographic_boundary_release": None,
    "geographic_reference_date": None,
    "reporting_period": None,
    "limitations": ["Authorization and documentation have not been verified."],
    "documentation_references": [],
    "outstanding_verification_requirements": [
        "Document source provenance, authorization, and applicable terms of use.",
        "Link an authoritative codebook or questionnaire and survey-design documentation.",
    ],
}


def _validate_relative_source_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataLoaderError("Each dataset must have a non-empty relative source path.")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DataPathError("Dataset source paths must stay relative to the approved data directory.")
    if any(part in {"", "."} for part in candidate.parts):
        raise DataPathError("Dataset source paths must be normalized relative paths.")
    return candidate.as_posix()


def _copy_defaults(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(DEFAULTS)
    result.update(record)
    result["source_path"] = _validate_relative_source_path(result.get("source_path"))
    if not isinstance(result["dataset_id"], str) or not result["dataset_id"].strip():
        raise DataLoaderError("Each dataset must have a non-empty dataset_id.")
    if not isinstance(result["display_name"], str) or not result["display_name"].strip():
        raise DataLoaderError("Each dataset must have a non-empty display_name.")
    if not isinstance(result["file_format"], str) or not result["file_format"].strip():
        raise DataLoaderError("Each dataset must have a non-empty file_format.")
    if not isinstance(result["limitations"], list) or not all(isinstance(item, str) for item in result["limitations"]):
        raise DataLoaderError("Dataset limitations must be a list of safe text messages.")
    if not isinstance(result["documentation_references"], list) or not all(
        isinstance(item, str) for item in result["documentation_references"]
    ):
        raise DataLoaderError("Dataset documentation references must be a list of safe text references.")
    if not isinstance(result["outstanding_verification_requirements"], list) or not all(
        isinstance(item, str) for item in result["outstanding_verification_requirements"]
    ):
        raise DataLoaderError("Outstanding verification requirements must be a list of safe text references.")
    for field in (
        "source_title",
        "source_url",
        "acquisition_date",
        "integrity_sha256",
        "dataset_version",
        "geographic_join_method",
        "geographic_level",
        "geographic_coverage",
        "geographic_boundary_release",
        "geographic_reference_date",
        "reporting_period",
        "survey_weight_variable",
        "geographic_variable",
    ):
        if result[field] is not None and not isinstance(result[field], str):
            raise DataLoaderError(f"Dataset field '{field}' must be text or null.")
    result["eligible_for_publication"] = result.get("eligible_for_publication") is True
    result["analytical_eligibility"] = result.get("analytical_eligibility") is True
    return result


def load_dataset_registry(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load and validate registry metadata without accessing source files."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataLoaderError("The dataset registry could not be read safely.") from exc
    records = document.get("datasets") if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise DataLoaderError("The dataset registry must contain a datasets list.")
    registry: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not REQUIRED_FIELDS.issubset(record):
            raise DataLoaderError("Each dataset registry entry is missing required metadata.")
        normalized = _copy_defaults(record)
        dataset_id = normalized["dataset_id"]
        if dataset_id in registry:
            raise DataLoaderError("Dataset IDs must be unique.")
        registry[dataset_id] = normalized
    return registry


def get_dataset(registry: dict[str, dict[str, Any]], dataset_id: str | None) -> dict[str, Any] | None:
    """Return a dataset only when an explicit non-empty ID was supplied."""

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        return None
    return registry.get(dataset_id)


def resolve_dataset_path(
    dataset: dict[str, Any], *, project_root: str | Path | None = None
) -> Path:
    """Validate and resolve a registered source path without loading it."""

    relative_path = _validate_relative_source_path(dataset.get("source_path"))
    return resolve_approved_data_path(
        Path("data") / relative_path,
        project_root=project_root,
    )


def registry_summary(registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return safe counts without returning registry paths or source records."""

    records = list(registry.values())
    return {
        "dataset_count": len(records),
        "authorization_counts": _counts(records, "authorization_status"),
        "provenance_counts": _counts(records, "provenance_status"),
        "documentation_counts": _counts(records, "documentation_status"),
        "license_counts": _counts(records, "license_status"),
        "data_quality_counts": _counts(records, "data_quality_status"),
        "geographic_crosswalk_counts": _counts(records, "geographic_crosswalk_status"),
        "codebook_counts": _counts(records, "codebook_status"),
        "analytical_eligibility_counts": _counts(records, "analytical_eligibility"),
        "publication_eligibility_counts": _counts(records, "eligible_for_publication"),
    }


def _counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field, "unavailable"))
        counts[value] = counts.get(value, 0) + 1
    return counts
