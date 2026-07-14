# Story 1.3: Delay, band, and payout

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want delay → band → payout computed correctly,
so that a service's claimability is unambiguous.

## Acceptance Criteria

1. **Early / on-time clamps to 0.** Given an actual arrival equal to or earlier than the scheduled arrival, `calculate_delay` returns `0` (never a negative number). *(Epic 1 AC; FR6)*
2. **A 16-minute-late arrival bands and pays correctly.** Given a 16-minute-late arrival, `band(16)` = the 15–29 band and `payout(<15–29 band>)` = `12.5`. *(Epic 1 AC; FR7, AD-11)*
3. **Sub-15-minute delay is not claimable and never crashes.** Given a delay below 15 minutes, `band(delay)` = `Band.NONE` and `payout(Band.NONE) == 0` with no exception. *(Epic 1 AC; FR7, AD-11)*
4. **Cross-midnight legs compute correctly.** Given a 23:50 → 00:15 leg expressed in origin-day-relative minutes, `calculate_delay` yields the correct positive delay — not `−1435` and not `+1445`. *(Epic 1 AC; AD-4)*

> **TDD (AD-12):** Encode all four ACs as failing tests first — pytest-bdd `@offline` scenarios mapping one-to-one to the criteria, backed by `tests/test_delay.py` unit tests that TDD-drive the arithmetic and the band boundaries. Watch each fail, then pass. No network, no credentials.

## Tasks / Subtasks

- [ ] **Task 1 — `calculate_delay` (AC: 1, 4)**
  - [ ] Implement `calculate_delay(actual: int, scheduled: int) -> int` in `trainline/engine/delay.py` as `max(0, actual - scheduled)`. Inputs are **origin-day-relative integer minutes** (AD-4) — no string parsing here.
  - [ ] Unit-test the clamp (AC1): equal → 0, earlier → 0, significantly earlier → 0.
  - [ ] Unit-test cross-midnight (AC4): scheduled 00:15-next-day = `15 + 1440 = 1455`, actual `1455+` etc.; assert the signed subtraction is right and never the ±1435/±1445 artefacts.
- [ ] **Task 2 — `Band` boundaries via `band()` (AC: 2, 3)**
  - [ ] Implement `band(delay_min: int) -> Band` using `Band` imported from `trainline.engine.models` (Story 1.2). Boundaries: `<15 → NONE`, `15–29`, `30–59`, `60–119`, `120+`.
  - [ ] Unit-test every boundary edge: 14→NONE, 15→15–29, 29→15–29, 30→30–59, 59→30–59, 60→60–119, 119→60–119, 120→120+.
- [ ] **Task 3 — `payout()` (AC: 2, 3)**
  - [ ] Implement `payout(band: Band) -> <number>` on the **open day return** track: `NONE→0`, `15–29→12.5`, `30–59→25`, `60–119→50`, `120+→100`.
  - [ ] Ensure `payout(Band.NONE) == 0` (no `KeyError`/crash — AC3).
  - [ ] **Resolve the int-vs-float return type first** (see Dev Notes open question) and keep the return unit stable.
- [ ] **Task 4 — Acceptance scenarios (AC: 1–4)**
  - [ ] Add `tests/features/delay.feature` (`@offline`) with one scenario per AC and step defs in `tests/test_bdd_delay.py`.
  - [ ] Confirm `python -m pytest` is green offline with no `HSP_CREDENTIALS_FILE`.

## Dev Notes

### Why this story exists
`engine.delay` is the arithmetic heart of claimability: it converts a service's times into a delay, a delay into an SWR band, and a band into the numeric payout the optimiser (Story 1.4) will sum. Getting the boundaries and the clamp exactly right is the correctness core (NFR1).

### Ownership & purity (AD-1, AD-4, AD-11)
- **`engine.delay` is the SOLE owner of delay arithmetic (AD-4).** No other module subtracts times. `optimiser` and `storage` call `calculate_delay`/`band`/`payout`; they never re-derive a delay.
- Pure core (AD-1): `delay.py` imports **nothing I/O** — only `trainline.engine.models` (for `Band`) and pure stdlib (`enum`/`typing` if needed). The Story 1.1 import-boundary test enforces this; do not add `os`/`json`/`csv`/`requests`.
- MVP surfaces the **band / percentage**, not a £ figure (AD-11, PRD FR14).

### CRITICAL — the times seam (AD-4): parsing lives in `hsp_client`, not here
`calculate_delay` receives **already-normalised** integer minutes relative to the service's **origin day**. The HSP `HHMM`-string → minutes conversion, including the post-midnight `+1440` roll, is done in `adapters/hsp_client` (Story 2.3) — **do not** parse `HHMM` strings in `engine.delay`. This is why AC4's test builds ints directly:

