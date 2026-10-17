"""Evidence-derived Phase 13 source access and indicator-review report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .readiness import evaluate_indicator_readiness
from insightrwanda.data.registry import get_dataset, resolve_dataset_path
from insightrwanda.data.errors import DataPathError
from insightrwanda.data.source_verification import summarize_access_checklist


def build_phase13_status(
    project_root: str | Path,
    registry: dict[str, dict[str, Any]],
    catalogue: dict[str, dict[str, Any]],
    evidence: dict[str, Any] | None,
    source_verification: dict[str, Any] | None,
    *,
    dataset_id: str = "finscope_2024_rwanda_csv",
    indicator_id: str = "FI-ACCESS-001",
) -> dict[str, Any]:
    """Build the access checklist and derive eligibility from the shared gates."""

    source_records = (source_verification or {}).get("sources", [])
    source = next((item for item in source_records if isinstance(item, dict) and item.get("dataset_id") == dataset_id), None)
    definition = catalogue.get(indicator_id)
    dataset = get_dataset(registry, dataset_id)
    try:
        source_available = bool(dataset and resolve_dataset_path(dataset, project_root=project_root).is_file())
    except (DataPathError, OSError, ValueError):
        source_available = False
    items = (evidence or {}).get("items", [])
    checklist = summarize_access_checklist([source] if source else [], items)
    if definition and dataset:
        readiness = evaluate_indicator_readiness(
            definition,
            dataset,
            requested_geography=False,
            publication_requested=False,
            require_research_evidence=True,
            require_data_quality=True,
            require_calculation_specification=True,
            require_mapping_evidence=True,
            source_verification=source,
            source_available=source_available,
        )
    else:
        readiness = None
    review = definition.get("definition_review", {}) if definition else {}
    fields = review.get("fields", []) if isinstance(review, dict) else []
    return {
        "phase": 13,
        "status": "ready" if readiness and readiness.analysis_eligible else "blocked",
        "dataset_id": dataset_id,
        "indicator_id": indicator_id,
        "sources_identified": [
            {
                "source_id": source_row.get("source_id"),
                "source_title": source_row.get("source_title"),
                "release_identifier": source_row.get("release_version"),
                "source_organization": source_row.get("source_organization"),
                "source_references": source_row.get("source_references", []),
                "documentation_records": source_row.get("documentation_records", []),
                "documentation_review_status": source_row.get("documentation_review_status", "missing"),
                "access_authorization_status": source_row.get("access_authorization_status", "missing"),
                "analysis_approval_status": source_row.get("analysis_approval_status", "missing"),
                "publication_approval_status": source_row.get("publication_approval_status", "missing"),
            }
            for source_row in source_records if isinstance(source_row, dict)
        ],
        "access_checklist": checklist,
        "definition_review": {
            "target_release_identifier": review.get("target_release_identifier") if isinstance(review, dict) else None,
            "fields": fields,
            "field_count": len(fields),
            "verified_field_count": sum(field.get("status") == "verified" for field in fields if isinstance(field, dict)),
            "unresolved_field_count": sum(field.get("status") not in {"verified", "not_applicable"} for field in fields if isinstance(field, dict)),
        },
        "readiness": readiness.as_dict() if readiness else None,
        "analysis_eligible": bool(readiness and readiness.analysis_eligible),
        "publication_eligible": bool(readiness and readiness.publication_eligible),
        "indicator_calculated": False,
        "result": None,
        "raw_records_included": False,
    }
