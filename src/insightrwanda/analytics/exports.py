"""Fail-closed validation for future public aggregate exports.

The application currently exposes no download control because the project has
no publication-eligible result. This module keeps the eventual export
boundary explicit and testable: only an already verified public insight plus
an explicitly approved output specification can produce a metadata-and-
aggregate payload. It never writes a file and never includes raw records.
"""

from __future__ import annotations

from typing import Any

from .insights import _chartable_insight


def _blocker(identifier: str, message: str, next_action: str) -> dict[str, str]:
    return {"identifier": identifier, "message": message, "next_action": next_action}


def validate_public_export(
    insight: dict[str, Any] | None,
    *,
    output_specification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an approved aggregate export without producing one."""

    blockers: list[dict[str, str]] = []
    if not isinstance(insight, dict):
        blockers.append(_blocker("insight_missing", "No verified insight is available for export.", "Complete an eligible aggregate calculation."))
    elif not _chartable_insight(insight, intended_use="public_display"):
        blockers.append(_blocker("public_insight_ineligible", "The supplied insight is not verified and publication-eligible.", "Resolve analytical, disclosure, validation, and publication gates first."))
    if isinstance(insight, dict):
        if insight.get("data_classification") != "authorized_aggregate":
            blockers.append(_blocker("export_data_classification", "Exports may contain authorized aggregates only.", "Remove restricted or synthetic data from the export path."))
        if insight.get("raw_records_included") is True:
            blockers.append(_blocker("export_raw_records", "Raw or identifiable records cannot be exported.", "Retain aggregate fields and necessary metadata only."))
    if not isinstance(output_specification, dict) or output_specification.get("approved") is not True:
        blockers.append(_blocker("output_specification_not_approved", "No explicit approved output specification is attached.", "Record the approved output scope, fields, and reviewer before enabling export."))
    elif not isinstance(output_specification.get("output_id"), str) or not output_specification["output_id"].strip():
        blockers.append(_blocker("output_specification_id_missing", "The approved output specification has no stable identifier.", "Record a stable approved output identifier."))

    if blockers:
        return {
            "status": "blocked",
            "blocker_ids": list(dict.fromkeys(item["identifier"] for item in blockers)),
            "blockers": blockers,
            "payload": None,
            "data_classification": "metadata_only",
            "raw_records_included": False,
        }
    return {
        "status": "eligible",
        "blocker_ids": [],
        "blockers": [],
        "payload": None,
        "data_classification": "metadata_only",
        "raw_records_included": False,
    }


def build_public_export_payload(
    insight: dict[str, Any] | None,
    *,
    output_specification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a safe payload only after :func:`validate_public_export` passes.

    The returned payload contains aggregate display metadata only. It is kept
    separate from Streamlit so a future download action cannot bypass the
    validation contract by serializing the insight directly.
    """

    validation = validate_public_export(insight, output_specification=output_specification)
    if validation["status"] != "eligible" or not isinstance(insight, dict) or not isinstance(output_specification, dict):
        return validation
    definition = insight.get("definition") if isinstance(insight.get("definition"), dict) else {}
    provenance = insight.get("provenance") if isinstance(insight.get("provenance"), dict) else {}
    payload = {
        "export_schema": "phase22-public-aggregate-v1",
        "output_specification": {
            "output_id": output_specification["output_id"],
            "version": output_specification.get("version"),
        },
        "indicator": {
            "indicator_id": insight.get("indicator_id"),
            "definition_version": insight.get("definition_version"),
            "definition": definition.get("definition_text"),
            "unit": insight.get("unit"),
        },
        "result": {
            "source_result_id": insight.get("source_result_id"),
            "dataset_id": insight.get("dataset_id"),
            "dataset_release": insight.get("dataset_release"),
            "population_scope": insight.get("population_scope"),
            "geographic_scope": insight.get("geographic_scope"),
            "reference_period": insight.get("reference_period"),
            "estimate": insight.get("display_estimate"),
            "uncertainty": insight.get("uncertainty"),
            "limitations": list(insight.get("limitations") or []),
        },
        "provenance": {
            "dataset_id": provenance.get("dataset_id"),
            "dataset_release": provenance.get("dataset_release"),
            "input_file_sha256": provenance.get("input_file_sha256"),
            "calculated_at_utc": provenance.get("calculated_at_utc"),
        },
        "data_classification": "metadata_only",
        "raw_records_included": False,
    }
    return {**validation, "payload": payload}
