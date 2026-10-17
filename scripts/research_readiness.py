#!/usr/bin/env python3
"""Generate a safe, machine-readable research-readiness report.

The report uses the registered metadata and a current path snapshot only. It
does not load source records or document contents, and it never grants
authorization or publication permission.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from insightrwanda.analytics.catalogue import load_indicator_catalogue  # noqa: E402
from insightrwanda.data.paths import resolve_derived_output_path  # noqa: E402
from insightrwanda.data.registry import load_dataset_registry  # noqa: E402
from insightrwanda.data.geography import load_geographic_resource_registry  # noqa: E402
from insightrwanda.data.evidence import load_evidence_register  # noqa: E402
from insightrwanda.data.source_verification import load_source_verification_matrix  # noqa: E402
from insightrwanda.data.research_readiness import build_research_readiness_report  # noqa: E402
from insightrwanda.analytics.phase12 import build_phase12_status  # noqa: E402
from insightrwanda.analytics.phase13 import build_phase13_status  # noqa: E402
from insightrwanda.analytics.phase14 import build_phase14_status  # noqa: E402
from insightrwanda.analytics.insights import build_phase17_status  # noqa: E402
from insightrwanda.analytics.release import build_phase18_status, save_workflow_audit  # noqa: E402
from insightrwanda.analytics.reproducibility import append_audit_event, build_audit_event, save_audit_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root containing data/ and metadata (default: repository root).",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("artifacts/source_inventory.json"),
        help="Inventory JSON path relative to the project root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/research_readiness.json"),
        help="Generated JSON output path under artifacts/ or data/processed/.",
    )
    args = parser.parse_args()
    project_root = args.project_root.expanduser().resolve()
    inventory_path = resolve_derived_output_path(args.inventory, project_root=project_root)
    try:
        inventory_document = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        inventory_document = None

    catalogue = load_indicator_catalogue(project_root / "data" / "metadata" / "indicator_catalogue.json")
    registry = load_dataset_registry(project_root / "data" / "metadata" / "dataset_registry.json")
    try:
        geographic_resources = load_geographic_resource_registry(
            project_root / "data" / "metadata" / "geographic_resources.json"
        )
    except Exception:
        geographic_resources = []
    try:
        evidence = load_evidence_register(
            project_root / "data" / "metadata" / "evidence_register.json",
            dataset_ids=registry.keys(),
            indicator_ids=catalogue.keys(),
        )
    except Exception:
        evidence = None
    try:
        source_verification = load_source_verification_matrix(
            project_root / "data" / "metadata" / "source_verification.json",
            dataset_ids=registry.keys(),
            project_root=project_root,
        )
    except Exception:
        source_verification = None
    report = build_research_readiness_report(
        project_root,
        inventory=inventory_document if isinstance(inventory_document, dict) else None,
        registry=registry,
        catalogue=catalogue,
        evidence=evidence,
        source_verification=source_verification,
        geographic_resources=geographic_resources,
    )
    output = resolve_derived_output_path(args.output, project_root=project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    phase12 = build_phase12_status(registry, catalogue, project_root=project_root)
    phase12_path = resolve_derived_output_path(Path("artifacts/phase12_status.json"), project_root=project_root)
    phase12_path.parent.mkdir(parents=True, exist_ok=True)
    phase12_path.write_text(json.dumps(phase12, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    phase13 = build_phase13_status(project_root, registry, catalogue, evidence, source_verification)
    phase13_path = resolve_derived_output_path(Path("artifacts/phase13_status.json"), project_root=project_root)
    phase13_path.parent.mkdir(parents=True, exist_ok=True)
    phase13_path.write_text(json.dumps(phase13, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    phase14 = build_phase14_status(project_root, registry, catalogue, source_verification)
    phase14_path = resolve_derived_output_path(Path("artifacts/phase14_status.json"), project_root=project_root)
    phase14_path.parent.mkdir(parents=True, exist_ok=True)
    phase14_path.write_text(json.dumps(phase14, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    phase17 = build_phase17_status(
        phase14,
        catalogue.get("FI-ACCESS-001"),
        intended_use="public_display",
    )
    phase18 = build_phase18_status(
        project_root,
        registry,
        catalogue,
        evidence,
        source_verification,
        inventory=inventory_document if isinstance(inventory_document, dict) else None,
        geographic_resources=geographic_resources,
        dataset_id="finscope_2024_rwanda_csv",
        indicator_id="FI-ACCESS-001",
        intended_use="public_display",
    )
    save_workflow_audit(phase18, project_root=project_root)
    phase20 = phase18.get("reproducibility") or {
        "status": "not_configured",
        "blocker_ids": ["reproducibility_manifest_missing"],
        "reproduction_status": "not_run",
    }
    audit_path = resolve_derived_output_path(Path("artifacts/phase20_audit.json"), project_root=project_root)
    existing_events: list[dict[str, object]] = []
    try:
        audit_document = json.loads(audit_path.read_text(encoding="utf-8"))
        if isinstance(audit_document, dict) and isinstance(audit_document.get("events"), list):
            existing_events = [item for item in audit_document["events"] if isinstance(item, dict)]
    except (OSError, UnicodeError, json.JSONDecodeError):
        existing_events = []
    event_status = "passed" if phase20.get("status") == "verified" else "blocked"
    phase20_event = build_audit_event(
        "reproducibility_evaluation",
        event_status,
        reason_codes=phase20.get("blocker_ids", []),
    )
    save_audit_events(append_audit_event(existing_events, phase20_event), project_root=project_root)
    report["phase17"] = {
        "status": phase17.get("status", "blocked"),
        "source_result_id": phase17.get("source_result_id"),
        "blocker_ids": list(phase17.get("blocker_ids", [])),
        "analytical_eligibility": phase17.get("analytical_eligibility", False),
        "publication_eligibility": phase17.get("publication_eligibility", False),
    }
    report["phase18"] = {
        "status": phase18.get("status", "blocked"),
        "blocker_ids": list(phase18.get("blocker_ids", [])),
        "analytical_eligibility": phase18.get("analytical_eligibility", False),
        "publication_eligibility": phase18.get("publication_eligibility", False),
        "release_eligible": phase18.get("release_eligible", False),
    }
    report["phase20"] = {
        "status": phase20.get("status", "not_configured"),
        "manifest_status": phase20.get("manifest_status", "invalid_or_missing"),
        "integrity_status": phase20.get("integrity_status", "not_run"),
        "lineage_status": phase20.get("lineage_status", "incomplete"),
        "reproduction_status": phase20.get("reproduction_status", "not_run"),
        "blocker_ids": list(phase20.get("blocker_ids", [])),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": output.relative_to(project_root).as_posix(),
                "overall_status": report["overall_status"],
                "inventory_status": report["inventory"]["status"],
                "blocked_requirements_count": len(report["blocked_requirements"]),
                "analytical_eligibility": report["analytical_eligibility"],
                "publication_eligibility": report["publication_eligibility"],
                "phase12_status": phase12["status"],
                "phase12_blockers": len(phase12["blockers"]),
                "phase13_status": phase13["status"],
                "phase13_analysis_eligible": phase13["analysis_eligible"],
                "phase13_publication_eligible": phase13["publication_eligible"],
                "phase14_status": phase14["status"],
                "phase14_calculation_status": phase14["calculation_status"],
                "phase14_blockers": len(phase14["blocker_ids"]),
                "geographic_resource_count": report["geographic_resources"]["resource_count"],
                "geographic_verified_resource_count": report["geographic_resources"]["verified_resource_count"],
                "geographic_requirement_status": next(
                    item["status"]
                    for item in report["requirements"]
                    if item["requirement"] == "geographic_assets"
                ),
                "phase17_status": phase17["status"],
                "phase17_blockers": len(phase17.get("blocker_ids", [])),
                "phase18_status": phase18["status"],
                "phase18_blockers": len(phase18.get("blocker_ids", [])),
                "phase20_status": phase20.get("status", "not_configured"),
                "phase20_blockers": len(phase20.get("blocker_ids", [])),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
