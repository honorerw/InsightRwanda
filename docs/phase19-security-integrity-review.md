# Phase 19 — Independent Security, Integrity and Research Governance Review

## Scope and conclusion

This was a defensive review of the local InsightRwanda workflow implemented in
Phases 12–18. It inspected the central readiness evaluator, source and
geographic registries, calculation and result validators, artifact writers,
the Phase 18 workflow audit, readiness reporting, and the Streamlit-facing
status paths.

The review did not access external systems or restricted datasets. The live
project remains blocked from real analysis and public release because the
required source authorization, exact-release documentation, mappings,
methodology, and other evidence are unresolved. Passing software tests does
not change that status.

## Threat model

The review considered the following realistic threats:

- missing, denied, contradictory, or manually edited authorization metadata;
- malformed or stale readiness summaries and unsupported status values;
- unregistered datasets, path traversal, absolute-path aliases, and symlink
  escapes;
- malformed results, contradictory lineage, stale integrity metadata, and
  synthetic results presented as research;
- direct calls to calculation or artifact-writing functions that bypass the
  dashboard;
- analytical eligibility being confused with publication eligibility;
- duplicate or unstable blocker records;
- raw records, dummy credentials, identifiers, or sensitive values appearing
  in errors, reports, or artifacts;
- accidental source-data modification; and
- test fixtures or rejected outputs leaking into production artifact paths.

The highest-impact boundaries are authorization and central eligibility,
result persistence, and public presentation. The review therefore tested
those boundaries independently of the UI.

## Components inspected

The review inspected:

- `analytics/phase12.py`, `phase13.py`, `phase14.py`, `readiness.py`,
  `validation.py`, `geography.py`, `insights.py`, and `release.py`;
- dataset, evidence, source-verification, geographic-resource, path, and
  research-readiness data helpers;
- `scripts/research_readiness.py` and the generated metadata-only readiness
  artifacts;
- result writers and loaders for Phase 14, geographic results, and the Phase
  18 workflow audit;
- dashboard readiness and analytical pages; and
- the Phase 12–18 tests and the new `tests/test_phase19.py` suite.

## Confirmed findings and fixes

### Medium — saved calculation results were not revalidated on load

`load_saved_calculation_result` previously checked only the calculated status
and a shallow set of top-level keys. A manually edited artifact could retain a
calculated status while containing nested row-level payloads or missing
required provenance.

The loader now applies the complete aggregate integrity validator and a
recursive raw-payload check before returning a result. The same recursive
check is used by the Phase 14 calculation writer.

### Medium — geographic artifact protection was separate and shallow

The geographic writer used a local top-level raw-key check. Nested records,
geometry, or coordinates could therefore evade that particular check.

Geographic persistence now uses the shared recursive aggregate-safety check
and explicitly rejects `raw_records_included=True`.

### Low — workflow-audit persistence accepted malformed structures

The Phase 18 audit writer checked the audit type and metadata-only marker but
did not validate status vocabulary, duplicate blockers, stage structure, or
the consistency of `release_eligible` with blockers and stage outcomes.

The writer now rejects unsupported statuses, duplicate blocker IDs, duplicate
or malformed stages, nested raw payloads, and inconsistent release eligibility.
The audit remains a report and is not an authorization source; the dashboard
and readiness workflow continue to derive decisions from current metadata and
the central evaluator.

## Controls verified by tests

The Phase 19 tests demonstrate that:

- missing or denied authorization remains analytically ineligible;
- a favorable readiness summary cannot override the central evaluator;
- malformed authorization status fails closed;
- unregistered datasets, traversal paths, and supported symlink escapes are
  rejected;
- contradictory lineage and synthetic results cannot become release outputs;
- direct artifact-writer calls still enforce their gates;
- rejected writes do not overwrite an existing artifact;
- nested raw payloads are rejected both before persistence and on load;
- analytical and publication/geographic gates remain separate;
- dummy sensitive values are not included in integrity diagnostics;
- rejected output paths leave source files unchanged; and
- a metadata-only blocked audit can be saved without granting eligibility.

These are software-boundary tests with synthetic or metadata-only fixtures.
They are not evidence that any Rwanda survey estimate is valid.

## Controls not verified or not available

- No restricted source data was available or accessed, so real-data access,
  source authenticity, and exact-release authorization remain unverified.
- No formal cryptographic signing or tamper-evident audit log exists. A file
  checksum, where recorded, remains an integrity reference and does not prove
  permission or authenticity.
- The current project does not implement a public-release service; public
  publication remains governed by the Phase 17 insight and disclosure gates.
- Complex-survey variance methods remain blocked where the approved inputs or
  implementation are unavailable.
- Geographic readiness remains scoped to geographic analysis and is not a
  universal prerequisite for non-geographic analysis.

## Remaining research and governance risks

FI-ACCESS-001 remains blocked. Human review is still required for the exact
source release, authorization and permitted use, codebook/questionnaire,
indicator mappings and definition, survey weights and design, quality
acceptance, calculation specification, disclosure review, and any publication
permission. No real indicator, geographic estimate, or public research output
was produced by this review.

The Phase 18 release audit remains a metadata-only status report. It must not
be treated as NISR approval, source authorization, statistical certification,
or publication permission.

## Tests and validation

The focused Phase 19 suite passed: 14 tests. The full project suite passed:
187 tests. The explicit Streamlit AppTest groups passed: 15 tests. The
readiness script exited successfully and reported `blocked`, with analytical
and publication eligibility both false, 32 Phase 18 blockers, and zero
verified geographic resources. Compilation, JSON validation of 11 metadata
and artifact files, dependency checking, and `git diff --check` also passed.
`pip check` reported no broken requirements; it emitted only the environment's
non-fatal unwritable pip-cache warning. The suite includes the existing Phase
12–18 regressions and does not place synthetic results in production artifact
directories.

