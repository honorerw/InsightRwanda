"""Tests for research.joint — pooled cross-source analysis.

Synthetic frames use keys prefixed "F-" so fixture rows are never mistaken for
NISR records. One integration test runs the audit and pooled estimates on the
two supplied files.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.data_pipeline import enrich_analysis_data, load_analysis_data
from research.joint import (
    COMBINED_COLUMNS,
    FEATURES,
    MEASURES,
    SOURCE_LABELS,
    TARGET_COMPONENTS,
    JointFrameError,
    build_combined_dataset,
    build_joint_frame,
    comparison_note,
    evaluate_transport,
    linkage_audit,
    pooled_estimates,
    wave_note,
    weighted_correlation,
    weighted_cross_tab,
    weighted_rate,
)
from research.spss_pipeline import enrich_spss_analysis_data, load_spss_analysis_data

SPSS_PATH = "data/Rwanda FinScope 2020_Final Data.sav"
MASTER_PATH = "data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta"


def synthetic_source(n: int, prefix: str, seed: int, offset: float = 0.0) -> pd.DataFrame:
    """A labelled synthetic frame with a learnable, non-leaking signal."""

    rng = np.random.default_rng(seed)
    latent = rng.normal(size=n) + offset
    logistic = 1 / (1 + np.exp(-latent))
    income_pressure = (rng.random(n) < 1 - logistic * 0.6).astype(float)
    internet = (rng.random(n) < logistic * 0.8).astype(float)
    emergency = (rng.random(n) < logistic * 0.5).astype(float)
    mobile = (rng.random(n) < logistic).astype(float)
    bank = (rng.random(n) < logistic * 0.9).astype(float)
    active = np.maximum(mobile, bank)
    return pd.DataFrame({
        "key": [f"{prefix}{i:05d}" for i in range(n)],
        "hh_wt": rng.integers(1, 50, n).astype(float),
        "hh_size": rng.integers(1, 10, n),
        "b1": rng.integers(16, 90, n),
        "b2": rng.choice([1, 2], n),
        "province": rng.choice(["Kigali", "South", "West", "North", "East"], n),
        "district": rng.choice(["Gasabo", "Huye", "Musanze", "Rusizi"], n),
        "setting": rng.choice(["Urban", "Rural"], n),
        "sex": rng.choice(["Male", "Female"], n),
        "active_access": active,
        "mobile_money": mobile,
        "bank_use": bank,
        "sacco_use": (rng.random(n) < 0.3).astype(float),
        "emergency_fund": emergency,
        "internet_access": internet,
        "income_pressure": income_pressure,
    })


def synthetic_pair(n_master: int = 400, n_spss: int = 300) -> tuple[pd.DataFrame, pd.DataFrame]:
    return synthetic_source(n_master, "F-M-", 11), synthetic_source(n_spss, "F-S-", 12, offset=.3)


class LinkageAuditTests(unittest.TestCase):
    def test_disjoint_keys_are_reported_as_unlinkable(self):
        master, spss = synthetic_pair()
        audit = linkage_audit(master, spss)
        self.assertEqual(audit.shared_keys, 0)
        self.assertFalse(audit.linkable)
        self.assertEqual(audit.master_rows, 400)
        self.assertEqual(audit.spss_rows, 300)
        self.assertIn("No shared record key", audit.verdict)

    def test_shared_key_is_reported_as_linkable(self):
        master, spss = synthetic_pair()
        spss.loc[0, "key"] = master.loc[0, "key"]
        audit = linkage_audit(master, spss)
        self.assertEqual(audit.shared_keys, 1)
        self.assertTrue(audit.linkable)

    def test_missing_key_column_raises(self):
        master, spss = synthetic_pair()
        with self.assertRaises(JointFrameError):
            linkage_audit(master.drop(columns=["key"]), spss)

    def test_composite_agreement_is_between_zero_and_one(self):
        master, spss = synthetic_pair()
        audit = linkage_audit(master, spss)
        self.assertGreater(audit.composite_pairs, 0)
        self.assertGreaterEqual(audit.composite_agreement_share, 0.0)
        self.assertLessEqual(audit.composite_agreement_share, 1.0)


class JointFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master, cls.spss = synthetic_pair()
        cls.joint = build_joint_frame(cls.master, cls.spss)

    def test_rows_stack_without_a_join(self):
        self.assertEqual(len(self.joint), len(self.master) + len(self.spss))
        self.assertEqual(self.joint["source"].value_counts().to_dict(), {"master": 400, "spss": 300})

    def test_weight_share_sums_to_one_per_source(self):
        shares = self.joint.groupby("source")["weight_share"].sum()
        for source in ("master", "spss"):
            self.assertAlmostEqual(float(shares[source]), 1.0, places=9)

    def test_wave_year_dates_both_documented_waves(self):
        years = self.joint.groupby("source")["wave_year"].unique()
        self.assertEqual(int(years["spss"][0]), 2020)
        self.assertEqual(int(years["master"][0]), 2024)

    def test_age_band_covers_every_row(self):
        self.assertTrue(self.joint["age_band"].isin(
            ["16-24", "25-34", "35-44", "45-54", "55-64", "65+", "Unknown"]).all())

    def test_missing_columns_raise_instead_of_silently_joining(self):
        with self.assertRaises(JointFrameError):
            build_joint_frame(self.master.drop(columns=["income_pressure"]), self.spss)

    def test_documented_year_override_replaces_undocumented_wave(self):
        joint = build_joint_frame(self.master, self.spss, wave_years={"master": 2020})
        self.assertEqual(int(joint.loc[joint["source"].eq("master"), "wave_year"].iloc[0]), 2020)


class CombinedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master, cls.spss = synthetic_pair()
        cls.dataset = build_combined_dataset(cls.master, cls.spss)

    def test_one_stacked_dataset_with_the_documented_columns(self):
        self.assertEqual(len(self.dataset), len(self.master) + len(self.spss))
        self.assertEqual(list(self.dataset.columns), list(COMBINED_COLUMNS))
        self.assertEqual(self.dataset["source"].value_counts().to_dict(), {"master": 400, "spss": 300})

    def test_original_keys_are_replaced_by_unique_record_ids(self):
        self.assertNotIn("key", self.dataset.columns)
        self.assertTrue(self.dataset["record_id"].is_unique)
        self.assertTrue(self.dataset["record_id"].str.fullmatch(r"[0-9a-f]{16}").all())

    def test_build_is_deterministic(self):
        again = build_combined_dataset(self.master, self.spss)
        self.assertTrue(self.dataset.equals(again))

    def test_duplicate_keys_still_get_distinct_ids(self):
        master = pd.concat([self.master, self.master.iloc[[0]]], ignore_index=True)
        dataset = build_combined_dataset(master, self.spss)
        self.assertTrue(dataset["record_id"].is_unique)

    def test_measures_and_weights_survive_the_export(self):
        self.assertAlmostEqual(
            weighted_rate(self.dataset, "mobile_money"),
            weighted_rate(build_joint_frame(self.master, self.spss), "mobile_money"),
        )
        shares = self.dataset.groupby("source")["weight_share"].sum()
        self.assertAlmostEqual(float(shares["master"]), 1.0, places=9)
        self.assertAlmostEqual(float(shares["spss"]), 1.0, places=9)


class RelationshipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master, cls.spss = synthetic_pair()
        cls.joint = build_joint_frame(cls.master, cls.spss)

    def test_weighted_rate_ignores_missing_and_invalid_weights(self):
        frame = pd.DataFrame({
            "m": [1.0, 0.0, np.nan, 1.0],
            "weight": [1.0, 1.0, 1.0, 0.0],
        })
        self.assertAlmostEqual(weighted_rate(frame, "m"), 0.5)

    def test_correlation_matrix_is_square_symmetric_with_unit_diagonal(self):
        matrix = weighted_correlation(self.joint)
        self.assertEqual(matrix.shape, (len(MEASURES), len(MEASURES)))
        self.assertTrue(np.allclose(np.diag(matrix), 1.0))
        self.assertTrue(np.allclose(matrix.to_numpy(), matrix.to_numpy().T, equal_nan=True))
        values = matrix.to_numpy()
        off_diagonal = values[~np.eye(len(MEASURES), dtype=bool)]
        self.assertTrue(np.all((off_diagonal >= -1.0001) & (off_diagonal <= 1.0001)))

    def test_cross_tab_rows_are_percentages(self):
        table = weighted_cross_tab(self.joint, "age_band", "mobile_money")
        self.assertFalse(table.empty)
        self.assertTrue(np.allclose(table.sum(axis=1), 100.0, atol=0.2))

    def test_pooled_estimate_gives_each_source_equal_weight(self):
        master = pd.DataFrame({
            **{c: [1, 1] for c in ("key",)},
            "hh_wt": [1.0, 1.0], "hh_size": [3, 3], "b1": [30, 40], "b2": [1, 2],
            "province": ["Kigali", "Kigali"], "district": ["Gasabo", "Gasabo"],
            "setting": ["Urban", "Urban"], "sex": ["Male", "Female"],
            **{m: [0.0, 0.0] for m in MEASURES},
        })
        spss = master.copy()
        spss["key"] = ["F-S-1", "F-S-2"]
        spss["hh_wt"] = [100.0, 100.0]
        for m in MEASURES:
            spss[m] = [1.0, 1.0]
        table = pooled_estimates(build_joint_frame(master, spss))
        row = table.loc[table["Measure"].eq(MEASURES["active_access"])].iloc[0]
        self.assertAlmostEqual(float(row["Pooled (equal source weight)"]), 0.5)
        self.assertAlmostEqual(float(row["Gap (pp)"]), 100.0)


class TransportModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master, cls.spss = synthetic_pair(n_master=600, n_spss=450)
        cls.joint = build_joint_frame(cls.master, cls.spss)

    def test_feature_set_never_contains_a_target_component(self):
        for target, components in TARGET_COMPONENTS.items():
            self.assertTrue(set(FEATURES).isdisjoint(components), target)

    def test_transport_table_has_all_scenarios(self):
        table = evaluate_transport(self.joint, "mobile_money", n_splits=3)
        self.assertEqual(len(table), 6)
        for column in ("Train on", "Test on", "Test records", "Observed positive share",
                       "Mean predicted", "ROC-AUC", "Brier", "Base-rate Brier"):
            self.assertIn(column, table.columns)
        self.assertTrue(table["ROC-AUC"].between(0, 1).all())
        self.assertTrue(table["Brier"].dropna().between(0, 1).all())
        self.assertTrue(table["Base-rate Brier"].between(0, 1).all())
        # Six scenarios: two within-source CVs, two external tests, two pooled tests.
        self.assertEqual(int(table["Test records"].sum()), len(self.joint) * 3)

    def test_unknown_target_raises(self):
        with self.assertRaises(KeyError):
            evaluate_transport(self.joint, "not_a_target")


class RealSourceJointTests(unittest.TestCase):
    """Integration test on the two supplied files (permitted analytic use)."""

    @classmethod
    def setUpClass(cls):
        cls.master = enrich_analysis_data(load_analysis_data(MASTER_PATH))
        cls.spss = enrich_spss_analysis_data(load_spss_analysis_data(SPSS_PATH))
        cls.joint = build_joint_frame(cls.master, cls.spss)

    def test_supplied_files_have_no_shared_record_key(self):
        audit = linkage_audit(self.master, self.spss)
        self.assertEqual(audit.shared_keys, 0)
        self.assertEqual(audit.master_unique_keys, 13994)
        self.assertEqual(audit.spss_unique_keys, 12480)
        self.assertIn("No shared record key", audit.verdict)

    def test_joint_frame_covers_both_sources(self):
        self.assertEqual(len(self.joint), 26474)
        self.assertEqual(set(self.joint["source"].unique()), {"master", "spss"})

    def test_pooled_estimates_are_plausible_and_stable(self):
        table = pooled_estimates(self.joint)
        self.assertEqual(len(table), len(MEASURES))
        for column in (SOURCE_LABELS["master"], SOURCE_LABELS["spss"], "Pooled (equal source weight)"):
            self.assertTrue(table[column].between(0, 1).all())
        indexed = table.set_index("Measure")
        pooled = indexed["Pooled (equal source weight)"]
        low = indexed[[SOURCE_LABELS["master"], SOURCE_LABELS["spss"]]].min(axis=1)
        high = indexed[[SOURCE_LABELS["master"], SOURCE_LABELS["spss"]]].max(axis=1)
        # Equal-source pooling must sit between the two source estimates.
        self.assertTrue(((pooled >= low - 1e-9) & (pooled <= high + 1e-9)).all())

    def test_combined_dataset_materializes_all_records(self):
        dataset = build_combined_dataset(self.master, self.spss)
        self.assertEqual(len(dataset), 26474)
        self.assertTrue(dataset["record_id"].is_unique)
        self.assertNotIn("key", dataset.columns)
        self.assertEqual(dataset["source"].value_counts().to_dict(), {"master": 13994, "spss": 12480})

    def test_wave_note_states_both_documented_waves(self):
        note = wave_note()
        self.assertIn("FinScope 2024", note)
        self.assertIn("FinScope 2020", note)
        self.assertIn("source-definition", comparison_note())


if __name__ == "__main__":
    unittest.main()
