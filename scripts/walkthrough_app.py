"""Headless walkthrough of every dashboard page using Streamlit AppTest.

This exercises the real UI code path (script execution, navigation, filters,
charts) without a browser. Each page must render without raising an exception.
Run directly, or wire into the test suite if you accept the extra runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit.testing.v1 as st_test

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    "Overview",
    "Financial inclusion",
    "Poverty insights",
    "Geographic insights",
    "Resilience lab",
    "Data quality",
    "Data explorer",
    "Methods & sources",
    "About the build",
]


def visit(page: str):
    """Render one page in a fresh AppTest session with the nav pre-selected.

    A fresh session per page avoids AppTest artefacts caused by orphaned
    widget keys from a previous page's filter bar.
    """

    at = st_test.AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["workspace_nav"] = page
    at.run()
    return at


def main() -> int:
    failures: list[str] = []
    for page in PAGES:
        at = visit(page)
        if at.exception:
            failures.append(page)
            print(f"  FAIL  {page}: {at.exception[0].value}")
        else:
            n_metrics = len(at.metric) + len(at.markdown)
            print(f"  OK    {page} rendered "
                  f"({n_metrics} metric/markdown blocks, {len(at.dataframe)} dataframes)")

    if failures:
        print(f"\nWALKTHROUGH FAILED ({len(failures)}/{len(PAGES)}): {failures}")
        return 1
    print(f"\nWALKTHROUGH PASSED: all {len(PAGES)} pages rendered without exception.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
