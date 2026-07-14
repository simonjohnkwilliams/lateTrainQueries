# Story 1.4: Feasibility, max-payout optimisation, tie-break

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want the per-day optimal claimable combination,
so that I recover the maximum without infeasible picks.

## Acceptance Criteria

1. **Feasibility is strict on actual times, no buffer.** Given an inbound whose *actual* WAT departure precedes (or equals) the outbound's *actual* WAT arrival, the pair is **infeasible**. The rule is `feasible(out, in) ⇔ in.actual_departure_WAT > out.actual_arrival_WAT` — strict `>`, so equal times are **not** feasible, and MVP applies **no interchange buffer**. *(Epic 1 AC; FR8, AD-10)*
2. **Max-total-payout selection, 0/1/2 rows, status passed through.** Given all services for a day, `optimise` returns the combination with the **maximum total payout** as a `DayResult` carrying 0, 1, or 2 `Claim`s. The `DayResult.status` (fetch outcome) is passed through **unchanged**. *(Epic 1 AC; FR9, AD-5)*
3. **Band beats earliness; earliness breaks equal bands.** Two 16-minute-late outbounds at 07:00 and 08:00 → **07:00** chosen (equal band → earliest). But 07:00 = 16 min (band 15–29, payout 12.5) vs 08:00 = 39 min (band 30–59, payout 25) → **08:00** wins (higher payout beats earliness). *(Epic 1 AC; FR9, FR10; addendum worked examples)*
4. **Deterministic, total tie-break.** On equal total payout, order alternatives by (1) fewer claim rows, then (2) earliest outbound departure, then (3) earliest inbound departure. Identical input yields identical output. *(Epic 1 AC; FR10, FR11, AD-10)*

> **TDD (AD-12):** Encode all four ACs as failing pytest-bdd scenarios first (the addendum worked examples map almost 1:1 to Gherkin), with TDD unit tests underneath for `feasible()`, the objective, and the tie-break comparator. Watch red → green. No criterion ships without a test.

## Tasks / Subtasks

- [ ] **Task 1 — Feasibility predicate (AC: 1)**
  - [ ] Implement `feasible(out, in) -> bool` using `in.actual_departure_WAT > out.actual_arrival_WAT` (strict, actual times, no buffer).
  - [ ] Both legs must be claimable candidates first (see Task 2 filtering) before a pair is even considered.
  - [ ] Unit tests: `>` strictly; equal minute → False; obvious feasible/infeasible cases.
- [ ] **Task 2 — Candidate set construction (AC: 2)**
  - [ ] From the day's outbound and inbound services, build the claimable candidate lists: for each service compute destination delay → band → payout (delegating to `engine.delay`, Story 1.3); **discard** band == `Band.NONE` (sub-15-min).
  - [ ] **Skip** any service where `cancelled is True` **or** the destination actual arrival is `None` (AD-3) — never treat a missing actual as delay 0. (Cancellation *fallback* is Story 1.5 and stays off — see boundary note.)
  - [ ] Candidate combinations = every feasible (out, in) pair **plus** single-leg options (out-only, in-only) **plus** the empty combination (0 rows).
- [ ] **Task 3 — Objective + selection (AC: 2, 3)**
  - [ ] Objective: total payout = numeric sum of `payout(band)` across the combination's legs — **numeric sum, not ordinal band comparison** (FR9).
  - [ ] Objective signature accepts an **optional per-day cap** (default `None`) pre-provisioning OQ2: `None` → plain `Σ payout`; a set cap → `min(Σ payout, cap)`. Wire the parameter now even though MVP always passes `None` (AD-10, OQ2).
  - [ ] Select the maximum-scoring combination; emit its 0/1/2 `Claim`s into a `DayResult`, **passing `status` through unchanged** (AD-5).
- [ ] **Task 4 — Deterministic total tie-break (AC: 3, 4)**
  - [ ] Comparator on equal total payout: (1) fewer claim rows, (2) earliest outbound departure, (3) earliest inbound departure. Total order — covers pair-vs-pair, single-vs-single, pair-vs-single.
  - [ ] Deterministic iteration (sort candidate services by departure before searching) so identical input → identical output.
  - [ ] Determinism test: run `optimise` twice on the same input, assert equal results.
- [ ] **Task 5 — Public entry point + purity (AC: 2, 4)**
  - [ ] Expose `optimise(days, config) -> list[DayResult]` in `trainline/engine/optimiser.py` (AD-1) — one `DayResult` per input day, status preserved.
  - [ ] No I/O, no global mutable state, `config` passed explicitly. The Story 1.1 import-boundary test must stay green.
- [ ] **Task 6 — BDD acceptance scenarios (AC: 1–4)**
  - [ ] `tests/features/optimiser.feature` + steps: the two worked examples (AC3), a feasibility-rejection scenario (AC1), a tie-break scenario (AC4), and a 0-row day. `@offline`.

## Dev Notes

### Why this story exists
This is the correctness heart of the product (NFR1). It owns the two rules that decide money: **feasibility** (can Simon actually make the return) and the **max-total-payout selection with a total tie-break**. Getting it deterministic and pure (AD-10, AD-1, FR11) is what lets the same input always yield the same claims and lets the core run unchanged as a CLI now and a Lambda later.

