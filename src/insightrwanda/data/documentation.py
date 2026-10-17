"""Metadata-only registration helper for locally held source documents."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .errors import DataLoaderError, DataPathError
from .paths import resolve_approved_data_path


DOCUMENT_TYPES = {"report", "questionnaire", "codebook", "methodology", "terms_of_use", "other"}


def prepare_local_document_record(
    project_root: str | Path,
    relative_path: str | Path,
    *,
    document_id: str,
    document_type: str,
    release_identifier: str | None,
) -> dict[str, Any]:
    """Return a safe registration record; presence/hash never imply review or permission."""

    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "data":
        raise DataPathError("Documentation must be registered using a relative path under data/.")
    if document_type not in DOCUMENT_TYPES:
        raise DataLoaderError("Unsupported source-document type.")
    path = resolve_approved_data_path(relative, project_root=project_root)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "document_id": document_id,
        "document_type": document_type,
        "path": path.relative_to(Path(project_root).resolve()).as_posix(),
        "release_identifier": release_identifier,
        "status": "provided_unverified",
        "exact_release_status": "missing",
        "review_status": "missing",
        "sha256": digest.hexdigest(),
        "reviewer": None,
        "review_date": None,
    }
