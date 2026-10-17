from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.phase14 import (
    load_saved_calculation_result,
    save_calculation_result,
)
from insightrwanda.analytics.geography import save_geographic_analysis_result
from insightrwanda.analytics.release import build_phase18_status, save_workflow_audit
from insightrwanda.analytics.validation import validate_result_integrity
from insightrwanda.data.errors import DataPathError, IndicatorBlockedError
from insightrwanda.data.paths import resolve_approved_data_path, resolve_derived_output_path

from tests.test_phase18 import authorized_result_fixture, live_audit


ROOT = Path(__file__).resolve().parents[1]


class Phase19SecurityIntegrityTests(unittest.TestCase):
    def test_missing_authorization_cannot_grant_analytical_eligibility(self):
        audit = live_audit()
        self.assertFalse(audit["analytical_eligibility"])
        self.assertIn("dataset_authorization", audit["blocker_ids"])

    def test_explicit_denial_is_not_overridden_by_a_report_summary(self):
        registry, catalogue, evidence, source_bundle = self._live_inputs()
        dataset = registry["finscope_2024_rwanda_csv"]
        denied = copy.deepcopy(dataset)
        denied["authorization_status"] = "denied"
        registry[denied["dataset_id"]] = denied
        # This summary is deliberately favorable and is not supplied to the
        # central evaluator as an authorization input.
        summary = {"analytical_eligibility": True, "publication_eligibility": True}
        self.assertTrue(summary["analytical_eligibility"])
        audit = build_phase18_status(
            ROOT,
            registry,
            catalogue,
            evidence,
            source_bundle,
            inventory=self._inventory(),
            geographic_resources=[],
        )
        self.assertFalse(audit["analytical_eligibility"])
        self.assertIn("dataset_authorization", audit["blocker_ids"])

    def test_malformed_status_fails_closed(self):
        registry, catalogue, evidence, source_bundle = self._live_inputs()
        registry["finscope_2024_rwanda_csv"]["authorization_status"] = "approved_without_review"
        audit = build_phase18_status(
            ROOT,
            registry,
            catalogue,
            evidence,
            source_bundle,
            inventory=self._inventory(),
            geographic_resources=[],
        )
        self.assertFalse(audit["analytical_eligibility"])
        self.assertIn("dataset_authorization", audit["blocker_ids"])

    def test_unregistered_dataset_and_traversal_are_rejected(self):
        audit = live_audit(dataset_id="not-registered")
        self.assertIn("dataset_registered", audit["blocker_ids"])
        with self.assertRaises(DataPathError):
            resolve_approved_data_path("data/../outside.csv", project_root=ROOT)
        with self.assertRaises(DataPathError):
            resolve_derived_output_path("artifacts/../data/source.csv", project_root=ROOT)

    def test_symlink_escape_is_rejected_when_supported(self):
        root = Path(tempfile.mkdtemp())
        outside = Path(tempfile.mkdtemp())
        try:
            (root / "data").mkdir()
            (outside / "secret.csv").write_text("dummy-secret", encoding="utf-8")
            link = root / "data" / "link.csv"
            try:
                os.symlink(outside / "secret.csv", link)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks are unavailable on this platform")
            with self.assertRaises(DataPathError):
                resolve_approved_data_path("data/link.csv", project_root=root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)

    def test_nested_raw_result_is_rejected_and_not_loaded(self):
        root, registry, catalogue, sources, result = authorized_result_fixture()
        try:
            result["validation"] = dict(result["validation"], diagnostic={"records": [{"secret": "dummy-secret"}]})
            integrity = validate_result_integrity(result)
            self.assertFalse(integrity.calculation_allowed)
            with self.assertRaises(IndicatorBlockedError):
                save_calculation_result(result, project_root=root)
            self.assertFalse((root / "artifacts" / "phase14_result.json").exists())

            clean_root, _, _, _, clean_result = authorized_result_fixture()
            try:
                save_calculation_result(clean_result, project_root=clean_root)
                result_path = clean_root / "artifacts" / "phase14_result.json"
                document = json.loads(result_path.read_text(encoding="utf-8"))
                document["validation"]["diagnostic"] = {"rows": [{"secret": "dummy-secret"}]}
                result_path.write_text(json.dumps(document), encoding="utf-8")
                self.assertIsNone(load_saved_calculation_result(clean_root))
            finally:
                shutil.rmtree(clean_root, ignore_errors=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_invalid_lineage_and_synthetic_results_cannot_be_released(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        inventory = source_bundle.pop("__inventory__")
        try:
            result["data_classification"] = "synthetic_test_data"
            result["provenance"] = dict(result["provenance"], dataset_id="wrong")
            audit = build_phase18_status(
                root,
                registry,
                catalogue,
                {"items": []},
                source_bundle,
                inventory=inventory,
                geographic_resources=[],
                dataset_id="synthetic-authorized",
                result=result,
            )
            lineage = next(item for item in audit["stages"] if item["stage_id"] == "result_lineage_and_integrity")
            self.assertIn("provenance_dataset_contradiction", lineage["blocker_ids"])
            self.assertIn("synthetic_result_not_for_real_research", lineage["blocker_ids"])
            self.assertFalse(audit["release_eligible"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_analytical_result_does_not_authorize_publication(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        inventory = source_bundle.pop("__inventory__")
        try:
            audit = build_phase18_status(
                root,
                registry,
                catalogue,
                {"items": []},
                source_bundle,
                inventory=inventory,
                geographic_resources=[],
                dataset_id="synthetic-authorized",
                result=result,
                intended_use="public_display",
            )
            self.assertTrue(next(item for item in audit["stages"] if item["stage_id"] == "analytical_execution")["status"] == "pass")
            publication = next(item for item in audit["stages"] if item["stage_id"] == "disclosure_and_publication")
            self.assertEqual(publication["status"], "blocked")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_geographic_writer_rejects_nested_payloads(self):
        root = Path(tempfile.mkdtemp())
        try:
            result = {
                "status": "validated",
                "analysis_eligible": True,
                "join_validation": {"status": "validated", "diagnostics": {"rows": [{"secret": "dummy"}]}},
                "area_validation": {"status": "pass"},
            }
            with self.assertRaises(IndicatorBlockedError):
                save_geographic_analysis_result(result, project_root=root)
            self.assertFalse((root / "artifacts" / "phase16_geographic_result.json").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_direct_writers_enforce_gates_and_preserve_existing_artifact(self):
        root = Path(tempfile.mkdtemp())
        try:
            audit_path = root / "artifacts" / "phase18_status.json"
            audit_path.parent.mkdir(parents=True)
            original = "existing-safe-artifact\n"
            audit_path.write_text(original, encoding="utf-8")
            with self.assertRaises(IndicatorBlockedError):
                save_workflow_audit({"audit_type": "end_to_end_workflow_readiness", "status": "ready", "release_eligible": True, "blocker_ids": ["x", "x"], "stages": []}, project_root=root)
            self.assertEqual(audit_path.read_text(encoding="utf-8"), original)

            blocked = live_audit()
            saved = save_workflow_audit(blocked, project_root=root)
            self.assertTrue(saved.exists())
            persisted = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(persisted["data_classification"], "metadata_only")
            self.assertFalse(persisted["release_eligible"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_geographic_requirement_is_scoped_and_publication_remains_separate(self):
        ordinary = live_audit(geographic_requested=False)
        geographic = live_audit(geographic_requested=True)
        ordinary_stage = next(item for item in ordinary["stages"] if item["stage_id"] == "geographic_resource_verification")
        geographic_stage = next(item for item in geographic["stages"] if item["stage_id"] == "geographic_resource_verification")
        self.assertEqual(ordinary_stage["status"], "not_applicable")
        self.assertEqual(geographic_stage["status"], "blocked")
        self.assertFalse(ordinary["publication_eligibility"])

    def test_sensitive_dummy_values_are_not_in_integrity_errors(self):
        dummy_secret = "dummy-secret-token-123"
        dummy_person = "Dummy Person 999"
        result = {"records": [{"name": dummy_person, "token": dummy_secret}]}
        report = validate_result_integrity(result).as_dict()
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(dummy_secret, rendered)
        self.assertNotIn(dummy_person, rendered)

    def test_rejected_output_path_does_not_modify_source_file(self):
        root = Path(tempfile.mkdtemp())
        try:
            source = root / "data" / "source.csv"
            source.parent.mkdir(parents=True)
            source.write_text("dummy-secret,1\n", encoding="utf-8")
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            with self.assertRaises(DataPathError):
                resolve_derived_output_path("data/source.csv", project_root=root)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_metadata_only_audit_is_valid_without_granting_research_eligibility(self):
        audit = live_audit()
        root = Path(tempfile.mkdtemp())
        try:
            path = save_workflow_audit(audit, project_root=root)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(stored["analytical_eligibility"])
            self.assertFalse(stored["release_eligible"])
            self.assertFalse(stored["raw_records_included"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _live_inputs():
        from tests.test_phase18 import live_inputs

        registry, catalogue, evidence, source_bundle = live_inputs()
        source_bundle.pop("__inventory__", None)
        return registry, catalogue, evidence, source_bundle

    @staticmethod
    def _inventory():
        return json.loads((ROOT / "artifacts/source_inventory.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
