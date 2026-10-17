# InsightRwanda Phase 4: Indicator Framework

Phase 4 defines a reviewable indicator catalogue and generic calculation
primitives. It intentionally produces no real poverty, financial-inclusion, or
geographic findings.

## Catalogue status

The machine-readable catalogue is
[`data/metadata/indicator_catalogue.json`](../data/metadata/indicator_catalogue.json).
Every current entry is proposed or blocked. No indicator currently has a
verified variable mapping, documented authorization for the local source, or
publication approval.

Phase 6 evaluates these conditions through the centralized readiness service.
Analytical eligibility means the documented evidence is sufficient for the
intended internal calculation. Publication eligibility is a separate decision
that also requires explicit permission for the dataset and indicator. Neither
status can be inferred from a successful function, a local file, or a passing
synthetic test.

The catalogue distinguishes:

1. **Officially documented indicators:** supported by authoritative definitions,
   verified source variables, and documented methodology. None are registered
   in the current Phase 4 catalogue.
2. **Derived indicators from verified variables:** calculated from approved
   variables whose meanings and source methods are documented. None are
   registered yet.
3. **Proposed or blocked indicators:** useful concepts requiring a codebook,
   source authorization, survey-design review, or domain-expert decision. All
   current entries are in this category.

## Evidence required before calculation

Before an entry can become calculable, the project needs:

- source authorization and licensing evidence;
- an authoritative codebook or questionnaire mapping for every required
  variable and response category;
- numerator, denominator, eligibility, and missing-value definitions;
- the dataset-specific survey weight and survey-design documentation;
- a defensible aggregation and geographic-comparison method;
- domain review of interpretation and disclosure risk.

The presence of a column name, report filename, questionnaire, or similar schema
does not establish any of these facts. FinScope, EICV, RPHC, census, and other
surveys remain separate sources; this phase performs no household-level linkage.

## Generic calculations

`src/insightrwanda/analytics/indicators.py` provides reusable primitives:

- `calculate_proportion` accepts explicit boolean numerator and denominator
  masks, reports valid and excluded counts, and returns `None` for a zero
  denominator;
- `validate_weights` reports missing, invalid, non-finite, zero, negative, and
  positive-weight counts;
- `calculate_weighted_proportion` uses only valid finite non-negative weights,
  reports exclusions, and never falls back to an unweighted estimate;
- `assert_indicator_calculable` blocks proposed or unresolved catalogue entries.

These functions do not infer variable semantics, apply survey design, estimate
confidence intervals, establish representativeness, or authorize publication.
Their outputs are aggregate metadata and calculation status only.

## Numerators, denominators, and exclusions

Numerators and denominators must be defined before calculation. Missing masks,
ineligible observations, and invalid weights are counted as exclusions rather
than silently recoded. A zero denominator or zero weighted denominator produces
an explicit non-estimate status.

Missingness is not automatically treated as an error. Missing-value codes and
nonresponse require the dataset codebook and domain review. Weights are
dataset-specific and remain separate columns in preparation outputs until an
approved analytical specification says how they should be used.

## Limitations and outstanding decisions

No confidence intervals or design-based variance estimates are implemented in
Phase 4. National or district representativeness must not be claimed until
sampling strata, clusters, weights, and variance-estimation requirements are
verified and correctly handled. District boundary files alone do not support
district-level estimates.

The following decisions remain outstanding:

- which source files are authorized for analysis and publication;
- which codebooks and survey methodologies are available to the team;
- which financial-inclusion concepts have valid source variables;
- which official poverty definition is approved for this project;
- how survey weights and design information will be handled;
- whether any geographic comparison is statistically and legally appropriate.

## Tests

Run the full synthetic-only suite from the project root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The indicator tests cover proportions, weighted proportions, invalid weights,
zero denominators, missing values, blocked catalogue entries, reproducibility,
and input immutability. No local survey records are used.

