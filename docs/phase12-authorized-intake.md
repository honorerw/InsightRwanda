# Phase 12 — Authorized intake and first indicator

## Current outcome

Phase 12 is implemented as a controlled, blocked workflow. No survey microdata or local codebook/document files are present in `data/`; the registered FinScope CSV, generic CSV, and Stata paths do not currently resolve to source files. All registered datasets remain unauthorized/unverified in metadata. `artifacts/phase12_status.json` is generated from the live registry and catalogue and contains no records or indicator estimate.

The first candidate remains `FI-ACCESS-001` (formal financial access), not a selected or approved measure. Its numerator, eligible denominator, variables, response categories, missing-value handling, and weighting method are not verified. The catalogue contains no required variables or verified mappings. Therefore no statistic, including a synthetic fixture result, is presented as an InsightRwanda/Rwanda estimate.

## Official references reviewed

- NISR microdata catalogue, *Rwanda - FinScope 2024, Financial Inclusion in Rwanda*, reference `RWA-NISR-FINSCOPE-2024-v01`. The page lists Access to Finance Rwanda as producer, identifies questionnaire/report documentation, and provides a distinct microdata access workflow with login/register. This establishes what that public catalogue page displays; it does not establish project authorization, specific terms, fieldwork dates, or approved use of local data.
- NISR, *Integrated Household Living Conditions Survey 7 (EICV7)*. The page states October 2023–October 2024, links methodological notes and public reports, and describes poverty-reduction monitoring intent. Public reports do not establish access to underlying microdata or permission to analyze it.

Official pages reviewed on 2026-10-14:

- <https://microdata.statistics.gov.rw/index.php/catalog/120>
- <https://statistics.gov.rw/data-sources/surveys/EICV/integrated-household-living-conditions-survey-7-eicv-7>

The linked FinScope questionnaire and methodology/codebook were not downloaded or reviewed. The public catalogue text alone does not verify sampling weights, strata, clusters, variance methods, geographic identifiers, license, or permissions. EICV7 is not used as an alternate source for the financial-inclusion candidate.

## Controlled intake behavior

`insightrwanda.analytics.phase12.inspect_registered_dataset` requires an explicit registered ID and resolves only a registered relative path under the project `data/` tree. It refuses to inspect bytes until provenance, documentation, license/terms, authorization, and analytical eligibility are explicitly verified. On the authorized CSV path it records file size, SHA-256, and CSV header only (`records_read: 0`); it does not return or log rows. No source files are downloaded, moved, changed, or copied. Unsupported formats remain blocked pending a suitable reviewed intake implementation.

The calculation still depends on the existing Phase 9 authorized loader and calculation gates. Phase 12 does not infer masks, recode response values, select weights, or bypass those gates. Publication remains a separate disclosure and permission decision.

## Required manual actions

1. Request the exact FinScope release through the catalogue's access process; retain the decision, data-use terms, and permitted purpose. Do not treat catalogue registration or public reports as authorization.
2. Obtain the release-matched questionnaire, codebook/data dictionary, and technical/survey-design documentation through approved channels. Have a reviewer confirm the unit, universe, fieldwork period, weight, strata/clusters, variance method, and geography.
3. Place an authorized file only in the controlled approved data directory. Update registry and evidence metadata with verifiable provenance, release, permission scope, and terms; keep analysis and publication approvals separate.
4. Have a domain reviewer define FI-ACCESS-001's population, numerator, denominator, valid responses, nonresponse treatment, and limitations. Independently review each variable mapping against the codebook and exact release schema.
5. Run aggregate data-quality checks and record approval. Calculate only after readiness, mapping, quality, authorization, and survey design gates all pass. Seek distinct disclosure/publication review before any release.

Refresh the source inventory and readiness report after metadata or approved files change by running the project's inventory and readiness scripts. A regenerated readiness report cannot itself grant an approval.
