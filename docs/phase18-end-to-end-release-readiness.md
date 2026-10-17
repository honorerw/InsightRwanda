# Phase 18 · End-to-End Research Workflow and Release Readiness

## Outcome

Phase 18 adds a metadata-only end-to-end workflow audit. It composes the
existing Phase 12 intake, Phase 13 access/readiness, Phase 14 calculation,
Phase 15 validation, Phase 16 geographic, and Phase 17 insight/publication
boundaries. It does not create a second authorization or eligibility system.

The current project remains blocked. No authorized real source release,
verified FI-ACCESS-001 definition and mappings, eligible analytical result,
verified geographic resource, disclosure review, or publication approval is
available. No real finding or public research output was produced.

## Workflow gates

`insightrwanda.analytics.release.build_phase18_status` records each transition
with a stable stage ID, status, authority, blocker IDs, explanation, next
actions, and safe evidence references:

1. `dataset_registration` — registry membership and current source inventory.
2. `source_identity_authorization` — provenance, exact release, permission,
   terms, and registered path from the central evaluator.
3. `definition_mapping_methodology` — codebook-backed mappings, definition,
   missingness rules, schema, and calculation specification.
4. `geographic_resource_verification` — required only when geographic analysis
   is explicitly requested; otherwise `not_applicable`.
5. `quality_and_survey_validation` — data-quality acceptance, weights, survey
   design, and supported variance requirements.
6. `analytical_execution` — current central eligibility and a calculated
   aggregate result.
7. `result_lineage_and_integrity` — dataset/release/indicator consistency,
   provenance, aggregate-only shape, and Phase 15 integrity validation.
8. `statistical_validation` — passing Phase 15 quality and calculation reports.
9. `disclosure_and_publication` — separate output-level disclosure and
   publication eligibility.
10. `approved_presentation` — Phase 17 verified insight/presentation gate.
11. `readiness_consistency` — indicator-level report agreement with the
    central evaluator.

The audit status is `ready` only if every applicable stage passes and there
are no blocker IDs. `not_applicable` is used only for scoped requirements;
missing, failed, or unperformed checks are never converted to pass.

## Central authority and consistency

The audit delegates analytical decisions to the existing central readiness
evaluator. For an existing aggregate result, it re-runs that same evaluator
against the registered documented schema without loading source observations.
It also compares the indicator row in the research-readiness report with the
central decision.

During implementation, a path-normalization defect was corrected in
`data.research_readiness`: registry source paths are relative to `data/`,
while inventory paths are repository-relative. The report now compares both
forms safely. This does not grant access or authorization.

Geographic readiness is scoped. An ordinary FI-ACCESS-001 workflow does not
become blocked merely because no geographic resource exists; an explicitly
requested geographic workflow does require a verified, release-compatible
resource and safe join.

## Lineage and artifact controls

The audit checks that a supplied result identifies the registered dataset,
exact release, indicator, and definition version; that its provenance agrees
with those identifiers; and that Phase 15 aggregate integrity passes. It
rejects synthetic classifications, contradictory provenance, failed quality
reports, raw-record fields, and results whose recorded analytical readiness is
false.

`save_workflow_audit` writes only a metadata-only readiness audit under the
existing derived-artifact boundary. It is not a successful research-result or
publication artifact. Existing `save_calculation_result` and
`save_geographic_analysis_result` gates remain responsible for successful
aggregate result persistence and reject blocked or invalid inputs.

## Tests

`tests/test_phase18.py` covers:

- missing authorization and unregistered datasets;
- unverified definition/mapping, quality, and survey prerequisites;
- scoped geographic requirements;
- analytically valid but publication-ineligible results;
- synthetic, missing, contradictory, and failed-integrity results;
- geographic presentation without verified resources;
- disclosure failure and central-readiness bypass attempts;
- stable blocker deduplication and readiness-report consistency;
- blocked artifact behavior and metadata-only audit persistence.

Fixtures are in-memory or isolated temporary directories. They are software
fixtures, not Rwanda data or statistical evidence.

## Current release decision

The generated Phase 18 status is blocked. The current readiness report records
the same blocked analytical/publication state, no verified geographic
resources, and no successful Phase 14 or Phase 16 result artifact. The audit
does not imply NISR approval, permission to analyze, or permission to publish.

Before real-data analysis, the project still needs the authorized exact
release, provenance and terms, reviewed questionnaire/codebook, approved
definition and mappings, documented survey design and weights, accepted data
quality checks, and central analytical eligibility. Before public release it
also needs output-level disclosure, licensing, attribution, and publication
approval.
