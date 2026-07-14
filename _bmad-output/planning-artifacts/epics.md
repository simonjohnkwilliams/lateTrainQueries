---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories']
inputDocuments:
  - '_bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md'
---

# lateTrainQueries - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Late Train
Query Engine, decomposing the requirements from the PRD and Architecture spine
into implementable, test-first stories. Per architecture **AD-12**, every story
is built TDD-style: its acceptance criteria are written first as pytest-bdd
Gherkin scenarios that fail, then pass.

## Requirements Inventory

### Functional Requirements

FR1: For each weekday in the lookback window, query HSP `serviceMetrics` for all services on the configured route/time window, in both directions (outbound and inbound).
FR2: For every service returned, query HSP `serviceDetails` for scheduled and actual times per calling point (`gbtt_ptd`/`gbtt_pta`, `actual_td`/`actual_ta`, in `locations[]`, keyed by `date_of_service`).
FR3: Extract ALL RIDs for a service, not just the first, so no service on the route is silently dropped.
FR4: Cache raw HSP responses to disk and reuse them on re-run for the same day/service; provide a way to force a refresh.
FR5: Tolerate per-day/per-service API failures — a failed day/service is logged and skipped without aborting the run, and is visibly distinct from "no claim".
FR6: Compute arrival delay in minutes at the destination for every service; early/on-time clamps to 0.
FR7: Classify each service into an SWR band from its destination delay; discard sub-15-min services (band = none).
FR8: Determine feasibility of an (outbound, inbound) pair: inbound actual departure from WAT > outbound actual arrival at WAT.
FR9: Over all feasible pairs plus single-leg options, select the combination with maximum total payout (sum of numeric band payouts), emitting 0, 1, or 2 claim rows for the day.
FR10: Break ties on equal total payout deterministically: (1) fewer claim rows, (2) earliest outbound, (3) earliest inbound.
FR11: The optimisation core is a pure function — `f(services, config) -> claim rows` — with no knowledge of disk, network, email, browser, or cloud.
FR12: Cancellation fallback — when a cancelled service is the best candidate for a leg, compute `delay = actual_arrival(next catchable service) - scheduled_arrival(cancelled service)`; actual late trains always take precedence. (Gated on OQ1.)
FR13: For each emitted claim, output the SWR-form fields: journey date, origin→destination, scheduled departure, scheduled arrival, actual arrival, delay (min), band, and reason.
FR14: Store output as both CSV (human-checkable) and JSON (structured); MVP surfaces the band, not a £ figure.
FR15: Output is grouped/sorted so a week reads at a glance (by date, then direction).
FR16: Route (origin/destination CRS), per-direction time windows, and the date/lookback window are driven by config, not hard-coded (default GOD ⇄ WAT).
FR17: HSP credentials are read from a file whose path comes from `HSP_CREDENTIALS_FILE`; credentials never live in the repo.
FR18: The data model must not preclude season tickets later (different band track).
FR19: A test suite encodes the new claimable-delay behaviour (15-min threshold, per-day payout optimisation, feasibility, tie-break, 0/1/2 rows).
FR20: Tests that lock in the old model (>1-min threshold, both-legs drop, worst-per-day pick) are rewritten to the new model, not kept as a regression baseline.
FR21: Offline tests run with no network and no credentials by default; optimisation logic is covered by fixtures grounded in real HSP responses.

### NonFunctional Requirements

NFR1: Correctness is the top priority — the model must be deterministic and test-covered; a wrong (over/under) claim is worse than a slow run.
NFR2: Offline-first testing — the default test invocation needs no network and no secrets; live tests are opt-in and skip cleanly without credentials.
NFR3: Runs on Windows under AVG TLS interception — the project-local CA-bundle workaround (`REQUESTS_CA_BUNDLE`) must keep working.
NFR4: Idempotent, cache-friendly runs — re-running a week does not re-hit the API for already-fetched days and produces the same output.
NFR5: Scale is trivial (one route, ~5 weekdays, tens of services/day) — no performance engineering beyond the response cache.
NFR6: Implemented in Python (matching the existing codebase and the HSP `requests` integration).

