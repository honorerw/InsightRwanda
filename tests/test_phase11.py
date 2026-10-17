from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.mappings import mapping_readiness, summarize_mapping_records, validate_mapping_records
from insightrwanda.data.errors import DataLoaderError, IndicatorDefinitionError
from insightrwanda.data.source_verification import (
    build_researcher_action_plan,
    load_source_verification_matrix,
    SOURCE_STATUS_FIELDS,
    summarize_source_verification,
    validate_source_verification_matrix,
)
from insightrwanda.ui.metadata import load_dashboard_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(**overrides):
    source = {
        "source_id": "SOURCE-SYNTHETIC-001",
        "dataset_id": "dataset",
        "candidate_dataset_name": None,
        "source_title": "Synthetic source",
        "source_organization": "Synthetic organization",
        "source_references": [
            {
                "label": "Synthetic landing page",
                "url": "https://example.org/source",
                "supports": "Source identity only.",
                "status": "provided_unverified",
            }
        ],
        "verification_status": "provided_unverified",
        "unresolved_questions": ["Permission?"],
        "next_actions": ["Obtain permission."],
        "manual_verification_required": True,
    }
    source.update(overrides)
    return source


def _mapping(**overrides):
    record = {
        "source_dataset_id": "dataset",
        "source_variable": "answer",
        "variable_meaning": "Documented answer meaning.",
        "codebook_reference": "codebook.pdf#answer",
        "eligible_population": "Documented eligible respondents.",
        "denominator_definition": "Eligible respondents with valid answer.",
        "missing_value_treatment": "Exclude documented missing codes.",
        "response_coding": {"1": "Yes", "0": "No"},
        "status": "provided_unverified",
        "evidence_reference": "codebook.pdf#answer",
    }
    record.update(overrides)
    return record


class Phase11SourceVerificationTests(unittest.TestCase):
    def test_project_source_matrix_records_public_references_without_granting_access(self) -> None:
        metadata = load_dashboard_metadata(PROJECT_ROOT)
        matrix = metadata.source_verification

        self.assertIsNone(metadata.source_verification_error)
        summary = summarize_source_verification(matrix["sources"])
        self.assertEqual(summary["source_count"], 5)
        self.assertEqual(summary["provided_unverified"], 2)
        self.assertEqual(summary["missing"], 3)
        self.assertEqual(summary["manual_verification_count"], 5)
        self.assertTrue(all(dataset["authorization_status"] == "unverified" for dataset in metadata.registry.values()))

    def test_unknown_dataset_and_invalid_reference_are_rejected(self) -> None:
        with self.assertRaises(DataLoaderError):
            validate_source_verification_matrix({"sources": [_source(dataset_id="unknown")]}, dataset_ids={"dataset"})
        with self.assertRaises(DataLoaderError):
            validate_source_verification_matrix({"sources": [_source(source_references=[{"label": "bad", "url": "not-a-url", "supports": "x", "status": "provided_unverified"}])]}, dataset_ids={"dataset"})

    def test_missing_source_matrix_file_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(DataLoaderError):
                load_source_verification_matrix(Path(temporary) / "missing.json")

    def test_source_records_keep_verification_dimensions_separate(self) -> None:
        metadata = load_dashboard_metadata(PROJECT_ROOT)
        records = metadata.source_verification["sources"]

        self.assertTrue(all(set(SOURCE_STATUS_FIELDS).issubset(record) for record in records))
        self.assertTrue(all(record["analysis_approval_status"] != "verified" for record in records))
        self.assertTrue(all(record["publication_approval_status"] != "verified" for record in records))
        self.assertEqual(
            metadata.research_readiness["source_verification"]["summary"]["blocking_dimension_count"],
            35,
        )

    def test_source_approval_order_is_enforced(self) -> None:
        with self.assertRaises(DataLoaderError):
            validate_source_verification_matrix(
                {"sources": [_source(analysis_approval_status="verified")]},
                dataset_ids={"dataset"},
            )


class Phase11MappingTests(unittest.TestCase):
    def test_mapping_requires_codebook_backed_fields_and_known_dataset(self) -> None:
        records = validate_mapping_records([_mapping()], indicator_id="SYNTHETIC-001", dataset_ids={"dataset"})
        self.assertEqual(records[0]["source_variable"], "answer")
        with self.assertRaises(IndicatorDefinitionError):
            validate_mapping_records([_mapping(codebook_reference="")], indicator_id="SYNTHETIC-001", dataset_ids={"dataset"})
        with self.assertRaises(IndicatorDefinitionError):
            validate_mapping_records([_mapping(source_dataset_id="unknown")], indicator_id="SYNTHETIC-001", dataset_ids={"dataset"})

    def test_unverified_mapping_and_incompatible_schema_remain_blocked(self) -> None:
        records = validate_mapping_records([_mapping()], indicator_id="SYNTHETIC-001", dataset_ids={"dataset"})
        result = mapping_readiness(records, required_variables=["answer"], dataset_id="dataset", available_columns={"other"})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["verified_variable_count"], 0)
        self.assertTrue(any("not independently verified" in item for item in result["blockers"]))

    def test_verified_mapping_still_requires_schema_presence(self) -> None:
        records = validate_mapping_records([_mapping(status="verified")], indicator_id="SYNTHETIC-001", dataset_ids={"dataset"})
        missing = mapping_readiness(records, required_variables=["answer"], dataset_id="dataset", available_columns={"other"})
        present = mapping_readiness(records, required_variables=["answer"], dataset_id="dataset", available_columns={"answer"})

        self.assertEqual(missing["status"], "blocked")
        self.assertEqual(present["status"], "verified")

    def test_mapping_readiness_rejects_incomplete_verified_records(self) -> None:
        result = mapping_readiness(
            [{"source_dataset_id": "dataset", "source_variable": "answer", "status": "verified"}],
            required_variables=["answer"],
            dataset_id="dataset",
            available_columns={"answer"},
        )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("incomplete" in item for item in result["blockers"]))

    def test_mapping_summary_requires_required_variable_coverage(self) -> None:
        definition = {
            "indicator_id": "SYNTHETIC-001",
            "display_name": "Synthetic indicator",
            "required_variables": ["answer", "eligible"],
            "mapping_records": [_mapping(status="verified")],
        }
        summary = summarize_mapping_records({"SYNTHETIC-001": definition}, dataset_ids={"dataset"})

        self.assertEqual(summary["indicators_with_verified_mappings"], 0)
        self.assertIn("cover every required source variable", summary["rows"][0]["blockers"][0])

    def test_researcher_action_plan_keeps_manual_tasks_visible(self) -> None:
        plan = build_researcher_action_plan(
            [
                {
                    "evidence_id": "EVID-SYNTHETIC",
                    "category": "variable_mapping",
                    "status": "provided_unverified",
                    "related_indicator_id": "SYNTHETIC-001",
                    "description": "Mapping review",
                    "reason_for_blocking": "Meaning is not independently reviewed.",
                    "next_action": "Review codebook.",
                    "mandatory": True,
                }
            ],
            [_source()],
        )

        self.assertIn("variable_mapping_review", plan)
        self.assertIn("source_acquisition", plan)
        self.assertTrue(plan["variable_mapping_review"][0]["manual_verification_required"])


if __name__ == "__main__":
    unittest.main()
