from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from insightrwanda.analytics.insights import (
    build_indicator_summary_figure,
    build_verified_insight,
    filter_verified_insights,
    interpret_verified_insight,
    verified_filter_options,
)
from insightrwanda.analytics.exports import build_public_export_payload, validate_public_export
from insightrwanda.ui.components import render_research_narrative
from tests.test_phase17 import definition_fixture, result_fixture


ROOT = Path(__file__).resolve().parents[1]


def public_insight(**changes: object) -> dict:
    definition = definition_fixture()
    definition["policy_question"] = "Which documented population groups meet the approved access definition?"
    result = result_fixture(
        readiness={"analysis_eligible": True, "publication_eligible": True},
        publication_status="approved",
        disclosure_status="approved",
        **changes,
    )
    return build_verified_insight(result, definition, intended_use="public_display")


class Phase22NarrativeAndFilterTests(unittest.TestCase):
    def test_eligible_result_chart_and_interpretation_use_supplied_metadata(self):
        insight = public_insight()
        self.assertEqual(insight["status"], "verified")
        figure = build_indicator_summary_figure(insight, intended_use="public_display")
        self.assertIsNotNone(figure)
        self.assertEqual(list(figure.data[0].y), [60.0])
        narrative = interpret_verified_insight(insight)
        self.assertEqual(narrative["research_question"], "Which documented population groups meet the approved access definition?")
        self.assertEqual(narrative["dataset_release"], "release-test-v1")
        self.assertEqual(narrative["population_scope"], "approved respondents")
        self.assertEqual(narrative["reference_period"], "2024")
        self.assertEqual(narrative["value"], 60.0)
        self.assertIn("does not establish a causal", narrative["text"])

    def test_filter_choices_are_derived_only_from_public_eligible_records(self):
        first = public_insight(comparison_category="Urban", comparison_category_status="verified")
        second = public_insight(
            reference_period="2025",
            comparison_category="Rural",
            comparison_category_status="verified",
            provenance={**result_fixture()["provenance"], "input_file_sha256": "b" * 64},
        )
        results = [first, second]
        self.assertEqual(verified_filter_options(results, "comparison_category"), ("Urban", "Rural"))
        self.assertEqual(verified_filter_options(results, "reference_period"), ())
        for insight in results:
            insight["temporal_comparability_status"] = "verified"
            insight["temporal_comparability_evidence_references"] = ["review-test#period-comparability"]
        self.assertEqual(verified_filter_options(results, "reference_period"), ("2024", "2025"))
        self.assertEqual(filter_verified_insights(results, filters={"comparison_category": "Rural"}), [second])
        self.assertIsNone(filter_verified_insights(results, filters={"comparison_category": "Invented"}))
        self.assertIsNone(filter_verified_insights(results, filters={"unsupported": "Rural"}))
        internal_only = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        self.assertEqual(verified_filter_options([internal_only], "indicator_id"), ())

    def test_uncertainty_is_included_only_for_finite_matching_interval(self):
        with_interval = public_insight(
            confidence_interval={"lower": 50.0, "upper": 70.0},
            confidence_interval_unit="percentage",
        )
        narrative = interpret_verified_insight(with_interval)
        self.assertEqual(narrative["uncertainty"], {"lower": 50.0, "upper": 70.0, "unit": "percentage"})
        altered = dict(with_interval)
        altered["uncertainty"] = {"unit": "ratio", "confidence_interval": {"lower": 0.5, "upper": 0.7}}
        self.assertIsNone(interpret_verified_insight(altered)["uncertainty"])

    def test_missing_or_ineligible_insights_do_not_make_findings_or_filter_options(self):
        blocked = build_verified_insight(None, definition_fixture(), intended_use="public_display")
        blocked_narrative = interpret_verified_insight(blocked)
        self.assertEqual(blocked_narrative["status"], "blocked")
        self.assertIn("source_result_missing", blocked_narrative["text"])
        self.assertIsNone(build_indicator_summary_figure(blocked, intended_use="public_display"))
        self.assertEqual(verified_filter_options([blocked], "indicator_id"), ())

    def test_non_authorized_result_classification_cannot_become_verified_insight(self):
        restricted = build_verified_insight(
            result_fixture(data_classification="restricted"),
            definition_fixture(),
            intended_use="internal_analysis",
        )
        self.assertEqual(restricted["status"], "blocked")
        self.assertIn("restricted_result_not_for_research", restricted["blocker_ids"])

    def test_narrative_component_rejects_analytically_eligible_but_unpublished_result(self):
        internal = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        with patch("insightrwanda.ui.components.st.info") as info:
            self.assertFalse(render_research_narrative(internal))
        info.assert_called_once()


class Phase22PresentationAndExportTests(unittest.TestCase):
    def test_overview_guided_flow_does_not_hide_live_blocked_state(self):
        app = AppTest.from_file(ROOT / "app_pages/overview.py").run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any("no verified research estimate" in element.value for element in app.info))
        walkthrough = next(element for element in app.selectbox if element.label == "Walkthrough step")
        self.assertEqual(len(walkthrough.options), 8)

    def test_export_page_keeps_download_unavailable_without_publication_approval(self):
        app = AppTest.from_file(ROOT / "app_pages/reports_exports.py").run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertTrue(any("Exports are currently unavailable" in element.value for element in app.get("markdown")))

    def test_export_contract_rejects_ineligible_restricted_and_synthetic_results(self):
        eligible = public_insight()
        specification = {"approved": True, "output_id": "approved-summary-v1", "version": "1"}
        export = build_public_export_payload(eligible, output_specification=specification)
        self.assertEqual(export["status"], "eligible")
        self.assertEqual(export["payload"]["data_classification"], "metadata_only")
        self.assertFalse(export["payload"]["raw_records_included"])
        self.assertNotIn("records", export["payload"])

        for candidate, blocker in (
            (build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis"), "public_insight_ineligible"),
            ({**eligible, "data_classification": "restricted"}, "export_data_classification"),
            ({**eligible, "status": "synthetic_test_only", "insight_status": "synthetic_test_only", "data_classification": "synthetic_test_data"}, "public_insight_ineligible"),
        ):
            rejected = validate_public_export(candidate, output_specification=specification)
            self.assertEqual(rejected["status"], "blocked")
            self.assertIn(blocker, rejected["blocker_ids"])
            self.assertIsNone(rejected["payload"])


if __name__ == "__main__":
    unittest.main()
