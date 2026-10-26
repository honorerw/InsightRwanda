import io
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from research.briefs import (
    PAGES,
    PageBrief,
    build_all_briefs,
    build_page_brief,
    brief_filenames,
    render_brief_pdf,
    render_brief_png,
)
from research.catalog import SourceProfile, build_source_profile
from research.data_pipeline import enrich_analysis_data, load_analysis_data
from research.quality import run_quality_checks


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta"


def _fixture_profile() -> SourceProfile:
    return SourceProfile(
        source_id="fixture", path="fixture.dta", format="Stata .dta", file_size_mb=0.1,
        source_sha256="a" * 64, analysis_version="financial_inclusion_fixture", rows=6,
        source_variables=10, analytical_variables=10, source_release="Not documented",
        population_period="Not documented", metadata_status="Inspected", analysis_status="Ready",
        authorization_status="Unknown", publication_status="Not approved",
        documentation=(), notes=(),
    )


class BriefUnitTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "hh_wt": [1.0, 2.0, 1.0, 1.0, 1.0, 2.0],
            "qf4_01": [1, 2, 1, 1, 2, 1],
            "qf4_02": [2, 2, 1, 1, 2, 1],
            "qf4_03": [2, 2, 1, 2, 2, 1],
            "qf4_04": [2, 2, 1, 2, 2, 1],
            "qf4_05": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
            "qf4_06": [2, 2, 2, 2, 2, 1],
            "e9b": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "e9c": [1, 2, 3, 1, 1, np.nan],
            "e7": [1, 2, 3, 4, 1, 1],
            "c14_5": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            "n11": [1, 2, 3, 4, 16, 10],
            "n12": [1, 2, 5, 6, 3, 2],
            "active_access": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
            "mobile_money": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
            "emergency_fund": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "income_pressure": [1.0, 1.0, 0.0, 1.0, 1.0, 1.0],
            "emergency_difficult": [1.0, 1.0, 0.0, 1.0, 1.0, np.nan],
            "internet_access": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
            "resilience_score": [0.25, 0.5, 0.75, 0.0, 0.5, 1.0],
            "resilience_band": ["Priority", "Watch", "Resilient", "Priority", "Watch", "Resilient"],
            "owns_money": [1.0, 0.0, 1.0, 0.0, 0.0, 1.0],
            "saves_regularly": [0.0, 1.0, 1.0, 0.0, 1.0, 1.0],
            "social_safety_net": [1.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            "province": ["Kigali", "South", "Kigali", "West", "South", "Kigali"],
        })

    def test_unknown_page_raises(self):
        with self.assertRaises(ValueError):
            build_page_brief("No such page", self.frame)

    def test_every_page_builds_a_complete_brief(self):
        briefs = build_all_briefs(self.frame, _fixture_profile())
        self.assertEqual(set(briefs), set(PAGES))
        for brief in briefs.values():
            self.assertIsInstance(brief, PageBrief)
            self.assertTrue(brief.kpis)
            self.assertTrue(brief.narrative)
            self.assertTrue(brief.caution)
            self.assertIn("not an official statistical publication", brief.footer_lines[-1])

    def test_overview_kpis_are_weighted_from_derived_columns(self):
        brief = build_page_brief("Overview", self.frame)
        values = dict((label, value) for label, value, _ in brief.kpis)
        self.assertEqual(values["Active formal access"], "62.5%")  # (1*1 + 1*1 + 1*1 + 1*2)/8
        self.assertEqual(values["Emergency buffer"], "12.5%")      # only row 3 = 1
        self.assertEqual(values["Access–buffer gap"], "50.0 pp")

    def test_resilience_bands_are_weighted_shares(self):
        brief = build_page_brief("Resilience lab", self.frame)
        values = dict((label, value) for label, value, _ in brief.kpis)
        self.assertEqual(values["Priority band"], "25.0%")   # weights 1+1 = 2 of 8
        self.assertEqual(values["Watch band"], "37.5%")      # weights 2+1 = 3 of 8
        self.assertEqual(values["Resilient band"], "37.5%")  # weights 1+2 = 3 of 8

    def test_geographic_brief_covers_each_present_province(self):
        brief = build_page_brief("Geographic insights", self.frame)
        labels = {label for label, _, _ in brief.kpis}
        self.assertEqual(labels, {"Kigali", "South", "West"})

    def test_renderers_are_deterministic_and_valid(self):
        brief = build_page_brief("Overview", self.frame)
        first, second = render_brief_png(brief), render_brief_png(brief)
        self.assertEqual(first, second)
        image = Image.open(io.BytesIO(first))
        self.assertEqual(image.size, (1654, 2339))
        pdf = render_brief_pdf(brief)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf)
        self.assertGreater(len(pdf), 1000)

    def test_filenames_are_stable_and_distinct(self):
        for page in PAGES:
            names = brief_filenames(build_page_brief(page, self.frame, _fixture_profile()))
            self.assertEqual(names["pdf"].count("_"), names["png"].count("_"))
            self.assertNotEqual(names["pdf"], names["png"])
        self.assertEqual(brief_filenames(build_page_brief("Overview", self.frame)), {"pdf": "brief_overview.pdf", "png": "brief_overview.png"})

    def test_brief_excludes_household_identifiers(self):
        malicious = self.frame.assign(key=["HH-001", "HH-002", "HH-003", "HH-004", "HH-005", "HH-006"])
        for brief in build_all_briefs(malicious, _fixture_profile()).values():
            self.assertIsInstance(render_brief_png(brief), bytes)
            # structural: no kpi label, value or note ever embeds a household identifier
            joined = " ".join(field for kpi in brief.kpis for field in kpi)
            self.assertNotIn("HH-00", joined)


class GoldenSourceBriefTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        cls.raw = load_analysis_data(SOURCE := cls.ROOT / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta")
        cls.data = enrich_analysis_data(cls.raw)
        cls.profile = build_source_profile(SOURCE, analytical_variables=94)
        cls.checks = run_quality_checks(cls.data, source_variable_count=cls.profile.source_variables)

    def test_all_nine_page_briefs_build_from_the_real_source(self):
        briefs = build_all_briefs(self.data, self.profile, self.checks)
        self.assertEqual(len(briefs), len(PAGES))
        for brief in briefs.values():
            self.assertIn("Analysis version: financial_inclusion_", brief.footer_lines[0])
            self.assertGreaterEqual(len(brief.kpis), 5)

    def test_poverty_brief_reports_the_blocked_contract_not_a_poverty_rate(self):
        brief = build_page_brief("Poverty insights", self.data, self.profile, self.checks)
        labels = {label for label, _, _ in brief.kpis}
        self.assertIn("Official poverty rate", labels)
        rate = [kpi for kpi in brief.kpis if kpi[0] == "Official poverty rate"][0]
        self.assertEqual(rate[1], "Blocked")
        self.assertIn("6 required inputs still missing", rate[2])

    def test_explorer_brief_reflects_the_governance_gate(self):
        brief = build_page_brief("Data explorer", self.data, self.profile, self.checks)
        gate = [kpi for kpi in brief.kpis if kpi[0] == "Explorer gate"][0]
        self.assertEqual(gate[1], "Gated")
        canceled = [kpi for kpi in brief.kpis if "Withheld" in kpi[1]]
        self.assertGreaterEqual(len(canceled), 3)

    def test_quality_brief_zero_failures_on_the_real_source(self):
        brief = build_page_brief("Data quality", self.data, self.profile, self.checks)
        fail = [kpi for kpi in brief.kpis if kpi[0] == "Checks executed"][0]
        self.assertIn("0 FAIL", fail[2])

    def test_methods_brief_requires_the_profile(self):
        with self.assertRaises(ValueError):
            build_page_brief("Methods & sources", self.data)


if __name__ == "__main__":
    unittest.main()
