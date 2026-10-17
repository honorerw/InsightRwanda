"""Build a conservative, non-row-level inventory of files below ``data``."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .metadata import (
    format_for_path,
    sensitivity_for_path,
    sha256_file,
    source_organization_for_path,
)
from .research_readiness import classify_data_path, current_data_file_paths


def _csv_shape(path: Path) -> dict[str, int | None]:
    """Count CSV rows and columns without retaining cells or printing values."""

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            return {"row_count": 0, "column_count": 0, "max_observed_columns": 0}

        row_count = 0
        max_observed_columns = len(header)
        for row in reader:
            row_count += 1
            max_observed_columns = max(max_observed_columns, len(row))
    return {
        "row_count": row_count,
        "column_count": len(header),
        "max_observed_columns": max_observed_columns,
    }


def _xlsx_sheet_count(path: Path) -> int | None:
    """Read only workbook structure; do not read worksheet cells."""

    if not zipfile.is_zipfile(path):
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            workbook_xml = archive.read("xl/workbook.xml")
        root = ElementTree.fromstring(workbook_xml)
        return sum(1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "sheet")
    except (KeyError, OSError, ElementTree.ParseError, zipfile.BadZipFile):
        return None


def _geojson_shape(path: Path) -> dict[str, Any]:
    """Read GeoJSON structure without returning properties or coordinates."""

    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    features = document.get("features") if isinstance(document, dict) else None
    return {
        "geojson_type": document.get("type") if isinstance(document, dict) else None,
        "feature_count": len(features) if isinstance(features, list) else None,
    }


def _structural_metadata(path: Path, file_format: str) -> dict[str, Any]:
    if file_format == "csv":
        return _csv_shape(path)
    if file_format == "xlsx":
        sheet_count = _xlsx_sheet_count(path)
        return {"sheet_count": sheet_count} if sheet_count is not None else {}
    if file_format == "geojson":
        return _geojson_shape(path)
    return {}


def _record_for_file(path: Path, *, project_root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(project_root).as_posix()
    file_format = format_for_path(path)
    record: dict[str, Any] = {
        "relative_path": relative_path,
        "extension": path.suffix.lower(),
        "format": file_format,
        "file_size_bytes": path.stat().st_size,
        "sha256": None,
        "is_empty": path.stat().st_size == 0,
        "source_organization": source_organization_for_path(path),
        "authorization_status": "unverified",
        "sensitivity_classification": sensitivity_for_path(path),
        "eligible_for_publication": False,
        "presence_status": "discovered",
        "review_status": "unverified",
        "documentation_category": classify_data_path(relative_path),
        "is_duplicate_by_checksum": False,
        "duplicate_paths": [],
    }
    try:
        record["sha256"] = sha256_file(path)
        record.update(_structural_metadata(path, file_format))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # Keep errors generic so malformed source content is never echoed.
        record["metadata_error"] = f"Unable to collect optional structural metadata: {type(exc).__name__}."
    return record


def build_inventory(project_root: str | Path) -> dict[str, Any]:
    """Return inventory metadata for every regular file below ``data``."""

    root = Path(project_root).expanduser().resolve()
    data_root = root / "data"
    if not data_root.is_dir():
        raise FileNotFoundError("The project data directory does not exist.")

    files = [root / relative_path for relative_path in current_data_file_paths(root)]
    records = [_record_for_file(path, project_root=root) for path in files]

    by_checksum: dict[str, list[str]] = defaultdict(list)
    for record in records:
        checksum = record["sha256"]
        if checksum:
            by_checksum[checksum].append(record["relative_path"])
    for record in records:
        paths = by_checksum.get(record["sha256"], [])
        if len(paths) > 1:
            record["is_duplicate_by_checksum"] = True
            record["duplicate_paths"] = paths

    duplicate_groups = sum(1 for paths in by_checksum.values() if len(paths) > 1)
    fingerprint_payload = [
        {
            key: value
            for key, value in record.items()
            if key not in {"is_duplicate_by_checksum", "duplicate_paths"}
        }
        for record in records
    ]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "inventory_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inventory_fingerprint": fingerprint,
        "data_root": "data",
        "authorization_default": "unverified",
        "eligible_for_publication_default": False,
        "file_count": len(records),
        "duplicate_checksum_group_count": duplicate_groups,
        "files": records,
    }

