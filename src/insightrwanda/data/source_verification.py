"""Source-verification matrix and researcher action-plan helpers.

This module records references found during source research separately from
authorization and indicator readiness.  A public landing page can support
source identity or document discovery, but it cannot by itself authorize
microdata analysis or establish a variable's conceptual meaning.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .errors import DataLoaderError
from .paths import resolve_approved_data_path
from .evidence import EVIDENCE_STATUSES


SOURCE_REQUIRED_FIELDS = {
    "source_id",
    "dataset_id",
    "candidate_dataset_name",
    "source_title",
    "source_organization",
    "source_references",
    "verification_status",
    "unresolved_questions",
    "next_actions",
    "manual_verification_required",
}

# These dimensions intentionally use the evidence-register vocabulary. They
# are separate because a public reference, reviewed documentation, access
# authorization, analytical approval, and publication approval are different
# decisions made by different reviewers.
SOURCE_STATUS_FIELDS = (
    "source_reference_status",
    "documentation_status",
    "documentation_review_status",
    "source_information_status",
    "access_authorization_status",
    "analysis_approval_status",
    "publication_approval_status",
)
SATISFYING_STATUSES = {"verified", "not_applicable"}


def _status(value: Any, field: str, *, default: str) -> str:
    normalized = default if value is None else _text(value, field, required=True)
    if normalized not in EVIDENCE_STATUSES:
        raise DataLoaderError(f"Source verification field '{field}' has an unsupported status.")
    return normalized


def source_verification_blockers(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Return dimension-specific source blockers from normalized metadata."""

    definitions = {
        "source_reference_status": {
            "label": "source reference discovery and review",
            "why_it_matters": "A discovered URL supports research direction but does not independently verify the source release.",
            "blocks": ["analysis", "geography", "publication"],
            "next_action": "Review the cited official reference and record the source identity, release, and reviewer.",
        },
        "documentation_status": {
            "label": "documentation obtained",
            "why_it_matters": "A codebook, questionnaire, or methodology document is needed to establish the documented source scope.",
            "blocks": ["analysis", "publication"],
            "next_action": "Obtain the authoritative codebook, questionnaire, and methodology documents through the approved channel.",
        },
        "documentation_review_status": {
            "label": "documentation review",
            "why_it_matters": "Presence of a document does not show that its variables, coding, universe, or weights were reviewed.",
            "blocks": ["analysis", "publication"],
            "next_action": "Review the documentation and record the relevant sections, reviewer, date, and limitations.",
        },
        "source_information_status": {
            "label": "source information verification",
            "why_it_matters": "The local or intended dataset has not been matched to an authoritative source record and release.",
            "blocks": ["analysis", "geography", "publication"],
            "next_action": "Match the intended or local file to an authoritative release without exposing source records.",
        },
        "access_authorization_status": {
            "label": "data access authorization",
            "why_it_matters": "Public discoverability does not grant permission to analyze or process microdata.",
            "blocks": ["analysis", "publication"],
            "next_action": "Record written authorization, permitted processing purpose, and responsible source owner.",
        },
        "analysis_approval_status": {
            "label": "dataset approval for analysis",
            "why_it_matters": "The project must approve the exact dataset and analytical purpose after provenance and access review.",
            "blocks": ["analysis", "geography"],
            "next_action": "Complete the dataset-specific analytical eligibility review; do not infer approval from a registry entry.",
        },
        "publication_approval_status": {
            "label": "output approval for publication",
            "why_it_matters": "Analytical access is separate from licensing, disclosure-risk, attribution, and publication permission.",
            "blocks": ["publication"],
            "next_action": "Record a separate publication and disclosure review for the intended aggregate output.",
        },
    }
    blockers = []
    for field in SOURCE_STATUS_FIELDS:
        status = source.get(field, "missing")
        if status in SATISFYING_STATUSES:
            continue
        detail = definitions[field]
        blockers.append(
            {
                "dimension": field,
                "requirement": detail["label"],
                "status": status,
                "why_it_matters": detail["why_it_matters"],
                "next_action": detail["next_action"],
                "blocks": list(detail["blocks"]),
                "evidence_needed": source.get("unresolved_questions", []),
            }
        )
    return blockers


def _text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise DataLoaderError(f"Source verification field '{field}' must be safe single-line text.")
    return value.strip()


def _url(value: Any) -> str:
    url = _text(value, "url", required=True)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DataLoaderError("Source references must use an absolute HTTP or HTTPS URL.")
    return url


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise DataLoaderError(f"Source verification field '{field}' must be a list of safe text.")
    return list(dict.fromkeys(item.strip() for item in value))


