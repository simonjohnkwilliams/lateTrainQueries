---
stepsCompleted: ['step-01-document-discovery', 'step-02-prd-analysis', 'step-03-epic-coverage-validation', 'step-04-ux-alignment', 'step-05-epic-quality-review', 'step-06-final-assessment']
documentsAssessed:
  - 'prds/prd-lateTrainQueries-2026-07-14/prd.md'
  - 'prds/prd-lateTrainQueries-2026-07-14/addendum.md'
  - 'architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md'
  - 'epics.md'
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-14
**Project:** lateTrainQueries — Late Train Query Engine

## Document Inventory

| Type | Path | Status | Notes |
|------|------|--------|-------|
| PRD | `prds/prd-lateTrainQueries-2026-07-14/prd.md` (+ `addendum.md`) | final | 21 FRs, 6 NFRs |
| Architecture | `architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md` | final | hexagonal spine, 12 ADs |
| Epics & Stories | `epics.md` | complete | 3 epics, 13 stories |
| UX | — | n/a | Solo CLI, no UI (per PRD §3) |

**Duplicates:** none. **Missing required docs:** none (UX not applicable).

## PRD Analysis

### Functional Requirements (21)

- **FR1** — query HSP `serviceMetrics` for all services on route/window, both directions, per weekday
- **FR2** — query HSP `serviceDetails` for scheduled/actual times per calling point
- **FR3** — extract ALL RIDs per service (not just first)
- **FR4** — cache raw HSP responses; reuse on re-run; force-refresh
- **FR5** — tolerate per-day/service API failures; log+skip, visibly distinct from no-claim
- **FR6** — compute destination arrival delay; early/on-time clamps to 0
- **FR7** — classify into SWR band; discard sub-15-min
- **FR8** — (outbound, inbound) feasibility: inbound actual dep WAT > outbound actual arr WAT
- **FR9** — max-total-payout selection over feasible pairs + single legs; 0/1/2 rows
- **FR10** — deterministic tie-break: fewer rows → earliest outbound → earliest inbound
- **FR11** — pure-function optimisation core, no I/O
- **FR12** — cancellation fallback (gated on OQ1); actual late beats cancellation
- **FR13** — output SWR-form fields per claim
- **FR14** — store as CSV + JSON; band not £
- **FR15** — group/sort output by date then direction
- **FR16** — config-driven route/window/date
- **FR17** — credentials from `HSP_CREDENTIALS_FILE`, never in repo
- **FR18** — data model allows season tickets later
- **FR19** — test suite encodes new claimable-delay behaviour
- **FR20** — old-model tests rewritten, not kept
- **FR21** — offline tests, no network/creds by default; real-HSP-grounded fixtures

**Total FRs: 21**

### Non-Functional Requirements (6)

- **NFR1** — correctness is top priority; deterministic, test-covered
- **NFR2** — offline-first testing; live opt-in, skips cleanly without creds
- **NFR3** — runs under AVG TLS interception (`REQUESTS_CA_BUNDLE`)
- **NFR4** — idempotent, cache-friendly runs
- **NFR5** — trivial scale, no perf engineering
- **NFR6** — Python

**Total NFRs: 6**

### Additional Requirements / Constraints

- Greenfield rewrite of the `TrainLine` monolith; design seams for the endgame (Lambda) but build only MVP; no AWS/Terraform yet.
- Open day return ticket premise (any train that day).
- **Open questions (deferred):** OQ1 (no HSP cancellation flag; capture a real cancelled-train fixture before enabling FR12), OQ2 (payout base single-vs-return + claim-stacking cap), OQ3 (SWR form field mapping vs live form).

### PRD Completeness Assessment

Complete and internally consistent (post reviewer-gate + reconciliation). Requirements are numbered, testable, and each has a clear home. Deferred items are explicitly flagged and pre-provisioned in the architecture, so none blocks MVP implementation.

## Epic Coverage Validation

### Coverage Matrix

| FR | Requirement (short) | Epic / Story | Status |
|----|--------------------|--------------|--------|
| FR1 | serviceMetrics both directions | Epic 2 / 2.2 | ✓ Covered |
| FR2 | serviceDetails times | Epic 2 / 2.3 | ✓ Covered |
| FR3 | extract ALL RIDs | Epic 2 / 2.2 | ✓ Covered |
| FR4 | cache + force-refresh | Epic 2 / 2.4 | ✓ Covered |
| FR5 | failure tolerance, visible | Epic 2 / 2.5 | ✓ Covered |
| FR6 | delay, clamp early to 0 | Epic 1 / 1.3 | ✓ Covered |
| FR7 | banding, discard sub-15 | Epic 1 / 1.3 | ✓ Covered |
| FR8 | feasibility | Epic 1 / 1.4 | ✓ Covered |
| FR9 | max-payout, 0/1/2 rows | Epic 1 / 1.4 | ✓ Covered |
| FR10 | deterministic tie-break | Epic 1 / 1.4 | ✓ Covered |
| FR11 | pure core | Epic 1 / 1.4, Epic 3 / 3.3 | ✓ Covered |
| FR12 | cancellation fallback (gated) | Epic 1 / 1.5 | ✓ Covered (gated OQ1) |
| FR13 | SWR-form fields | Epic 3 / 3.2 | ✓ Covered |
| FR14 | CSV + JSON, band not £ | Epic 3 / 3.2 | ✓ Covered |
| FR15 | sort date→direction | Epic 3 / 3.2 | ✓ Covered |
| FR16 | config-driven route/window | Epic 3 / 3.1 | ✓ Covered |
| FR17 | creds from env, not in repo | Epic 3 / 3.1 | ✓ Covered |
| FR18 | season-ticket-ready model | Epic 1 / 1.2 | ✓ Covered |
| FR19 | new-model test suite | Epic 1 / 1.3, 1.4 | ✓ Covered |
| FR20 | old-model tests rewritten | Epic 1 / 1.1 | ✓ Covered |
| FR21 | offline fixtures | Epic 1 / 1.1, Epic 3 / 3.3 | ✓ Covered |

