"""Generate the committed one-page briefs for all dashboard pages.

Writes docs/briefs/brief_<page>.pdf and .png from the real source using the
same estimators the app runs. Aggregates only — no household records.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.briefs import PAGES, brief_filenames, render_brief_pdf, render_brief_png, build_all_briefs
from research.catalog import build_source_profile, combine_source_profiles
from research.data_pipeline import ANALYSIS_COLUMNS, enrich_analysis_data, load_analysis_data
from research.joint import build_combined_analysis_frame
from research.quality import run_quality_checks
from research.spss_pipeline import build_spss_profile, enrich_spss_analysis_data, load_spss_analysis_data

MASTER_PATH = ROOT / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta"
SPSS_PATH = ROOT / "data" / "Rwanda FinScope 2020_Final Data.sav"


def main() -> int:
    out_dir = ROOT / "docs" / "briefs"
    out_dir.mkdir(parents=True, exist_ok=True)

    master = enrich_analysis_data(load_analysis_data(MASTER_PATH))
    spss = enrich_spss_analysis_data(load_spss_analysis_data(SPSS_PATH))
    data = build_combined_analysis_frame(master, spss)
    profile = combine_source_profiles(
        build_source_profile(MASTER_PATH, analytical_variables=len(ANALYSIS_COLUMNS)),
        build_spss_profile(SPSS_PATH),
        source_id="insightrwanda_combined",
        analytical_variables=len(ANALYSIS_COLUMNS),
        mapped_variables=len(ANALYSIS_COLUMNS),
        population_period="FinScope 2024 wave (master); FinScope 2020 wave (SPSS, fieldwork Sept-Nov 2019)",
        analysis_status="Combined pool ready; measures absent on one file are computed on the records where they are observed",
        notes=(
            "The two files share no record key; briefs use the stacked combined pool and retain source-specific missingness.",
            "Briefs contain aggregate values only; respondent-level records and raw exports are never rendered.",
        ),
    )
    checks = run_quality_checks(
        data,
        source_variable_count=profile.source_variables,
        expected_columns=list(data.columns),
        row_unit="mixed household and individual respondent rows from two pooled samples",
        slice_label=f"the combined analytical frame ({len(data.columns):,} columns)",
    )

    briefs = build_all_briefs(data, profile, checks)
    results = []
    for page in PAGES:
        brief = briefs[page]
        names = brief_filenames(brief)
        pdf_path, png_path = out_dir / names["pdf"], out_dir / names["png"]
        pdf_path.write_bytes(render_brief_pdf(brief))
        png_path.write_bytes(render_brief_png(brief))
        results.append(f"OK {brief.page:<20} -> {names['pdf']} ({pdf_path.stat().st_size // 1024} KB) · {names['png']} ({png_path.stat().st_size // 1024} KB)")
    print("\n".join(results))
    print(f"BRIEFS PASSED: {len(results)}/{len(PAGES)} pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
