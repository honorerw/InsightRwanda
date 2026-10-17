from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.analytics.authorized import (
    calculate_authorized_proportion,
    load_authorized_dataset,
    prepare_publication_aggregate,
)
from insightrwanda.analytics.geography import join_approved_geographic_aggregate


def _definition(**overrides):
    definition = {
        "indicator_id": "SYNTHETIC-PHASE9-001",
        "display_name": "Synthetic approved proportion",
        "status": "derived_from_verified_variables",
        "evidence_status": "verified_codebook_mapping",
        "required_variables": ["answer", "eligible", "weight"],
        "verified_variable_mappings": [
            {
                "source_variable": "answer",
                "status": "verified",
                "evidence_reference": "synthetic-codebook.pdf#answer",
                "response_coding": {"true": "approved response"},
            },
            {
                "source_variable": "eligible",
                "status": "verified",
                "evidence_reference": "synthetic-codebook.pdf#eligible",
                "response_coding": {"true": "eligible population"},
            },
            {
                "source_variable": "weight",
                "status": "verified",
                "evidence_reference": "synthetic-survey-design.pdf#weight",
                "response_coding": "positive survey weight",
            },
        ],
        "definition_approval_status": "approved",
        "methodology_approval_status": "approved",
        "value_semantics_verified": True,
        "numerator_definition": "Verified answer is true.",
        "denominator_definition": "Verified eligible population with non-missing answer.",
        "missing_value_treatment": "Exclude missing answer and invalid weight values.",
        "calculation_method": "weighted_proportion",
        "survey_weight_requirements": "required",
        "publication_status": "not_eligible",
    }
    definition.update(overrides)
    return definition


def _dataset(**overrides):
    dataset = {
        "dataset_id": "synthetic-phase9",
        "display_name": "Synthetic Phase 9 source",
        "source_path": "mine/synthetic.csv",
        "file_format": "csv",
        "is_synthetic": True,
        "authorization_status": "synthetic_test",
        "analytical_eligibility": True,
        "provenance_status": "verified",
        "documentation_status": "verified",
        "license_status": "verified",
        "codebook_status": "verified",
        "data_quality_status": "approved",
        "survey_weight_status": "verified",
        "survey_design_status": "verified",
        "survey_weight_variable": "weight",
        "eligible_for_publication": False,
        "dataset_version": "synthetic-v1",
    }
    dataset.update(overrides)
    return dataset


def _write_source(root: Path, text: str = "answer,eligible,weight\nTrue,True,1\nFalse,True,3\nTrue,False,1\n,True,1\n") -> None:
    source = root / "data" / "mine" / "synthetic.csv"
    source.parent.mkdir(parents=True)
    source.write_text(text, encoding="utf-8")


class Phase9LoadingTests(unittest.TestCase):
    def test_unverified_dataset_is_blocked_before_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            result = load_authorized_dataset(
                _definition(),
                _dataset(authorization_status="unverified", is_synthetic=False, analytical_eligibility=False),
                project_root=root,
            )

        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.frame)
        self.assertFalse(result.readiness.analysis_eligible)

    def test_explicit_eligible_synthetic_source_loads_without_serializing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            result = load_authorized_dataset(_definition(), _dataset(), project_root=root, allow_synthetic_test_data=True)

        self.assertEqual(result.status, "loaded")
        self.assertEqual(set(result.columns), {"answer", "eligible", "weight"})
        self.assertNotIn("True", json.dumps(result.as_dict()))

    def test_schema_mismatch_blocks_after_safe_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root, "answer,eligible\nTrue,True\n")
            result = load_authorized_dataset(_definition(), _dataset(), project_root=root, allow_synthetic_test_data=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("weight", " ".join(result.readiness.messages))
        self.assertIsNone(result.frame)

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            result = load_authorized_dataset(
                _definition(), _dataset(source_path="../outside.csv"), project_root=root
            )

        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.frame)
        self.assertIn("source_file_availability", result.readiness.blocked_checks)

    def test_mapping_evidence_is_required_even_with_similar_variable_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            definition = _definition(verified_variable_mappings=[])
            result = load_authorized_dataset(definition, _dataset(), project_root=root, allow_synthetic_test_data=True)

        self.assertEqual(result.status, "blocked")
        self.assertIn("mapping_evidence", result.readiness.blocked_checks)

    def test_missing_quality_evidence_blocks_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            result = load_authorized_dataset(
                _definition(), _dataset(data_quality_status="unverified"), project_root=root
            )

        self.assertEqual(result.status, "blocked")
        self.assertIn("data_quality_acceptance", result.readiness.blocked_checks)