- 23:50 departure origin-day = `23*60 + 50 = 1430`.
- 00:15 **next-day** arrival on the same origin base = `0*60 + 15 + 1440 = 1455`.
- If the actual arrival were 00:40 next day = `40 + 1440 = 1480`, then `calculate_delay(1480, 1455) = 25`. Correct.
- The bug this guards against: parsing 00:15 as `15` and subtracting `1430` → `−1415` (silent miss) or mishandling the roll → `+1445`. Because normalisation happens upstream, `delay` just does `max(0, actual − scheduled)` and is immune — the test proves the contract holds when inputs are correctly based.

Document this seam in the module docstring so a future dev doesn't "helpfully" add string parsing here.

### Band & payout table (PRD addendum — open day return track)
| Destination delay | `Band` | `payout` |
|---|---|---|
| 0–14 min | `Band.NONE` | 0 |
| 15–29 min | 15–29 band | 12.5 |
| 30–59 min | 30–59 band | 25 |
| 60–119 min | 60–119 band | 50 |
| 120+ min | 120+ band | 100 |

Band **ordering** is what the optimiser relies on ("higher band wins"); the emitted percentages differ from a single ticket but the ordering is identical (addendum correction note). Delay is always measured at **destination arrival** (WAT for outbound, GOD for inbound).

### ⚠️ OPEN QUESTION / SPEC INCONSISTENCY — `payout` return type (int vs 12.5)
The Architecture spine **AD-11** states `payout(band) -> int` with `payout(Band.NONE) == 0`. But the addendum's open-day-return track is **12.5** / 25 / 50 / 100 — and **12.5 is not an int**. AC2 explicitly asserts `payout == 12.5`. These conflict.

**Recommended resolution (pick before implementing, keep stable per AD-11 "does not change the return unit silently"):**
- **Preferred:** return `float` (`12.5`, `25.0`, …). Simplest, matches AC2 verbatim, MVP only surfaces the band/percentage so float precision is a non-issue at this scale (NFR5). Update AD-11's `-> int` wording to `-> float` (percentage) in the spine.
- Alternative: return `Decimal("12.5")` to avoid float-sum drift when the optimiser sums two claims — defensible under NFR1 (correctness-first), heavier ergonomically.
- Avoid: scaling to integer tenths (125/250/…) — technically honours `-> int` but breaks AC2's `== 12.5` and leaks a scaling convention into every caller.

Flag this to Simon/architect; do not silently choose. This also touches **OQ2** (payout base & stacking) — keep `payout`'s signature extensible (it may later take ticket-type/fare params) without changing the base return unit.

### Dependencies & sequence
- **Depends on Story 1.2** for `Band` (and `Service`/`Claim` shapes) in `trainline.engine.models`. If 1.2 has not landed, define/confirm `Band` there first — do not define `Band` in `delay.py` (AD-3: models is the single source of shapes; AD-11 binds `Band` to `engine.models`).
- **Feeds Story 1.4** (optimiser sums `payout(band)` across feasible pairs) and **Story 3.2** (storage emits the band per claim).
- The module stub `trainline/engine/delay.py` already exists from Story 1.1.

### Testing standards (AD-12, testing convention)
- Test-first: write `tests/features/delay.feature` (`@offline`) + `tests/test_bdd_delay.py` and `tests/test_delay.py` before implementing; see them fail, then pass.
- Offline by default (NFR2/FR21): no network, no credentials; keep `live` deselected via `pytest.ini` `addopts`.
- Cover boundary edges exhaustively (14/15/29/30/59/60/119/120) — off-by-one at 15 or 120 is exactly the kind of correctness bug NFR1 guards against.

### Project Structure Notes
- All work lands in `trainline/engine/delay.py` (+ `engine/models.py` if `Band` needs finalising) and `tests/`. No adapter or I/O code. Aligns with the Architecture "Structural Seed"; no variances.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3] — user story + ACs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#SWR Delay Repay band table] — band table + `payout(band)` values + worked examples
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR6] delay clamp; #FR7 banding/discard sub-15; #FR14 band not £
- [Source: ARCHITECTURE-SPINE.md#AD-4] times are integer origin-day-relative minutes, `delay` sole owner; #AD-11 band/payout contract (note the `-> int` conflict above); #AD-1 pure core; #AD-3 models single source; #AD-12 test-first
- Depends on: Story 1.2 (`Band` in `engine.models`). Feeds: Story 1.4 (optimiser), Story 3.2 (storage).

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
