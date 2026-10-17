# Phase 15 — Statistical validation and quality assurance

## Outcome

Phase 15 adds independent statistical and result-integrity validation around the existing Phase 14 workflow. The live `FI-ACCESS-001` candidate remains blocked by the central readiness evaluator. Synthetic fixture tests validate software behavior only; they are not Rwanda estimates and are not saved in production analytical locations.

## Architecture and files

- `src/insightrwanda/analytics/validation.py` defines stable QA checks and aggregate `ValidationReport` objects. Checks use `pass`, `fail`, `blocked`, `not_applicable`, and `not_run`; no QA result can override central analytical eligibility.
- `src/insightrwanda/analytics/phase14.py` runs the QA checks after central readiness and before the production calculation, includes validation/provenance metadata in successful aggregate results, and validates result integrity before persistence.
- `src/insightrwanda/analytics/readiness.py` continues to own source, definition, authorization, survey-design, calculation-specification, and analytical-eligibility gates.
- `src/insightrwanda/ui/pages.py` distinguishes source readiness, calculation validation, analytical status, publication status, and synthetic software coverage on existing pages.
- `tests/test_phase15.py` contains deterministic temporary/in-memory fixtures and independent expected values.

## Formulas independently tested

For the weighted-proportion fixture, the expected reference is calculated directly as:

`sum(weight × affirmative numerator) / sum(weight × eligible denominator)`.

For weights `[2, 100, 1]`, numerator `[True, False, False]`, and denominator `[True, False, True]`, the independent expected value is `(2×1 + 1×0)/(2+1) = 2/3`. The test does not call the production calculation function to derive that expected value.

Tests also compare weight scaling (`[1,2,2]` versus `[10,20,20]`), an explicitly unweighted approved method, and a rounded one-third percentage (`33.3333` with the fixture's approved four-decimal rule). Missing mask responses are excluded according to the documented treatment; they are not recoded as negative responses.

## QA checks

The validation layer records stable identifiers, status, required input/evidence, explanation, analytical impact, and corrective action. It covers schema presence, boolean mask alignment, numerator/denominator consistency, duplicate policy, missing-response documentation, weight validity and aggregate diagnostics, non-finite values, positive weighted-denominator consistency, zero eligible denominator, precision metadata, and variance-method support.

No arbitrary domain thresholds were introduced. Valid response semantics, survey universes, and acceptable missingness remain codebook/domain-review responsibilities. A missing prerequisite is `blocked`; an input or integrity problem is `fail`; a non-requested uncertainty method is `not_applicable`; and checks prevented by central ineligibility are `not_run`.

## Survey design and uncertainty

The current implementation supports only the approved point-estimate paths already supported by Phase 14. It does not calculate standard errors, confidence intervals, p-values, or population totals. A request for uncertainty without an approved design-based variance implementation is blocked; no simple-random-sample substitute is used. Complex-survey strata, clusters, replicate weights, and variance methods must be documented and implemented before uncertainty can be reported.

## Reproducibility and artifact integrity

Successful aggregate results must carry dataset/release identifiers, indicator and definition version, mapping references, calculation-specification references, implementation version, input checksum, survey-design/variance metadata, validation outcomes, timestamp, limitations, and disclosure/publication status. Repeated fixture runs are compared on numerical and stable provenance fields; timestamps are intentionally allowed to differ.

`validate_result_integrity` rejects missing provenance and raw-record keys. `save_calculation_result` rejects blocked, incomplete, or unsafe results. The current live run has no `artifacts/phase14_result.json`; it has only the blocked status artifact.

## Dashboard and current eligibility

The Research Readiness page reports source-access readiness, definition review, analytical eligibility, calculation validation (`not_run` for the blocked live source), and publication eligibility separately. Financial Inclusion shows that synthetic QA coverage is software-only and that no real indicator finding is available. Data Quality distinguishes missing/unauthorized sources from validation checks that cannot yet run.

Current `FI-ACCESS-001` analytical eligibility is false and publication eligibility is false. The readiness report records 30 Phase 14 blockers. The exact release, authorization, codebook mappings, complete definition, weight interpretation, survey design, quality acceptance, and approved calculation specification remain unresolved.

## Validation commands and results

Executed from the project root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
.venv/bin/python -m compileall -q app.py src app_pages scripts tests
.venv/bin/python -m pip check
git diff --check
```

The full suite passed 137 tests, including the 10 focused Phase 15 tests. The readiness script reports `overall_status=blocked`, `analytical_eligibility=false`, `publication_eligibility=false`, and `phase14_blockers=30`. Compileall, `git diff --check`, and validation of all 9 metadata/artifact JSON files passed. Streamlit AppTest passed for all 17 entry-point/page files. `pip check` reports no broken requirements; its only output is the environment's non-fatal unwritable pip-cache warning.

No real-data statistical validation was performed because no authorized real observations are available.
