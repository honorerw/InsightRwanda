"""Safe, aggregate metadata adapters used by the dashboard.

This module intentionally reads only JSON metadata and never discovers or
loads source datasets. It exposes summaries rather than inventory paths,
column values, or row-level records.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from insightrwanda.analytics.catalogue import load_indicator_catalogue
from insightrwanda.analytics.readiness import ReadinessResult, evaluate_indicator_readiness
from insightrwanda.data.registry import get_dataset, load_dataset_registry, resolve_dataset_path
from insightrwanda.data.errors import DataPathError
from insightrwanda.data.evidence import load_evidence_register
from insightrwanda.data.geography import load_geographic_resource_registry
from insightrwanda.data.source_verification import load_source_verification_matrix
from insightrwanda.data.research_readiness import build_research_readiness_report


@dataclass(frozen=True)
class DashboardMetadata:
    """Aggregate metadata required to render safe readiness states."""

    catalogue: dict[str, dict[str, Any]]
    catalogue_error: str | None
    inventory: dict[str, Any] | None
    inventory_error: str | None
    registry: dict[str, dict[str, Any]]
    registry_error: str | None
    evidence: dict[str, Any] | None = None
    evidence_error: str | None = None
    source_verification: dict[str, Any] | None = None
    source_verification_error: str | None = None
    research_readiness: dict[str, Any] | None = None
    research_readiness_error: str | None = None
    project_root: Path | None = None
    geographic_resources: tuple[dict[str, Any], ...] = ()
    geographic_resources_error: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("JSON document must be an object")
    return document


def load_dashboard_metadata(project_root: str | Path) -> DashboardMetadata:
    """Load catalogue and inventory summaries without touching source data."""

    root = Path(project_root).resolve()
    catalogue_path = root / "data" / "metadata" / "indicator_catalogue.json"
    try:
        catalogue = load_indicator_catalogue(catalogue_path)
        catalogue_error = None
    except Exception:
        catalogue = {}
        catalogue_error = "The indicator catalogue is missing or could not be validated."

    inventory_path = root / "artifacts" / "source_inventory.json"
    try:
        inventory = _read_json(inventory_path)
        inventory_error = None
    except (OSError, ValueError, json.JSONDecodeError):
        inventory = None
        inventory_error = "The source inventory is unavailable or malformed."

    registry_path = root / "data" / "metadata" / "dataset_registry.json"
    try:
        registry = load_dataset_registry(registry_path)
        registry_error = None
    except Exception:
        registry = {}
        registry_error = "The dataset registry is unavailable or malformed."

    evidence_path = root / "data" / "metadata" / "evidence_register.json"
    try:
        evidence = load_evidence_register(
            evidence_path,
            dataset_ids=registry.keys(),
            indicator_ids=catalogue.keys(),
        )
        evidence_error = None
    except Exception:
        evidence = None
        evidence_error = "The evidence register is unavailable or malformed."

    source_verification_path = root / "data" / "metadata" / "source_verification.json"
    try:
        source_verification = load_source_verification_matrix(
            source_verification_path,
            dataset_ids=registry.keys(),
            project_root=root,
        )
        source_verification_error = None
    except Exception:
        source_verification = None
        source_verification_error = "The source-verification matrix is unavailable or malformed."

    geographic_resources_path = root / "data" / "metadata" / "geographic_resources.json"
    try:
        geographic_resources = tuple(load_geographic_resource_registry(geographic_resources_path))
        geographic_resources_error = None
    except Exception:
        geographic_resources = ()
        geographic_resources_error = "The geographic resource registry is unavailable or malformed."

    try:
        research_readiness = build_research_readiness_report(
            root,
            inventory=inventory,
            registry=registry,
            catalogue=catalogue,
            evidence=evidence,
            source_verification=source_verification,
            geographic_resources=list(geographic_resources),
        )
        research_readiness_error = None
    except Exception:
        research_readiness = None
        research_readiness_error = "Research-readiness metadata could not be validated."

    return DashboardMetadata(
        catalogue=catalogue,
        catalogue_error=catalogue_error,
        inventory=inventory,
        inventory_error=inventory_error,
        registry=registry,
        registry_error=registry_error,
        evidence=evidence,
        evidence_error=evidence_error,
        source_verification=source_verification,
        source_verification_error=source_verification_error,
        research_readiness=research_readiness,
        research_readiness_error=research_readiness_error,
        project_root=root,
        geographic_resources=geographic_resources,
        geographic_resources_error=geographic_resources_error,
    )


def evaluate_catalogue_indicator(
    metadata: DashboardMetadata,
    definition: dict[str, Any],
    *,
    dataset_id: str | None = None,
    requested_geography: bool = False,
    publication_requested: bool = False,
    geographic_resource_status: str | None = None,
    geographic_resource_publication_status: str | None = None,
) -> ReadinessResult:
    """Evaluate one catalogue entry against only explicitly selected metadata."""

    source_record = next(
        (
            source
            for source in (metadata.source_verification or {}).get("sources", [])
            if isinstance(source, dict) and source.get("dataset_id") == dataset_id
        ),
        None,
    )

    dataset = get_dataset(metadata.registry, dataset_id)
    try:
        source_available = bool(
            dataset
            and metadata.project_root
            and resolve_dataset_path(dataset, project_root=metadata.project_root).is_file()
        )
    except (DataPathError, OSError, ValueError):
        source_available = False
    return evaluate_indicator_readiness(
        definition,
        dataset,
        requested_geography=requested_geography,
        publication_requested=publication_requested,
        require_research_evidence=True,
        require_data_quality=True,
        require_calculation_specification=True,
        require_mapping_evidence=True,
        source_verification=source_record,
        source_available=source_available,
        geographic_resource_status=geographic_resource_status,
        geographic_resource_publication_status=geographic_resource_publication_status,
    )


def catalogue_readiness_summary(
    metadata: DashboardMetadata, *, dataset_id: str | None = None, requested_geography: bool = False
) -> dict[str, int]:
    """Summarize readiness statuses without calculating any indicator values."""

    results = [
        evaluate_catalogue_indicator(
            metadata,
            definition,
            dataset_id=dataset_id,
            requested_geography=requested_geography,
        )
        for definition in metadata.catalogue.values()
    ]
    return {
        "indicator_count": len(results),
        "analysis_eligible_count": sum(result.analysis_eligible for result in results),
        "publication_eligible_count": sum(result.publication_eligible for result in results),
        "blocked_count": sum(not result.analysis_eligible for result in results),
    }


def catalogue_summary(catalogue: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return display-safe counts and status groupings for indicator definitions."""

    definitions = list(catalogue.values())
    status_counts = Counter(str(item.get("status", "unknown")) for item in definitions)
    authorization_counts = Counter(str(item.get("authorization_status", "unknown")) for item in definitions)
    publication_counts = Counter(str(item.get("publication_status", "unknown")) for item in definitions)
    verified_mappings = sum(
        bool(item.get("required_variables"))
        and item.get("evidence_status") in {"verified_codebook_mapping", "officially_documented"}
        for item in definitions
    )
    blockers = sum(bool(item.get("review_blockers")) for item in definitions)
    return {
        "indicator_count": len(definitions),
        "status_counts": dict(status_counts),
        "authorization_counts": dict(authorization_counts),
        "publication_counts": dict(publication_counts),
        "verified_mapping_count": int(verified_mappings),
        "indicators_with_review_blockers": int(blockers),
    }


