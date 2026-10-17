#!/usr/bin/env python3
"""Generate a conservative inventory of files under ``data/``.

The output contains file metadata and safe structural counts only. It does not
print or export row-level values, column values, coordinates, or identifiers.
Authorization is always ``unverified`` until documented evidence is reviewed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from insightrwanda.data.inventory import build_inventory  # noqa: E402


def _output_path(project_root: Path, requested: str | Path) -> Path:
    output = Path(requested)
    if not output.is_absolute():
        output = project_root / output
    output = output.expanduser().resolve()
    root = project_root.resolve()
    data_root = (root / "data").resolve()
    try:
        output.relative_to(root)
        output.relative_to(data_root)
    except ValueError:
        pass
    else:
        raise ValueError("Inventory output must not be written inside the data directory.")
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Inventory output must remain inside the project directory.") from exc
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root containing data/ (default: repository root).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/source_inventory.json"),
        help="Ignored JSON output path relative to the project root.",
    )
    args = parser.parse_args()
    project_root = args.project_root.expanduser().resolve()
    output = _output_path(project_root, args.output)
    inventory = build_inventory(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": output.relative_to(project_root).as_posix(),
                "file_count": inventory["file_count"],
                "duplicate_checksum_group_count": inventory["duplicate_checksum_group_count"],
                "authorization_default": inventory["authorization_default"],
                "eligible_for_publication_default": inventory["eligible_for_publication_default"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

