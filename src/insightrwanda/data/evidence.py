"""Validated metadata for evidence required by research-readiness gates.

The evidence register records what must be provided and reviewed.  It does
not verify documents, grant authorization, or change analytical and
publication eligibility.  Verification remains an explicit human decision
recorded in metadata outside the Streamlit runtime.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .errors import DataLoaderError


EVIDENCE_STATUSES = {
    "missing",
    "provided_unverified",
    "verified",
    "rejected",
    "not_applicable",
}
EVIDENCE_CATEGORIES = {
    "dataset_provenance",
    "authorization",
    "licensing",
    "documentation",
    "variable_mapping",
    "indicator_methodology",
    "survey_design",
    "geography",
    "data_quality",
    "disclosure_publication",
}
SATISFYING_STATUSES = {"verified", "not_applicable"}
REQUIRED_FIELDS = {
    "evidence_id",
    "category",
    "description",
    "status",
    "mandatory",
    "reason_for_blocking",
    "next_action",
}


def _safe_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise DataLoaderError(f"Evidence field '{field}' must be a single non-empty line of text.")
    return value.strip()


def _safe_reference(value: Any) -> str | None:
    reference = _safe_text(value, "evidence_reference")
    if reference is None:
        return None
    path = Path(reference)
    if path.is_absolute() or ".." in path.parts or reference.startswith("~"):
        raise DataLoaderError("Evidence references must not contain absolute or parent-traversal paths.")
    return reference


def _normalize_item(
    item: Any,
    *,
    dataset_ids: set[str] | None,
    indicator_ids: set[str] | None,
) -> dict[str, Any]:
    if not isinstance(item, dict) or not REQUIRED_FIELDS.issubset(item):
        raise DataLoaderError("Each evidence item is missing required metadata fields.")
    evidence_id = _safe_text(item.get("evidence_id"), "evidence_id", required=True)
    category = _safe_text(item.get("category"), "category", required=True)
    status = _safe_text(item.get("status"), "status", required=True)
    if category not in EVIDENCE_CATEGORIES:
        raise DataLoaderError("Evidence item category is not supported.")
    if status not in EVIDENCE_STATUSES:
        raise DataLoaderError("Evidence item status is not supported.")
    if not isinstance(item.get("mandatory"), bool):
        raise DataLoaderError("Evidence item mandatory must be a boolean.")

    normalized: dict[str, Any] = {
        "evidence_id": evidence_id,
        "category": category,
        "related_dataset_id": _safe_text(item.get("related_dataset_id"), "related_dataset_id"),
        "related_indicator_id": _safe_text(item.get("related_indicator_id"), "related_indicator_id"),
        "related_resource_id": _safe_text(item.get("related_resource_id"), "related_resource_id"),
        "description": _safe_text(item.get("description"), "description", required=True),
        "status": status,
        "evidence_reference": _safe_reference(item.get("evidence_reference")),
        "source_organization": _safe_text(item.get("source_organization"), "source_organization"),
        "verification_date": _safe_text(item.get("verification_date"), "verification_date"),
        "reviewer": _safe_text(item.get("reviewer"), "reviewer"),
        "reason_for_blocking": _safe_text(item.get("reason_for_blocking"), "reason_for_blocking", required=True),
        "next_action": _safe_text(item.get("next_action"), "next_action", required=True),
        "mandatory": item["mandatory"],
        "blocks": [],
    }
    blocks = item.get("blocks", [])
    if not isinstance(blocks, list) or not all(isinstance(scope, str) and scope.strip() for scope in blocks):
        raise DataLoaderError("Evidence item blocks must be a list of safe scope labels.")
    normalized["blocks"] = list(dict.fromkeys(scope.strip() for scope in blocks))

    related_dataset_id = normalized["related_dataset_id"]
    if related_dataset_id and dataset_ids is not None and related_dataset_id not in dataset_ids:
        raise DataLoaderError("Evidence item references an unknown dataset ID.")
    related_indicator_id = normalized["related_indicator_id"]
    if related_indicator_id and indicator_ids is not None and related_indicator_id not in indicator_ids:
        raise DataLoaderError("Evidence item references an unknown indicator ID.")
    return normalized


def validate_evidence_register(
    document: Any,
    *,
    dataset_ids: Iterable[str] | None = None,
    indicator_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate and normalize a register without reading referenced files."""

    if not isinstance(document, dict) or not isinstance(document.get("items"), list):
        raise DataLoaderError("The evidence register must contain an items list.")
    known_dataset_ids = set(dataset_ids) if dataset_ids is not None else None
    known_indicator_ids = set(indicator_ids) if indicator_ids is not None else None
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in document["items"]:
        record = _normalize_item(item, dataset_ids=known_dataset_ids, indicator_ids=known_indicator_ids)
        if record["evidence_id"] in seen:
            raise DataLoaderError("Evidence IDs must be unique.")
        seen.add(record["evidence_id"])
        normalized.append(record)
    return normalized


def load_evidence_register(
    path: str | Path,
    *,
    dataset_ids: Iterable[str] | None = None,
    indicator_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Load a safe evidence register and return normalized metadata only."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataLoaderError("The evidence register could not be read safely.") from exc
    items = validate_evidence_register(
        document,
        dataset_ids=dataset_ids,
        indicator_ids=indicator_ids,
    )
    return {
        "evidence_register_version": document.get("evidence_register_version", 1),
        "purpose": document.get("purpose", "Research-readiness evidence metadata."),
        "items": items,
    }


def summarize_evidence(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate evidence statuses and blocking scopes for safe display."""

    records = [item for item in items if isinstance(item, dict)]
    status_counts = Counter(str(item.get("status", "unavailable")) for item in records)
    category_counts = Counter(str(item.get("category", "unavailable")) for item in records)
    blockers = [
        item
        for item in records
        if item.get("mandatory") is True and item.get("status") not in SATISFYING_STATUSES
    ]
    scope_counts = Counter(
        scope
        for item in blockers
        for scope in item.get("blocks", [])
        if isinstance(scope, str)
    )
    return {
        "total": len(records),
        "verified": status_counts.get("verified", 0),
        "missing": status_counts.get("missing", 0),
        "provided_unverified": status_counts.get("provided_unverified", 0),
        "rejected": status_counts.get("rejected", 0),
        "not_applicable": status_counts.get("not_applicable", 0),
        "blocked": len(blockers),
        "analysis_blocking": scope_counts.get("analysis", 0),
        "geography_blocking": scope_counts.get("geography", 0),
        "publication_blocking": scope_counts.get("publication", 0),
        "category_counts": dict(sorted(category_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
    }


def actionable_evidence_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return safe, deterministic blocker records for the Evidence Center."""

    blockers = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("mandatory") is True
        and item.get("status") not in SATISFYING_STATUSES
    ]
    return sorted(blockers, key=lambda item: str(item.get("evidence_id", "")))
