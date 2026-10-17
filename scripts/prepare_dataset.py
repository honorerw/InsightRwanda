#!/usr/bin/env python3
"""Prepare one explicitly selected tabular source with explicit options."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from insightrwanda.data.prepare import PreparationConfig, prepare_dataset  # noqa: E402


def _mapping(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Mappings must use COLUMN=VALUE syntax.")
        key, mapped = value.split("=", 1)
        if not key or not mapped:
            raise ValueError("Mappings must contain non-empty names on both sides.")
        result[key] = mapped
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="One explicit source file below data/.")
    parser.add_argument("--output", required=True, type=Path, help="Ignored .csv or .parquet output under artifacts/ or data/processed/.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--require-column", action="append", default=[])
    parser.add_argument("--weight-column", action="append", default=[])
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--cast", action="append", default=[], metavar="COLUMN=TYPE")
    parser.add_argument("--authorization-status", default="unverified")
    parser.add_argument("--allow-unverified-source", action="store_true")
    args = parser.parse_args()
    config = PreparationConfig(
        required_columns=tuple(args.require_column),
        weight_columns=tuple(args.weight_column),
        rename_columns=_mapping(args.rename),
        cast_columns=_mapping(args.cast),
        source_authorization_status=args.authorization_status,
        allow_unverified_source=args.allow_unverified_source,
    )
    report = prepare_dataset(args.input, args.output, project_root=args.project_root, config=config)
    print(f"Prepared {report['row_count']} rows and {report['column_count']} columns into {report['output_path']}")
    print(f"Authorization status: {report['source_authorization_status']}; publication eligible: {report['eligible_for_publication']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

