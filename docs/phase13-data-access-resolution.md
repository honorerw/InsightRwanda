# Phase 13 — Official data access and documentation resolution

## Outcome

The workflow is auditable and remains blocked. No microdata, questionnaire, codebook, survey-design document, license, or project authorization is present in the approved `data/` tree. The source matrix continues to distinguish source references, document review, access authorization, analytical approval, and publication approval. No source or indicator was promoted to verified by adding checklist fields.

The FinScope catalogue identifies *Rwanda - FinScope 2024, Financial Inclusion in Rwanda*, reference `RWA-NISR-FINSCOPE-2024-v01`, and lists Access to Finance Rwanda as producer. It displays a distinct “Get Microdata” link and Login/Register links, and lists a questionnaire and report. The linked policy URL returned 404 when checked; the Get Microdata target was not readable by the review tool. These observations identify an official access route and document listing, not the current application requirements, possession of the listed documents, a local-file release match, or permission for this project.

The EICV7 NISR page states an October 2023–October 2024 period and links methodology notes and public reports. This is recorded as a candidate source for poverty work only; it is not an alternative source for FI-ACCESS-001. No microdata permissions are inferred from public reports.

Official references reviewed 2026-10-14:

- FinScope: <https://microdata.statistics.gov.rw/index.php/catalog/120>
- FinScope Get Microdata route: <https://microdata.statistics.gov.rw/index.php/catalog/120/get_microdata>
- EICV7: <https://statistics.gov.rw/data-sources/surveys/EICV/integrated-household-living-conditions-survey-7-eicv-7>
- Catalogue-linked microdata policy (returned 404 on review): <https://statistics.gov.rw/publications/microdata-release-policy>

The older FinScope publication URL and EICV7 main-indicators publication URL timed out on review and remain unverified references; they are not treated as reviewed documents.

## Checklist and current status

The FinScope source record carries 13 actionable checklist rows. Statuses use the project evidence vocabulary and are resolved from linked evidence IDs or source-verification dimensions at report generation. Updating an evidence status updates the checklist summary; merely adding a row cannot satisfy a gate.

Current items:

| Requirement | Current status | Evidence/action |
|---|---|---|
| Official access procedure identified | Provided, unverified | Get Microdata/Login/Register is visible; document the actual process and authority. |
| Access request requirements documented | Missing | Obtain current applicant, purpose, and review requirements from the responsible source owner. |
| Exact release confirmed for local data | Provided, unverified | Catalogue lists `RWA-NISR-FINSCOPE-2024-v01`; no local file is available to match. |
| Permission/license obtained and reviewed | Missing | Obtain project-specific written terms; do not apply or accept terms automatically. |
| Permitted-use restrictions recorded | Missing | Record storage, analysis, sharing, attribution, and publication conditions. |
| Exact-release questionnaire reviewed | Missing | Obtain and review the release-matched questionnaire. |
| Exact-release codebook reviewed | Missing | Obtain and independently review meanings, codes, universes, and nonresponse values. |
| Methodology/sampling documentation reviewed | Missing | Obtain weights, strata, clusters, variance, and geographic guidance. |
| Expected schema documented | Missing | Record schema expectations from reviewed documentation. |
| Data-quality requirements defined | Missing | Define acceptance checks after authorized intake. |
| Indicator definition/mappings verified | Missing | Resolve FI-ACCESS-001 field review and independently verify mappings. |
| Analytical eligibility approved | Missing | Complete a distinct governance decision after all evidence gates. |
| Publication/disclosure reviewed separately | Missing | Obtain output-specific license, attribution, disclosure, and publication review. |

The machine-readable source checklist is under the FinScope record in `data/metadata/source_verification.json`. The evidence register holds supporting dataset/indicator requirements and current evidence statuses. Current report counts are generated from those records rather than fixed historical numbers.

