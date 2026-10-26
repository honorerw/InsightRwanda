# InsightRwanda

InsightRwanda is a Streamlit research and analytics platform for the NISR 2026 Big Data Hackathon, focused on Financial Inclusion & Poverty Reduction in Rwanda.

The application is connected to **two supplied sources**: the master `data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta` (Stata, 13,994 households, the FinScope 2024 wave) and the second source `data/Rwanda FinScope 2020_Final Data.sav` (SPSS, 12,480 individual respondents, the FinScope 2020 wave). Every page analyses **one combined dataset** that pools both waves as independent samples on the harmonized measures — no sidebar source selector; where a measure lacks a label-verified counterpart on one wave, its estimate is computed on the records where it is observed and never imputed. The two files share **no record key** (0 of 12,480 SPSS keys match a master key), so they are never merged: the pool keeps the source as a dimension and reports the source gap instead of a fabricated household link. It does not claim an official poverty estimate because the workspace does not include a documented poverty line, welfare aggregate, sampling methodology, variance method, authorization record, or publication approval.

## What is implemented

- Custom branded Streamlit sidebar and navigation with the default header, footer and toolbar hidden.
- Real Stata loading through `research/data_pipeline.py` and second-source SPSS loading through `research/spss_pipeline.py` (label-verified alias mapping onto the master schema; `pyreadstat`).
- A documented 94-variable analytical slice from the 2,442-variable source file.
- A **combined dataset** as the single analysis source with a per-page **Survey year** filter (2020 SPSS wave vs 2024 master wave), honest scope notes, and a cross-source agreement table (same indicator rules applied to both supplied files, no merging).
- A **combined view** (`research/joint.py`): a linkage audit that measures the zero key overlap (including a chance-level check on province/district/age/sex pairs), pooled estimates for the seven shared measures with an equal-source weight, a weighted relationship matrix, and a transport check that trains the same non-leaking model within each file, across files in both directions and on the pooled frame for both shared outcomes.
- Explicit wave/year handling: the master Stata file is supplied as the FinScope 2024 wave (release name) and the SPSS file as the FinScope 2020 wave (release and file timestamp; official fieldwork September-November 2019). `research/joint.py::WAVE_YEARS` is the single place where a documented year can be revised.
- **One combined dataset on disk**: `python scripts/build_combined_dataset.py` writes `data/derived/insightrwanda_combined.csv` (26,474 stacked rows, 20 harmonized columns) plus a metadata manifest with both source hashes, the zero-key-linkage audit and the column dictionary. Source keys are replaced by deterministic hashed record ids; `data/derived/` is git-ignored because the rows are respondent-level records.
- Structural data-quality checks for schema, row count, identifier uniqueness, weights, codes, geographic consistency and missingness.
- Verified financial-inclusion indicators using embedded Stata variable labels:
  - active formal financial access;
  - current mobile-money use;
  - emergency-fund coverage;
  - emergency liquidity difficulty;
  - income pressure;
  - internet access.
- Household-weighted estimates with visible denominators and source variables.
- Geographic comparisons using the supplied province/district identifiers.
- An explicit poverty-status page that reports blockers rather than fabricating poverty rates.
- Governance-gated aggregate data explorer; household-level preview and raw export stay disabled pending explicit authorization, publication approval and an approved disclosure rule.
- One-page, non-gated insight brief for every page (PDF + PNG) — download buttons in the app and committed copies in `docs/briefs/`; aggregate values only, no household records.
- A dedicated Predictive insights page: candidate comparison under group-stratified cross-validation, held-out scorecard, threshold trade-off analysis and subgroup model performance with low-evidence flags.
- Methods, source profile, governance status and evidence-chain pages.
- Real-source tests in `tests/test_real_pipeline.py` plus estimation, brief, and second-source SPSS suites (including a synthetic `.sav` fixture and a real 12,480-row integration test).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Run the real-source test suite with:

```bash
python -m unittest discover -s tests -v
```

