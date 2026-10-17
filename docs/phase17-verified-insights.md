# Phase 17 · Verified Analytical Insights and Evidence-Driven Visualizations

## Outcome

Phase 17 adds an evidence-linked insight boundary around the aggregate result
contract produced by Phase 14 and the geographic safeguards from Phase 16. The
current project remains blocked from producing a real Rwanda insight: the live
FI-ACCESS-001 candidate has no approved definition, verified mappings,
authorized source release, or eligible result artifact.

Synthetic fixtures are used only to test software behavior. They are labelled
as test data and are rejected by the real-research insight and dashboard
visualization paths.

## Architecture and result flow

`insightrwanda.analytics.insights` is the Phase 17 boundary. It consumes an
aggregate result and a versioned indicator definition; it never reads source
rows. `build_verified_insight` checks the result status, central analytical
eligibility, Phase 15 validation reports, aggregate-only shape, provenance,
definition/mapping evidence, scope, reference period, and uncertainty metadata
when the approved method requires it.

The insight carries a stable source-result identifier, indicator and definition
version, dataset and release, estimate, unit, scope, period, uncertainty,
limitations, evidence references, reproducibility metadata, and separate
analytical/publication status. It does not copy raw records.

`build_indicator_summary_figure` and
`build_verified_comparison_figure` return no figure for blocked, empty,
synthetic, incompatible, or publication-ineligible inputs. Comparisons retain
input order and do not create rankings. The dashboard uses the public-display
gate, so analytical eligibility alone cannot make a chart visible.

`interpret_verified_insight` is deterministic and descriptive. It explains
what the approved measure represents and states that the result does not
establish a causal policy effect, poverty-reduction impact, or policy
effectiveness.

## Eligibility and blockers

The layer uses the existing central readiness decision; it does not create a
Phase 17 approval flag. Typical blocker identifiers are:

- `source_result_missing` or `result_not_calculated`
- `central_analytical_eligibility`
- `calculation_validation` and `result_provenance`
- `indicator_definition_missing`, `definition_incomplete`, or
  `definition_provenance_missing`
- `definition_result_mismatch`
- `uncertainty_metadata_missing`
- `publication_eligibility`, `publication_status`, and `disclosure_status`
- `synthetic_result_not_for_real_research`

The Financial Inclusion page displays these blockers and explicitly states that
no verified insight or chart is available. Research Readiness reports insight
availability separately from source access, analytical eligibility, and
publication eligibility.

## Validation performed

`tests/test_phase17.py` independently exercises:

- traceable eligible aggregate construction;
- missing and malformed result references;
- synthetic-result separation;
- analytical versus publication gates;
- missing definition/provenance;
- scope, period, and required uncertainty checks;
- preservation of missing estimates rather than conversion to zero;
- blocked and empty chart behavior;
- compatible unsorted comparisons;
- deterministic non-causal interpretation.

Phase 17 does not introduce a new estimator. The numeric value is accepted
only from the approved Phase 14 aggregate result; chart tests independently
check that the supplied aggregate is carried to the figure without replacing
missing values or reweighting observations. Weighted-proportion behavior and
independent expected values remain covered by the Phase 15 validation suite.
No simple-random-sample variance, confidence interval, ranking, or population
total is introduced here. If the approved result requests uncertainty, the
insight gate requires the result's supported standard error and confidence
interval metadata and the summary chart renders the interval as an error bar.

Quality thresholds are not invented by Phase 17: the source result must carry
a passing Phase 15 quality report. A missing, failed, or unperformed report is
blocked. Geographic charts remain subject to the Phase 16 verified resource,
join, survey-design, and disclosure gates.

The fixtures are in-memory test objects. No synthetic result is written to a
production analytical artifact directory and no fixture is an official Rwanda
estimate.

## Current result and remaining actions

No real Phase 17 insight, chart, geographic comparison, or estimate was
produced. The current readiness artifacts report blocked analysis and
publication, no verified geographic resources, and no Phase 14 result
artifact. Human actions remain to obtain and review the authorized exact
release, terms, codebook/questionnaire, survey design, mappings, approved
definition, quality acceptance, and output disclosure/publication permission.

Software tests validate implementation behavior only. They do not validate
statistical validity of an unperformed Rwanda analysis and do not authorize
publication.

## Validation commands

The required project commands are run for this phase and their actual results
are reported in the handoff. A successful synthetic test suite must not be
read as evidence that FI-ACCESS-001 is currently analytically or publicly
eligible.
