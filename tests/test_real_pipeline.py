import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from research.catalog import aggregate_release_allowed, build_source_profile
from research.data_pipeline import (
    SourceLoadError,
    aggregate_weighted_measure,
    enrich_analysis_data,
    filter_analysis_data,
    load_analysis_data,
)
from research.indicators import INDICATORS, calculate_indicator
from research.quality import run_quality_checks


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "dataset.dta"


class RealSourcePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load_analysis_data(SOURCE)
        cls.data = enrich_analysis_data(cls.raw)
        cls.profile = build_source_profile(SOURCE, analytical_variables=94)

    def test_supplied_source_is_loaded(self):
        self.assertEqual(self.raw.shape[0], 13994)
        self.assertEqual(self.profile.source_variables, 2442)
        self.assertEqual(self.profile.rows, 13994)
        self.assertEqual(len(self.profile.source_sha256), 64)
        self.assertRegex(self.profile.analysis_version, r"^financial_inclusion_[0-9a-f]{12}$")

    def test_source_is_read_only_and_repeatable(self):
        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        before = digest(SOURCE)
        repeat = load_analysis_data(SOURCE)
        after = digest(SOURCE)
        pd.testing.assert_frame_equal(self.raw, repeat)
        self.assertEqual(before, after)
        self.assertEqual(before, self.profile.source_sha256)

    def test_required_source_fields_are_present_and_weighted(self):
        self.assertTrue(self.data["hh_wt"].gt(0).all())
        self.assertEqual(self.data["key"].duplicated().sum(), 0)
        self.assertSetEqual(set(self.data["province"]), {"Kigali", "South", "West", "North", "East"})

    def test_quality_checks_report_real_source_findings(self):
        checks = run_quality_checks(self.data, source_variable_count=self.profile.source_variables)
        self.assertEqual(sum(check.status == "FAIL" for check in checks), 0)
        self.assertEqual(next(check for check in checks if check.check_id == "unique_household_key").evidence["duplicate_rows"], 0)

    def test_all_indicators_are_independently_reproducible(self):
        manual_values = {
            "FI-01": self.data[[f"qf4_{i:02d}" for i in range(1, 7)]].where(lambda x: x.isin([1, 2])).eq(1).any(axis=1).astype(float).mask(self.data[[f"qf4_{i:02d}" for i in range(1, 7)]].where(lambda x: x.isin([1, 2])).notna().any(axis=1).eq(False)),
            "FI-02": self.data["qf4_05"].where(self.data["qf4_05"].isin([1, 2])).eq(1).astype(float).mask(~self.data["qf4_05"].isin([1, 2])),
            "FI-03": self.data["e9b"].where(self.data["e9b"].isin([1, 2])).eq(1).astype(float).mask(~self.data["e9b"].isin([1, 2])),
            "FI-04": self.data["e9c"].where(self.data["e9c"].isin([1, 2, 3])).isin([1, 2]).astype(float).mask(~self.data["e9c"].isin([1, 2, 3])),
            "FI-05": self.data["e7"].where(self.data["e7"].isin([1, 2, 3, 4])).isin([1, 2]).astype(float).mask(~self.data["e7"].isin([1, 2, 3, 4])),
            "FI-06": self.data["c14_5"].where(self.data["c14_5"].isin([1, 2])).eq(1).astype(float).mask(~self.data["c14_5"].isin([1, 2])),
        }
        for indicator_id in INDICATORS:
            values = manual_values[indicator_id]
            valid = values.notna() & self.data["hh_wt"].gt(0) & np.isfinite(self.data["hh_wt"])
            expected = np.average(values[valid], weights=self.data.loc[valid, "hh_wt"])
            result = calculate_indicator(self.data, indicator_id)
            self.assertAlmostEqual(result.estimate, expected, places=12, msg=indicator_id)
            self.assertEqual(result.denominator_n, int(valid.sum()), indicator_id)
            self.assertEqual(result.numerator_n, int((values[valid] == 1).sum()), indicator_id)

    def test_dashboard_derived_active_access_matches_indicator_rule(self):
        expected = self.data[[f"qf4_{i:02d}" for i in range(1, 7)]].where(
            lambda x: x.isin([1, 2])
        ).eq(1).any(axis=1).astype(float)
        substantive = self.data[[f"qf4_{i:02d}" for i in range(1, 7)]].where(
            lambda x: x.isin([1, 2])
        ).notna().any(axis=1)
        expected = expected.mask(~substantive)
        pd.testing.assert_series_equal(
            self.data["active_access"], expected, check_names=False
        )

    def test_invalid_weights_and_unexpected_codes_are_excluded(self):
        fixture = pd.DataFrame({"hh_wt": [1.0, 2.0, 0.0, -1.0, np.inf, np.nan], "qf4_05": [1, 2, 1, 1, 99, np.nan]})
        result = calculate_indicator(fixture, "FI-02")
        self.assertAlmostEqual(result.estimate, 1 / 3)
        self.assertEqual(result.denominator_n, 2)
        self.assertEqual(result.numerator_n, 1)

    def test_quality_checks_handle_invalid_source_structure(self):
        bad = self.data.head(4).copy()
        bad.loc[bad.index[1], "key"] = bad.loc[bad.index[0], "key"]
        bad.loc[bad.index[0], "hh_wt"] = 0
        bad.loc[bad.index[1], "hh_wt"] = np.inf
        bad.loc[bad.index[0], "a1"] = 1
        bad.loc[bad.index[0], "a2"] = 51
        bad.loc[bad.index[0], "qf4_05"] = 88
        checks = run_quality_checks(bad)
        by_id = {check.check_id: check for check in checks}
        self.assertEqual(by_id["unique_household_key"].status, "FAIL")
        self.assertEqual(by_id["household_weight"].status, "FAIL")
        self.assertEqual(by_id["core_value_codes"].status, "WARN")
        self.assertEqual(by_id["district_province_consistency"].status, "WARN")

    def test_missing_schema_does_not_crash_quality_checks(self):
        checks = run_quality_checks(pd.DataFrame({"key": [1]}))
        by_id = {check.check_id: check for check in checks}
        self.assertEqual(by_id["schema_required_columns"].status, "FAIL")
        self.assertEqual(by_id["household_weight"].status, "FAIL")
        self.assertEqual(by_id["geographic_codes"].status, "FAIL")

    def test_filtering_is_consistent_and_empty_filters_are_safe(self):
        kigali_female = filter_analysis_data(self.data, province="Kigali", setting="Urban", respondent_sex="Female")
        self.assertTrue((kigali_female["province"] == "Kigali").all())
        self.assertTrue((kigali_female["setting"] == "Urban").all())
        self.assertTrue((kigali_female["sex"] == "Female").all())
        self.assertTrue(filter_analysis_data(self.data, province="No such province").empty)
        with self.assertRaises(ValueError):
            filter_analysis_data(self.data.drop(columns=["district"]), district="Huye")

    def test_source_errors_are_explicit(self):
        with self.assertRaises(FileNotFoundError):
            load_analysis_data(ROOT / "data" / "missing.dta")
        with tempfile.NamedTemporaryFile(suffix=".dta") as corrupted:
            corrupted.write(b"not a stata file")
            corrupted.flush()
            with self.assertRaises(SourceLoadError):
                load_analysis_data(corrupted.name)

    def test_publication_gate_is_closed_without_explicit_approval(self):
        self.assertFalse(aggregate_release_allowed(self.profile))
        approved = replace(self.profile, authorization_status="Approved by data steward", publication_status="Approved for publication")
        self.assertTrue(aggregate_release_allowed(approved))

    def test_explorer_aggregation_is_weighted_and_record_safe(self):
        aggregate = aggregate_weighted_measure(self.data, "mobile_money", dimensions=("province",))
        self.assertEqual(set(aggregate["province"]), {"Kigali", "South", "West", "North", "East"})
        self.assertTrue((aggregate["records"] > 0).all())
        self.assertTrue((aggregate["valid_records"] <= aggregate["records"]).all())
        self.assertTrue((aggregate["positive_records"] <= aggregate["valid_records"]).all())
        self.assertTrue((aggregate["weight_sum"] > 0).all())
        self.assertNotIn("key", aggregate.columns)


if __name__ == "__main__":
    unittest.main()
