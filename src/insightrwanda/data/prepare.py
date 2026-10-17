"""Explicit, conservative preparation for one selected tabular source.

The pipeline performs no implicit cleaning, joining, deduplication, imputation,
outlier removal, or weight application. Every transformation is supplied by a
caller and recorded in a metadata report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import DataPreparationError, SchemaValidationError
from .loaders import load_source
from .paths import resolve_approved_data_path, resolve_derived_output_path, safe_relative_path
from .quality import is_identifier_like_name
from .validation import check_expected_columns, validate_dataframe


@dataclass(frozen=True)
class PreparationConfig:
    """Explicit preparation choices; empty transformations preserve the frame."""

    required_columns: tuple[str, ...] = ()
    rename_columns: dict[str, str] = field(default_factory=dict)
    cast_columns: dict[str, str] = field(default_factory=dict)
    weight_columns: tuple[str, ...] = ()
    source_authorization_status: str = "unverified"
    allow_unverified_source: bool = False


def _check_transform_columns(frame: pd.DataFrame, config: PreparationConfig) -> None:
    missing_required = check_expected_columns(frame, config.required_columns)
    missing_rename = check_expected_columns(frame, config.rename_columns)
    if missing_required or missing_rename:
        raise SchemaValidationError("Required or explicitly renamed columns are missing from the source.")


def _apply_transformations(frame: pd.DataFrame, config: PreparationConfig) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    _check_transform_columns(frame, config)
    transformed = frame
    transformations: list[dict[str, Any]] = []
    if config.rename_columns:
        renamed_columns = [config.rename_columns.get(str(column), str(column)) for column in transformed.columns]
        if len(set(renamed_columns)) != len(renamed_columns):
            raise DataPreparationError("Explicit column renaming would create duplicate column names.")
        transformed = transformed.rename(columns=config.rename_columns)
        transformations.append({"operation": "rename_columns", "columns": dict(config.rename_columns)})

    missing_cast = check_expected_columns(transformed, config.cast_columns)
    if missing_cast:
        raise SchemaValidationError("Explicit cast columns are missing after renaming.")
    for column, target_dtype in config.cast_columns.items():
        if is_identifier_like_name(column) and str(target_dtype).lower() not in {"string", "str", "object"}:
            raise DataPreparationError(
                f"Refusing to cast candidate identifier column '{column}' to a numeric or unknown dtype."
            )
    if config.cast_columns:
        try:
            transformed = transformed.astype(config.cast_columns)
        except (TypeError, ValueError) as exc:
            raise DataPreparationError("An explicit column cast failed; no fallback coercion was attempted.") from exc
        transformations.append({"operation": "cast_columns", "columns": dict(config.cast_columns)})
    missing_weights = check_expected_columns(transformed, config.weight_columns)
    if missing_weights:
        raise SchemaValidationError("Configured survey-weight columns are missing after transformations.")
    return transformed, transformations


def _write_frame(frame: pd.DataFrame, output_path: Path) -> None:
    suffix = output_path.suffix.lower()
    try:
        if suffix == ".csv":
            frame.to_csv(output_path, index=False)
        elif suffix == ".parquet":
            frame.to_parquet(output_path, index=False)
        else:
            raise DataPreparationError("Prepared outputs must use .csv or .parquet format.")
    except DataPreparationError:
        raise
    except (OSError, ImportError, ValueError, TypeError) as exc:
        raise DataPreparationError("The prepared output could not be written safely.") from exc


def prepare_dataset(
    input_path: str | Path,
    output_path: str | Path,
    *,
    project_root: str | Path | None = None,
    config: PreparationConfig | None = None,
) -> dict[str, Any]:
    """Prepare one selected tabular source and return its safe metadata report.

    By default, unverified sources are refused for record-preserving output.
    A caller may explicitly allow a local unverified preparation, but the
    resulting metadata remains unverified and ineligible for publication.
    """

    config = config or PreparationConfig()
    source = resolve_approved_data_path(input_path, project_root=project_root)
    output = resolve_derived_output_path(output_path, project_root=project_root)
    if source == output:
        raise DataPreparationError("The prepared output must not overwrite the selected source file.")
    if output.exists():
        raise DataPreparationError("The prepared output already exists; refusing to overwrite it.")
    metadata_path = output.with_name(f"{output.stem}.metadata.json")
    if metadata_path.exists():
        raise DataPreparationError("The preparation metadata output already exists; refusing to overwrite it.")

    allowed_status = {"approved", "synthetic_test"}
    if config.source_authorization_status not in allowed_status and not config.allow_unverified_source:
        raise DataPreparationError(
            "Source authorization is not approved. Set allow_unverified_source=True only for controlled local work."
        )

    try:
        loaded = load_source(source, project_root=project_root)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit, DataPreparationError)):
            raise
        raise DataPreparationError("The selected source could not be loaded for preparation.") from exc
    if not isinstance(loaded, pd.DataFrame):
        raise DataPreparationError("Preparation currently supports tabular DataFrame sources only.")

    transformed, transformations = _apply_transformations(loaded, config)
    validation = validate_dataframe(transformed, expected_columns=config.required_columns)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_frame(transformed, output)

    warnings = [
        "This preparation report does not establish source authorization or publication eligibility.",
        "No automatic cleaning, deduplication, imputation, outlier removal, weighting, or survey linkage was performed.",
    ]
    if config.source_authorization_status not in allowed_status:
        warnings.append("The source authorization status remains unverified or review-required.")
    report = {
        "preparation_version": 1,
        "input_path": safe_relative_path(source, project_root=project_root),
        "output_path": safe_relative_path(output, project_root=project_root),
        "output_format": output.suffix.lower().lstrip("."),
        "source_authorization_status": config.source_authorization_status,
        "eligible_for_publication": False,
        "row_count": validation.row_count,
        "column_count": validation.column_count,
        "columns": list(validation.columns),
        "required_columns": list(config.required_columns),
        "weight_columns_preserved": list(config.weight_columns),
        "transformations": transformations,
        "warnings": warnings,
        "limitations": [
            "The pipeline processes one explicit input and never links separate surveys.",
            "Survey weights remain columns and are not automatically applied.",
            "Domain review is required for variable meaning, missing-value codes, linkage, and representativeness.",
        ],
    }
    metadata_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report