### Additional Requirements

<!-- From the Architecture spine — technical constraints that shape stories -->

- **Greenfield scaffold (AD-7):** a new `trainline/` package replaces the monolithic `TrainLine/TestFileGenerator.py`. Layout: `engine/{models,delay,optimiser}`, `adapters/{hsp_client,storage,config}`, `cli.py`. Old logic and its tests are not carried forward (FR20); NFR3 (TLS) and NFR4 (cache) are re-implemented fresh. → **Epic 1, Story 1.**
- **Hexagonal purity & dependency direction (AD-1, AD-2, AD-9):** `engine` imports nothing I/O; adapters import `engine.models` only; `cli` imports all; no adapter imports another adapter. `engine.optimise(days, config) -> list[DayResult]`.
- **Single data-shape source (AD-3):** `Service`, `Claim`, `DayResult` defined once in `engine.models`; actual-time fields are `int | None` (`None` = no actual); HSP JSON→`Service` mapping only in `hsp_client`; `Claim`→CSV/JSON only in `storage`.
- **Time base (AD-4):** integer origin-day-relative minutes (post-midnight arrival +1440); `engine.delay.calculate_delay` is the sole owner of delay arithmetic.
- **Failure contract (AD-5):** a day is `OK` only if every required leg fetched, else `FETCH_FAILED`; engine passes status through; never emit a failed day as clean no-claim.
- **Deterministic optimiser (AD-10):** sole owner of feasibility + tie-break; identical input → identical output; objective signature accepts an optional per-day cap (pre-provisions OQ2).
- **Band/payout contract (AD-11):** `band(delay_min) -> Band` (incl. `Band.NONE`); `payout(band) -> int` with `payout(Band.NONE) == 0`; MVP surfaces percentage, not £.
- **Cancellation seam (AD-6):** pure `engine` path behind a flag, off until OQ1; actual late beats cancellation; `hsp_client` only sets `Service.cancelled` from empty actuals + `late_canc_reason`.
- **Composition root (AD-8):** `cli.py` is the only MVP orchestrator; a future Lambda handler is a second root calling the same `engine.optimise`.
- **Test-first / TDD (AD-12):** each story's acceptance criteria are pytest-bdd Gherkin scenarios written before code (fail-first→pass); engine logic TDD-unit-driven; a story is not done until its acceptance tests are green and no criterion is untested.
- **Stack:** Python 3.10+ (dev 3.12), `requests>=2.31`, `pytest>=7.0`, `pytest-bdd>=7.0`.
- **Deferred (not this MVP):** OQ1 (real cancelled-train fixture, gates FR12), OQ2 (payout base / stacking cap value), and all infra/AWS/roadmap adapters (email, auto-filing, ticket ingest, Lambda).

### UX Design Requirements

None — solo command-line tool, no UI surface (per PRD §3).

### FR Coverage Map

FR1: Epic 2 — HSP `serviceMetrics` query for all services on route/window, both directions
FR2: Epic 2 — HSP `serviceDetails` query for scheduled/actual times per calling point
FR3: Epic 2 — extract ALL RIDs per service
FR4: Epic 2 — cache raw HSP responses; reuse on re-run; force-refresh
FR5: Epic 2 — tolerate per-day/service API failures; visible, not silent
FR6: Epic 1 — compute destination arrival delay; clamp early/on-time to 0
FR7: Epic 1 — classify into SWR band; discard sub-15-min
FR8: Epic 1 — (outbound, inbound) feasibility
FR9: Epic 1 — max-total-payout selection; 0/1/2 claim rows
FR10: Epic 1 — deterministic tie-break (fewer rows, earliest out, earliest in)
FR11: Epic 1 — pure-function optimisation core
FR12: Epic 1 — cancellation fallback (gated on OQ1)
FR13: Epic 3 — output SWR-form fields per claim
FR14: Epic 3 — store as CSV + JSON (band, not £)
FR15: Epic 3 — group/sort output by date then direction
FR16: Epic 3 — config-driven route/window/date
FR17: Epic 3 — credentials from `HSP_CREDENTIALS_FILE`, never in repo
FR18: Epic 1 — data model allows season tickets later
FR19: Epic 1 — test suite encodes new claimable-delay behaviour
FR20: Epic 1 — old-model tests rewritten, not kept
FR21: Epic 1 — offline tests, no network/creds by default; real-HSP-grounded fixtures