def inventory_summary(inventory: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reduce inventory JSON to aggregate values suitable for the UI."""

    if not isinstance(inventory, dict):
        return None
    files = inventory.get("files")
    if not isinstance(files, list):
        return None
    formats = Counter(str(item.get("format", "unknown")) for item in files if isinstance(item, dict))
    authorization = Counter(str(item.get("authorization_status", "unknown")) for item in files if isinstance(item, dict))
    publication = Counter(str(item.get("eligible_for_publication", "unknown")) for item in files if isinstance(item, dict))
    return {
        "file_count": int(inventory.get("file_count", len(files))),
        "duplicate_checksum_group_count": int(inventory.get("duplicate_checksum_group_count", 0)),
        "formats": dict(formats),
        "authorization_counts": dict(authorization),
        "publication_counts": dict(publication),
    }


def status_label(status: str | None) -> tuple[str, str]:
    """Map catalogue status to a readable label and CSS class."""

    labels = {
        "officially_documented": ("Documented", "ready"),
        "derived_from_verified_variables": ("Verified mapping", "ready"),
        "proposed_pending_review": ("Proposed · review required", "blocked"),
        "blocked_pending_evidence": ("Blocked · evidence required", "blocked"),
    }
    return labels.get(status or "", ("Status unavailable", "neutral"))
