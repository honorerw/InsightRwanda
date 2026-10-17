# InsightRwanda Data Inventory and Loaders

Phase 2 provides explicit, path-safe loaders and a conservative source
inventory. Loading a file is not authorization to analyze, redistribute, or
publish it. Authorization and licensing must be documented before analysis or
publication.

## Run the source inventory

From the project root:

```bash
PYTHONPATH=src .venv/bin/python scripts/inventory_sources.py
```

The script writes `artifacts/source_inventory.json`, which is ignored by Git.
The inventory contains relative paths, formats, sizes, SHA-256 checksums,
empty-file flags, conservative sensitivity classifications, authorization and
publication defaults, duplicate checksum groups, and limited structural counts.
It does not include row values, coordinates, column values, or identifiers.

Duplicate files are reported by checksum and path. They are not deleted or
automatically consolidated.

## Use a specific loader

Use `PYTHONPATH=src` or install the package through a future controlled project
setup. Every loader requires an explicit file path below the approved `data/`
directory:

```python
from pathlib import Path

from insightrwanda.data.loaders import (
    load_csv,
    load_geojson,
    load_stata,
    load_xls,
    load_xlsx,
)

root = Path("/path/to/insight-rwanda")
csv_frame = load_csv(root / "data" / "approved" / "example.csv", project_root=root)
geojson_document = load_geojson(
    root / "data" / "approved" / "boundaries.geojson", project_root=root
)
```

The CSV loader protects identifier-like columns such as keys, IDs, codes, and
UUIDs from automatic numeric inference. Callers may provide an explicit dtype
mapping for other columns. The Stata loader disables categorical conversion and
protects identifier-like columns after loading.

XLSX requires `openpyxl`; legacy XLS requires `xlrd`. These readers are not
currently installed in the project environment, so the loaders return a clear
optional-dependency error rather than silently using an unverified fallback.
Basic Stata loading uses pandas. `pyreadstat` is deferred because it is not
currently installed and is not required for the loader’s basic operation; it
may be evaluated later for richer Stata labels and survey-design metadata.

## Validate selected data

Validation utilities report expected columns, duplicate column names, dtypes,
dimensions, and missingness counts. They do not return cell values. GeoJSON
validation checks the FeatureCollection and feature structure without exposing
coordinates or properties.

## Source, processed, and public data

- **Source data:** original files under `data/`, treated as unverified and
  potentially restricted. They remain local until authorization and licensing
  are documented.
- **Approved processed aggregates:** derived outputs created by reviewed code,
  with disclosure controls, provenance, denominators, definitions, and
  limitations recorded.
- **Public data:** only files that pass authorization, licensing, sensitivity,
  provenance, and publication review. A local file is not automatically public.

Tests use only small synthetic fixtures. No raw survey records are used as test
fixtures, committed, uploaded, or deployed.

## Run the data-layer tests

No package installation is required for the Phase 2/3 data-layer test suite.
Quality profiling and preparation details are documented in
[docs/data-quality.md](data-quality.md).

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

