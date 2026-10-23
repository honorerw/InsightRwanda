# InsightRwanda — Submission & Judge Guide

**Track 2 · Financial Inclusion & Poverty Reduction — NISR Big Data Hackathon 2026**

Read this before choosing between running the app and reviewing the screenshots — both are available, and both were produced from the same code.

*All screenshots below are real captures of the running application (headless Chrome via the DevTools protocol, marker-verified per page).*

**Take-away briefs:** every page also offers a one-page insight brief (PDF + PNG) via download buttons in the app, and committed copies live in `docs/briefs/` (`python scripts/build_briefs.py` regenerates them). Briefs are aggregate-only — no household records, no gated exports — with an explicit "what this brief cannot claim" panel, a "Preview first" modal, and three further governance modals (the poverty unlock contract, the explorer gate explainer). Motion is CSS-only with staggered card entrances, a KPI count-up, and a `prefers-reduced-motion` fallback for accessibility.

---

## 1. What to run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens on **Overview** and loads the active source directly (read-only, nothing to configure, no API keys). The sidebar **Source** selector switches between the two supplied datasets — `data/dataset.dta` (master, 13,994 households) and `data/Rwanda FinScope 2020_Final Data.sav` (second source, 12,480 individual respondents). On the SPSS source every page degrades honestly: indicators/components with no label-verified counterpart are shown as explicit "not reproducible" cards rather than approximated (see `docs/screenshots/*_spss.png`), and the Financial inclusion page carries a cross-source agreement table that applies the same indicator rules to both sources side by side. The left rail is a grouped, numbered nav system (Evidence / Governance / How it is built) that matches each page's `0N /` eyebrow; the interface uses an Inter / Lora / JetBrains Mono webfont stack with offline fallbacks.

To re-verify before judging (optional, ~5 s):

```bash
python -m unittest discover -s tests        # 62/62 pass (incl. the synthetic .sav + real SPSS integration)
python scripts/walkthrough_app.py           # headless render of all 10 pages under both sources
python scripts/browser_render_check.py      # real-Chrome render + marker check
```

## 2. The one-sentence thesis

**Account access is not resilience** — this dashboard shows where financial access is broad but shock-absorption is thin, and converts that gap into a district- and setting-level prioritisation lens.

## 3. Nine-page tour

### 01 · Overview — the national signal
Weighted KPIs (active formal access, mobile money, emergency buffer, income pressure) plus a headline candidate: *access is broad, buffers are thin*. The dedicated **Predictive insights** page runs the real predictive workflow: a majority-class baseline vs logistic regression, a decision tree and a gradient-boosted ensemble under group-stratified 5-fold cross-validation with the household weight attached to every metric. The best candidate by weighted F1 is refit and evaluated once on a held-out fold (ROC-AUC, F1, precision/recall, log loss, Brier, confusion counts), with a calibration table, permutation importance, **threshold trade-offs** (weighted precision/recall/F1 from 0.3 to 0.7 plus a precision-vs-recall sweep) and **subgroup performance** (held-out metrics per province, setting and respondent sex, low-evidence cells flagged) — all labelled as predictive associations on resampled rows, never causality or eligibility.

![Overview](screenshots/overview.png)

### 02 · Financial inclusion — the indicator registry
Six verified indicators (FI-01…FI-06), each with definition, valid-response rule, source variables, method and limitations — inspected down to numerator/denominator counts.

![Financial inclusion](screenshots/financial_inclusion.png)

### 03 · Poverty insights — honesty as a feature
Reports the exact research blockers (no poverty line, no welfare aggregate, no variance methodology) instead of fabricating a poverty rate. Includes genuine non-poverty context metrics.

![Poverty insights](screenshots/poverty_insights.png)

### 04 · Geographic insights — where to act
Province and district rankings of access, emergency funds and internet access, plus a district drill-down: pick any district to see active access, emergency buffer and internet against the national weighted mean (with deltas), the assessed case count, and the resilience Priority share split by urban/rural setting inside that district. A 60-second demo script mapped to the judging criteria is in `docs/DEMO.md`.

![Geographic insights](screenshots/geographic_insights.png)

### 05 · Resilience lab — a transparent composite
The four observed capabilities behind the resilience band are shown separately, keeping the lens auditable rather than a black-box score.

![Resilience lab](screenshots/resilience_lab.png)

### 06 · Data quality — checks that actually ran
Live structural checks on the real source (0 FAIL at the current audit) plus core-variable missingness — measured, never imputed.

![Data quality](screenshots/data_quality.png)

### 07 · Data explorer — governance enforced in code
Withholds aggregate tables and exports until an authorization and publication-approval record exists in the source profile. The gate is tested software, not a disclaimer.

![Data explorer](screenshots/data_explorer.png)

### 08 · Methods & sources — the evidence chain
Source profile (SHA-256, analysis-version fingerprint, row/variable inventory) and the five-step trail: Inspect → Load → Validate → Calculate → Explain.

![Methods & sources](screenshots/methods_sources.png)

### 09 · About the build — the product thesis
Why the access-vs-resilience framing is the actionable one, and how the prototype maps to each judging criterion.

![About the build](screenshots/about_the_build.png)

## 4. What was verified

| Check | Result |
|---|---|
| Unit tests (real source + synthetic fixtures + SPSS second source + estimation + briefs + modeling + page artifacts) | 62/62 OK |
| Headless page walkthrough (incl. filters, tabs) | 10/10 master + 10/10 SPSS + 7/7 filtered + honest-degradation markers + tabs OK |
| Real-browser render (Chrome/CDP, DOM + pixel check) | PASSED — incl. 3 SPSS pages with degraded-marker verification in the live DOM |
| Data-quality checks on the source file | 0 FAIL (both sources use the same check layer) |
| Screenshots in this guide | 10/10 pages + 3 SPSS degradation captures, marker-verified |

## 5. Deliberate boundaries

No official poverty rate (methodology not supplied), no standard errors (no PSU/strata/variance metadata), no household-level exports (no authorization/disclosure rule supplied). The app states each of these on its own pages — those with the missing documents can unlock them in seconds, by design.
