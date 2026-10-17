# Research visualizations: evidence gates and current limits

## Architecture

Research result figures reuse `analytics.insights`: it validates the existing Phase 14 aggregate/Phase 17 insight contract, including analytical eligibility, result validation, evidence-linked definition, scope, units, and publication status for public display. Reusable Plotly styling and the evidence-register status chart are in `ui/visualizations.py`. The Overview and Research Readiness pages chart only counts from the current validated evidence records; counts describe governance metadata, not survey observations or findings.

The Financial Inclusion page renders a result chart only through the existing Phase 17 verified-insight path. The Poverty Insights page remains an evidence-gated unavailable state because there is no approved poverty estimate schema/result. Geographic Analysis shows only a verified neutral boundary reference, and currently shows no map because no official boundary resource is registered and verified. It does not infer values or color areas.

## Supported chart contracts

- Single aggregate indicator summary: requires a verified insight, eligible aggregate result, definition, unit, scope, period, and publication eligibility for public use. A validated confidence interval is shown as an interval; no uncertainty is invented.
- Existing scope comparison: accepts only compatible verified insights under the Phase 17 comparison checks.
- Time series: `build_verified_time_series_figure` additionally requires an explicit verified temporal-comparability status and non-empty evidence references for every point. It preserves supplied period order and never infers comparability from labels. Confidence intervals must be valid and consistently present across the series or all absent.
- Grouped category comparison: `build_verified_grouped_comparison_figure` requires an approved comparison-group status and evidence, verified category mappings, same unit/period/population/geographic scope, and a complete matching category set for every indicator. No implicit harmonization occurs.
- Readiness evidence chart: counts are recomputed from the actual evidence-item list and label unknown status codes; an absent/malformed item list yields no chart rather than zero-valued findings.
- Data-quality page metadata chart: recorded file-format counts are shown only when the source inventory is current. This is inventory structure, not a data-quality score or a research result.

## Not currently supported for research findings

There is no approved bivariate aggregate schema for scatter plots, so the application does not draw relationship/scatter charts. There is also no verified, authorized geographic aggregate result available to pair with the missing official boundary resource. The current application therefore does not render choropleths. Phase 16 join and area-validation gates remain required; a future map needs a safely loadable validated aggregate artifact, verified boundary/version and code keys, exact join diagnostics, supported survey-domain method, disclosure review, and publication approval. Geographic readiness is not imposed on unrelated non-geographic analyses.

Financial inclusion and poverty values, categories, sample sizes, rankings, and statistical uncertainty are not populated from candidate catalogue text. Missing results stay unavailable, never zero. Descriptive outputs do not establish causal impact. No synthetic chart/demo mode is exposed in the application; synthetic fixtures exist only in isolated tests and cannot pass the production result path as real aggregates.

For percentage indicators, the chart uses the result's explicit reported percentage field; it does not graph a ratio such as `0.6` on a percentage axis. Missing unit-matched output values block the insight. Confidence intervals are displayed only when their recorded unit matches the indicator unit and the interval contains the point estimate.

## Accessibility and behavior

Plotly views use explicit titles, axis labels, visible count labels, readable hover templates, responsive container sizing, and accompanying explanatory captions. Status colors are paired with text labels. If there are no eligible research results, the relevant page retains its blocked/unavailable explanation instead of rendering an empty or placeholder result chart.

## Validation scope

`tests/test_research_visualizations.py` tests readiness-chart derivation from records, absent-state behavior, verified trend/grouped chart contracts, uncertainty integrity, synthetic/ineligible rejection, and page rendering. These are software tests (including in-memory test fixtures), not validation of Rwanda survey estimates, official source authorization, statistical correctness, or permission to publish.
