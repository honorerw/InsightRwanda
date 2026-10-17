from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from insightrwanda.data.errors import DataLoaderError
from insightrwanda.data.evidence import load_evidence_register, summarize_evidence, validate_evidence_register
from insightrwanda.ui.metadata import load_dashboard_metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _item(**overrides):
    item = {
        "evidence_id": "EVID-SYNTHETIC-001",
        "category": "authorization",
        "description": "Synthetic authorization evidence.",
        "status": "missing",
        "evidence_reference": None,
        "source_organization": None,
        "verification_date": None,
        "reviewer": None,
        "reason_for_blocking": "Synthetic evidence is not provided.",
        "next_action": "Provide synthetic evidence.",
        "mandatory": True,
        "blocks": ["analysis"],
    }
    item.update(overrides)
    return item


class EvidenceRegisterTests(unittest.TestCase):
    def test_valid_register_loads_and_aggregates_statuses(self) -> None:
        document = {"evidence_register_version": 1, "items": [_item(), _item(evidence_id="EVID-SYNTHETIC-002", status="provided_unverified")]}
        items = validate_evidence_register(document, dataset_ids={"dataset"}, indicator_ids={"indicator"})
        summary = summarize_evidence(items)

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(summary["provided_unverified"], 1)
        self.assertEqual(summary["blocked"], 2)
        self.assertEqual(summary["analysis_blocking"], 2)

    def test_invalid_status_and_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(DataLoaderError):
            validate_evidence_register({"items": [_item(status="approved")]})
        with self.assertRaises(DataLoaderError):
            validate_evidence_register({"items": [_item(), _item()]})

    def test_unknown_references_are_rejected(self) -> None:
        with self.assertRaises(DataLoaderError):
            validate_evidence_register(
                {"items": [_item(related_dataset_id="unknown")]},
                dataset_ids={"known"},
            )
        with self.assertRaises(DataLoaderError):
            validate_evidence_register(
                {"items": [_item(related_indicator_id="unknown")]},
                indicator_ids={"known"},
            )

    def test_malformed_register_file_fails_with_safe_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(DataLoaderError):
                load_evidence_register(path)


class EvidenceIntegrationTests(unittest.TestCase):
    def test_project_evidence_register_is_validated_against_catalogue_and_registry(self) -> None:
        metadata = load_dashboard_metadata(PROJECT_ROOT)

        self.assertIsNone(metadata.evidence_error)
        self.assertIsNotNone(metadata.research_readiness)
        report = metadata.research_readiness
        summary = report["evidence"]["summary"]
        self.assertEqual(summary["total"], 39)
        self.assertEqual(summary["verified"], 0)
        self.assertEqual(summary["missing"], 37)
        self.assertEqual(summary["provided_unverified"], 2)
        self.assertEqual(report["overall_status"], "blocked")
        self.assertFalse(report["analytical_eligibility"])
        self.assertFalse(report["publication_eligibility"])
        self.assertTrue(all(not item["analytical_eligibility"] for item in report["datasets"]))

    def test_blockers_have_reasons_and_next_actions(self) -> None:
        report = load_dashboard_metadata(PROJECT_ROOT).research_readiness
        blockers = report["evidence"]["blockers"]

        self.assertTrue(blockers)
        self.assertTrue(all(item["reason_for_blocking"] for item in blockers))
        self.assertTrue(all(item["next_action"] for item in blockers))

    def test_malformed_evidence_metadata_degrades_without_approving_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata_dir = root / "data" / "metadata"
            metadata_dir.mkdir(parents=True)
            (metadata_dir / "indicator_catalogue.json").write_text(
                json.dumps({"indicators": []}), encoding="utf-8"
            )
            (metadata_dir / "dataset_registry.json").write_text(
                json.dumps({"datasets": []}), encoding="utf-8"
            )
            (metadata_dir / "evidence_register.json").write_text(
                json.dumps({"items": [{"status": "approved"}]}), encoding="utf-8"
            )
            metadata = load_dashboard_metadata(root)

        self.assertIsNotNone(metadata.evidence_error)
        self.assertIsNotNone(metadata.research_readiness)
        self.assertEqual(metadata.research_readiness["evidence"]["status"], "unavailable")
        self.assertFalse(metadata.research_readiness["analytical_eligibility"])
        self.assertFalse(metadata.research_readiness["publication_eligibility"])


class EvidencePageSmokeTests(unittest.TestCase):
    def test_evidence_center_renders_without_exceptions(self) -> None:
        app = AppTest.from_file(PROJECT_ROOT / "app_pages" / "research_readiness.py").run(timeout=20)

        self.assertFalse(app.exception)
        rendered = "\n".join(item.value for item in app.markdown)
        self.assertIn("Research readiness", rendered)
        self.assertIn("Provided · unverified", rendered)


if __name__ == "__main__":
    unittest.main()
