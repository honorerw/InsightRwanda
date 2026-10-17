"""Load and validate the machine-readable indicator catalogue."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from insightrwanda.data.errors import IndicatorDefinitionError
from insightrwanda.data.evidence import EVIDENCE_STATUSES


REQUIRED_FIELDS = {
    "indicator_id",
    "display_name",
    "description",
    "status",
    "required_variables",
    "authorization_status",
    "publication_status",
}


def load_indicator_catalogue(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load catalogue definitions without reading any survey source data."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndicatorDefinitionError("The indicator catalogue could not be read safely.") from exc
    definitions = document.get("indicators") if isinstance(document, dict) else None
    if not isinstance(definitions, list):
        raise IndicatorDefinitionError("The indicator catalogue must contain an indicators list.")
    catalogue: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, dict) or not REQUIRED_FIELDS.issubset(definition):
            raise IndicatorDefinitionError("Each indicator definition is missing required metadata fields.")
        indicator_id = definition["indicator_id"]
        if not isinstance(indicator_id, str) or not indicator_id:
            raise IndicatorDefinitionError("Each indicator must have a non-empty string indicator_id.")
        if indicator_id in catalogue:
            raise IndicatorDefinitionError("Indicator IDs must be unique.")
        if not isinstance(definition["required_variables"], list):
            raise IndicatorDefinitionError("required_variables must be a list.")
        review = definition.get("definition_review")
        if review is not None:
            if not isinstance(review, dict) or not isinstance(review.get("fields"), list):
                raise IndicatorDefinitionError("definition_review must contain a fields list.")
            seen_fields = set()
            for field in review["fields"]:
                if not isinstance(field, dict) or not all(key in field for key in ("field_id", "label", "status", "value", "evidence_reference", "next_action")):
                    raise IndicatorDefinitionError("Each definition review field is missing required metadata.")
                if field["field_id"] in seen_fields or field["status"] not in EVIDENCE_STATUSES:
                    raise IndicatorDefinitionError("Definition review IDs must be unique and statuses supported.")
                if field.get("value") is not None and not isinstance(field.get("value"), str):
                    raise IndicatorDefinitionError("Definition review values must be text or null.")
                for optional_text in ("evidence_reference", "release_identifier", "reviewer", "review_date", "next_action"):
                    if field.get(optional_text) is not None and not isinstance(field.get(optional_text), str):
                        raise IndicatorDefinitionError(f"Definition review {optional_text} must be text or null.")
                seen_fields.add(field["field_id"])
                if field["status"] == "verified" and not all(field.get(key) for key in ("value", "evidence_reference", "reviewer", "review_date", "release_identifier")):
                    raise IndicatorDefinitionError("Verified definition fields require value, evidence, reviewer, date, and exact release.")
                if field.get("review_date"):
                    try:
                        date.fromisoformat(field["review_date"])
                    except (TypeError, ValueError) as exc:
                        raise IndicatorDefinitionError("Definition review dates must use ISO format.") from exc
        catalogue[indicator_id] = definition
    return catalogue


def get_indicator(catalogue: dict[str, dict[str, Any]], indicator_id: str) -> dict[str, Any]:
    """Return one definition or raise a non-sensitive missing-ID error."""

    try:
        return catalogue[indicator_id]
    except KeyError as exc:
        raise IndicatorDefinitionError("The requested indicator ID is not in the catalogue.") from exc

