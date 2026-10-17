"""Exercise every app page via Streamlit AppTest and report runtime errors."""
import traceback
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PAGES = [
    "overview.py",
    "financial_inclusion.py",
    "poverty_insights.py",
    "geographic_analysis.py",
    "dataset_registry.py",
    "source_inventory.py",
    "data_quality.py",
    "codebooks_variables.py",
    "indicator_catalogue.py",
    "variable_mapping.py",
    "statistical_analysis.py",
    "research_methodology.py",
    "research_readiness.py",
    "reports_exports.py",
    "evidence_provenance.py",
    "methodology_sources.py",
]


def main() -> int:
    failures = 0
    for page in PAGES:
        path = PROJECT_ROOT / "app_pages" / page
        try:
            at = AppTest.from_file(path, default_timeout=120).run()
            for err in at.error:
                print(f"[ERRTEXT] {page}: {err.value}")
            if at.exception:
                failures += 1
                exc = at.exception[0]
                print(f"[FAIL] {page}: exception")
                value = getattr(exc, "value", exc)
                print(value)
                traceback.print_exception(type(value), value, value.__traceback__)
            else:
                print(f"[OK]   {page}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {page}: AppTest driver error: {exc!r}")
    print(f"Pages with errors: {failures}/{len(PAGES)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
