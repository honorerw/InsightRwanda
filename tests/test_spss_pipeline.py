"""Tests for research.spss_pipeline — the second-source SPSS pipeline.

Synthetic fixtures are written as real small .sav files with keys prefixed
"F-S-" so fixture rows are recognisable and never presented as NISR findings.
The integration test runs the loader on the supplied SPSS source.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
import pyreadstat

from research.spss_pipeline import (
    SPSS_COLUMNS,
    SPSS_SUPPORTED,
    SPSS_WITHHELD,
    build_spss_profile,
    enrich_spss_analysis_data,
    load_spss_analysis_data,
)

SPSS_PATH = "data/Rwanda FinScope 2020_Final Data.sav"


def write_synthetic_sav(path: str, n: int = 40, seed: int = 5) -> None:
    """Create a tiny labelled .sav fixture shaped like the real source."""

    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        household = f"F-S-H{i // 2:03d}"  # two respondents per household
        rows.append({
            "ID": float(i + 1),
            "KEY": household,
            "HH_WEIGHT": float(rng.integers(1, 30)),
            "Individuals_Weight": float(rng.integers(1, 15)),
            "TOTAL_IND": float(rng.integers(1, 11)),
            "NUMVILL": float(rng.integers(1, 400)),
            "A1": float(rng.choice([1, 2, 3, 4, 5])),
            "A2": float(rng.choice([11, 12, 13, 21, 31, 51])),
            "A3": float(rng.choice([1, 2])),
            "B0": float(rng.choice([1, 2])),
            "B1": float(rng.integers(16, 90)),
            "B2": float(rng.choice([1, 2])),
            **{f"QF5_{j:02d}": float(rng.choice([1, 2, 3], p=[.45, .45, .1])) for j in range(1, 11)},
            "EF9": float(rng.choice([1, 2, 3], p=[.4, .5, .1])),
        })
    frame = pd.DataFrame(rows, columns=SPSS_COLUMNS)
    labels = {
        "A1": {1.0: "Kigali City", 2.0: "Southern Province", 3.0: "Western Province",
               4.0: "Northern Province", 5.0: "Eastern Province"},
        "QF5_04": {1.0: "Yes", 2.0: "No"},
        "EF9": {1.0: "Yes", 2.0: "No,"},
    }
    pyreadstat.write_sav(frame, path, column_labels={c: c for c in SPSS_COLUMNS},
                         variable_value_labels=labels)


class SpssLoaderFixtureTests(unittest.TestCase):
    """Unit tests on a written-to-disk synthetic .sav fixture."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.sav_path = "/tmp/finscope_fixture.sav"
        write_synthetic_sav(cls.sav_path)
        cls.frame = enrich_spss_analysis_data(load_spss_analysis_data(cls.sav_path))

    @classmethod
    def tearDownClass(cls):
        import os

        if os.path.exists(cls.sav_path):
            os.remove(cls.sav_path)

    def test_fixture_rows_are_identifiable_as_synthetic(self):
        self.assertTrue(self.frame["key"].str.startswith("F-S-").all())

    def test_rename_maps_documented_subset_only(self):
        for column in ("key", "hh_wt", "pop_wt", "hh_size", "province", "district",
                       "setting", "sex", "active_access", "mobile_money", "emergency_fund"):
            self.assertIn(column, self.frame.columns)
        for column in SPSS_WITHHELD:
            self.assertNotIn(column, self.frame.columns)

    def test_geography_codes_match_master_semantics(self):
        self.assertTrue(self.frame["a1"].isin([1, 2, 3, 4, 5]).all())
        self.assertEqual(set(self.frame["province"].unique()) <=
                         {"Kigali", "South", "West", "North", "East"}, True)
        self.assertFalse(self.frame["district"].str.contains("Unknown").all())
        self.assertTrue(self.frame["setting"].isin(["Urban", "Rural"]).all())
        self.assertTrue(self.frame["sex"].isin(["Male", "Female"]).all())

    def test_invalid_codes_are_never_counted_as_responses(self):
        # Code 3 exists in the fixture on every yes/no variable.
        for column in ("active_access", "mobile_money", "emergency_fund", "bank_use", "sacco_use"):
            values = self.frame[column]
            invalid_rows = values.isna()
            self.assertTrue((values.loc[~invalid_rows].isin([0, 1])).all())

    def test_weights_positive_and_duplicate_households_preserved(self):
        self.assertTrue((self.frame["hh_wt"] > 0).all())
        self.assertFalse(self.frame["key"].is_unique)  # row unit is individuals


class SpssRealSourceTests(unittest.TestCase):
    """Integration test on the supplied SPSS source (permitted analytic use)."""

    @classmethod
    def setUpClass(cls):
        cls.frame = enrich_spss_analysis_data(load_spss_analysis_data(SPSS_PATH))
        cls.profile = build_spss_profile(SPSS_PATH)

    def test_profile_shape(self):
        self.assertGreater(self.profile.rows, 12000)
        self.assertGreater(self.profile.source_variables, 1200)
        self.assertEqual(self.profile.mapped_variables, len(SPSS_COLUMNS))
        self.assertEqual(len(self.profile.source_sha256), 64)
        self.assertTrue(self.profile.psu_documented)

    def test_geography_fully_documented(self):
        unknown_districts = float((self.frame["district"] == "Unknown").mean())
        self.assertGreater(0.05, unknown_districts)  # almost all codes map
        self.assertTrue(self.frame["psu"].notna().all())

    def test_reproducible_indicators_compute(self):
        for column in SPSS_SUPPORTED:
            values = self.frame[column]
            self.assertGreaterEqual(values.mean(), 0.0)
            weighted = np.average(values.dropna(),
                                  weights=self.frame.loc[values.notna(), "hh_wt"])
            self.assertLess(0.0, weighted)
            self.assertLess(weighted, 1.0)

    def test_withheld_components_are_absent(self):
        for column in SPSS_WITHHELD:
            self.assertNotIn(column, self.frame.columns)

    def test_fi01_reproducible_fi04_withheld(self):
        """FI-01 computes over the reduced channel set; FI-04 (e9c) is withheld."""

        from research.indicators import calculate_indicator
        r = calculate_indicator(self.frame, "FI-01")
        self.assertGreater(1.0, r.estimate)
        self.assertGreater(r.estimate, 0.0)
        with self.assertRaises(ValueError):
            calculate_indicator(self.frame, "FI-04")


if __name__ == "__main__":
    unittest.main()
