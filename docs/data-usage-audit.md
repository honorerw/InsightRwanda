# InsightRwanda data-usage audit

Audit date: 2026-10-14

## Current implementation update

The historical audit below predates the project's explicit local-material
authorization. The current Financial Inclusion page reads exactly
`../data/mine/dataset.dta` for the authorized local aggregate view, with the
matching questionnaire as its definition reference. The historical formal
readiness and publication findings remain separate; they do not block this
local analysis.

This audit was performed against the filesystem that is available in the
workspace, not only against the historical registry. Source records were not
printed, copied, uploaded, or modified. The CSV inspection was limited to
file metadata, row/column counts, and header names. GeoJSON inspection was
limited to structure and property-key counts.

## Executive finding

The project is not currently using the supplied FinScope records to calculate
a Rwanda indicator. The records are present in the workspace parent directory
(`../data/mine/` relative to this repository), but the application accepts
source files only below this repository's `data/` directory. The registered
FinScope path is `data/mine/FinScope 2024 Rwanda.csv`, which is absent in the
repository.

Even if the file were placed at the registered path, the central readiness
evaluator would still block analysis. The registry and source matrix record no
project authorization, permitted processing purpose, exact-release codebook or
questionnaire review, verified indicator mapping, data-quality acceptance,
survey-design approval, or publication approval. Possession of the file and a
public FinScope report do not establish those permissions or meanings.

Accordingly, this audit produced no Rwanda estimate and no result artifact.
The correct safe outcome is a blocked state, not an unweighted calculation
based on similarly named variables.

## Materials discovered outside the repository

The following files were found under `/home/dna/Projects/hackton` and are
reported with paths relative to the repository. They are not inside the
application's approved data boundary.

| Relative path | Format and size | Inspection outcome | Apparent role | Application use |
| --- | --- | --- | --- | --- |
| `../data/mine/FinScope 2024 Rwanda.csv` | CSV, 101,291,012 bytes | Readable; 13,994 data rows and 2,442 columns; header inspected | FinScope survey records | Not used. Outside `insight-rwanda/data/`; registry is unverified and the indicator has no mapping. |
| `../data/mine/dataset.csv` | CSV, 101,291,012 bytes | Readable; same 13,994 × 2,442 schema; SHA-256 is identical to the named FinScope CSV | Duplicate copy of the same tabular source | Not used for the same path, authorization, and mapping reasons. It is not a second independent sample. |
| `../data/mine/FinScope 2024 Rwanda.xlsx` | XLSX, 49,045,258 bytes | ZIP package readable; one worksheet named `Sheet1`; the project `openpyxl` reader is not installed, so cell/schema loading was not completed | Spreadsheet copy of survey records | Not used. Outside the approved boundary and no supported reader is installed. |
| `../data/mine/dataset.dta` | Stata, 50,835,916 bytes | File type is recognized as Stata; no application load was attempted because the source failed authorization/path gates. Record readability and labels were not treated as verified | Statistical-file copy of survey records | Not used. Outside the approved boundary and unverified. |
| `../data/mine/Finscope-Final-Report__10_07_2024-1.pdf` | PDF, 6,354,752 bytes, 77 pages | Text extraction and methodology/report sections inspected; no raw records | Public FinScope report/documentation | Not consumed by analytical code. It supports high-level context only; it is not the exact codebook or a project authorization. |
| `../data/mine/search-10-12-26-015354.csv` | CSV, 14,768 bytes, 76 data rows and 9 columns | Header/schema inspected; fields are catalogue/search metadata (`id`, `surveyid`, `titl`, `nation`, dates) | Catalogue/search export, not survey observations | Not registered or consumed. It does not supply indicator variables or permission. |
| `../2026 Hackathon Competition.pdf` | PDF, 38,688 bytes, 5 pages | Text extracted; Track 2 and data-use/submission language inspected | Competition brief | Not consumed by calculations. It establishes the problem context, not access to restricted microdata. |
| `../data/geo/rw_districts_adm2.geojson` | GeoJSON, 6,322,416 bytes | Parsed as FeatureCollection with 30 features; property keys inspected | District boundary reference | Not used. It is outside the repository and no geographic resource is registered or authorized. |
| `../data/geo/rw_districts_adm2_simplified.geojson` | GeoJSON, 289,074 bytes | Parsed as FeatureCollection with 30 features; property keys inspected | Simplified district boundary reference | Not used for the same provenance/licensing/registration reasons. |
| `../data/geo/rw_provinces_adm1_simplified.geojson` | GeoJSON, 132,231 bytes | Parsed as FeatureCollection with 5 features; property keys inspected | Simplified province boundary reference | Not used for the same provenance/licensing/registration reasons. |
| `../data/mine/FALL 2.mp4` | MP4, 1,335,997,933 bytes | Container type identified; no video frames or records inspected | Video/demo material | Not research data and not consumed. |
| `../data/mine/.~lock.Finscope-Final-Report__10_07_2024-1.pdf#` | Lock file, 65 bytes | Identified as an editor lock artifact; contents not used | Temporary application artifact | Not research data and not consumed. |

