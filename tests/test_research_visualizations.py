from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from insightrwanda.analytics.insights import (
    build_verified_grouped_comparison_figure,
    build_verified_insight,
    build_verified_time_series_figure,
)
from insightrwanda.ui.visualizations import (
    build_evidence_status_figure,
    build_metadata_count_figure,
    evidence_status_counts,
)
from tests.test_phase17 import definition_fixture, result_fixture


ROOT = Path(__file__).resolve().parents[1]


class ReadinessVisualizationTests(unittest.TestCase):
    def test_evidence_chart_counts_actual_status_records(self):
        report = {
            "evidence": {
                "items": [
                    {"status": "missing"},
                    {"status": "missing"},
                    {"status": "verified"},
                    {"status": "pending_review"},
                ]
            }
        }
        self.assertEqual(evidence_status_counts(report), {"missing": 2, "verified": 1, "pending_review": 1})
        figure = build_evidence_status_figure(report)
        self.assertIsNotNone(figure)
        self.assertEqual(list(figure.data[0].x), [1, 2, 1])
        self.assertIn("Evidence records", figure.data[0].hovertemplate)
        self.assertIsNone(build_evidence_status_figure({"evidence": {"items": []}}))
        self.assertIsNone(build_evidence_status_figure(None))

    def test_generic_metadata_chart_rejects_malformed_or_non_count_values(self):
        figure = build_metadata_count_figure(
            {"csv": 3, "stata": 1},
            title="Inventory formats",
            category_axis="Recorded format",
            count_axis="Current files",
        )
        self.assertIsNotNone(figure)
        self.assertEqual(list(figure.data[0].x), [3, 1])
        for invalid in (None, {}, {"csv": -1}, {"csv": 1.5}, {"csv": True}, {"": 1}):
            self.assertIsNone(build_metadata_count_figure(
                invalid,
                title="Invalid",
                category_axis="Category",
                count_axis="Count",
            ))

    def test_dashboard_renders_metadata_and_local_exploratory_charts_without_verified_estimates(self):
        for page in ("overview.py", "research_readiness.py"):
            app = AppTest.from_file(ROOT / "app_pages" / page).run(timeout=30)
            self.assertFalse(app.exception, page)
            self.assertGreaterEqual(len(app.get("plotly_chart")), 1, page)
        for page in ("financial_inclusion.py", "poverty_insights.py", "geographic_analysis.py"):
            app = AppTest.from_file(ROOT / "app_pages" / page).run(timeout=30)
            self.assertFalse(app.exception, page)
            expected_charts = 4 if page == "financial_inclusion.py" else 0
            self.assertEqual(len(app.get("plotly_chart")), expected_charts, page)
        quality = AppTest.from_file(ROOT / "app_pages/data_quality.py").run(timeout=30)
        self.assertFalse(quality.exception)
        self.assertGreaterEqual(len(quality.get("plotly_chart")), 1)

    def test_public_page_withholds_analytically_calculated_but_unapproved_value(self):
        internal_result = {
            "calculation_status": "calculated",
            "result": {"percentage": 73.0, "reported_percentage": 73.0, "raw_records_included": False},
            "readiness": {"analysis_eligible": True, "publication_eligible": False},
        }
        blocked_public_insight = {
            "status": "blocked",
            "blockers": [],
            "blocker_ids": ["publication_eligibility"],
        }
        with patch("insightrwanda.ui.pages._phase14", return_value=internal_result), patch(
            "insightrwanda.ui.pages._phase17", return_value=blocked_public_insight
        ):
            app = AppTest.from_file(ROOT / "app_pages/financial_inclusion.py").run(timeout=30)
        self.assertFalse(app.exception)
        rendered = "\n".join(item.value for collection in (app.info, app.error, app.caption) for item in collection)
        self.assertIn("withholds its value", rendered)
        self.assertNotIn("73.0", rendered)
        self.assertEqual(len(app.metric), 0)


