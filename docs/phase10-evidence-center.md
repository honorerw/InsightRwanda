# Phase 10: Research Readiness Evidence Center

Phase 10 adds a metadata-only evidence register and a Research Readiness page.
The register is stored at `data/metadata/evidence_register.json` and is loaded
and validated against the current dataset registry and indicator catalogue.

## Status vocabulary

Each evidence item uses one of these statuses:

- `missing`: no supporting evidence has been recorded;
- `provided_unverified`: a reference has been supplied but independent review
  has not been recorded;
- `verified`: the evidence has been explicitly reviewed and accepted;
- `rejected`: the submitted evidence cannot support the requirement; or
- `not_applicable`: the requirement is documented as not applicable.

The application never changes an item to `verified`, grants authorization, or
approves publication. Verification is a manual metadata process owned by the
project's responsible reviewer. The register may contain references and
descriptions, but it must not contain credentials, personal identifiers, raw
records, or restricted source content.

## Readiness calculation

The existing `build_research_readiness_report` remains the source of truth for
technical and governance gates. Phase 10 adds the validated register's counts
and mandatory blockers to that report. A mandatory item is blocking unless its
status is `verified` or `not_applicable`. The report continues to require the
existing dataset authorization, provenance, documentation, mapping,
methodology, survey-design, geography, quality, disclosure, and publication
checks.

The evidence counts are not a quality score and do not measure statistical
validity. A provided document can remain unverified, and a structurally valid
file can remain unauthorized.

## Resolving blockers

For each blocker, obtain the authoritative evidence named in the next action,
review it outside the dashboard, then update the corresponding metadata record
with the evidence reference, reviewer, verification date, and status. Related
dataset and indicator IDs are validated when the register is loaded. Re-run the
research-readiness report after metadata changes:

```bash
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
```

No dashboard action approves a dataset, indicator, geographic join, or
publication output. After evidence is verified, the existing Phase 9
eligibility service still requires an approved definition, exact codebook
mapping, required columns, data-quality acceptance, survey-design evidence,
and any applicable geographic and publication safeguards.

## Current limitations

The current project register records three sources, but none has verified
provenance, authorization, codebook documentation, survey-design evidence,
quality acceptance, or publication permission. The seven catalogue concepts
remain proposed or blocked; no real variable mappings or calculations are
approved. No reviewed geographic boundary/crosswalk evidence or publication
disclosure decision is recorded. The Evidence Center therefore displays a
blocked state and actionable next steps rather than estimates.

## Audit scope

The report reads JSON metadata and safe file-path structure only. It does not
load or preview `data/mine/`, inspect row-level content, upload files, or
alter source datasets. The current source inventory timestamp and report
references are shown as audit context; a timestamp is not evidence of review.