### The per-day algorithm (addendum, made precise)
For a date D with `OUT` (GOD→WAT) and `IN` (WAT→GOD) services:
1. Per service: `delay = actual_arrival − scheduled_arrival` at its destination → band → discard sub-15-min (`Band.NONE`).
2. `feasible(out, in) ⇔ in.actual_departure_WAT > out.actual_arrival_WAT` (**actual** times — when Simon would really be free to travel back).
3. Search all feasible (out, in) pairs **plus** single-leg options (out-only, in-only) **plus** empty → choose **maximum total payout** (sum of `payout(band)`).
4. Tie-break equal totals: (1) fewer rows, (2) earliest outbound, (3) earliest inbound (FR10).
5. Result: 0, 1, or 2 claim rows.

Worked examples (become BDD scenarios):
- Two 16-min outbounds 07:00 & 08:00 (both band 15–29, payout 12.5) → pick **07:00** (equal band, earliest).
- 07:00 = 16 min (12.5) vs 08:00 = 39 min (band 30–59, payout 25) → pick **08:00** (higher payout beats earliness).
- A lone higher-band leg beats an early-outbound-plus-claimable-return combination only when its `payout` strictly exceeds the combination's **summed** `payout` — this is why the objective must sum numerics, not compare labels.

### `payout` values (addendum, open-day-return track)
`none → 0`, `15–29 → 12.5`, `30–59 → 25`, `60–119 → 50`, `120+ → 100`. Sourced from `engine.delay.payout(band)` (Story 1.3) — do **not** re-define the table here (AD-11 single owner). **Inconsistency to watch:** the addendum/PRD payout for 15–29 is **12.5** (a float), but ARCHITECTURE-SPINE AD-11 states `payout(band) -> int`. The optimiser only sums whatever `engine.delay.payout` returns, so it is unaffected numerically — but the return *type* is contradictory between docs. Flagged in Open Questions; the optimiser must not hard-code the type assumption (sum works for `int` or `float`).

### Architecture guardrails (AD-10, AD-1, AD-2, AD-5)
- **Sole ownership (AD-10):** feasibility and tie-break live **only** in `engine.optimiser`. No other module re-implements them.
- **Optional per-day cap (AD-10 / OQ2):** the objective is a single function taking an optional cap so OQ2's "does SWR cap stacked claims?" becomes a value change (`max Σ` → `max min(Σ, cap)`), not a structural rewrite. Provision the parameter now; MVP passes `None`.
- **Purity (AD-1, FR11):** `engine/*` imports nothing I/O and performs no I/O. `optimise(days, config) -> list[DayResult]`; a bare `list[Claim]` is illegal — it can't express a no-claim or failed day.
- **Inward deps (AD-2):** optimiser imports `engine.models` and `engine.delay` only.
- **Status pass-through (AD-5):** the engine copies `DayResult.status` unchanged; it does not compute or reinterpret fetch outcomes. A `FETCH_FAILED` day is not "0 claims" — it is "not analysed".
- **Skip rule (AD-3):** ignore services with `cancelled is True` or destination actual `None`; missing time ≠ delay 0.

### Scope boundary — cancellation fallback is NOT here
FR12 cancellation-derived claims are **Story 1.5**, behind a flag that stays **off** until OQ1 (AD-6). This story's optimiser sees only actual-late candidates. Do not add cancellation logic; leave the seam for 1.5 (the objective/candidate construction should be extendable, not pre-built for it).

### Dependencies / sequencing
- **Requires:** Story 1.2 (`Service`, `Claim`, `DayResult`, `Band` — data shapes and `int | None` actual fields, AD-3/AD-4) and Story 1.3 (`band()`, `payout()`).
- **Feeds:** Story 1.5 (adds the gated cancellation path to this optimiser), Story 3.3 (CLI calls `optimise`), Story 3.2 (storage serialises the emitted `Claim`s).
- All times are integer origin-day-relative minutes (AD-4) — the optimiser compares ints; it never parses `HHMM` (that's `hsp_client`, AD-4).

### Testing standards (AD-12, testing convention)
- Test-first: scenarios/units written and seen to fail before implementation.
- Offline by default (NFR2): pure in-memory `Service`/`DayResult` fixtures; **no** network, **no** credentials, no disk.
- Cover: feasibility strictness (`>` incl. equal-minute rejection), single-vs-pair selection, both worked examples, all three tie-break levels, a 0-claim day, status pass-through (including a `FETCH_FAILED` day emitting no claims but retaining its status), and determinism (double-run equality).
- Unit-drive the tie-break comparator directly (it's the subtlest logic) in addition to the end-to-end BDD.

### Project Structure Notes
- Implementation in `trainline/engine/optimiser.py` (stub created in Story 1.1). Tests in `tests/test_optimiser.py` and `tests/features/optimiser.feature` (+ steps module).
- No structural variance from the Architecture "Structural Seed".

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4] — user story + ACs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#The per-day optimisation, precisely] — algorithm + worked examples; #SWR Delay Repay band table — payout values; #OQ2 — cap
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR8] feasibility; #FR9 max-payout 0/1/2; #FR10 tie-break; #FR11 pure core
- [Source: ARCHITECTURE-SPINE.md#AD-10] deterministic total optimiser + optional cap; #AD-1 pure core; #AD-2 inward deps; #AD-3 skip cancelled/None; #AD-5 status pass-through; #AD-6 cancellation gated (Story 1.5); #AD-11 band/payout ownership
- Depends on Story 1.2 (models) and Story 1.3 (delay/band/payout)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
