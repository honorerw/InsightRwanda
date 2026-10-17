from __future__ import annotations

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from insightrwanda.ui.components import (
    build_evidence_blocker_records,
    build_indicator_readiness_summary,
    build_readiness_blocker_records,
    prepare_researcher_action_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def readiness_fixture() -> dict:
    return {
        "blocked_checks": ["dataset_authorization", "verified_variable_mappings"],
        "publication_blocked_checks": ["publication_permission"],
        "messages": [
            "The dataset is not authorized.",
            "Verified mappings are missing.",
            "Publication permission is not recorded.",
        ],
    }


def report_fixture() -> dict:
    return {
        "evidence": {
            "blockers": [
                {
                    "evidence_id": "EVID-AUTH-001",
                    "category": "authorization",
                    "status": "missing",
                    "description": "Written permission for the approved analysis.",
                    "reason_for_blocking": "Local presence is not authorization.",
                    "next_action": "Record the source owner's permitted-use decision.",
                    "related_dataset_id": "dataset-1",
                    "blocks": ["analysis"],
                },
                {
                    "evidence_id": "EVID-MAP-001",
                    "category": "variable_mapping",
                    "status": "provided_unverified",
                    "description": "Codebook-backed mapping for the indicator.",
                    "reason_for_blocking": "The mapping has not been independently verified.",
                    "next_action": "Review the exact-release codebook.",
                    "related_indicator_id": "FI-ACCESS-001",
                    "blocks": ["analysis"],
                },
                {
                    "evidence_id": "EVID-PUB-001",
                    "category": "disclosure_publication",
                    "status": "missing",
                    "description": "Output-specific disclosure and publication review.",
                    "reason_for_blocking": "No publication decision is recorded.",
                    "next_action": "Complete the separate publication review.",
                    "blocks": ["publication"],
                },
            ]
        }
    }


class Phase23ReadinessUiTests(unittest.TestCase):
    def test_blockers_are_separate_records_with_existing_ids_and_statuses(self):
        records = build_readiness_blocker_records(
            readiness_fixture(),
            report_fixture(),
            indicator_id="FI-ACCESS-001",
            dataset_id="dataset-1",
        )
        self.assertEqual(
            [record["identifier"] for record in records],
            ["dataset_authorization", "verified_variable_mappings", "publication_permission"],
        )
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["evidence_ids"], ["EVID-AUTH-001"])
        self.assertEqual(records[1]["evidence_statuses"], ["provided_unverified"])
        self.assertNotIn("The dataset is not authorized. Verified mappings are missing.", records[0]["why_it_matters"])

    def test_evidence_blockers_remain_unverified_and_are_not_approved_by_display(self):
        records = build_evidence_blocker_records(report_fixture())
        mapping = next(record for record in records if record["identifier"] == "EVID-MAP-001")
        self.assertEqual(mapping["status"], "provided_unverified")
        self.assertEqual(mapping["evidence_ids"], ["EVID-MAP-001"])

    def test_missing_estimate_and_publication_approval_never_become_success_states(self):
        summary = build_indicator_readiness_summary(
            {"analysis_eligible": False, "publication_eligible": False},
            {"calculation_status": "blocked", "publication_status": "not_approved", "result": None},
            indicator_id="FI-ACCESS-001",
            blocker_count=3,
        )
        self.assertEqual(summary["estimate_status"], "Not calculated")
        self.assertEqual(summary["publication_status"], "Not approved")
        self.assertNotEqual(summary["estimate_status"], "0")

    def test_action_plan_reacts_to_evidence_status_changes_and_preserves_order(self):
        action_plan = {
            "variable_mapping_review": [
                {"evidence_id": "MAP", "status": "missing", "related_indicator_id": "FI-ACCESS-001"}
            ],
            "source_acquisition": [
                {"evidence_id": "SOURCE", "status": "provided_unverified", "related_dataset_id": "dataset-1"}
            ],
            "authorization_and_permitted_use": [
                {"evidence_id": "AUTH", "status": "missing", "related_dataset_id": "dataset-1"}
            ],
        }
        tasks = prepare_researcher_action_plan(
            action_plan,
            indicator_id="FI-ACCESS-001",
            dataset_id="dataset-1",
        )
        self.assertEqual([task["evidence_id"] for task in tasks], ["SOURCE", "AUTH", "MAP"])
        action_plan["source_acquisition"][0]["status"] = "verified"
        remaining = prepare_researcher_action_plan(action_plan, indicator_id="FI-ACCESS-001", dataset_id="dataset-1")
        self.assertNotIn("SOURCE", [task["evidence_id"] for task in remaining])

    def test_financial_inclusion_and_research_readiness_pages_render_without_exceptions(self):
        for page in ("financial_inclusion.py", "research_readiness.py"):
            app = AppTest.from_file(ROOT / "app_pages" / page).run(timeout=45)
            self.assertFalse(app.exception, page)
        financial = AppTest.from_file(ROOT / "app_pages/financial_inclusion.py").run(timeout=45)
        self.assertEqual(len(financial.warning), 0)
        self.assertTrue(any("FI-ACCESS-001" in item.value for item in financial.get("markdown")))


if __name__ == "__main__":
    unittest.main()