The two CSV copies are byte-identical. They must not be treated as separate
datasets or merged. No file was moved into the repository or changed during
this audit.

## Materials inside the repository

The repository's `data/` directory currently contains only five JSON metadata
files:

| Relative path | Role | Inspection outcome |
| --- | --- | --- |
| `data/metadata/dataset_registry.json` | Three registered candidate datasets | Parsed; all three have unverified authorization, documentation, quality, and analytical eligibility. |
| `data/metadata/source_verification.json` | Source identity/access/documentation matrix | Parsed; FinScope identity is provided through a catalogue reference, but access authorization, exact documentation review, analysis approval, and publication approval are missing. |
| `data/metadata/evidence_register.json` | Evidence requirements and statuses | Parsed; FinScope provenance is provided-but-unverified; authorization, codebook, questionnaire, schema, survey design, quality, and license items are missing. |
| `data/metadata/indicator_catalogue.json` | Candidate definitions | Parsed; `FI-ACCESS-001` is `proposed_pending_review`, has no required variables, no numerator or denominator, no mapping records, and is not calculable. |
| `data/metadata/geographic_resources.json` | Approved geographic resources | Parsed; resource list is empty. |

The generated `artifacts/source_inventory.json` describes five files in the
repository `data/` tree, all JSON metadata. It does not scan the workspace
parent's `data/mine/` or `data/geo/` directories, so it cannot be used as an
inventory of the supplied workspace materials.

## Authorization and research-readiness assessment

The available evidence supports the following separate conclusions:

| Dimension | FinScope finding | Consequence |
| --- | --- | --- |
| File availability | Supplied files exist in the workspace parent; the registered repository path is absent | The application reports the registered source as unavailable. External presence is not silently adopted. |
| Readability | The named CSV and duplicate CSV are readable; XLSX package is structurally readable but `openpyxl` is absent; the DTA was not loaded through the gated application path | No reader result is promoted to an analytical input. |
| Source identity/release | Source matrix records `RWA-NISR-FINSCOPE-2024-v01` and a verified catalogue reference, but the local file is not checksum/release matched in the registry | Release identity remains unverified for the local input. |
| Permission | Catalogue access uses a separate Get Microdata/login workflow; no written project authorization is recorded | Analysis remains blocked. Public discoverability is not authorization. |
| Terms/license | Registry and source matrix are unverified; the cited release-policy link was not reviewed as a usable terms record | Analysis and redistribution/publication remain blocked. |
| Codebook/questionnaire | No exact-release codebook or questionnaire is registered and reviewed in the repository | Variable meaning, response categories, universe, skip patterns, and missingness cannot be established. |
| Indicator definition | `FI-ACCESS-001` has only a candidate policy question; numerator, denominator, required variables, coding, and definition approval are absent | No defensible formal-access estimate can be calculated. |
| Weight/design | The public report describes a stratified three-stage cluster sample and weighting at a high level; the exact weight, strata, clusters, and approved variance method for the supplied file are not recorded | A representative estimate or uncertainty interval cannot be claimed. The CSV header visibly contains `hh_wt` and `pop_wt`, but names alone do not establish their meaning. |
| Quality | No indicator-specific quality acceptance is recorded | Calculation cannot pass the quality gate. |
| Geography | Supplied boundary files are outside the repository; no resource or crosswalk is registered | Geographic comparisons are unavailable and would require separate verification. |
| Publication | No separate disclosure/publication approval exists | Even a future analytical estimate would not automatically be publishable. |

