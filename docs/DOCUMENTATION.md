# InsightRwanda — Project Documentation

**Project:** InsightRwanda · Financial Inclusion & Poverty Research Analytics
**Context:** NISR 2026 Big Data Hackathon — Track 2 (Financial Inclusion & Poverty Reduction in Rwanda)
**Stack:** Python 3.14, Streamlit ≥1.40, pandas ≥2.1, NumPy ≥1.26, Plotly ≥5.18, groq ≥1.7 (optional AI wording)
**Current state at documentation time:** 170/170 tests pass; dashboard runs locally. Includes the estimation layer (interval estimates, income-band context estimates, official-poverty contract), the per-page briefs layer (one-page PDF/PNG renders), the real predictive-modeling layer (`research/modeling.py`) and the dedicated **Predictive insights** page. Recent repairs: `load_analysis_data` now catches `struct.error` (see §7), the About page is wired into navigation, and the pandas 4.0 `select_dtypes` deprecation warning is fixed.

> Verified at a recent audit: SHA-256 `5c183d0fdf9fbf02d170a5ed28e96fa112ea2318fea0ff6d9f8e95699f5bd7ae` · analysis version `financial_inclusion_135869b472e3`

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Repository Layout](#2-repository-layout)
3. [Architecture Overview](#3-architecture-overview)
4. [Module Reference — `research/`](#4-module-reference--research)
5. [Dashboard Reference — `app.py`](#5-dashboard-reference--apppy)
6. [Data Sources](#6-data-sources)
7. [Verification & Limitations](#7-verification--limitations)
8. [Governance Boundaries](#8-governance-boundaries)

---

## 1. Purpose and Scope

InsightRwanda is a Streamlit research and analytics application. It converts the supplied NISR Stata survey file (`data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta`) into a presentation-ready set of **weighted financial-inclusion indicators** and supporting research pages. This project is deliberately **explicit about research boundaries**: it does not fabricate an official poverty estimate, does not publish household-level records, and does not claim official statistical publication status.

### What this project does

- Loads the supplied Stata file **read-only** through a single documented pipeline (`research/data_pipeline.py`).
- Extracts a documented **94-variable analytical slice** from the original 2,442-variable source and derives labelled geographic fields, indicator columns and a resilience composite.
- Runs **structural data-quality checks** (schema, key uniqueness, weights, geographic code validity and consistency, value-code validity, missingness) and displays them in the app with explicit PASS/WARN/FAIL/INFO statuses.
- Calculates **six verified household-weighted indicators** (FI-01 to FI-06), each with a full definition, valid-response rule, source-variable mapping, method and stated limitations.
- Presents results across **eight Streamlit pages** with custom branded styling, filters, Plotly charts, indicator registry cards and a governance-gated Data Explorer.
- Maintains a **source profile** with SHA-256 hash, file size, row count, source-variable count and a code-derived `analysis_version` fingerprint for reproducibility.

### What this project explicitly does NOT do

- It does **not** assert an official poverty rate. No poverty line, welfare aggregate, sampling methodology, variance method, authorization record, or publication approval is present in the workspace.
- It does **not** expose household-level records or raw CSV export by default. Aggregate exports remain disabled until explicit authorization and publication approval records exist in the source profile.
- It does **not** modify, upload, or re-upload the original Stata file or the competition PDF. Both are read-only inputs.
- It does **not** impute missing values. Missing/invalid responses are excluded from each indicator denominator rather than treated as negative responses.

---

## 2. Repository Layout

```
InsightRwanda/
├── app.py                        # Streamlit dashboard (pages 01–08, ~890 lines)
├── research/                     # Analysis-only layer (no Streamlit imports)
│   ├── __init__.py
│   ├── data_pipeline.py          # Loading, enrichment, filtering, aggregation
│   ├── indicators.py             # Indicator definitions + weighted calculations
│   ├── quality.py                # Structural + analytical-slice quality checks
│   ├── modeling.py               # Resilience-band predictive workflow
│   ├── spss_pipeline.py          # Second-source SPSS loader + verified aliases
│   ├── joint.py                  # Pooled cross-source analysis + transport model
│   └── catalog.py                # Source profile, SHA-256, governance gates
├── tests/
│   ├── test_real_pipeline.py     # 13 real-source + synthetic-fixture tests
│   ├── test_spss_pipeline.py     # 10 tests incl. a synthetic .sav + real SPSS integration
│   └── test_joint.py             # 27 pooled-analysis, export-contract + transport tests
├── data/
│   ├── FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta # Supplied NISR Stata source (READ-ONLY input)
│   └── Rwanda FinScope 2020_Final Data.sav  # Supplied SPSS source (READ-ONLY input)
├── 2026 Hackathon Competition.pdf # Scope reference (READ-ONLY input)
├── requirements.txt               # streamlit, pandas, numpy, plotly, pyreadstat
├── README.md                      # Project-level summary + reproducibility record
└── docs/
    └── DOCUMENTATION.md          # This document
```

---

## 3. Architecture Overview

```text
            ┌───────────────────────────────────────────────┐
            │ data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta  (READ-ONLY Stata source)    │
            └───────────────────────┬───────────────────────┘
                                    │ pd.read_stata (94 analytical columns)
                                    ▼
            ┌───────────────────────────────────────────────┐
            │ research/data_pipeline.py                     │
            │  load_analysis_data()     → raw 13,994 rows   │
            │  enrich_analysis_data()   → +derived columns  │
            │  filter_analysis_data()   → dashboard lenses  │
            │  aggregate_weighted_measure() → explorer table│
            └───────────┬──────────────────────┬────────────┘
                        │                      │
data/Rwanda FinScope    │                      ▼
2020_Final Data.sav     │        ┌──────────────────────────┐
(documented subset)     │        │ research/quality.py      │
        │               │        │ run_quality_checks()     │
        ▼               │        │ → PASS/WARN/INFO/FAIL    │
┌───────────────────────┴───┐    └──────────────────────────┘
│ research/spss_pipeline.py │
│  load_spss_analysis_data   │
│  enrich_spss_analysis_data │
│  build_spss_profile()      │
└───────────┬───────────────┘
            │ (alias-mapped onto the master schema)
                        ▼                      ▼
        ┌───────────────────────┐    ┌──────────────────────────┐
        │ research/indicators.py│    │ research/quality.py      │
        │ INDICATORS registry   │    │ run_quality_checks()     │
        │ calculate_indicator() │    │ → PASS/WARN/INFO/FAIL    │
        │ calculate_by_group()  │    └──────────────────────────┘
        └───────────┬───────────┘
                    │
                    └───► all research modules feed into:
                                    │
                                    ▼
            ┌───────────────────────────────────────────────┐
            │ app.py (Streamlit presentation layer)         │
            │ Source: FinScope 2024 master or SPSS 2020 second     │
            │ Pages: Overview · Financial inclusion ·       │
            │ Poverty insights · Geographic insights ·      │
            │ Resilience lab · Predictive insights ·        │
            │ Data quality · Data explorer ·                │
            │ Methods & sources                             │
            └───────────────────────────────────────────────┘

            research/catalog.py  (parallel track)
              build_source_profile() → SHA-256, rows, variable count,
              governance status, analysis version fingerprint
              aggregate_release_allowed() → publication gate
```

### Key design decision

`research/` is deliberately free of Streamlit code. The **same functions** power the dashboard and the real-source tests, so analysis and presentation are independent. This is also what enables `test_real_pipeline.py` to verify indicator mathematics against hand-coded reference implementations.

### Data flow in `app.py::main()`

```python
PIPELINE_LOAD → PIPELINE_ENRICH → SOURCE_PROFILE (cached) → QUALITY_CHECKS
                     │
                     └── on error: st.error + st.stop()
```

---

## 4. Module Reference — `research/`

### 4.1 `research/data_pipeline.py`

Reproducible Stata loading and transformation. No UI code.

| Component | Purpose |
|---|---|
| `ANALYSIS_COLUMNS` | List of 94 documented analytical variables extracted from the 2,442-variable source (metadata + qf/q/e/g/h/i/j/k/n variable blocks). |
| `PROVINCES = {1:"Kigali", 2:"South", 3:"West", 4:"North", 5:"East"}` | Province code map (used on `a1`). |
| `DISTRICTS = {11:"Nyarugenge",…,57:"Bugesera"}` | 30-district code map (used on `a2`). |
| `URBAN_RURAL = {1:"Urban", 2:"Rural"}` | Setting map (used on `a6`). |
| `SEX = {1:"Male", 2:"Female"}` | Respondent sex map (used on `b2`). |
| `SourceLoadError` | Raised when a file exists but is not a readable Stata source with the required fields. |
| `yes(series, code=1)` | Returns nullable 0/1 indicator for a labelled yes code. |
| `any_yes(df, columns, code=1)` | Returns 1 when **any** component of a multi-part current-use question equals 1, but only when at least one component has a substantive (1/2) response. All-missing rows stay missing, not false. |
| `load_analysis_data(path)` | Reads only `ANALYSIS_COLUMNS` via `pd.read_stata(..., convert_categoricals=False)`, raises `FileNotFoundError` if the file is absent, maps province/district/setting/sex codes to labels stored alongside the loaded slice. |
| `enrich_analysis_data(frame)` | Creates derived indicator columns (see below) and the `resilience_score`/`resilience_band` composite. |
| `filter_analysis_data(frame, province, district, setting, respondent_sex)` | Applies dashboard filters; raises `ValueError` if a requested derived column is missing. |
| `aggregate_weighted_measure(frame, measure, dimensions)` | Builds a disclosure-safe weighted aggregate table with `records`, `valid_records`, `positive_records`, `weight_sum`, `estimate`. Never returns row-level data. |

#### Derived columns produced by `enrich_analysis_data`

| Column | Rule | Source |
|---|---|---|
| `active_access` | "yes" if any of `qf4_01..qf4_06` == 1 (substantive rows only) | qf4_01–06 |
| `mobile_money` | `qf4_05 == 1` | qf4_05 |
| `bank_use` | "yes" if any of `qf4_01,qf4_02` == 1 | qf4_01,02 |
| `sacco_use` | `qf4_06 == 1` | qf4_06 |
| `formal_own_name` | "yes" if any of `qf3_01..qf3_06` == 1 | qf3_01–06 |
| `emergency_fund` | `e9b == 1` | e9b |
| `emergency_difficult` | `e9c in {1,2}` | e9c |
| `income_pressure` | `e7 in {1,2}` | e7 |
| `financial_stress` | `e6 in {1,2,3}` | e6 |
| `owns_money` | `e2a == 1` | e2a |
| `saves_regularly` | `e2c in {1,2}` | e2c |
| `internet_access` | `c14_5 == 1` | c14_5 |
| `phone_ownership` | `f3 == 1` | f3 |
| `microinsurance` | `i4a == 1` | i4a |
| `social_safety_net` | `i9a == 1` | i9a |
| `has_pension` | `g11a == 1` | g11a |
| `resilience_score` | Mean of (`emergency_fund`, `owns_money`, `saves_regularly`, `social_safety_net`), skipna | derived |
| `resilience_band` | Cut of score into `Priority` (<0.40), `Watch` (0.40–0.69), `Resilient` (≥0.70), `Unknown` if score missing | derived |

---

### 4.2 `research/indicators.py`

Indicator definitions + weighted calculations. This is the "research contract" that the dashboard surface renders.

| Component | Purpose |
|---|---|
| `IndicatorDefinition` (frozen dataclass) | ID, title, definition, unit, population, valid_response_rule, source_variables, method, verification, limitations. |
| `IndicatorResult` | Definition returned with the estimate, numerator_n, denominator_n, weight_sum, valid flag and a note explaining the absence of survey-design standard errors. |
| `weighted_mean(frame, values, weight="hh_wt")` | Returns `(average, valid_n, weight_sum)`. Valid = value notna AND weight notna AND weight > 0 AND weight is finite. |
| `INDICATORS` | Registry of 6 defined indicators. |
| `indicator_value(frame, id)` | Builds the 0/1/NaN response series for an indicator, applying that indicator's valid-response rule before weighting. |
| `calculate_indicator(frame, id)` | Validates required columns exist; returns the full `IndicatorResult`. |
| `calculate_by_group(frame, id, group)` | Same calculation per group; used for dashboard breakdowns. |

#### Indicator registry (FI-01 … FI-06)

All indicators use positive, finite `hh_wt`. Missing, unexpected and non-substantive responses are **excluded** from each indicator-specific denominator — not silently treated as negative.

| ID | Title | Numerator rule | Valid-response rule | Source variables |
|---|---|---|---|---|
| FI-01 | Active formal financial access | Any of `qf4_01..qf4_06` == 1 | At least one substantive 1/2 response across the six components | `qf4_01–06` |
| FI-02 | Current mobile-money use | `qf4_05 == 1` | `qf4_05 in {1,2}` | `qf4_05` |
| FI-03 | Emergency fund coverage | `e9b == 1` | `e9b in {1,2}` | `e9b` |
| FI-04 | Emergency money is difficult to raise | `e9c in {1,2}` | `e9c in {1,2,3}` (99 = do-not-know excluded) | `e9c` |
| FI-05 | Income pressure | `e7 in {1,2}` | `e7 in {1,2,3,4}` | `e7` |
| FI-06 | Internet access | `c14_5 == 1` | `c14_5 in {1,2}` | `c14_5` |

Every indicator definition carries explicit `limitations` fields in the code (for example "not an official published rate", "does not establish fund adequacy", "not a poverty threshold", "does not measure affordability/quality").

---

### 4.3 `research/quality.py`

Structural and analytical-slice checks. These describe **data structure and coding integrity only**; they do not certify representativeness, fieldwork quality, or publication readiness.

| Check ID | Category | Purpose |
|---|---|---|
| `schema_required_columns` | Schema | All requested analytical variables are present (PASS/FAIL). |
| `row_count` | Schema | >0 rows are available. |
| `unique_household_key` | Integrity | `key` is unique (PASS/FAIL). |
| `household_weight` | Survey fields | All `hh_wt` values are present, finite and positive. |
| `geographic_codes` | Coding | Every `a1`/`a2` maps to the supplied province/district dictionaries (PASS/WARN/FAIL). |
| `district_province_consistency` | Consistency | `a2 // 10 == a1` for every row. |
| `core_missingness` | Completeness | Measured (not imputed) missingness on `qf4_05, e9b, e9c, e7, c14_5, b2, a1, a2` (INFO). |
| `core_value_codes` | Coding | Only allowed codes appear in the checked indicator variables (PASS/WARN). |
| `source_inventory` | Traceability | Source-variable count vs. analytical-slice count (PASS). |

`quality_summary(checks)` returns a `{"PASS": n, "WARN": n, "FAIL": n, "INFO": n}` dict used by the dashboard.

---

### 4.4 `research/modeling.py`

Real predictive-analytics workflow (scikit-learn 1.9). Task: predict the Priority resilience band (versus Watch/Resilient) from features that do not define it.

| Piece | Behaviour |
|---|---|
| `build_model_frame(frame)` | Assembles features/target; raises loudly if any target-defining column (resilience_band, resilience_score, emergency_fund, owns_money, saves_regularly, social_safety_net) is used as a feature — the leakage guard. Unknown bands and unusable weights are excluded. |
| `evaluate_candidates(frame)` | Group-stratified 5-fold CV (`StratifiedGroupKFold` on the respondent `key`): majority-class baseline vs logistic regression, decision tree (depth 5), Hist gradient boosting. All metrics carry `hh_wt` via `sample_weight`; deterministic per seed 42. |
| `train_final_model(frame)` | Selects by mean CV weighted F1 (baseline excluded), refits, and evaluates once on a held-out fold: weighted ROC-AUC, F1, precision, recall, accuracy, log loss, Brier, unweighted confusion counts, calibration table (5 quantile bins), permutation importance (AUC drop, 8 repeats), and a provenance dict (candidates, folds, seed, positive class, threshold, split rule, weight rule). |
| `predict_priority(record, values)` | Prediction for a composed household; unentered features fall back to training-typical values. |

| Page-surface helpers (added 2026-10-23 for the dedicated Predictive insights page) | |
|---|---|
| `holdout_artifacts(frame, record)` | Rebuilds the seeded held-out fold and returns scored rows (truth, probability, `hh_wt`, province/setting/sex) — the backing table for threshold and subgroup views. |
| `threshold_metrics(table, thresholds=(.3,.4,.5,.6,.7))` | Weighted precision/recall/F1 and predicted-Positive share at fixed thresholds. |
| `pr_curve(table, steps=19)` | Precision/recall pairs across a probability sweep for charting. |
| `subgroup_performance(table, by, min_n=150)` | Held-out metrics per subgroup; AUC gated on both classes present; cells below `min_n` flagged `Low evidence`. |

Real-data result reported by the app (seed 42, 5 folds, 13,994 usable records): selected model **Hist gradient boosting**; CV weighted F1 0.656 ± 0.010, CV weighted ROC-AUC 0.773 ± 0.011 (baseline: F1 0.000, AUC 0.500); held-out-fold weighted F1 0.648, ROC-AUC 0.762, Brier 0.200 against a 39.9% weighted base rate. All results are predictive associations on resampled rows — not survey-design standard errors and not causal claims.

### 4.5 `research/estimation.py`

Estimation layer (added 2026-10-19): interval estimates, income-band context estimates and the official-poverty unlock contract. No UI code.

| Component | Purpose |
|---|---|
| `INCOME_BAND_MONTHLY` / `INCOME_BAND_ANNUAL` (in `data_pipeline.py`) | Embedded Stata band labels (N11a_lbl / N12a_lbl) for `n11`/`n12`. |
| `CONTEXT_ESTIMATES` | EI-01 (≤3,000 Rwf monthly), EI-02 (irregular/seasonal monthly — 0 responses in this release, a structural zero, noted in the definition), EI-03 (≤15,000 Rwf annual). All weighted with `hh_wt`, 99/missing excluded. **Never called poverty.** |
| `weighted_bootstrap_ci(frame, id, n_boot, seed)` | Weighted nonparametric bootstrap percentile interval; deterministic per seed; note states it is NOT a survey-design standard error. |
| `calculate_context_estimate(frame, id)` | Point estimate with visible weighted population. |
| `context_weight_distribution(frame, column)` | Weighted band distribution on embedded labels, DK/refusal excluded. |
| `official_poverty_status(...)` | Code-enforced contract: lists exactly which of the six required inputs (poverty line, concept, welfare aggregate, variance documentation, authorization, publication approval) are missing. Nothing is inferred. |

### 4.5 `research/briefs.py`

One-page, non-gated insight briefs (added 2026-10-20): each of the nine dashboard pages can export a single-page PNG and PDF summary of its own aggregates.

| Component | Purpose |
|---|---|
| `build_page_brief(page, view, profile, checks)` | Builds the `PageBrief` (KPIs, narrative, caution panel, lens note, footer) for a named page from a loaded, enriched view. Unknown pages raise `ValueError`. |
| `build_all_briefs(view, ...)` | All nine briefs at once (used by tests and `scripts/build_briefs.py`). |
| `render_brief_png(brief)` / `render_brief_pdf(brief)` | Deterministic A4 @ 200 dpi renders via Pillow. The PDF embeds the same rendered page as the PNG, so brief text is an image, not selectable text. |
| `brief_filenames(brief)` | Stable names, e.g. `brief_overview.pdf` / `brief_overview.png`. |

Non-gated by construction: briefs contain only aggregate values produced by the existing estimators — no household identifiers, no raw records, no gated exports — and every brief repeats what its numbers cannot claim in a caution panel. The in-app brief export (`render_brief_export`, "Preview first" modal + PDF/PNG download pair) was removed from the UI in a later refinement; committed copies: `docs/briefs/` (regenerate with `python scripts/build_briefs.py`).

### 4.6 `research/spss_pipeline.py`

Second-source SPSS pipeline mirroring `data_pipeline.py`'s rules (added 2026-10-23; see §6.2 for source facts).

| Component | Purpose |
|---|---|
| `SPSS_COLUMNS` | The documented subset of the .sav file that is loaded — everything else stays out of the analytical frame. |
| `_RENAME` / `_ALIASES` | SPSS names → master-schema names; `_ALIASES` holds the label-verified concept aliases (QF5 current-use → `qf4_*`, `EF9 → e9b`). |
| `load_spss_analysis_data(path)` | `pyreadstat.read_sav` on the documented subset, empty-string→NaN masking, code maps for province/district/setting/sex, `head_sex` from `B0`. Raises `SpssLoadError` on undocumented shapes; never writes. |
| `enrich_spss_analysis_data(frame)` | Derived columns over the alias-mapped names using the master pipeline's `yes`/`any_yes` validity rules. Withheld components (resilience lens, financial stress, income bands, FI-04) are deliberately absent. |
| `build_spss_profile(path)` | Same `SourceProfile` structure as the master (`catalog.SourceProfile`, extended with `mapped_variables` / `psu_documented`) so every governance gate and Methods view works uniformly. |
| `SPSS_SUPPORTED` / `SPSS_WITHHELD` | Positive and negative capability contracts pages use for honest degradation. |

### 4.7 `research/catalog.py`

Source inventory, reproducibility fingerprint and governance gates.

| Component | Purpose |
|---|---|
| `SourceProfile` (frozen dataclass) | Holds `source_id`, `path`, `format`, `file_size_mb`, `source_sha256`, `analysis_version`, `rows`, `source_variables`, `analytical_variables`, `source_release`, `population_period`, `metadata_status`, `analysis_status`, `authorization_status`, `publication_status`, `documentation`, `notes`. |
| `build_source_profile(path, analytical_variables)` | Inspects the source (row count via `read_stata(columns=["key"])`, variable count via read-only iterator, SHA-256 of file bytes, code fingerprint). Does **not** modify the source. |
| `_sha256(path)` | Streaming SHA-256 of the actual file bytes. |
| `_analysis_version()` | SHA-256-based fingerprint of `data_pipeline.py`, `indicators.py`, and `quality.py` bytes, e.g. `financial_inclusion_135869b472e3`. Changes whenever relevant research logic changes. |
| `aggregate_release_allowed(profile)` | Returns `True` only when **both** `authorization_status` and `publication_status` start with "Approved". This is the gate used by the Data Explorer. |

Current profile status (defaults, no approvals supplied):

- `authorization_status = "Unknown: no authorization record supplied"`
- `publication_status = "Not approved: no disclosure/publication approval supplied"`
- → `aggregate_release_allowed()` returns `False`.
- `source_release` and `population_period` are `"Not documented in supplied materials"`.

### 4.8 `research/joint.py`

Pooled cross-source analysis (added 2026-10-25). The two supplied files share **no record key**, so this module never joins them; it stacks them as independent samples on the label-verified shared measures and keeps the source as a dimension.

| Component | Purpose |
|---|---|
| `linkage_audit(master, spss)` | Reports unique keys per file, the shared-key count (0 on the supplied files), and a composite-key check: pairs matching on province/district/age/sex plus the share that also agree on every jointly observed measure (31% on the supplied files — far below the near-100% a re-keyed sample would show, so it is evidence against linkage, not for it). |
| `build_joint_frame(master, spss, wave_years=None)` | Stacks the harmonized columns, sets `source`, `wave_year` (2020 for SPSS, empty for the undated master), `weight` (source weight) and `weight_share` (rescaled to sum to 1 per source, so pooling gives each file equal influence). Raises `JointFrameError` on missing columns. |
| `WAVE_YEARS` | The single documented place to date a file. The master's wave is `None`; no year is inferred from content. |
| `pooled_estimates(frame)` | Each of the seven shared measures by source, the gap in percentage points and the equal-source pooled figure, with valid denominators. |
| `weighted_correlation(frame, columns)` / `weighted_cross_tab(frame, row, column)` | Pairwise-complete weighted Pearson correlations and row-percentage cross-tabs. |
| `evaluate_transport(frame, target)` | Trains one non-leaking logistic model (demographics, household size, internet access, income pressure, emergency funds) four ways: within each source (out-of-fold), master→SPSS, SPSS→master, and pooled→each source. Reports weighted ROC-AUC, Brier, its base-rate reference and predicted/observed shares. Channel indicators that define the outcome are blocked by a leakage guard. |
| `build_combined_dataset(master, spss)` | Returns the single stacked, harmonized dataset (20 columns) with a deterministic hashed `record_id` instead of the supplied keys. Backs `scripts/build_combined_dataset.py`, which writes `data/derived/insightrwanda_combined.csv` + `.metadata.json` (source hashes, row counts, linkage audit, column notes). `data/derived/` is git-ignored: the rows are respondent-level records and are never published by the app. |
| `wave_note()` / `comparison_note()` | The exact caveats the UI repeats: one dated file only, and a source gap is not a time trend or a causal effect. |

### 4.9 `research/assistant.py` and `research/assistant_llm.py`

`assistant.py` is the deterministic answer engine behind **Ask InsightRwanda**. It resolves ordinary-language questions to the six verified FI indicators, simple-English definitions, calculation rules, documented limitations, data-quality checks, source references and page navigation, and returns an `AssistantAnswer` carrying the question kind, evidence references and a `grounded` flag. Numeric answers are calculated from the active lens with `hh_wt`; refusals, fallbacks and unsupported questions never carry invented evidence. User input is length-limited, treated as data (never as instructions), and household-level requests are refused.

`assistant_llm.py` is the **optional** Groq wording layer. It is disabled unless `GROQ_API_KEY` is configured, and its contract is deliberately closed:

| Guard | Rule |
|---|---|
| Eligible answers | Only grounded documentation kinds (`explain_indicator`, `indicator_catalog`, `indicator_methods`, `limitations`, `identity`). Source inventory, publication status, quality findings, page narratives, refusals and fallbacks are never sent. |
| Redaction | Every survey figure in the question and answer is replaced locally with `⟦Qn⟧` / `⟦Vn⟧`; indicator IDs and `Page NN` citations stay readable. Questions containing an email, key-like token or explicit identifier phrase are blocked. No DataFrame, record, identifier, path or exception text is ever included. |
| Restoration | The wording is accepted only when every placeholder appears exactly once and no new digits were introduced; otherwise the deterministic answer is returned unchanged (`guard_rejected`). |
| Transport | `groq` (official SDK), `openai/gpt-oss-120b` by default, 20-second timeout, `max_completion_tokens=1200`, `temperature=0.2`, short hidden reasoning on GPT-OSS models, SDK retries disabled (`max_retries=0`). |
| Failures | Missing key `disabled`; ineligible payload `blocked`; quota `rate_limited`; bad key `invalid_key`; timeout `timeout`; empty response `invalid_response`; any other failure `unavailable`. No paid fallback provider. |

**General-knowledge mode (`answer_general_with_status` / `GroqProvider.general`).** In addition to wording, the layer can answer questions the offline core has no verified evidence for (`question_kind="fallback"`). Only the user's typed question is then sent — never a survey figure, record, identifier or project metadata — with a fixed `GENERAL_GUIDANCE` prompt that instructs the model to never state, guess or compute any statistic about InsightRwanda's survey data, to refuse personal/household-level requests, and to treat the question as text rather than instructions. The same identifier block, 600-character question cap, 20-second timeout and error translation apply. Successes carry status `general` and are labelled in the UI as *“General AI answer — not from this survey's verified data”*; a privacy/length-blocked question is `refused` and never leaves the app; provider failures fall back to the deterministic answer with a plain status. |

---

## 5. Dashboard Reference — `app.py`

Streamlit presentation layer (~1,000 lines) with a custom brand styling system — Google-font stack (Inter for UI text, Lora for display/serif numerals, JetBrains Mono for labels, all with offline fallbacks), tamper-evident custom sidebar, hidden default header/footer/toolbar and a fully responsive CSS layout.

### Pages (via the custom sidebar button rail)

The sidebar nav is rebuilt as a labelled system: grouped numbered entries — **Evidence** (01 Overview · 02 Financial inclusion · 03 Poverty insights · 04 Geographic insights · 05 Resilience lab · 06 Predictive insights), **Governance** (07 Data quality · 08 Data explorer), **How it is built** (09 Methods & sources · 10 About the build) — where every entry number matches that page's own `0N /` eyebrow, followed by context cards (dataset status and reading guidance).

| Page | What it shows |
|---|---|
| **Overview** | Weighted KPI cards (Active formal access, Mobile money, Emergency buffer, Income pressure), 2 tabs: National signal (bar + resilience-lite mix donut) and Opportunity map (3 narrative signal cards). Model work has its own page. |
| **Predictive insights** | The full model readout as a first-class page: candidate-comparison CV table, selected-model holdout metrics + base rate, calibration table, permutation importance, holdout confusion counts, the composed-household prediction form, **threshold trade-off** (weighted precision/recall/F1 at 0.3–0.7 plus a precision-vs-recall sweep chart) and **subgroup performance** (held-out AUC/F1/recall per province, setting, respondent sex, with low-evidence flags). Delegates to `render_model_evaluation_tab` so the two surfaces share provenance. |
| **Financial inclusion** | Four KPI cards (FI-01 to FI-04), horizontal weighted bar chart of all six indicators, indicator-detail inspector (definition, calculation, source variables, limitations), full indicator registry dataframe, footer showing source variables vs loaded rows. |
| **Poverty insights** | Explicit status callout + "Exact blockers" table (Poverty concept / Welfare aggregate / Survey methodology / Authorization — all currently blocked). Non-poverty context metrics only (FI-04, FI-05) clearly labelled "not an official poverty measure". |
| **Geographic insights** | Active access by province (bar), 3-signal grouped bar (access / emergency / internet), district explorer table with decision cue (highest vs lowest access). |
| **Resilience lab** | Risk profile cards (Priority households, Watch list, Emergency difficulty, Financial stress), observed-capability profile bars, priority-by-setting chart, 3 action prompts (Buffer / Access / Protection). |
| **Data quality** | Quality summary metric cards, executed checks table, core-variable missingness chart, scope callout, and explicit "quality limitations" of what is outside the checks. |
| **Data explorer** | **Governance-gated.** If `aggregate_release_allowed(profile)` is `False`, shows a callout saying output is withheld and returns early. Otherwise offers measure selection, dimension breakdown and a weighted aggregate table + CSV download (only when publication status is Approved). |
| **Methods & sources** | Full source profile table, five-step evidence chain (Inspect → Load → Validate → Calculate → Explain), documentation list, governance boundary callout, weighted-methodology registry. |

| **About the build** (*Navbar entry: “About the build”, `render_about`*) | Product thesis (the challenge), stack overview (4 components), method-transparency cards (weighted estimates, resilience lens, data integrity), hackathon alignment table, footer. Numbered "10" in the page-eyebrow sequence. |

*(Previously `render_about` existed but was not wired into navigation; as of the 2026-10-19 fix it is a live nav entry.)*

### Shared UI helpers

| Helper | Purpose |
|---|---|
| `load_source_profile(path)` | `@st.cache_data` wrapper around `build_source_profile`. |
| `weighted_rate(frame, values, weights="hh_wt")` | Same validity rule as `research.indicators.weighted_mean`. |
| `weighted_group(frame, group, measure)` / `weighted_distribution(frame, category)` | Per-group weighted bar data + weighted category mix. |
| `has_data`, `filter_bar`, `section_head`, `metric_card`, `chart_theme`, `app_header`, `nav`, `page_intro` | Reusable UI primitives. |
| `filter_bar` | Province + district + setting + respondent filter shell, wrapped around `pipeline_filter_analysis_data`. |
| `lens_signature` / `lens_toast` | Describes the active lens and raises a quiet `st.toast` when it changes (added 2026-10-20). |
| `kpi_countup()` | Animate numeric `.metric-value` text from 0 to its value on scroll (silent fallback, `prefers-reduced-motion` respected; added 2026-10-20). |

### Ask InsightRwanda AI Assistant (panel)

A floating **AI Assistant** launcher (`key="ask_launcher"`) appears at the
bottom-right of every page and opens an in-screen panel (`key="ask_panel"`) —
no redirect and no page reload. The panel is a `@st.fragment`, so opening,
closing and chatting rerender only the widget. It shows a welcome message, the
conversation (`st.chat_message`), inline verified bar charts (chart questions
resolve to an FI indicator plus province/district/urban-rural group and render
the weighted shares with a numbers table), provenance captions, a
loading spinner, a 600-character question input, **Send**, **New conversation**
and **Close**, plus a short privacy footer. History is session-only (capped
at 40 messages); when the page/lens changes the panel inserts an explicit
context-change marker instead of mixing numbers from different views. A queued
question is processed once, preventing duplicate submissions.

Groq is optional. `_ask_provider()` reads `GROQ_API_KEY` from
`st.secrets` first and the environment second (model: `GROQ_MODEL`, default
`openai/gpt-oss-120b`), creates at most one client per session, and returns
`None` on missing/malformed configuration. `_ask_process` routes a fallback
question to `answer_general_with_status` when a provider exists and appends a
labelled general answer (`general: True`); when the general send fails, the
deterministic fallback is shown with a dedicated status caption
(`ASK_GENERAL_STATUS`). The UI labels AI-reworded answers as
AI-generated, names the model, reports how many figures were restored locally,
and gives a safe status message for every provider failure. With no key, the
panel says answers stay local and the deterministic answer is used unchanged.

### Modals and motion (added 2026-10-20)

Two native `@st.dialog` modals, opened via in-page buttons:

- **Explorer gate** (`explorer_gate_modal`, Data explorer → "Why is this withheld?") — the gate rule and current governance state.

Motion design: staggered card entrances (`metric-card exercise data-delay`, `chart-card`/`filter-shell`/`page-intro` CSS delays), all CSS-only, plus a global `@media (prefers-reduced-motion: reduce)` guard that disables every animation for users (and judges) who request it. No `data-testid` selectors are used for motion, so Streamlit internals can change without breaking the visuals.

### Predictive insights page (model readout)

The predictive workflow was moved out of the Overview into its own page (`06 / Predictive insights`, `render_predictive_insights`) with two analysis surfaces added on top of the shared `render_model_evaluation_tab` readout:

- **Threshold trade-off** (`render_threshold_tradeoff`): weighted precision/recall/F1 at thresholds 0.3–0.7 and a precision-vs-recall sweep across the probability range, computed on the deterministic held-out fold (`holdout_artifacts`).
- **Subgroup performance** (`render_subgroup_performance`): held-out weighted F1, recall and ROC-AUC (AUC only where both classes exist) split by province, setting or respondent sex, with cells below 150 held-out records flagged as low evidence (`subgroup_performance`).

**Explicitly not a poverty or eligibility model** — the page captions mark every figure as a predictive association on resampled rows.

The page inherits the Overview's lens filter behaviour (prefix `predictive`).

---

## 6. Data Sources

### 6.1 Master — `data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta` (Stata, READ-ONLY)

- **File:** `data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta` (Stata `.dta`, READ-ONLY input).
- **Rows:** 13,994 (households).
- **Source variables:** 2,442 (inventoried, not loaded).
- **Analytical slice:** 94 documented source variables plus derived columns.
- **SHA-256:** `5c183d0fdf9fbf02d170a5ed28e96fa112ea2318fea0ff6d9f8e95699f5bd7ae`.
- **Weights present:** `hh_wt` (household), `pop_wt` (population).
- **Metadata source:** embedded Stata variable/value labels (no external codebook supplied).
- **Not documented in the workspace:** source release, population period, sampling methodology, strata/PSU/variance design, poverty line, welfare aggregate, authorization record, publication approval.

### 6.2 Second source — `data/Rwanda FinScope 2020_Final Data.sav` (SPSS, READ-ONLY)

- **Rows:** 12,480 — the row unit is the **individual respondent** (`KEY` repeats across household members).
- **Source variables:** 1,314 (inventoried; a documented subset is loaded).
- **Loader:** `research/spss_pipeline.py` reads only its documented `SPSS_COLUMNS` subset via `pyreadstat.read_sav` and renames it onto the master frame schema — one source of coding rules (`yes` / `any_yes`) serves both sources, so no second interpretation of the codes can appear.
- **Verified aliases** (label-identical semantics): `QF5_01..05 → qf4_01/03/04/05/06` (current use; QF4 on this file means *registered in own name*, never conflated), `EF9 → e9b`, `C14A4 → c14_5`, `EF7 → e7`; geography/setting/sex/PSU (`A1`, `A2`, `A3`, `B2`, `NUMVILL`) map unchanged.
- **PSU** is documented on this source (`NUMVILL`) — unlike the master — but strata/variance documentation still is not.
- **Not reproducible on this source** (withheld, never imputed): the digital-bank channel (master `qf4_02`) — FI-01's union runs over the five present channels; `e9c`, `e6`, `e2a`, `e2c`, `i4a`, `i9a`, `g11a`, `n11`/`n12` — so FI-04, financial stress, three resilience-lens components, the resilience band and the predictive model are **not reproducible** here, and every page degrades to an explicit "not reproducible" card instead of approximating.
- **Cross-source agreement:** the Financial inclusion page has an expander that loads *both* sources through their own pipelines and applies the shared indicator rules to each side (no merging). On the real files: FI-01 92.0% vs 89.6%, FI-02 95.9% vs 94.6%, FI-03 21.3% vs 27.9%, FI-04 master-only, FI-05 80.2% vs 77.7%, FI-06 14.1% vs 19.5% — differences reflect the different question filters and row units, not errors.
- **Metadata source:** embedded SPSS variable/value labels (no external codebook supplied). Authorization and publication status remain undocumented, identical to the master file.

Real-indicator differences (row units differ) are surfaced in a cross-source agreement table on the Financial inclusion page rather than merged.

---

## 7. Verification & Limitations

### How to run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Real-source test suite:

```bash
python -m unittest discover -s tests -v
```

### Groq configuration (optional)

The assistant works with no key. To enable the wording layer:

1. Create a key in the [Groq console](https://console.groq.com/keys).
2. Locally, copy `.streamlit/secrets.toml.example` to
   `.streamlit/secrets.toml` and replace the placeholder, **or** export
   `GROQ_API_KEY`. The real `secrets.toml` is git-ignored. `GROQ_MODEL` may
   override the default `openai/gpt-oss-120b`.
3. On Render, add `GROQ_API_KEY` (and optionally `GROQ_MODEL`) under the
   service's **Environment** settings and redeploy. Never commit the key or put
   it in `render.yaml`.

Groq's free tier is rate-limited and limits vary by model; check the **Limits**
page in the console rather than assuming a fixed allowance. The app does not
promise unlimited free usage; it disables SDK retries, caps
output/payload/history sizes, and shows a clear message when quota is exhausted.
Groq's data policy states that inference inputs and outputs are not retained by
default, though they may be logged for up to 30 days for reliability and abuse
monitoring unless Zero Data Retention is enabled. For evidence answers only
figure-redacted, already-displayed project documentation is transmitted; for
general-knowledge answers only the user's typed question is sent. Never
transmitted: raw survey records, identifiers, source inventory, quality
findings or unpublished outputs. Deployments that cannot accept that sharing
should leave the key unset.

### Test suite status (current, 2026-10-26)

The assistant suites add deterministic routing/privacy tests, a stubbed Groq adapter suite and AppTest UI tests. Current total: **170/170 pass**. Earlier counts below are historical records.

26 tests total (13 original + 13 estimation tests). Executed again after the estimation layer was added:

- **Then extended to 39 tests** (13 brief tests added with the per-page briefs layer: content, weighted arithmetic, deterministic rendering, PNG/PDF validity, identifier exclusion). The earlier audit lines below are historical records of the states before that extension.

- **Result (historical audit, superseded by the estimation round):** `Ran 13 tests in 3.357s. OK`, exit code 0 — **13/13 pass, fully green.**
- **Previously failing (`test_source_errors_are_explicit`)** — root-cause tracked to `pandas.read_stata` raising `struct.error` on intentionally corrupted input; the exception tuple in `load_analysis_data` (`except (OSError, ValueError, EOFError, ImportError)`) did not include `struct.error`. Verified by direct reproduction, then **fixed** by importing `struct` and adding it to the caught exception tuple so corrupt inputs produce a clean `SourceLoadError` (matches the test's intended contract; no assertion was weakened).
- **Side effect of the fix:** the `analysis_version` fingerprint naturally changed to `financial_inclusion_f43dfd9a140b` (its design behaviour: it re-fingerprints whenever research logic changes). The README's audit record was synced accordingly; the previous audit value was `financial_inclusion_135869b472e3`.
- Additional polish applied in the same pass: `select_dtypes` updated to `include=["object", "str"]` to silence the pandas 4.0 `Pandas4Warning`, and "About the build" was wired into the sidebar navigation (previously dead code).

> **Status:** fully green — 170/170 tests pass (original suite + estimation + briefs + real predictive-modeling suite + page-surface artifacts + pooled joint-source suite + deterministic assistant, Groq adapter and AppTest UI suites). Latest analysis-version fingerprint: `financial_inclusion_3d668fd37080` (unchanged — the fingerprint covers data_pipeline, indicators, quality and estimation only).

### Notable interpretation limit

Because the workspace supplies no `psu`, `strata`, or variance/weight documentation, the project **does not display standard errors or confidence intervals**. `IndicatorResult.note` is explicit about this. All published numbers are descriptive weighted means only.

---

## 8. Governance Boundaries

The app distinguishes clearly between four different stages of data visibility:

1. **File existence** — the file being present is not treated as proof of authorization.
2. **Metadata inspection** — always allowed (variable labels, row count, SHA-256, variable count).
3. **Internal analysis** — allowed (weighted indicator calculation, filters, exploration of derived columns).
4. **Public publication** — **blocked** until both `authorization_status` and `publication_status` start with `"Approved"` inside the `SourceProfile`.

Concretely, `aggregate_release_allowed()` is the gate, and the Data Explorer is the only surface it controls today. Household-level records and raw CSV export are additionally suppressed by design until explicit authorization and an approved disclosure rule exist.

The AI assistant sits inside the same boundary. It answers from verified project
evidence only, refuses row-level requests, and the optional Groq path is
restricted to five documentation answer kinds whose survey figures are replaced
with local placeholders before transmission, plus a strictly separated
general-knowledge mode that can send only the user's typed question (clearly
labelled, never accepted as survey evidence). The model receives no filesystem,
shell, database or raw-survey access, and cannot execute Python or SQL. If an
answer kind's external-sharing permission is not established, the payload is
blocked and the deterministic answer stays local. The model can never change an
authorisation or publication gate.

### Reproducibility promise

- Source hash is computed from actual bytes, not from the file name.
- Analysis version is computed from current source of `data_pipeline.py`, `indicators.py`, and `quality.py`; any change to research logic changes the fingerprint.
- The source file is never modified.
- Quality-check output is reproducible via the cached source profile and the current indicator registry.
