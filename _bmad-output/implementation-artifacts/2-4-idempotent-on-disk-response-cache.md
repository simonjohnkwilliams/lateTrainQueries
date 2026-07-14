# Story 2.4: Idempotent on-disk response cache

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want fetched HSP responses cached to disk,
so that re-running a week is fast and doesn't re-hit the API.

## Acceptance Criteria

1. **Cache hit avoids the network.** For a day/service already fetched, a re-run uses the cached response and makes **no** API call (transport is not invoked). *(Epic 2 AC; NFR4)*
2. **Force-refresh re-fetches.** When force-refresh is requested, the cache is cleared (for the run's scope) and responses are re-fetched from the API. *(Epic 2 AC; FR4)*
3. **Idempotent output.** Given the same cached inputs, a re-run produces identical output — same raw responses in, same `Service` objects and downstream claims out. *(Epic 2 AC; NFR4, NFR1)*

> **TDD (AD-12):** Encode these three ACs as pytest-bdd scenarios in `tests/features/cache.feature` (`@offline`), written **before** the cache code and seen to fail → pass. The call-count assertions (transport invoked N times then 0 times) are the load-bearing checks — drive them with the injectable transport from Story 2.1 so no network or credentials are ever needed.

## Tasks / Subtasks

- [ ] **Task 1 — Add a private response cache to `hsp_client` (AC: 1)**
  - [ ] Cache **raw** HSP JSON responses to disk (the bytes/dict as returned by the API), before any JSON→`Service` mapping (that mapping is Story 2.3's job and stays downstream of the cache).
  - [ ] Key `serviceMetrics` responses per **day + direction + window** (one file per metrics query); key `serviceDetails` responses per **RID** (one file per service). Use a filename-safe, deterministic key scheme (e.g. `metrics_{from_loc}_{to_loc}_{from_time}-{to_time}_{date}.json`, `details_{rid}.json`).
  - [ ] Fetch flow becomes: build key → if cache file exists, load and return it **without** calling the transport → else call the injectable transport (Story 2.1), store the raw response, return it.
  - [ ] Keep the cache a **private detail of `hsp_client`** — no other module imports or knows the cache path or layout (consistency convention).
- [ ] **Task 2 — Configurable/injectable cache directory (AC: 1, 3)**
  - [ ] The cache root is injectable (constructor arg / run config) so tests use `tmp_path` and real runs use a fixed project-local dir. Default to a dedicated dir (e.g. `.hsp-cache/`); **add that dir to `.gitignore`** (mirrors the old, now-removed `TrainLine/downloaded/` entry — raw API captures are not source).
  - [ ] Create the cache dir lazily if missing; never write outside it.
- [ ] **Task 3 — Force-refresh (AC: 2)**
  - [ ] Add a force-refresh flag (on the client or run config). When set, bypass/clear the relevant cache entries and re-fetch, then repopulate the cache with fresh responses.
  - [ ] Provide a clear-all path (wipe the cache dir) as the documented "force a refresh" mechanism (FR4).
- [ ] **Task 4 — Prove idempotency (AC: 3)**
  - [ ] A second run over an unchanged cache returns byte-identical raw responses, hence identical `Service` lists and identical downstream claims. No timestamps or run-varying data written into cached payloads.
- [ ] **Task 5 — Tests (AC: 1, 2, 3)**
  - [ ] `tests/features/cache.feature` + step defs, plus `tests/test_cache.py` unit tests using a counting fake transport and `tmp_path` cache dir.

## Dev Notes

### Why this story exists
Caching is what makes NFR4 (idempotent, cache-friendly runs) and NFR5 (trivial scale — "no performance engineering beyond the response cache") true. It sits inside `hsp_client` and wraps the fetches built in Stories 2.1–2.3. Re-running a week must be fast, offline-repeatable, and produce the same claims every time.

### Where it lives (AD-2, AD-7, consistency convention)
- All cache code is inside `trainline/adapters/hsp_client.py` (or a private helper module it owns). `hsp_client` imports `trainline.engine.models` **only** — never another adapter (AD-2). Filesystem I/O for the cache is legitimately adapter-side.
- **Re-implement fresh (AD-7).** The old `TrainLine/TestFileGenerator.py` (removed in Story 1.1) had the *behaviour* we want but not the code: `writeServiceMetricsTestData` skipped the POST when the day's JSON file already existed, and `writeAttributeMessageTestData` skipped re-requesting an existing RID file. Reproduce that skip-if-cached behaviour cleanly in the new client; do not resurrect the old code.

### Cache layering (important)
The cache stores **raw** responses, keyed as above, and sits **between the transport and the JSON→`Service` mapping**:
```
key → cache hit?  ──yes──> load raw JSON ─┐
                  └─no──> transport POST → store raw JSON ─┴─> (Story 2.3) map to Service
```
This means a cache hit must be indistinguishable from a fresh fetch to everything downstream — same raw dict, so same `Service`, so same `DayResult`/`Claim`. That is exactly AC3.

### Dependencies / sequencing
- Depends on **Story 2.1** (injectable transport seam — the thing whose call count we assert is zero on a cache hit), **Story 2.2** (`serviceMetrics` fetch to wrap), **Story 2.3** (`serviceDetails` fetch to wrap).
- Interacts with **Story 2.5** (fetch-failure contract): do **not** cache a failed fetch as if it were a successful empty response — a `FETCH_FAILED` day must re-fetch next run, not read back a cached failure as a clean no-claim (AD-5). Cache only successful responses.
- The force-refresh flag will later be surfaced through `adapters/config` / `cli` (Stories 3.1, 3.3); this story just needs the flag to exist and work at the client level.

### Testing standards (AD-12, testing convention)
- `@offline` by default; no network, no `HSP_CREDENTIALS_FILE` (NFR2/FR21).
- Use a **counting fake transport** (a stub session/callable injected per Story 2.1) that records how many times it was called and returns canned JSON (reuse the recorded fixtures `tests/fixtures/recorded_metrics_2026-05-28.json` / `recorded_details_*.json` where useful — FR21).
- Point the cache root at `tmp_path` so tests never touch the real `.hsp-cache/`.
- Scenarios:
  1. **Cache hit:** first fetch → transport called once, cache file written; second fetch of same key → transport call count unchanged (0 further calls), same data returned.
  2. **Force-refresh:** with a populated cache, force-refresh → cache cleared and transport called again; fresh data repopulates the cache.
  3. **Idempotent:** two runs over the same cache yield identical `Service` lists (and identical serialized output).
  4. **Don't cache failures** (guard for AD-5 / Story 2.5): a failed transport call is not written as a cache entry.

### Stack
Python 3.10+ (dev 3.12), `requests>=2.31` (only relevant to the live transport; the cache itself is stdlib `json`/`pathlib`/`os`), `pytest>=7.0`, `pytest-bdd>=7.0`.

### Project Structure Notes
- Cache dir default `.hsp-cache/` at project root; add to `.gitignore`. Keep it injectable so tests and future adapters (S3 later, per the addendum seam table) can vary it without touching the engine.
- No new top-level modules required; the cache is internal to `hsp_client`.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4] — ACs
- [Source: ARCHITECTURE-SPINE.md#AD-7] re-implement NFR4 fresh; #AD-2 adapter imports engine.models only; #AD-5 fetch-failure ≠ no-claim (don't cache failures); #Consistency Conventions "response cache is a private detail of hsp_client"
- [Source: prd.md#FR4] cache + force-refresh; #NFR4 idempotent cache-friendly; #NFR5 no perf work beyond the cache
- [Source: prd addendum.md#HSP JSON shape reference] — response shapes being cached
- Old behaviour re-implemented (not carried): `TrainLine/TestFileGenerator.py` skip-if-file-exists (removed in Story 1.1)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
