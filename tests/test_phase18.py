from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.analytics.phase14 import calculate_verified_indicator, save_calculation_result
from insightrwanda.analytics.release import build_phase18_status, save_workflow_audit
from insightrwanda.data.errors import IndicatorBlockedError
from insightrwanda.data.registry import load_dataset_registry
from insightrwanda.analytics.catalogue import load_indicator_catalogue
from insightrwanda.data.evidence import load_evidence_register
from insightrwanda.data.source_verification import load_source_verification_matrix

from tests.test_phase14 import eligible_fixture


ROOT = Path(__file__).resolve().parents[1]


def live_inputs() -> tuple[dict, dict, dict, dict]:
    registry = load_dataset_registry(ROOT / "data/metadata/dataset_registry.json")
    catalogue = load_indicator_catalogue(ROOT / "data/metadata/indicator_catalogue.json")
    evidence = load_evidence_register(
        ROOT / "data/metadata/evidence_register.json",
        dataset_ids=registry.keys(),
        indicator_ids=catalogue.keys(),
    )
    sources = load_source_verification_matrix(
        ROOT / "data/metadata/source_verification.json",
        dataset_ids=registry.keys(),
        project_root=ROOT,
    )
    inventory = json.loads((ROOT / "artifacts/source_inventory.json").read_text(encoding="utf-8"))
    return registry, catalogue, evidence, sources | {"__inventory__": inventory}


def live_audit(**overrides: object) -> dict:
    registry, catalogue, evidence, source_bundle = live_inputs()
    inventory = source_bundle.pop("__inventory__")
    return build_phase18_status(
        ROOT,
        registry,
        catalogue,
        evidence,
        source_bundle,
        inventory=inventory,
        geographic_resources=[],
        **overrides,
    )


def authorized_result_fixture() -> tuple[Path, dict, dict, dict, dict]:
    root = Path(tempfile.mkdtemp())
    registry, catalogue, sources = eligible_fixture(root)
    dataset = registry["synthetic-authorized"]
    # This is a schema-only test fixture. The marker is removed so this test
    # can exercise the authorized aggregate contract separately from the
    # explicit synthetic-result rejection test below.
    dataset["is_synthetic"] = False
    definition = catalogue["FI-ACCESS-001"]
    definition.update(
        {
            "description": "Approved test definition for a documented access measure.",
            "unit": "percentage",
            "source_dataset_candidates": ["synthetic-authorized"],
        }
    )
    frame = pd.DataFrame({"access": [1, 0, 1], "weight": [1.0, 2.0, 2.0]})
    result = calculate_verified_indicator(
        project_root=root,
        definition=definition,
        dataset=dataset,
        source_verification=sources,
        input_data=frame,
        numerator=pd.Series([True, False, True], dtype="boolean"),
        denominator=pd.Series([True, True, True], dtype="boolean"),
        weights=frame["weight"],
    )
    inventory = {"files": [{"relative_path": "data/mine/fixture.csv"}]}
    return root, registry, catalogue, sources | {"__inventory__": inventory}, result


