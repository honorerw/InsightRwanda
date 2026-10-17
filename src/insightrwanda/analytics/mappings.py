"""Validation helpers for codebook-backed indicator mappings.

These helpers validate the shape and evidence of a mapping.  They do not
infer meaning from a variable name and do not approve a proposed indicator.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from insightrwanda.data.errors import IndicatorDefinitionError
from insightrwanda.data.evidence import EVIDENCE_STATUSES


MAPPING_REQUIRED_FIELDS = {
    "source_dataset_id",
    "source_variable",
    "variable_meaning",
    "codebook_reference",
    "eligible_population",
    "denominator_definition",
    "missing_value_treatment",
    "response_coding",
    "status",
    "evidence_reference",
}


def _valid_reference(value: Any) -> bool:
    """Accept a safe relative document reference or an explicit HTTPS URL."""

    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        return False
    reference = value.strip()
    parsed = urlparse(reference)
    if parsed.scheme:
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    path = reference.split("#", 1)[0]
    candidate = Path(path)
    return bool(path) and not candidate.is_absolute() and ".." not in candidate.parts and not reference.startswith("~")


def _mapping_record_problems(
    record: dict[str, Any],
    *,
    required_variable: str | None = None,
    dataset_id: str | None = None,
) -> list[str]:
    problems: list[str] = []
    if not MAPPING_REQUIRED_FIELDS.issubset(record):
        problems.append("mapping record is missing required codebook fields")
        return problems
    if required_variable is not None and record.get("source_variable") != required_variable:
        problems.append("mapping source variable does not match the required variable")
    if dataset_id is not None and record.get("source_dataset_id") != dataset_id:
        problems.append("mapping belongs to a different dataset")
    if record.get("status") not in EVIDENCE_STATUSES:
        problems.append("mapping status is unsupported")
    for field in (
        "variable_meaning",
        "codebook_reference",
        "eligible_population",
        "denominator_definition",
        "missing_value_treatment",
        "evidence_reference",
    ):
        if not isinstance(record.get(field), str) or not record[field].strip():
            problems.append(f"{field} is not documented")
    if not _valid_reference(record.get("codebook_reference")):
        problems.append("codebook_reference is not a valid document reference")
    if not _valid_reference(record.get("evidence_reference")):
        problems.append("evidence_reference is not a valid document reference")
    if not isinstance(record.get("response_coding"), (dict, list, str)) or not record.get("response_coding"):
        problems.append("response_coding is not documented")
    return list(dict.fromkeys(problems))


def validate_mapping_records(
    records: Any,
    *,
    indicator_id: str,
    dataset_ids: Iterable[str],
    codebook_references: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate mapping metadata without opening a source or codebook."""

    if records is None:
        return []
    if not isinstance(records, list):
        raise IndicatorDefinitionError("Indicator mapping_records must be a list.")
    known_dataset_ids = set(dataset_ids)
    known_codebook_references = {
        str(reference).split("#", 1)[0]
        for reference in (codebook_references or ())
        if isinstance(reference, str) and reference.strip()
    }
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or not MAPPING_REQUIRED_FIELDS.issubset(record):
            raise IndicatorDefinitionError("Each indicator mapping record is missing required evidence fields.")
        source_dataset_id = record.get("source_dataset_id")
        source_variable = record.get("source_variable")
        if not isinstance(source_dataset_id, str) or source_dataset_id not in known_dataset_ids:
            raise IndicatorDefinitionError("Indicator mapping references an unknown dataset ID.")
        if not isinstance(source_variable, str) or not source_variable.strip():
            raise IndicatorDefinitionError("Indicator mappings require a non-empty source variable.")
        if "indicator_id" in record and record.get("indicator_id") != indicator_id:
            raise IndicatorDefinitionError("Indicator mapping has a conflicting indicator ID.")
        status = record.get("status")
        if status not in EVIDENCE_STATUSES:
            raise IndicatorDefinitionError("Indicator mapping status is not supported.")
        key = (source_dataset_id, source_variable)
        if key in seen:
            raise IndicatorDefinitionError("Indicator mappings must not duplicate a dataset and source variable.")
        seen.add(key)
        for field in ("variable_meaning", "codebook_reference", "eligible_population", "denominator_definition", "missing_value_treatment", "evidence_reference"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise IndicatorDefinitionError(f"Indicator mapping field '{field}' must be documented.")
        if not _valid_reference(record.get("codebook_reference")):
            raise IndicatorDefinitionError("Indicator mappings require a safe codebook reference.")
        if known_codebook_references:
            codebook_reference = str(record["codebook_reference"]).split("#", 1)[0]
            if codebook_reference not in known_codebook_references:
                raise IndicatorDefinitionError("Indicator mapping codebook reference is not in the documented source references.")
        if not _valid_reference(record.get("evidence_reference")):
            raise IndicatorDefinitionError("Indicator mappings require a safe evidence reference.")
        if not isinstance(record.get("response_coding"), (dict, list, str)) or not record["response_coding"]:
            raise IndicatorDefinitionError("Indicator mappings require documented response coding.")
        normalized.append(dict(record, indicator_id=indicator_id))
    return normalized


def mapping_readiness(
    records: Iterable[dict[str, Any]],
    *,
    required_variables: Iterable[str],
    dataset_id: str | None = None,
    available_columns: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return deterministic mapping blockers for one indicator."""

    mappings = [record for record in records if isinstance(record, dict)]
    required = list(dict.fromkeys(str(variable) for variable in required_variables))
    by_variable = {
        record.get("source_variable"): record
        for record in mappings
        if isinstance(record.get("source_variable"), str)
        and (dataset_id is None or record.get("source_dataset_id") == dataset_id)
    }
    blockers: list[str] = []
    verified_variables: list[str] = []
    for variable in required:
        record = by_variable.get(variable)
        if record is None:
            blockers.append(f"No documented mapping for source variable '{variable}'.")
            continue
        record_problems = _mapping_record_problems(record, required_variable=variable, dataset_id=dataset_id)
        if record_problems:
            blockers.append(
                f"Mapping for source variable '{variable}' is incomplete: "
                + "; ".join(record_problems)
                + "."
            )
            continue
        if record.get("status") != "verified":
            blockers.append(f"Mapping for source variable '{variable}' is not independently verified.")
            continue
        if available_columns is not None and variable not in {str(column) for column in available_columns}:
            blockers.append(f"Verified source variable '{variable}' is absent from the available schema.")
            continue
        verified_variables.append(variable)
    return {
        "required_variable_count": len(required),
        "documented_mapping_count": len(mappings),
        "verified_variable_count": len(verified_variables),
        "verified_variables": verified_variables,
        "status": "verified" if required and len(verified_variables) == len(required) and not blockers else "blocked",
        "blockers": blockers,
    }


def summarize_mapping_records(
    catalogue: dict[str, dict[str, Any]],
    *,
    dataset_ids: Iterable[str],
    codebook_references: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Summarize catalogue mapping coverage without calculating indicators."""

    status_counts: Counter[str] = Counter()
    known_dataset_ids = set(dataset_ids)
    mapped_indicators = 0
    verified_indicators = 0
    rows: list[dict[str, Any]] = []
    for indicator_id, definition in sorted(catalogue.items()):
        records = validate_mapping_records(
            definition.get("mapping_records", []),
            indicator_id=indicator_id,
            dataset_ids=known_dataset_ids,
            codebook_references=codebook_references,
        )
        required_variables = {
            str(variable)
            for variable in definition.get("required_variables", [])
            if isinstance(variable, str) and variable.strip()
        }
        mapped_variables = {
            str(record.get("source_variable"))
            for record in records
            if isinstance(record.get("source_variable"), str)
        }
        variables_by_dataset: dict[str, set[str]] = {}
        for record in records:
            dataset_id = record.get("source_dataset_id")
            variable = record.get("source_variable")
            if isinstance(dataset_id, str) and isinstance(variable, str):
                variables_by_dataset.setdefault(dataset_id, set()).add(variable)
        complete_dataset_ids = [
            dataset_id
            for dataset_id, variables in variables_by_dataset.items()
            if required_variables and required_variables.issubset(variables)
        ]
        complete = len(complete_dataset_ids) == 1
        status = "verified" if records and complete and all(
            not _mapping_record_problems(record) and record.get("status") == "verified"
            for record in records
        ) else "unverified"
        if not required_variables:
            blockers = ["The indicator catalogue does not define required source variables."]
        elif not records:
            blockers = ["No documented codebook mapping records are present."]
        elif not complete:
            blockers = ["Mapping records do not cover every required source variable in exactly one dataset."]
        elif status != "verified":
            blockers = ["Each mapping requires independently verified status and valid codebook evidence."]
        else:
            blockers = []
        status_counts[status] += 1
        mapped_indicators += bool(records)
        verified_indicators += status == "verified"
        rows.append(
            {
                "indicator_id": indicator_id,
                "display_name": definition.get("display_name"),
                "mapping_status": status,
                "mapping_count": len(records),
                "evidence_references": [record.get("evidence_reference") for record in records],
                "required_variables": sorted(required_variables),
                "mapped_variables": sorted(mapped_variables),
                "blockers": blockers,
            }
        )
    return {
        "indicator_count": len(catalogue),
        "indicators_with_documented_mappings": int(mapped_indicators),
        "indicators_with_verified_mappings": int(verified_indicators),
        "status_counts": dict(sorted(status_counts.items())),
        "rows": rows,
    }
