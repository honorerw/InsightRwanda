from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from insightrwanda.analytics.phase14 import calculate_verified_indicator
from insightrwanda.analytics.validation import (
    validate_calculation_inputs,
    validate_result_integrity,
)
from insightrwanda.data.errors import IndicatorBlockedError

from tests.test_phase14 import eligible_fixture


def run_fixture(
    root: Path,
    registry: dict,
    catalogue: dict,
    sources: dict,
    *,
    access: list[object] | None = None,
    weights: list[object] | None = None,
    numerator: list[object] | None = None,
    denominator: list[object] | None = None,
    definition: dict | None = None,
    publication_requested: bool = False,
) -> dict:
    frame = pd.DataFrame(
        {
            "access": access if access is not None else [1, 0, 1],
            "weight": weights if weights is not None else [1.0, 2.0, 2.0],
        }
    )
    return calculate_verified_indicator(
        project_root=root,
        definition=definition or catalogue["FI-ACCESS-001"],
        dataset=registry["synthetic-authorized"],
        source_verification=sources,
        input_data=frame,
        numerator=pd.Series(
            numerator if numerator is not None else [True, False, True],
            dtype="boolean",
        ),
        denominator=pd.Series(
            denominator if denominator is not None else [True, True, True],
            dtype="boolean",
        ),
        weights=frame["weight"],
        publication_requested=publication_requested,
        allow_synthetic_test_data=True,
    )


