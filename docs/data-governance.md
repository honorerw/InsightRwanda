# InsightRwanda Data Governance

This document defines the minimum controls for using data in InsightRwanda.
It is a working policy for the project foundation, not a statement that any
current source file is approved for publication.

## 1. Source authorization

Before a source is used in the application, record:

- the source organization and dataset or publication title;
- the acquisition date and original location;
- the legal, licensing, or access terms;
- whether the source is public, restricted, licensed, or unclear;
- the permitted purpose and any required attribution;
- the responsible reviewer and review date.

NISR origin alone does not establish that a downloaded file may be redistributed
or used as public application data. When authorization or licensing is unclear,
the source remains local and restricted.

## 2. Sensitivity classification

Classify each source before processing:

- **Public and approved:** permitted for the intended repository and deployment
  use, with attribution recorded.
- **Public but review required:** apparently accessible, but redistribution,
  licensing, or disclosure conditions still need confirmation.
- **Restricted microdata:** record-level survey or administrative data, including
  files with identifiers, keys, detailed household attributes, or sensitive
  combinations of fields.
- **Unknown:** provenance or permissions are not established.

Files in `data/mine/` are treated as review-required or restricted by default.
The `.gitignore` rules specifically exclude raw tabular files and source PDFs
from normal version-control operations; this is a safeguard, not a substitute
for access control.

## 3. Raw microdata handling

Raw microdata must not be committed, uploaded, or deployed. It should remain in
an approved local or controlled storage location. Do not expose record-level
rows through Streamlit tables, downloads, logs, error messages, chart tooltips,
or cached objects.

Record-level keys and survey weights must be handled as sensitive metadata until
their release conditions and analytical role are confirmed. Do not attempt to
identify, re-identify, contact, or link individuals or households.

## 4. Safe aggregation

Only publish derived data after a review of disclosure risk. The review should
consider:

- minimum cell sizes and suppression rules;
- rare categories and potentially identifying combinations;
- geographic granularity;
- whether repeated filters can reconstruct suppressed values;
- whether weights or denominators reveal record-level information;
- whether downloads, cached data, logs, or temporary files contain raw rows.

Aggregated outputs must retain enough metadata to explain their population,
denominator, filter conditions, time period, weighting approach, and source.
Suppression and rounding decisions must be documented rather than silently
applied.

## 5. Provenance

Each approved source and derived dataset should have a provenance entry covering
its source path or identifier, checksum where appropriate, version or data
vintage, processing script, transformation date, reviewer, and publication
status. The planned registry is `data/metadata/source_registry.yml`.

Derived data must be reproducible from authorized inputs and documented code.
If raw inputs cannot be distributed, the repository should provide instructions
for authorized users rather than embedding those inputs in the repository.

## 6. Publication review

Before a file or result is placed in a public repository or deployed app, review:

1. authorization and attribution;
2. sensitivity classification;
3. aggregation and disclosure risk;
4. source and transformation documentation;
5. validation and reproducibility;
6. visible limitations and uncertainty;
7. absence of secrets, raw rows, cached records, and debug output.

The result of this review must be recorded. A file being present locally, or
being downloadable from a website, is not sufficient approval for publication.

The Phase 6 dataset registry is metadata only. A registry entry is not an
approval, and a successful path validation or file load is not authorization.
The dashboard requires an explicit dataset selection and shows conservative
defaults for authorization, analytical eligibility, codebook status, and
publication eligibility. Source authorization and permitted processing purpose
must be recorded from documentary evidence outside the UI.

## 7. Operational rules

- Never commit credentials, tokens, private keys, or local environment files.
- Do not use raw microdata in screenshots, demo exports, or public notebooks.
- Do not place raw data in Streamlit cache directories or generated artifacts.
- Prefer sanitized fixtures for tests and demonstrations.
- Report any suspected accidental exposure immediately and stop publication
  work until it is reviewed.