**NFR anchors:** NFR1 (correctness) → Epic 1; NFR2 (offline-first) → Epic 1 harness + all; NFR3 (AVG-TLS) → Epic 2; NFR4 (idempotent cache) → Epic 2; NFR5 (trivial scale) → n/a; NFR6 (Python) → all.

## Epic List

### Epic 1: Provably-correct claim engine
Given a set of services for a day, compute the maximum-payout claim combination(s) — the correctness heart of the product, fully TDD'd against real-HSP-grounded fixtures with no network needed. Includes the greenfield package scaffold.
**FRs covered:** FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR18, FR19, FR20, FR21

### Epic 2: Real historic data from HSP
Fetch what actually ran on the route from the live HSP API and turn it into engine `Service` objects — with caching, the AVG-TLS workaround, and the fetch-failure contract.
**FRs covered:** FR1, FR2, FR3, FR4, FR5

### Epic 3: One-command, file-ready claims
Configure the route/window, run end-to-end, and write file-ready claim output — `config`, `storage` (CSV+JSON, sorted), and the `cli.py` composition root wiring it all together.
**FRs covered:** FR13, FR14, FR15, FR16, FR17

## Epic 1: Provably-correct claim engine

Given a set of services for a day, compute the maximum-payout claim combination(s) — the correctness heart of the product, fully TDD'd against real-HSP-grounded fixtures with no network needed. Includes the greenfield package scaffold. Per AD-12, each story's acceptance criteria below are the pytest-bdd Gherkin scenarios to be written first (fail → pass).

### Story 1.1: Scaffold the hexagonal package + offline test harness

As Simon,
I want a clean `trainline/` package skeleton and an offline pytest/pytest-bdd harness,
So that every later story has a home and is built test-first with no network.

**Acceptance Criteria:**

**Given** the repo
**When** the package is scaffolded
**Then** `trainline/{engine/{models,delay,optimiser},adapters/{hsp_client,storage,config},cli}.py` exist as importable stubs

**Given** the new package
**When** an import-boundary test runs
**Then** nothing under `engine/` imports an I/O module or another adapter (AD-1, AD-2)

**Given** the old monolith
**When** the scaffold lands
**Then** the old `TrainLine` behaviour tests (>1-min / both-legs / worst-per-day) are removed (FR20)
**And** `pytest` runs green offline with no network and no credentials (NFR2, FR21)

### Story 1.2: Domain model — `Service`, `Claim`, `DayResult`

As Simon,
I want the single source-of-truth data shapes,
So that the engine and adapters never diverge on representation.

**Acceptance Criteria:**

**Given** `engine.models`
**When** inspected
**Then** it defines `Service`, `Claim`, and `DayResult` with the agreed fields (AD-3)
**And** no other module defines these shapes

**Given** a service with no actual arrival
**When** a `Service` is built
**Then** `actual_arrival is None` (not 0)
**And** `cancelled` is representable

**Given** the model
**When** a season-ticket type is later added
**Then** no field change is required to represent it (FR18)

### Story 1.3: Delay, band, and payout

As Simon,
I want delay → band → payout computed correctly,
So that a service's claimability is unambiguous.

**Acceptance Criteria:**

**Given** actual arrival equal to or earlier than scheduled
**When** `calculate_delay` runs
**Then** the result is `0` (FR6)

