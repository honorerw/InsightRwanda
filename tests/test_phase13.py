from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.catalogue import load_indicator_catalogue
from insightrwanda.analytics.phase13 import build_phase13_status
from insightrwanda.analytics.readiness import evaluate_indicator_readiness
from insightrwanda.data.documentation import prepare_local_document_record
from insightrwanda.data.errors import DataLoaderError, DataPathError
from insightrwanda.data.evidence import load_evidence_register, summarize_evidence
from insightrwanda.data.registry import load_dataset_registry
from insightrwanda.data.research_readiness import build_research_readiness_report
from insightrwanda.data.source_verification import (
    load_source_verification_matrix,
    summarize_access_checklist,
    validate_source_verification_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase13AccessAndDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_dataset_registry(ROOT / "data/metadata/dataset_registry.json")
        self.catalogue = load_indicator_catalogue(ROOT / "data/metadata/indicator_catalogue.json")
        self.sources = load_source_verification_matrix(
            ROOT / "data/metadata/source_verification.json", dataset_ids=self.registry.keys()
        )
        self.evidence = load_evidence_register(
            ROOT / "data/metadata/evidence_register.json",
            dataset_ids=self.registry.keys(), indicator_ids=self.catalogue.keys(),
        )

    def test_public_catalogue_reference_does_not_grant_microdata_authorization(self):
        fs = next(s for s in self.sources["sources"] if s["source_id"] == "SOURCE-FINSCOPE-2024")
        catalog = next(r for r in fs["source_references"] if r["source_type"] == "catalogue")
        self.assertEqual(catalog["status"], "verified")
        self.assertEqual(catalog["release_identifier"], "RWA-NISR-FINSCOPE-2024-v01")
        self.assertEqual(fs["source_reference_status"], "provided_unverified")
        self.assertEqual(fs["access_authorization_status"], "missing")
        self.assertEqual(self.registry["finscope_2024_rwanda_csv"]["authorization_status"], "unverified")

    def test_public_document_listing_does_not_mark_questionnaire_or_codebook_reviewed(self):
        fs = next(s for s in self.sources["sources"] if s["source_id"] == "SOURCE-FINSCOPE-2024")
        self.assertEqual(fs["documentation_review_status"], "missing")
        self.assertEqual(fs["documentation_records"], [])
        self.assertEqual(next(i for i in self.evidence["items"] if i["evidence_id"] == "EVID-DATASET-FINSCOPE-CODEBOOK")["status"], "missing")

    def test_exact_release_document_review_rejects_a_different_release(self):
        source = {
            "source_id": "SOURCE-SYNTHETIC", "dataset_id": "dataset", "candidate_dataset_name": None,
            "source_title": "Synthetic", "source_organization": "Synthetic", "source_references": [],
            "verification_status": "missing", "unresolved_questions": [], "next_actions": [],
            "manual_verification_required": True, "release_version": "release-A",
            "documentation_records": [{
                "document_id": "DOC-1", "document_type": "codebook", "path": "data/docs/codebook.pdf",
                "release_identifier": "release-B", "status": "verified", "exact_release_status": "verified",
                "review_status": "verified", "sha256": "a" * 64, "reviewer": "reviewer", "review_date": "2026-01-01",
            }],
        }
        with self.assertRaises(DataLoaderError):
            validate_source_verification_matrix({"sources": [source]}, dataset_ids={"dataset"})

    def test_access_checklist_counts_follow_underlying_evidence_status(self):
        before = summarize_access_checklist(self.sources["sources"], self.evidence["items"])
        self.assertEqual(before["total"], 13)
        self.assertEqual(before["verified"], 0)
        changed = [dict(item) for item in self.evidence["items"]]
        target = next(item for item in changed if item["evidence_id"] == "EVID-DATASET-FINSCOPE-CODEBOOK")
        target["status"] = "verified"
        after = summarize_access_checklist(self.sources["sources"], changed)
        self.assertEqual(after["verified"], 1)
        self.assertNotEqual(before["status_counts"], after["status_counts"])
        self.assertEqual(summarize_evidence(changed)["verified"], summarize_evidence(self.evidence["items"])["verified"] + 1)

    def test_generated_readiness_counts_and_checklist_follow_evidence_records(self):
        inventory = json.loads((ROOT / "artifacts/source_inventory.json").read_text(encoding="utf-8"))
        before = build_research_readiness_report(
            ROOT, inventory=inventory, registry=self.registry, catalogue=self.catalogue,
            evidence=self.evidence, source_verification=self.sources,
        )
        changed_items = [dict(item) for item in self.evidence["items"]]
        next(item for item in changed_items if item["evidence_id"] == "EVID-DATASET-FINSCOPE-CODEBOOK")["status"] = "verified"
        changed_evidence = {**self.evidence, "items": changed_items}
        after = build_research_readiness_report(
            ROOT, inventory=inventory, registry=self.registry, catalogue=self.catalogue,
            evidence=changed_evidence, source_verification=self.sources,
        )
        self.assertEqual(after["evidence"]["summary"]["verified"], before["evidence"]["summary"]["verified"] + 1)
        self.assertEqual(after["source_verification"]["access_checklist"]["verified"], before["source_verification"]["access_checklist"]["verified"] + 1)

    def test_dashboard_indicator_eligibility_matches_phase13_gate_result(self):
        phase13 = build_phase13_status(ROOT, self.registry, self.catalogue, self.evidence, self.sources)
        from insightrwanda.ui.metadata import load_dashboard_metadata
        dashboard = load_dashboard_metadata(ROOT)
        row = next(item for item in dashboard.research_readiness["indicators"] if item["indicator_id"] == "FI-ACCESS-001")
        self.assertEqual(row["analytical_eligibility"], phase13["analysis_eligible"])
        self.assertEqual(row["publication_eligibility"], phase13["publication_eligible"])

    def test_missing_mapping_or_weight_keeps_candidate_ineligible(self):
        report = build_phase13_status(ROOT, self.registry, self.catalogue, self.evidence, self.sources)
        self.assertFalse(report["analysis_eligible"])
        self.assertFalse(report["publication_eligible"])
        self.assertIsNone(report["result"])
        self.assertFalse(report["indicator_calculated"])
        readiness = report["readiness"]
        self.assertIn("verified_variable_mappings", readiness["blocked_checks"])
        self.assertIn("survey_weight_and_design", readiness["blocked_checks"])

    def test_missing_local_source_file_is_a_central_readiness_blocker(self):
        report = build_phase13_status(ROOT, self.registry, self.catalogue, self.evidence, self.sources)
        self.assertFalse(self.registry["finscope_2024_rwanda_csv"].get("is_synthetic", False))
        self.assertIn("source_file_availability", report["readiness"]["blocked_checks"])
        self.assertFalse(report["analysis_eligible"])

    def test_verified_definition_field_without_exact_reviewed_document_stays_blocked(self):
        definition = dict(self.catalogue["FI-ACCESS-001"])
        definition["definition_review"] = {
            "target_release_identifier": "release-A",
            "fields": [{
                "field_id": "purpose", "status": "verified", "release_identifier": "release-A",
                "value": "verified-looking text", "evidence_reference": "data/docs/not-reviewed.pdf#p1",
                "reviewer": "reviewer", "review_date": "2026-01-01",
            }],
        }
        source = {"dataset_id": "finscope_2024_rwanda_csv", "release_version": "release-A", "documentation_records": []}
        result = evaluate_indicator_readiness(definition, self.registry["finscope_2024_rwanda_csv"], source_verification=source)
        self.assertIn("definition_review", result.blocked_checks)

    def test_synthetic_registry_flag_alone_does_not_bypass_real_source_gates(self):
        dataset = {
            "dataset_id": "real-dataset", "is_synthetic": True,
            "authorization_status": "synthetic_test", "analytical_eligibility": True,
        }
        result = evaluate_indicator_readiness({}, dataset)
        self.assertIn("dataset_authorization", result.blocked_checks)

    def test_mapping_requires_reviewed_exact_release_codebook_document(self):
        definition = {
            "indicator_id": "FI-TEST", "status": "proposed_pending_review",
            "required_variables": ["candidate_var"],
            "mapping_records": [{
                "source_dataset_id": "finscope_2024_rwanda_csv", "source_variable": "candidate_var",
                "variable_meaning": "candidate meaning", "codebook_reference": "data/docs/codebook.pdf#p1",
                "eligible_population": "candidate population", "denominator_definition": "candidate denominator",
                "missing_value_treatment": "candidate missing rules", "response_coding": {"1": "yes"},
                "status": "verified", "evidence_reference": "data/docs/codebook.pdf#p1",
            }],
        }
        source = {
            "dataset_id": "finscope_2024_rwanda_csv", "release_version": "release-A",
            "documentation_records": [],
        }
        result = evaluate_indicator_readiness(
            definition, self.registry["finscope_2024_rwanda_csv"], source_verification=source,
            require_mapping_evidence=True,
        )
        self.assertIn("mapping_evidence", result.blocked_checks)

    def test_wrong_release_definition_review_blocks_even_otherwise_ready_metadata(self):
        definition = dict(self.catalogue["FI-ACCESS-001"])
        definition["status"] = "derived_from_verified_variables"
        definition["definition_approval_status"] = "approved"
        definition["methodology_approval_status"] = "approved"
        definition["definition_review"] = {
            "target_release_identifier": "release-A",
            "fields": [{"field_id": "purpose", "status": "verified", "release_identifier": "release-B"}],
        }
        result = evaluate_indicator_readiness(definition, self.registry["finscope_2024_rwanda_csv"])
        self.assertIn("definition_review", result.blocked_checks)

    def test_local_document_registration_is_safe_and_starts_unverified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = root / "data" / "docs" / "questionnaire.pdf"
            document.parent.mkdir(parents=True)
            document.write_bytes(b"synthetic document fixture")
            record = prepare_local_document_record(
                root, "data/docs/questionnaire.pdf", document_id="DOC-SYNTHETIC",
                document_type="questionnaire", release_identifier="release-test",
            )
        self.assertEqual(record["status"], "provided_unverified")
        self.assertEqual(record["review_status"], "missing")
        self.assertEqual(record["exact_release_status"], "missing")
        self.assertEqual(len(record["sha256"]), 64)

    def test_local_document_registration_rejects_paths_outside_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "secret.pdf"
            outside.write_bytes(b"fixture")
            with self.assertRaises(DataPathError):
                prepare_local_document_record(
                    root, outside, document_id="DOC-OUT", document_type="codebook", release_identifier="release-test"
                )

    def test_registered_document_symlink_cannot_escape_data_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_docs = root / "data" / "docs"
            data_docs.mkdir(parents=True)
            outside = root / "outside.pdf"
            outside.write_bytes(b"synthetic fixture")
            (data_docs / "linked.pdf").symlink_to(outside)
            source = {
                "source_id": "SOURCE-SYNTHETIC", "dataset_id": "dataset", "candidate_dataset_name": None,
                "source_title": "Synthetic", "source_organization": "Synthetic", "source_references": [],
                "verification_status": "missing", "unresolved_questions": [], "next_actions": [],
                "manual_verification_required": True, "release_version": "release-A",
                "documentation_records": [{
                    "document_id": "DOC-1", "document_type": "codebook", "path": "data/docs/linked.pdf",
                    "release_identifier": "release-A", "status": "provided_unverified",
                    "exact_release_status": "missing", "review_status": "missing",
                }],
            }
            with self.assertRaises(DataLoaderError):
                validate_source_verification_matrix({"sources": [source]}, dataset_ids={"dataset"}, project_root=root)


if __name__ == "__main__":
    unittest.main()
