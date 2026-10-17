# Phase 8: Data-source verification and research readiness

Phase 8 provides a reproducible, metadata-only workflow for distinguishing
files discovered in the project from sources that are documented, authorized,
analytically eligible, or approved for publication. File presence, successful
parsing, or local access never grants permission.

## Rebuild the inventory

Review the approved `data/` scope, then run:

```bash
PYTHONPATH=src .venv/bin/python scripts/inventory_sources.py
```

The generated inventory records relative paths, formats, sizes, hashes, safe
structural counts, and conservative `unverified`/`false` defaults. It skips
symbolic links and never records rows, cell values, coordinates, or document
text. Do not place generated output under `data/`.

The dashboard compares the indexed relative paths with the current approved
data tree. A stale inventory is shown as stale and is not treated as current.

## Generate the readiness report

After reviewing the inventory and metadata files, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
```

The report is written to the ignored `artifacts/research_readiness.json` by
default. Use `--project-root`, `--inventory`, and `--output` for a controlled
fixture or another generated output path. Output paths are restricted to
`artifacts/` or `data/processed/`.

The report uses statuses such as `verified`, `unverified`, `missing`,
`present_unverified`, and `blocked`. It does not produce a readiness percentage or an
overall score. The overall result remains blocked while any required evidence
is unresolved.

## Registering and verifying a dataset

Add a dataset record to `data/metadata/dataset_registry.json` with a stable
ID, display name, normalized path relative to `data/`, and file format. Keep
the following fields explicit even when unknown:

- `source_organization`, `source_title`, `source_url`, and `acquisition_date`;
- `provenance_status`, `authorization_status`, `license_status`, and
  `documentation_status`;
- `integrity_sha256`, when an integrity reference has been reviewed;
- `analytical_eligibility` and `eligible_for_publication`;
- `outstanding_verification_requirements`.

Use `verified` or an authorization value only when documentary evidence has
been reviewed and recorded. A local file, inventory entry, or successful load
is not that evidence. Analytical eligibility and publication eligibility are
separate decisions; publication also needs disclosure-risk and release review.

## Codebooks and indicator mappings

For each candidate indicator, record the authoritative dataset, variable
names, response coding, numerator, denominator, population, exclusions,
missing-value treatment, weight and survey-design requirements, geography,
methodology approval, and evidence reference. A questionnaire is not assumed
to be a complete codebook, and similar variable names across surveys are not
treated as equivalent. Until the mapping and methodology are verified, the
catalogue entry remains proposed or blocked and the dashboard shows no value.

## Geographic assets

Boundary files are inventoried by metadata and, when explicitly selected,
validated structurally. Structural validity is separate from provenance,
licensing, identifiers, and permission to publish. A geographic join requires
validated keys, compatible coverage and vintage, and an approved crosswalk.
Boundary geometry alone never supplies poverty or financial-inclusion values.
When no reviewed boundary asset exists, Geographic Analysis remains in an
unavailable boundary-only state.

## Outstanding project state

The current registry entries remain conservative: provenance, authorization,
documentation, licensing, survey design, analytical eligibility, and
publication eligibility are unresolved. Candidate indicator definitions remain
unverified. The dashboard therefore reports blockers and next actions rather
than estimates, rankings, or readiness percentages.

The next review actions are to obtain authoritative source provenance and
terms, link codebooks and survey-design documentation, verify variable
mappings and definitions, validate geographic identifiers and crosswalks, and
record separate analytical and publication decisions.