class VerifiedTrendChartTests(unittest.TestCase):
    def _insight(self, period: str, *, estimate: float, **result_changes: object) -> dict:
        result = result_fixture()
        result.update({
            "reference_period": period,
            "estimate": estimate,
            "reported_estimate": estimate,
            "percentage": estimate * 100,
            "reported_percentage": estimate * 100,
            "temporal_comparability_status": "verified",
            "temporal_comparability_evidence_references": ["review-test#harmonization"],
            "provenance": {
                **result["provenance"],
                "input_file_sha256": ("a" if period == "2023" else "b") * 64,
            },
            **result_changes,
        })
        return build_verified_insight(result, definition_fixture(), intended_use="internal_analysis")

    def test_time_series_requires_verified_period_comparability_and_preserves_input_order(self):
        first = self._insight("2024", estimate=0.55)
        second = self._insight("2023", estimate=0.50)
        figure = build_verified_time_series_figure([first, second], intended_use="internal_analysis")
        self.assertIsNotNone(figure)
        self.assertEqual(list(figure.data[0].x), ["2024", "2023"])
        self.assertEqual(figure.layout.xaxis.title.text, "Reference period (approved order)")
        unsupported = self._insight("2022", estimate=0.4, temporal_comparability_status="unreviewed")
        self.assertIsNone(build_verified_time_series_figure([first, unsupported], intended_use="internal_analysis"))

    def test_mixed_uncertainty_or_malformed_intervals_do_not_render(self):
        first = self._insight(
            "2023", estimate=0.5,
            confidence_interval={"lower": 40.0, "upper": 60.0},
            confidence_interval_unit="percentage",
        )
        second = self._insight("2024", estimate=0.55)
        self.assertIsNone(build_verified_time_series_figure([first, second], intended_use="internal_analysis"))
        malformed = self._insight(
            "2024", estimate=0.55,
            confidence_interval={"lower": 70.0, "upper": 80.0},
            confidence_interval_unit="percentage",
        )
        self.assertIsNone(build_verified_time_series_figure([first, malformed], intended_use="internal_analysis"))
        self.assertIsNone(build_verified_time_series_figure([], intended_use="internal_analysis"))

    def test_grouped_chart_requires_verified_group_and_complete_categories(self):
        definitions = []
        for indicator, version in (("FI-A", "a-v1"), ("FI-B", "b-v1")):
            definition = definition_fixture()
            definition.update({
                "indicator_id": indicator,
                "definition_version": version,
                "comparison_group": "approved-access-family",
                "comparison_group_status": "verified",
                "comparison_group_evidence_references": ["review-test#family"],
            })
            definitions.append(definition)
        insights = []
        for definition, estimate in zip(definitions, (0.5, 0.7)):
            for category in ("Group A", "Group B"):
                result = result_fixture(
                    indicator_id=definition["indicator_id"],
                    definition_version=definition["definition_version"],
                    comparison_category=category,
                    comparison_category_status="verified",
                    estimate=estimate,
                    reported_estimate=estimate,
                    percentage=estimate * 100,
                    reported_percentage=estimate * 100,
                )
                insights.append(build_verified_insight(result, definition, intended_use="internal_analysis"))
        figure = build_verified_grouped_comparison_figure(insights, intended_use="internal_analysis")
        self.assertIsNotNone(figure)
        self.assertEqual(figure.layout.barmode, "group")
        self.assertEqual(len(figure.data), 2)
        self.assertEqual(list(figure.data[0].x), ["Group A", "Group B"])
        incomplete = build_verified_grouped_comparison_figure(insights[:-1], intended_use="internal_analysis")
        self.assertIsNone(incomplete)

    def test_synthetic_or_publication_ineligible_results_are_not_research_charts(self):
        synthetic = self._insight("2023", estimate=0.5, data_classification="synthetic_test_data")
        self.assertEqual(synthetic["status"], "blocked")
        self.assertIsNone(build_verified_time_series_figure([synthetic, synthetic], intended_use="internal_analysis"))
        public_blocked = self._insight("2023", estimate=0.5)
        self.assertIsNone(build_verified_time_series_figure([public_blocked, public_blocked], intended_use="public_display"))


if __name__ == "__main__":
    unittest.main()
