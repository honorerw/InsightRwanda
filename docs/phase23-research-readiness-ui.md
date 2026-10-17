# Phase 23 — Research readiness UI, blocker cards, and layout fixes

## Root cause

The Financial Inclusion page joined every central readiness message into one
`st.warning` string. The same page also rendered related governance details in
later sections, which made the reason for `FI-ACCESS-001` being blocked hard to
scan. The Research Readiness page used wide blocker and action-plan tables,
even though the underlying metadata already contained evidence IDs, statuses,
reasons, and next actions.

## Implemented

- Added a compact FI-ACCESS-001 status strip showing indicator ID, analytical
  status, estimate status, publication status, and the scoped blocker count.
- Added grouped, expandable blocker cards. Cards preserve central blocker IDs,
  current status, explanation, required action, evidence needed, linked
  evidence IDs, references, and evidence status.
- Reused the existing evidence register and `researcher_action_plan`; no second
  readiness evaluator or approval path was introduced.
- Added a responsive researcher action-plan card renderer with logical order:
  source identity, authorization, codebook/questionnaire, mappings,
  survey design, quality review, and publication/disclosure review.
- Removed the concatenated blocker warning and the wide actionable-blocker and
  action-plan tables from the affected pages.
- Tightened shared top spacing, content width, and narrow-screen padding while
  preserving the existing navigation and dependency set.
- Missing estimates remain `Not calculated`; publication remains `Not approved`
  without the existing approval state. Evidence marked `provided_unverified`
  remains unverified.

Geographic blockers are excluded from the Financial Inclusion action plan
unless the requested analysis is geographic. They remain visible in the
general Research Readiness view.

## Validation — 2026-10-14

- Full suite: 234 tests passed.
- Focused Phase 23 suite: 5 tests passed.
- Focused AppTest/regression set including Phase 23 and existing Phase 1–22 UI
  coverage: 51 tests passed.
- Research readiness generation succeeded with `overall_status=blocked`,
  inventory `current`, analytical eligibility `false`, publication eligibility
  `false`, Phase 14/17/18 `blocked`, zero verified geographic resources, and
  Phase 20 `not_configured`.
- Python compilation passed; `pip check` reported no broken requirements;
  `git diff --check` passed; 12 metadata/artifact JSON files parsed.
- AppTests verified the Financial Inclusion and Research Readiness pages render
  without exceptions and that the Financial Inclusion page has no warning
  containing the former concatenated messages.
- No browser or narrow-viewport launch was performed. Local AppTest coverage is
  not a claim of deployed or browser-verified behavior.

## Local launch

```bash
cd /home/dna/Projects/hackton/insight-rwanda
streamlit run app.py
```

This phase did not modify source data, download/upload datasets, create result
artifacts, or alter analytical/publication eligibility.