**Given** a 16-minute-late arrival
**When** it is banded
**Then** band = 15–29 and `payout` = 12.5 (FR7, AD-11)

**Given** a sub-15-minute delay
**When** it is banded
**Then** band = `Band.NONE` and `payout(Band.NONE) == 0` with no crash

**Given** a 23:50 → 00:15 leg
**When** `calculate_delay` runs
**Then** the delay is correct via origin-day-relative minutes, not −1435 or +1445 (AD-4)

### Story 1.4: Feasibility, max-payout optimisation, tie-break

As Simon,
I want the per-day optimal claimable combination,
So that I recover the maximum without infeasible picks.

**Acceptance Criteria:**

**Given** an inbound whose actual WAT departure precedes the outbound's actual WAT arrival
**When** the pair is evaluated
**Then** the pair is infeasible (FR8)

**Given** all services for a day
**When** optimised
**Then** it returns the maximum-total-`payout` combination as a `DayResult` with 0, 1, or 2 `Claim`s (FR9)
**And** `fetch_status` is passed through unchanged

**Given** two 16-minute outbounds at 07:00 and 08:00
**When** optimised
**Then** 07:00 is chosen (equal band → earliest)
**And** given 07:00 = 16 min vs 08:00 = 39 min, 08:00 wins (higher band)

**Given** equal-total alternatives
**When** tie-broken
**Then** order is fewer rows → earliest outbound → earliest inbound (FR10)
**And** identical input yields identical output (AD-10 determinism, FR11 purity)

### Story 1.5: Gated cancellation fallback

As Simon,
I want cancellation-derived claims computed only when clearly correct,
So that I never file a disputable claim.

**Acceptance Criteria:**

**Given** the cancellation flag is off (default)
**When** optimised
**Then** no cancellation-derived claims are emitted (FR12 gate)

**Given** the flag on and a synthetic cancelled service
**When** optimised
**Then** `delay = actual_arrival(next catchable) − scheduled_arrival(cancelled)`
**And** an actual late train for the same leg always takes precedence (AD-6)

**Given** OQ1 is unresolved (no real cancelled-train fixture)
**Then** the story is blocked for production-enable and the flag stays off

## Epic 2: Real historic data from HSP

Fetch what actually ran on the route from the live HSP API and turn it into engine `Service` objects — with caching, the AVG-TLS workaround, and the fetch-failure contract. All stories are offline-testable via the injectable transport introduced in Story 2.1.

### Story 2.1: HSP client — auth + AVG-TLS + injectable HTTP seam

As Simon,
I want an HSP client that authenticates and works under AVG TLS interception, with the HTTP call injectable,
So that real runs succeed on my machine and tests run offline.

**Acceptance Criteria:**

**Given** an injectable transport/session
**When** the client is constructed in a test
**Then** a fake transport is used and no real network call happens (NFR2)

**Given** `REQUESTS_CA_BUNDLE` is set
**When** a real request is made
**Then** it is honoured so requests verify under AVG interception (NFR3)

**Given** credentials
**When** a request is sent
**Then** HTTP basic auth is applied

### Story 2.2: Fetch `serviceMetrics` and extract ALL RIDs

As Simon,
I want every service on the route/window fetched for both directions,
So that no claimable train is missed.

**Acceptance Criteria:**

**Given** a route, window, and date
**When** `serviceMetrics` is called
**Then** the POST body is `{from_loc,to_loc,from_time,to_time,from_date,to_date,days:'WEEKDAY'}`

**Given** a metrics response
**When** RIDs are extracted
**Then** all `Services[].serviceAttributesMetrics.rids` are returned, not just `[0]` (FR3)

**Given** a run
**When** metrics are fetched
**Then** both outbound and inbound directions are queried (FR1)

### Story 2.3: Fetch `serviceDetails` and map JSON → `Service`

As Simon,
I want raw HSP detail responses turned into clean domain `Service`s,
So that the engine never sees HSP JSON.

**Acceptance Criteria:**

