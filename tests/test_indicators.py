from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from insightrwanda.analytics.catalogue import get_indicator, load_indicator_catalogue
from insightrwanda.analytics.indicators import (
    assert_indicator_calculable,
    calculate_proportion,
    calculate_weighted_proportion,
    validate_weights,
)
from insightrwanda.data.errors import IndicatorBlockedError, IndicatorDefinitionError


class IndicatorTests(unittest.TestCase):
    def test_proportion_and_percentage_use_explicit_denominator(self) -> None:
        numerator = pd.Series([True, False, True, None], dtype="boolean")
        denominator = pd.Series([True, True, False, True], dtype="boolean")

        result = calculate_proportion(numerator, denominator, indicator_id="SYNTHETIC")

        self.assertEqual(result["numerator_count"], 1)
        self.assertEqual(result["denominator_count"], 2)
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(result["estimate"], 0.5)
        self.assertEqual(result["percentage"], 50.0)

    def test_zero_denominator_is_explicit(self) -> None:
        numerator = pd.Series([True, False], dtype="boolean")
        denominator = pd.Series([False, False], dtype="boolean")

        result = calculate_proportion(numerator, denominator)

        self.assertEqual(result["calculation_status"], "zero_denominator")
        self.assertIsNone(result["estimate"])
        self.assertIsNone(result["percentage"])

    def test_missing_values_are_excluded_and_counted(self) -> None:
        numerator = pd.Series([True, False, None], dtype="boolean")

        result = calculate_proportion(numerator)

        self.assertEqual(result["numerator_count"], 1)
        self.assertEqual(result["denominator_count"], 2)
        self.assertEqual(result["excluded_count"], 1)

    def test_weighted_proportion_is_not_replaced_by_unweighted(self) -> None:
        numerator = pd.Series([True, False, True], dtype="boolean")
        weights = pd.Series([1.0, 3.0, 1.0])

        result = calculate_weighted_proportion(numerator, weights)

        self.assertTrue(result["weighted"])
        self.assertEqual(result["weighted_numerator"], 2.0)
        self.assertEqual(result["weighted_denominator"], 5.0)
        self.assertEqual(result["estimate"], 0.4)

    def test_invalid_negative_nonfinite_and_zero_weights_are_reported(self) -> None:
        weights = pd.Series([1.0, -1.0, np.inf, 0.0, None, "bad"])

        diagnostics = validate_weights(weights)
        result = calculate_weighted_proportion(
            pd.Series([True, True, True, False, True, True], dtype="boolean"),
            weights,
        )

        self.assertEqual(diagnostics["negative_count"], 1)
        self.assertEqual(diagnostics["non_finite_count"], 1)
        self.assertEqual(diagnostics["zero_count"], 1)
        self.assertEqual(diagnostics["invalid_count"], 1)
        self.assertEqual(result["excluded_count"], 4)
        self.assertNotEqual(result["calculation_status"], "calculated_unweighted")

    def test_all_zero_weights_have_no_estimate(self) -> None:
        result = calculate_weighted_proportion(
            pd.Series([True, False], dtype="boolean"),
            pd.Series([0.0, 0.0]),
        )

        self.assertEqual(result["calculation_status"], "zero_weight_denominator")
        self.assertIsNone(result["estimate"])

    def test_missing_required_or_non_boolean_inputs_are_rejected(self) -> None:
        with self.assertRaises(IndicatorDefinitionError):
            calculate_proportion(pd.Series([1, 0]))
        with self.assertRaises(IndicatorDefinitionError):
            calculate_proportion(pd.Series([True, False]), pd.Series([True]))

    def test_catalogue_entries_are_blocked_without_verified_mappings(self) -> None:
        catalogue_path = Path("data/metadata/indicator_catalogue.json")
        catalogue = load_indicator_catalogue(catalogue_path)
        definition = get_indicator(catalogue, "FI-ACCESS-001")

        with self.assertRaises(IndicatorBlockedError):
            assert_indicator_calculable(definition, ["synthetic_column"])

    def test_catalogue_missing_id_is_rejected(self) -> None:
        catalogue = load_indicator_catalogue(Path("data/metadata/indicator_catalogue.json"))
        with self.assertRaises(IndicatorDefinitionError):
            get_indicator(catalogue, "NOT-A-REAL-INDICATOR")

    def test_calculation_is_reproducible_and_does_not_mutate_input(self) -> None:
        frame = pd.DataFrame({"answer": [True, False, True], "weight": [1.0, 2.0, 1.0]})
        before = copy.deepcopy(frame)

        first = calculate_weighted_proportion(frame["answer"], frame["weight"])
        second = calculate_weighted_proportion(frame["answer"], frame["weight"])

        self.assertEqual(first, second)
        pd.testing.assert_frame_equal(frame, before)
        self.assertNotIn("1.0", json.dumps(first))

    def test_empty_input_is_handled(self) -> None:
        result = calculate_proportion(pd.Series([], dtype="boolean"))

        self.assertEqual(result["calculation_status"], "zero_denominator")
        self.assertEqual(result["excluded_count"], 0)

    def test_report_metadata_distinguishes_unverified_status(self) -> None:
        result = calculate_proportion(
            pd.Series([True, False], dtype="boolean"),
            source_authorization_status="unverified",
            indicator_definition_status="proposed_pending_review",
        )

        self.assertEqual(result["source_authorization_status"], "unverified")
        self.assertEqual(result["indicator_definition_status"], "proposed_pending_review")
        self.assertFalse(result["eligible_for_publication"])


if __name__ == "__main__":
    unittest.main()

