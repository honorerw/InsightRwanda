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
- One-page, non-gated insight brief for every page (PDF + PNG) — committed copies in `docs/briefs/`; aggregate values only, no household records.
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

The current test suite contains 170 tests, including a modeling suite that verifies the leakage guard, grouped splitting, candidate evaluation, the end-to-end workflow on the real source and the page-surface artifact helpers (holdout scoring, threshold trade-offs, PR sweep, subgroup performance). A joint-source suite (`tests/test_joint.py`) verifies the zero-overlap linkage audit, equal-source weight rescaling, weighted correlations and cross-tabs, the leakage-free transport evaluation, the combined-dataset export contract and the pooled estimates on both real files. It exercises the supplied Stata file
as well as small synthetic fixtures for invalid weights, unexpected response
codes, duplicate identifiers, geographic inconsistencies, missing schemas,
filtering, source errors, publication gates, bootstrap intervals, income-band
context estimates, the official-poverty unlock contract and the ten one-page
briefs (content, weighting arithmetic, deterministic rendering, PDF/PNG validity
and identifier exclusion).

## Ask InsightRwanda AI Assistant

The floating **AI Assistant** button at the bottom-right of every page opens an
in-screen chat panel — no external website, no page reload. The panel keeps its
conversation in Streamlit session state, offers example questions, a loading
indicator, a **New conversation** action, and a **Close** button.

The assistant is **evidence-first**:

- The deterministic core (`research/assistant.py`) answers from the project's
  verified indicator definitions, calculation rules, documented limitations,
  quality checks, navigation and data-governance status. Numeric answers are
  computed live from the loaded survey records at the active lens, with the
  survey's household weight and visible denominators.
- It refuses household-level or personal requests and says plainly when
  information is unavailable or unverified; it never invents statistics,
  sources, intervals, geographic findings or research conclusions.
- The optional Groq layer (`research/assistant_llm.py`) can **only reword**
  an already-verified answer. It never chooses statistics, adds citations or
  changes a publication/authorisation gate. Every figure in both the question
  and the answer is replaced locally with a placeholder (`⟦Q1⟧` for the
  question, `⟦V1⟧`, `⟦V2⟧`, … for the answer) before transmission, and
  restored only if the returned wording preserves every figure and adds none.
  Questions containing an email address, key-like token or explicit identifier
  phrase are blocked.
- On a missing key, quota/rate limit, invalid key, timeout, network failure or
  a changed figure, the verified answer is shown unchanged. There are no
  automatic retries and no paid fallback provider.

### Enable Groq locally

1. Create an API key in the [Groq console](https://console.groq.com/keys).
2. Copy the tracked example and fill in your key:

   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   `.streamlit/secrets.toml` is git-ignored. Alternatively export the key:

   ```bash
   export GROQ_API_KEY="your-key"
   ```

3. Optionally set `GROQ_MODEL` (Streamlit secret or environment variable). The
   default is `openai/gpt-oss-120b`, a current production model on Groq.
4. Restart `streamlit run app.py`. The panel shows the active Groq model when a
   key is configured; otherwise it states that answers stay local.

### Configure the key on Render

In the Render dashboard open the service → **Environment** → add
`GROQ_API_KEY` as a secret environment variable (and optionally `GROQ_MODEL`),
then save and redeploy. Do not add the key to `render.yaml`, a committed `.env`
file or any source file. The app never logs or displays the key, and all
provider failures are reduced to safe status messages.

### Free tier and quotas

Groq currently offers a rate-limited free tier for developer accounts, but free
usage is **limited and not guaranteed**, and limits differ by model. Check the
**Limits** page in the Groq console for the exact allowance on your account;
do not assume unlimited requests. The app sets `max_completion_tokens=1200`, a
20-second request timeout, a 600-character question limit, a 40-message history
cap and a 12,000-character payload cap. It disables the SDK's automatic retries
so a failed request cannot silently consume the quota again, and it reports an
exhausted quota instead of promising unlimited free usage. No billing is
configured by the app.

Groq's data policy states that inference inputs and outputs are not retained by
default, though they may be logged for up to 30 days for reliability and abuse
monitoring unless the organisation enables Zero Data Retention. The assistant
sends only non-sensitive, already-displayed documentation, with every survey
figure redacted; raw records, identifiers, file paths, source inventory and
unpublished/restricted outputs are never transmitted. If that external sharing
is not acceptable for your deployment, leave `GROQ_API_KEY` unset — the
assistant continues to work entirely locally.

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
for every financial-inclusion indicator by the estimation layer
(`research/estimation.py`, covered by its own test suite) with an explicit note
that they are not survey-design standard errors. Labelled income-band context
estimates (EI-01…EI-03, from the embedded N11a_lbl/N12a_lbl band labels)
surfaced earlier as exploratory financial context on the Poverty insights page
and remain part of that layer and the page briefs: they are not
poverty rates. An official poverty estimation stays blocked behind a
code-enforced contract (`official_poverty_status`) until a documented poverty
line, poverty concept, welfare aggregate, variance documentation,
authorization record and publication approval are all supplied explicitly.

One-page insight briefs per dashboard page (PDF and PNG, one per page,
nine total; committed copies in `docs/briefs/`, regenerated with
`python scripts/build_briefs.py`). Briefs contain aggregate
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
