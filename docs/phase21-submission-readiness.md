# Phase 21 — Submission readiness assessment

## Current assessment

This is a technical readiness report, not an NISR approval or a claim that the project is ready to publish research. Current generated metadata reports the project as blocked: real analytical eligibility is false, publication eligibility is false, and Phase 20 reproducibility is `not_configured`. No genuine Rwanda estimate is claimed here. Re-run `PYTHONPATH=src .venv/bin/python scripts/research_readiness.py` to refresh metadata before relying on current status; the application and assessment helper do not run the test suite.

| Dimension | Evidence-based state | Meaning |
| --- | --- | --- |
| Software capabilities | Implemented workflow and dashboard pages, described in Phases 12–20 | Code presence does not establish research validity. |
| Software validation | Must be established by the repository test command | Synthetic fixtures validate software behavior only. |
| Source data and authorization | Blocked in `artifacts/research_readiness.json` and `artifacts/phase18_status.json` | Exact release, provenance, authorization, permitted use, documentation, and codebook evidence remain unresolved. |
| Indicator/methodology | Blocked | FI-ACCESS-001 remains a candidate; no verified mapping and approved survey method support a real estimate. |
| Geographic research | Unavailable/blocked where requested | No verified official boundary resource or crosswalk is registered. Geography is not a universal prerequisite for non-geographic analysis. |
| Analytical eligibility | False | Central readiness remains authoritative. |
| Publication eligibility | False | Separate disclosure and publication review has not passed. |
| Reproducibility | `not_configured` | No genuine eligible result exists to reproduce. |
| Official hackathon compliance | Not verified | Competition document requirements were reviewed, but team eligibility, registration, GitHub/deployment deliverables, declarations, and organizer-specific interpretation have not been verified. |

## Competition-document review

The local document `/home/dna/Projects/hackton/2026 Hackathon Competition.pdf` was available and reviewed (five pages). It describes Track 2 as understanding financial exclusion, poverty dynamics, and social-protection impact in Rwanda, and says solutions should use NISR data, optionally with related public/open data. It encourages tangible practical impact. The document lists student eligibility, a two-student team with at least one Rwandan citizen, public GitHub link, deployed app link and documentation, IP assignment to NISR, originality/source acknowledgement declarations, and disclosure of AI-tool use. It gives registration and submission deadlines of 20 October and 30 October 2026 at 11:59 PM, respectively. Its five evaluation areas are problem relevance, data use/methodology, technical innovation, usability/design, and tangible impact (20 points each).

These are statements transcribed from the available competition PDF, not confirmation that the team meets them or that rules have not subsequently changed. The PDF does not establish project approval, data authorization, or permission to publish. Public GitHub/deployed-app submission requirements are not considered met merely because this repository has a Git remote or runs locally.

## Safe demonstration boundary

No synthetic-result dashboard mode has been added. The application demonstrates its real metadata-backed workflow and blocked states; it does not show fictional numeric examples as Rwanda statistics. Synthetic fixtures remain confined to tests and are explicitly identified there. The financial-inclusion page communicates that no estimate was calculated. The demo script in [phase21-demo-script.md](phase21-demo-script.md) follows the existing app rather than implying unavailable functionality.

## Local technical setup

The repository pins dependencies in `requirements.txt`; the container definition uses Python 3.12, while this validation environment uses Python 3.14.7. To mirror the container locally, create an isolated Python 3.12 environment and install the pinned requirements:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q app.py src app_pages scripts tests
.venv/bin/python -m pip check
streamlit run app.py
```

The final command is the documented launch command; it is not a claim that a deployed app or a server launch was verified in every environment. Streamlit AppTests are run as part of `unittest` discovery (see [test_phase7.py](../tests/test_phase7.py) and [test_phase10.py](../tests/test_phase10.py)). `git diff --check` is also part of validation. Refresh the readiness report after metadata changes; do not edit its derived status to imply approval.

See [phase21-evidence-index.md](phase21-evidence-index.md) for traceable project evidence and [phase20-reproducibility-audit-trail.md](phase20-reproducibility-audit-trail.md) for the manifest workflow and its limits.

## Validation snapshots

The historical Phase 21 snapshot recorded 211 full-suite tests and 8 focused Phase 21 tests. That count is retained here only as a record of the earlier phase; it is not the latest project total.

The latest Phase 22 validation on 2026-10-14 ran 227 tests successfully with `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests`. Existing Streamlit AppTests ran within that suite, not in a deployed browser or hosted server. The Phase 22 focused suite passed 7 tests; the combined Phase 17, visualization, and Phase 22 suites passed 28 tests. `compileall` completed successfully, `pip check` reported no broken requirements (with a non-fatal cache-permission warning), `git diff --check` passed, and all 12 JSON files in `data/metadata/` and `artifacts/` parsed successfully.

The latest readiness command reported `overall_status=blocked`, inventory `current`, analytical eligibility `false`, publication eligibility `false`, Phase 14/17/18 `blocked`, Phase 20 `not_configured`, and zero registered or verified geographic resources. The nine top-level blocked requirement categories are metadata-derived, not a manually entered readiness score. No source dataset was read and no real result artifact was created. See [Phase 22 validation](phase22-interactive-research-storytelling.md) for the exact current check outcomes.
