# Story 3.2: Storage — write claims as CSV + JSON, sorted

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want claim output I can eyeball and re-use,
so that I can verify each row against SWR before filing.

## Acceptance Criteria

1. **Every claim row carries the SWR-form fields.** Given a list of `Claim`s, when written, each row carries: journey date, origin→destination, scheduled departure, scheduled arrival, actual arrival, delay (min), band, and delay/cancellation reason. *(Epic 3 AC; FR13, AD-3)*
2. **Both CSV and JSON are produced, surfacing the band — not £.** Given a run's results, when stored, both a CSV file (human-checkable, one row per claim) and a JSON file (structured, for later phases) are produced; both surface the band/percentage, never a £/pence figure. *(Epic 3 AC; FR14, AD-11)*
3. **Output is sorted by date then direction.** Given multiple days and directions, when written, output is ordered by date ascending, then direction (outbound before inbound) so a week reads at a glance. *(Epic 3 AC; FR15)*

> **TDD (AD-12):** Write these ACs as failing `@offline` pytest-bdd/unit tests first (build `Claim`s in-memory, write, assert file contents), watch them fail, then implement `adapters/storage`. No network, no credentials.

## Tasks / Subtasks

- [ ] **Task 1 — Define the SWR-form field order and `Claim` → row mapping (AC: 1)**
  - [ ] Fix the canonical column order once, in `storage`: `journey_date, origin, destination, scheduled_departure, scheduled_arrival, actual_arrival, delay_min, band, reason` (FR13). Derive it from `Claim` fields (AD-3); do not invent fields not on `Claim`.
  - [ ] This is the **only** module that serialises `Claim` (AD-3) — no serialisation logic in `engine` or elsewhere.
- [ ] **Task 2 — Format origin-day-relative minutes back to human HH:MM (AC: 1)**
  - [ ] `Claim` times are `int` origin-day-relative minutes (AD-4). Convert to `HH:MM` for the CSV/SWR fields using `mod 1440` (a 00:15 arrival stored as `1455` renders `00:15`). This is the **inverse** of Story 2.3's `HHMM`→minutes parsing and belongs here, not in the engine.
  - [ ] `delay_min` is emitted as a plain integer count of minutes (not HH:MM).
  - [ ] Decide and document the render for a `None` actual arrival (cancelled/unarrived) — e.g. empty string; the engine already excludes these from claims, so in practice claim rows have concrete actuals, but be defensive.
- [ ] **Task 3 — Write CSV (AC: 1, 2)**
  - [ ] Use the stdlib `csv` module. Header row = the FR13 field names; one data row per `Claim`.
  - [ ] Band surfaced as its label/percentage (e.g. `15-29` / `12.5`), never £ (AD-11).
- [ ] **Task 4 — Write JSON (AC: 2)**
  - [ ] Emit structured JSON (list of claim objects, or grouped by day) that a later phase (email digest, auto-filer) can consume without re-parsing CSV. Keys mirror the FR13 fields.
  - [ ] Deterministic ordering and stable key names (NFR1/NFR4 — same input → same file bytes where practical).
- [ ] **Task 5 — Sort output by date then direction (AC: 3)**
  - [ ] Sort claims by `(journey_date ASC, direction)` with outbound before inbound. Apply the same order to both CSV rows and JSON entries so they agree.
- [ ] **Task 6 — Tests (AC: 1, 2, 3)**
  - [ ] `tests/test_storage.py` (or `.feature` + steps): build `Claim`s spanning ≥2 days and both directions; write to `tmp_path`; assert CSV has exact FR13 columns, HH:MM formatting (incl. a cross-midnight case), integer delay, band present and no `£`; assert JSON round-trips to the same data; assert both are sorted date-then-direction. All `@offline`.

## Dev Notes

### Why this story exists
`storage` is the output edge of the pipeline: it turns the engine's pure `Claim`s into the two files Simon actually uses — a CSV he eyeballs against the SWR site before filing (SM1/CM2), and a JSON structured feed for the roadmap's later phases (email digest, auto-filer). It is a leaf adapter with no dependencies on other adapters.

