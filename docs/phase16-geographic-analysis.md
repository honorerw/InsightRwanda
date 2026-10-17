# Phase 16 — Geographic analysis and survey-aware comparisons

## Outcome

Phase 16 adds an auditable geographic-resource registry, structural boundary
validation, conservative aggregate-to-boundary joins, and survey-aware area
comparison gates. The live project remains blocked: no boundary resource is
registered or present in the approved data scope, the dataset geographic
identifier and crosswalk are unverified, and FI-ACCESS-001 is not analytically
eligible. No geographic estimate, ranking, choropleth, or public map result was
produced.

Synthetic fixtures are used only in `tests/test_phase16.py`. They are labeled
synthetic test data and are not Rwanda boundaries or statistics.

## Architecture and files

- `data/metadata/geographic_resources.json` is the geographic resource registry.
  It currently contains an empty `resources` list because no official
  boundary resource is verified in the repository.
- `src/insightrwanda/data/geography.py` loads registry records and produces
  safe status summaries. Registration, local presence, provenance, licensing,
  permitted use, verification, and publication are separate fields.
- `src/insightrwanda/analytics/geography.py` validates registered resources,
  basic GeoJSON structure, identifiers, geometry coordinates, CRS metadata,
  explicit joins, survey-domain method support, variance support, disclosure,
  and publication gates.
- `src/insightrwanda/analytics/readiness.py` remains the central readiness
  evaluator. Geographic requests require both verified dataset geography and
  a verified geographic resource; publication remains a separate gate.
- `src/insightrwanda/ui/pages.py` derives Geographic Analysis and Research
  Readiness states from the registry, readiness report, and validation results.
- `tests/test_phase16.py` covers synthetic resource, join, method, disclosure,
  and artifact-integrity behavior.

## Resource and validation behavior

A registry entry does not establish that a boundary file exists, is authentic,
licensed, authorized, or approved for public visualization. The validator
requires an approved-scope file or explicitly labeled in-memory test fixture,
official source/provenance evidence, reviewed license and permitted use,
administrative level, boundary release, reference date, CRS, feature fields,
and unique identifiers.

The implementation performs safe structural GeoJSON checks, finite/non-empty
coordinate checks, expected geometry-type checks, missing/duplicate identifier
checks, and aggregate diagnostics. It never returns feature properties or
coordinates in validation reports. Fuzzy name matching and row-order matching
are not supported.

The current environment does not provide `shapely`, `geopandas`, `pyproj`, or
`fiona`. Therefore topological geometry validity is explicitly blocked rather
than claimed. No geospatial dependency was added.

Join diagnostics contain only counts and documented key names: aggregate and
boundary counts, matched/unmatched counts, duplicate-key counts, expected
cardinality, multiplicity status, and final row count. A join requires central
analytical eligibility, a successful validated aggregate, verified geographic
metadata, compatible levels/releases, explicit identifier keys, and one-to-one
cardinality.

## Survey-aware comparisons

Area comparison validation requires an approved survey-domain estimation method,
documented sampling design, point-estimate support, and a reviewed small-area
reliability rule. Standard errors and confidence intervals remain blocked unless
design-based variance estimation is explicitly supported by the approved
strata/cluster/weight method. Rankings additionally require an approved
multiple-comparison method. No naive grouped household estimate or
simple-random-sample uncertainty substitute is used.

Geographic disclosure requirements are mandatory. The implementation does not
invent a minimum sample-size threshold. Missing small-area, sensitive-combination,
geographic-detail, or export review remains blocked.

## Dashboard and current blockers

The Geographic Analysis page now shows registered resource records and their
verification/local-presence/publication states. With the current empty registry
it displays an unavailable state and does not draw a map. The Research Readiness
report distinguishes structural assets from registered resources and verified
crosswalks. Existing navigation and neutral boundary safeguards remain intact.

Current required human actions are:

- provide an official boundary resource through an approved channel;
- record its exact administrative level, release/vintage, reference date, CRS,
  identifier and name fields, source checksum, provenance, license, and
  permitted-use evidence;
- verify the survey geographic identifier and release-compatible crosswalk;
- obtain survey-statistician approval for domain estimation, reliability, and
  variance methods; and
- complete output-specific disclosure, attribution, and publication review.

No official geographic source was newly inspected or downloaded in this phase.
The repository metadata and evidence register were inspected; they record the
boundary and crosswalk requirements as missing, not as verified sources.

## Validation results

Executed from the project root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
PYTHONPATH=src .venv/bin/python scripts/research_readiness.py
.venv/bin/python -m compileall -q app.py src app_pages scripts tests
.venv/bin/python -m pip check
git diff --check
```

The full unittest suite passed 148 tests, including 11 focused Phase 16 tests.
The readiness script completed with `overall_status=blocked`, current inventory,
9 blocked requirements, 0 registered geographic resources, 0 verified geographic
resources, and geographic requirement status `missing`. Compileall and
`git diff --check` passed. Ten JSON files were validated, including metadata and
generated artifacts. Streamlit AppTest passed for all 17 entry-point/page files.
`pip check` reported no broken requirements; it emitted only the environment's
non-fatal unwritable pip-cache warning.

Analytical eligibility and publication eligibility are both false. No genuine
geographic analysis was performed, and no Phase 16 result artifact was written.
