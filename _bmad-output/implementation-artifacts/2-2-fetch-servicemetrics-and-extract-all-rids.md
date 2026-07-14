# Story 2.2: Fetch serviceMetrics and extract ALL RIDs

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want every service on the route/window fetched for both directions,
so that no claimable train is missed.

## Acceptance Criteria

1. **serviceMetrics POST body is correct.** When `serviceMetrics` is called, the POST body is exactly `{from_loc, to_loc, from_time, to_time, from_date, to_date, days: 'WEEKDAY'}` and the endpoint is `https://hsp-prod.rockshore.net/api/v1/serviceMetrics`. *(Epic 2 AC; FR1)*
2. **ALL RIDs extracted (the FR3 fix).** Given a metrics response, every `Services[].serviceAttributesMetrics.rids` entry is returned — across **all** services and **all** RIDs within each service — not just `Services[0]...rids[0]`. No service on the route is silently dropped. *(Epic 2 AC; FR3)*
3. **Both directions queried.** A single run queries **both** the outbound (GOD→WAT) and inbound (WAT→GOD) directions. *(Epic 2 AC; FR1)*

> **TDD (AD-12):** Write these as failing pytest-bdd/unit scenarios first, watch them fail against the stub, then implement. The AC2 "all RIDs" scenario is the anchor — it is the concrete FR3 regression the old code got wrong.

## Tasks / Subtasks

- [ ] **Task 1 — `fetch_service_metrics` on the HSP client (AC: 1)**
  - [ ] Add a method/function in `trainline/adapters/hsp_client.py` that POSTs to `.../serviceMetrics` via the **injectable transport** from Story 2.1 (no direct `requests` call at call sites).
  - [ ] Build the body `{from_loc, to_loc, from_time, to_time, from_date, to_date, days: 'WEEKDAY'}` from the passed route/window/date arguments.
  - [ ] Apply HTTP basic auth via the client constructed in Story 2.1.
- [ ] **Task 2 — Extract every RID (AC: 2, FR3)**
  - [ ] Parse the metrics JSON and collect `rids` from **every** element of `Services[]` at `serviceAttributesMetrics.rids`.
  - [ ] Flatten into a single list; **de-duplicate** while preserving first-seen order (a RID can legitimately appear once per service, but guard against accidental repeats). Document the de-dup choice in a comment.
  - [ ] Tolerate services with an empty/absent `rids` list (skip, don't crash).
- [ ] **Task 3 — Query both directions (AC: 3, FR1)**
  - [ ] Provide the direction-pair behaviour: one metrics fetch for outbound (from_loc=origin, to_loc=dest) and one for inbound (from_loc=dest, to_loc=origin), returning RIDs tagged by direction so downstream (2.3/optimiser) knows which leg each RID belongs to.
  - [ ] The concrete route/window/dates are injected by config (Story 3.1); this story only needs to prove both directions are issued and their RIDs kept distinct.
- [ ] **Task 4 — Tests, offline + recorded (AC: all)**
  - [ ] `tests/test_fetch_metrics.py`.
  - [ ] `@recorded`: drive extraction against the real `tests/fixtures/recorded_metrics_2026-05-28.json` and assert the full RID set is returned (count > 1, i.e. proves we don't stop at `[0]`).
  - [ ] `@offline`: fake-transport test asserting the exact POST body dict and endpoint for AC1.
  - [ ] `@offline`: test that a run issues two metrics POSTs (outbound + inbound) with swapped `from_loc`/`to_loc` (AC3).
  - [ ] All tests run with no network and no credentials.

## Dev Notes

### Why this story exists
This is the acquisition entry point: it lists *what ran* on the route so every candidate train reaches the engine. The old monolith's `generatePidList` took `rids[0]` of each metrics file — silently discarding every additional RID and therefore claimable trains. FR3 exists specifically to kill that bug; AC2 is its executable proof.

### The FR3 bug being fixed (from the removed monolith)
Old `TrainLine/TestFileGenerator.py::generatePidList` effectively did `rids[0]` per service/file. HSP returns **multiple** RIDs per matched service pattern; taking the first drops real services. New behaviour: return the union of all `rids` across all `Services[]`.

### HSP serviceMetrics shape (addendum, grounded from fixtures)
```
{ header: { from_location, to_location },
  Services: [ { serviceAttributesMetrics: { origin_location, destination_location,
                                            gbtt_ptd, gbtt_pta, toc_code,
                                            matched_services, rids: [...] },
               Metrics: [...] } ] }
```
- RIDs live at `Services[].serviceAttributesMetrics.rids` — extract **all**.
- Endpoint (POST): `https://hsp-prod.rockshore.net/api/v1/serviceMetrics`.
- Body uses `days: 'WEEKDAY'`.

### Boundary rules (AD-2, AD-3)
- All HSP JSON and field names (`Services`, `serviceAttributesMetrics`, `rids`) stay **inside** `hsp_client`. The engine never sees them. Mapping raw JSON → `Service` is **Story 2.3**, not here — this story returns RIDs (plus direction) as the adapter's own intermediate type/list.
- `hsp_client` may import `trainline.engine.models` only; no other adapter.

### Dependencies / sequencing
- **Depends on Story 2.1** for the injectable transport, auth, and the `REQUESTS_CA_BUNDLE`/AVG-TLS handling (NFR3). Do not re-invent the HTTP seam here.
- Route/window/dates are supplied by **Story 3.1** config at wire-up (Story 3.3). For this story, accept them as parameters.
- Feeds **Story 2.3** (serviceDetails per RID) and **Story 2.5** (fetch-failure rollup — a failed metrics fetch for a direction makes the day `FETCH_FAILED`).

### Testing standards (AD-12, NFR2, FR21)
- Test-first; offline by default via the injected fake transport.
- Ground the RID-extraction test in the **real** recorded fixture (`recorded_metrics_2026-05-28.json`) per FR21 — this is the anti-`rids[0]` guarantee on real Darwin data.
- Keep `live`-marked scenarios deselected by default (`pytest.ini` `addopts = -m "not live"`).

### Project Structure Notes
- Lives in `trainline/adapters/hsp_client.py` (extends the 2.1 stub). Tests in `tests/test_fetch_metrics.py`.
- No engine or storage changes.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2] — user story + ACs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR1] both directions; #FR3 all RIDs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#HSP JSON shape reference] serviceMetrics shape + endpoint + WEEKDAY payload
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-2] inward-only deps; #AD-3 no HSP JSON in engine; #AD-7 re-implement acquisition fresh
- Fixture (preserved by Story 1.1, FR21): `tests/fixtures/recorded_metrics_2026-05-28.json`
- Replaces old `TrainLine/TestFileGenerator.py::generatePidList` (rids[0] bug) — removed in Story 1.1

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
