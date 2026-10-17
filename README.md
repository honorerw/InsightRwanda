---
title: InsightRwanda
emoji: 📊
colorFrom: blue
colorTo: cyan
sdk: docker
app_port: 8501
---

# InsightRwanda

InsightRwanda is a planned Streamlit decision-support prototype for the NISR
2026 Big Data Hackathon, focused on the **Financial Inclusion & Poverty
Reduction** track. Its intended purpose is to help users explore evidence about
financial access, poverty, and social-protection outcomes in Rwanda using
authorized NISR and other public data.

## Current status

Phase 1 established the project foundation and data-governance rules. Phase 2
added a conservative source inventory and explicit path-safe data loaders.
Phase 3 added aggregate data-quality profiling and an explicit preparation
pipeline. Phase 4 adds a reviewable indicator catalogue and generic calculation
primitives. Phase 5 adds a professional Streamlit application foundation with
explicit navigation, safe metadata integration, aggregate readiness views,
and a neutral geographic-boundary reference. Verified indicators and model
modules have not yet been implemented.

Phase 6 adds a metadata-only dataset registry and centralized indicator
readiness service. Dataset selection is explicit, but selection does not load
or authorize a source. Current registry entries remain unverified and are not
eligible for analytical or public output. See
[docs/phase6-readiness.md](docs/phase6-readiness.md).

Phase 8 adds reproducible source-verification and research-readiness reporting.
The workflow distinguishes discovered files from documented provenance,
authorization, codebook availability, geographic assets, analytical
eligibility, and publication permission. See
[docs/phase8-readiness.md](docs/phase8-readiness.md). Generate the metadata
reports with:

```bash
PYTHONPATH=src .venv/bin/python scripts/inventory_sources.py
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
```

These commands inspect approved metadata and file properties only; they do not
authorize sources, expose records, or create analytical estimates.

Phase 9 adds the controlled analytical loading and calculation boundary. It
reuses the central readiness service and refuses to load or calculate from the
current unverified registry entries. Verified mappings, approved calculation
specifications, data-quality acceptance, survey-design evidence, and separate
publication/disclosure review are required before a real result can appear.
See [docs/phase9-analytics.md](docs/phase9-analytics.md).

Phase 10 adds a metadata-only Research Readiness Evidence Center. The
validated register at `data/metadata/evidence_register.json` records missing,
provided-but-unverified, verified, rejected, and not-applicable evidence for
datasets, indicators, geographic resources, and publication review. The new
Research Readiness page computes counts and actionable blockers from that
register and the existing readiness report. It cannot approve sources or
publish results; current real datasets and indicators remain blocked. See
[docs/phase10-evidence-center.md](docs/phase10-evidence-center.md).

Phase 11 adds official-source reference tracking in
`data/metadata/source_verification.json` and codebook mapping validation for
catalogue entries. Public NISR and Access to Finance Rwanda references are
recorded as provided-but-unverified source evidence; they do not grant access
to local microdata or approve indicators. The Research Readiness page now
shows source references, mapping coverage, traceability, and grouped manual
actions. See [docs/phase11-source-verification.md](docs/phase11-source-verification.md).

Analytical results and prediction features are not yet verified; no prediction
feature has been implemented. Any future dashboard values must be produced from documented,
validated inputs and must show their source, data vintage, definitions, and
limitations. Prediction features will only be added if a legitimate target,
adequate data, leakage controls, and defensible evaluation design are
available.

## Planned technology

- Python
- Streamlit
- Pandas and NumPy
- Plotly
- Scikit-learn
- XGBoost only if the data and evaluation design justify it

The current `requirements.txt` is preserved. The Phase 5 foundation uses the
already pinned Streamlit and Plotly dependencies and does not add packages.

## Phase 5 application

From the project root, launch the application with:

```bash
streamlit run app.py
```

The application currently provides these navigation destinations:

- Main Dashboard: Overview, Financial Inclusion, Poverty Insights, and Geographic Analysis
- Data Management: Dataset Registry, Source Inventory, Data Quality, and Codebooks & Variables
- Research & Analytics: Indicator Catalogue, Variable Mapping, Statistical Analysis, and Research Methodology
- Governance & Reports: Research Readiness, Reports & Exports, Evidence & Provenance, and Methodology & Sources

The additional destinations are focused views over existing validated metadata.
Statistical Analysis and Reports & Exports remain explicitly blocked while no
indicator is analytically or publication eligible; they do not fabricate
estimates or export restricted data.

The app reads `data/metadata/indicator_catalogue.json` and the aggregate
`artifacts/source_inventory.json`. It does not discover or combine arbitrary
files under `data/mine/`, and it never displays row-level data. The Financial
Inclusion page has one explicit local-material path for the supplied
`../data/mine/dataset.dta` and its matching questionnaire; that
path produces clearly labelled exploratory aggregates only. It does not use
`dataset.csv`, external downloads, or any other source. The central readiness
and publication gates remain separate and unchanged. The geographic page
loads only the explicitly selected local boundary file and attaches no
analytical values to it. Missing or malformed metadata produces a visible
warning instead of crashing the application.

