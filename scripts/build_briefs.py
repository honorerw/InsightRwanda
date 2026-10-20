"""Generate the committed one-page briefs for all nine dashboard pages.

Writes docs/briefs/brief_<page>.pdf and .png from the real source using the
same estimators the app runs. Aggregates only — no household records.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.briefs import PAGES, brief_filenames, render_brief_pdf, render_brief_png, build_all_briefs
from research.catalog import build_source_profile
from research.data_pipeline import enrich_analysis_data, load_analysis_data
from research.quality import run_quality_checks


def main() -> int:
    out_dir = ROOT / "docs" / "briefs"
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = load_analysis_data(ROOT / "data" / "dataset.dta")
    data = enrich_analysis_data(raw)
    profile = build_source_profile(ROOT / "data" / "dataset.dta", analytical_variables=94)
    checks = run_quality_checks(data, source_variable_count=profile.source_variables)

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
