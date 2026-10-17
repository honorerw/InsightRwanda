"""Metadata-only submission readiness summary; never grants research approval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_submission_assessment(
    project_root: str | Path,
    *,
    competition_document: str | Path | None = None,
) -> dict[str, Any]:
    """Read current generated readiness artifacts and label their limits.

    The function intentionally does not run tests, inspect source observations,
    or infer official compliance from the existence of the competition PDF.
    """

    root = Path(project_root).resolve()

    def read_json(relative_path: str) -> dict[str, Any] | None:
        try:
            value = json.loads((root / relative_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    readiness = read_json("artifacts/research_readiness.json")
    release = read_json("artifacts/phase18_status.json")
    document = Path(competition_document).expanduser() if competition_document else root.parent / "2026 Hackathon Competition.pdf"
    document_available = document.is_file()

    return {
        "assessment_schema": "phase21-submission-assessment-v1",
        "software_validation": {
            "status": "not_assessed_at_runtime",
            "basis": "The dashboard does not execute the repository test suite.",
            "command": "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests",
        },
        "research": {
            "status": (readiness or {}).get("overall_status", "unavailable"),
            "analytical_eligibility": (readiness or {}).get("analytical_eligibility") is True,
            "publication_eligibility": (readiness or {}).get("publication_eligibility") is True,
            "readiness_report_available": readiness is not None,
        },
        "release": {
            "status": (release or {}).get("status", "unavailable"),
            "reproducibility_status": ((release or {}).get("reproducibility") or {}).get("status", "not_configured"),
            "release_report_available": release is not None,
        },
        "competition_document": {
            "status": "available_for_review" if document_available else "unavailable",
            "official_compliance": "not_verified",
        },
        "real_result_artifacts": {
            "status": "not_verified_from_readiness_metadata",
            "result_artifact_written": (release or {}).get("result_artifact_written") is True,
        },
    }