SOURCE_TYPES = {"catalogue", "report", "questionnaire", "codebook", "methodology", "microdata", "terms_of_use", "other"}


def _normalize_source_reference(reference: Any) -> dict[str, Any]:
    if not isinstance(reference, dict):
        raise DataLoaderError("Each source reference must be an object.")
    status = _text(reference.get("status"), "source reference status", required=True)
    if status not in EVIDENCE_STATUSES:
        raise DataLoaderError("Source reference status is not supported.")
    kind = reference.get("source_type", "other")
    if kind not in SOURCE_TYPES:
        raise DataLoaderError("Source reference source_type is not supported.")
    checked = _text(reference.get("last_checked"), "source reference last_checked")
    if checked:
        try:
            date.fromisoformat(checked)
        except ValueError as exc:
            raise DataLoaderError("Source reference last_checked must be an ISO date.") from exc
    applicability = reference.get("exact_release_applicability", "missing")
    if applicability not in EVIDENCE_STATUSES:
        raise DataLoaderError("Source reference exact-release status is not supported.")
    return {
        "label": _text(reference.get("label"), "source reference label", required=True),
        "url": _url(reference.get("url")),
        "supports": _text(reference.get("supports"), "source reference supports", required=True),
        "status": status,
        "source_type": kind,
        "release_identifier": _text(reference.get("release_identifier"), "source reference release_identifier"),
        "exact_release_applicability": applicability,
        "last_checked": checked,
    }