Latest generated counts: 5 source records (0 verified, 2 provided but unverified, 3 missing); 39 evidence items (0 verified, 2 provided but unverified, 37 missing); 13 FinScope checklist entries (11 missing, 2 provided but unverified); 3 registered datasets; 7 candidate indicators; 0/7 verified mappings; 0/16 FI-ACCESS-001 definition-review fields verified. The approved data inventory currently contains 4 metadata files and no survey microdata or local source documents. Analytical eligibility and publication eligibility are both false.

## FI-ACCESS-001 review

The catalogue describes “Formal financial access” as a candidate and asks which population groups face limited access. That concept is not an official definition. The structured `definition_review` in `data/metadata/indicator_catalogue.json` tracks 16 review fields for target release `RWA-NISR-FINSCOPE-2024-v01`, including population, eligibility, numerator, denominator, variable mappings, valid categories, nonresponse handling, weight, design, calculation/validation, limitations, analysis approval, and publication approval.

Only the candidate name, purpose, and cautionary language are currently labelled `provided_unverified`; no field is verified. No source variables or codebook mappings are registered. The dataset-specific weight, strata, clusters, estimator, and release-matched schema are unknown. FI-ACCESS-001 remains blocked and has no estimate.

The shared readiness evaluator now consumes source-verification authorization/review dimensions as well as registry, mapping, quality, methodology, and publication gates. Local non-synthetic analytical loading also requires the corresponding source record. Publication continues to require a distinct source publication approval in addition to dataset and indicator publication conditions.

## Registering locally held documents

For an authorized local document, `insightrwanda.data.documentation.prepare_local_document_record` accepts a project-relative `data/...` path, checks that it resolves to a regular file below the approved data root (including symlink resolution), and returns document type, release label, size-independent SHA-256, and metadata with `provided_unverified` document status and `missing` exact-release/review statuses. It reads no text and does not copy or change the file.

Add that metadata to the relevant source's `documentation_records` in `source_verification.json`. A checksum is only an integrity fingerprint. A human reviewer must inspect contents, confirm exact-release applicability, record reviewer/date and evidence, and then update statuses using the normal evidence vocabulary. The validator rejects a verified document review if its release label disagrees with the source's registered release. Never put confidential text or raw observations into logs or evidence descriptions.

## Remaining human actions

1. Use the official FinScope catalogue's Get Microdata route to establish current access requirements; the application must not submit requests or accept terms for the project owner.
2. Obtain written permission and terms with the intended processing purpose and permitted-use restrictions.
3. Obtain and locally register the exact-release questionnaire, codebook, and survey-design/methodology materials; review them manually.
4. If a data file is authorized, place it only in controlled `data/` storage and independently match its provenance/release. Define its expected schema from the reviewed codebook.
5. Have a domain reviewer resolve each FI-ACCESS-001 field and a second reviewer verify every exact variable mapping, denominator, missing-value rule, weight, and design requirement.
6. Complete indicator-specific quality acceptance and dataset-specific analytical approval. Keep publication/disclosure authorization separate.

Regenerate the evidence-based readiness artifacts with `PYTHONPATH=src .venv/bin/python scripts/research_readiness.py`. This refreshes reports only; it never grants an approval.

## Validation performed

- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` — 113 tests passed.
- `PYTHONPATH=src .venv/bin/python scripts/inventory_sources.py` — completed; 4 files inventoried.
- `PYTHONPATH=src .venv/bin/python scripts/research_readiness.py` — completed; overall status blocked, analytical eligibility false, publication eligibility false.
- `PYTHONPATH=src .venv/bin/python -m compileall -q app.py src app_pages scripts tests` — passed.
- `.venv/bin/python -m pip check` — no broken requirements; pip emitted a non-fatal warning that its cache directory is not writable.
- `git diff --check` — passed.
- JSON validation — passed for 4 metadata files and 4 generated artifacts.
- Streamlit AppTest — entry point and all 16 existing pages passed. No browser/server test was run; AppTest was used for page execution.
