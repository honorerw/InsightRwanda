"""Reproducibility manifests and privacy-preserving audit events.

This module records how an aggregate result could be traced and revalidated.
It never loads source observations, executes code named by a manifest, grants
eligibility, or treats a checksum as authorization or authenticity evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import platform
import re
from typing import Any, Iterable, Mapping

from insightrwanda.data.errors import IndicatorBlockedError
from insightrwanda.data.paths import resolve_derived_output_path

from .phase14 import CALCULATION_CODE_VERSION
from .validation import contains_forbidden_raw_keys, validate_result_integrity


MANIFEST_SCHEMA_VERSION = "phase20-manifest-v1"
AUDIT_SCHEMA_VERSION = "phase20-audit-v1"
SUPPORTED_OUTPUT_FORMATS = {"json"}
SUPPORTED_METHOD_VERSIONS = {CALCULATION_CODE_VERSION}
HEX_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
SAFE_REASON = re.compile(r"^[a-z][a-z0-9_.-]{1,95}$")
_AUDIT_EVENT_KEYS = {
    "audit_schema_version",
    "event_id",
    "event_type",
    "status",
    "manifest_id",
    "result_id",
    "reason_codes",
    "created_at_utc",
    "data_classification",
    "raw_records_included",
}

_MANIFEST_REQUIRED = (
    "manifest_schema_version",
    "manifest_id",
    "result_id",
    "dataset_id",
    "dataset_release",
    "input_content_checksum",
    "indicator_id",
    "definition_version",
    "mapping_version",
    "calculation_specification_id",
    "calculation_specification_version",
    "method_version",
    "result_checksum",
    "validation_references",
    "analytical_eligibility_reference",
    "created_at_utc",
    "output_format",
    "known_limitations",
    "data_classification",
    "reproducibility_status",
    "manifest_checksum",
)

_NUMERIC_RESULT_FIELDS = {
    "estimate",
    "percentage",
    "weighted_denominator",
    "standard_error",
    "eligible_observation_count",
}


class ReproducibilityError(ValueError):
    """Raised when a manifest or audit record cannot be safely represented."""


def _normalise(value: Any) -> Any:
    """Convert supported JSON-like values to a deterministic representation."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ReproducibilityError("Non-finite numbers are not supported in canonical metadata.")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ReproducibilityError("Canonical metadata requires string object keys.")
            result[key] = _normalise(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    raise ReproducibilityError(f"Unsupported canonical metadata type: {type(value).__name__}.")


def canonical_json(value: Any) -> str:
    """Serialize supported values with stable ordering and UTF-8 semantics."""

    return json.dumps(
        _normalise(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    """Hash the documented canonical JSON representation."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ReproducibilityError(f"Manifest field '{field}' must be safe single-line text.")
    return value.strip()


def _utc_timestamp(value: Any) -> str:
    text = _text(value, "created_at_utc")
    assert text is not None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReproducibilityError("created_at_utc must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        raise ReproducibilityError("created_at_utc must include an explicit timezone.")
    return parsed.astimezone(timezone.utc).isoformat()


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Return result content used for hashing, excluding artifact bookkeeping."""

    payload = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
    payload.pop("reproducibility_manifest", None)
    payload.pop("result_checksum", None)
    payload.pop("result_artifact_written", None)
    return payload


def result_checksum(result: dict[str, Any]) -> str:
    """Hash an aggregate result without its mutable persistence marker."""

    if not isinstance(result, dict) or contains_forbidden_raw_keys(result):
        raise ReproducibilityError("Only aggregate results without raw payloads can be hashed.")
    return canonical_sha256(_result_payload(result))


def _manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = dict(manifest)
    payload.pop("manifest_checksum", None)
    return payload


def manifest_checksum(manifest: dict[str, Any]) -> str:
    return canonical_sha256(_manifest_payload(manifest))


def build_reproducibility_manifest(
    result: dict[str, Any],
    *,
    manifest_id: str,
    mapping_version: str,
    calculation_specification_id: str,
    validation_references: Mapping[str, str],
    analytical_eligibility_reference: str,
    indicator_definition: Mapping[str, Any] | None = None,
    calculation_specification: Mapping[str, Any] | None = None,
    geographic_resource: Mapping[str, Any] | None = None,
    publication_eligibility_reference: str | None = None,
    publication_requested: bool = False,
    method_version: str | None = None,
    created_at_utc: str | None = None,
    software: Mapping[str, Any] | None = None,
    dependency_versions: Mapping[str, str] | None = None,
    random_seed: int | None = None,
) -> dict[str, Any]:
    """Build a manifest from explicit, already-recorded result metadata.

    Missing identifiers or checksums are errors.  This function never reads a
    source file to fill them in and never infers authorization from a result.
    """

    if not isinstance(result, dict) or result.get("calculation_status") != "calculated":
        raise ReproducibilityError("A successful aggregate result is required to build a manifest.")
    if contains_forbidden_raw_keys(result) or result.get("raw_records_included") is True:
        raise ReproducibilityError("Manifests cannot be built from raw-record results.")
    integrity = validate_result_integrity(result)
    if not integrity.calculation_allowed:
        raise ReproducibilityError("The result must pass aggregate integrity validation before manifest creation.")

    provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    reproducibility = result.get("reproducibility") if isinstance(result.get("reproducibility"), dict) else {}
    definition = indicator_definition if isinstance(indicator_definition, Mapping) else {}
    specification = calculation_specification if isinstance(calculation_specification, Mapping) else {}
    dataset_release = result.get("dataset_release")
    input_checksum = provenance.get("input_file_sha256")
    definition_version = result.get("definition_version") or definition.get("definition_version")
    indicator_id = result.get("indicator_id") or definition.get("indicator_id")
    specification_version = specification.get("version") or reproducibility.get("calculation_specification_version")
    method = method_version or reproducibility.get("code_version")
    values = {
        "manifest_id": manifest_id,
        "result_id": result.get("result_id"),
        "dataset_id": result.get("dataset_id"),
        "dataset_release": dataset_release,
        "input_content_checksum": input_checksum,
        "indicator_id": indicator_id,
        "definition_version": definition_version,
        "mapping_version": mapping_version,
        "calculation_specification_id": calculation_specification_id,
        "calculation_specification_version": specification_version,
        "method_version": method,
        "analytical_eligibility_reference": analytical_eligibility_reference,
    }
    for field, value in values.items():
        _text(value, field)
    if not isinstance(validation_references, Mapping) or not validation_references:
        raise ReproducibilityError("Validation evidence references are required.")
    if not all(isinstance(key, str) and isinstance(value, str) and key and value for key, value in validation_references.items()):
        raise ReproducibilityError("Validation evidence references must be safe text mappings.")
    if not isinstance(input_checksum, str) or not HEX_SHA256.fullmatch(input_checksum):
        raise ReproducibilityError("An existing authorized input SHA-256 checksum is required.")
    if publication_requested:
        _text(publication_eligibility_reference, "publication_eligibility_reference")
    if random_seed is not None and (isinstance(random_seed, bool) or not isinstance(random_seed, int)):
        raise ReproducibilityError("random_seed must be an integer when supplied.")

    geographic = geographic_resource if isinstance(geographic_resource, Mapping) else {}
    boundary_release = geographic.get("boundary_release")
    resource_id = geographic.get("resource_id")
    if geographic_resource is not None:
        _text(resource_id, "geographic_resource_id")
        _text(boundary_release, "geographic_boundary_release")

    manifest: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": _text(manifest_id, "manifest_id"),
        "result_id": _text(result.get("result_id"), "result_id"),
        "dataset_id": _text(result.get("dataset_id"), "dataset_id"),
        "dataset_release": _text(dataset_release, "dataset_release"),
        "input_content_checksum": input_checksum,
        "indicator_id": _text(indicator_id, "indicator_id"),
        "definition_version": _text(definition_version, "definition_version"),
        "mapping_version": _text(mapping_version, "mapping_version"),
        "calculation_specification_id": _text(calculation_specification_id, "calculation_specification_id"),
        "calculation_specification_version": _text(specification_version, "calculation_specification_version"),
        "method_version": _text(method, "method_version"),
        "software": dict(software or {"python_version": platform.python_version()}),
        "dependency_versions": dict(dependency_versions or {}),
        "random_seed": random_seed,
        "geographic_resource_id": _text(resource_id, "geographic_resource_id", required=False),
        "geographic_boundary_release": _text(boundary_release, "geographic_boundary_release", required=False),
        "validation_references": dict(validation_references),
        "analytical_eligibility_reference": _text(analytical_eligibility_reference, "analytical_eligibility_reference"),
        "publication_eligibility_reference": _text(publication_eligibility_reference, "publication_eligibility_reference", required=False),
        "publication_requested": bool(publication_requested),
        "created_at_utc": _utc_timestamp(created_at_utc or datetime.now(timezone.utc).isoformat()),
        "output_format": "json",
        "result_checksum": result_checksum(result),
        "known_limitations": list(result.get("limitations") or []),
        "data_classification": result.get("data_classification", "authorized_aggregate"),
        "reproducibility_status": "manifest_created",
    }
    manifest["manifest_checksum"] = manifest_checksum(manifest)
    validate_manifest(manifest)
    return manifest


def _check(check_id: str, status: str, explanation: str, action: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "explanation": explanation,
        "prevents_analytical_eligibility": status in {"fail", "blocked"},
        "corrective_action": action,
    }


@dataclass(frozen=True)
class ReproducibilityReport:
    """Separate reproducibility states; never an eligibility override."""

    status: str
    manifest_valid: bool
    integrity_verified: bool | None
    lineage_traceable: bool
    reproduction_status: str
    analytical_eligibility_verified: bool
    publication_eligibility_verified: bool | None
    blocker_ids: tuple[str, ...]
    checks: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "manifest_valid": self.manifest_valid,
            "integrity_verified": self.integrity_verified,
            "lineage_traceable": self.lineage_traceable,
            "reproduction_status": self.reproduction_status,
            "analytical_eligibility_verified": self.analytical_eligibility_verified,
            "publication_eligibility_verified": self.publication_eligibility_verified,
            "blocker_ids": list(self.blocker_ids),
            "checks": [dict(item) for item in self.checks],
        }


def validate_manifest(
    manifest: dict[str, Any] | None,
    *,
    result: dict[str, Any] | None = None,
    expected_lineage: Mapping[str, Any] | None = None,
    current_eligibility: Mapping[str, Any] | None = None,
    geographic_required: bool = False,
    publication_requested: bool = False,
) -> ReproducibilityReport:
    """Validate structure, checksums, lineage, and current decision references."""

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    if not isinstance(manifest, dict):
        checks.append(_check("manifest_schema", "fail", "No manifest object was supplied.", "Create a versioned manifest from an eligible aggregate result."))
        return ReproducibilityReport("invalid", False, None, False, "not_run", False, None, ("manifest_missing",), tuple(checks))

    try:
        canonical_json(manifest)
        raw = contains_forbidden_raw_keys(manifest)
    except ReproducibilityError as exc:
        checks.append(_check("manifest_schema", "fail", str(exc), "Use only supported JSON metadata types."))
        return ReproducibilityReport("invalid", False, None, False, "not_run", False, None, ("manifest_schema",), tuple(checks))
    if raw:
        blockers.append("manifest_contains_raw_payload")
        checks.append(_check("manifest_privacy", "fail", "The manifest contains a forbidden row-level or geometry field.", "Retain aggregate metadata only."))
    else:
        checks.append(_check("manifest_privacy", "pass", "The manifest contains no forbidden row-level payload fields.", "No action required."))

    missing = [field for field in _MANIFEST_REQUIRED if manifest.get(field) in (None, "", [])]
    schema_ok = manifest.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION and not missing
    if not schema_ok:
        blockers.append("manifest_schema")
    checks.append(_check("manifest_schema", "pass" if schema_ok else "fail", "Manifest schema and required fields are valid." if schema_ok else "Manifest schema version or required fields are missing.", "Use the supported manifest schema and record every required lineage field."))

    try:
        for field in ("manifest_id", "result_id", "dataset_id", "dataset_release", "indicator_id", "definition_version", "mapping_version", "calculation_specification_id", "calculation_specification_version", "method_version", "analytical_eligibility_reference"):
            _text(manifest.get(field), field)
        _utc_timestamp(manifest.get("created_at_utc"))
        input_checksum = manifest.get("input_content_checksum")
        if not isinstance(input_checksum, str) or not HEX_SHA256.fullmatch(input_checksum):
            raise ReproducibilityError("input_content_checksum is not a SHA-256 digest.")
        if not isinstance(manifest.get("result_checksum"), str) or not HEX_SHA256.fullmatch(manifest["result_checksum"]):
            raise ReproducibilityError("result_checksum is not a SHA-256 digest.")
        if manifest.get("output_format") not in SUPPORTED_OUTPUT_FORMATS:
            raise ReproducibilityError("The output format is unsupported.")
        if not isinstance(manifest.get("validation_references"), dict) or not manifest["validation_references"]:
            raise ReproducibilityError("Validation references are missing.")
        checksum_ok = manifest.get("manifest_checksum") == manifest_checksum(manifest)
    except (ReproducibilityError, TypeError):
        checksum_ok = False
    if not checksum_ok:
        blockers.append("manifest_checksum_mismatch")
    checks.append(_check("manifest_checksum", "pass" if checksum_ok else "fail", "The manifest checksum matches its canonical content." if checksum_ok else "The manifest checksum is malformed or does not match canonical content.", "Regenerate the manifest from the approved metadata."))

    method_ok = manifest.get("method_version") in SUPPORTED_METHOD_VERSIONS
    if not method_ok:
        blockers.append("unsupported_method_version")
    checks.append(_check("method_version", "pass" if method_ok else "blocked", "The calculation implementation version is supported." if method_ok else "The recorded method version is not supported by this implementation.", "Use the approved implementation or complete a reviewed method integration."))

    integrity_verified: bool | None = None
    lineage_traceable = not any(item in blockers for item in ("manifest_schema", "manifest_checksum_mismatch", "manifest_contains_raw_payload"))
    if result is None:
        blockers.append("result_reference_missing")
        checks.append(_check("result_integrity", "not_run", "No result content was supplied for integrity verification.", "Provide the saved aggregate result through the approved workflow."))
        integrity_verified = None
    else:
        integrity = validate_result_integrity(result)
        try:
            actual_result_checksum = result_checksum(result)
        except (ReproducibilityError, TypeError, ValueError):
            actual_result_checksum = None
        integrity_verified = integrity.calculation_allowed and actual_result_checksum == manifest.get("result_checksum")
        if not integrity.calculation_allowed:
            blockers.append("result_integrity")
        if actual_result_checksum != manifest.get("result_checksum"):
            blockers.append("result_checksum_mismatch")
        checks.append(_check("result_integrity", "pass" if integrity_verified else "fail", "The supplied result passes aggregate integrity checks and matches the manifest checksum." if integrity_verified else "The supplied result is invalid or differs from the manifest checksum.", "Revalidate the result and regenerate its manifest."))

        if result.get("data_classification") == "synthetic_test_data":
            blockers.append("synthetic_result_not_for_real_research")
            checks.append(_check("research_data_classification", "blocked", "Synthetic test data is valid only for software-level tests.", "Use an authorized aggregate result for real research."))

    expected = dict(expected_lineage or {})
    for field in ("dataset_id", "dataset_release", "indicator_id", "definition_version", "mapping_version", "calculation_specification_version", "method_version"):
        if field in expected and expected[field] is not None and manifest.get(field) != expected[field]:
            blockers.append(f"lineage_{field}_mismatch")
    if expected:
        lineage_traceable = lineage_traceable and not any(item.startswith("lineage_") for item in blockers)
    checks.append(_check("lineage", "pass" if lineage_traceable else "fail", "Manifest lineage agrees with the expected approved identifiers." if lineage_traceable else "Manifest lineage contradicts the expected approved identifiers.", "Reconcile the manifest with the exact approved release, definition, mapping, and method."))

    if geographic_required and not manifest.get("geographic_boundary_release"):
        blockers.append("geographic_boundary_version_missing")
    checks.append(_check("geographic_lineage", "pass" if not geographic_required or manifest.get("geographic_boundary_release") else "blocked", "Required geographic lineage is recorded." if not geographic_required or manifest.get("geographic_boundary_release") else "A required geographic boundary version is missing.", "Record the verified geographic resource and boundary release."))

    eligibility = dict(current_eligibility or {})
    analysis_ok = eligibility.get("analysis_eligible") is True
    if "analysis_eligible" in eligibility and not analysis_ok:
        blockers.append("central_analytical_eligibility")
    if "authorization_valid" in eligibility and eligibility.get("authorization_valid") is not True:
        blockers.append("authorization_revalidation_required")
    checks.append(_check("analytical_eligibility", "pass" if analysis_ok or "analysis_eligible" not in eligibility else "blocked", "Current analytical eligibility is verified by the supplied central decision." if analysis_ok else "Current analytical eligibility was not verified.", "Re-evaluate the authoritative authorization and readiness evidence."))
    publication_ok: bool | None = None
    if publication_requested:
        publication_ok = eligibility.get("publication_eligible") is True
        if not publication_ok:
            blockers.append("publication_eligibility")
        checks.append(_check("publication_eligibility", "pass" if publication_ok else "blocked", "Current publication eligibility is separately verified." if publication_ok else "Publication eligibility is absent or false.", "Complete the separate disclosure and publication review."))

    unique_blockers = tuple(dict.fromkeys(blockers))
    if not schema_ok or not checksum_ok:
        status = "invalid"
    elif unique_blockers:
        status = "software_test_only" if set(unique_blockers) == {"synthetic_result_not_for_real_research"} else "blocked"
    else:
        status = "manifest_valid"
    reproduction_status = "software_test_only" if status == "software_test_only" else "blocked" if unique_blockers else "not_run"
    return ReproducibilityReport(status, schema_ok and checksum_ok and not raw, integrity_verified, lineage_traceable, reproduction_status, analysis_ok, publication_ok, unique_blockers, tuple(checks))


def detect_reproducibility_changes(manifest: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare only supplied reproducibility-critical fields."""

    if not isinstance(manifest, Mapping) or not isinstance(current, Mapping):
        return {"status": "blocked", "changed_fields": ["change_detection_input"], "blocker_ids": ["change_detection_input"]}
    fields = (
        "dataset_release",
        "input_content_checksum",
        "definition_version",
        "mapping_version",
        "calculation_specification_version",
        "method_version",
        "geographic_boundary_release",
        "validation_schema_version",
        "dependency_versions",
        "authorization_status",
    )
    changed = [field for field in fields if field in current and current.get(field) != manifest.get(field)]
    return {
        "status": "revalidation_required" if changed else "unchanged",
        "changed_fields": changed,
        "blocker_ids": [f"revalidation_{field}" for field in changed],
        "explanation": "Reproducibility-critical inputs changed; revalidation is required." if changed else "No supplied reproducibility-critical inputs changed.",
    }


def _without_comparison_volatility(value: Any, *, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "result_artifact_written" or path + (key,) == ("provenance", "calculated_at_utc"):
                continue
            if key in _NUMERIC_RESULT_FIELDS or key in {"lower", "upper"}:
                result[key] = "__numeric_field__"
            else:
                result[key] = _without_comparison_volatility(item, path=path + (key,))
        return result
    if isinstance(value, list):
        return [_without_comparison_volatility(item, path=path) for item in value]
    return value


def _numeric_values(value: Any, path: tuple[str, ...] = ()) -> dict[str, float]:
    values: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _NUMERIC_RESULT_FIELDS or key in {"lower", "upper"}:
                if item is not None:
                    if isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(float(item)):
                        values[".".join(path + (key,))] = float("nan")
                    else:
                        values[".".join(path + (key,))] = float(item)
            else:
                values.update(_numeric_values(item, path + (key,)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            values.update(_numeric_values(item, path + (str(index),)))
    return values


def compare_reproduced_results(
    reference_result: dict[str, Any] | None,
    reproduced_result: dict[str, Any] | None,
    *,
    numerical_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Compare aggregate outputs without executing or exposing source rows."""

    if isinstance(numerical_tolerance, bool) or not isinstance(numerical_tolerance, (int, float)) or not isfinite(float(numerical_tolerance)) or numerical_tolerance < 0:
        return {"status": "blocked", "equivalent": False, "blocker_ids": ["invalid_comparison_tolerance"]}
    if not isinstance(reference_result, dict) or not isinstance(reproduced_result, dict):
        return {"status": "blocked", "equivalent": False, "blocker_ids": ["reproduction_input_missing"]}
    reference_integrity = validate_result_integrity(reference_result).calculation_allowed
    reproduced_integrity = validate_result_integrity(reproduced_result).calculation_allowed
    if not reference_integrity or not reproduced_integrity:
        return {"status": "blocked", "equivalent": False, "blocker_ids": ["result_integrity"]}
    if _without_comparison_volatility(reference_result) != _without_comparison_volatility(reproduced_result):
        return {"status": "failed", "equivalent": False, "comparison_mode": "exact_metadata_and_numeric_tolerance", "differing_fields": ["canonical_result_content"]}
    left = _numeric_values(reference_result)
    right = _numeric_values(reproduced_result)
    differences = [field for field in sorted(set(left) | set(right)) if field not in left or field not in right or not isfinite(left.get(field, float("nan"))) or not isfinite(right.get(field, float("nan"))) or abs(left[field] - right[field]) > float(numerical_tolerance)]
    if differences:
        return {"status": "failed", "equivalent": False, "comparison_mode": "exact_metadata_and_numeric_tolerance", "tolerance": float(numerical_tolerance), "differing_fields": differences}
    synthetic = reference_result.get("data_classification") == "synthetic_test_data" or reproduced_result.get("data_classification") == "synthetic_test_data"
    return {"status": "software_test_only" if synthetic else "passed", "equivalent": True, "comparison_mode": "exact" if numerical_tolerance == 0 else "numerical_tolerance", "tolerance": float(numerical_tolerance)}


def build_audit_event(
    event_type: str,
    status: str,
    *,
    manifest_id: str | None = None,
    result_id: str | None = None,
    reason_codes: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a safe, deduplicatable event using reason codes only."""

    if not isinstance(event_type, str) or not SAFE_REASON.fullmatch(event_type):
        raise ReproducibilityError("Unsupported audit event type.")
    if status not in {"passed", "failed", "blocked", "revalidation_required", "not_run"}:
        raise ReproducibilityError("Unsupported audit event status.")
    reasons = tuple(dict.fromkeys(str(item) for item in reason_codes))
    if any(not SAFE_REASON.fullmatch(item) for item in reasons):
        raise ReproducibilityError("Audit reason codes must be stable safe identifiers.")
    identity = {"event_type": event_type, "status": status, "manifest_id": manifest_id, "result_id": result_id, "reason_codes": list(reasons)}
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "event_id": "event-" + canonical_sha256(identity)[:24],
        "event_type": event_type,
        "status": status,
        "manifest_id": _text(manifest_id, "manifest_id", required=False),
        "result_id": _text(result_id, "result_id", required=False),
        "reason_codes": list(reasons),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_classification": "metadata_only",
        "raw_records_included": False,
    }


def _validate_audit_event(event: dict[str, Any]) -> None:
    if set(event) - _AUDIT_EVENT_KEYS:
        raise ReproducibilityError("Audit events contain unsupported fields.")
    if event.get("audit_schema_version") != AUDIT_SCHEMA_VERSION:
        raise ReproducibilityError("Audit event schema version is unsupported.")
    if not isinstance(event.get("event_id"), str) or not event["event_id"].startswith("event-"):
        raise ReproducibilityError("Audit events require a stable event identifier.")
    if not isinstance(event.get("event_type"), str) or not SAFE_REASON.fullmatch(event["event_type"]):
        raise ReproducibilityError("Audit event type is malformed.")
    if event.get("status") not in {"passed", "failed", "blocked", "revalidation_required", "not_run"}:
        raise ReproducibilityError("Audit event status is unsupported.")
    if not isinstance(event.get("reason_codes"), list) or any(not isinstance(item, str) or not SAFE_REASON.fullmatch(item) for item in event["reason_codes"]):
        raise ReproducibilityError("Audit reason codes are malformed.")
    if event.get("data_classification") != "metadata_only" or event.get("raw_records_included") is not False:
        raise ReproducibilityError("Audit events must be metadata-only.")
    _utc_timestamp(event.get("created_at_utc"))


def append_audit_event(events: Iterable[dict[str, Any]] | None, event: dict[str, Any]) -> list[dict[str, Any]]:
    """Append an event once, preserving existing event history order."""

    if not isinstance(event, dict) or contains_forbidden_raw_keys(event) or event.get("raw_records_included") is True:
        raise ReproducibilityError("Audit events must contain metadata only.")
    existing = [dict(item) for item in (events or ()) if isinstance(item, dict)]
    for item in existing:
        _validate_audit_event(item)
    _validate_audit_event(event)
    if any(item.get("event_id") == event.get("event_id") for item in existing):
        return existing
    return existing + [dict(event)]


def save_audit_events(
    events: Iterable[dict[str, Any]],
    *,
    project_root: str | Path,
    output_path: str | Path = "artifacts/phase20_audit.json",
) -> Path:
    """Persist only safe metadata audit events; this is not immutable storage."""

    safe_events: list[dict[str, Any]] = []
    try:
        for event in events:
            safe_events = append_audit_event(safe_events, event)
    except (ReproducibilityError, TypeError) as exc:
        raise IndicatorBlockedError("Reproducibility audit events must contain valid metadata only.") from exc
    output = resolve_derived_output_path(output_path, project_root=project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"audit_schema_version": AUDIT_SCHEMA_VERSION, "events": safe_events}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def build_phase20_status(
    *,
    manifest: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    expected_lineage: Mapping[str, Any] | None = None,
    current_eligibility: Mapping[str, Any] | None = None,
    geographic_required: bool = False,
    publication_requested: bool = False,
    reproduction_comparison: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a metadata-only Phase 20 state without granting eligibility."""

    if manifest is None:
        report = ReproducibilityReport("not_configured", False, None, False, "not_run", False, None, ("reproducibility_manifest_missing",), (_check("manifest_configuration", "blocked", "No reproducibility manifest is available for the result.", "Create a manifest only after an eligible aggregate result exists."),))
    else:
        report = validate_manifest(
            manifest,
            result=result,
            expected_lineage=expected_lineage,
            current_eligibility=current_eligibility,
            geographic_required=geographic_required,
            publication_requested=publication_requested,
        )
    status = report.status
    reproduction_status = report.reproduction_status
    blockers = list(report.blocker_ids)
    if reproduction_comparison is not None:
        if reproduction_comparison.get("status") == "passed" and reproduction_comparison.get("equivalent") is True and report.status == "manifest_valid":
            status = "verified"
            reproduction_status = "verified"
        elif reproduction_comparison.get("status") == "software_test_only" and reproduction_comparison.get("equivalent") is True:
            status = "software_test_only"
            reproduction_status = "software_test_only"
        else:
            status = "blocked"
            reproduction_status = "blocked"
            blockers.append("reproduction_comparison_failed")
    return {
        "phase": 20,
        "status": status,
        "manifest_status": "valid" if report.manifest_valid else "invalid_or_missing",
        "integrity_status": "verified" if report.integrity_verified is True else "not_run" if report.integrity_verified is None else "failed",
        "lineage_status": "traceable" if report.lineage_traceable else "incomplete",
        "reproduction_status": reproduction_status,
        "analytical_eligibility_verified": report.analytical_eligibility_verified,
        "publication_eligibility_verified": report.publication_eligibility_verified,
        "blocker_ids": list(dict.fromkeys(blockers)),
        "checks": [dict(item) for item in report.checks],
        "data_classification": "metadata_only",
        "raw_records_included": False,
    }


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "ReproducibilityError",
    "append_audit_event",
    "build_audit_event",
    "build_phase20_status",
    "build_reproducibility_manifest",
    "canonical_json",
    "canonical_sha256",
    "compare_reproduced_results",
    "detect_reproducibility_changes",
    "manifest_checksum",
    "result_checksum",
    "save_audit_events",
    "validate_manifest",
]
