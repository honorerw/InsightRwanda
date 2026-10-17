# InsightRwanda Phase 3: Data Quality and Preparation

Phase 3 adds aggregate quality profiling and an explicit preparation pipeline.
It does not build indicators, merge surveys, train models, or claim any poverty
or financial-inclusion findings.

## Profile one selected source

The input and output paths are mandatory; the profiler never chooses the first
file in a directory or scans a dataset collection automatically.

```bash
PYTHONPATH=src .venv/bin/python scripts/profile_source.py \
  --input data/approved/example.csv \
  --output artifacts/example.quality.json
```

The report contains dimensions, column names and dtypes, missingness, exact
duplicate-row count for the selected DataFrame, duplicate-column names,
constant and near-constant heuristics, numeric summaries, candidate identifier
and weight warnings, authorization status, and limitations. It never includes
row values or identifiers. Reports are written only below ignored `artifacts/`
or `data/processed/` paths.

The duplicate-row operation is exact for the selected pandas DataFrame but may
require additional memory for wide data. This trade-off is explicit; callers
should profile one selected source rather than automatically profiling all
local files.

Missing values are descriptive facts, not automatic errors. Duplicate rows,
constant columns, candidate identifiers, and candidate weights are review
signals rather than automatic deletion or semantic conclusions.

## Prepare one selected source

Preparation requires an explicit output path and refuses to write into source
directories or overwrite an existing output. Unverified sources are refused by
default for record-preserving output. A controlled local test can explicitly
override that guard, but the result remains ineligible for publication:

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_dataset.py \
  --input data/approved/example.csv \
  --output artifacts/example.prepared.csv \
  --require-column household_id \
  --weight-column hh_wt \
  --authorization-status synthetic_test
```

Supported transformations are only explicit column renames and explicit casts.
No records are automatically dropped, deduplicated, imputed, joined, weighted,
or treated as outliers. Candidate identifier columns cannot be silently cast to
numeric types. Weight columns remain columns; applying survey weights requires
separate documented analytical code and domain review.

Each prepared output receives a companion `.metadata.json` report containing
the input/output paths, authorization status, dimensions, selected columns,
explicit transformations, and limitations. The report does not contain rows.

## Authorization and review boundaries

The profiler and preparation pipeline do not grant authorization. Current local
source files remain `unverified` unless documented evidence says otherwise.
Before analysis or publication, a domain expert must review source permissions,
codebooks, survey design, variable meaning, missing-value codes, weight choice,
geographic comparability, disclosure risk, and any proposed linkage. EICV and
FinScope sources are not linked by this phase.

## Missing values and survey weights

Profiles report missing counts and percentages without deciding whether missing
values are errors. Candidate weight columns are checked for missing, invalid,
non-finite, zero, and negative values. These are warnings for review, not
automatic corrections. The methodology must document the appropriate weight,
survey design, and uncertainty treatment before estimates are produced.

## Tests

Tests use only small synthetic fixtures:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

