from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from insightrwanda.ui.metadata import (
    catalogue_summary,
    inventory_summary,
    load_dashboard_metadata,
    status_label,
)


class AppFoundationTests(unittest.TestCase):
    def test_catalogue_summary_reports_only_metadata_statuses(self) -> None:
        summary = catalogue_summary(
            {
                "candidate": {
                    "indicator_id": "SYNTHETIC-001",
                    "status": "proposed_pending_review",
                    "authorization_status": "unverified",
                    "publication_status": "not_eligible",
                    "required_variables": [],
                    "evidence_status": "no_verified_codebook_mapping",
                    "review_blockers": ["codebook"],
                }
            }
        )

        self.assertEqual(summary["indicator_count"], 1)
        self.assertEqual(summary["verified_mapping_count"], 0)
        self.assertEqual(summary["indicators_with_review_blockers"], 1)
        self.assertEqual(summary["authorization_counts"], {"unverified": 1})

    def test_inventory_summary_does_not_return_paths_or_records(self) -> None:
        summary = inventory_summary(
            {
                "file_count": 2,
                "duplicate_checksum_group_count": 1,
                "files": [
                    {"format": "csv", "authorization_status": "unverified", "eligible_for_publication": False, "relative_path": "restricted.csv"},
                    {"format": "geojson", "authorization_status": "unverified", "eligible_for_publication": False, "relative_path": "boundary.geojson"},
                ],
            }
        )

        self.assertEqual(summary["file_count"], 2)
        self.assertNotIn("files", summary)
        self.assertNotIn("relative_path", json.dumps(summary))

    def test_missing_or_malformed_metadata_degrades_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "metadata").mkdir(parents=True)
            (root / "data" / "metadata" / "indicator_catalogue.json").write_text("not json", encoding="utf-8")
            metadata = load_dashboard_metadata(root)

        self.assertEqual(metadata.catalogue, {})
        self.assertIsNotNone(metadata.catalogue_error)
        self.assertIsNone(metadata.inventory)
        self.assertIsNotNone(metadata.inventory_error)

    def test_valid_metadata_is_loaded_without_data_directory_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalogue_dir = root / "data" / "metadata"
            catalogue_dir.mkdir(parents=True)
            (root / "data" / "restricted.csv").write_text("secret,record\nnot-used,not-used\n", encoding="utf-8")
            (catalogue_dir / "indicator_catalogue.json").write_text(
                json.dumps(
                    {
                        "indicators": [
                            {
                                "indicator_id": "SYNTHETIC-001",
                                "display_name": "Synthetic candidate",
                                "description": "Synthetic metadata only",
                                "status": "proposed_pending_review",
                                "required_variables": [],
                                "authorization_status": "unverified",
                                "publication_status": "not_eligible",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            metadata = load_dashboard_metadata(root)

        self.assertEqual(list(metadata.catalogue), ["SYNTHETIC-001"])
        self.assertIsNone(metadata.catalogue_error)

    def test_project_catalogue_count_is_loaded_from_metadata(self) -> None:
        root = Path(__file__).resolve().parents[1]
        metadata = load_dashboard_metadata(root)

        self.assertIsNone(metadata.catalogue_error)
        self.assertEqual(catalogue_summary(metadata.catalogue)["indicator_count"], 7)

    def test_status_labels_are_conservative(self) -> None:
        self.assertEqual(status_label("proposed_pending_review")[0], "Proposed · review required")
        self.assertEqual(status_label("unrecognized")[0], "Status unavailable")


if __name__ == "__main__":
    unittest.main()
