from __future__ import annotations

import copy
import unittest

from insightrwanda.analytics.insights import (
    build_indicator_summary_figure,
    build_verified_comparison_figure,
    build_verified_insight,
    interpret_verified_insight,
)


def definition_fixture() -> dict:
    return {
        "indicator_id": "FI-ACCESS-001",
        "definition_version": "fi-access-verified-test-v1",
        "description": "Share of the approved target population meeting the documented access condition.",
        "numerator_definition": "Eligible respondents with the approved affirmative response.",
        "denominator_definition": "Eligible respondents with a valid response.",
        "unit": "percentage",
        "definition_approval_status": "approved",
        "methodology_approval_status": "approved",
        "mapping_records": [{"evidence_reference": "codebook-test#access", "codebook_reference": "codebook-test#access"}],
        "calculation_specification": {
            "version": "calc-test-v1",
            "method": "weighted_proportion",
            "confidence_interval_requested": False,
        },
    }


def result_fixture(**overrides: object) -> dict:
    result = {
        "status": "calculated",
        "calculation_status": "calculated",
        "indicator_id": "FI-ACCESS-001",
        "definition_version": "fi-access-verified-test-v1",
        "dataset_id": "authorized-test-release",
        "dataset_release": "release-test-v1",
        "estimate": 0.6,
        "reported_estimate": 0.6,
        "percentage": 60.0,
        "reported_percentage": 60.0,
        "eligible_observation_count": 3,
        "population_scope": "approved respondents",
        "geographic_scope": "Rwanda",
        "reference_period": "2024",
        "limitations": ["Synthetic schema fixture; not a Rwanda estimate."],
        "quality_validation": {"status": "pass"},
        "readiness": {"analysis_eligible": True, "publication_eligible": False},
        "validation": {
            "input_validation": {"status": "pass"},
            "result_integrity": {"status": "pass"},
        },
        "provenance": {
            "mapping_evidence_references": ["codebook-test#access"],
            "calculation_specification_evidence_references": ["calculation-test#v1"],
            "input_file_sha256": "a" * 64,
            "calculated_at_utc": "2026-10-14T08:00:00+00:00",
        },
        "reproducibility": {
            "code_version": "test-calculation-v1",
            "calculation_specification_version": "calc-test-v1",
            "survey_design_method": "approved weighted point estimate",
            "variance_method": "not_requested",
            "uncertainty_status": "not_requested",
        },
        "disclosure_status": "not_reviewed",
        "publication_status": "not_approved",
        "data_classification": "authorized_aggregate",
        "raw_records_included": False,
    }
    result.update(overrides)
    return result


