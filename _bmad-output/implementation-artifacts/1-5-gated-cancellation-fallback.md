# Story 1.5: Gated cancellation fallback

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want cancellation-derived claims computed only when clearly correct,
so that I never file a disputable claim.

## Acceptance Criteria

1. **Flag OFF is the default and emits nothing cancellation-derived.** With the cancellation fallback flag off (the default), the optimiser emits **no** cancellation-derived claims — a cancelled service never contributes a claim row. *(Epic 1 AC; FR12 gate, AD-6)*
2. **Flag ON computes next-catchable delay, actual-late always wins.** With the flag on and a synthetic cancelled service present, the optimiser computes `delay = actual_arrival(next catchable service) − scheduled_arrival(cancelled service)`, where "next catchable" is the earliest service departing at/after the cancelled train's scheduled departure that actually ran. For the same leg, an **actual late train always takes precedence** over a cancellation-derived claim. *(Epic 1 AC; FR12, AD-6)*
3. **OQ1 gates production-enable; flag stays OFF.** Because OQ1 is unresolved (no real cancelled-train fixture pins the HSP JSON shape), the story is **blocked for production-enable**: the flag ships **off**, and no code path turns it on by default. The pure logic and its synthetic-data tests are delivered; enabling it in a real run is out of scope until OQ1 closes. *(Epic 1 AC; FR12, OQ1)*

> **TDD (AD-12):** Encode ACs 1–2 as pytest-bdd `@offline` scenarios (plus TDD unit tests underneath) using **synthetic** cancelled `Service`s — write them failing first, then implement the gated path to green. AC3 is a scope/governance constraint verified by the flag defaulting off and the absence of any real cancelled fixture — do **not** fabricate one.

## Tasks / Subtasks

- [ ] **Task 1 — Add the cancellation flag to the optimiser signature (AC: 1, 3)**
  - [ ] Extend `engine.optimiser.optimise(...)` (from Story 1.4) with a keyword flag, e.g. `enable_cancellation_fallback: bool = False`. Default **False** (AD-6). Pure function — no I/O, no global state.
  - [ ] With the flag `False`, cancelled services are simply skipped (consistent with AD-3: engine skips any service where `cancelled` is true or destination actual is `None`). No cancellation claim can be produced.
- [ ] **Task 2 — Implement the gated fallback path (AC: 2)**
  - [ ] When the flag is `True`, for a leg (direction) whose best candidate would be a cancelled service, find the **next catchable** service: earliest service in the same direction whose `scheduled_departure >= cancelled.scheduled_departure` **and** that actually ran (not cancelled, destination actual present).
  - [ ] Compute `delay = actual_arrival(next catchable) − scheduled_arrival(cancelled)` in origin-day-relative minutes; band/payout via `engine.delay` (Story 1.3). Clamp early/on-time to 0 (FR6 semantics).
  - [ ] **Precedence:** if any *actual* (non-cancelled) claimable service exists for the same leg, it wins over the cancellation-derived claim regardless of payout ordering (AD-6). The cancellation candidate is a *fallback* only — considered when no actual late train covers that leg.
  - [ ] Feed the resulting candidate(s) into the existing feasibility + max-payout + tie-break machinery (Story 1.4) so 0/1/2-row selection and determinism are unchanged.
- [ ] **Task 3 — Keep the boundary clean (AC: all)**
  - [ ] Confirm `hsp_client` (Epic 2) only sets `Service.cancelled` from empty actual times + `late_canc_reason` and computes **no** fallback delay (AD-6). The optimiser owns all delay math. (This story does not touch `hsp_client`; just do not push math into it.)
- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] `@offline` BDD + unit tests with **synthetic** cancelled `Service`s:
    - flag off → cancelled service yields no claim (AC1);
    - flag on → next-catchable delay computed correctly, including a cross-midnight case per AD-4 (AC2);
    - flag on + an actual late train on the same leg → the actual claim is chosen, cancellation candidate discarded (AC2 precedence);
    - determinism: identical input → identical output (AD-10).
  - [ ] Assert the default `optimise(...)` call (no flag) is byte-identical in behaviour to Story 1.4 — the flag is purely additive (regression guard, AC1/AC3).

