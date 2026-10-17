# Phase 9: Verified data integration and indicator analytics

Phase 9 adds a controlled analytical boundary without changing the current
registry decisions. The production registry remains blocked because no local
dataset has verified provenance, authorization, codebook mappings, survey
design evidence, or publication permission.

## Eligibility gates

`insightrwanda.analytics.readiness.evaluate_indicator_readiness` remains the
central readiness service. The Phase 9 loading workflow enables its additional
evidence gates for:

- documented provenance, dataset documentation, and license or terms;
- approved numerator, denominator, missing-value, and calculation rules;
- codebook-backed mapping records for every required source variable; and
- indicator-specific data-quality acceptance.

The existing authorization, definition, required-column, value-semantics,
survey-design, geography, and publication checks remain active. Analytical
eligibility and publication eligibility are separate decisions.

## Controlled loading

Use `load_authorized_dataset` from
`insightrwanda.analytics.authorized` with one explicitly selected registered
dataset and one catalogue definition. It performs a metadata preflight,
validates the resolved source path inside `data/`, loads only after the
preflight passes, and evaluates the actual loaded schema before returning an
internal frame. Blocked and error results contain safe messages and never
contain source rows.

There is no automatic dataset selection or directory-wide source loading. The
current real registry entries fail the preflight and therefore cannot be
loaded for analytical calculation.

## Mappings and calculations

Approved catalogue definitions may include a
`verified_variable_mappings` list. Each mapping must identify the exact source
variable, a non-empty evidence reference, verified status, and response coding.
Variable names alone are not accepted. The caller must create explicit
boolean numerator and denominator masks from the verified mapping; the
calculation layer does not infer response codes or silently recode special
values.

`calculate_authorized_proportion` delegates to the existing proportion and
weighted-proportion primitives. It records non-sensitive reproducibility
metadata, excludes invalid weights without an unweighted fallback, and returns
a blocked non-numeric result when the source is not eligible. It does not
produce confidence intervals or claim design-based inference.

## Publication and disclosure

Analytical output remains separate from publication output. Call
`prepare_publication_aggregate` only after an eligible calculation exists and
provide an approved disclosure review and minimum-cell rule. Missing
permission, licensing, disclosure review, or a valid minimum-cell rule keeps
publication blocked. The publication result contains aggregate metadata only;
raw records are never exported.

## Geographic integration

`join_approved_geographic_aggregate` requires verified source and boundary
identifiers, a documented crosswalk, compatible level and dtypes, unique keys,
complete coverage, and the documented identifier matching method. It rejects
name-based inference, duplicate keys, missing keys, and unmatched coverage.
The dashboard retains its boundary-only/unavailable behavior because no real
validated geographic aggregate is currently available.

## Reproducing an eligible synthetic calculation

The isolated synthetic tests in `tests/test_phase9.py` demonstrate the full
controlled path without modifying production metadata or source data:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_phase9 -v
```

Synthetic fixtures are test-only and cannot appear in the dashboard. To use a
real source in the future, record documentary provenance, authorization,
terms, codebook mappings, methodology approval, survey design and weights,
data-quality acceptance, and—if applicable—validated geography and disclosure
review before changing any eligibility state.
