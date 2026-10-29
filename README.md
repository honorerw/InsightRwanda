# InsightRwanda

[![CI](https://github.com/honorerw/InsightRwanda/actions/workflows/ci.yml/badge.svg)](https://github.com/honorerw/InsightRwanda/actions/workflows/ci.yml)

InsightRwanda is a Streamlit research and analytics platform for the NISR 2026
Big Data Hackathon, Track 2: Financial Inclusion & Poverty Reduction in Rwanda.
It turns two supplied FinScope survey files into traceable weighted descriptive
evidence, geographic comparisons, an exploratory resilience lens, and a local
evidence assistant.

The project is deliberately conservative: it does not fabricate an official
poverty rate, does not claim a causal effect or official trend, and does not
publish household-level records without governance approval.

## Current status

- Nine-page Streamlit dashboard.
- One combined analysis pool containing both supplied waves.
- Survey-year lens for 2020, 2024, or both waves.
- Six verified financial-inclusion indicators.
- Three descriptive income-context estimates.
- Transparent four-component resilience heuristic.
- Geographic comparisons and district drill-downs.
- Cross-source linkage audit, pooled estimates, relationship matrix, and model
  transport checks.
- Non-leaking predictive workflow with holdout, threshold, calibration, and
  subgroup diagnostics.
- Deterministic local Evidence Assistant with verified inline charts.
- Governance-gated aggregate explorer and downloads.
- Aggregate-only one-page briefs in `docs/briefs/` and reference screenshots in
  `docs/screenshots/`.
- 147 `unittest` test methods in the repository.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Run the complete test suite after installing dependencies:

```bash
python -m unittest discover -s tests -v
```

Other verification and generation commands:

```bash
python -m py_compile app.py research/*.py scripts/*.py tests/*.py
python scripts/walkthrough_app.py
python scripts/browser_render_check.py
python scripts/build_briefs.py
python scripts/build_combined_dataset.py
```

The browser checks require Chrome or Chromium. `websockets` is declared in
`requirements.txt` because the browser scripts communicate through Chrome's
DevTools Protocol.

## What the application does

### Dashboard pages

1. **Overview** — national weighted signal and the access-versus-buffer gap.
2. **Financial inclusion** — FI-01…FI-06 definitions, denominators, estimates,
   intervals, and cross-wave comparison.
3. **Poverty insights** — income/liquidity context and the blocked official
   poverty-estimation checklist.
4. **Geographic insights** — province and district comparisons plus drill-down.
5. **Resilience lab** — component-level resilience lens and action prompts.
6. **Predictive insights** — candidate comparison, held-out evaluation,
   thresholds, calibration, and subgroup performance.
7. **Data explorer** — governance-gated aggregate analysis.
8. **Methods & sources** — hashes, inventories, evidence chain, and limitations.
9. **About the build** — product thesis, analysis workflow, solutions, and
   evidence-based outlook.

The sidebar Survey year filter is applied once in `main()` before page rendering,
so pages, briefs, and assistant answers share the same scope. Page filters use the
shared province, district, setting, and respondent-sex filtering path.

### Evidence Assistant

The assistant is fully local and deterministic. It uses the indicator registry,
estimation rules, source profile, quality checks, page narratives, and the active
loaded frame. Numeric answers are computed with the same tested functions as the
dashboard. It can draw verified weighted indicator charts by province, district,
or urban/rural setting.

It refuses household-level, personal, unsupported, and unverified requests. User
text is escaped before display, conversation state stays in the Streamlit session,
and no API key, external model, network request, or third-party service is used.

## Data sources

### FinScope 2024 Stata source

File: `data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta`

- 13,994 household rows.
- 2,442 source variables.
- 94 documented source variables loaded for the analytical slice.
- Household weight: `hh_wt`; population weight: `pop_wt`.
- SHA-256: `5c183d0fdf9fbf02d170a5ed28e96fa112ea2318fea0ff6d9f8e95699f5bd7ae`.

### FinScope 2020 SPSS source

File: `data/Rwanda FinScope 2020_Final Data.sav`

- 12,480 individual respondent rows.
- `KEY` can repeat across members of one household.
- A documented subset is loaded with `pyreadstat`.
- Native fields are mapped only when embedded labels verify equivalent concepts.
- Current-use channels come from `QF5_*`; this file's `QF4_*` means registered in
  the respondent's own name and is not conflated with the master's current-use
  `qf4_*` module.
- `NUMVILL` is retained as a documented PSU field, but complete variance and
  strata documentation is not supplied.
- SHA-256:
  `552651916c60752ef360be7018f04c45adaea328aeb8a5762ede79c5c04d58f8`.

### Pooling and linkage rule

The files share no record key and are never joined. `linkage_audit()` reports the
zero key overlap and a composite-pair diagnostic. The source remains an explicit
dimension in every combined result.

Pooled estimates rescale each source's supplied weight to equal source mass. This
is an explicit exploratory choice, not an official combined survey weight. The
different row units—households in the Stata source and respondents in the SPSS
source—mean pooled values must not be presented as an official national trend or
causal change estimate.

## Analytical pipeline

```text
Stata .dta ──┐
             ├─> source loaders ─> enriched frames ─> combined analysis frame
SPSS .sav ───┘                                      │
                                                    ├─> quality checks
                                                    ├─> indicators/context estimates
                                                    ├─> geography/resilience/modeling
                                                    ├─> local evidence assistant
                                                    └─> Streamlit pages and briefs
```

There are two combined representations in `research/joint.py`:

- `build_combined_analysis_frame()` preserves the wider union of enriched source
  columns for dashboard pages and brief generation.
- `build_joint_frame()` retains the harmonized fields required for pooled
  comparisons, relationships, and transport modeling.

`build_combined_dataset()` writes a local respondent-level artifact to
`data/derived/insightrwanda_combined.csv` with deterministic hashed record IDs.
The `data/derived/` directory is Git-ignored because it contains respondent-level
rows; the application does not publish it.

## Verified indicators

All estimates require finite positive `hh_wt`. Missing, unexpected, and
non-substantive responses are excluded from the indicator denominator; they are
not silently treated as negative responses. Numerator and denominator counts are
visible in the dashboard.

| ID | Meaning | Valid response rule |
|---|---|---|
| FI-01 | Any active formal channel | at least one valid 1/2 channel response is 1 |
| FI-02 | Current mobile-money use | `qf4_05` is 1/2; estimate is the share equal to 1 |
| FI-03 | Emergency-fund coverage | `e9b` is 1/2; estimate is the share equal to 1 |
| FI-04 | Emergency money difficult to raise | `e9c` is 1/2/3; 1/2 is positive |
| FI-05 | Income pressure | `e7` is 1/2/3/4; 1/2 is positive |
| FI-06 | Internet access | `c14_5` is 1/2; estimate is the share equal to 1 |

Indicator definitions, source variables, methods, verification notes, and
limitations are maintained in `research/indicators.py` and surfaced in the app.

## Estimation, resilience, and prediction

The estimation layer provides seeded non-parametric bootstrap intervals. These
capture row-resampling variability only and are not survey-design standard errors.
Income-band estimates use embedded labels and are descriptive context, not poverty
rates.

`official_poverty_status()` keeps official poverty estimation blocked until the
workspace supplies a documented poverty concept/line, welfare aggregate,
equivalence rule, variance method, authorization record, and publication approval.

The resilience score is the mean of four observed binary capabilities: emergency
funds, owning money, saving regularly, and social safety net. Its `Priority`,
`Watch`, and `Resilient` bands are an auditable prioritisation heuristic, not a
welfare model.

The predictive workflow excludes target-defining variables, uses appropriate
grouped/stratified validation, attaches survey weights to fitting and metrics,
and labels all findings as associations. It is not an eligibility, poverty, or
causal model.

## Governance and privacy

The source profiles distinguish:

1. file existence;
2. metadata inspection;
3. internal analysis; and
4. public publication.

`aggregate_release_allowed()` requires both authorization and publication status
to begin with `Approved`. In the supplied workspace those approvals are absent,
so the Data Explorer returns before exposing aggregate tables or downloads.

Household-level rows and raw exports are not exposed. The application does not
modify or upload the original source files.

## Repository structure

```text
app.py                         Streamlit application and UI composition
research/data_pipeline.py     Stata loading, enrichment, filtering, aggregation
research/spss_pipeline.py     SPSS loading and verified aliases
research/indicators.py        FI-01…FI-06 registry and calculations
research/estimation.py        Bootstrap, income context, poverty contract
research/quality.py           Structural and coding checks
research/joint.py             Linkage, combined frames, pooling, transport
research/modeling.py          Resilience predictive workflow
research/briefs.py            Aggregate-only brief builders/renderers
research/assistant.py         Local evidence answer/chart engine
research/catalog.py           Profiles, hashes, governance gate
scripts/                      Build, brief, walkthrough, and browser helpers
tests/                        Unit, integration, modeling, assistant, UI tests
data/                         Read-only survey sources and ignored derived data
assets/                       Runtime logo asset
docs/briefs/                  Generated aggregate-only PDF/PNG briefs
docs/screenshots/             Reference UI screenshots
.streamlit/config.toml        Streamlit runtime/theme configuration
.github/workflows/ci.yml      CI compilation and unit-test workflow
requirements.txt              Runtime and verification dependencies
2026 Hackathon Competition.pdf Scope reference input
```

## Reproducibility

- Source files are loaded read-only.
- Source hashes are computed from actual file bytes.
- The analysis fingerprint is generated at runtime from every non-package module
  in `research/`, so changes to harmonization, indicators, quality, estimation,
  modeling, briefs, joint analysis, or assistant logic change the fingerprint.
- The combined source profile uses a deterministic SHA-256 digest derived from
  both complete source hashes and retains the originals in its notes/manifest.
- Run `python scripts/build_briefs.py` after research changes; it now uses the
  same combined enriched frame as the dashboard.

## Review findings and fixes

The project review found and fixed:

- brief generation previously used only the 2024 Stata source while the app used
  both waves;
- combined-frame construction was duplicated between the app and scripts;
- combined provenance used a concatenated value under a SHA-256 label;
- browser scripts used undeclared `websockets`;
- documentation contained stale source-selector, page-count, and test-count text;
- the analysis fingerprint omitted newer joint, SPSS, modeling, brief, and
  assistant modules.

These are now addressed in the research layer, scripts, requirements, tests, and
this README.

## Verification status

Passed during the review:

- `python -m py_compile app.py research/*.py scripts/*.py tests/*.py`;
- `git diff --check`;
- all 13 real Stata pipeline tests;
- all 13 estimation tests;
- all 13 brief tests;
- synthetic combined-frame and combined-profile provenance checks.

Full test discovery was attempted but could not complete in the review environment
because `streamlit` and `pyreadstat` were not installed. Install
`requirements.txt` and rerun the full command before deployment.

## Remaining gaps and next steps

### High priority

- Supply sampling, strata, PSU, non-response, calibration, and survey-variance
  documentation.
- Define and independently review the official poverty concept, line, welfare
  aggregate, equivalence scale, and variance method.
- Add a versioned authorization record, disclosure-control rule, and publication
  approval record; the current gate should remain closed until then.
- Obtain a statistician-approved estimand and harmonized weighting method before
  presenting pooled values as representative or longitudinal.

### Medium priority

- Pin dependencies with a tested Python version and lock/constraints file.
- Extend CI to run the Streamlit AppTest walkthrough and browser check when a
  browser is available.
- Obtain a citable external codebook, release note, sampling document, and
  fieldwork metadata to reduce semantic drift in aliases and wave labels.

### Low priority

- Add a tracked deployment manifest and health-check runbook covering hosting,
  runtime, data access, memory, secrets, and source-file updates.

Until these inputs are supplied, retain the current descriptive labels, source
separation, visible limitations, and closed publication gates.