def _normalize_access_checklist(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DataLoaderError("access_checklist must be a list.")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise DataLoaderError("Each access checklist item must be an object.")
        item_id = _text(item.get("check_id"), "check_id", required=True)
        status = _text(item.get("status"), "check status", required=True)
        if item_id in seen or status not in EVIDENCE_STATUSES:
            raise DataLoaderError("Access checklist IDs must be unique and statuses supported.")
        seen.add(item_id)
        references = item.get("evidence_references", [])
        if not isinstance(references, list) or not all(isinstance(ref, str) and ref.strip() for ref in references):
            raise DataLoaderError("Access checklist evidence_references must be text references.")
        status_field = item.get("source_status_field")
        if status_field is not None and status_field not in SOURCE_STATUS_FIELDS:
            raise DataLoaderError("Access checklist source_status_field is unsupported.")
        result.append({
            "check_id": item_id,
            "label": _text(item.get("label"), "check label", required=True),
            "status": status,
            "evidence_needed": _text(item.get("evidence_needed"), "evidence_needed", required=True),
            "responsible_action": _text(item.get("responsible_action"), "responsible_action", required=True),
            "next_action": _text(item.get("next_action"), "next_action", required=True),
            "evidence_references": list(references),
            "source_status_field": status_field,
        })
    return result


def _normalize_document_records(
    value: Any, *, expected_release: str | None, project_root: str | Path | None
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DataLoaderError("documentation_records must be a list.")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise DataLoaderError("Each documentation record must be an object.")
        doc_id = _text(item.get("document_id"), "document_id", required=True)
        path = _text(item.get("path"), "document path", required=True)
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "data":
            raise DataLoaderError("Local documentation paths must remain relative to the approved data directory.")
        if project_root is not None:
            try:
                resolve_approved_data_path(relative, project_root=project_root)
            except Exception as exc:
                raise DataLoaderError("Registered local documentation must resolve to a file inside the approved data directory.") from exc
        checksum = _text(item.get("sha256"), "document sha256")
        if checksum and not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
            raise DataLoaderError("Document checksums must be SHA-256 hex digests.")
        statuses = {}
        for field in ("status", "exact_release_status", "review_status"):
            statuses[field] = _text(item.get(field, "missing"), field, required=True)
            if statuses[field] not in EVIDENCE_STATUSES:
                raise DataLoaderError(f"Documentation field {field} has an unsupported status.")
        release_identifier = _text(item.get("release_identifier"), "document release_identifier")
        document_type = _text(item.get("document_type"), "document_type", required=True)
        if document_type not in SOURCE_TYPES - {"catalogue", "microdata"}:
            raise DataLoaderError("Documentation record has an unsupported document_type.")
        if statuses["exact_release_status"] == "verified" and (not expected_release or release_identifier != expected_release):
            raise DataLoaderError("Exact-release documentation status conflicts with the registered source release.")
        if statuses["review_status"] == "verified" and (statuses["status"] != "verified" or statuses["exact_release_status"] != "verified"):
            raise DataLoaderError("Document review cannot be verified until the document and exact-release applicability are verified.")
        reviewer = _text(item.get("reviewer"), "document reviewer")
        review_date = _text(item.get("review_date"), "document review_date")
        if statuses["review_status"] == "verified":
            if not reviewer or not review_date or not checksum:
                raise DataLoaderError("Verified document review requires reviewer, review date, and an integrity checksum.")
            try:
                date.fromisoformat(review_date)
            except ValueError as exc:
                raise DataLoaderError("Document review_date must be an ISO date.") from exc
        if doc_id in seen:
            raise DataLoaderError("Documentation record IDs must be unique per source.")
        seen.add(doc_id)
        result.append({
            "document_id": doc_id,
            "document_type": document_type,
            "path": relative.as_posix(),
            "release_identifier": release_identifier,
            "status": statuses["status"],
            "exact_release_status": statuses["exact_release_status"],
            "review_status": statuses["review_status"],
            "sha256": checksum,
            "reviewer": reviewer,
            "review_date": review_date,
        })
    return result


def _normalize_source(
    record: Any,
    *,
    dataset_ids: set[str] | None,
    project_root: str | Path | None,
) -> dict[str, Any]:
    if not isinstance(record, dict) or not SOURCE_REQUIRED_FIELDS.issubset(record):
        raise DataLoaderError("Each source verification record is missing required fields.")
    source_id = _text(record.get("source_id"), "source_id", required=True)
    dataset_id = _text(record.get("dataset_id"), "dataset_id")
    candidate_name = _text(record.get("candidate_dataset_name"), "candidate_dataset_name")
    if not dataset_id and not candidate_name:
        raise DataLoaderError("A source record must identify a registered dataset or candidate dataset.")
    if dataset_id and dataset_ids is not None and dataset_id not in dataset_ids:
        raise DataLoaderError("Source verification references an unknown registered dataset.")
    verification_status = _text(record.get("verification_status"), "verification_status", required=True)
    if verification_status not in EVIDENCE_STATUSES:
        raise DataLoaderError("Source verification status is not supported.")
    if not isinstance(record.get("manual_verification_required"), bool):
        raise DataLoaderError("manual_verification_required must be a boolean.")

    references = record.get("source_references")
    if not isinstance(references, list):
        raise DataLoaderError("source_references must be a list.")
    normalized_references: list[dict[str, Any]] = []
    for reference in references:
        normalized_references.append(_normalize_source_reference(reference))

    reference_status = _status(
        record.get("source_reference_status"),
        "source_reference_status",
        default="provided_unverified" if normalized_references else "missing",
    )
    documentation_status = _status(
        record.get("documentation_status"),
        "documentation_status",
        default="provided_unverified" if record.get("documentation_references") else "missing",
    )
    documentation_review_status = _status(
        record.get("documentation_review_status"),
        "documentation_review_status",
        default="missing",
    )
    source_information_status = _status(
        record.get("source_information_status"),
        "source_information_status",
        default=verification_status,
    )
    access_authorization_status = _status(
        record.get("access_authorization_status"),
        "access_authorization_status",
        default="missing",
    )
    analysis_approval_status = _status(
        record.get("analysis_approval_status"),
        "analysis_approval_status",
        default="missing",
    )
    publication_approval_status = _status(
        record.get("publication_approval_status"),
        "publication_approval_status",
        default="missing",
    )
    if source_information_status != verification_status:
        raise DataLoaderError("source_information_status must match the legacy verification_status field.")
    if not normalized_references and reference_status == "verified":
        raise DataLoaderError("A source cannot have verified reference status without a source reference.")
    if reference_status == "verified" and any(
        reference.get("status") not in SATISFYING_STATUSES for reference in normalized_references
    ):
        raise DataLoaderError("Source reference status cannot be verified while a cited reference is unverified.")
    if not record.get("documentation_references") and documentation_status == "verified":
        raise DataLoaderError("Documentation cannot be verified without a documentation reference.")
    if documentation_review_status == "verified" and documentation_status != "verified":
        raise DataLoaderError("Documentation review cannot be verified before documentation is verified.")
    if analysis_approval_status == "verified" and access_authorization_status != "verified":
        raise DataLoaderError("Analytical approval requires verified access authorization.")
    if analysis_approval_status == "verified" and not dataset_id:
        raise DataLoaderError("Analytical approval requires a registered dataset ID.")
    if access_authorization_status == "verified" and _text(record.get("permission_status"), "permission_status") not in {"verified", "approved"}:
        raise DataLoaderError("Access authorization status conflicts with the legacy permission status.")
    if publication_approval_status == "verified" and analysis_approval_status != "verified":
        raise DataLoaderError("Publication approval requires verified analytical approval.")
    if publication_approval_status == "verified" and _text(record.get("license_status"), "license_status") not in {"verified", "approved"}:
        raise DataLoaderError("Publication approval requires verified legacy license or terms status.")

    source_last_checked = _text(record.get("last_checked"), "last_checked")
    if source_last_checked:
        try:
            date.fromisoformat(source_last_checked)
        except ValueError as exc:
            raise DataLoaderError("Source last_checked must be an ISO date.") from exc
    normalized = {
        "source_id": source_id,
        "dataset_id": dataset_id,
        "candidate_dataset_name": candidate_name,
        "source_title": _text(record.get("source_title"), "source_title"),
        "source_organization": _text(record.get("source_organization"), "source_organization"),
        "release_version": _text(record.get("release_version"), "release_version"),
        "last_checked": source_last_checked,
        "collection_period": _text(record.get("collection_period"), "collection_period"),
        "unit_of_analysis": _text(record.get("unit_of_analysis"), "unit_of_analysis"),
        "target_population": _text(record.get("target_population"), "target_population"),
        "geographic_coverage": _text(record.get("geographic_coverage"), "geographic_coverage"),
        "source_references": normalized_references,
        "access_checklist": _normalize_access_checklist(record.get("access_checklist")),
        "documentation_records": _normalize_document_records(
            record.get("documentation_records"), expected_release=_text(record.get("release_version"), "release_version"),
            project_root=project_root,
        ),
        "source_reference_status": reference_status,
        "documentation_references": _text_list(record.get("documentation_references", []), "documentation_references"),
        "documentation_status": documentation_status,
        "documentation_review_status": documentation_review_status,
        "survey_methodology_references": _text_list(record.get("survey_methodology_references", []), "survey_methodology_references"),
        "sampling_weighting_status": _text(record.get("sampling_weighting_status"), "sampling_weighting_status"),
        "access_requirements": _text(record.get("access_requirements"), "access_requirements"),
        "access_method": _text(record.get("access_method"), "access_method"),
        "permission_status": _text(record.get("permission_status"), "permission_status") or "unverified",
        "license_status": _text(record.get("license_status"), "license_status") or "unverified",
        "geographic_references": _text_list(record.get("geographic_references", []), "geographic_references"),
        "verification_status": verification_status,
        "source_information_status": source_information_status,
        "access_authorization_status": access_authorization_status,
        "analysis_approval_status": analysis_approval_status,
        "publication_approval_status": publication_approval_status,
        "unresolved_questions": _text_list(record.get("unresolved_questions"), "unresolved_questions"),
        "next_actions": _text_list(record.get("next_actions"), "next_actions"),
        "manual_verification_required": record["manual_verification_required"],
    }
    normalized["verification_blockers"] = source_verification_blockers(normalized)
    return normalized


def validate_source_verification_matrix(
    document: Any,
    *,
    dataset_ids: Iterable[str] | None = None,
    project_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Validate source references without downloading or opening them."""

    if not isinstance(document, dict) or not isinstance(document.get("sources"), list):
        raise DataLoaderError("The source verification matrix must contain a sources list.")
    known_ids = set(dataset_ids) if dataset_ids is not None else None
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in document["sources"]:
        normalized = _normalize_source(record, dataset_ids=known_ids, project_root=project_root)
        if normalized["source_id"] in seen:
            raise DataLoaderError("Source verification IDs must be unique.")
        seen.add(normalized["source_id"])
        records.append(normalized)
    return records


def load_source_verification_matrix(
    path: str | Path,
    *,
    dataset_ids: Iterable[str] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load the source matrix as safe, normalized metadata."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataLoaderError("The source verification matrix could not be read safely.") from exc
    return {
        "source_verification_version": document.get("source_verification_version", 1),
        "sources": validate_source_verification_matrix(document, dataset_ids=dataset_ids, project_root=project_root),
    }


def summarize_source_verification(sources: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = [source for source in sources if isinstance(source, dict)]
    statuses = Counter(str(source.get("verification_status", "unavailable")) for source in records)
    dimension_counts = {
        field: dict(
            sorted(
                Counter(str(source.get(field, "missing")) for source in records).items()
            )
        )
        for field in SOURCE_STATUS_FIELDS
    }
    return {
        "source_count": len(records),
        "verified": statuses.get("verified", 0),
        "provided_unverified": statuses.get("provided_unverified", 0),
        "missing": statuses.get("missing", 0),
        "rejected": statuses.get("rejected", 0),
        "not_applicable": statuses.get("not_applicable", 0),
        "manual_verification_count": sum(source.get("manual_verification_required") is True for source in records),
        "status_counts": dict(sorted(statuses.items())),
        "dimension_status_counts": dimension_counts,
        "blocking_dimension_count": sum(
            len(source_verification_blockers(source)) for source in records
        ),
        "access_checklist": summarize_access_checklist(records),
    }


def summarize_access_checklist(
    sources: Iterable[dict[str, Any]], evidence_items: Iterable[dict[str, Any]] = ()
) -> dict[str, Any]:
    """Resolve checklist status from its linked evidence/source dimensions."""

    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in evidence_items
        if isinstance(item, dict) and item.get("evidence_id")
    }
    rows = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for check in source.get("access_checklist", []):
            if not isinstance(check, dict):
                continue
            status = check.get("status", "missing")
            status_field = check.get("source_status_field")
            if status_field:
                status = source.get(status_field, "missing")
            linked = [evidence_by_id.get(ref) for ref in check.get("evidence_references", []) if ref in evidence_by_id]
            if linked:
                linked_statuses = [item.get("status", "missing") for item in linked]
                if all(value in SATISFYING_STATUSES for value in linked_statuses):
                    status = "verified"
                elif "rejected" in linked_statuses:
                    status = "rejected"
                elif "provided_unverified" in linked_statuses:
                    status = "provided_unverified"
                else:
                    status = "missing"
            rows.append({**check, "status": status, "source_id": source.get("source_id"), "dataset_id": source.get("dataset_id")})
    counts = Counter(str(row.get("status", "missing")) for row in rows)
    return {"total": len(rows), "rows": rows, "status_counts": dict(sorted(counts.items())), "verified": counts.get("verified", 0), "outstanding": sum(value for key, value in counts.items() if key not in SATISFYING_STATUSES)}


_ACTION_GROUPS = {
    "dataset_provenance": "source_acquisition",
    "authorization": "authorization_and_permitted_use",
    "licensing": "publication_and_disclosure_review",
    "documentation": "codebook_acquisition",
    "variable_mapping": "variable_mapping_review",
    "indicator_methodology": "variable_mapping_review",
    "survey_design": "survey_methodology_and_weighting",
    "geography": "geographic_resources",
    "data_quality": "data_quality_review",
    "disclosure_publication": "publication_and_disclosure_review",
}


def build_researcher_action_plan(
    evidence_items: Iterable[dict[str, Any]],
    sources: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group unresolved evidence into manual, auditable work items."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in evidence_items:
        if not isinstance(item, dict) or item.get("status") in {"verified", "not_applicable"}:
            continue
        group = _ACTION_GROUPS.get(str(item.get("category")), "source_acquisition")
        grouped.setdefault(group, []).append(
            {
                "evidence_id": item.get("evidence_id"),
                "status": item.get("status"),
                "related_dataset_id": item.get("related_dataset_id"),
                "related_indicator_id": item.get("related_indicator_id"),
                "description": item.get("description"),
                "why_it_matters": item.get("reason_for_blocking"),
                "next_action": item.get("next_action"),
                "completion_criterion": "A responsible reviewer records acceptable evidence, reference, date, and status in the metadata register.",
                "manual_verification_required": True,
                "blocks": list(item.get("blocks", [])),
                "affected_dataset_id": item.get("related_dataset_id"),
                "affected_indicator_id": item.get("related_indicator_id"),
            }
        )
    for source in sources:
        if not isinstance(source, dict) or source.get("verification_status") in {"verified", "not_applicable"}:
            continue
        source_task = {
                "source_id": source.get("source_id"),
                "related_dataset_id": source.get("dataset_id"),
                "candidate_dataset_name": source.get("candidate_dataset_name"),
                "status": source.get("verification_status"),
                "description": "Review the public source reference and confirm it corresponds to the local or intended data product.",
                "why_it_matters": "A landing page supports discovery but does not prove local file provenance or permission.",
                "next_action": "; ".join(source.get("next_actions", [])),
                "completion_criterion": "Source identity, version, local-file relationship, and responsible owner are documented and independently reviewed.",
                "manual_verification_required": source.get("manual_verification_required", True),
                "missing_requirements": [item.get("requirement") for item in source.get("verification_blockers", [])],
                "blocks": sorted({scope for item in source.get("verification_blockers", []) for scope in item.get("blocks", [])}),
                "verification_blockers": source.get("verification_blockers", []),
            }
        grouped.setdefault("source_acquisition", []).append(source_task)
    return {group: sorted(items, key=lambda item: str(item.get("evidence_id") or item.get("source_id"))) for group, items in sorted(grouped.items())}
