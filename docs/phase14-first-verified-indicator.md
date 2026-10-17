# Phase 14 — First verified indicator calculation

## Current outcome

Phase 14 is implemented as a reproducible, evidence-gated calculation workflow. The live InsightRwanda metadata remains blocked for `FI-ACCESS-001` (Formal financial access). No Rwanda estimate was calculated and no successful result artifact was written.

Current blockers include the absent registered FinScope file, unverified project authorization and terms, missing exact-release questionnaire/codebook review, missing release-matched schema and mappings, unresolved definition and missing-value rules, unverified weight and survey-design support, missing quality acceptance, and absent approved calculation specification. These are derived from the central readiness evaluator and recorded in `artifacts/phase14_status.json`.

## Architecture

- `src/insightrwanda/analytics/readiness.py` remains the single readiness evaluator. Strict Phase 14 checks cover the approved registered path, exact release match, permitted use, exact-release documents, schema validation, eligibility/missingness, calculation specification, weight interpretation, survey design, and central analytical eligibility.
- `src/insightrwanda/analytics/phase14.py` provides `evaluate_phase14_readiness`, `build_phase14_status`, `calculate_verified_indicator`, `save_calculation_result`, and `load_saved_calculation_result`.
- `scripts/research_readiness.py` regenerates `artifacts/phase14_status.json` alongside the Phase 12 and Phase 13 status artifacts. Status generation is metadata-only and does not load observations.
- `src/insightrwanda/ui/pages.py` uses the same Phase 14 evaluator on the Financial Inclusion and Research Readiness pages. It shows blocker IDs and human actions when blocked, and only approved aggregate fields from a valid saved result artifact when eligible.
- `tests/test_phase14.py` uses temporary synthetic fixtures only. No fixture is stored in a production data directory.

Blocked outcomes contain `blocker_ids`, messages, next actions, readiness metadata, and `estimate: null`. `save_calculation_result` rejects blocked outcomes, and serialized result paths reject raw-record fields.

## Calculation contract

The calculation function accepts an explicitly selected registered dataset, a verified definition, codebook-backed mappings, an approved calculation specification, approved survey-design metadata, validated input data, explicit boolean numerator/denominator masks, and an applicable weight. It does not infer response coding from variable names.

The implementation supports aggregate proportion and weighted-proportion point estimates. Missing mask responses are excluded and summarized. Numerator observations outside the denominator, duplicate observations under a rejecting policy, invalid or missing eligible weights, missing required columns, and zero denominators block the result. There is no unweighted fallback.

Confidence intervals and standard errors are not fabricated. If an approved specification requests them without an implemented and approved design-based variance method, the calculation is blocked. The current live project has no approved survey design, so no uncertainty estimate is reported.

Publication remains separate from analytical eligibility. A successful analytical calculation does not make an output publishable; disclosure review, terms, attribution, and publication approval must be recorded independently.

## Evidence and methodology

`FI-ACCESS-001` is still a candidate in `data/metadata/indicator_catalogue.json`. Its complete official definition, numerator, denominator, response categories, missing-value treatment, required variables, weight interpretation, and survey-design method have not been verified against `RWA-NISR-FINSCOPE-2024-v01`. The Phase 12 and Phase 13 records therefore do not authorize a real estimate.

The live status is analytical-ineligible and publication-ineligible. Public catalogue availability, a matching column name, a checksum, or a local file would not independently satisfy authorization or semantic evidence gates.

## Synthetic tests versus real analysis

The synthetic authorized fixture tests a weighted aggregate and returns an explicitly labelled `synthetic_test_data` result. It is not a Rwanda estimate and is not placed in the project data tree. The test suite separately covers missing/unregistered/out-of-scope sources, wrong release, authorization, mapping, schema, weight, invalid-value, missing-response, zero-denominator, numerator/denominator consistency, survey-design, quality, central eligibility, publication, blocked-calculation, and raw-record safeguards.

No real indicator estimate is present in this phase.

## Validation

Run these checks after metadata or code changes:

```bash
cd /home/dna/Projects/hackton/insight-rwanda
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
.venv/bin/python -m compileall -q app.py src app_pages scripts tests
.venv/bin/python -m pip check
git diff --check
```

The readiness script currently reports `phase14_status: blocked` and `phase14_calculation_status: blocked`. AppTest remains metadata-only for the entry point and existing pages; no browser/server test is claimed here.

## Next actions

1. Obtain the exact FinScope release and written project-specific permission through the official access process; record permitted processing and publication restrictions.
2. Register and independently review the release-matched questionnaire, codebook, and survey-design documentation.
3. Verify FI-ACCESS-001's complete definition, mappings, missingness, weight, design, and calculation specification; record quality acceptance and analytical eligibility in the existing metadata model.
4. Rerun the readiness script. Only if the central evaluator returns analytical eligibility may an aggregate result be calculated; publication still requires a distinct disclosure review.
