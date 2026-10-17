from __future__ import annotations

import copy
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from insightrwanda.analytics.reproducibility import (
    MANIFEST_SCHEMA_VERSION,
    ReproducibilityError,
    append_audit_event,
    build_audit_event,
    build_phase20_status,
    build_reproducibility_manifest,
    canonical_json,
    compare_reproduced_results,
    detect_reproducibility_changes,
    save_audit_events,
    validate_manifest,
)

from tests.test_phase18 import authorized_result_fixture


def manifest_fixture() -> tuple[Path, dict, dict, dict]:
    root, registry, catalogue, sources, result = authorized_result_fixture()
    result["result_id"] = "result-phase20-test-1"
    definition = catalogue["FI-ACCESS-001"]
    manifest = build_reproducibility_manifest(
        result,
        manifest_id="manifest-phase20-test-1",
        mapping_version="mapping-fi-access-test-v1",
        calculation_specification_id="fi-access-calculation-test-1",
        validation_references={
            "input_validation": "phase15-input-test-1",
            "result_integrity": "phase15-integrity-test-1",
        },
        analytical_eligibility_reference="phase14-decision-test-1",
        indicator_definition=definition,
        calculation_specification=definition["calculation_specification"],
        created_at_utc="2026-10-14T00:00:00+00:00",
        dependency_versions={"pandas": "synthetic-test-version"},
    )
    return root, result, manifest, definition