The report is useful supporting methodology context: it describes one adult per
selected household, district-oriented sampling, and weighting to population
size. It does not replace the exact-release codebook, questionnaire, data-use
terms, or a project-specific approval decision. The competition PDF likewise
sets the challenge and submission context; it is not a microdata license.

## End-to-end data flow actually present

The current path is intentionally conservative:

1. `scripts/inventory_sources.py` discovers files below the repository's
   `data/` directory only. It does not discover the parent workspace files.
2. `load_dataset_registry()` in `src/insightrwanda/data/registry.py` reads
   metadata only. `resolve_dataset_path()` converts the registered relative
   path to `data/mine/FinScope 2024 Rwanda.csv`.
3. `resolve_approved_data_path()` in
   `src/insightrwanda/data/paths.py` requires an existing regular file below
   the repository's `data/` root and rejects paths outside it. This is the
   exact transition where the supplied parent file ceases to be an approved
   application input.
4. `inspect_registered_dataset()` in
   `src/insightrwanda/analytics/phase12.py` checks the registered path and
   governance gates first. Since the file is absent at that path and the
   gates are unresolved, it returns `file_inspected: false`; its CSV intake,
   when eligible, reads a header and records `records_read: 0`.
5. `evaluate_indicator_readiness()` in
   `src/insightrwanda/analytics/readiness.py` is the single readiness
   evaluator. It blocks authorization, source provenance/release, documentation,
   terms, access authorization, analysis approval, source availability,
   definition, mappings, schema, value semantics, weighting/design, and strict
   calculation checks.
6. `load_authorized_dataset()` in
   `src/insightrwanda/analytics/authorized.py` would call `load_source()` only
   after the preflight passes. The current FinScope record fails preflight, so
   no real rows enter this loader.
7. `load_source()` in `src/insightrwanda/data/loaders.py` supports CSV, XLSX,
   XLS, Stata, and GeoJSON for an explicitly approved path. It is a capability,
   not an authorization decision. No production call currently passes one of
   the supplied parent files through it.
8. `prepare_dataset()` in `src/insightrwanda/data/prepare.py` requires an
   explicit preparation configuration and does not infer cleaning, mappings,
   weighting, or survey design. It is not a substitute for the central
   analytical gate and was not run on the supplied records.
9. `build_phase14_status()` in
   `src/insightrwanda/analytics/phase14.py` is metadata-only. It reports the
   current blockers and never loads observations.
10. `calculate_verified_indicator()` accepts explicit verified numerator and
    denominator masks and an applicable weight only after central readiness is
    eligible. It does not infer response coding from names. No call with the
    supplied records occurred.
11. `save_calculation_result()` rejects blocked, raw-record, unsafe, or
    synthetic results. There is no successful real-data result artifact.
12. The dashboard uses `_phase14()` in `src/insightrwanda/ui/pages.py`, which
    loads a saved aggregate only when current readiness says the analysis is
    eligible. Since it is not, Financial Inclusion and downstream insight
    pages correctly show blocked/no-result states; Plotly does not receive a
    Rwanda estimate.

Thus the current application reads repository metadata and generated status
artifacts, and the audit manually inspected the supplied CSV header and
aggregate file metadata. It does not currently read supplied observation rows
for an official calculation.

