# Phase 11: Official source verification and codebook mapping

Phase 11 extends the Phase 10 Evidence Center with a source-verification
matrix and a controlled mapping-validation workflow.

## Source verification

`data/metadata/source_verification.json` records public references, the source
facts they support, and unresolved questions for registered and candidate
sources. It includes references researched from official NISR and Access to
Finance Rwanda pages. The current FinScope 2024 and EICV7 references are
`provided_unverified`: they support discovery of source identity, reports,
questionnaires, and high-level survey information, but they do not establish
that a local file is the same release, that microdata analysis is permitted,
or that a result may be redistributed.

Each source also carries separate evidence statuses for source-reference
discovery, documentation obtained, documentation review, source-information
verification, access authorization, analytical approval, and publication
approval. These dimensions are deliberately independent. A public URL or
available document cannot upgrade authorization, analytical eligibility, or
publication permission. Approval statuses are constrained by the validator:
analytical approval requires verified access authorization, and publication
approval requires verified analytical approval.

The matrix distinguishes:

- a public URL from an obtained document;
- a document from a reviewed document;
- source identity from local-file provenance;
- technical metadata from authorization; and
- a public report from permission to publish derived results.

Local CSV and Stata entries remain `missing` because their owner, release,
documentation, and access conditions are unknown. Candidate EICV7 has public
NISR references but is not a registered analytical dataset. Candidate RPHC has
no verified reference in the project.

## Codebook mappings

The existing indicator catalogue remains the definition source. Each entry now
supports `mapping_records`. Records must identify a registered dataset and
exact source variable, document its meaning and response coding, reference a
codebook section, define the eligible population and denominator, document
missing-value treatment, and carry an evidence reference and controlled
status. `validate_mapping_records` rejects unknown datasets, missing evidence
fields, duplicate source variables, and unsupported statuses.

`mapping_readiness` additionally checks that required verified variables are
present in an authorized schema. Schema presence is only a technical check;
it does not establish conceptual validity. Full catalogue mapping records
must contain a safe codebook reference, evidence reference, documented
meaning, response coding, eligible population, denominator, and missing-value
rule. The current catalogue contains no mapping records, so all seven
concepts remain unverified and blocked.

## Researcher action plan

The readiness report groups unresolved evidence into source acquisition,
authorization, codebook acquisition, variable mapping, survey methodology and
weighting, geographic resources, quality review, and publication/disclosure
review. Each item has a reason, next action, affected scope, and completion
criterion. A human reviewer must update the evidence register and source
matrix; the application has no approval button and cannot verify legal
permission, data ownership, or documentary contents.

## Reproducible reports

Regenerate the combined source and research-readiness artifact with:

```bash
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
```

The script reads registry, catalogue, evidence-register, source-matrix, and
safe inventory metadata. It does not download URLs, load `data/mine/`, inspect
microdata, or change eligibility flags. Official source pages must be reviewed
by the project owner before any reference or permission status is upgraded.

## Current limitations

No real dataset currently satisfies authorization, codebook mapping,
methodology, quality, survey-design, and publication requirements. No real
indicator is calculated. Geographic joins remain unavailable until a verified
identifier, boundary, crosswalk, and publication review are recorded.