class Phase17InsightTests(unittest.TestCase):
    def test_eligible_aggregate_becomes_traceable_internal_insight(self):
        insight = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        self.assertEqual(insight["status"], "verified")
        self.assertEqual(insight["source_result_id"].startswith("result-"), True)
        self.assertEqual(insight["indicator_id"], "FI-ACCESS-001")
        self.assertEqual(insight["provenance"]["mapping_evidence_references"], ["codebook-test#access"])
        self.assertFalse(insight["raw_records_included"])

    def test_missing_or_malformed_result_is_blocked(self):
        missing = build_verified_insight(None, definition_fixture())
        malformed = build_verified_insight({"calculation_status": "calculated"}, definition_fixture())
        self.assertIn("source_result_missing", missing["blocker_ids"])
        self.assertIn("result_provenance", malformed["blocker_ids"])

    def test_synthetic_result_is_not_a_real_insight(self):
        result = result_fixture(data_classification="synthetic_test_data")
        blocked = build_verified_insight(result, definition_fixture())
        test_only = build_verified_insight(result, definition_fixture(), allow_synthetic_test_data=True)
        self.assertIn("synthetic_result_not_for_real_research", blocked["blocker_ids"])
        self.assertEqual(test_only["status"], "synthetic_test_only")
        self.assertIsNone(build_indicator_summary_figure(test_only, intended_use="internal_analysis"))

    def test_analytical_and_publication_eligibility_are_separate(self):
        internal = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        public = build_verified_insight(result_fixture(), definition_fixture(), intended_use="public_display")
        self.assertEqual(internal["status"], "verified")
        self.assertIn("publication_eligibility", public["blocker_ids"])

        approved = result_fixture(
            readiness={"analysis_eligible": True, "publication_eligible": True},
            disclosure_status="approved",
            publication_status="approved",
        )
        public_insight = build_verified_insight(approved, definition_fixture(), intended_use="public_display")
        self.assertEqual(public_insight["status"], "verified")

    def test_missing_definition_and_provenance_are_blocked(self):
        incomplete = copy.deepcopy(definition_fixture())
        incomplete["mapping_records"] = []
        incomplete["definition_approval_status"] = "pending"
        result = result_fixture(provenance={})
        blocked = build_verified_insight(result, incomplete)
        self.assertIn("result_provenance", blocked["blocker_ids"])
        self.assertIn("definition_not_approved", blocked["blocker_ids"])
        self.assertIn("definition_provenance_missing", blocked["blocker_ids"])

    def test_scope_period_and_uncertainty_requirements_are_checked(self):
        mismatch = build_verified_insight(result_fixture(), definition_fixture(), population_scope="all adults")
        self.assertIn("population_scope_mismatch", mismatch["blocker_ids"])
        definition = definition_fixture()
        definition["calculation_specification"]["confidence_interval_requested"] = True
        blocked = build_verified_insight(result_fixture(), definition)
        self.assertIn("uncertainty_metadata_missing", blocked["blocker_ids"])

    def test_quality_unit_and_raw_record_integrity_are_required(self):
        quality = build_verified_insight(result_fixture(quality_validation={"status": "fail"}), definition_fixture())
        unit = build_verified_insight(result_fixture(unit="ratio"), definition_fixture())
        raw = build_verified_insight(result_fixture(raw_records_included=True), definition_fixture())
        self.assertIn("quality_validation", quality["blocker_ids"])
        self.assertIn("unit_mismatch", unit["blocker_ids"])
        self.assertIn("raw_records_in_result", raw["blocker_ids"])

    def test_missing_estimate_is_not_converted_to_zero(self):
        blocked = build_verified_insight(result_fixture(estimate=None), definition_fixture())
        self.assertIn("result_provenance", blocked["blocker_ids"])
        self.assertNotIn("estimate", blocked)

    def test_blocked_or_empty_results_do_not_make_charts(self):
        self.assertIsNone(build_indicator_summary_figure(None))
        blocked = build_verified_insight(result_fixture(readiness={"analysis_eligible": False}), definition_fixture())
        self.assertIsNone(build_indicator_summary_figure(blocked))
        self.assertIsNone(build_verified_comparison_figure([]))

    def test_verified_chart_has_definition_unit_and_period(self):
        insight = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        figure = build_indicator_summary_figure(insight, intended_use="internal_analysis")
        self.assertIsNotNone(figure)
        self.assertIn("approved target population", figure.layout.title.text)
        self.assertEqual(figure.layout.yaxis.title.text, "percentage")
        self.assertEqual(figure.layout.xaxis.title.text, "Reference period")
        self.assertEqual(list(figure.data[0].y), [60.0])

    def test_percentage_chart_requires_an_explicit_value_in_the_definition_unit(self):
        result = result_fixture()
        result.pop("percentage")
        result.pop("reported_percentage")
        blocked = build_verified_insight(result, definition_fixture(), intended_use="internal_analysis")
        self.assertIn("result_unit_value_missing", blocked["blocker_ids"])
        self.assertIsNone(build_indicator_summary_figure(blocked, intended_use="internal_analysis"))

    def test_comparison_is_unsorted_and_requires_compatible_scope(self):
        geo_gates = {
            "geographic_validation_status": "verified",
            "geographic_join_status": "validated",
            "area_validation_status": "pass",
            "geographic_resource_id": "synthetic-resource-test",
            "geographic_resource_version": "synthetic-boundary-v1",
            "geographic_disclosure_status": "reviewed",
        }
        first = build_verified_insight(result_fixture(geographic_scope="North", **geo_gates), definition_fixture(), intended_use="internal_analysis")
        second = build_verified_insight(result_fixture(geographic_scope="South", estimate=0.4, **geo_gates), definition_fixture(), intended_use="internal_analysis")
        figure = build_verified_comparison_figure([first, second], intended_use="internal_analysis")
        self.assertIsNotNone(figure)
        self.assertEqual(list(figure.data[0].x), ["North", "South"])
        blocked_geography = build_verified_insight(result_fixture(geographic_scope="East"), definition_fixture(), intended_use="internal_analysis")
        self.assertIsNone(build_verified_comparison_figure([first, blocked_geography], intended_use="internal_analysis"))
        incompatible = build_verified_insight(result_fixture(reference_period="2023", **geo_gates), definition_fixture(), intended_use="internal_analysis")
        self.assertIsNone(build_verified_comparison_figure([first, incompatible], intended_use="internal_analysis"))

    def test_interpretation_is_deterministic_and_noncausal(self):
        insight = build_verified_insight(result_fixture(), definition_fixture(), intended_use="internal_analysis")
        interpretation = interpret_verified_insight(insight)
        self.assertEqual(interpretation["status"], "verified")
        self.assertIn("does not establish", interpretation["text"])
        self.assertIn("poverty reduction impact", interpretation["unsupported_claims"])
        self.assertNotIn("caused this result", interpretation["text"])


if __name__ == "__main__":
    unittest.main()