## Current indicator and the defensible first research question

The competition brief's Financial Inclusion & Poverty Reduction track and the
FinScope report support this candidate question:

> Which population groups face limited access to formal financial services?

The current candidate is `FI-ACCESS-001` (Formal financial access). It is the
most defensible first concept because the supplied FinScope report explicitly
describes financial access and access strands. It is not ready for estimation.
The following must be established against the exact release before calculation:

- target population and unit of analysis;
- exact formal-access construct and research question;
- source variable(s), response coding, skip patterns, and valid categories;
- numerator, eligible denominator, exclusions, and nonresponse treatment;
- exact population weight and its interpretation;
- strata, clusters, and supported point/variance estimation method;
- duplicate, range, missingness, and consistency checks;
- release-matched source checksum/schema and codebook-backed mappings;
- dataset-specific analytical authorization and separate publication/disclosure
  approval.

No alternative indicator was substituted. Poverty measures are also not
available in the catalogue with the evidence needed for calculation.

## Readiness before and after this audit

No eligibility metadata was changed. The latest checked readiness artifacts
therefore remain the same before and after the audit:

- overall readiness: `blocked`;
- Phase 12: `blocked`, 14 blocker details, no file inspected;
- Phase 13: `blocked`, analytical eligibility `false`, publication eligibility
  `false`;
- Phase 14: `blocked`, 30 blocker IDs, `calculation_status: blocked`,
  `estimate: null`, `percentage: null`, and no result artifact;
- Phase 17/18 downstream presentation/release readiness: blocked;
- analytical eligibility: `false`;
- publication eligibility: `false`.

The unchanged status is intentional. Promoting the external file or treating
`hh_wt`, `pop_wt`, or any similarly named column as a verified mapping would
weaken the existing research safeguards.

## Implemented changes in this audit

- Added this evidence-based audit document.
- Reconciled the repository inventory against the actual workspace files.
- Confirmed that the duplicate CSVs are the same file rather than separate
  observations.
- Confirmed that no supplied source was copied, moved, overwritten, uploaded,
  or used to create a research result.
- Kept the existing central readiness, authorization, disclosure, and result
  persistence gates unchanged.

No analytical code change was justified by the available evidence. The safe
portion of the workflow is already implemented; the remaining work requires
human authorization and documentation, not a permissive loader change.

## Exact next evidence needed

1. Obtain written project-specific authorization and permitted processing
   purpose through the official FinScope access route.
2. Register the authorized exact-release file below the approved repository
   data boundary and record its checksum and release identity.
3. Obtain and review the exact-release questionnaire, codebook, and survey
   methodology, including the weight, strata, clusters, and variance method.
4. Have a reviewer complete the `FI-ACCESS-001` definition review and record
   codebook-backed mappings, valid response categories, denominator, and
   missing-value rules.
5. Run aggregate schema/data-quality checks through the existing intake and
   calculation workflow; record reviewer acceptance.
6. Obtain separate disclosure and publication approval before displaying or
   exporting an aggregate result.

Only after these records make the central evaluator analytically eligible
should the application load real rows and calculate a result. Any resulting
estimate must retain its source release, checksum, definition/mapping
references, weighting/design method, validation, and limitations.

## Validation record

The repository already contains focused Phase 12–22/23 tests for the gated
loaders, synthetic-only calculation fixtures, eligibility, result integrity,
visualization, and publication safeguards. During this audit, the full test
command was started but the environment's `.venv/bin/python` test process
stalled during startup and was interrupted; no fresh passing total is claimed
until that runtime issue is resolved. No test fixture is a Rwanda finding.

The final handoff must rerun the repository's established commands, including
the full unittest discovery, `scripts/research_readiness.py`, compileall, pip
check, JSON validation, and `git diff --check`. The audit itself did not launch
a Streamlit server or browser and makes no deployed-application claim.