### Missing Requirements

None. No FR is uncovered; no story references an FR absent from the PRD.

### Coverage Statistics

- Total PRD FRs: **21**
- FRs covered in epics/stories: **21**
- Coverage: **100%**
- Note: FR12 is covered but intentionally **gated** on OQ1 (production-enable deferred until a real cancelled-train fixture exists).

## UX Alignment Assessment

### UX Document Status

Not Found — and **not required**.

### Alignment Issues

None. No UI is implied: the PRD (§3 Users & Context) explicitly states a CLI/script is an acceptable interface and "the value is in the correctness of the answer, not the UI." No web, mobile, or user-facing surface exists. The only human-facing output is the CSV/JSON claim files (governed by FR13–15, Epic 3 Story 3.2).

### Warnings

None. Absence of a UX spec is correct for this solo command-line tool, not a gap.

## Epic Quality Review

### Epic structure & independence

| Check | Result |
|-------|--------|
| Epics deliver value, not pure tech layers | ✓ (value increments: correct engine → real data → runnable tool) |
| Epic independence (N never needs N+1) | ✓ (2 builds on 1; 3 on 1+2) |
| File-churn across epics | ✓ clean (`engine/*` · `hsp_client` · `storage`+`config`+`cli`) |
| Starter/greenfield setup as Epic 1 Story 1 | ✓ (Story 1.1 scaffold — required for greenfield) |
| Forward dependencies within epics | ✓ none (1.1→1.5, 2.1→2.5, 3.1→3.3 strictly incremental) |
| Story sizing (single dev session) | ✓ all 13 |
| Acceptance criteria in Given/When/Then, testable | ✓ (incl. edge cases: cross-midnight, `None` actuals, sub-15, fetch-failure) |
| FR traceability | ✓ 100% (see matrix) |
| Entity creation only when needed | ✓ (`engine.models` in 1.2; justified single-definition per AD-3, not an "all-upfront" violation) |

### 🔴 Critical Violations

None.

### 🟠 Major Issues

None.

### 🟡 Minor Concerns

1. **Epic 1 value is "correctness/tested library", not end-user-runnable output** — a user can't produce real claim files until Epic 3. *Assessment:* acceptable and deliberate — NFR1 makes correctness-first the right sequencing, and Epic 1 is the product's domain core, not a horizontal tech layer. No change recommended.
2. **Story 1.5 (cancellation) is externally blocked on OQ1** for production-enable (no real cancelled-train fixture). *Assessment:* correctly gated; the story is completable (code path + synthetic-fixture test, flag off). Track so it isn't mistaken for fully shippable. No change recommended.
3. **No explicit CI/CD or dev-environment story.** *Assessment:* acceptable for a solo hobby tool — the offline pytest harness (Story 1.1) covers the essential test loop; CI is optional and can be added later without restructuring.

### Best-Practices Compliance

- [x] Epic delivers user value
- [x] Epic can function independently
- [x] Stories appropriately sized
- [x] No forward dependencies
- [x] Entities created when needed
- [x] Clear acceptance criteria
- [x] Traceability to FRs maintained

## Summary and Recommendations

### Overall Readiness Status

**READY** ✅

### Critical Issues Requiring Immediate Action

None. Zero critical, zero major issues. FR coverage is 100%; PRD ⇄ Architecture ⇄ Epics/Stories are consistent (they were reviewer-gated and reconciled during creation).

### Recommended Next Steps

1. Proceed to **Sprint Planning** (`bmad-sprint-planning`) to sequence the 13 stories for implementation.
2. Begin the story cycle at **Story 1.1** (scaffold) → work Epic 1 (engine) → Epic 2 (HSP) → Epic 3 (CLI), test-first per AD-12.
3. Track the two deferred items so they resurface at the right moment: **OQ1** (capture a real cancelled-train HSP fixture) before enabling Story 1.5's cancellation flag; **OQ2** (confirm payout base/stacking) at your next real SWR filing.
4. *Optional:* run `bmad-generate-project-context` first so the dev agent is grounded on the greenfield-over-brownfield layout.

### Final Note

This assessment identified **3 minor concerns across 0 blocking categories** — all reviewed and judged acceptable with no change recommended. The planning artifacts are development-ready. You may proceed to implementation as-is.

**Assessor:** Implementation Readiness workflow · **Date:** 2026-07-14
