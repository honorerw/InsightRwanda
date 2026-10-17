from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.analytics.phase14 import (
    build_phase14_status,
    calculate_verified_indicator,
    save_calculation_result,
)
from insightrwanda.data.errors import IndicatorBlockedError


def eligible_fixture(root: Path) -> tuple[dict[str, dict], dict[str, dict], dict]:
    source_path = root / "data" / "mine" / "fixture.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("access,weight\n1,1\n0,2\n1,1\n", encoding="utf-8")
    dataset = {
        "dataset_id": "synthetic-authorized",
        "display_name": "Synthetic authorized fixture",
        "is_synthetic": True,
        "source_path": "mine/fixture.csv",
        "file_format": "csv",
        "dataset_version": "release-test-1",
        "provenance_status": "verified",
        "authorization_status": "authorized_for_analysis",
        "analytical_eligibility": True,
        "permitted_processing_purpose": "analysis of the approved indicator",
        "license_status": "verified",
        "documentation_status": "verified",
        "codebook_status": "verified",
        "verified_schema_columns": ["access", "weight"],
        "survey_weight_status": "verified",
        "survey_weight_variable": "weight",
        "survey_weight_interpretation": "Population weight for the approved adult respondent universe.",
        "survey_design_status": "verified",
        "data_quality_status": "passed",
        "integrity_sha256": "a" * 64,
        "documentation_references": ["data/docs/codebook.pdf", "data/docs/questionnaire.pdf"],
        "eligible_for_publication": False,
        "survey_design": {
            "status": "approved",
            "sampling_design": "Documented survey design; weighted point estimate approved.",
            "variance_method": "not_requested",
            "point_estimate_supported": True,
            "variance_estimation_supported": False,
        },
    }
    definition = {
        "indicator_id": "FI-ACCESS-001",
        "definition_version": "fi-access-test-v1",
        "status": "officially_documented",
        "evidence_status": "verified_codebook_mapping",
        "definition_approval_status": "approved",
        "methodology_approval_status": "approved",
        "required_variables": ["access", "weight"],
        "numerator_definition": "Eligible respondents with the codebook-approved affirmative access response.",
        "denominator_definition": "All eligible respondents with valid access response.",
        "missing_value_treatment": "Missing, refused, and not-applicable responses are excluded and reported.",
        "eligibility_rules": ["Use the exact release respondent universe and skip pattern."],
        "survey_weight_requirements": "Use the documented respondent population weight.",
        "requires_survey_weight": True,
        "calculation_method": "weighted_proportion",
        "value_semantics_verified": True,
        "interpretation_cautions": ["Synthetic fixture only; never a Rwanda estimate."],
        "source_documentation": [
            {"path": "data/docs/codebook.pdf"},
            {"path": "data/docs/questionnaire.pdf"},
        ],
        "mapping_records": [
            {
                "indicator_id": "FI-ACCESS-001",
                "source_dataset_id": "synthetic-authorized",
                "source_variable": "access",
                "variable_meaning": "Approved access response",
                "codebook_reference": "data/docs/codebook.pdf#access",
                "eligible_population": "Approved respondent universe",
                "denominator_definition": "Valid access responses",
                "missing_value_treatment": "Exclude documented nonresponse codes",
                "response_coding": {"1": "affirmative", "0": "negative"},
                "status": "verified",
                "evidence_reference": "data/docs/codebook.pdf#access",
            },
            {
                "indicator_id": "FI-ACCESS-001",
                "source_dataset_id": "synthetic-authorized",
                "source_variable": "weight",
                "variable_meaning": "Approved population weight",
                "codebook_reference": "data/docs/codebook.pdf#weight",
                "eligible_population": "Approved respondent universe",
                "denominator_definition": "Weight applies to valid eligible responses",
                "missing_value_treatment": "Missing weights invalidate eligible observations",
                "response_coding": "Numeric positive weight",
                "status": "verified",
                "evidence_reference": "data/docs/codebook.pdf#weight",
            },
        ],
        "definition_review": {
            "target_release_identifier": "release-test-1",
            "complete": True,
            "fields": [
                {
                    "field_id": field,
                    "status": "verified",
                    "release_identifier": "release-test-1",
                    "value": "Reviewed synthetic fixture definition",
                    "evidence_reference": "data/docs/codebook.pdf#review",
                    "reviewer": "synthetic-reviewer",
                    "review_date": "2026-10-14",
                }
                for field in ("numerator", "denominator", "weighting", "survey_design", "limitations")
            ],
        },
        "calculation_specification": {
            "status": "approved",
            "version": "calc-test-v1",
            "indicator_id": "FI-ACCESS-001",
            "dataset_id": "synthetic-authorized",
            "method": "weighted_proportion",
            "formula": "sum(weight * affirmative) / sum(weight * eligible)",
            "evidence_references": ["data/docs/calculation-specification.pdf#v1"],
            "duplicate_policy": "reject",
            "weighted_denominator_allowed": True,
            "confidence_interval_requested": False,
            "rounding_digits": 4,
        },
    }
    source = {
        "sources": [{
            "source_id": "SOURCE-SYNTHETIC",
            "dataset_id": "synthetic-authorized",
            "release_version": "release-test-1",
            "source_reference_status": "verified",
            "source_information_status": "verified",
            "documentation_review_status": "verified",
            "access_authorization_status": "verified",
            "analysis_approval_status": "verified",
            "publication_approval_status": "missing",
            "permitted_use_status": "verified",
            "documentation_records": [
                {"document_type": "codebook", "path": "data/docs/codebook.pdf", "release_identifier": "release-test-1", "status": "verified", "review_status": "verified", "exact_release_status": "verified"},
                {"document_type": "questionnaire", "path": "data/docs/questionnaire.pdf", "release_identifier": "release-test-1", "status": "verified", "review_status": "verified", "exact_release_status": "verified"},
            ],
        }],
    }
    return {dataset["dataset_id"]: dataset}, {definition["indicator_id"]: definition}, source


