from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from insightrwanda.analytics.submission import build_submission_assessment
from insightrwanda.analytics.phase14 import save_calculation_result
from insightrwanda.analytics.geography import save_geographic_analysis_result
from insightrwanda.data.errors import IndicatorBlockedError


ROOT = Path(__file__).resolve().parents[1]


class Phase21SubmissionTests(unittest.TestCase):
    def test_assessment_derives_research_and_release_status_from_current_artifacts(self):
        assessment = build_submission_assessment(ROOT)
        current = json.loads((ROOT / "artifacts/research_readiness.json").read_text())
        release = json.loads((ROOT / "artifacts/phase18_status.json").read_text())
        self.assertEqual(assessment["research"]["status"], current["overall_status"])
        self.assertFalse(assessment["research"]["analytical_eligibility"])
        self.assertFalse(assessment["research"]["publication_eligibility"])
        self.assertEqual(assessment["release"]["status"], release["status"])
        self.assertEqual(assessment["release"]["reproducibility_status"], "not_configured")
        self.assertEqual(assessment["competition_document"]["official_compliance"], "not_verified")

    def test_missing_competition_document_is_reported_without_claiming_compliance(self):
        with tempfile.TemporaryDirectory() as directory:
            assessment = build_submission_assessment(ROOT, competition_document=Path(directory) / "missing.pdf")
        self.assertEqual(assessment["competition_document"]["status"], "unavailable")
        self.assertEqual(assessment["competition_document"]["official_compliance"], "not_verified")

    def test_dashboard_states_software_validation_is_separate_and_not_run_in_ui(self):
        app = AppTest.from_file(ROOT / "app_pages/research_readiness.py").run(timeout=30)
        self.assertFalse(app.exception)
        rendered = "\n".join([item.value for item in app.caption] + [item.value for item in app.info])
        self.assertIn("Software validation", rendered)
        self.assertIn("not executed by this dashboard", rendered)
        self.assertIn("Analytical eligibility", rendered)
        self.assertIn("Publication eligibility", rendered)

    def test_financial_inclusion_shows_authorized_supplied_dta_analysis(self):
        app = AppTest.from_file(ROOT / "app_pages/financial_inclusion.py").run(timeout=30)
        self.assertFalse(app.exception)
        rendered = "\n".join(item.value for collection in (app.info, app.error, app.caption) for item in collection)
        self.assertIn("data/mine/dataset.dta", rendered)
        self.assertIn("Authorized local-source result", rendered)

    def test_synthetic_phase14_result_cannot_be_written_to_project_artifacts(self):
        result = {
            "calculation_status": "calculated",
            "data_classification": "synthetic_test_data",
            "raw_records_included": False,
        }
        output = ROOT / "artifacts/phase21_synthetic_must_not_exist.json"
        self.assertFalse(output.exists())
        with self.assertRaises(IndicatorBlockedError):
            save_calculation_result(result, project_root=ROOT, output_path=output.relative_to(ROOT))
        self.assertFalse(output.exists())

    def test_synthetic_geographic_result_cannot_be_written_to_project_artifacts(self):
        result = {
            "status": "validated",
            "analysis_eligible": True,
            "data_classification": "synthetic_test_data",
            "join_validation": {"status": "validated"},
            "area_validation": {"status": "pass"},
        }
        output = ROOT / "artifacts/phase21_synthetic_geo_must_not_exist.json"
        with self.assertRaises(IndicatorBlockedError):
            save_geographic_analysis_result(result, project_root=ROOT, output_path=output.relative_to(ROOT))
        self.assertFalse(output.exists())

    def test_evidence_index_paths_resolve_and_statuses_are_non_authorizing(self):
        index = (ROOT / "docs/phase21-evidence-index.md").read_text(encoding="utf-8")
        expected = [
            ROOT / "artifacts/research_readiness.json",
            ROOT / "artifacts/phase18_status.json",
            ROOT / "docs/phase20-reproducibility-audit-trail.md",
            ROOT / "docs/phase14-first-verified-indicator.md",
            ROOT / "docs/phase15-statistical-validation.md",
            ROOT / "docs/phase16-geographic-analysis.md",
            ROOT / "docs/phase17-verified-insights.md",
            ROOT / "docs/phase18-end-to-end-release-readiness.md",
            ROOT / "docs/phase19-security-integrity-review.md",
            ROOT / "tests/test_phase14.py",
            ROOT / "tests/test_phase21.py",
            ROOT / "app.py",
            ROOT / "README.md",
        ]
        for path in expected:
            self.assertTrue(path.exists(), str(path))
        self.assertIn("team compliance not verified", index)
        self.assertIn("Software tests; no research evidence", index)

    def test_competition_pdf_is_available_but_not_treated_as_team_compliance(self):
        assessment = build_submission_assessment(ROOT)
        self.assertEqual(assessment["competition_document"]["status"], "available_for_review")
        self.assertEqual(assessment["competition_document"]["official_compliance"], "not_verified")


if __name__ == "__main__":
    unittest.main()
