"""Aggregate data-quality profiling for one explicitly selected dataset.

The profiler reports schema and aggregate quality facts only. It does not
return row values, coordinates, or identifier values, and it does not decide
whether a source is authorized for analysis or publication.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .errors import DataPathError
from .paths import resolve_derived_output_path
from .validation import duplicate_column_names


_IDENTIFIER_NAME_PATTERN = re.compile(
    r"(?:^|_)(?:id|key|code|uuid|identifier|surveyid)(?:$|_)", re.IGNORECASE
)
_WEIGHT_NAME_PATTERN = re.compile(
    r"(?:^|_)(?:wt|wgt|weight|weights|ponder|expansion|factor)(?:$|_)", re.IGNORECASE
)


@dataclass(frozen=True)
class QualityConfig:
    """Configurable heuristics; none are claims about substantive validity."""

    near_constant_threshold: float = 0.99
    identifier_unique_ratio: float = 0.98
    source_authorization_status: str = "unverified"
    include_numeric_summaries: bool = True

    def __post_init__(self) -> None:
        if not 0 < self.near_constant_threshold <= 1:
            raise ValueError("near_constant_threshold must be greater than 0 and at most 1.")
        if not 0 < self.identifier_unique_ratio <= 1:
            raise ValueError("identifier_unique_ratio must be greater than 0 and at most 1.")


def is_identifier_like_name(name: Any) -> bool:
    """Return whether a name is a candidate identifier label, not proof of role."""

    return bool(_IDENTIFIER_NAME_PATTERN.search(str(name)))


def is_weight_like_name(name: Any) -> bool:
    """Return whether a name is a candidate survey-weight label."""

    return bool(_WEIGHT_NAME_PATTERN.search(str(name)))


def _json_number(value: Any) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if np.isfinite(number) else None


def _finite_numeric(series: pd.Series) -> tuple[pd.Series, int]:
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype="float64", na_value=np.nan)
    finite = np.isfinite(values)
    non_finite_count = int((~finite & ~np.isnan(values)).sum())
    return numeric[finite], non_finite_count


def _unique_count(series: pd.Series, *, dropna: bool) -> int | None:
    try:
        return int(series.nunique(dropna=dropna))
    except (TypeError, ValueError):
        return None


def _numeric_summary(series: pd.Series) -> dict[str, Any] | None:
    if not pd.api.types.is_numeric_dtype(series):
        return None
    finite, non_finite_count = _finite_numeric(series)
    if finite.empty:
        return {
            "finite_count": 0,
            "non_finite_count": non_finite_count,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "median": None,
        }
    return {
        "finite_count": int(len(finite)),
        "non_finite_count": non_finite_count,
        "min": _json_number(finite.min()),
        "max": _json_number(finite.max()),
        "mean": _json_number(finite.mean()),
        "std": _json_number(finite.std(ddof=1)) if len(finite) > 1 else None,
        "median": _json_number(finite.median()),
    }


def _column_profile(
    series: pd.Series,
    *,
    row_count: int,
    config: QualityConfig,
) -> dict[str, Any]:
    missing_count = int(series.isna().sum())
    non_null_count = row_count - missing_count
    unique_non_null = _unique_count(series, dropna=True)
    unique_including_missing = _unique_count(series, dropna=False)
    constant = unique_including_missing == 1 if unique_including_missing is not None else None
    near_constant = None
    try:
        frequencies = series.value_counts(dropna=False)
        top_frequency = int(frequencies.iloc[0]) if not frequencies.empty else 0
        near_constant = bool(row_count > 0 and top_frequency / row_count >= config.near_constant_threshold)
    except (TypeError, ValueError):
        top_frequency = None

    unique_ratio = None
    if non_null_count > 0 and unique_non_null is not None:
        unique_ratio = unique_non_null / non_null_count

    result: dict[str, Any] = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "row_count": row_count,
        "missing_count": missing_count,
        "missing_percentage": (missing_count / row_count * 100) if row_count else None,
        "non_null_unique_count": unique_non_null,
        "non_null_unique_ratio": unique_ratio,
        "constant": constant,
        "near_constant": near_constant,
        "top_frequency": top_frequency,
    }
    if config.include_numeric_summaries:
        result["numeric_summary"] = _numeric_summary(series)
    return result


def _identifier_candidates(
    frame: pd.DataFrame,
    *,
    config: QualityConfig,
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw_name in enumerate(frame.columns):
        name = str(raw_name)
        series = frame.iloc[:, index]
        profile = _column_profile(series, row_count=len(frame), config=config)
        reasons: list[str] = []
        if is_identifier_like_name(name):
            reasons.append("identifier_like_name")
        ratio = profile["non_null_unique_ratio"]
        if ratio is not None and ratio >= config.identifier_unique_ratio:
            reasons.append("high_non_null_uniqueness")
        if reasons:
            candidates.append(
                {
                    "column": name,
                    "reasons": reasons,
                    "dtype": profile["dtype"],
                    "non_null_unique_ratio": ratio,
                }
            )
        if is_identifier_like_name(name) and pd.api.types.is_numeric_dtype(series):
            warnings.append(
                f"Candidate identifier column '{name}' has a numeric dtype; review whether leading zeros or semantic codes were lost."
            )
    return candidates, warnings


def _weight_checks(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw_name in enumerate(frame.columns):
        name = str(raw_name)
        if not is_weight_like_name(name):
            continue
        series = frame.iloc[:, index]
        numeric = pd.to_numeric(series, errors="coerce")
        invalid_count = int((series.notna() & numeric.isna()).sum())
        finite, non_finite_count = _finite_numeric(series)
        zero_count = int((finite == 0).sum())
        negative_count = int((finite < 0).sum())
        result = {
            "column": name,
            "dtype": str(series.dtype),
            "missing_count": int(series.isna().sum()),
            "invalid_count": invalid_count,
            "zero_count": zero_count,
            "negative_count": negative_count,
            "non_finite_count": non_finite_count,
        }
        checks.append(result)
        if invalid_count or non_finite_count:
            warnings.append(f"Candidate survey-weight column '{name}' contains values requiring numeric review.")
        if zero_count:
            warnings.append(f"Candidate survey-weight column '{name}' contains zero weights; review survey documentation.")
        if negative_count:
            warnings.append(f"Candidate survey-weight column '{name}' contains negative weights; review survey documentation.")
    return checks, warnings


def profile_dataframe(
    frame: pd.DataFrame,
    *,
    config: QualityConfig | None = None,
) -> dict[str, Any]:
    """Return aggregate quality metadata for one already selected DataFrame.

    Exact duplicate rows use pandas' row-wise duplicate operation. This is
    accurate but may allocate additional memory proportional to the selected
    DataFrame; callers should not apply it indiscriminately to every source.
    """

    config = config or QualityConfig()
    row_count, column_count = frame.shape
    columns = [str(column) for column in frame.columns]
    duplicate_columns = list(duplicate_column_names(columns))
    column_profiles = [
        _column_profile(frame.iloc[:, index].rename(str(column)), row_count=row_count, config=config)
        for index, column in enumerate(frame.columns)
    ]
    identifier_candidates, identifier_warnings = _identifier_candidates(frame, config=config)
    weight_checks, weight_warnings = _weight_checks(frame)
    warnings = [
        *identifier_warnings,
        *weight_warnings,
        "Missingness is descriptive and is not, by itself, evidence of an error.",
        "Candidate identifier and weight roles require review against a codebook or survey documentation.",
        "This profile does not establish representativeness, survey design validity, linkage validity, or publication authorization.",
    ]
    try:
        duplicate_row_count: int | None = int(frame.duplicated(keep="first").sum())
        duplicate_method = "pandas.DataFrame.duplicated(keep='first')"
    except (TypeError, ValueError):
        duplicate_row_count = None
        duplicate_method = "unavailable_for_selected_types"
        warnings.append("Exact duplicate-row profiling was unavailable for one or more selected column types.")

    constant_columns = [profile["name"] for profile in column_profiles if profile["constant"] is True]
    near_constant_columns = [profile["name"] for profile in column_profiles if profile["near_constant"] is True]
    numeric_columns = [
        profile["name"]
        for profile in column_profiles
        if profile["numeric_summary"] is not None
    ]
    return {
        "profile_version": 1,
        "profile_scope": "one_explicitly_selected_dataframe",
        "source_authorization_status": config.source_authorization_status,
        "eligible_for_publication": False,
        "row_count": int(row_count),
        "column_count": int(column_count),
        "columns": column_profiles,
        "duplicate_column_names": duplicate_columns,
        "duplicate_row_count": duplicate_row_count,
        "duplicate_row_count_method": duplicate_method,
        "constant_columns": constant_columns,
        "near_constant_columns": near_constant_columns,
        "numeric_columns": numeric_columns,
        "candidate_identifier_columns": identifier_candidates,
        "candidate_weight_columns": weight_checks,
        "warnings": list(dict.fromkeys(warnings)),
        "limitations": [
            "Heuristics identify candidates for review and do not establish semantic roles.",
            "No records, identifiers, coordinates, or cell values are included in this report.",
            "No records, columns, missing values, or outliers are automatically removed or transformed.",
            "Survey weights and missing-value meanings require source documentation and domain review.",
        ],
    }


def profile_geojson(document: dict[str, Any], *, authorization_status: str = "unverified") -> dict[str, Any]:
    """Return safe structural metadata for one loaded GeoJSON document."""

    features = document.get("features", [])
    geometry_types = Counter(
        feature.get("geometry", {}).get("type")
        for feature in features
        if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict)
    )
    return {
        "profile_version": 1,
        "profile_scope": "one_explicitly_selected_geojson_document",
        "source_authorization_status": authorization_status,
        "eligible_for_publication": False,
        "geojson_type": document.get("type"),
        "feature_count": len(features),
        "geometry_type_counts": dict(sorted(geometry_types.items())),
        "warnings": [
            "GeoJSON structure does not establish licensing, boundary validity, or analytical comparability.",
            "Feature properties and coordinates are intentionally excluded from this report.",
        ],
        "limitations": [
            "Boundary source, vintage, and publication permission require separate review.",
        ],
    }


def write_quality_report(
    report: dict[str, Any],
    output_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> Path:
    """Write a JSON quality report only to an approved generated-data path."""

    try:
        resolved = resolve_derived_output_path(output_path, project_root=project_root)
    except DataPathError:
        raise
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return resolved

