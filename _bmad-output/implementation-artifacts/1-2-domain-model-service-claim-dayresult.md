# Story 1.2: Domain model — `Service`, `Claim`, `DayResult`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want the single source-of-truth data shapes,
so that the engine and adapters never diverge on representation.

## Acceptance Criteria

1. **`engine.models` is the single source of the data shape.** `trainline/engine/models.py` defines `Service`, `Claim`, and `DayResult` with the agreed fields, and **no other module in the package defines these shapes**. Raw HSP JSON→`Service` mapping and `Claim`→CSV/JSON serialisation live elsewhere (in adapters, later stories) — `models` holds only the shapes. *(Epic 1 AC; AD-3)*
2. **A missing actual arrival is `None`, never `0`.** When a `Service` is built for a train with no recorded actual arrival, `actual_arrival is None` (and likewise `actual_departure`), distinct from an on-time `0`. `cancelled` is representable as a boolean. The engine must be able to tell "no actual recorded" apart from "arrived exactly on time". *(Epic 1 AC; AD-3, AD-4)*
3. **Season tickets require no field change later (FR18).** The model can represent a future season-ticket claim track without altering any field on `Service`, `Claim`, or `DayResult` — the ticket-type/payout dimension is expressible as a parameter to banding/payout (Story 1.3), not a shape change here. *(Epic 1 AC; FR18)*
4. **`DayResult` can express no-claim and failed days, not just claims.** `DayResult` carries a `status` (`OK` / `FETCH_FAILED`) and 0–2 `Claim`s, so a bare `list[Claim]` is never the engine's unit of output (AD-1, AD-5). *(AD-1, AD-5)*

> **TDD (AD-12):** Encode ACs 1–4 as failing unit tests in `tests/test_models.py` first (None-not-0, cancelled representable, `DayResult` holds status + 0..2 claims, single-source-of-shape), watch them fail against the Story 1.1 stub, then implement `models.py` to green. A pytest-bdd Gherkin scenario is optional for this structural story — a `@offline` unit suite is sufficient and lighter; note the choice in the story record.

## Tasks / Subtasks

- [ ] **Task 1 — Define the enums that the shapes depend on (AC: 1, 3, 4)**
  - [ ] `Band(Enum)` with `NONE` plus the four SWR bands (`B15_29`, `B30_59`, `B60_119`, `B120_PLUS` or similar clear names). **Only the enum lives here** — `band(delay)` and `payout(band)` are functions built in Story 1.3 in `engine.delay`. Order the members so "higher band" is comparable (band ordering is ticket-agnostic — the return/single/season tracks differ only in the payout number, per addendum).
  - [ ] `FetchStatus(Enum)` with `OK` and `FETCH_FAILED` (AD-5) for `DayResult.status`.
  - [ ] `Direction`/leg representation — either an enum (`OUTBOUND`/`INBOUND`) or origin/destination CRS pair on `Service`. Choose one and be consistent (CRS codes are uppercase, e.g. `GOD`, `WAT`).
- [ ] **Task 2 — Define `Service` (AC: 1, 2)**
  - [ ] Frozen `@dataclass(frozen=True)`: `rid: str`, direction/origin/destination CRS, `date: str` (ISO `YYYY-MM-DD`), `scheduled_departure: int`, `scheduled_arrival: int` (origin-day-relative minutes, AD-4), `actual_departure: int | None`, `actual_arrival: int | None`, `cancelled: bool`, `reason: str | None`.
  - [ ] `None` (not `0`) is the only representation of "no actual recorded" (AC2, AD-3).
- [ ] **Task 3 — Define `Claim` (AC: 1)**
  - [ ] Frozen dataclass carrying the SWR-form fields (FR13): journey `date`, `origin`→`destination`, `scheduled_departure`, `scheduled_arrival`, `actual_arrival`, `delay` (min), `band: Band`, `reason: str | None`. These are the exact fields `storage` (Story 3.2) serialises — cross-reference so the two never drift.
- [ ] **Task 4 — Define `DayResult` (AC: 1, 4)**
  - [ ] Frozen dataclass: `date: str`, `status: FetchStatus`, `claims: tuple[Claim, ...]` (0–2). Use an immutable container (tuple) to preserve frozen/deterministic semantics.
