from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.data.errors import DataPathError
from insightrwanda.data.quality import QualityConfig, profile_dataframe, write_quality_report


class QualityProfileTests(unittest.TestCase):
    def test_missingness_and_numeric_summary_are_aggregate_only(self) -> None:
        frame = pd.DataFrame(
            {
                "household_id": ["S-001", "S-002", "S-002"],
                "income": [10.0, None, 10.0],
                "category": ["A", "A", "A"],
            }
        )

        report = profile_dataframe(frame)
        by_name = {item["name"]: item for item in report["columns"]}

        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["duplicate_row_count"], 0)
        self.assertEqual(by_name["income"]["missing_count"], 1)
        self.assertAlmostEqual(by_name["income"]["missing_percentage"], 100 / 3)
        self.assertEqual(by_name["income"]["numeric_summary"]["finite_count"], 2)
        serialized = json.dumps(report)
        self.assertNotIn("S-001", serialized)
        self.assertNotIn("S-002", serialized)

    def test_empty_dataset_is_profiled_without_failure(self) -> None:
        frame = pd.DataFrame(columns=["key", "amount"])

        report = profile_dataframe(frame)

        self.assertEqual(report["row_count"], 0)
        self.assertEqual(report["column_count"], 2)
        self.assertIsNone(report["columns"][0]["missing_percentage"])
        self.assertEqual(report["duplicate_row_count"], 0)

    def test_duplicate_rows_and_duplicate_columns_are_reported(self) -> None:
        frame = pd.DataFrame([[1, 1], [1, 1], [2, 3]], columns=["same", "same"])

        report = profile_dataframe(frame)

        self.assertEqual(report["duplicate_row_count"], 1)
        self.assertEqual(report["duplicate_column_names"], ["same"])

    def test_identifier_and_weight_warnings_are_candidates_not_assertions(self) -> None:
        frame = pd.DataFrame(
            {
                "person_id": [1, 2, 3],
                "hh_wt": [1.0, 0.0, -1.0],
                "label": ["x", "y", None],
            }
        )

        report = profile_dataframe(frame)

        self.assertEqual(report["source_authorization_status"], "unverified")
        self.assertFalse(report["eligible_for_publication"])
        self.assertIn("person_id", [item["column"] for item in report["candidate_identifier_columns"]])
        self.assertEqual(report["candidate_weight_columns"][0]["zero_count"], 1)
        self.assertEqual(report["candidate_weight_columns"][0]["negative_count"], 1)
        self.assertTrue(any("numeric dtype" in warning for warning in report["warnings"]))

    def test_profile_is_reproducible(self) -> None:
        frame = pd.DataFrame({"key": ["a", "b"], "value": [1, 2]})

        self.assertEqual(profile_dataframe(frame), profile_dataframe(frame))

    def test_quality_report_requires_derived_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = profile_dataframe(pd.DataFrame({"value": [1, 2]}))
            with self.assertRaises(DataPathError):
                write_quality_report(report, root / "data" / "source.json", project_root=root)

