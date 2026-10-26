import unittest

import numpy as np
import pandas as pd

from research.data_pipeline import INCOME_BAND_ANNUAL, INCOME_BAND_MONTHLY, enrich_analysis_data, load_analysis_data
from research.estimation import (
    ANNUAL_INCOME, CONTEXT_ESTIMATES, MONTHLY_INCOME,
    calculate_context_estimate, context_weight_distribution,
    indicator_value_for, official_poverty_status, weighted_bootstrap_ci,
)
from research.indicators import INDICATORS, indicator_value




class EstimationUnitTests(unittest.TestCase):
    def test_bootstrap_interval_brackets_point_estimate_and_reproduces(self):
        fixture = pd.DataFrame({
            "hh_wt": np.ones(40),
            "qf4_05": np.repeat([1, 2], 20),
        })
        first = weighted_bootstrap_ci(fixture, "FI-02", n_boot=500, seed=7)
        second = weighted_bootstrap_ci(fixture, "FI-02", n_boot=500, seed=7)
        self.assertEqual(first, second)
        self.assertLessEqual(first.low, 0.5)
        self.assertGreaterEqual(first.high, 0.5)
        self.assertIn("NOT a survey-design standard error", first.note)

    def test_bootstrap_detects_extreme_data_via_wider_interval(self):
        mixed = pd.DataFrame({
            "hh_wt": np.ones(60),
            "qf4_05": [1] * 30 + [2] * 30,
        })
        unanimous = pd.DataFrame({
            "hh_wt": np.ones(60),
            "qf4_05": [1] * 60,
        })
        mixed_ci = weighted_bootstrap_ci(mixed, "FI-02", n_boot=300)
        unanimous_ci = weighted_bootstrap_ci(unanimous, "FI-02", n_boot=300)
        self.assertGreater(mixed_ci.high - mixed_ci.low, 0.0)
        self.assertEqual(unanimous_ci.high, unanimous_ci.low)
        self.assertAlmostEqual(mixed_ci.low, 0.5, delta=0.15)
        self.assertAlmostEqual(mixed_ci.high, 0.5, delta=0.15)

    def test_context_estimates_exclude_refusal_and_counts_irregular(self):
        fixture = pd.DataFrame({
            "hh_wt": [1.0] * 8,
            MONTHLY_INCOME: [1, 2, 1, 16, 99, np.nan, 2, 1],
        })
        low = calculate_context_estimate(fixture, "EI-01")
        irregular = calculate_context_estimate(fixture, "EI-02")
        self.assertAlmostEqual(low["estimate"], 5 / 6, places=12)
        self.assertAlmostEqual(irregular["estimate"], 1 / 6, places=12)
        self.assertAlmostEqual(low["weight_sum"], 6.0)

    def test_context_estimate_valid_response_rule_matches_definition(self):
        for estimate_id in CONTEXT_ESTIMATES:
            frame = pd.DataFrame({
                "hh_wt": [1.0, 2.0, 1.0],
                MONTHLY_INCOME if estimate_id != "EI-03" else ANNUAL_INCOME: [1, 2, 16 if estimate_id != "EI-03" else 99],
            })
            values = indicator_value_for(frame, CONTEXT_ESTIMATES[estimate_id])
            if estimate_id == "EI-02":
                self.assertEqual(values.tolist()[:2], [0.0, 0.0])
            elif estimate_id == "EI-01":
                self.assertEqual(values.tolist()[:2], [1.0, 1.0])
            else:
                self.assertEqual(values.tolist()[:2], [1.0, 1.0])

    def test_context_missing_columns_fail_loudly(self):
        with self.assertRaises(ValueError):
            calculate_context_estimate(pd.DataFrame({"hh_wt": [1.0]}), "EI-01")

    def test_unknown_context_estimate_raises(self):
        with self.assertRaises(KeyError):
            _ = CONTEXT_ESTIMATES["EI-99"]  # noqa: F841  # pylint: disable=pointless-statement

    def test_distribution_labels_use_embedded_bands(self):
        fixture = pd.DataFrame({
            "hh_wt": [2.0], MONTHLY_INCOME: [16],
        })
        series = context_weight_distribution(fixture, MONTHLY_INCOME)
        self.assertIn(INCOME_BAND_MONTHLY[16], series.index)
        self.assertTrue(all(isinstance(band, str) for band in series.index))

    def test_official_poverty_contract_requires_every_input(self):
        status_1 = official_poverty_status()
        self.assertFalse(status_1.ready)
        self.assertEqual(len(status_1.missing), 6)
        status_2 = official_poverty_status(
            poverty_line_rwf=175000.0,
            poverty_concept="national absolute",
            welfare_aggregate=pd.Series(np.ones(10), name="welfare"),
            variance_documentation="strata+psu documented",
            authorization="Approved by steward",
            publication_approval="Approved",
        )
        self.assertTrue(status_2.ready)
        self.assertEqual(status_2.missing, ())
        self.assertEqual(status_2.supplied["poverty_line_rwf"], "175,000")

    def test_half_supplied_poverty_status_still_blocked(self):
        blocked = official_poverty_status(poverty_line_rwf=125_000.0)
        self.assertFalse(blocked.ready)
        self.assertEqual(len(blocked.missing), 5)


class GoldenSourceEstimationTests(unittest.TestCase):
    ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        cls.raw = load_analysis_data(cls.ROOT / "data" / "FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta")
        cls.data = enrich_analysis_data(cls.raw)

    def test_real_source_band_labels_are_consistent_with_pipeline_dicts(self):
        for estimate_id in CONTEXT_ESTIMATES:
            column = CONTEXT_ESTIMATES[estimate_id].source_variables[0]
            allowed = set(range(1, 17)) if column == MONTHLY_INCOME else set(range(1, 15))
            observed = set(self.data[column].dropna().astype(int).unique())
            self.assertTrue(observed <= allowed, f"{estimate_id}: stray band codes {observed - allowed}")

    def test_real_source_bootstrap_ci_fits_indicator_estimate(self):
        result = weighted_bootstrap_ci(self.data, "FI-02", n_boot=200, seed=11)
        point = indicator_value(self.data, "FI-02")
        valid = point.notna() & self.data["hh_wt"].gt(0) & np.isfinite(self.data["hh_wt"])
        expected = np.average(point[valid], weights=self.data.loc[valid, "hh_wt"])
        self.assertAlmostEqual(result.estimate, expected, places=12)
        self.assertLessEqual(result.low, result.estimate)
        self.assertLessEqual(result.estimate, result.high)
        for indicator_id in ("FI-01", "FI-03", "FI-06"):
            ci = weighted_bootstrap_ci(self.data, indicator_id, n_boot=120, seed=11)
            self.assertLessEqual(ci.low, ci.estimate, indicator_id)
            self.assertLessEqual(ci.estimate, ci.high, indicator_id)

    def test_real_source_context_estimates_have_positive_weight(self):
        for estimate_id in CONTEXT_ESTIMATES:
            result = calculate_context_estimate(self.data, estimate_id)
            self.assertGreater(float(result["weight_sum"]), 0, estimate_id)
            definition = result["definition"]
            self.assertIn("not a poverty rate" if estimate_id in ("EI-01", "EI-03") else "project-calculated",
                          definition.verification, estimate_id)

    def test_real_source_filled_band_labels_cover_n12(self):
        self.assertEqual(INCOME_BAND_ANNUAL[1], "12,000 Rwf or less")
        self.assertEqual(INCOME_BAND_ANNUAL[14], "More than 300,000 Rwf")


if __name__ == "__main__":
    unittest.main()
