from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.readiness import evaluate_indicator_readiness
from insightrwanda.data.errors import DataPathError, DataLoaderError
from insightrwanda.data.registry import get_dataset, load_dataset_registry, registry_summary, resolve_dataset_path
from insightrwanda.ui.metadata import DashboardMetadata, catalogue_readiness_summary


def _definition(**overrides):
    definition = {
        "indicator_id": "SYNTHETIC-READY-001",
        "status": "derived_from_verified_variables",
        "evidence_status": "verified_codebook_mapping",
        "required_variables": ["respondent_status", "survey_weight"],
        "definition_approval_status": "approved",
        "methodology_approval_status": "approved",
        "value_semantics_verified": True,
        "survey_weight_requirements": "required",
        "publication_status": "not_eligible",
    }
    definition.update(overrides)
    return definition


def _authorized_dataset(**overrides):
    dataset = {
        "dataset_id": "synthetic",
        "authorization_status": "authorized_for_analysis",
        "analytical_eligibility": True,
        "eligible_for_publication": False,
        "codebook_status": "verified",
        "survey_weight_status": "verified",
        "survey_design_status": "verified",
        "survey_weight_variable": "survey_weight",
    }
    dataset.update(overrides)
    return dataset


class Phase6RegistryTests(unittest.TestCase):
    def test_registry_defaults_are_conservative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(
                json.dumps({"datasets": [{"dataset_id": "one", "display_name": "One", "source_path": "mine/one.csv", "file_format": "csv"}]}),
                encoding="utf-8",
            )
            registry = load_dataset_registry(path)

        record = registry["one"]
        self.assertEqual(record["authorization_status"], "unverified")
        self.assertFalse(record["analytical_eligibility"])
        self.assertFalse(record["eligible_for_publication"])

    def test_selection_requires_an_explicit_dataset_id(self) -> None:
        registry = {"one": {"dataset_id": "one"}}
        self.assertIsNone(get_dataset(registry, None))
        self.assertIsNone(get_dataset(registry, ""))
        self.assertEqual(get_dataset(registry, "one")["dataset_id"], "one")

    def test_registry_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(
                json.dumps({"datasets": [{"dataset_id": "bad", "display_name": "Bad", "source_path": "../secret.csv", "file_format": "csv"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(DataPathError):
                load_dataset_registry(path)

    def test_registered_absolute_path_is_rejected(self) -> None:
        with self.assertRaises(DataPathError):
            resolve_dataset_path({"source_path": "/tmp/outside.csv"}, project_root=Path("."))

    def test_malformed_registry_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text("not json", encoding="utf-8")
            with self.assertRaises(DataLoaderError):
                load_dataset_registry(path)

    def test_registry_summary_contains_no_paths(self) -> None:
        summary = registry_summary({"one": {"authorization_status": "unverified", "eligible_for_publication": False, "analytical_eligibility": False, "codebook_status": "missing"}})
        self.assertNotIn("source_path", json.dumps(summary))


class Phase6ReadinessTests(unittest.TestCase):
    def test_unverified_dataset_is_blocked(self) -> None:
        result = evaluate_indicator_readiness(_definition(), {"authorization_status": "unverified"}, available_columns={"respondent_status", "survey_weight"})
        self.assertFalse(result.analysis_eligible)
        self.assertIn("dataset_authorization", result.blocked_checks)

    def test_missing_mapping_and_codebook_are_blocked(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(required_variables=[], evidence_status="no_verified_codebook_mapping"),
            _authorized_dataset(),
            available_columns=set(),
        )
        self.assertFalse(result.analysis_eligible)
        self.assertIn("verified_variable_mappings", result.blocked_checks)
        self.assertIn("approved_definition_and_methodology", result.passed_checks)

    def test_missing_codebook_blocks_a_definition_with_a_mapping(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(), _authorized_dataset(codebook_status="missing_or_unverified"), available_columns={"respondent_status", "survey_weight"}
        )
        self.assertIn("verified_variable_mappings", result.blocked_checks)

    def test_missing_required_columns_are_named(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(), _authorized_dataset(), available_columns={"respondent_status"}
        )
        self.assertTrue(any("survey_weight" in message for message in result.messages))

    def test_survey_design_and_weight_requirements_are_enforced(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(), _authorized_dataset(survey_weight_status="unverified"), available_columns={"respondent_status", "survey_weight"}
        )
        self.assertIn("survey_weight_and_design", result.blocked_checks)

    def test_geographic_comparisons_require_validated_geography(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(), _authorized_dataset(), available_columns={"respondent_status", "survey_weight"}, requested_geography=True
        )
        self.assertIn("validated_geography", result.blocked_checks)

    def test_publication_permission_is_separate_from_analysis(self) -> None:
        result = evaluate_indicator_readiness(
            _definition(), _authorized_dataset(), available_columns={"respondent_status", "survey_weight"}, publication_requested=True
        )
        self.assertTrue(result.analysis_eligible)
        self.assertFalse(result.publication_eligible)
        self.assertFalse(result.eligible_for_requested_purpose)

    def test_readiness_is_deterministic_and_does_not_create_an_estimate(self) -> None:
        definition = _definition()
        dataset = _authorized_dataset()
        first = evaluate_indicator_readiness(definition, dataset, available_columns={"respondent_status", "survey_weight"}).as_dict()
        second = evaluate_indicator_readiness(definition, dataset, available_columns={"respondent_status", "survey_weight"}).as_dict()
        self.assertEqual(first, second)
        self.assertNotIn("estimate", first)

    def test_dashboard_readiness_summary_reports_blocked_state(self) -> None:
        metadata = DashboardMetadata(
            catalogue={"SYNTHETIC-READY-001": _definition()},
            catalogue_error=None,
            inventory=None,
            inventory_error=None,
            registry={"synthetic": _authorized_dataset()},
            registry_error=None,
        )
        summary = catalogue_readiness_summary(metadata, dataset_id="synthetic")
        self.assertEqual(summary["analysis_eligible_count"], 0)
        self.assertEqual(summary["blocked_count"], 1)
        self.assertEqual(summary["publication_eligible_count"], 0)


if __name__ == "__main__":
    unittest.main()
