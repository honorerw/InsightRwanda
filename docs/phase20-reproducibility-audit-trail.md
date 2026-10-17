# Phase 20 — Research Reproducibility and Audit Trail

## Scope and current state

Phase 20 adds a metadata-only reproducibility layer for future eligible
aggregate results. It does not load source observations, execute code from a
manifest, grant analytical eligibility, grant publication permission, or
produce a Rwanda estimate.

The live project remains blocked. No authorized real result or reproducibility
manifest exists, so the live Phase 20 state is `not_configured` with
`reproducibility_manifest_missing`. Synthetic fixtures are used only to test
software behavior.

## Manifest schema

Manifests use the explicit schema version `phase20-manifest-v1`. Required
lineage includes:

- an explicitly supplied manifest and result identifier;
- dataset ID, exact release, and the existing authorized input SHA-256
  reference;
- indicator, definition, mapping, calculation-specification, and method
  versions or identifiers;
- validation evidence references and an analytical eligibility decision
  reference;
- result checksum, output format, limitations, classification, and a
  timezone-aware creation timestamp; and
- geographic resource and boundary release when geographic analysis applies.

The builder rejects missing identifiers and does not read source files to
invent checksums. It can reuse an existing registered content checksum, but a
checksum remains a content-consistency check, not proof of authenticity,
authorization, statistical correctness, or publication permission.

## Canonicalization and integrity

Supported metadata is JSON-like: nulls, booleans, finite numbers, strings,
lists, and mappings with string keys. Canonical serialization uses UTF-8
Unicode, sorted object keys, compact separators, and explicit rejection of
unsupported types and non-finite numbers. SHA-256 is calculated over that
canonical representation.

Result checksums exclude only mutable artifact bookkeeping and the manifest
itself. Manifest checksums exclude only the manifest checksum field. Altered
result content, malformed manifests, unsupported schema versions, raw payloads,
and contradictory lineage are rejected.

## Lineage and reproduction states

The validator keeps these decisions separate:

- manifest structure and checksum validity;
- result integrity verification;
- lineage traceability;
- reproduction comparison status;
- current analytical eligibility; and
- current publication eligibility.

Aggregate comparisons use exact canonical metadata and exact numeric values by
default. A caller may supply an explicit non-negative numerical tolerance;
the output records whether exact or tolerance-based comparison was used.
Synthetic comparisons are reported as `software_test_only`, never as verified
research reproduction. No reproduction executor or arbitrary code loader was
introduced; if authorized inputs or the exact method are unavailable,
reproduction remains blocked.

## Change detection and revalidation

`detect_reproducibility_changes` compares only supplied critical fields:
source release and checksum, definition and mapping versions, calculation
specification and method versions, geographic boundary release, validation
schema, dependency versions, and authorization status. A changed field
returns `revalidation_required` with stable field-specific blocker IDs.
Unchanged content does not independently prove that authorization remains
valid; current eligibility is rechecked separately.

## Audit trail

Audit records use schema `phase20-audit-v1` and contain event IDs, event type,
status, optional manifest/result IDs, safe reason codes, timestamps, and
metadata-only markers. Event IDs are deterministic for the decision identity,
so repeated evaluation can be deduplicated. The persisted JSON file is useful
metadata history but is not immutable or tamper-proof storage; no signature or
external audit service was added.

Audit events cannot grant eligibility. The central readiness evaluator and
existing authorization, analytical, geographic, disclosure, and publication
gates remain authoritative.

## Dashboard and readiness integration

Phase 18 now includes a scoped “Reproducibility manifest and audit trail”
transition. The Research Readiness page reports manifest, integrity, lineage,
and reproduction states separately and displays blockers when no manifest or
eligible result exists. The readiness script records the Phase 20 summary and
deduplicated metadata-only evaluation events without loading source rows.

## Tests and limitations

`tests/test_phase20.py` contains 16 focused tests covering canonicalization,
schema and checksum failures, lineage, version changes, authorization
revalidation, eligibility separation, synthetic fixtures, numerical
comparison, unavailable inputs, privacy, audit deduplication, and live blocked
readiness. These tests validate software behavior only; they do not establish
reproducibility or validity of real Rwanda research findings.

Final validation passed: 203 total unit tests, 15 Streamlit AppTests,
compilation, 12 JSON metadata/artifact files, `pip check`, and `git diff
--check`. The readiness report remained blocked with analytical and
publication eligibility false; Phase 20 remained `not_configured` with
`reproducibility_manifest_missing`. `pip check` emitted only the environment's
non-fatal unwritable pip-cache warning. No source-data diff or Phase 14/16
research result artifact was created.

Before real-data reproduction, the project still needs verified exact-release
source access, permitted use, indicator mappings and definition, approved
methodology and calculation specification, passing validation, current
analytical eligibility, and—when relevant—geographic and publication review.

