"""Small, non-row-level metadata helpers for source files."""

from __future__ import annotations

import hashlib
from pathlib import Path


FORMAT_BY_SUFFIX = {
    ".csv": "csv",
    ".dta": "stata",
    ".geojson": "geojson",
    ".json": "json",
    ".pdf": "pdf",
    ".xls": "legacy_xls",
    ".xlsx": "xlsx",
}


def format_for_path(path: Path) -> str:
    """Return a format label based on the lower-case file extension."""

    return FORMAT_BY_SUFFIX.get(path.suffix.lower(), "unknown")


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a file checksum without retaining file contents in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_organization_for_path(path: Path) -> str | None:
    """Return only organization attribution supported by the path context.

    Most local source files do not contain enough safe metadata to establish an
    organization. Those files intentionally return ``None`` and remain
    unverified in the inventory.
    """

    lower_parts = {part.lower() for part in path.parts}
    if "brief" in lower_parts and "hackathon" in path.name.lower():
        return "National Institute of Statistics of Rwanda (NISR)"
    return None


def sensitivity_for_path(path: Path) -> str:
    """Assign a conservative sensitivity class from the source location."""

    lower_parts = {part.lower() for part in path.parts}
    if "mine" in lower_parts:
        if path.suffix.lower() in {".csv", ".dta", ".sav", ".sas7bdat", ".xls", ".xlsx"}:
            return "restricted_or_review_required"
        return "source_document_review_required"
    return "publication_review_required"