class Phase14Tests(unittest.TestCase):
    def test_live_project_is_blocked_with_precise_prerequisites(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "data/metadata/dataset_registry.json").read_text(encoding="utf-8"))
        catalogue = json.loads((root / "data/metadata/indicator_catalogue.json").read_text(encoding="utf-8"))
        sources = json.loads((root / "data/metadata/source_verification.json").read_text(encoding="utf-8"))
        registry_by_id = {item["dataset_id"]: item for item in registry["datasets"]}
        catalogue_by_id = {item["indicator_id"]: item for item in catalogue["indicators"]}
        report = build_phase14_status(root, registry_by_id, catalogue_by_id, sources)
        self.assertEqual(report["calculation_status"], "blocked")
        self.assertIsNone(report["estimate"])
        self.assertIn("source_file_availability", report["blocker_ids"])
        self.assertIn("verified_variable_mappings", report["blocker_ids"])
        self.assertFalse(report["raw_records_included"])

    def test_authorized_fixture_calculates_weighted_aggregate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            result = calculate_verified_indicator(
                project_root=root,
                definition=catalogue["FI-ACCESS-001"],
                dataset=registry["synthetic-authorized"],
                source_verification=sources,
                input_data=frame,
                numerator=pd.Series([True, False, True], dtype="boolean"),
                denominator=pd.Series([True, True, True], dtype="boolean"),
                weights=frame["weight"],
                allow_synthetic_test_data=True,
            )
        self.assertEqual(result["calculation_status"], "calculated")
        self.assertEqual(result["estimate"], 0.6)
        self.assertEqual(result["weighted_denominator"], 5.0)
        self.assertEqual(result["data_classification"], "synthetic_test_data")
        self.assertFalse(result["raw_records_included"])

    def test_missing_response_is_excluded_and_summarized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            result = calculate_verified_indicator(
                project_root=root,
                definition=catalogue["FI-ACCESS-001"],
                dataset=registry["synthetic-authorized"],
                source_verification=sources,
                input_data=frame,
                numerator=pd.Series([True, False, pd.NA], dtype="boolean"),
                denominator=pd.Series([True, True, True], dtype="boolean"),
                weights=frame["weight"],
                allow_synthetic_test_data=True,
            )
        self.assertEqual(result["calculation_status"], "calculated")
        self.assertEqual(result["missingness_summary"]["numerator_missing"], 1)
        self.assertNotIn("records", result)

    def test_missing_dataset_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, catalogue, sources = eligible_fixture(Path(directory))
            report = build_phase14_status(directory, registry, catalogue, sources, dataset_id="unknown")
        self.assertIn("dataset_registered", report["blocker_ids"])

    def test_outside_path_and_wrong_release_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            registry["synthetic-authorized"]["source_path"] = "../outside.csv"
            report = build_phase14_status(root, registry, catalogue, sources, dataset_id="synthetic-authorized")
            self.assertIn("approved_registered_path", report["blocker_ids"])
            registry["synthetic-authorized"]["source_path"] = "mine/fixture.csv"
            registry["synthetic-authorized"]["dataset_version"] = "wrong-release"
            report = build_phase14_status(root, registry, catalogue, sources, dataset_id="synthetic-authorized")
        self.assertIn("release_match", report["blocker_ids"])

    def test_authorization_mapping_schema_quality_design_and_weight_failures_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            for field, expected in (
                ("authorization_status", "unverified"),
                ("data_quality_status", "unverified"),
                ("analytical_eligibility", False),
                ("survey_design", {"status": "invalid"}),
            ):
                changed_registry = copy.deepcopy(registry)
                changed_registry["synthetic-authorized"][field] = expected
                report = build_phase14_status(root, changed_registry, catalogue, sources, dataset_id="synthetic-authorized")
                self.assertTrue(report["blocker_ids"])
            changed_catalogue = copy.deepcopy(catalogue)
            changed_catalogue["FI-ACCESS-001"]["mapping_records"] = []
            report = build_phase14_status(root, registry, changed_catalogue, sources, dataset_id="synthetic-authorized")
            self.assertIn("verified_variable_mappings", report["blocker_ids"])

    def test_missing_variable_invalid_weight_zero_denominator_and_inconsistent_masks_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            missing_schema = frame.drop(columns=["access"])
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=missing_schema, numerator=pd.Series([True, False, True], dtype="boolean"), denominator=pd.Series([True, True, True], dtype="boolean"), weights=missing_schema["weight"])
            self.assertIn("documented_schema", result["blocker_ids"])
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([True, False, True], dtype="boolean"), denominator=pd.Series([True, True, True], dtype="boolean"), weights=pd.Series([1.0, None, 1.0]))
            self.assertIn("invalid_or_missing_weights", result["blocker_ids"])
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([False, False, False], dtype="boolean"), denominator=pd.Series([False, False, False], dtype="boolean"), weights=frame["weight"])
            self.assertEqual(result["calculation_status"], "zero_eligible_denominator")
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([True, False, False], dtype="boolean"), denominator=pd.Series([False, True, True], dtype="boolean"), weights=frame["weight"])
        self.assertIn("inconsistent_numerator_denominator", result["blocker_ids"])

    def test_invalid_values_and_confidence_intervals_do_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([1, 0, 1]), denominator=pd.Series([True, True, True], dtype="boolean"), weights=frame["weight"])
            self.assertIn("input_masks", result["blocker_ids"])
            changed = copy.deepcopy(catalogue)
            changed["FI-ACCESS-001"]["calculation_specification"]["confidence_interval_requested"] = True
            result = calculate_verified_indicator(project_root=root, definition=changed["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([True, False, True], dtype="boolean"), denominator=pd.Series([True, True, True], dtype="boolean"), weights=frame["weight"])
        self.assertIn("variance_estimation_supported", result["blocker_ids"])

    def test_publication_restriction_and_blocked_result_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([True, False, True], dtype="boolean"), denominator=pd.Series([True, True, True], dtype="boolean"), weights=frame["weight"], publication_requested=True)
            self.assertEqual(result["calculation_status"], "blocked")
            with self.assertRaises(IndicatorBlockedError):
                save_calculation_result(result, project_root=root)
            self.assertFalse((root / "artifacts" / "phase14_result.json").exists())

    def test_saved_result_contains_no_raw_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
            result = calculate_verified_indicator(project_root=root, definition=catalogue["FI-ACCESS-001"], dataset=registry["synthetic-authorized"], source_verification=sources, input_data=frame, numerator=pd.Series([True, False, True], dtype="boolean"), denominator=pd.Series([True, True, True], dtype="boolean"), weights=frame["weight"], allow_synthetic_test_data=True)
            path = save_calculation_result(result, project_root=root)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["calculation_status"], "calculated")
        self.assertNotIn("records", saved)
        self.assertNotIn("raw_records", saved)
        self.assertFalse(saved["raw_records_included"])


if __name__ == "__main__":
    unittest.main()
