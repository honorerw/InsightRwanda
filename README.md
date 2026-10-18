# InsightRwanda

InsightRwanda is a Streamlit research and analytics platform for the NISR 2026 Big Data Hackathon, focused on Financial Inclusion & Poverty Reduction in Rwanda.

The application is connected to the supplied `data/dataset.dta` source. It does not claim an official poverty estimate because the workspace does not include a documented poverty line, welfare aggregate, sampling methodology, variance method, authorization record, or publication approval.

## What is implemented

- Custom branded Streamlit sidebar and navigation with the default header, footer and toolbar hidden.
- Real Stata loading through `research/data_pipeline.py`.
- A documented 94-variable analytical slice from the 2,442-variable source file.
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
- Methods, source profile, governance status and evidence-chain pages.
- Real-source tests in `tests/test_real_pipeline.py`.

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

The current test suite contains 13 tests. It exercises the supplied Stata file
as well as small synthetic fixtures for invalid weights, unexpected response
codes, duplicate identifiers, geographic inconsistencies, missing schemas,
filtering, source errors and publication gates.

## Reproducibility record

The supplied source is loaded read-only from `data/dataset.dta`:

- rows loaded: 13,994;
- source variables inventoried: 2,442;
- analytical slice: 94 documented source variables, plus derived labels and indicators;
- SHA-256: `5c183d0fdf9fbf02d170a5ed28e96fa112ea2318fea0ff6d9f8e95699f5bd7ae`;
- analysis version at this audit: `financial_inclusion_135869b472e3` (generated from the calculation, loading and quality-check code at runtime).

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

## Research boundaries

The supplied file is structurally usable for the financial-inclusion slice, but source release/period details and survey-design variance metadata are not documented in the workspace. Rates are therefore descriptive, use `hh_wt`, and do not display standard errors. The resilience score is an exploratory prioritisation lens, not an official poverty or welfare model.

The original Stata file and competition PDF are read-only inputs. The application does not upload them, modify them, or expose household-level records by default.

The source has no supplied authorization record or publication approval. As a
result, the Data Explorer withholds aggregate tables and exports until both
approvals and a disclosure rule are recorded in the source profile. Metadata,
quality checks, documentation review and the verified internal analytical slice
remain available separately from publication eligibility.
