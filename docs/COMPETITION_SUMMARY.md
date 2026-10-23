# InsightRwanda — Competition Summary

**Track 2 · Financial Inclusion & Poverty Reduction — NISR Big Data Hackathon 2026**

---

## The pitch (30 seconds)

Access to a bank account is not resilience. This prototype answers the sharper question judges care about: **who can absorb a shock, and where?** InsightRwanda loads the supplied household survey (13,994 records, 2,442 variables) read-only, extracts a documented 94-variable slice, and turns it into household-weighted, fully traceable indicators — showing decision-makers *where* financial access is broad but buffers are thin, and *which* districts and households to prioritise.

## What differentiates this build from a demo dashboard

1. **Every number is reproducible.** Indicators are recalculated from the source file through one documented pipeline; the source SHA-256 and a code-derived `analysis_version` fingerprint (`financial_inclusion_3d668fd37080`) are displayed in-app. Change the research logic and the fingerprint changes — tamper-evidence, not decoration.
2. **Indicators are a contract, not a chart.** Each of FI-01…FI-06 carries an explicit definition, valid-response rule, source-variable mapping, method and stated limitations, all surfaced on the dashboard itself.
3. **Honesty is the feature.** The Poverty page shows exact research blockers (no poverty line, no welfare aggregate, no variance methodology) instead of fabricating a rate. Denominators are visible; missing responses are excluded, never imputed or relabelled as "No".
4. **Governance is enforced in code.** Household-level records and exports stay locked until explicit authorization plus publication approval exist in the source profile — enforced by `aggregate_release_allowed()` and verified by the test suite.
5. **It estimates what it can — and refuses what it cannot.** Weighted bootstrap interval estimates accompany every financial-inclusion indicator (labelled explicitly as NOT survey-design standard errors), while a code-enforced contract (`official_poverty_status`) keeps official poverty estimation blocked until all six documented inputs are supplied. Indicator maths checked against hand-coded reference calculations plus bootstrap, income-band and contract tests, and a headless Streamlit walkthrough script renders all 10 pages, exits non-zero on any failure. Current suite: **62/62 tests OK**.

## Judging criteria alignment

| Criterion | This build |
|---|---|
| Problem relevance | Targets the access-vs-resilience gap: emergency buffers, liquidity stress, income pressure, digital exclusion |
| Data + methodology | Real NISR-labelled Stata data, household weights (`hh_wt`), denominators shown, weights validated finite/positive by automated checks; a second supplied source (FinScope 2020 SPSS, 12,480 respondents) mapped through label-verified aliases with honest per-page degradation on what it cannot support |
| Tech innovation | Transparent resilience composite, exploratory weighted prioritisation model cross-validated with accuracy/AUC (per-fold stability, confusion matrix, standardized-coefficient signs) and a district drill-down, tamper-evident reproducibility fingerprint, governance-gated explorer |
| Usability + design | Custom branded 9-page UI, filter lens (province → district → setting → respondent), plain-language insights, responsive layout |
| Tangible impact | Action prompts mapped to evidence: emergency-savings nudges, assisted digital rails (USSD/agents where internet access is thin), shock-responsive finance links |

## Verification record

- Unit tests: current total **62/62 OK** (real-source + synthetic-fixture coverage of weights, codes, keys, geography, filters, publication gate, bootstrap intervals, income-band context estimates, official-estimation contract, briefs, and the predictive-modeling suite: leakage guard, grouped splitting, candidate evaluation, end-to-end run on the real source + the page-surface artifacts: holdout scoring, threshold trade-off, PR sweep, subgroup performance)
- Headless UI walkthrough: all 10 pages render without exception under **both** supplied sources, with the SPSS source's degraded pages showing their honesty markers (`python scripts/walkthrough_app.py`)
- Data-quality checks on the real source: **0 FAIL** (schema, key uniqueness, weights, geographic code validity/consistency, value codes)

## Deliberate boundaries (why this is more credible, not less)

No official poverty estimate, no standard errors (no PSU/strata/variance metadata supplied), no household-level exports (no disclosure rule or authorization supplied). The app says exactly this on its own pages — the difference between a slide and an evidence chain.
