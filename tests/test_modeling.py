"""Tests for research.modeling — the real predictive-analytics workflow.

Every synthetic frame here is clearly labelled as a TEST FIXTURE; results from
it are never presented as genuine Rwanda research findings. The integration
test runs the actual workflow on the supplied Stata source.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.data_pipeline import load_analysis_data, enrich_analysis_data
from research.modeling import (
    BASELINE_NAME,
    BLOCKED_FROM_FEATURES,
    CANDIDATE_NAMES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    ModelRecord,
    build_model_frame,
    evaluate_candidates,
    holdout_artifacts,
    predict_priority,
    pr_curve,
    select_candidate,
    subgroup_performance,
    threshold_metrics,
    train_final_model,
)


def synthetic_survey_frame(n: int = 900, seed: int = 3) -> pd.DataFrame:
    """Labelled synthetic fixture mimicking the analytical slice's shape.

    Rows carry synthetic keys starting with "F-" so fixture data is easy to
    recognise. The Priority band is made predictable from shock-outcome codes
    that do NOT define it, while the four lens components (which DO define the
    band) are present in the frame and must never enter the feature set.
    """

    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        key = f"F-{i:05d}"  # one row per household, like the real slice
        province = str(rng.choice(["Kigali", "South", "West", "North", "East"]))
        setting = str(rng.choice(["Urban", "Rural"], p=[.3, .7]))
        bleeder = float(rng.normal())  # drives the label but is NOT a lens component
        latent = float(np.clip((bleeder + 1.5) / 3, 0, 1))  # ~N(0,1) mapped into [0,1]
        # Observable shock/emergency codes carry the latent signal, so the
        # fixture is genuinely learnable from the features the model may use.
        shock_d = float(1 + rng.binomial(6, .15 + .5 * latent))
        shock_e = float(1 + rng.binomial(6, .1 + .55 * latent))
        emergency_code = float(1 + rng.binomial(2, .2 + .5 * latent))
        # Band thresholds: Priority < .4, Watch < .7, else Resilient.
        score = float(np.clip(.05 + .085 * (shock_d + shock_e), 0, .92))
        band = "Priority" if score < .4 else ("Watch" if score < .7 else "Resilient")
        rows.append({
            "key": key,
            "province": province,
            "district": "Gasabo",
            "setting": setting,
            "sex": str(rng.choice(["Female", "Male"])),
            "head_sex": str(rng.choice(["Female", "Male"])),
            "hh_wt": float(rng.integers(1, 40)),
            "hh_size": int(rng.integers(1, 11)),
            "b2": float(rng.choice([1, 2])),
            "a6": 1.0 if setting == "Urban" else 2.0,
            "c14_5": float(rng.choice([1, 2], p=[.4, .6])),
            "f3": float(rng.choice([1, 2], p=[.7, .3])),
            "qf4_05": float(rng.choice([1, 2], p=[.6, .4])),
            "e2d": shock_d,
            "e2e": shock_e,
            "e9c": emergency_code,
            "e6": float(rng.choice([1, 2, 3, 4], p=[.5, .2, .2, .1])),
            "e7": float(rng.choice([1, 2, 3, 4], p=[.4, .3, .2, .1])),
            "emergency_fund": float(score >= .25),
            "owns_money": float(score >= .25),
            "saves_regularly": float(score >= .2),
            "social_safety_net": float(score >= .1),
            "resilience_score": score,
            "resilience_band": band,
        })
    return pd.DataFrame(rows)


class ModelingFixtureTests(unittest.TestCase):
    """Unit tests on the labelled synthetic fixture."""

    def test_leakage_guard_blocks_target_defining_features(self):
        frame = synthetic_survey_frame(200)
        X, y, groups, weights = build_model_frame(frame)
        columns = set(X.columns)
        self.assertEqual(len(columns), len(CATEGORICAL_FEATURES) + len(NUMERIC_FEATURES))
        self.assertTrue(columns.isdisjoint(set(BLOCKED_FROM_FEATURES)))
        self.assertFalse(y.isna().any())
        self.assertFalse(weights.isna().any())
        self.assertTrue((weights > 0).all())

    def test_fixture_rows_are_identifiable_as_synthetic(self):
        frame = synthetic_survey_frame(50)
        self.assertTrue(frame["key"].str.startswith("F-").all())

    def test_baseline_is_worst_candidate(self):
        frame = synthetic_survey_frame()
        results, *_ = evaluate_candidates(frame)
        baseline = next(r for r in results if r.name == BASELINE_NAME)
        for candidate in results:
            if candidate.name != BASELINE_NAME:
                self.assertGreaterEqual(candidate.mean_auc, baseline.mean_auc)
                self.assertGreaterEqual(candidate.mean_f1, baseline.mean_f1)

    def test_selection_rule_excludes_baseline(self):
        frame = synthetic_survey_frame()
        results, *_ = evaluate_candidates(frame)
        chosen = select_candidate(results)
        self.assertNotEqual(chosen.name, BASELINE_NAME)
        self.assertIn(chosen.name, CANDIDATE_NAMES)

    def test_final_model_record_has_audit_shape(self):
        record = train_final_model(synthetic_survey_frame())
        self.assertIsInstance(record, ModelRecord)
        self.assertIn(record.model_name, CANDIDATE_NAMES)
        self.assertFalse(set(record.features) & set(BLOCKED_FROM_FEATURES))
        for name in ("roc_auc", "weighted_f1", "weighted_precision", "weighted_recall",
                     "weighted_accuracy", "weighted_log_loss", "brier", "base_rate"):
            self.assertIn(name, record.metrics)
        self.assertTrue(0 <= record.metrics["roc_auc"] <= 1)
        self.assertTrue(0 <= record.metrics["base_rate"] <= 1)
        self.assertEqual(sum(record.confusion.values()), record.n_test)
        self.assertGreater(record.n_train, 0)
        self.assertEqual(record.calibration_table.columns.tolist(),
                         ["Predicted bin midpoint", "Observed Priority share (%)"])
        self.assertGreaterEqual(len(record.fold_metrics_table), len(CANDIDATE_NAMES))

    def test_prediction_falls_back_to_reference_values(self):
        record = train_final_model(synthetic_survey_frame())
        partial = {"hh_size": 6, "setting": "Rural", "province": "Kigali",
                   "sex": "Female", "head_sex": "Male"}
        probability = predict_priority(record, partial)
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)

    def test_documented_feature_lists(self):
        self.assertIn("hh_size", NUMERIC_FEATURES)
        self.assertIn("province", CATEGORICAL_FEATURES)


class ModelingPageArtifactTests(unittest.TestCase):
    """Helpers behind the dedicated Predictive insights page."""

    @classmethod
    def setUpClass(cls):
        frame = synthetic_survey_frame()
        cls.frame = frame
        cls.record = train_final_model(frame)
        cls.table = holdout_artifacts(frame, cls.record)

    def test_holdout_artifacts_matches_record_and_is_scored(self):
        expected_columns = {"paid", "proba", "hh_wt", "province", "setting", "sex"}
        self.assertEqual(set(self.table.columns), expected_columns)
        self.assertEqual(len(self.table), self.record.n_test)
        self.assertTrue(((self.table["proba"] >= 0) & (self.table["proba"] <= 1)).all())
        self.assertTrue(set(self.table["paid"].unique()).issubset({0, 1}))
        self.assertTrue((self.table["hh_wt"] > 0).all())

    def test_threshold_metrics_shape_and_monotone_recall(self):
        thresholds = threshold_metrics(self.table)
        self.assertEqual(len(thresholds), 5)
        self.assertEqual(thresholds.iloc[0, 0], "0.3")
        recalls = thresholds["Weighted recall"].tolist()
        self.assertEqual(recalls, sorted(recalls, reverse=True))
        for column in ("Weighted precision", "Weighted recall", "Weighted F1"):
            self.assertTrue(((thresholds[column] >= 0) & (thresholds[column] <= 1)).all())

    def test_pr_curve_recall_is_monotone_in_threshold(self):
        curve = pr_curve(self.table)
        self.assertEqual(len(curve), 19)
        self.assertTrue(curve["threshold"].is_monotonic_increasing)
        self.assertTrue(curve["recall"].is_monotonic_decreasing)

    def test_subgroup_performance_structure(self):
        report = subgroup_performance(self.table, "province")
        self.assertEqual(report.columns.tolist(),
                         ["province", "Records", "Base rate", "ROC-AUC", "Weighted F1",
                          "Weighted recall", "Low evidence"])
        self.assertEqual(int(report["Records"].sum()), self.record.n_test)
        self.assertTrue(set(report["ROC-AUC"]).issubset({"n/a"} |
                         {f"{v:.3f}" for v in np.linspace(0, 1, 1001)}))
        # A tiny min_n flags every cell; a generous one flags none.
        flagged_all = subgroup_performance(self.table, "province", min_n=10_000)
        self.assertTrue((flagged_all["Low evidence"] == "yes").all())
        none_flagged = subgroup_performance(self.table, "province", min_n=1)
        self.assertTrue((none_flagged["Low evidence"].eq("")).all())
        # Consistency rule: flagged exactly when records < the evidence bar.
        self.assertTrue(
            (report["Low evidence"].eq("yes")).eq(report["Records"].lt(150)).all()
        )

class RealSourceModelingTests(unittest.TestCase):
    """Integration test on the supplied Stata source (permitted analytic use)."""

    @classmethod
    def setUpClass(cls):
        cls.frame = enrich_analysis_data(load_analysis_data("data/dataset.dta"))

    def test_real_data_end_to_end_beats_random(self):
        record = train_final_model(self.frame)
        self.assertIsInstance(record, ModelRecord)
        # Against a majority/coin baseline, a usable model must clearly exceed chance.
        self.assertGreater(record.metrics["roc_auc"], 0.6)
        self.assertLess(record.metrics["brier"], 0.4)
        self.assertGreater(record.n_test, 100)
        self.assertTrue(set(record.features).isdisjoint(set(BLOCKED_FROM_FEATURES)))

    def test_group_integrity_on_holdout(self):
        record = train_final_model(self.frame)
        # The slice holds one record per household key: groups equal rows exactly.
        self.assertEqual(record.households_train, record.n_train)
        self.assertEqual(record.households_test, record.n_test)


if __name__ == "__main__":
    unittest.main()
