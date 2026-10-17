# InsightRwanda Methodology Template

This document is a template for the project methodology. It intentionally
contains no analytical results or invented values. Complete each section only
after the relevant source, code, and validation have been reviewed.

## 1. Research question and intended use

- Decision or user need:
- Target audience:
- Scope and exclusions:
- Relationship to the Financial Inclusion & Poverty Reduction track:

## 2. Data sources

For every source, document:

- source organization and dataset/publication name;
- survey or reference period;
- access date and authorization status;
- unit of observation;
- relevant questionnaire, codebook, or report;
- geographic coverage;
- provenance record and checksum, where applicable.

## 3. Data preparation

Document file readers, schema checks, type conversions, category mappings,
deduplication rules, joins, geographic crosswalks, and transformations. Record
which steps are reproducible from code and which depend on manual review.

## 4. Indicator definitions

For each indicator, record:

- indicator name and plain-language definition;
- numerator and denominator;
- population and unit of analysis;
- inclusion and exclusion rules;
- time period and geography;
- source variables and recoding rules;
- missing-value treatment;
- weighting and uncertainty treatment;
- known comparability limitations.

No indicator should be displayed in the application until this definition is
complete and the implementation has been validated.

## 5. Survey weights and design

Document whether weights are required, which weight is appropriate, and how
weights are applied. Record any known strata, clusters, finite-population
considerations, replicate weights, or design limitations. If the available
tools cannot fully account for the survey design, state that limitation clearly
and avoid overstating precision.

## 6. Missing data and data quality

Document structural missingness, nonresponse, special codes, invalid values,
outliers, duplicate records, and any imputation. Explain whether calculations
use complete cases, explicit missing categories, or another approved rule.

Include validation checks and their outcomes once they exist. Do not replace
unknown or unavailable values with invented estimates.

## 7. Uncertainty and statistical reporting

Document the method used for standard errors, confidence intervals, uncertainty
bands, or other reliability measures. State when uncertainty cannot be
estimated with the available metadata. Report denominators and relevant
suppression rules alongside estimates.

## 8. Geographic comparisons

Document boundary source, geographic level, naming and code matching,
boundary vintage, missing geographies, and any changes that affect comparison.
Explain how estimates are compared across districts, provinces, or time and
which comparisons are not valid.

## 9. Prediction and model evaluation

Complete this section only if a prediction feature is justified.

- Prediction target and decision context:
- Target authorization and observation period:
- Feature availability at prediction time:
- Leakage checks:
- Inclusion criteria and sample size:
- Train/validation/test or temporal/geographic split:
- Baseline model:
- Candidate models, including whether XGBoost is justified:
- Primary metrics and why they fit the task:
- Calibration, subgroup checks, and error analysis:
- Explainability approach:
- Reproducibility details and model version:
- Known limitations and appropriate use:

No model performance should be reported until these items are supported by
validated data and reproducible evaluation.

## 10. Limitations

Record limitations involving coverage, representativeness, survey design,
comparability, measurement, missingness, geography, access permissions,
uncertainty, model validity, and potential misuse. Distinguish observed facts
from interpretation and from future work.

## 11. Reproducibility and review record

- Code version or commit identifier:
- Source registry entries:
- Processing date:
- Environment and dependency versions:
- Validation checks run:
- Reviewer and review date:
- Publication decision:

## 12. Phase 4 indicator framework

The current candidate indicator catalogue and review rules are documented in
[docs/indicator-methodology.md](indicator-methodology.md) and
`data/metadata/indicator_catalogue.json`. All current entries are proposed or
blocked because verified codebook mappings, source authorization, survey-design
evidence, and domain review are not yet recorded.

