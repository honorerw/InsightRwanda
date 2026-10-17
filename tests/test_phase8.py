from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from insightrwanda.data.inventory import build_inventory
from insightrwanda.data.research_readiness import (
    build_research_readiness_report,
    current_data_file_paths,
    verify_inventory_snapshot,
)


def _catalogue() -> dict[str, dict[str, object]]:
    return {
        "SYNTHETIC-001": {
            "indicator_id": "SYNTHETIC-001",
            "display_name": "Synthetic candidate",
            "status": "proposed_pending_review",
            "evidence_status": "no_verified_codebook_mapping",
            "required_variables": [],
            "review_blockers": ["authoritative codebook mapping"],
        }
    }


def _registry() -> dict[str, dict[str, object]]:
    return {
        "synthetic": {
            "dataset_id": "synthetic",
            "display_name": "Synthetic source",
            "source_path": "mine/synthetic.csv",
            "file_format": "csv",
            "provenance_status": "unverified",
            "authorization_status": "unverified",
            "documentation_status": "missing_or_unverified",
            "license_status": "unverified",
            "analytical_eligibility": False,
            "eligible_for_publication": False,
            "survey_design_status": "unverified",
            "outstanding_verification_requirements": ["Synthetic evidence requirement"],
        }
    }


class Phase8InventoryTests(unittest.TestCase):
    def test_inventory_fingerprint_is_stable_for_unchanged_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data" / "mine" / "synthetic.csv"
            source.parent.mkdir(parents=True)
            source.write_text("group,value\na,1\n", encoding="utf-8")
            first = build_inventory(root)
            second = build_inventory(root)

        self.assertEqual(first["inventory_fingerprint"], second["inventory_fingerprint"])
        self.assertEqual(first["files"][0]["presence_status"], "discovered")
        self.assertEqual(first["files"][0]["review_status"], "unverified")

    def test_inventory_snapshot_detects_removed_files_and_invalid_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data" / "mine" / "synthetic.csv"
            source.parent.mkdir(parents=True)
            source.write_text("value\n1\n", encoding="utf-8")
            inventory = build_inventory(root)
            source.unlink()
            inventory["files"].append({"relative_path": "../outside.csv"})
            snapshot = verify_inventory_snapshot(inventory, project_root=root)

        self.assertEqual(snapshot["status"], "stale")
        self.assertEqual(snapshot["invalid_record_count"], 1)
        self.assertEqual(snapshot["current_file_count"], 0)

    def test_inventory_skips_symlinks_outside_approved_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "data" / "mine"
            data_root.mkdir(parents=True)
            outside = root / "outside.csv"
            outside.write_text("secret\n", encoding="utf-8")
            link = data_root / "linked.csv"
            try:
                os.symlink(outside, link)
            except OSError:
                self.skipTest("symbolic links are unavailable in this environment")

            self.assertEqual(current_data_file_paths(root), ())
            self.assertEqual(build_inventory(root)["file_count"], 0)


class Phase8ReadinessTests(unittest.TestCase):
    def test_unknown_provenance_and_mapping_keep_report_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            report = build_research_readiness_report(
                root,
                inventory=None,
                registry=_registry(),
                catalogue=_catalogue(),
            )

        self.assertEqual(report["overall_status"], "blocked")
        self.assertFalse(report["analytical_eligibility"])
        self.assertFalse(report["publication_eligibility"])
        self.assertIn("source_provenance", report["blocked_requirements"])
        self.assertIn("indicator_mappings", report["blocked_requirements"])
        self.assertEqual(report["indicators"][0]["mapping_status"], "unverified")

    def test_present_documentation_is_not_treated_as_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            documentation = root / "data" / "docs" / "codebook.pdf"
            documentation.parent.mkdir(parents=True)
            documentation.write_bytes(b"synthetic documentation")
            report = build_research_readiness_report(
                root,
                inventory=build_inventory(root),
                registry=_registry(),
                catalogue=_catalogue(),
            )

        self.assertEqual(report["documentation"]["documentation_file_count"], 1)
        self.assertEqual(report["documentation"]["requirements"]["codebook_or_data_dictionary"], "present_unverified")
        self.assertEqual(report["datasets"][0]["authorization_status"], "unverified")
        self.assertFalse(report["publication_eligibility"])

    def test_invalid_geographic_asset_is_reported_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root / "data" / "geo" / "rwanda.geojson"
            boundary.parent.mkdir(parents=True)
            boundary.write_text(json.dumps({"type": "NotAFeatureCollection"}), encoding="utf-8")
            report = build_research_readiness_report(
                root,
                inventory=build_inventory(root),
                registry={},
                catalogue={},
            )

        self.assertEqual(report["geographic_assets"]["invalid_asset_count"], 1)
        geographic_requirement = next(
            item for item in report["requirements"] if item["requirement"] == "geographic_assets"
        )
        self.assertEqual(geographic_requirement["status"], "invalid")
        self.assertNotIn("coordinates", json.dumps(report))

    def test_report_contains_metadata_only_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            first = build_research_readiness_report(
                root,
                inventory=None,
                registry=_registry(),
                catalogue=_catalogue(),
            )
            second = build_research_readiness_report(
                root,
                inventory=None,
                registry=_registry(),
                catalogue=_catalogue(),
            )

        self.assertEqual(first, second)
        serialized = json.dumps(first)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("relative_path", serialized)
        self.assertNotIn("row_value", serialized)


if __name__ == "__main__":
    unittest.main()
