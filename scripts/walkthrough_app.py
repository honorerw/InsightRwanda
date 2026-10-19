"""Headless walkthrough of every dashboard page using Streamlit AppTest.

Phase 1 — every page renders without exception.
Phase 2 — every page still renders with a non-default filter lens applied
          (province=Kigali, setting=Urban, respondent=Female).
Phase 3 — the Overview page's tabs are exercised.

A fresh AppTest session per visit avoids AppTest artefacts caused by orphaned
widget keys from a previous page's filter bar. Exits non-zero on any failure.
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
    """Render one page in a fresh AppTest session with the nav pre-selected."""

    at = st_test.AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["workspace_nav"] = page
    at.run()
    return at


def apply_filter_lens(at: st_test.AppTest, page: str) -> bool:
    """Set the page's filter widgets to a non-default lens; True if applied."""

    # Explicit mapping of nav page -> filter_bar key prefix in app.py.
    prefix = {
        "Overview": "overview",
        "Financial inclusion": "financial_inclusion",
        "Poverty insights": "poverty_context",
        "Geographic insights": "regional",
        "Resilience lab": "resilience",
        "Data explorer": "explorer",
    }.get(page)
    if prefix is None:
        return False  # page has no filter bar
    at.selectbox(key=f"{prefix}_province").set_value("Kigali")
    at.selectbox(key=f"{prefix}_setting").set_value("Urban")
    at.selectbox(key=f"{prefix}_sex").set_value("Female")
    at.run()
    return True


def report(label: str, at: st_test.AppTest) -> bool:
    if at.exception:
        print(f"  FAIL  {label}: {at.exception[0].value}")
        return False
    blocks = len(at.markdown) + len(at.metric) + len(at.dataframe)
    print(f"  OK    {label} ({blocks} rendered blocks)")
    return True


def main() -> int:
    failures: list[str] = []

    print("Phase 1 — baseline render of every page")
    for page in PAGES:
        if not report(page, visit(page)):
            failures.append(page)

    print("Phase 2 — filtered lens (Kigali / Urban / Female) on every filtered page")
    for page in PAGES:
        at = visit(page)
        if apply_filter_lens(at, page) and not report(f"{page} · Kigali/Urban/Female", at):
            failures.append(f"{page} (filtered)")

    print("Phase 3 — Overview tab structure")
    at = visit("Overview")
    if at.exception:
        failures.append("Overview tabs")
        print(f"  FAIL  Overview tabs: {at.exception[0].value}")
    elif len(at.tabs) == 3:
        print("  OK    Overview · 3 tabs present (National signal / Opportunity map / Train & predict)")
    else:
        failures.append("Overview tab count")
        print(f"  FAIL  Overview · expected 3 tabs, found {len(at.tabs)}")

    if failures:
        print(f"\nWALKTHROUGH FAILED ({len(failures)}): {failures}")
        return 1
    print("\nWALKTHROUGH PASSED: baseline, filtered and interactive checks all clear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
