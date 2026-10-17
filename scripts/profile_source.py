#!/usr/bin/env python3
"""Profile one explicitly selected source into an ignored JSON report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from insightrwanda.data.loaders import load_source  # noqa: E402
from insightrwanda.data.quality import (  # noqa: E402
    QualityConfig,
    profile_dataframe,
    profile_geojson,
    write_quality_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="One explicit source file below data/.")
    parser.add_argument("--output", required=True, type=Path, help="Ignored JSON path under artifacts/ or data/processed/.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--authorization-status", default="unverified")
    parser.add_argument("--no-numeric-summaries", action="store_true")
    args = parser.parse_args()

    selected = load_source(args.input, project_root=args.project_root)
    config = QualityConfig(
        source_authorization_status=args.authorization_status,
        include_numeric_summaries=not args.no_numeric_summaries,
    )
    if isinstance(selected, dict):
        report = profile_geojson(selected, authorization_status=args.authorization_status)
    else:
        report = profile_dataframe(selected, config=config)
    output = write_quality_report(report, args.output, project_root=args.project_root)
    print(f"Wrote aggregate quality report to {output.relative_to(args.project_root.resolve())}")
    print(f"Authorization status: {report['source_authorization_status']}; publication eligible: {report['eligible_for_publication']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