**Given** a RID
**When** `serviceDetails` is called
**Then** the POST body is `{rid}` and `locations[]` is parsed (FR2)

**Given** a location's times
**When** mapped
**Then** `gbtt_pta`/`actual_ta` etc. become origin-day-relative minutes on a `Service` (AD-4)
**And** an empty actual maps to `None` (AD-3)

**Given** empty actual times plus a `late_canc_reason`
**When** mapped
**Then** `Service.cancelled` is set true and `reason` carried (raw signal only — no fallback delay computed)

### Story 2.4: Idempotent on-disk response cache

As Simon,
I want fetched responses cached,
So that re-running a week is fast and doesn't re-hit the API.

**Acceptance Criteria:**

**Given** a day/service already fetched
**When** the run repeats
**Then** the cached response is used and no API call is made (NFR4)

**Given** a force-refresh
**When** the run starts
**Then** the cache is cleared and responses re-fetched (FR4)

**Given** the same cached inputs
**When** re-run
**Then** output is identical (idempotent)

### Story 2.5: Fetch-failure contract (per-day status)

As Simon,
I want a failed fetch to never masquerade as "no claim",
So that I never silently miss money.

**Acceptance Criteria:**

**Given** a metrics or details fetch fails
**When** the day is assembled
**Then** the day is `FETCH_FAILED`, reported as "not analysed", never a clean no-claim (FR5, AD-5)

**Given** a day
**When** its status is computed
**Then** it is `OK` only if every required leg (both directions' metrics + all their details) fetched successfully

**Given** a single failure
**When** it occurs
**Then** it is logged and skipped without aborting the run

## Epic 3: One-command, file-ready claims

Configure the route/window, run end-to-end, and write file-ready claim output — `config`, `storage` (CSV+JSON, sorted), and the `cli.py` composition root wiring it all together. Delivers the full MVP.

### Story 3.1: Config — route/window/dates + credential loading

As Simon,
I want route, time windows, and dates driven by config,
So that I'm not editing code to change a query, and credentials stay out of the repo.

**Acceptance Criteria:**

**Given** no arguments
**When** the tool runs
**Then** it defaults to GOD ⇄ WAT with the per-direction windows and lookback (FR16)

**Given** a config override
**When** provided
**Then** origin/destination CRS, per-direction time windows, and date/lookback are all configurable with no hard-coding

**Given** `HSP_CREDENTIALS_FILE`
**When** the tool loads credentials
**Then** they are read from that path and never committed to the repo (FR17)
**And** a missing or malformed file is reported clearly

### Story 3.2: Storage — write claims as CSV + JSON, sorted

As Simon,
I want claim output I can eyeball and re-use,
So that I can verify each row against SWR before filing.

**Acceptance Criteria:**

**Given** a list of `Claim`s
**When** written
**Then** each row carries the SWR-form fields: date, origin→destination, scheduled departure, scheduled arrival, actual arrival, delay, band, reason (FR13)

**Given** a run's results
**When** stored
**Then** both a CSV and a JSON file are produced, surfacing the band/percentage (not a £ figure) (FR14)

**Given** multiple days and directions
**When** written
**Then** output is sorted by date then direction so a week reads at a glance (FR15)

### Story 3.3: CLI composition root — end-to-end run

As Simon,
I want one command that produces a week of file-ready claims,
So that filing is a matter of copying verified rows into the SWR form.

**Acceptance Criteria:**

**Given** the wired `cli.py`
**When** run
**Then** it orchestrates config → hsp_client → engine → storage and nothing else orchestrates (AD-8)

**Given** a week of (stubbed) HSP data
**When** the pipeline runs end-to-end
**Then** CSV + JSON claim files are produced for the claimable days

**Given** a day that failed to fetch
**When** the run completes
**Then** it appears as "not analysed", distinct from a clean no-claim day (AD-5)

**Given** the recorded real-HSP fixtures
**When** the end-to-end BDD scenario runs offline
**Then** it passes — grounding the whole pipeline in real Darwin data (FR21)
