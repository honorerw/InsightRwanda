# Phase 21 — Submission evidence index

This index points to repository artifacts; it does not independently approve research or submission compliance. “Verified” means the referenced repository artifact was inspected for this assessment, not that an external authority endorsed it.

| Evidence ID | Type | Repository path | Supports | Status |
| --- | --- | --- | --- | --- |
| P21-DOC-001 | Competition rules | `../2026 Hackathon Competition.pdf` (workspace parent; outside the repository) | Track scope, participation/submission conditions, timelines, and rubric transcribed in the assessment | Available and reviewed locally; team compliance not verified |
| P21-READINESS-001 | Generated metadata report | `../artifacts/research_readiness.json` | Current evidence inventory and central research readiness | Blocked; regenerate before reuse |
| P21-RELEASE-001 | Generated workflow audit | `../artifacts/phase18_status.json` | Workflow stages, blockers, separate analytical/publication state | Blocked; no release approval |
| P21-PH20-001 | Reproducibility documentation | `phase20-reproducibility-audit-trail.md` | Manifest, integrity, lineage, audit-event behavior and limits | Software capability; no real result to reproduce |
| P21-PH14-001 | Calculation documentation | `phase14-first-verified-indicator.md` | First-indicator gates and blocked outcome | Blocked |
| P21-PH15-001 | Statistical QA documentation | `phase15-statistical-validation.md` | Synthetic formula/input validation limits | Synthetic-only software validation |
| P21-PH16-001 | Geography documentation | `phase16-geographic-analysis.md` | Boundary, join, and survey-aware gates | Blocked for real geography |
| P21-PH17-001 | Insight documentation | `phase17-verified-insights.md` | Evidence-linked insight and chart gates | No eligible real results |
| P21-PH18-001 | Workflow documentation | `phase18-end-to-end-release-readiness.md` | End-to-end readiness and release constraints | Blocked |
| P21-PH19-001 | Security review documentation | `phase19-security-integrity-review.md` | Defensive review findings and tested controls | Software review only; not certification |
| P21-TEST-001 | Test suite | `../tests/test_phase14.py`–`../tests/test_phase21.py` | Synthetic and metadata-only regression behavior across phases | Software tests; no research evidence |
| P22-TEST-001 | Test suite | `../tests/test_phase22.py` and `../tests/test_research_visualizations.py` | Interactive narrative/filter and visualization contracts, including AppTests | Software tests; synthetic fixtures only |
| P22-DOC-001 | Phase documentation | `phase22-interactive-research-storytelling.md` | Current walkthrough, narrative, filters, export restrictions, and validation snapshot | Inspected; no real findings |
| P21-APP-001 | Application entry point | `../app.py` and `../app_pages/` | Actual navigation and pages | Code inspected; deployment not verified |
| P21-README-001 | Setup documentation | `../README.md` | Project setup and limits | Repository documentation |

## Reviewer verification

From the repository root, inspect the referenced files, refresh current metadata with `PYTHONPATH=src .venv/bin/python scripts/research_readiness.py`, and run the commands in the submission assessment. Check the resulting central eligibility fields and blocker IDs. Do not interpret generated files, passing tests, a repository URL, or a checksum as source authorization or publication permission.