class Phase15ValidationTests(unittest.TestCase):
    def test_independent_weighted_reference_and_eligible_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            result = run_fixture(
                root, registry, catalogue, sources,
                weights=[2.0, 100.0, 1.0],
                numerator=[True, False, False],
                denominator=[True, False, True],
            )
        # Independent reference: (2*1 + 1*0) / (2 + 1) = 2/3.
        expected = (2.0 * 1 + 1.0 * 0) / (2.0 + 1.0)
        self.assertAlmostEqual(result["estimate"], expected)
        self.assertEqual(result["eligible_observation_count"], 2)
        self.assertEqual(result["validation"]["input_validation"]["status"], "pass")
        self.assertEqual(result["data_classification"], "synthetic_test_data")

    def test_weight_normalization_preserves_ratio_and_unweighted_differs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            first = run_fixture(root, registry, catalogue, sources, weights=[1.0, 2.0, 2.0])
            scaled = run_fixture(root, registry, catalogue, sources, weights=[10.0, 20.0, 20.0])
            unweighted_definition = copy.deepcopy(catalogue["FI-ACCESS-001"])
            unweighted_definition["calculation_specification"]["method"] = "proportion"
            unweighted = run_fixture(root, registry, catalogue, sources, definition=unweighted_definition)
        self.assertEqual(first["estimate"], scaled["estimate"])
        self.assertEqual(first["weighted_denominator"], 5.0)
        self.assertEqual(scaled["weighted_denominator"], 50.0)
        self.assertEqual(unweighted["estimate"], 2 / 3)

    def test_missing_refused_and_not_applicable_masks_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            result = run_fixture(
                root, registry, catalogue, sources,
                numerator=[True, pd.NA, False],
                denominator=[True, True, pd.NA],
            )
        # Only the first row is eligible and affirmative; missing responses do
        # not become negative responses or enter the denominator.
        self.assertEqual(result["estimate"], 1.0)
        self.assertEqual(result["eligible_observation_count"], 1)
        self.assertEqual(result["missingness_summary"], {"numerator_missing": 1, "denominator_missing": 1, "weight_missing": 0})

    def test_duplicates_invalid_masks_and_schema_fail_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            duplicate = run_fixture(root, registry, catalogue, sources, access=[1, 1, 1], weights=[1.0, 1.0, 1.0])
            invalid_mask = validate_calculation_inputs(
                readiness_eligible=True,
                frame=pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]}),
                numerator=pd.Series([1, 0, 1]),
                denominator=pd.Series([True, True, True], dtype="boolean"),
                weights=pd.Series([1.0, 2.0, 2.0]),
                required_columns=["access", "weight"],
                method="weighted_proportion",
                duplicate_policy="reject",
                missing_value_treatment="Exclude documented nonresponse.",
                rounding_digits=2,
            )
            invalid_schema = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0], "unexpected": [1, 2, 3]})
            invalid_schema_result = calculate_verified_indicator(
                project_root=root,
                definition=catalogue["FI-ACCESS-001"],
                dataset=registry["synthetic-authorized"],
                source_verification=sources,
                input_data=invalid_schema,
                numerator=pd.Series([True, False, True], dtype="boolean"),
                denominator=pd.Series([True, True, True], dtype="boolean"),
                weights=invalid_schema["weight"],
            )
        self.assertIn("duplicate_observations", duplicate["blocker_ids"])
        self.assertIn("input_masks", [check["check_id"] for check in invalid_mask.as_dict()["checks"] if check["status"] == "fail"])
        self.assertIn("documented_schema", invalid_schema_result["blocker_ids"])
        self.assertIsNone(invalid_schema_result["estimate"])

    def test_zero_all_missing_and_inconsistent_denominator_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            zero = run_fixture(root, registry, catalogue, sources, numerator=[False, False, False], denominator=[False, False, False])
            all_missing = run_fixture(root, registry, catalogue, sources, numerator=[pd.NA, pd.NA, pd.NA], denominator=[pd.NA, pd.NA, pd.NA])
            inconsistent = run_fixture(root, registry, catalogue, sources, numerator=[True, False, False], denominator=[False, True, True])
        self.assertEqual(zero["calculation_status"], "zero_eligible_denominator")
        self.assertEqual(all_missing["calculation_status"], "zero_eligible_denominator")
        self.assertIn("inconsistent_numerator_denominator", inconsistent["blocker_ids"])

    def test_invalid_negative_zero_missing_and_nonfinite_weights(self):
        cases = ([1.0, -1.0, 2.0], [1.0, np.inf, 2.0], [1.0, None, 2.0], [1.0, "bad", 2.0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            results = [run_fixture(root, registry, catalogue, sources, weights=weights) for weights in cases]
            zero_definition = copy.deepcopy(catalogue["FI-ACCESS-001"])
            zero_definition["calculation_specification"]["duplicate_policy"] = "allow"
            zero_weight = run_fixture(root, registry, catalogue, sources, weights=[0.0, 0.0, 0.0], definition=zero_definition)
        for result in results:
            self.assertIn("invalid_or_missing_weights", result["blocker_ids"])
            self.assertIsNone(result["estimate"])
        self.assertEqual(zero_weight["calculation_status"], "zero_weight_denominator")

    def test_precision_metadata_and_repeated_numerical_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            first = run_fixture(root, registry, catalogue, sources)
            second = run_fixture(root, registry, catalogue, sources)
            thirds_definition = copy.deepcopy(catalogue["FI-ACCESS-001"])
            thirds_definition["calculation_specification"]["duplicate_policy"] = "allow"
            thirds = run_fixture(
                root, registry, catalogue, sources,
                access=[1, 0, 0],
                weights=[1.0, 1.0, 1.0],
                numerator=[True, False, False],
                definition=thirds_definition,
            )
        self.assertEqual(first["reproducibility"]["rounding_digits"], 4)
        self.assertEqual(first["estimate"], second["estimate"])
        self.assertEqual(first["percentage"], second["percentage"])
        self.assertEqual(thirds["reported_percentage"], 33.3333)
        self.assertEqual(first["provenance"]["dataset_release"], second["provenance"]["dataset_release"])
        self.assertNotEqual(first["provenance"]["calculated_at_utc"], second["provenance"]["calculated_at_utc"])

    def test_validation_distinguishes_blocked_not_run_and_unsupported_variance(self):
        blocked = validate_calculation_inputs(
            readiness_eligible=False,
            frame=None,
            numerator=None,
            denominator=None,
            weights=None,
            required_columns=["access"],
            method="weighted_proportion",
            duplicate_policy="reject",
            missing_value_treatment=None,
            rounding_digits=None,
        )
        unsupported = validate_calculation_inputs(
            readiness_eligible=True,
            frame=pd.DataFrame({"access": [1], "weight": [1.0]}),
            numerator=pd.Series([True], dtype="boolean"),
            denominator=pd.Series([True], dtype="boolean"),
            weights=pd.Series([1.0]),
            required_columns=["access", "weight"],
            method="weighted_proportion",
            duplicate_policy="reject",
            missing_value_treatment="Exclude documented nonresponse.",
            rounding_digits=2,
            confidence_interval_requested=True,
            variance_supported=False,
        )
        blocked_statuses = {check["check_id"]: check["status"] for check in blocked.as_dict()["checks"]}
        unsupported_statuses = {check["check_id"]: check["status"] for check in unsupported.as_dict()["checks"]}
        self.assertEqual(blocked_statuses["central_readiness"], "blocked")
        self.assertEqual(blocked_statuses["input_schema"], "not_run")
        self.assertEqual(unsupported_statuses["variance_method_support"], "blocked")
        self.assertFalse(unsupported.calculation_allowed)

    def test_result_integrity_and_publication_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, catalogue, sources = eligible_fixture(root)
            result = run_fixture(root, registry, catalogue, sources)
            integrity = validate_result_integrity(result)
            self.assertTrue(integrity.calculation_allowed)
            self.assertEqual(result["publication_status"], "not_approved")
            self.assertFalse(result["readiness"]["publication_eligible"])
            tampered = dict(result)
            tampered["records"] = [{"confidential": "never"}]
            self.assertFalse(validate_result_integrity(tampered).calculation_allowed)
            ineligible = dict(result)
            ineligible["readiness"] = dict(result["readiness"])
            ineligible["readiness"]["analysis_eligible"] = False
            self.assertFalse(validate_result_integrity(ineligible).calculation_allowed)
            from insightrwanda.analytics.phase14 import save_calculation_result

            with self.assertRaises(IndicatorBlockedError):
                save_calculation_result(ineligible, project_root=root)
            self.assertFalse((root / "artifacts" / "phase14_result.json").exists())

    def test_invalid_result_cannot_be_saved_as_success(self):
        from insightrwanda.analytics.phase14 import save_calculation_result

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(IndicatorBlockedError):
                save_calculation_result({"calculation_status": "calculated", "estimate": 0.5}, project_root=directory)
            self.assertFalse((Path(directory) / "artifacts" / "phase14_result.json").exists())


if __name__ == "__main__":
    unittest.main()
