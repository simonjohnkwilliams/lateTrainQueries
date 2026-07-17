---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
release: 2
baseline_tag: v1.0.0
documentsAssessed:
  - 'prds/prd-lateTrainQueries-2026-07-14/prd.md'
  - 'prds/prd-lateTrainQueries-2026-07-14/addendum.md'
  - 'architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md'
  - 'epics.md'
  - 'implementation-artifacts/sprint-status.yaml'
---

# Implementation Readiness Assessment Report — Release 2

**Date:** 2026-07-16  
**Project:** lateTrainQueries — Late Train Query Engine  
**Baseline:** v1.0.0 (Epics 1–3 complete, 160 tests green)

## Executive verdict

**READY TO IMPLEMENT** — with one open question (OQ4: SWR session/2FA) that does not block Epic 4 or 5, and should be resolved before Epic 6 live filing.

## Document inventory

| Type | Path | Status | Notes |
|------|------|--------|-------|
| PRD | `prds/prd-lateTrainQueries-2026-07-14/prd.md` | final (R2 updated) | FR1–FR31, NFR1–NFR10 |
| PRD addendum | `prds/.../addendum.md` | updated | Release 2 adapter contracts |
| Architecture | `architecture/.../ARCHITECTURE-SPINE.md` | final (extended) | AD-1–AD-17 |
| Epics & Stories | `epics.md` | complete | 6 epics, 23 stories |
| Sprint status | `implementation-artifacts/sprint-status.yaml` | generated | Epics 4–6 ready-for-dev |
| Story files | `implementation-artifacts/4-1` … `6-4` | ready-for-dev | 10 Release 2 story files |
| UX | — | n/a | Solo CLI |

## PRD analysis — Release 2 FRs

| FR | Requirement | Epic | Story coverage |
|----|-------------|------|----------------|
| FR22 | Email digest | 4 | 4.1–4.3 |
| FR23 | Ticket directory | 5 | 5.1 |
| FR24 | Ticket naming contract | 5 | 5.1 |
| FR25 | Ticket prerequisite gate | 5 | 5.2, 5.3 |
| FR26 | Playwright auto-submit all rows | 6 | 6.2, 6.3 |
| FR27 | SWR field mapping at submit | 6 | 6.1 |
| FR28 | Ticket upload per claim | 6 | 6.2 |
| FR29 | Filing audit log | 6 | 6.3 |
| FR30 | Single `--file` command | 6 | 6.4 |
| FR31 | Assess-only default preserved | 6 | 6.4 |

**Coverage:** 10/10 Release 2 FRs mapped. No orphans.

## Architecture alignment

| AD | Release 2 binding | Status |
|----|-------------------|--------|
| AD-1 | Engine unchanged | ✓ |
| AD-2 | No adapter cross-imports | ✓ — import-boundary test must extend |
| AD-8 | cli sole orchestrator | ✓ — AD-17 extends for `--file` |
| AD-13 | notification adapter | ✓ |
| AD-14 | ticket_gate adapter | ✓ |
| AD-15 | Playwright claim_submission | ✓ |
| AD-16 | JSONL audit log | ✓ |
| AD-17 | `--file` pipeline | ✓ |

**Stack addition:** Playwright >=1.40 documented in spine.

## Epic quality review

| Epic | User value | Standalone? | Story deps OK? | Notes |
|------|-----------|-------------|----------------|-------|
| 4 Digest | ✓ | ✓ | ✓ | No filing dependency |
| 5 Ticket gate | ✓ | ✓ | ✓ | `--check-tickets` standalone |
| 6 Auto-file | ✓ | Needs 5 for `--file` | ✓ sequential | 6.4 wires all |

**File churn:** Epics 4–6 touch distinct adapter files — no unnecessary split.

## UX alignment

N/A — CLI-only. No UX document required.

## Open items / risks

| ID | Item | Severity | Blocks |
|----|------|----------|--------|
| OQ2 | Payout base / stacking cap | medium | Live £ amounts only; not blocking R2 |
| OQ4 | SWR session persistence / 2FA | high | Epic 6 live `@live` tests |
| — | Playwright browser install on Windows | low | Dev setup (QUICKSTART update) |
| — | SWR form selector drift | medium | Epic 6.2 — validate against live form |

## Gaps found (minor)

1. **QUICKSTART.md** not yet updated for Release 2 env vars — defer to Story 4.1 or 6.2.

## Final assessment

| Check | Result |
|-------|--------|
| All FRs have story coverage | PASS |
| Architecture binds all new capabilities | PASS |
| Stories sized for single dev agent | PASS |
| No forward story dependencies | PASS |
| Release 1 behaviour preserved (FR31) | PASS |
| Test-first (AD-12) in story ACs | PASS |

**Recommendation:** Proceed to sprint implementation starting Epic 4 Story 4.1. Run Epic 5 in parallel if desired. Gate Epic 6 live tests on OQ4 discovery.
