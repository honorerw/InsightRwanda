# Phase 22 — Interactive Research Storytelling

## What is implemented

- Overview now contains a selectable eight-step judge walkthrough. It links to existing pages and describes the current blocked state; it does not alter readiness or suppress blockers.
- The Financial Inclusion chart path continues to consume only the Phase 17 insight produced from the central Phase 14 decision. If a public-eligible result exists, its narrative identifies the supplied research question (when recorded), definition, source and exact release, population, period, descriptive value, limitations, and unit-matched uncertainty when valid.
- Reusable filter helpers return choices only from results that already satisfy the Phase 17 analytical, validation, provenance, and intended-use checks. Applying a filter can only narrow that eligible set; an unsupported option fails closed. The UI displays selectors only where multiple verified choices exist. The current application has no eligible results, so no research filter or finding is shown.
- Result classifications are fail-closed: restricted, unknown, or otherwise non-authorized aggregate inputs cannot be normalized into verified insights. Blocked narratives identify blocker IDs and the next evidence needed.
- Plotly summary, trend, comparison, and grouped comparison figures remain behind existing result gates. Their method-specific comparability requirements are documented in [research-visualizations.md](research-visualizations.md).
- Reports & Exports has no download action. Export remains unavailable until publication eligibility and an explicit approved output specification are recorded.
- A reusable metadata-only export validator/payload builder is covered by tests. It rejects ineligible, restricted, synthetic, raw-record, and unspecified outputs and does not write files; the UI does not expose it while the live readiness state is blocked.

## Presentation flow

Use the Overview walkthrough, then open the linked existing pages in order: problem and value; architecture/data flow; provenance and authorization; indicator/method; actual eligible findings (currently none); geographic/statistical safeguards; reproducibility; and limitations/next evidence. The walkthrough does not constitute a separate research mode. Continue to show the blocked Research Readiness and export states.

## Evidence and interpretation rules

The insight constructor requires the aggregate result, exact definition, passing calculation and quality validation, provenance, analytical eligibility, and publication eligibility for public display. Filters derive options from these already-eligible insight records, not from candidate catalogue entries. Missing results are unavailable, not zero. Narratives are deterministic templates over the insight metadata; they do not infer causes or policy impact. Uncertainty is included only for a finite interval whose recorded unit matches the indicator unit and which contains the point estimate.

There is no verified result, no publication-eligible indicator, and no approved boundary/join input in the current project. Consequently, no genuine Rwanda research chart or narrative is produced. Synthetic fixtures remain isolated to tests and are not rendered by the application.

## Accessibility, exports, and limitations

Existing Plotly charts provide labels, units, period, hover detail, responsive width, and visible uncertainty when valid. The walkthrough is keyboard-selectable through Streamlit controls and keeps explanatory text visible. Status is conveyed in text as well as color. The current result API/page exposes only the FI-ACCESS-001 result path, so multi-indicator/category/period controls are dormant unless a future approved result collection supplies multiple eligible records. No scatter plot or choropleth is enabled without its required evidence contracts.

Exports are intentionally absent. No raw, restricted, synthetic, invalid, or merely analytically eligible output can be downloaded from the Reports & Exports page. The future export contract is metadata-only and requires an explicit approved output specification.

## Validation performed (2026-10-14)

- The repository state inspected before the final hardening changes had a 227-test full-suite baseline.
- Focused Phase 22 suite: 9 tests passed. The combined Phase 17, visualization, and Phase 22 regression suites ran 30 tests successfully.
- Final full suite: `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` ran 229 tests successfully. This includes the existing Streamlit AppTests and the Overview/Reports AppTests.
- Readiness report generation succeeded. It reported `overall_status=blocked`, analytical and publication eligibility false, Phase 14/17/18 blocked, zero verified geographic resources, and Phase 20 `not_configured`.
- Compile check passed; `pip check` reported no broken requirements (with a non-fatal pip-cache permission warning); `git diff --check` passed.
- JSON parsing passed for 12 metadata and artifact files.
- No Streamlit server/browser deployment check was performed; AppTest is the UI validation performed here.

These are software-contract tests using synthetic in-memory fixtures; they do not verify source authorization, statistical validity, official findings, deployment, or permission to publish. No result artifact or Rwanda estimate was produced.
