from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.phase12 import build_phase12_status, inspect_registered_dataset


def registered(**changes):
    dataset = {
        "dataset_id": "synthetic-test", "source_path": "mine/fixture.csv", "file_format": "csv",
        "provenance_status": "verified", "documentation_status": "verified", "license_status": "verified",
        "codebook_status": "verified", "authorization_status": "authorized_for_analysis", "analytical_eligibility": True,
        "verified_schema_columns": ["answer", "weight"],
    }
    dataset.update(changes)
    return {dataset["dataset_id"]: dataset}


class Phase12IntakeTests(unittest.TestCase):
    def test_missing_source_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_registered_dataset(registered(), "synthetic-test", project_root=directory)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("absent" in item for item in result["requirements"]))

    def test_unauthorized_source_is_not_opened_even_if_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data" / "mine" / "fixture.csv"
            source.parent.mkdir(parents=True)
            source.write_text("secret,value\nPERSON,42\n", encoding="utf-8")
            result = inspect_registered_dataset(registered(authorization_status="unverified"), "synthetic-test", project_root=root)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["file_inspected"])
        self.assertNotIn("secret", str(result))

    def test_path_traversal_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_registered_dataset(registered(source_path="../outside.csv"), "synthetic-test", project_root=directory)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["file_inspected"])

    def test_authorized_intake_returns_header_size_and_checksum_not_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data" / "mine" / "fixture.csv"
            source.parent.mkdir(parents=True)
            source.write_text("answer,weight\nYES,1\n", encoding="utf-8")
            result = inspect_registered_dataset(registered(), "synthetic-test", project_root=root)
        self.assertEqual(result["status"], "inspected")
        self.assertEqual(result["schema_columns"], ["answer", "weight"])
        self.assertEqual(result["records_read"], 0)
        self.assertNotIn("YES", str(result))

    def test_schema_must_match_documented_expectations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data" / "mine" / "fixture.csv"
            source.parent.mkdir(parents=True)
            source.write_text("answer,wrong\nYES,1\n", encoding="utf-8")
            result = inspect_registered_dataset(registered(), "synthetic-test", project_root=root)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["schema_validation"], "failed")
        self.assertEqual(result["records_read"], 0)

    def test_phase12_does_not_report_a_result_when_gates_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_phase12_status(
                {"finscope_2024_rwanda_csv": {"dataset_id": "finscope_2024_rwanda_csv", "source_path": "mine/missing.csv", "file_format": "csv"}},
                {"FI-ACCESS-001": {"indicator_id": "FI-ACCESS-001", "required_variables": []}},
                project_root=directory,
            )
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["indicator_calculated"])
        self.assertIsNone(report["result"])
        self.assertFalse(report["analysis_eligible"])
        self.assertFalse(report["publication_eligible"])


if __name__ == "__main__":
    unittest.main()