class Phase18WorkflowTests(unittest.TestCase):
    def test_live_workflow_is_blocked_with_stable_deduplicated_ids(self):
        audit = live_audit()
        self.assertEqual(audit["status"], "blocked")
        self.assertFalse(audit["analytical_eligibility"])
        self.assertFalse(audit["publication_eligibility"])
        self.assertEqual(len(audit["blocker_ids"]), len(set(audit["blocker_ids"])))
        self.assertIn("dataset_authorization", audit["blocker_ids"])
        self.assertIn("verified_variable_mappings", audit["blocker_ids"])
        stages = {stage["stage_id"]: stage for stage in audit["stages"]}
        self.assertEqual(stages["geographic_resource_verification"]["status"], "not_applicable")
        self.assertEqual(stages["readiness_consistency"]["status"], "pass")

    def test_unregistered_dataset_cannot_enter_workflow(self):
        audit = live_audit(dataset_id="not-registered")
        self.assertIn("dataset_registered", audit["blocker_ids"])
        self.assertEqual(audit["stages"][0]["status"], "blocked")
        self.assertFalse(audit["release_eligible"])

    def test_unverified_definition_mapping_quality_and_methodology_block_transitions(self):
        audit = live_audit()
        stages = {stage["stage_id"]: stage for stage in audit["stages"]}
        self.assertEqual(stages["definition_mapping_methodology"]["status"], "blocked")
        self.assertIn("verified_variable_mappings", stages["definition_mapping_methodology"]["blocker_ids"])
        self.assertEqual(stages["quality_and_survey_validation"]["status"], "blocked")
        self.assertIn("data_quality_acceptance", stages["quality_and_survey_validation"]["blocker_ids"])

    def test_geography_is_required_only_when_requested(self):
        ordinary = live_audit()
        requested = live_audit(geographic_requested=True)
        ordinary_stage = next(item for item in ordinary["stages"] if item["stage_id"] == "geographic_resource_verification")
        requested_stage = next(item for item in requested["stages"] if item["stage_id"] == "geographic_resource_verification")
        self.assertEqual(ordinary_stage["status"], "not_applicable")
        self.assertEqual(requested_stage["status"], "blocked")
        self.assertIn("geographic_resource_verified", requested_stage["blocker_ids"])

    def test_valid_analytical_result_can_remain_publication_ineligible(self):
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
        finally:
            # The fixture directory is temporary and intentionally isolated
            # from the production data and artifact directories.
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        stages = {stage["stage_id"]: stage for stage in audit["stages"]}
        self.assertEqual(stages["analytical_execution"]["status"], "pass")
        self.assertEqual(stages["result_lineage_and_integrity"]["status"], "pass")
        self.assertIn("publication_eligibility", stages["disclosure_and_publication"]["blocker_ids"])
        self.assertFalse(audit["release_eligible"])

    def test_synthetic_result_cannot_become_real_release_output(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        result["data_classification"] = "synthetic_test_data"
        inventory = source_bundle.pop("__inventory__")
        try:
            audit = build_phase18_status(
                root, registry, catalogue, {"items": []}, source_bundle,
                inventory=inventory, geographic_resources=[], dataset_id="synthetic-authorized", result=result,
            )
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        lineage = next(item for item in audit["stages"] if item["stage_id"] == "result_lineage_and_integrity")
        self.assertIn("synthetic_result_not_for_real_research", lineage["blocker_ids"])
        self.assertFalse(audit["release_eligible"])

    def test_missing_and_contradictory_lineage_is_rejected(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        result["provenance"] = dict(result["provenance"], dataset_id="different-dataset", dataset_release="different-release")
        inventory = source_bundle.pop("__inventory__")
        try:
            audit = build_phase18_status(
                root, registry, catalogue, {"items": []}, source_bundle,
                inventory=inventory, geographic_resources=[], dataset_id="synthetic-authorized", result=result,
            )
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        lineage = next(item for item in audit["stages"] if item["stage_id"] == "result_lineage_and_integrity")
        self.assertIn("provenance_dataset_contradiction", lineage["blocker_ids"])
        self.assertIn("provenance_release_contradiction", lineage["blocker_ids"])

    def test_failed_result_integrity_and_quality_checks_block(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        result["quality_validation"] = {"status": "fail"}
        result["validation"] = {"input_validation": {"status": "fail"}, "result_integrity": {"status": "fail"}}
        result["readiness"] = {"analysis_eligible": False, "publication_eligible": False}
        inventory = source_bundle.pop("__inventory__")
        try:
            audit = build_phase18_status(
                root, registry, catalogue, {"items": []}, source_bundle,
                inventory=inventory, geographic_resources=[], dataset_id="synthetic-authorized", result=result,
            )
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        stages = {stage["stage_id"]: stage for stage in audit["stages"]}
        self.assertIn("result_integrity", stages["result_lineage_and_integrity"]["blocker_ids"])
        self.assertIn("quality_validation", stages["statistical_validation"]["blocker_ids"])
        self.assertIn("calculation_validation", stages["statistical_validation"]["blocker_ids"])

    def test_disclosure_failure_blocks_publication(self):
        root, registry, catalogue, source_bundle, result = authorized_result_fixture()
        result["readiness"] = dict(result["readiness"], publication_eligible=True)
        result["publication_status"] = "approved"
        result["disclosure_status"] = "not_reviewed"
        inventory = source_bundle.pop("__inventory__")
        try:
            audit = build_phase18_status(
                root, registry, catalogue, {"items": []}, source_bundle,
                inventory=inventory, geographic_resources=[], dataset_id="synthetic-authorized", result=result,
            )
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        publication = next(item for item in audit["stages"] if item["stage_id"] == "disclosure_and_publication")
        self.assertIn("disclosure_status", publication["blocker_ids"])

    def test_geographic_result_without_verified_resource_cannot_present(self):
        blocked_geo = {
            "status": "validated",
            "analysis_eligible": True,
            "join_validation": {"status": "validated"},
            "area_validation": {"status": "pass"},
        }
        audit = live_audit(geographic_requested=True, geographic_result=blocked_geo)
        geographic = next(item for item in audit["stages"] if item["stage_id"] == "geographic_resource_verification")
        self.assertEqual(geographic["status"], "blocked")
        self.assertIn("geographic_resource_verified", geographic["blocker_ids"])

    def test_central_readiness_cannot_be_bypassed_by_supplied_result(self):
        supplied = {
            "status": "calculated",
            "calculation_status": "calculated",
            "readiness": {"analysis_eligible": True},
            "dataset_id": "finscope_2024_rwanda_csv",
            "dataset_release": "release-looking",
            "indicator_id": "FI-ACCESS-001",
            "definition_version": "definition-looking",
        }
        audit = live_audit(result=supplied)
        execution = next(item for item in audit["stages"] if item["stage_id"] == "analytical_execution")
        self.assertEqual(execution["status"], "blocked")
        self.assertIn("central_analytical_eligibility", execution["blocker_ids"])

    def test_blocked_workflow_and_audit_do_not_create_successful_result_artifacts(self):
        audit = live_audit()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit_path = save_workflow_audit(audit, project_root=root)
            self.assertTrue(audit_path.exists())
            self.assertFalse((root / "artifacts" / "phase14_result.json").exists())
            self.assertFalse((root / "artifacts" / "phase16_geographic_result.json").exists())
            with self.assertRaises(IndicatorBlockedError):
                save_calculation_result(audit, project_root=root)
            saved = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["data_classification"], "metadata_only")
            self.assertFalse(saved["raw_records_included"])

    def test_saved_audit_rejects_raw_or_non_audit_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(IndicatorBlockedError):
                save_workflow_audit({"status": "blocked", "records": []}, project_root=directory)
            with self.assertRaises(IndicatorBlockedError):
                save_workflow_audit({"audit_type": "end_to_end_workflow_readiness", "data_classification": "synthetic_test_data", "raw_records_included": False}, project_root=directory)


if __name__ == "__main__":
    unittest.main()