## Dev Notes

### Why this story exists
This closes Epic 1 by adding the **cancellation fallback** as a pure, gated code path inside `engine.optimiser`. Cancellations are a *fallback* candidate only — an actual late train is always easier to compute and less disputable, so it wins (PRD §4, addendum "Cancellation handling"). The whole path ships **off** because the data to validate it does not yet exist (OQ1).

### The fallback rule (addendum — Cancellation handling, FR12)
- `delay = actual_arrival(next catchable service) − scheduled_arrival(cancelled service)`.
- **next catchable** = earliest service departing **at/after** the cancelled train's scheduled departure that actually ran.
- Actual late trains **always** take precedence over cancellation-derived claims for the same leg.

### Gating (AD-6, OQ1) — do not skip
- The flag defaults **off** and stays off for MVP. No default run enables it.
- **OQ1 data gap:** HSP exposes **no** cancellation flag or disruption code. The only signal is the free-text `late_canc_reason` field plus empty `actual_ta`/`actual_td`. **None** of the recorded fixtures (`tests/fixtures/recorded_details_*.json`, all 2026-05-28) contain a cancelled service — they all ran. A real cancelled-service fixture is required before this path can be trusted in production. **Do not fabricate a "real" fixture** to force AC3 green; use clearly-synthetic data for AC1/AC2 and leave the flag off.
- When OQ1 resolves (a real cancelled-train fixture is captured), a follow-up enables the flag and adds a `@recorded` scenario. That is *not* this story.

### Dependencies (pure core, AD-1/AD-2)
- `engine.models` (Story 1.2): `Service.cancelled: bool`, `Service.reason`, actual-time fields typed `int | None` (`None` = no actual), `Claim`, `DayResult`.
- `engine.delay` (Story 1.3): `calculate_delay`, `band`, `payout` — reused for the fallback delay; no new delay arithmetic here (AD-4: `engine.delay` is the sole owner).
- `engine.optimiser` (Story 1.4): feasibility, max-payout selection, tie-break, determinism — this story extends it additively; the objective/tie-break rules do not change.
- This module imports **nothing I/O** (AD-1); the Story 1.1 import-boundary test must stay green.

### Files being touched
| File | Change |
| --- | --- |
| `trainline/engine/optimiser.py` | Add the `enable_cancellation_fallback` flag + gated next-catchable fallback logic (additive to Story 1.4). |
| `tests/test_cancellation.py` (new) or extend `tests/test_optimiser.py` | Synthetic-data unit tests for the three ACs. |
| `tests/features/cancellation.feature` (new) or extend the optimiser feature | `@offline` BDD scenarios mapping ACs 1–2. |

### Testing standards (AD-12, testing convention)
- Test-first, `@offline` by default, no network/credentials (NFR2/FR21).
- Synthetic cancelled `Service`s only — a cancelled service is one with `cancelled=True` and/or destination actual `None` plus a `late_canc_reason`.
- Cover a cross-midnight next-catchable case (AD-4) so the fallback shares the origin-day-relative minute base and never yields a `−1435`/`+1445` artefact.
- Determinism assertion (AD-10): identical input → identical output.

### Project Structure Notes
- Pure-core change only; sits behind the composition root (AD-8). No adapter or CLI wiring in this story.
- Aligns with the Structural Seed: `trainline/engine/optimiser.py` holds the "per-day max-payout optimise + gated cancellation path (AD-6)".

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-6] gated cancellation seam; #AD-10 deterministic optimiser; #AD-1/#AD-2 pure core & deps; #AD-4 delay arithmetic ownership
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR12] cancellation fallback; #§9 OQ1
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#Cancellation handling (fallback only) — FR12 / OQ1]
- Depends on Stories 1.2 (`engine.models`), 1.3 (`engine.delay`), 1.4 (`engine.optimiser`); consumes `Service.cancelled` set by `hsp_client` (Story 2.3)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