class Phase9CalculationTests(unittest.TestCase):
    def test_approved_weighted_calculation_uses_explicit_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            definition = _definition()
            dataset = _dataset()
            loaded = load_authorized_dataset(definition, dataset, project_root=root, allow_synthetic_test_data=True)
            frame = loaded.frame
            result = calculate_authorized_proportion(
                loaded,
                definition,
                dataset,
                frame["answer"].astype("boolean"),
                frame["eligible"].astype("boolean"),
                weights=frame["weight"],
            )

        self.assertEqual(result["calculation_status"], "calculated")
        self.assertAlmostEqual(result["estimate"], 0.25)
        self.assertEqual(result["weighted_denominator"], 4.0)
        self.assertEqual(result["dataset_id"], "synthetic-phase9")
        self.assertNotIn("True", json.dumps(result))

    def test_invalid_weights_are_reported_without_unweighted_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_source(root)
            definition = _definition()
            dataset = _dataset()
            loaded = load_authorized_dataset(definition, dataset, project_root=root, allow_synthetic_test_data=True)
            frame = loaded.frame
            result = calculate_authorized_proportion(
                loaded,
                definition,
                dataset,
                frame["answer"].astype("boolean"),
                frame["eligible"].astype("boolean"),
                weights=pd.Series([1.0, -1.0, float("inf"), 0.0], index=frame.index),
            )

        self.assertTrue(result["weighted"])
        self.assertNotEqual(result["calculation_status"], "calculated_unweighted")
        self.assertEqual(result["weight_diagnostics"]["negative_count"], 1)

    def test_publication_requires_permission_and_disclosure_review(self) -> None:
        calculation = {
            "calculation_status": "calculated",
            "publication_eligible": False,
            "denominator_count": 10,
            "indicator_id": "SYNTHETIC-PHASE9-001",
        }
        result = prepare_publication_aggregate(
            calculation,
            disclosure_review_status="pending",
            minimum_cell_count=5,
        )

        self.assertEqual(result["publication_status"], "blocked")
        self.assertFalse(result["publication_eligible"])
        self.assertNotIn("estimate", result)


class Phase9GeographyTests(unittest.TestCase):
    def test_missing_crosswalk_blocks_geographic_join(self) -> None:
        result = join_approved_geographic_aggregate(
            pd.DataFrame({"district_id": [1], "estimate": [0.5]}),
            pd.DataFrame({"district_id": [1]}),
            dataset={"geography_status": "verified", "geographic_crosswalk_status": "missing"},
            aggregate_key="district_id",
            boundary_key="district_id",
            geographic_level="district",
            calculation_metadata={
                "calculation_status": "calculated",
                "validation_status": "validated",
                "publication_eligible": False,
            },
        )

        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.joined)

    def test_valid_documented_identifier_join_is_internal_only(self) -> None:
        result = join_approved_geographic_aggregate(
            pd.DataFrame({"district_id": pd.Series([1, 2], dtype="int64"), "estimate": [0.5, 0.3]}),
            pd.DataFrame({"district_id": pd.Series([1, 2], dtype="int64"), "geometry": ["a", "b"]}),
            dataset={
                "geography_status": "verified",
                "geographic_crosswalk_status": "verified",
                "geographic_level": "district",
                "geographic_join_method": "documented_identifier",
            },
            aggregate_key="district_id",
            boundary_key="district_id",
            geographic_level="district",
            calculation_metadata={
                "calculation_status": "calculated",
                "validation_status": "validated",
                "publication_eligible": False,
            },
        )

        self.assertEqual(result.status, "validated")
        self.assertNotIn("estimate", json.dumps(result.as_dict()))

    def test_unmatched_geography_blocks_join(self) -> None:
        result = join_approved_geographic_aggregate(
            pd.DataFrame({"district_id": pd.Series([1], dtype="int64"), "estimate": [0.5]}),
            pd.DataFrame({"district_id": pd.Series([2], dtype="int64")}),
            dataset={
                "geography_status": "verified",
                "geographic_crosswalk_status": "verified",
                "geographic_level": "district",
                "geographic_join_method": "documented_identifier",
            },
            aggregate_key="district_id",
            boundary_key="district_id",
            geographic_level="district",
            calculation_metadata={
                "calculation_status": "calculated",
                "validation_status": "validated",
                "publication_eligible": False,
            },
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.unmatched_aggregate_count, 1)


if __name__ == "__main__":
    unittest.main()
