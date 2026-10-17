"""Metadata helpers for registered geographic resources.

The registry is deliberately separate from the geometry and analytical
validators: registration records what a reviewer says should be considered,
while the validators establish whether the resource is present, structurally
usable, provenance-reviewed, and permitted for the requested use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import DataLoaderError, DataPathError


_STATUS_FIELDS = (
    "provenance_status",
    "license_status",
    "permitted_use_status",
    "verification_status",
    "publication_status",
)
_VERIFIED_STATUSES = {"verified", "approved"}


def _safe_relative_path(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DataLoaderError("Geographic source_path must be text or null.")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or any(part in {"", "."} for part in candidate.parts):
        raise DataPathError("Geographic source_path must remain a normalized relative path.")
    return candidate.as_posix()


def _safe_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DataLoaderError("Geographic source_url must be an absolute HTTP or HTTPS URL.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DataLoaderError("Geographic source_url must be an absolute HTTP or HTTPS URL.")
    return value.strip()


def normalize_geographic_resource(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a registry record without treating it as verified."""

    if not isinstance(record, dict) or not isinstance(record.get("resource_id"), str) or not record["resource_id"].strip():
        raise DataLoaderError("Each geographic resource requires a non-empty resource_id.")
    normalized = {
        "resource_id": record["resource_id"].strip(),
        "display_name": record.get("display_name") or record["resource_id"].strip(),
        "source_url": _safe_url(record.get("source_url")),
        "producing_organization": record.get("producing_organization"),
        "administrative_level": record.get("administrative_level"),
        "boundary_release": record.get("boundary_release"),
        "reference_date": record.get("reference_date"),
        "coordinate_reference_system": record.get("coordinate_reference_system"),
        "feature_id_field": record.get("feature_id_field"),
        "feature_name_field": record.get("feature_name_field"),
        "admin_level_field": record.get("admin_level_field"),
        "geometry_types": list(record.get("geometry_types") or []),
        "source_path": _safe_relative_path(record.get("source_path")),
        "source_checksum": record.get("source_checksum"),
        "license_status": record.get("license_status", "unverified"),
        "permitted_use_status": record.get("permitted_use_status", "unverified"),
        "provenance_status": record.get("provenance_status", "unverified"),
        "verification_status": record.get("verification_status", "unverified"),
        "publication_status": record.get("publication_status", "not_approved"),
        "intended_use": record.get("intended_use"),
        "limitations": list(record.get("limitations") or []),
        "evidence_references": list(record.get("evidence_references") or []),
        "disclosure_requirements": record.get("disclosure_requirements"),
    }
    if not isinstance(normalized["display_name"], str) or not normalized["display_name"].strip():
        raise DataLoaderError("Geographic display_name must be non-empty text.")
    for field in (
        "producing_organization",
        "administrative_level",
        "boundary_release",
        "reference_date",
        "coordinate_reference_system",
        "feature_id_field",
        "feature_name_field",
        "admin_level_field",
        "source_checksum",
        "intended_use",
    ):
        value = normalized[field]
        if value is not None and not isinstance(value, str):
            raise DataLoaderError(f"Geographic resource field '{field}' must be text or null.")
    if not isinstance(normalized["geometry_types"], list) or not all(isinstance(item, str) and item for item in normalized["geometry_types"]):
        raise DataLoaderError("Geographic geometry_types must be a list of non-empty text values.")
    for field in _STATUS_FIELDS:
        if not isinstance(normalized[field], str) or not normalized[field].strip():
            raise DataLoaderError(f"Geographic resource field '{field}' must be a non-empty status.")
    if not all(isinstance(item, str) and item.strip() for item in normalized["limitations"]):
        raise DataLoaderError("Geographic limitations must be a list of text.")
    if not all(isinstance(item, str) and item.strip() for item in normalized["evidence_references"]):
        raise DataLoaderError("Geographic evidence_references must be a list of text.")
    return normalized


def load_geographic_resource_registry(path: str | Path) -> list[dict[str, Any]]:
    """Load geographic resource metadata without opening geometry files."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataLoaderError("The geographic resource registry could not be read safely.") from exc
    records = document.get("resources") if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise DataLoaderError("The geographic resource registry must contain a resources list.")
    result = []
    seen: set[str] = set()
    for record in records:
        normalized = normalize_geographic_resource(record)
        if normalized["resource_id"] in seen:
            raise DataLoaderError("Geographic resource IDs must be unique.")
        seen.add(normalized["resource_id"])
        result.append(normalized)
    return result


def summarize_geographic_resources(
    resources: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return status counts and safe resource records for dashboard readiness."""

    root = Path(project_root).resolve() if project_root is not None else None
    rows: list[dict[str, Any]] = []
    for resource in resources:
        source_path = resource.get("source_path")
        present = False
        if root is not None and isinstance(source_path, str):
            candidate = (root / "data" / source_path).resolve(strict=False)
            data_root = (root / "data").resolve()
            try:
                candidate.relative_to(data_root)
                present = candidate.is_file()
            except ValueError:
                present = False
        rows.append(
            {
                "resource_id": resource.get("resource_id"),
                "display_name": resource.get("display_name"),
                "administrative_level": resource.get("administrative_level"),
                "boundary_release": resource.get("boundary_release"),
                "reference_date": resource.get("reference_date"),
                "coordinate_reference_system": resource.get("coordinate_reference_system"),
                "verification_status": resource.get("verification_status", "unverified"),
                "license_status": resource.get("license_status", "unverified"),
                "permitted_use_status": resource.get("permitted_use_status", "unverified"),
                "publication_status": resource.get("publication_status", "not_approved"),
                "local_presence": "present" if present else "missing",
                "evidence_reference_count": len(resource.get("evidence_references") or []),
                "limitations": list(resource.get("limitations") or []),
            }
        )
    return {
        "resource_count": len(rows),
        "verified_resource_count": sum(item["verification_status"] in _VERIFIED_STATUSES for item in rows),
        "locally_present_count": sum(item["local_presence"] == "present" for item in rows),
        "publication_approved_count": sum(item["publication_status"] in _VERIFIED_STATUSES for item in rows),
        "resources": rows,
    }