The Dataset Registry page reads the safe metadata registry at
`data/metadata/dataset_registry.json`. Choosing a registered dataset records
only a session-level selection and displays its authorization and documentation
state; it does not load the selected source. The readiness service keeps
analytical and publication eligibility separate.

### Application and hosting chrome

The application uses Streamlit's supported `client.toolbarMode = "minimal"`
setting in `.streamlit/config.toml`. This suppresses application-level
developer toolbar options such as rerun, clear-cache, and deploy controls while
preserving the explicit sidebar navigation. A local file-watcher status may
still be shown by Streamlit while a development server is processing changes;
it is not generated by this application. The project does not use CSS to hide
Streamlit controls.

Managed hosting environments may add their own Share, GitHub, Edit, or Manage
app controls around the application. Those controls are outside the Streamlit
page and this repository contains no provider-specific configuration for them;
they must be managed by the deployment provider. They are not evidence that the
application itself has added duplicate navigation or a second header.

Run the complete synthetic-only test suite with:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Compilation and dependency checks can be run with:

```bash
PYTHONPATH=src .venv/bin/python -m compileall -q src app.py app_pages tests scripts
.venv/bin/pip check
```

## Phase 2 commands

From the project root:

```bash
PYTHONPATH=src .venv/bin/python scripts/inventory_sources.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The inventory is written to the ignored path `artifacts/source_inventory.json`.
It contains no row-level survey values. See
[docs/data-loaders.md](docs/data-loaders.md) for loader usage and format
limitations.

## Phase 3 commands

Profile one explicitly selected source into an ignored aggregate report:

```bash
PYTHONPATH=src .venv/bin/python scripts/profile_source.py \
  --input data/approved/example.csv \
  --output artifacts/example.quality.json
```

Run the explicit preparation pipeline only with an approved or controlled
synthetic source configuration:

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_dataset.py \
  --input data/approved/example.csv \
  --output artifacts/example.prepared.csv \
  --authorization-status synthetic_test
```

See [docs/data-quality.md](docs/data-quality.md) for quality signals,
transformation limits, survey-weight review, and authorization boundaries.

## Phase 4 indicator framework

The candidate catalogue is stored at
`data/metadata/indicator_catalogue.json`, with the review methodology in
[docs/indicator-methodology.md](docs/indicator-methodology.md). Current
entries are proposed or blocked because source authorization, codebooks, and
verified variable mappings are not yet documented. No real indicator results
are produced by Phase 4.

## Planned features

- A clear overview of financial inclusion and poverty evidence
- Transparent, documented indicator calculations
- Geographic exploration using approved boundary data
- Comparisons across approved survey periods or population groups
- Methodology, provenance, and limitation views within the application
- An optional prediction or scenario view, gated by model validation

These are planned capabilities, not claims about currently available results.
The current dashboard is a foundation and intentionally shows empty or
blocked states until evidence, authorization, and methodology review are
complete.

## Submission and demonstration status

The application currently has no synthetic-statistics demo mode. Its judge
demonstration uses the real metadata-driven pages and their honest blocked
states; test fixtures are synthetic software tests only. Current analytical
and publication eligibility remain false, and no genuine Rwanda research
result is claimed. See [the Phase 21 submission assessment](docs/phase21-submission-readiness.md),
[demo script](docs/phase21-demo-script.md), and
[evidence index](docs/phase21-evidence-index.md). The local competition PDF
requirements are summarized there, but participant eligibility and official
submission compliance have not been verified.

The chart evidence rules and current visualization limits are documented in
[Research visualizations](docs/research-visualizations.md). Readiness charts
summarize actual evidence-register records; no Rwanda estimate or choropleth
is available until the applicable central analysis, geographic, and publication
gates pass.

The guided presentation flow, evidence-linked narrative behavior, filter
eligibility rules, and export restrictions are documented in
[Phase 22 research storytelling](docs/phase22-interactive-research-storytelling.md).

## Data governance

Files under the workspace `data/mine/` are treated as local source material
until source authorization, licensing, sensitivity, and publication status
have been reviewed. The Financial Inclusion page reads only the explicitly
named supplied FinScope CSV for exploratory aggregate calculations; it does
not expose rows or treat those results as official or publication-approved.
Tabular survey files may contain record-level identifiers, survey weights, or
other restricted information. They must not be committed to a public
repository or deployed application.

The repository should contain only approved code, documentation, metadata, and
sanitized aggregates or fixtures. Future derived data must be aggregated to a
safe level, checked for disclosure risk, and linked to a provenance record.
See [docs/data-governance.md](docs/data-governance.md) before adding data.

## Methodology

The planned statistical approach, indicator definitions, weighting decisions,
missing-data handling, uncertainty, geographic comparisons, limitations, and
model evaluation will be recorded in
[docs/methodology.md](docs/methodology.md). That document is currently a
template and contains no findings.

## Tests

Test dependencies are recorded in `requirements-dev.txt`:

```bash
pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

The suite covers the data layer, readiness and evidence gates, the local
material analysis, and every Streamlit page through `AppTest`.

## Development status

This project is not yet ready for deployment or public publication. Do not
upload raw source data, commit credentials, or present unverified statistics
as official findings.