- [ ] **Task 5 — Prove the invariants (AC: 1, 2, 3, 4)**
  - [ ] `tests/test_models.py`: construct a `Service` with no actual arrival → assert `actual_arrival is None`; a cancelled service is representable; a `DayResult` with `FETCH_FAILED` + zero claims is valid and distinct from `OK` + zero claims; `Claim` exposes all FR13 fields.
  - [ ] Add/extend a single-source-of-shape check (can piggyback on the Story 1.1 import-boundary/AST approach): assert `Service`/`Claim`/`DayResult`/`Band`/`FetchStatus` are defined only in `engine.models`.

## Dev Notes

### Why this story exists
`engine.models` is the contract every other module speaks (AD-3). Get the shapes right once and the HSP adapter, the optimiser, and storage all agree; get them wrong and they diverge. This story defines *only* the shapes and their enums — no behaviour. Behaviour (`calculate_delay`, `band`, `payout`) is Story 1.3; mapping/serialisation is Epics 2–3.

### Fields and the ADs that constrain them
- **AD-3 (single data shape):** `Service`, `Claim`, `DayResult` defined once, here. HSP field names (`gbtt_pta`, `actual_ta`, `rids`, `late_canc_reason`) must NOT appear in `models` — they are mapped to these clean fields only inside `hsp_client` (Epic 2). Actual-time fields are `int | None`; `None` = no actual (unarrived/cancelled).
- **AD-4 (time base):** all times are `int` minutes relative to the service's origin day (post-midnight +1440). `models` just types them `int`; the arithmetic owner is `engine.delay` (Story 1.3). No `HHMM` strings in the core.
- **AD-5 (failure ≠ no-claim):** `DayResult.status` distinguishes a trustworthy `OK` day from a `FETCH_FAILED` "not analysed" day. The engine passes status through unchanged (it does not own its meaning — `hsp_client` sets it).
- **AD-1 (pure core):** `models` imports nothing I/O. Allowed: `dataclasses`, `enum`, `typing`. The Story 1.1 import-boundary test enforces this — do not add `json`/`os`/`csv` here.
- **AD-10 (determinism):** prefer `frozen=True` dataclasses so domain objects are immutable and hashable — no accidental mutation between optimiser passes.
- **AD-11 (band/payout):** the `Band` enum is the *data*; `band(delay_min) -> Band` and `payout(band) -> number` are *functions* in `engine.delay`. Keep the enum free of payout numbers so the return/single/season tracks (addendum table) are a function concern, not a shape concern.

### FR18 — why season tickets need no field change
The SWR band **ordering** is identical across ticket types; only the payable percentage differs (addendum: return track 12.5/25/50/100 vs single 25/50/100/100 vs season proportions). So a future season-ticket track is a new `payout(...)` parameterisation in `engine.delay` (Story 1.3) and, at most, a ticket-type value threaded through `config` — **not** a new field on `Service`/`Claim`/`DayResult`. Document this reasoning in the model docstring so a later dev doesn't "helpfully" add a `ticket_type` field to `Service`.

### ⚠️ Known inconsistency to surface (payout type)
The addendum's `payout` table uses **12.5** (a non-integer), but ARCHITECTURE-SPINE AD-11 states `payout(band) -> int`. This bites in **Story 1.3**, not here (the enum carries no number), but the `Band` names you pick here should not encode a unit. Flag it for Story 1.3 to resolve (likely `float`, or integer half-percent units). Do not silently pick `int` in a way that truncates 12.5 → 12.

### Files being touched
- **UPDATE `trainline/engine/models.py`** — currently a Story 1.1 stub (module docstring only). Fill it with the enums + three dataclasses. No I/O imports.
- **NEW `tests/test_models.py`** — the invariant unit tests.
- No adapter/CLI changes in this story.

### Testing standards (AD-12, testing convention)
- Test-first, `@offline` by default, no network/credentials (NFR2). These are pure in-memory constructions — fast unit tests, no fixtures needed beyond hand-built objects.
- Keep the existing `pytest.ini` markers and `addopts = -m "not live"` untouched.

### Project Structure Notes
- Lives entirely under `trainline/engine/` (the pure core) created by Story 1.1. No structural additions beyond filling the `models.py` stub and adding one test file.
- Depends on Story 1.1 (scaffold + import-boundary test) being done first. Blocks Story 1.3 (delay/band/payout consume these shapes) and everything downstream.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-3] single data shape; #AD-4 time base; #AD-5 failure≠no-claim; #AD-1 pure core; #AD-10 determinism; #AD-11 band/payout contract
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR18] season-ticket-ready; #FR13 SWR-form claim fields
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#SWR Delay Repay band table] — return-track payout numbers (12.5/25/50/100)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
