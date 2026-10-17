from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from insightrwanda.data.errors import DataPathError, DataPreparationError
from insightrwanda.data.prepare import PreparationConfig, prepare_dataset


class PreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "data" / "fixtures").mkdir(parents=True)
        (self.root / "artifacts").mkdir()
        self.source = self.root / "data" / "fixtures" / "synthetic.csv"
        self.source.write_text(
            "household_id,hh_wt,value\nS-001,1.0,10\nS-002,2.0,20\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_unverified_source_requires_explicit_local_override(self) -> None:
        with self.assertRaises(DataPreparationError):
            prepare_dataset(
                self.source,
                self.root / "artifacts" / "prepared.csv",
                project_root=self.root,
            )

    def test_explicit_preparation_preserves_identifier_and_weight_columns(self) -> None:
        output = self.root / "artifacts" / "prepared.csv"
        report = prepare_dataset(
            self.source,
            output,
            project_root=self.root,
            config=PreparationConfig(
                required_columns=("household_id", "hh_wt"),
                weight_columns=("hh_wt",),
                source_authorization_status="synthetic_test",
            ),
        )

        self.assertTrue(output.is_file())
        self.assertTrue((self.root / "artifacts" / "prepared.metadata.json").is_file())
        self.assertEqual(report["weight_columns_preserved"], ["hh_wt"])
        self.assertFalse(report["eligible_for_publication"])
        written = output.read_text(encoding="utf-8")
        self.assertIn("household_id", written)
        self.assertIn("hh_wt", written)
        metadata = json.loads((self.root / "artifacts" / "prepared.metadata.json").read_text())
        self.assertEqual(metadata["source_authorization_status"], "synthetic_test")

    def test_source_path_cannot_be_overwritten(self) -> None:
        with self.assertRaises(DataPathError):
            prepare_dataset(
                self.source,
                self.source,
                project_root=self.root,
                config=PreparationConfig(source_authorization_status="synthetic_test"),
            )

    def test_output_path_must_be_derived_or_artifact_path(self) -> None:
        with self.assertRaises(DataPathError):
            prepare_dataset(
                self.source,
                self.root / "outside" / "prepared.csv",
                project_root=self.root,
                config=PreparationConfig(source_authorization_status="synthetic_test"),
            )

    def test_identifier_numeric_cast_is_rejected(self) -> None:
        with self.assertRaises(DataPreparationError):
            prepare_dataset(
                self.source,
                self.root / "artifacts" / "prepared.csv",
                project_root=self.root,
                config=PreparationConfig(
                    cast_columns={"household_id": "int64"},
                    source_authorization_status="synthetic_test",
                ),
            )

