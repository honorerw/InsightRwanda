# Phase 6: Authorized data integration and indicator readiness

Phase 6 connects safe metadata to the dashboard. It does not authorize a
source, load microdata, or publish an estimate.

## Dataset registry

Register a candidate source in `data/metadata/dataset_registry.json`. Each
entry uses a stable `dataset_id`, a display name, a path relative to the
approved `data/` root, and a file format. Record the source organization and
permitted purpose only when documented. Keep defaults as `unverified`,
`analytical_eligibility: false`, and `eligible_for_publication: false` until a
reviewer records evidence.

The Data Quality page requires an explicit selection. Selection only displays
safe metadata and validates the registered path; it never loads, previews, or
profiles the source. Registry paths are rejected when they are absolute,
traverse with `..`, or resolve outside the approved data directory.

## Readiness checks

`insightrwanda.analytics.readiness.evaluate_indicator_readiness` is the
central service. It checks source authorization, verified codebook mappings,
approved definitions and methodology, required columns and value semantics,
survey weights and sampling design, validated geography and crosswalks when
requested, and publication permission for public output.

The result separates `analysis_eligible` from `publication_eligible` and
returns passed checks, blocked checks, safe messages, and safe documentation
references. Missing evidence keeps the result `blocked_pending_evidence`.
Passing a code path or test does not approve an indicator.

## Resolving blockers

1. Record written source authorization and the permitted processing purpose.
2. Attach the authoritative codebook or questionnaire mapping and confirm
   response-value semantics.
3. Record the approved numerator, denominator, population, exclusions, and
   methodology review in the catalogue.
4. Document the dataset-specific weight, strata, clusters, and variance plan.
5. Validate geographic identifiers and any boundary crosswalk before asking
   for comparisons.
6. Record a separate publication decision and disclosure-risk review before
   public display.

Until those steps are complete, dashboard pages show blocked or unavailable
states and no analytical result is fabricated.

## Verification

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -m compileall -q src app.py app_pages tests scripts
.venv/bin/pip check
git diff --check
```

Launch the dashboard with `streamlit run app.py`. No Git commit or push is part
of this workflow.