### Where this sits in the package (Structural Seed)
```text
trainline/adapters/storage.py   # Claim -> CSV + JSON (this story)
```
Built on the scaffold from Story 1.1; consumes `Claim`/`DayResult` from Story 1.2 (`engine.models`); wired by `cli.py` in Story 3.3.

### Dependency rules (AD-2, AD-3, AD-9)
- `adapters/storage` imports **`trainline.engine.models` only** — never another adapter (`config`, `hsp_client`), never `engine.delay`/`engine.optimiser`.
- `Claim` → CSV/JSON serialisation happens **only here** (AD-3). If you find yourself formatting a `Claim` anywhere else, that is a boundary violation the Story 1.1 import-boundary test should ideally catch.

### The band/percentage, not £ (AD-11, FR14, OQ2)
MVP surfaces the SWR **band** and its numeric percentage (open day return track: `15-29→12.5`, `30-59→25`, `60-119→50`, `120+→100`), **not** a £ figure. What each percentage is a percentage *of*, and whether two claims stack, is unresolved (OQ2) — so do not compute or emit money. Surface exactly what the engine gives (band + payout percentage). SM1 (Simon verifies each row against the live SWR form before filing) is the correctness net.

### SWR-form field mapping (FR13, addendum §"SWR claim form")
The published SWR online form needs: journey date; origin and destination; scheduled and actual arrival times (or cancellation details); ticket details; payout method. The MVP CSV/JSON covers the *journey* fields (date, O→D, sched dep, sched arr, actual arr, delay, band, reason); ticket details and payout method are entered by Simon at filing time (manual submission is the MVP per addendum seams table). Exact live-form field names are OQ3 — do not over-fit the column names to a form we haven't validated; keep them clear and human-readable.

### Time formatting (AD-4) — the inverse of Story 2.3
Internally all times are `int` minutes relative to the service's origin day; a post-midnight time carries `+1440`. Render with `f"{(m % 1440)//60:02d}:{(m % 1440)%60:02d}"`. Cross-midnight example: `1455` → `00:15`. `hsp_client` (Story 2.3) owns `HHMM`→minutes; `storage` owns minutes→`HH:MM`. The engine never formats time.

### Sorting (FR15)
Sort by date ascending, then direction with **outbound (GOD→WAT) before inbound (WAT→GOD)**. `Claim`/`DayResult` should expose enough to know a claim's direction (origin/destination CRS or an explicit direction field from Story 1.2). Keep CSV and JSON in the same order.

### Testing standards (AD-12, testing convention)
- Test-first, `@offline`, no network/creds. Drive with in-memory `Claim`s (no HSP, no engine run needed — construct `Claim`s directly).
- Write to `tmp_path`; never write into the repo tree during tests.
- Cover: exact FR13 columns and order; HH:MM formatting incl. a cross-midnight (`00:15`) case; integer `delay_min`; band/percentage present and **no `£`**; CSV↔JSON agreement; multi-day/both-direction sort order.
- Determinism (NFR1/NFR4): same `Claim` list → identical file output.

### Stack
Python 3.10+ (dev 3.12); stdlib `csv` + `json` only — no new dependencies. `pytest>=7.0`, `pytest-bdd>=7.0`.

### Project Structure Notes
- Output file location/paths should come from `config` (Story 3.1) and be passed in by `cli.py` (Story 3.3) — do not hard-code an absolute output dir inside `storage`; accept a target directory/paths argument so it stays a pure adapter (no global state, AD "State & cross-cutting").
- The old monolith wrote `Results/outboundLateTrains.csv` with a bespoke header ("Outbound Train To WAT") and a different, old-model schema — that is **removed** in Story 1.1 and must **not** be reproduced. This story defines the new-model schema from scratch.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2] — user story + ACs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR13] SWR fields; #FR14 CSV+JSON, band not £; #FR15 sorted by date then direction
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#SWR claim form — field mapping & constraints]; #SWR Delay Repay band table (open day return track)
- [Source: ARCHITECTURE-SPINE.md#AD-3] serialisation only in storage; #AD-11 band/percentage not £; #AD-2/#AD-9 dependency direction; #Consistency Conventions (dates ISO, CSV+JSON sorted)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
