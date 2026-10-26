"""Write the single combined dataset built from the two supplied sources.

The files share no record key, so this is a stacked dataset (two independent
samples of the same survey on harmonized variables), not a join. Source keys
are replaced by deterministic record ids. Output defaults to
``data/derived/insightrwanda_combined.csv`` with a ``.metadata.json`` beside it;
``data/derived/`` is git-ignored because the rows are respondent-level records.

Run from the project root:

    python scripts/build_combined_dataset.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.catalog import build_source_profile
from research.data_pipeline import ANALYSIS_COLUMNS, enrich_analysis_data, load_analysis_data
from research.joint import (
    COMBINED_COLUMN_NOTES,
    WAVE_YEARS,
    build_combined_dataset,
    comparison_note,
    linkage_audit,
    wave_note,
)
from research.spss_pipeline import build_spss_profile, enrich_spss_analysis_data, load_spss_analysis_data

MASTER_PATH = ROOT / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta"
SPSS_PATH = ROOT / "data" / "Rwanda FinScope 2020_Final Data.sav"
DEFAULT_OUT = ROOT / "data" / "derived" / "insightrwanda_combined.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the single combined InsightRwanda dataset.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Destination CSV path.")
    args = parser.parse_args(argv)

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)

    master = enrich_analysis_data(load_analysis_data(MASTER_PATH))
    spss = enrich_spss_analysis_data(load_spss_analysis_data(SPSS_PATH))
    audit = linkage_audit(master, spss)
    dataset = build_combined_dataset(master, spss)
    dataset.to_csv(destination, index=False)

    master_profile = build_source_profile(MASTER_PATH, analytical_variables=len(ANALYSIS_COLUMNS))
    spss_profile = build_spss_profile(SPSS_PATH)
    metadata = {
        "dataset": destination.name,
        "rows": int(len(dataset)),
        "columns": list(dataset.columns),
        "column_notes": COMBINED_COLUMN_NOTES,
        "sources": {
            "master": {
                "file": "data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta",
                "sha256": master_profile.source_sha256,
                "rows": master_profile.rows,
                "wave_year": WAVE_YEARS["master"],
            },
            "spss": {
                "file": "data/Rwanda FinScope 2020_Final Data.sav",
                "sha256": spss_profile.source_sha256,
                "rows": spss_profile.rows,
                "wave_year": WAVE_YEARS["spss"],
            },
        },
        "combination": {
            "method": "stacked as two independent samples on label-verified shared variables; no record linkage",
            "verdict": audit.verdict,
            "shared_keys": audit.shared_keys,
            "composite_pairs": audit.composite_pairs,
            "composite_agreement_share": round(audit.composite_agreement_share, 4),
            "pooling_weight": "weight_share sums to 1 within each source; weight is the source's own household weight",
        },
        "notes": [
            wave_note(),
            comparison_note(),
            "The combined file is a local analytical artifact; the dashboard does not publish it or expose raw records.",
        ],
    }
    metadata_path = destination.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"WROTE {destination} ({destination.stat().st_size / (1024 * 1024):.2f} MB, {len(dataset):,} rows)")
    print(f"WROTE {metadata_path}")
    print(f"Sources: master {audit.master_rows:,} + SPSS {audit.spss_rows:,} rows · shared keys: {audit.shared_keys}")
    print("NOTE: stacked, not merged — the supplied files share no record key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
