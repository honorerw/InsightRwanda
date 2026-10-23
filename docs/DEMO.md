# Demo script — 60 seconds + slide outline

**Track 2 · Financial Inclusion & Poverty Reduction — NISR Big Data Hackathon 2026**

Everything below is live in the shipped app (`streamlit run app.py`) — no stubs, no mock footage. Timings total ~60 s of narration.

---

## The 60-second script

| # | Time | On screen (open this page) | Say |
|---|---|---|---|
| 1 | 0–8 s | **01 / National signal** | "Access to an account is not resilience. This is the real NISR household survey — 13,994 records — turned into nine weighted, fully traceable decision pages. The national story in one line: access is broad, buffers are thin." |
| 2 | 8–16 s | **02 / Financial inclusion** | "Every indicator — FI-01 to FI-06 — carries its definition, valid-response rule, source variables and stated limitations, right on the page. This is a contract, not a chart." |
| 3 | 16–24 s | **03 / Poverty insights** | "Here is what wins rules on integrity: no poverty line, no welfare aggregate in the data — so we *refuse* to print a poverty rate, and we ship instead the exact six-input machine checklist that unlocks official estimation the moment NISR supplies it." |
| 4 | 24–34 s | **04 / Geographic insights** | "For targeting: the regional pulse ranks provinces, then a district drill-down shows one district against the national mean on access, buffer and connectivity — with the resilience priority split by urban and rural setting." |
| 5 | 34–42 s | **01 / National signal → Train & predict** | "One exploratory weighted model, honestly evaluated: holdout accuracy *and* five-fold cross-validation with AUC, a confusion matrix, and the caveat that this is descriptive — never an eligibility decision." |
| 6 | 42–50 s | **05 / Resilience lab** | "The resilience lab turns four observed capabilities into a transparent priority lens — every component shown separately so the intervention logic stays auditable." |
| 7 | 50–58 s | **08 / Methods & sources** | "And the evidence chain: source SHA-256, a code-derived analysis fingerprint, 0-quality-check failures, 39 passing tests, and a governance gate that keeps household data locked until an authorized steward signs off." |
| 8 | 58–60 s | any | "InsightRwanda — *where* to act, and only the claims the data can survive." |

**Delivery notes**
- Open the app already scrolled: do not let the app boot on video; have these URLs/tabs pre-loaded.
- Words to never say: "AI-powered", "predicts poverty" (say "estimates likelihood of priority band"), "official poverty rate".
- If interrupted, the strongest single fallback page is **03 / Poverty insights** — it is the differentiator ("honesty as a feature").

---

## Slide outline (7 slides · ~3-minute appendix version)

1. **Hook** — Access ≠ resilience; the question this build answers: *who can absorb a shock, and where?* (kicker: access is broad, buffers are thin)
2. **What it is** — Read-only NISR Stata source → documented 94-variable pipeline → 9 weighted decision pages; screenshot of the Overview.
3. **The evidence chain** — SHA-256 + `analysis_version` fingerprint, indicator contract (FI-01…06), visible denominators, bootstrap intervals labelled *not* design SEs.
4. **Integrity as a feature** — the refused poverty estimate + the six-input unlock contract in code; screenshot of the gate modal.
5. **From evidence to action** — district drill-down map cue, resilience-lens priority share, the three action prompts (buffer / assisted digital / shock-responsive finance).
6. **Verification** — Test suite: 39/39 tests, walkthrough: 9/9 pages, 9/9 screenshots, real-browser render check, 0 data-quality failures. Governance gate enforces exports in code.
7. **Ask** — What unlocks next: NISR's six official-poverty inputs; authorization + disclosure rule for aggregates; PSU/strata/variance documentation for design SEs.

Mapping to the published judging criteria lives in `docs/COMPETITION_SUMMARY.md` ("Judging criteria alignment"); slide 6 is the tangible-impact slide, slide 7 is the problem-relevance closer.