class Phase20ReproducibilityTests(unittest.TestCase):
    def test_canonical_serialization_is_stable(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
        self.assertEqual(canonical_json({"unicode": "é", "items": [True, None]}), canonical_json({"items": [True, None], "unicode": "é"}))

    def test_unsupported_types_and_nonfinite_numbers_are_rejected(self):
        with self.assertRaises(ReproducibilityError):
            canonical_json({"values": {1, 2}})
        with self.assertRaises(ReproducibilityError):
            canonical_json({"value": math.inf})

    def test_valid_manifest_is_structurally_and_integrity_valid(self):
        root, result, manifest, definition = manifest_fixture()
        try:
            report = validate_manifest(
                manifest,
                result=result,
                expected_lineage={
                    "dataset_id": result["dataset_id"],
                    "dataset_release": result["dataset_release"],
                    "indicator_id": definition["indicator_id"],
                    "definition_version": definition["definition_version"],
                },
                current_eligibility={"analysis_eligible": True, "publication_eligible": False},
            )
            self.assertEqual(report.status, "manifest_valid")
            self.assertTrue(report.manifest_valid)
            self.assertTrue(report.integrity_verified)
            self.assertTrue(report.lineage_traceable)
            self.assertEqual(report.reproduction_status, "not_run")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_or_unsupported_manifest_versions_fail(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            missing = dict(manifest)
            missing.pop("dataset_release")
            self.assertEqual(validate_manifest(missing, result=result).status, "invalid")
            unsupported = dict(manifest, manifest_schema_version="phase20-manifest-v999")
            self.assertEqual(validate_manifest(unsupported, result=result).status, "invalid")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_modified_result_content_is_detected(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            modified = copy.deepcopy(result)
            modified["estimate"] = float(modified["estimate"]) + 0.01
            report = validate_manifest(manifest, result=modified, current_eligibility={"analysis_eligible": True})
            self.assertIn("result_checksum_mismatch", report.blocker_ids)
            self.assertFalse(report.integrity_verified)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_reference_and_contradictory_lineage_are_rejected(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            no_release = dict(manifest, dataset_release=None)
            self.assertIn("manifest_schema", validate_manifest(no_release, result=result).blocker_ids)
            contradictory = dict(manifest, dataset_id="other-dataset")
            contradictory["manifest_checksum"] = __import__("insightrwanda.analytics.reproducibility", fromlist=["manifest_checksum"]).manifest_checksum(contradictory)
            report = validate_manifest(contradictory, result=result, expected_lineage={"dataset_id": result["dataset_id"]})
            self.assertIn("lineage_dataset_id_mismatch", report.blocker_ids)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_changed_method_indicator_and_geographic_versions_require_revalidation(self):
        root, _, manifest, _ = manifest_fixture()
        try:
            current = {
                "method_version": "insightrwanda-phase14-v2",
                "definition_version": "fi-access-test-v2",
                "geographic_boundary_release": "boundary-v2",
            }
            changed = detect_reproducibility_changes(manifest, current)
            self.assertEqual(changed["status"], "revalidation_required")
            self.assertIn("revalidation_method_version", changed["blocker_ids"])
            self.assertIn("revalidation_definition_version", changed["blocker_ids"])
            self.assertIn("revalidation_geographic_boundary_release", changed["blocker_ids"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_analytical_and_publication_eligibility_remain_separate(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            internal = validate_manifest(manifest, result=result, current_eligibility={"analysis_eligible": True, "publication_eligible": False})
            self.assertEqual(internal.status, "manifest_valid")
            public = validate_manifest(manifest, result=result, current_eligibility={"analysis_eligible": True, "publication_eligible": False}, publication_requested=True)
            self.assertIn("publication_eligibility", public.blocker_ids)
            self.assertFalse(public.publication_eligibility_verified)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_revoked_authorization_is_rechecked(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            report = validate_manifest(
                manifest,
                result=result,
                current_eligibility={"analysis_eligible": False, "authorization_valid": False, "authorization_status": "revoked"},
            )
            self.assertIn("authorization_revalidation_required", report.blocker_ids)
            self.assertIn("central_analytical_eligibility", report.blocker_ids)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_synthetic_results_are_software_tests_only(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            synthetic = copy.deepcopy(result)
            synthetic["data_classification"] = "synthetic_test_data"
            synthetic_manifest = build_reproducibility_manifest(
                synthetic,
                manifest_id="manifest-synthetic-test-1",
                mapping_version="mapping-fi-access-test-v1",
                calculation_specification_id="fi-access-calculation-test-1",
                validation_references=manifest["validation_references"],
                analytical_eligibility_reference="phase14-decision-test-1",
                indicator_definition={"indicator_id": synthetic["indicator_id"], "definition_version": synthetic["definition_version"]},
                calculation_specification={"version": manifest["calculation_specification_version"]},
                created_at_utc="2026-10-14T00:00:00+00:00",
            )
            report = validate_manifest(synthetic_manifest, result=synthetic, current_eligibility={"analysis_eligible": True})
            self.assertEqual(report.status, "software_test_only")
            self.assertIn("synthetic_result_not_for_real_research", report.blocker_ids)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_comparison_policy_handles_exact_tolerance_and_missing_inputs(self):
        root, result, manifest, _ = manifest_fixture()
        try:
            reproduced = copy.deepcopy(result)
            reproduced["estimate"] = float(reproduced["estimate"]) + 0.00001
            exact = compare_reproduced_results(result, reproduced)
            self.assertFalse(exact["equivalent"])
            tolerant = compare_reproduced_results(result, reproduced, numerical_tolerance=0.001)
            self.assertTrue(tolerant["equivalent"])
            self.assertEqual(tolerant["status"], "passed")
            verified_state = build_phase20_status(
                manifest=manifest,
                result=result,
                current_eligibility={"analysis_eligible": True},
                reproduction_comparison=tolerant,
            )
            self.assertEqual(verified_state["status"], "verified")
            self.assertEqual(verified_state["reproduction_status"], "verified")
            blocked = compare_reproduced_results(result, None)
            self.assertIn("reproduction_input_missing", blocked["blocker_ids"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_reproduction_is_blocked_without_authorized_inputs(self):
        root, _, manifest, _ = manifest_fixture()
        try:
            status = build_phase20_status(manifest=manifest, result=None, current_eligibility={"analysis_eligible": False})
            self.assertEqual(status["reproduction_status"], "blocked")
            self.assertIn("result_reference_missing", status["blocker_ids"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_audit_events_are_safe_and_deduplicated(self):
        event = build_audit_event("manifest_validation", "blocked", manifest_id="manifest-1", reason_codes=["manifest_schema"])
        duplicate = append_audit_event([event], event)
        self.assertEqual(len(duplicate), 1)
        self.assertNotIn("dummy-secret", json.dumps(event))
        with self.assertRaises(ReproducibilityError):
            build_audit_event("manifest_validation", "blocked", reason_codes=["dummy secret"])
        with self.assertRaises(ReproducibilityError):
            append_audit_event([], {"event_id": "bad", "records": [{"person": "Dummy Person"}]})
        with self.assertRaises(ReproducibilityError):
            append_audit_event([], dict(event, accidental_secret="dummy-secret"))

    def test_audit_records_cannot_grant_eligibility_and_can_be_saved_safely(self):
        root, _, _, _ = manifest_fixture()
        try:
            event = build_audit_event("eligibility_changed", "passed", manifest_id="manifest-1", reason_codes=[])
            path = save_audit_events([event], project_root=root)
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["audit_schema_version"], "phase20-audit-v1")
            status = build_phase20_status()
            self.assertFalse(status["analytical_eligibility_verified"])
            self.assertIn("reproducibility_manifest_missing", status["blocker_ids"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_repeated_evaluation_is_not_an_uncontrolled_duplicate(self):
        first = build_audit_event("reproducibility_evaluation", "blocked", reason_codes=["reproducibility_manifest_missing"])
        second = build_audit_event("reproducibility_evaluation", "blocked", reason_codes=["reproducibility_manifest_missing"])
        events = append_audit_event([], first)
        events = append_audit_event(events, second)
        self.assertEqual(len(events), 1)
        self.assertEqual(first["event_id"], second["event_id"])

    def test_live_phase20_state_is_blocked_and_metadata_only(self):
        status = build_phase20_status()
        self.assertEqual(status["status"], "not_configured")
        self.assertEqual(status["data_classification"], "metadata_only")
        self.assertFalse(status["raw_records_included"])
        self.assertFalse(status["analytical_eligibility_verified"])


if __name__ == "__main__":
    unittest.main()
