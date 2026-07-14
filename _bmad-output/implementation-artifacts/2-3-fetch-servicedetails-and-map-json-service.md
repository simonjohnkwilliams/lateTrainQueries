# Story 2.3: Fetch serviceDetails and map JSON → Service

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want raw HSP detail responses turned into clean domain `Service`s,
so that the engine never sees HSP JSON.

## Acceptance Criteria

1. **`serviceDetails` is called per RID and `locations[]` is parsed.** Given a RID, the client POSTs body `{"rid": <rid>}` to the `serviceDetails` endpoint and parses `serviceAttributesDetails.locations[]` from the response. *(Epic 2 AC; FR2)*
2. **Times become origin-day-relative integer minutes; empty actuals map to `None`.** Given a location's times, `gbtt_ptd`/`gbtt_pta`/`actual_td`/`actual_ta` (HHMM) become `int` minutes relative to the service's origin day on the resulting `Service` (a calling point past midnight carries `+1440`, AD-4); an empty actual string maps to `actual_* is None` (AD-3), not `0`. *(Epic 2 AC; FR2, AD-3, AD-4)*
3. **Cancellation is surfaced as a raw signal only.** Given empty actual times **plus** a non-empty `late_canc_reason`, the mapper sets `Service.cancelled = True` and carries `reason`; it computes **no** fallback delay (that is the engine's gated job, Story 1.5). *(Epic 2 AC; AD-6)*

> **TDD (AD-12):** Write each AC as a failing pytest-bdd/unit test first (against the real `recorded_details_*.json` fixtures plus small synthetic dicts), watch it fail, then implement the mapper until green. No criterion ships without a test.

## Tasks / Subtasks

- [ ] **Task 1 — `serviceDetails` fetch on the injectable seam (AC: 1)**
  - [ ] Add a `fetch_service_details(rid)` path to `trainline/adapters/hsp_client.py` that POSTs `{"rid": rid}` to `https://hsp-prod.rockshore.net/api/v1/serviceDetails` via the injectable transport/session from Story 2.1 (basic auth, `REQUESTS_CA_BUNDLE` honoured). No new network code — reuse the 2.1 seam.
  - [ ] Return the parsed `serviceAttributesDetails` dict (or the raw response for the mapper to consume).
- [ ] **Task 2 — HHMM → origin-day-relative minutes (AC: 2)**
  - [ ] Implement a private `_to_minutes(hhmm)` helper: `""`/absent → `None`; `"HHMM"` → `int(hh)*60 + int(mm)`.
  - [ ] Implement origin-day normalisation across `locations[]`: walk calling points in list order; track the running reference; when a subsequent time is *less* than the previous non-null time on the same track, add `1440` (past-midnight wrap). Scheduled and actual for one calling point must share the same day base so `actual − scheduled` is the true signed delay.
  - [ ] Keep the origin calling point (empty `gbtt_pta`/`actual_ta`) and the terminus (empty `gbtt_ptd`/`actual_td`) handled without crashing.
- [ ] **Task 3 — Map to `engine.models.Service` (AC: 2, 3)**
  - [ ] Given the configured origin/destination CRS for the direction, pick the origin calling point (its `gbtt_ptd`/`actual_td`) and the destination calling point (its `gbtt_pta`/`actual_ta`) from `locations[]` and populate a `Service`: `rid`, `date_of_service`, direction/origin/destination CRS, `scheduled_departure`, `scheduled_arrival`, `actual_departure` (`int | None`), `actual_arrival` (`int | None`), `cancelled`, `reason`.
  - [ ] Empty actual → `None` (AD-3), never `0`.
  - [ ] Empty actuals + non-empty `late_canc_reason` → `cancelled = True`, `reason = late_canc_reason`; do **not** compute any fallback delay (AD-6).
- [ ] **Task 4 — Tests, offline + recorded (AC: 1, 2, 3)**
  - [ ] `tests/test_fetch_details.py` (see Testing standards). Fail-first, then green. No network, no credentials.

## Dev Notes

### Why this story exists
This is the boundary where raw HSP JSON becomes the clean domain `Service` (AD-3). It is the **only** place in the codebase allowed to know HSP field names (`gbtt_pta`, `actual_ta`, `late_canc_reason`, `locations`, …). Everything downstream (`engine.delay`, `engine.optimiser`, `storage`) works purely on `Service`/`Claim`/`DayResult`. Get this mapping right and the cross-midnight delay bug (AD-4) is impossible for the rest of the system.

### Target module & dependency rules (AD-2, AD-3)
- Lives in `trainline/adapters/hsp_client.py` (extends Stories 2.1 auth/TLS/seam and 2.2 metrics/RIDs).
- May import `trainline.engine.models` **only** — never another adapter, never `engine.delay`/`engine.optimiser`. The import-boundary test from Story 1.1 will enforce this.
- Produces `engine.models.Service` instances (fields defined in Story 1.2). If a field you need is missing from `Service`, that is a signal to reconcile with Story 1.2 — do not invent a second shape here (AD-3).

### CRITICAL — origin-day-relative minutes (AD-4)
HSP gives bare `HHMM` per calling point with no date. A GOD→WAT service that departs 23:50 and arrives 00:15 must yield `delay = actual − scheduled` around a shared base, not `−1435`/`+1445`.
- Convert each `HHMM` to raw minutes-of-day, then normalise the whole `locations[]` sequence onto the **service's origin day**: as you walk calling points in order, if a time drops below the previous one it has crossed midnight — add `1440` to it (and keep adding to subsequent points).
- Apply the same offset to a calling point's scheduled and actual so they stay on the same base.
- This normalisation is owned **here**; `engine.delay.calculate_delay` (Story 1.3) only subtracts two already-normalised ints. No other module parses `HHMM`.

### AD-6 — cancellation is a raw signal, nothing more
HSP has **no** cancellation flag. The only signal is empty `actual_ta`/`actual_td` **and** a free-text `late_canc_reason`. Set `Service.cancelled = True` and carry `reason`. Do **not** compute the next-catchable-service fallback delay here — that is gated engine logic (Story 1.5, OQ1). Mapping a cancelled service must not raise.

### HSP `serviceDetails` JSON shape (grounded from `recorded_details_*.json`)
```json
{ "serviceAttributesDetails": {
    "date_of_service": "2026-05-28", "toc_code": "SW", "rid": "202605287679094",
    "locations": [
      {"location": "HAV", "gbtt_ptd": "0803", "gbtt_pta": "",     "actual_td": "0803", "actual_ta": "",     "late_canc_reason": ""},
      {"location": "GOD", "gbtt_ptd": "0848", "gbtt_pta": "0847", "actual_td": "0849", "actual_ta": "0848", "late_canc_reason": ""},
      {"location": "WAT", "gbtt_ptd": "",     "gbtt_pta": "0931", "actual_td": "",     "actual_ta": "0933", "late_canc_reason": ""}
    ] } }
```
- Scheduled: `gbtt_ptd` (dep) / `gbtt_pta` (arr). Actual: `actual_td` / `actual_ta`.
- **Origin** calling point has empty `gbtt_pta`/`actual_ta`; **terminus** has empty `gbtt_ptd`/`actual_td`. The service's own origin (e.g. `HAV`) may differ from the route origin (`GOD`) — pick the calling points by the configured CRS codes, not by list position.
- For GOD→WAT: departure = the `GOD` calling point's `gbtt_ptd`/`actual_td`; arrival = the `WAT` calling point's `gbtt_pta`/`actual_ta`. Inbound WAT→GOD mirrors this.

### Files being touched
- **UPDATE** `trainline/adapters/hsp_client.py` — add the details fetch + JSON→`Service` mapper (stub created in Story 1.1; auth/TLS/seam in 2.1; metrics/RIDs in 2.2).
- **READ/USE** `trainline/engine/models.py` — `Service` shape (Story 1.2); do not redefine it here.
- **NEW** `tests/test_fetch_details.py`.

### Testing standards (AD-12, NFR2, FR21)
- `tests/test_fetch_details.py`, all offline — no network, no credentials.
- **`@recorded`** — map the real `recorded_details_*.json` fixtures (real 2026-05-28 Darwin data) through the mapper and assert the produced `Service` for the GOD and WAT calling points has the right scheduled/actual minutes and `cancelled = False`. This is the FR21 grounding.
- **`@offline`** synthetic cases:
  - Cross-midnight leg (e.g. sched dep `2350`, arr `0015`) → normalised minutes give a correct small positive delay, not `−1435`/`+1445` (AD-4).
  - Empty actual arrival → `actual_arrival is None` (not `0`) (AD-3).
  - Empty actuals + `late_canc_reason = "Cancelled: signalling failure"` → `cancelled is True` and `reason` carried, no delay computed (AD-6).
- Drive the fetch through the injectable seam (Story 2.1) with a fake transport; assert the POST body is exactly `{"rid": <rid>}` and the URL is the `serviceDetails` endpoint (AC1).

### Stack
Python 3.10+ (dev 3.12), `requests>=2.31`, `pytest>=7.0`, `pytest-bdd>=7.0`.

### Project Structure Notes
- No new modules — this fills in `adapters/hsp_client.py` alongside 2.1/2.2. The old `TrainLine/TestFileGenerator.py` mapping (`generateLateTrainObject`, HHMM `calculate_delay`) is **not** carried forward (AD-7, removed in Story 1.1); its cross-midnight-naïve arithmetic is exactly what AD-4 fixes.
- `date_of_service` from the response is the canonical day key used later by `serviceMetrics` assembly (Story 2.5) and `storage` sorting (Story 3.2).

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-3] single data shape / int|None; #AD-4 origin-day-relative minutes; #AD-6 cancellation raw signal; #AD-2 dependency direction
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR2]
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#HSP JSON shape reference] serviceDetails shape, empty origin/terminus fields
- Grounding fixtures: `tests/fixtures/recorded_details_202605287679094.json` (+ the other 2026-05-28 captures)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
