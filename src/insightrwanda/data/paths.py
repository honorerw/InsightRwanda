"""Path controls for source data access.

These helpers constrain loaders to files below the project's ``data``
directory. They do not grant authorization to analyze or publish a source.
"""

from __future__ import annotations

from pathlib import Path

from .errors import DataPathError


def default_project_root() -> Path:
    """Return the repository root inferred from this source module."""

    return Path(__file__).resolve().parents[3]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_approved_data_path(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> Path:
    """Resolve an existing file and reject paths outside ``<root>/data``.

    Relative paths are interpreted relative to ``project_root``. Symlinks are
    resolved before the boundary check, so a link inside ``data`` cannot point
    a loader outside the approved directory.
    """

    root = Path(project_root or default_project_root()).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DataPathError("The requested data source does not exist.") from exc
    except OSError as exc:
        raise DataPathError("The requested data source could not be resolved.") from exc

    data_root = (root / "data").resolve()
    if not _is_relative_to(resolved, data_root):
        raise DataPathError("Data sources must be files inside the approved data directory.")
    if not resolved.is_file():
        raise DataPathError("The requested data source is not a regular file.")
    return resolved


def safe_relative_path(path: Path, *, project_root: str | Path | None = None) -> str:
    """Return a repository-relative path for non-sensitive diagnostics."""

    root = Path(project_root or default_project_root()).expanduser().resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return "<outside-project>"


def resolve_derived_output_path(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> Path:
    """Resolve a generated output below ``artifacts`` or ``data/processed``.

    Original source directories are intentionally not valid output locations.
    The returned path need not exist yet, but its parent must be inside an
    approved generated-data directory.
    """

    root = Path(project_root or default_project_root()).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    allowed_roots = (
        (root / "artifacts").resolve(),
        (root / "data" / "processed").resolve(),
    )
    if not any(_is_relative_to(resolved, allowed) for allowed in allowed_roots):
        raise DataPathError(
            "Generated outputs must be inside the ignored artifacts or data/processed directory."
        )
    if resolved.exists() and resolved.is_dir():
        raise DataPathError("The generated output path is a directory, not a file.")
    return resolved

