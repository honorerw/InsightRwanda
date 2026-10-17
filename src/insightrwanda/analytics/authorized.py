"""Controlled analytical loading, calculation, and publication boundaries.

This module is the Phase 9 boundary between approved metadata and analytical
code. It reuses the central readiness service, loads only an explicitly
selected eligible source, and returns aggregate metadata rather than source
records from serialized results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from insightrwanda.data.errors import DataLoaderError, DataPathError, IndicatorDefinitionError
from insightrwanda.data.loaders import load_source
from insightrwanda.data.validation import check_expected_columns
from insightrwanda.data.source_verification import load_source_verification_matrix
from insightrwanda.data.registry import resolve_dataset_path

from .indicators import calculate_proportion, calculate_weighted_proportion
from .readiness import ReadinessResult, evaluate_indicator_readiness


@dataclass(frozen=True)
class AuthorizedLoadResult:
    """Safe decision and, only when eligible, an internal analytical frame."""

    status: str
    dataset_id: str | None
    readiness: ReadinessResult | None
    columns: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    source_version: str | None = None
    frame: pd.DataFrame | None = field(default=None, repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        """Return serializable metadata without source rows or the frame."""

        return {
            "status": self.status,
            "dataset_id": self.dataset_id,
            "columns": list(self.columns),
            "messages": list(self.messages),
            "source_version": self.source_version,
            "readiness": self.readiness.as_dict() if self.readiness else None,
        }


def _result(
    *,
    status: str,
    dataset: dict[str, Any] | None,
    readiness: ReadinessResult | None = None,
    messages: tuple[str, ...] = (),
    columns: tuple[str, ...] = (),
    frame: pd.DataFrame | None = None,
) -> AuthorizedLoadResult:
    return AuthorizedLoadResult(
        status=status,
        dataset_id=dataset.get("dataset_id") if isinstance(dataset, dict) else None,
        readiness=readiness,
        columns=columns,
        messages=messages,
        source_version=dataset.get("dataset_version") if isinstance(dataset, dict) else None,
        frame=frame,
    )


def load_authorized_dataset(
    definition: dict[str, Any],
    dataset: dict[str, Any] | None,
    *,
    project_root: str,
    requested_geography: bool = False,
    publication_requested: bool = False,
    allow_synthetic_test_data: bool = False,
) -> AuthorizedLoadResult:
    """Load one explicit source only after all analytical metadata gates pass.

    The preflight supplies the *verified* required variable names only to
    complete metadata checks. The source is loaded only when those checks pass;
    a second readiness evaluation uses the actual loaded schema before any
    calculation can use it.
    """

    if not isinstance(dataset, dict) or not isinstance(dataset.get("dataset_id"), str):
        return _result(
            status="blocked",
            dataset=dataset,
            messages=("An explicit registered dataset selection is required; no source was loaded.",),
        )

    required = definition.get("required_variables")
    required_columns = tuple(str(column) for column in required) if isinstance(required, list) else ()
    synthetic_test = allow_synthetic_test_data and dataset.get("is_synthetic") is True
    source_verification = None
    if not synthetic_test:
        try:
            matrix = load_source_verification_matrix(
                Path(project_root) / "data" / "metadata" / "source_verification.json",
                project_root=project_root,
            )
            source_verification = next(
                (item for item in matrix["sources"] if item.get("dataset_id") == dataset.get("dataset_id")),
                None,
            )
        except Exception:
            source_verification = None
    try:
        source_path = resolve_dataset_path(dataset, project_root=project_root)
        source_available = source_path.is_file()
    except (DataPathError, OSError, ValueError):
        source_path = None
        source_available = False
    preflight = evaluate_indicator_readiness(
        definition,
        dataset,
        available_columns=required_columns,
        requested_geography=requested_geography,
        publication_requested=publication_requested,
        require_research_evidence=True,
        require_data_quality=True,
        require_calculation_specification=True,
        require_mapping_evidence=True,
        source_verification=source_verification,
        source_available=source_available,
        allow_synthetic_test_data=synthetic_test,
    )
    if not preflight.eligible_for_requested_purpose:
        return _result(
            status="blocked",
            dataset=dataset,
            readiness=preflight,
            messages=("Analytical loading is blocked by the selected dataset or indicator evidence.",),
        )

    try:
        if source_path is None:
            raise DataPathError("The registered source could not be resolved.")
        loaded = load_source(source_path, project_root=project_root)
    except (DataPathError, DataLoaderError, OSError, ValueError, UnicodeError):
        return _result(
            status="error",
            dataset=dataset,
            readiness=preflight,
            messages=("The selected authorized source could not be safely loaded.",),
        )
    except Exception:
        return _result(
            status="error",
            dataset=dataset,
            readiness=preflight,
            messages=("The selected authorized source could not be safely loaded.",),
        )

    if not isinstance(loaded, pd.DataFrame):
        return _result(
            status="error",
            dataset=dataset,
            readiness=preflight,
            messages=("The selected source did not produce a supported tabular frame.",),
        )

    columns = tuple(str(column) for column in loaded.columns)
    missing = check_expected_columns(loaded, required_columns)
    final_readiness = evaluate_indicator_readiness(
        definition,
        dataset,
        available_columns=columns,
        requested_geography=requested_geography,
        publication_requested=publication_requested,
        require_research_evidence=True,
        require_data_quality=True,
        require_calculation_specification=True,
        require_mapping_evidence=True,
        source_verification=source_verification,
        source_available=source_available,
        allow_synthetic_test_data=synthetic_test,
    )
    if missing or not final_readiness.eligible_for_requested_purpose:
        return _result(
            status="blocked",
            dataset=dataset,
            readiness=final_readiness,
            columns=columns,
            messages=(
                "The selected source schema does not satisfy the verified indicator mapping."
                if missing
                else "Analytical calculation remains blocked after schema validation.",
            ),
        )

    return _result(
        status="loaded",
        dataset=dataset,
        readiness=final_readiness,
        columns=columns,
        frame=loaded,
    )


def calculate_authorized_proportion(
    loaded: AuthorizedLoadResult,
    definition: dict[str, Any],
    dataset: dict[str, Any],
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    weights: pd.Series | None = None,
    publication_requested: bool = False,
) -> dict[str, Any]:
    """Calculate one approved proportion from an eligible internal frame.

    Numerator and denominator masks must be created from a verified mapping by
    the caller. This function performs no response-code inference or recoding.
    """

    if loaded.status != "loaded" or loaded.frame is None or loaded.readiness is None:
        return blocked_calculation("The source is not analytically eligible; no calculation was performed.")
    if not loaded.readiness.analysis_eligible or (
        publication_requested and not loaded.readiness.publication_eligible
    ):
        return blocked_calculation("The requested calculation purpose is not eligible.")
    if definition.get("calculation_method") not in {"proportion", "weighted_proportion"}:
        return blocked_calculation("The approved calculation method is unavailable or unsupported.")
    if denominator is None:
        return blocked_calculation("An explicit denominator is required; no calculation was performed.")

    try:
        if definition.get("calculation_method") == "weighted_proportion":
            if weights is None:
                return blocked_calculation("The approved weighted calculation requires a verified weight column.")
            result = calculate_weighted_proportion(
                numerator,
                weights,
                denominator,
                indicator_id=str(definition.get("indicator_id", "UNNAMED")),
                source_authorization_status=str(dataset.get("authorization_status", "unverified")),
                indicator_definition_status=str(definition.get("status", "unavailable")),
            )
        else:
            result = calculate_proportion(
                numerator,
                denominator,
                indicator_id=str(definition.get("indicator_id", "UNNAMED")),
                source_authorization_status=str(dataset.get("authorization_status", "unverified")),
                indicator_definition_status=str(definition.get("status", "unavailable")),
            )
    except (IndicatorDefinitionError, TypeError, ValueError):
        return blocked_calculation("The supplied calculation masks or weights failed validation.")

    result.update(
        {
            "calculation_status": result.get("calculation_status", "calculated"),
            "validation_status": "validated" if result.get("estimate") is not None else "no_estimate",
            "definition_version": definition.get("definition_version", "unversioned"),
            "dataset_id": dataset.get("dataset_id"),
            "dataset_version": dataset.get("dataset_version", "unversioned"),
            "calculation_method": definition.get("calculation_method"),
            "numerator_definition": definition.get("numerator_definition"),
            "denominator_definition": definition.get("denominator_definition"),
            "publication_eligible": loaded.readiness.publication_eligible,
            "geographic_coverage": dataset.get("geographic_coverage"),
            "reporting_period": dataset.get("reporting_period"),
        }
    )
    return result


def blocked_calculation(message: str) -> dict[str, Any]:
    """Return a structured non-numeric calculation result."""

    return {
        "calculation_status": "blocked",
        "validation_status": "not_calculated",
        "estimate": None,
        "percentage": None,
        "eligible_for_publication": False,
        "blocked_checks": ["analytical_eligibility"],
        "messages": [message],
    }


def prepare_publication_aggregate(
    calculation: dict[str, Any],
    *,
    disclosure_review_status: str,
    minimum_cell_count: int | None,
) -> dict[str, Any]:
    """Gate an aggregate result for publication without exposing raw data."""

    blocked: list[str] = []
    messages: list[str] = []
    if calculation.get("calculation_status") != "calculated":
        blocked.append("calculated_result")
        messages.append("Only a successfully validated aggregate can enter publication review.")
    if calculation.get("publication_eligible") is not True:
        blocked.append("publication_permission")
        messages.append("Dataset and indicator publication permission is not approved.")
    if disclosure_review_status != "approved":
        blocked.append("disclosure_review")
        messages.append("Disclosure review is not approved.")
    if minimum_cell_count is None or minimum_cell_count < 1:
        blocked.append("disclosure_rule")
        messages.append("An approved minimum-cell disclosure rule is required.")
    elif int(calculation.get("denominator_count", 0)) < minimum_cell_count:
        blocked.append("minimum_cell_count")
        messages.append("The aggregate does not meet the approved minimum-cell threshold.")

    if blocked:
        return {
            "publication_status": "blocked",
            "publication_eligible": False,
            "blocked_checks": blocked,
            "messages": list(dict.fromkeys(messages)),
        }
    return {
        "publication_status": "approved_for_release",
        "publication_eligible": True,
        "indicator_id": calculation.get("indicator_id"),
        "dataset_id": calculation.get("dataset_id"),
        "estimate": calculation.get("estimate"),
        "percentage": calculation.get("percentage"),
        "denominator_count": calculation.get("denominator_count"),
        "calculation_method": calculation.get("calculation_method"),
    }
