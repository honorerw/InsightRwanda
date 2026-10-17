"""Explicit, path-safe loaders for supported InsightRwanda source formats.

Loading a file is not authorization to analyze, redistribute, or publish it.
Callers must select a specific source path. These functions never enumerate
the data directory or print loaded content.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import (
    DataLoaderError,
    OptionalDependencyError,
    UnsupportedFormatError,
)
from .paths import resolve_approved_data_path, safe_relative_path
from .validation import validate_geojson_structure


_IDENTIFIER_TOKEN = re.compile(r"(?:^|_)(?:id|key|code|uuid|identifier|surveyid)(?:$|_)", re.IGNORECASE)


def _pandas():
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - requirements currently include pandas
        raise OptionalDependencyError("Pandas is required for tabular data loading.") from exc
    return pd


def _identifier_columns(columns: list[Any]) -> list[str]:
    return [str(column) for column in columns if _IDENTIFIER_TOKEN.search(str(column))]


def _protected_dtype(columns: list[Any], dtype: Mapping[str, Any] | None) -> dict[str, Any]:
    if dtype is not None and not isinstance(dtype, Mapping):
        raise DataLoaderError("The dtype argument must be a mapping of column names to types.")
    protected = dict(dtype or {})
    for column in _identifier_columns(columns):
        protected.setdefault(column, "string")
    return protected


def _csv_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            return next(csv.reader(handle), [])
    except (OSError, csv.Error) as exc:
        raise DataLoaderError("The CSV header could not be read safely.") from exc


def _display(path: Path, project_root: str | Path | None) -> str:
    return safe_relative_path(path, project_root=project_root)


def load_csv(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    dtype: Mapping[str, Any] | None = None,
    **read_csv_kwargs: Any,
):
    """Load one approved CSV while preserving identifier-like columns as strings."""

    resolved = resolve_approved_data_path(path, project_root=project_root)
    if resolved.suffix.lower() != ".csv":
        raise UnsupportedFormatError("The selected source is not a CSV file.")
    if "dtype" in read_csv_kwargs:
        raise DataLoaderError("Pass dtype as the explicit mapping argument.")
    pd = _pandas()
    protected_dtype = _protected_dtype(_csv_header(resolved), dtype)
    try:
        return pd.read_csv(resolved, dtype=protected_dtype, **read_csv_kwargs)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise DataLoaderError(f"Could not load CSV '{_display(resolved, project_root)}'.") from exc


def _load_excel(
    path: str | Path,
    *,
    project_root: str | Path | None,
    engine: str,
    dependency_name: str,
    dtype: Mapping[str, Any] | None,
    sheet_name: int | str = 0,
    **read_excel_kwargs: Any,
):
    resolved = resolve_approved_data_path(path, project_root=project_root)
    pd = _pandas()
    try:
        __import__(dependency_name)
    except ImportError as exc:
        raise OptionalDependencyError(
            f"Loading this format requires optional dependency '{dependency_name}'."
        ) from exc
    if "dtype" in read_excel_kwargs:
        raise DataLoaderError("Pass dtype as the explicit mapping argument.")
    try:
        header_frame = pd.read_excel(
            resolved,
            sheet_name=sheet_name,
            engine=engine,
            nrows=0,
        )
        protected_dtype = _protected_dtype(list(header_frame.columns), dtype)
        return pd.read_excel(
            resolved,
            sheet_name=sheet_name,
            engine=engine,
            dtype=protected_dtype,
            **read_excel_kwargs,
        )
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit, OptionalDependencyError)):
            raise
        raise DataLoaderError(f"Could not load spreadsheet '{_display(resolved, project_root)}'.") from exc


def load_xlsx(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    dtype: Mapping[str, Any] | None = None,
    sheet_name: int | str = 0,
    **read_excel_kwargs: Any,
):
    """Load one XLSX worksheet; requires the optional ``openpyxl`` reader."""

    resolved = resolve_approved_data_path(path, project_root=project_root)
    if resolved.suffix.lower() != ".xlsx":
        raise UnsupportedFormatError("The selected source is not an XLSX file.")
    return _load_excel(
        resolved,
        project_root=project_root,
        engine="openpyxl",
        dependency_name="openpyxl",
        dtype=dtype,
        sheet_name=sheet_name,
        **read_excel_kwargs,
    )


def load_xls(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    dtype: Mapping[str, Any] | None = None,
    sheet_name: int | str = 0,
    **read_excel_kwargs: Any,
):
    """Load one legacy XLS worksheet; requires the optional ``xlrd`` reader."""

    resolved = resolve_approved_data_path(path, project_root=project_root)
    if resolved.suffix.lower() != ".xls":
        raise UnsupportedFormatError("The selected source is not a legacy XLS file.")
    return _load_excel(
        resolved,
        project_root=project_root,
        engine="xlrd",
        dependency_name="xlrd",
        dtype=dtype,
        sheet_name=sheet_name,
        **read_excel_kwargs,
    )


def load_stata(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    **read_stata_kwargs: Any,
):
    """Load one Stata file with categorical conversion disabled by default.

    Pandas reads the selected file; it does not recursively discover or load
    other files. Identifier-like columns are converted to strings after load so
    callers do not silently receive numeric identifiers from this loader.
    ``pyreadstat`` is not required for basic loading but may be useful later for
    richer Stata labels and survey metadata.
    """

    resolved = resolve_approved_data_path(path, project_root=project_root)
    if resolved.suffix.lower() != ".dta":
        raise UnsupportedFormatError("The selected source is not a Stata file.")
    if "convert_categoricals" in read_stata_kwargs:
        raise DataLoaderError("convert_categoricals is controlled by this loader.")
    pd = _pandas()
    try:
        frame = pd.read_stata(resolved, convert_categoricals=False, **read_stata_kwargs)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise DataLoaderError(f"Could not load Stata source '{_display(resolved, project_root)}'.") from exc
    for column in _identifier_columns(list(frame.columns)):
        if column in frame.columns:
            frame[column] = frame[column].astype("string")
    return frame


def load_geojson(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
):
    """Load and structurally validate one GeoJSON document."""

    resolved = resolve_approved_data_path(path, project_root=project_root)
    if resolved.suffix.lower() != ".geojson":
        raise UnsupportedFormatError("The selected source is not a GeoJSON file.")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        validate_geojson_structure(document)
        return document
    except json.JSONDecodeError as exc:
        raise DataLoaderError(f"Could not parse GeoJSON '{_display(resolved, project_root)}'.") from exc


def load_source(path: str | Path, *, project_root: str | Path | None = None, **kwargs: Any):
    """Dispatch to a loader for one explicitly selected supported source."""

    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return load_csv(path, project_root=project_root, **kwargs)
    if suffix == ".xlsx":
        return load_xlsx(path, project_root=project_root, **kwargs)
    if suffix == ".xls":
        return load_xls(path, project_root=project_root, **kwargs)
    if suffix == ".dta":
        return load_stata(path, project_root=project_root, **kwargs)
    if suffix == ".geojson":
        return load_geojson(path, project_root=project_root)
    raise UnsupportedFormatError(f"No loader is registered for the '{suffix or 'unknown'}' format.")

