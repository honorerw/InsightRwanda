from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from insightrwanda.analytics.local_material import (
    FORMAL_PROVIDER_COLUMNS,
    _weighted_summary,
    load_supplied_financial_inclusion,
    supplied_material_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


class LocalMaterialTests(unittest.TestCase):
    def test_weighted_summary_uses_only_positive_weights_and_qf4_yes(self):
        frame = pd.DataFrame(
            {
                "pop_wt": [2.0, 3.0, 0.0, -1.0, None],
                **{column: ["No", "Yes", "Yes", "Yes", "Yes"] for column in FORMAL_PROVIDER_COLUMNS},
            }
        )
        result = _weighted_summary(frame)
        self.assertEqual(result["respondents"], 5)
        self.assertEqual(result["weight_valid_respondents"], 2)
        self.assertEqual(result["weighted_denominator"], 5.0)
        self.assertEqual(result["weighted_numerator"], 3.0)
        self.assertEqual(result["share_percent"], 60.0)

    def test_project_uses_only_the_supplied_stata_dataset_and_questionnaire(self):
        result = load_supplied_financial_inclusion(str(ROOT))
        self.assertEqual(result.status, "exploratory")
        self.assertEqual(result.authorization_status, "authorized_for_analysis")
        self.assertEqual(result.source_path, "data/mine/dataset.dta")
        self.assertEqual(
            result.questionnaire_path,
            "data/mine/FinScope/2024/FinScope_2024_Consumer_Questionnaire.pdf",
        )
        self.assertEqual(result.rows, 13994)
        self.assertGreater(result.national["share_percent"], 0)
        self.assertLess(result.national["share_percent"], 100)
        serialized = result.as_dict()
        # Variable identifiers may appear inside documented measure
        # definitions, but respondent-level answers or raw source rows
        # must never appear in the aggregate serialization.
        self.assertNotIn("'Yes'", str(serialized))
        self.assertNotIn("'No'", str(serialized))
        measures = serialized["measures"]
        self.assertEqual(len(measures), 14)
        for measure in measures.values():
            share = measure["national"]["share_percent"]
            self.assertIsNotNone(share)
            self.assertGreater(share, 0)
            self.assertLess(share, 100)
            self.assertIn("b2", measure["groups"])
        self.assertNotIn("key", str(serialized))

    def test_measure_specs_cover_documented_variables_and_well_defined_columns(self):
        import json

        from insightrwanda.analytics.local_material import (
            ACCOUNT_PROVIDER_COLUMNS,
            MEASURE_SPECS,
        )

        codebook = json.loads((ROOT / "data/metadata/finscope_codebook.json").read_text())
        documented = {entry["variable"] for entry in codebook["variables"]}
        for spec in MEASURE_SPECS:
            self.assertTrue(spec["columns"], spec["measure_id"])
            self.assertTrue(all(column in documented for column in spec["columns"]))
        self.assertEqual(
            tuple(ACCOUNT_PROVIDER_COLUMNS[:9]),
            tuple(ACCOUNT_PROVIDER_COLUMNS)[:9],
        )

    def test_f5_module_tracks_official_report_and_qf_diverges(self):
        result = load_supplied_financial_inclusion(str(ROOT))
        measures = result.measures or {}

        # The F5 mobile-money module in the supplied release tracks the
        # official FinScope 2024 report values (registered wallet 77%,
        # own-or-ever-used 86%): the local F5 shares stay within ~11 points.
        registered_current = measures["mobile_money_registered_current"]["national"]["share_percent"]
        ever_or_current = measures["mobile_money_ever_use"]["national"]["share_percent"]
        self.assertBetween(registered_current, 60.0, 72.0)
        self.assertBetween(ever_or_current, 70.0, 82.0)

        # The QF battery in the same release disagrees sharply with the F
        # module (about 35.5% ever use vs 76.3% in F5), which documents the
        # known QF/F internal inconsistency of the supplied extract.
        qf_ever = measures["mobile_money_ever"]["national"]["share_percent"]
        self.assertLess(qf_ever, 45.0)

        # The QF1 exclusion battery cannot reproduce the official 4%
        # exclusion headline.
        self.assertBetween(
            measures["any_provider_ever"]["national"]["share_percent"],
            70.0,
            85.0,
        )

    def assertBetween(self, value, low, high):  # noqa: N802
        self.assertGreaterEqual(value, low)
        self.assertLessEqual(value, high)

    def test_synthetic_skip_pattern_denominator_and_grouping(self):
        from insightrwanda.analytics.local_material import (
            _group_summaries,
            _weighted_summary,
        )

        frame = pd.DataFrame(
            {
                "pop_wt": [1.0, 2.0, 3.0, 4.0, 5.0],
                "qf3_05": ["Yes", None, "No", "Yes", None],
                "b2": ["Male", "Female", "Male", "Female", "Male"],
            }
        )
        # Skip-pattern blanks are non-affirmative but all positive weights
        # count toward the population denominator (16+ adults).
        summary = _weighted_summary(frame, ("qf3_05",))
        self.assertEqual(summary["weighted_denominator"], 15.0)
        self.assertEqual(summary["weighted_numerator"], 5.0)  # (1.0 + 4.0)
        self.assertAlmostEqual(summary["share_percent"], 100 * 5.0 / 15.0)

        rows = _group_summaries(frame, "b2", ("qf3_05",))
        by_group = {row["group"]: row for row in rows}
        self.assertEqual(by_group["Male"]["weighted_numerator"], 1.0)
        self.assertEqual(by_group["Female"]["weighted_numerator"], 4.0)
        self.assertEqual(by_group["Male"]["weighted_denominator"], 9.0)
        self.assertEqual(by_group["Female"]["weighted_denominator"], 6.0)

    def test_all_supplied_material_is_inventoried_by_type(self):
        inventory = supplied_material_inventory(str(ROOT))
        self.assertEqual(inventory["status"], "available")
        self.assertGreater(inventory["file_count"], 0)
        self.assertGreater(inventory["categories"]["tabular"], 0)
        self.assertGreater(inventory["categories"]["documentation"], 0)
        self.assertGreater(inventory["categories"]["media"], 0)


if __name__ == "__main__":
    unittest.main()
