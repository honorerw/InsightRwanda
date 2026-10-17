"""Schema and structural validation without displaying row-level values."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import SchemaValidationError


def duplicate_column_names(columns: Iterable[Any]) -> tuple[str, ...]:
    """Return duplicate column names in first-seen order."""

    counts: dict[str, int] = {}
    ordered: list[str] = []
    for column in columns:
        name = str(column)
        counts[name] = counts.get(name, 0) + 1
        if counts[name] == 2:
            ordered.append(name)
    return tuple(ordered)


def check_expected_columns(frame: Any, expected_columns: Iterable[str]) -> tuple[str, ...]:
    """Return expected columns that are absent, without inspecting cell values."""

    actual = {str(column) for column in getattr(frame, "columns", ())}
    return tuple(str(column) for column in expected_columns if str(column) not in actual)


def missingness_summary(frame: Any) -> tuple[dict[str, Any], ...]:
    """Return per-column missing counts and fractions without returning values."""

    row_count = len(frame)
    summaries: list[dict[str, Any]] = []
    for index, column in enumerate(frame.columns):
        series = frame.iloc[:, index]
        missing_count = int(series.isna().sum())
        summaries.append(
            {
                "column": str(column),
                "missing_count": missing_count,
                "missing_fraction": (missing_count / row_count) if row_count else None,
            }
        )
    return tuple(summaries)


@dataclass(frozen=True)
class DataFrameValidationReport:
    """Non-sensitive validation metadata for a selected DataFrame."""

    row_count: int
    column_count: int
    columns: tuple[str, ...]
    duplicate_columns: tuple[str, ...]
    missing_expected_columns: tuple[str, ...]
    dtypes: tuple[dict[str, str], ...]
    missingness: tuple[dict[str, Any], ...]


def validate_dataframe(frame: Any, expected_columns: Iterable[str] = ()) -> DataFrameValidationReport:
    """Summarize basic schema, dimensions, dtypes, and missingness."""

    columns = tuple(str(column) for column in frame.columns)
    dtypes = tuple(
        {"column": str(column), "dtype": str(frame.dtypes.iloc[index])}
        for index, column in enumerate(frame.columns)
    )
    return DataFrameValidationReport(
        row_count=len(frame),
        column_count=len(columns),
        columns=columns,
        duplicate_columns=duplicate_column_names(columns),
        missing_expected_columns=check_expected_columns(frame, expected_columns),
        dtypes=dtypes,
        missingness=missingness_summary(frame),
    )


def require_expected_columns(frame: Any, expected_columns: Iterable[str]) -> None:
    """Raise a schema error when required columns are absent."""

    missing = check_expected_columns(frame, expected_columns)
    if missing:
        raise SchemaValidationError("Required columns are missing from the selected source.")


def validate_geojson_structure(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate GeoJSON container structure without inspecting coordinates."""

    if not isinstance(document, Mapping) or document.get("type") != "FeatureCollection":
        raise SchemaValidationError("GeoJSON must be a FeatureCollection.")
    features = document.get("features")
    if not isinstance(features, list):
        raise SchemaValidationError("GeoJSON FeatureCollection must contain a features list.")
    for feature in features:
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise SchemaValidationError("Every GeoJSON feature must have type Feature.")
        geometry = feature.get("geometry")
        if geometry is not None and (
            not isinstance(geometry, Mapping) or not isinstance(geometry.get("type"), str)
        ):
            raise SchemaValidationError("GeoJSON feature geometry is malformed.")
        properties = feature.get("properties")
        if properties is not None and not isinstance(properties, Mapping):
            raise SchemaValidationError("GeoJSON feature properties must be an object or null.")
    return {
        "type": "FeatureCollection",
        "feature_count": len(features),
        "has_bbox": "bbox" in document,
    }

