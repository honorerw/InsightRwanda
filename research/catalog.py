"""Source inventory and research-readiness metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    path: str
    format: str
    file_size_mb: float
    source_sha256: str
    analysis_version: str
    rows: int
    source_variables: int
    analytical_variables: int
    source_release: str
    population_period: str
    metadata_status: str
    analysis_status: str
    authorization_status: str
    publication_status: str
    documentation: tuple[str, ...]
    notes: tuple[str, ...]
    mapped_variables: int | None = None
    psu_documented: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_release_allowed(profile: SourceProfile | None) -> bool:
    """Require explicit authorization and publication approval for aggregate export."""

    if profile is None:
        return False
    return profile.authorization_status.startswith("Approved") and profile.publication_status.startswith("Approved")


def _source_variable_count(path: Path) -> int:
    with pd.read_stata(path, iterator=True) as reader:
        return len(reader.variable_labels())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _analysis_version() -> str:
    """Fingerprint the calculation and validation code used by the app."""

    digest = hashlib.sha256()
    code_root = Path(__file__).resolve().parent
    for name in ["data_pipeline.py", "indicators.py", "quality.py", "estimation.py"]:
        digest.update((code_root / name).read_bytes())
    return f"financial_inclusion_{digest.hexdigest()[:12]}"


def build_source_profile(path: str | Path, analytical_variables: int) -> SourceProfile:
    """Inspect source metadata without changing or exporting the source file."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Source dataset does not exist: {source}")
    rows = int(pd.read_stata(source, columns=["key"], convert_categoricals=False).shape[0])
    return SourceProfile(
        source_id="supplied_dataset_dta",
        path=str(source),
        format="Stata .dta",
        file_size_mb=round(source.stat().st_size / (1024 * 1024), 2),
        source_sha256=_sha256(source),
        analysis_version=_analysis_version(),
        rows=rows,
        source_variables=_source_variable_count(source),
        analytical_variables=analytical_variables,
        mapped_variables=analytical_variables,
        source_release="Not documented in supplied materials",
        population_period="Not documented in supplied materials",
        metadata_status="Inspected: embedded Stata variable labels available",
        analysis_status="Ready for the verified financial-inclusion slice",
        authorization_status="Unknown: no authorization record supplied",
        publication_status="Not approved: no disclosure/publication approval supplied",
        documentation=(
            "2026 Hackathon Competition.pdf",
            "Embedded Stata variable labels and value labels",
        ),
        notes=(
            "The file exists and has been structurally inspected; existence is not proof of authorization.",
            "No codebook, sampling methodology, poverty methodology, or release note was supplied in the workspace.",
            "The dashboard does not expose household-level records by default and does not publish the source file.",
        ),
    )
