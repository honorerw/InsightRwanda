# Supplied local-material analysis

The Financial Inclusion page uses the explicitly authorized raw material
supplied in the workspace. The primary numerical view uses:

- `../data/mine/dataset.dta`
- `../data/mine/FinScope/2024/FinScope_2024_Consumer_Questionnaire.pdf`

It does not discover, combine, download, or substitute another dataset. All 48
supplied files are inventoried by role. The Stata dataset is read for aggregate calculation only; respondent rows are not rendered
or serialized.

## Measure

The page reports the weighted share of respondents currently using at least
one provider in QF4 columns `qf4_01` through `qf4_06`:

1. Commercial bank
2. Digital bank
3. Microfinance institution
4. Non-deposit-taking financial service provider
5. Mobile money operator
6. Umurenge SACCO

The calculation uses `pop_wt`, excludes non-positive or missing weights, and
uses the labelled Stata responses (`Yes`/`No`). The displayed breakdowns
are by province (`a1`) and residence (`a6`).

The current supplied file contains 13,994 respondents. Its local
national result is 53.6% weighted current use of at least one listed provider.
This is an authorized local result, not an official publication-approved
estimate, and it does not change the separate central publication-readiness
decision.

## Comparability and data-quality caveats

- **Not comparable with the official headline figures.** The official FinScope
  2024 report supplied with this workspace publishes 96% financial inclusion
  and 92% formal inclusion using broader product-based definitions (all formal
  and informal products). The 53.6% local figure is a narrow, QF4-only
  "current use of six provider types" measure. The two numbers must never be
  presented as the same indicator. The Financial Inclusion page now renders an
  explicit cross-check table between the extract measures and the official
  published values so the gaps are visible and labelled row by row.
- **The supplied extract is internally inconsistent.** In `dataset.dta` the QF
  access module disagrees with the F mobile-money module: `qf1_05` ("ever used
  a mobile money operator") gives 35.5% weighted, while `f5` codes 4·5·6
  (registered former user, unregistered current user, registered current user)
  give 76.3% — and 4,887 of the 9,434 active registered mobile-money users
  answer "No" to `qf1_05`. Likewise `qf1_12` ("none of the above") implies
  21.9% excluded against the official report's 4%. The F5 module, however,
  cross-checks well against the official report: registered current users
  66.6% local versus the report's 77% registered mobile wallets, and 76.3%
  current-or-former use versus the report's 86% own-or-have-used. The page
  therefore treats F5-based measures as the primary mobile-money indicators
  and flags the QF mobile-money figures as extract-specific.
- **The F5 codes are verified against the supplied questionnaire.**
  `f5` maps to the questionnaire's mobile-money experience question: 1 = not
  heard of mobile money; 2 = not registered and never used; 3 = registered and
  never used; 4 = registered former user; 5 = unregistered current user;
  6 = registered current user. These definitions come from the questionnaire
  and report text in `data/mine/FinScope/2024/`, and the codebook records the
  same semantics.
- **Duplicate raw file.** `../data/mine/dataset.csv` is byte-identical (MD5
  `0f1cd1ad74ae4c613a0170ea48985cce`) to
  `../data/mine/FinScope 2024 Rwanda.csv`. The dataset registry records the
  duplication so the two files are not treated as independent sources.

## 2026-10-15 correction: QF1 battery and F5 module added to the analysis

The original implementation exposed only the QF3/QF4 follow-up batteries and
one QF1 item. The result was technically a correct weighted aggregate of the
coded extract, but it carried two interpretation hazards:

1. **Skip pattern.** The supplied questionnaire asks QF2–QF7 per provider
   selected in QF1, so QF3/QF4 cells are blank unless that provider was
   selected. Blank cells were treated as non-affirmatives over the whole
   population, which is valid for own-name account measures only because a
   never-used provider cannot be held. Every such measure now states this
   basis explicitly in its definition.
2. **Missing cross-check surface.** The numerically divergent QF figures were
   displayed without the adjacent F-module evidence.

The corrected analysis adds:

- QF1 battery measures computed over the full respondent base with no skip
  ambiguity: `any_provider_ever` (78.1%), `bank_ever` (18.0%), `sacco_ever`
  (26.1%), `mobile_money_ever` (35.5%).
- F5 mobile-money measures from the module that agrees with the official
  report: registered current user 66.6%, current-or-former use 76.3%, unaware
  or never used 20.5%.
- A cross-check table rendering the extract measures beside the official
  report's published values (96% financial inclusion, 92% formal inclusion,
  22% banked, 77% registered mobile wallets, 28% SACCO accounts, 86% own or
  have used mobile money, 4% excluded) with per-row readings.

The codebook (`data/metadata/finscope_codebook.json`) also now documents the
full QF1 battery, `f5`, and the value-label semantics read directly from the
release file, plus the official-report benchmark section.
