from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.data.errors import DataLoaderError, DataPathError, SchemaValidationError, UnsupportedFormatError
from insightrwanda.data.loaders import load_csv, load_geojson, load_source
from insightrwanda.data.validation import (
    check_expected_columns,
    duplicate_column_names,
    validate_dataframe,
    validate_geojson_structure,
)


class DataLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "data" / "fixtures"
        self.data_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_valid_csv_preserves_identifier_like_column_as_string(self) -> None:
        path = self.data_dir / "sample.csv"
        path.write_text("key,amount\n001,10\n002,20\n", encoding="utf-8")

        frame = load_csv(path, project_root=self.root)

        self.assertEqual(frame["key"].dtype.name, "string")
        self.assertEqual(frame["key"].tolist(), ["001", "002"])
        self.assertEqual(frame.shape, (2, 2))

    def test_malformed_csv_raises_safe_loader_error(self) -> None:
        path = self.data_dir / "malformed.csv"
        path.write_text('key,amount\n001,"unterminated\n', encoding="utf-8")

        with self.assertRaises(DataLoaderError):
            load_csv(path, project_root=self.root)

    def test_geojson_structure_validation(self) -> None:
        document = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"label": "Synthetic"},
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                }
            ],
        }
        path = self.data_dir / "sample.geojson"
        path.write_text(json.dumps(document), encoding="utf-8")

        loaded = load_geojson(path, project_root=self.root)
        summary = validate_geojson_structure(loaded)

        self.assertEqual(summary["type"], "FeatureCollection")
        self.assertEqual(summary["feature_count"], 1)

    def test_path_traversal_is_rejected(self) -> None:
        outside = self.root / "outside.csv"
        outside.write_text("key\n001\n", encoding="utf-8")

        with self.assertRaises(DataPathError):
            load_csv(outside, project_root=self.root)

    def test_missing_expected_columns_are_reported(self) -> None:
        frame = pd.DataFrame({"present": [1, 2]})

        self.assertEqual(check_expected_columns(frame, ["present", "missing"]), ("missing",))
        report = validate_dataframe(frame, expected_columns=["present", "missing"])
        self.assertEqual(report.missing_expected_columns, ("missing",))
        with self.assertRaises(SchemaValidationError):
            from insightrwanda.data.validation import require_expected_columns

            require_expected_columns(frame, ["missing"])

    def test_duplicate_column_names_are_detected(self) -> None:
        frame = pd.DataFrame([[1, 2]], columns=["same", "same"])

        self.assertEqual(duplicate_column_names(frame.columns), ("same",))
        self.assertEqual(validate_dataframe(frame).duplicate_columns, ("same",))

    def test_unsupported_format_is_rejected(self) -> None:
        path = self.data_dir / "sample.txt"
        path.write_text("not a supported source", encoding="utf-8")

        with self.assertRaises(UnsupportedFormatError):
            load_source(path, project_root=self.root)


if __name__ == "__main__":
    unittest.main()