The current test suite contains 117 tests, including a modeling suite that verifies the leakage guard, grouped splitting, candidate evaluation, the end-to-end workflow on the real source and the page-surface artifact helpers (holdout scoring, threshold trade-offs, PR sweep, subgroup performance). A joint-source suite (`tests/test_joint.py`) verifies the zero-overlap linkage audit, equal-source weight rescaling, weighted correlations and cross-tabs, the leakage-free transport evaluation, the combined-dataset export contract and the pooled estimates on both real files. It exercises the supplied Stata file
as well as small synthetic fixtures for invalid weights, unexpected response
codes, duplicate identifiers, geographic inconsistencies, missing schemas,
filtering, source errors, publication gates, bootstrap intervals, income-band
context estimates, the official-poverty unlock contract and the ten one-page
briefs (content, weighting arithmetic, deterministic rendering, PDF/PNG validity
and identifier exclusion).

## Reproducibility record

The supplied source is loaded read-only from `data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta`:

- rows loaded: 13,994;
- source variables inventoried: 2,442;
- analytical slice: 94 documented source variables, plus derived labels and indicators;
- SHA-256: `5c183d0fdf9fbf02d170a5ed28e96fa112ea2318fea0ff6d9f8e95699f5bd7ae`;
- analysis version at this audit: `financial_inclusion_3d668fd37080` (generated from the calculation, loading, quality-check and estimation code at runtime; previous audit values `financial_inclusion_f43dfd9a140b`, then `financial_inclusion_135869b472e3`).

The analysis version changes when relevant research logic changes. The source
hash is calculated from the actual file bytes, not from its filename or metadata.

## Verified indicator rules

All six current indicators use positive, finite `hh_wt` values. Missing,
unexpected and non-substantive responses are excluded from the indicator-specific
denominator; they are not silently treated as negative responses.

- FI-01 active formal financial access: any valid `qf4_01`–`qf4_06` response equal to 1, denominator rows with at least one valid 1/2 response.
- FI-02 current mobile-money use: `qf4_05 == 1`, valid `qf4_05` responses are 1/2.
- FI-03 emergency-fund coverage: `e9b == 1`, valid `e9b` responses are 1/2.
- FI-04 emergency money is difficult to raise: `e9c` in 1/2, denominator substantive 1/2/3 responses; code 99 is excluded.
- FI-05 income pressure: `e7` in 1/2, denominator valid 1/2/3/4 responses.
- FI-06 internet access: `c14_5 == 1`, valid `c14_5` responses are 1/2.

The project calculates descriptive, weighted estimates. It does not claim
official publication status or survey-design standard errors because the
workspace does not supply the required methodology and variance documentation.
Bootstrap interval estimates (nonparametric, weighted, seeded) are provided
for every financial-inclusion indicator with an explicit note that they are
not survey-design standard errors. Labelled income-band context estimates
(EI-01…EI-03, from the embedded N11a_lbl/N12a_lbl band labels) are reported
as exploratory financial context on the Poverty insights page: they are not
poverty rates. An official poverty estimation stays blocked behind a
code-enforced contract (`official_poverty_status`) until a documented poverty
line, poverty concept, welfare aggregate, variance documentation,
authorization record and publication approval are all supplied explicitly.

Every page also offers a one-page insight brief (PDF and PNG, one per page,
nine total; committed copies in `docs/briefs/`). Briefs contain aggregate
values only — never household records or gated exports — and repeat what their
numbers cannot claim. The PDF embeds the same rendered page as the PNG
(Pillow, 200 dpi), so brief text is an image, not selectable text.

## Research boundaries

The supplied file is structurally usable for the financial-inclusion slice, but source release/period details and survey-design variance metadata are not documented in the workspace. Rates are therefore descriptive, use `hh_wt`, and do not display standard errors. The resilience score is an exploratory prioritisation lens, not an official poverty or welfare model.

The original Stata file and competition PDF are read-only inputs. The application does not upload them, modify them, or expose household-level records by default.

The source has no supplied authorization record or publication approval. As a
result, the Data Explorer withholds aggregate tables and exports until both
approvals and a disclosure rule are recorded in the source profile. Metadata,
quality checks, documentation review and the verified internal analytical slice
remain available separately from publication eligibility.
