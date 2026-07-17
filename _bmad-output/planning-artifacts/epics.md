---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
release: 2
release_tag: v1.0.0
inputDocuments:
  - '_bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md'
  - '_bmad-output/implementation-artifacts/epic-1-3-retro-2026-07-15.md'
discovery_date: 2026-07-16
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

---

## Release 2 — Requirements (roadmap, approved 2026-07-16)

Derived from PRD §8 roadmap, Epic 1–3 retrospective, and discovery interview.

### Release 2 Functional Requirements

FR22: After a claims run, send an email digest summarising the week's claimable rows (dates, directions, bands).
FR23: Ticket artifacts live in a `ticket/` directory; each file is a photo (jpg/png) or PDF of a digital ticket.
FR24: Ticket files must follow the naming contract `<MM-DD-TICKET_NUMBER>` (e.g. `07-10-ABC123`); misnamed files are rejected with a clear error.
FR25: Before auto-filing, every claim row's journey date must have at least one correctly named ticket file; missing tickets hard-error with a list of gaps.
FR26: Auto-submit all emitted claim rows to the SWR Delay Repay site via browser automation (Playwright).
FR27: Map CRS codes → station names and HSP `reason` → SWR delay-reason category at submit time (OQ3 follow-up).
FR28: Attach/upload the matching ticket file per claim during SWR form submission.
FR29: Write an audit log of every filing attempt (journey date, direction, outcome, timestamp, SWR reference if available).
FR30: A single CLI command runs assess → ticket gate → auto-file all rows (no separate manual steps).
FR31: Default assess-only behaviour preserved (`python -m trainline` without `--file`).

### Release 2 Non-Functional Requirements

NFR7: Notification and submission adapters follow hexagonal boundaries — no adapter imports another adapter (AD-2).
NFR8: Browser automation tests are offline-first via recorded page fixtures / stub transport; live SWR tests are `@live` gated.
NFR9: Email and SWR credentials come from config/env, never committed to the repo (same pattern as FR17).
NFR10: Audit log is append-only JSONL on local disk.

### Explicitly deferred past Release 2

- Photo → OCR → auto-read ticket contents
- AWS Lambda / cloud API endpoint
- Season-ticket band track (FR18 data model ready; logic deferred)
- Ticket ingest adapter (auto-discover tickets without manual naming)

### Release 2 FR Coverage Map

FR22: Epic 4 — weekly email digest
FR23, FR24: Epic 5 — ticket naming + directory scan
FR25: Epic 5 — claim-to-ticket matcher + CLI gate
FR26, FR27, FR28: Epic 6 — SWR browser submission
FR29: Epic 6 — audit log
FR30, FR31: Epic 6 — single-command pipeline (assess → gate → file)

## Release 2 Epic List

### Epic 4: Weekly claims digest
After each run, receive an email with the week's claimable rows so you don't have to remember to open `claims.csv`.
**FRs covered:** FR22

### Epic 5: Ticket artifact gate
Before any filing, verify every claim date has a correctly named ticket photo/PDF in `ticket/`; hard-error on gaps.
**FRs covered:** FR23, FR24, FR25

### Epic 6: SWR auto-filing (single command)
One command assesses claims, checks tickets, auto-files every row on the SWR site, and writes an audit log.
**FRs covered:** FR26, FR27, FR28, FR29, FR30, FR31

## Epic 4: Weekly claims digest

Adds the `notification` adapter seam. Standalone — valuable before browser automation lands.

### Story 4.1: Notification adapter + email config

As Simon,
I want email settings loaded from config/env,
So that digest credentials stay out of the repo and the notification seam is ready.

**Acceptance Criteria:**

**Given** no email config
**When** digest is requested
**Then** a clear error explains which settings are missing (NFR9)

**Given** SMTP settings in config/env (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO`)
**When** the notification adapter is constructed
**Then** it is importable without pulling in browser or HSP modules (NFR7, AD-2)

**Given** the adapter
**When** `send_digest(subject, body_html, body_text)` is called with a test payload
**Then** the message is sent via SMTP (offline test uses a fake transport)

### Story 4.2: Weekly digest email content

As Simon,
I want the email to summarise claimable rows for the week,
So that I can see at a glance what was found without opening files.

**Acceptance Criteria:**

**Given** a completed run with claim rows and fetch-failed days
**When** the digest is rendered
**Then** the email lists each claimable row: date, direction, band, origin→destination, delay (FR22)

**Given** days with no claim and days marked "not analysed"
**When** the digest is rendered
**Then** fetch-failed days appear distinctly from clean no-claim days (AD-5)

**Given** zero claimable rows
**When** the digest is rendered
**Then** the email says so explicitly (no silent empty send)

### Story 4.3: CLI digest integration

As Simon,
I want the digest sent automatically after a successful assess run,
So that I get a weekly nudge without a separate command.

**Acceptance Criteria:**

**Given** `--digest` or config `send_digest: true`
**When** a claims run completes successfully
**Then** the weekly digest email is sent (FR22)

**Given** `--no-digest` or email config absent
**When** a claims run completes
**Then** no email is sent and the run still succeeds

**Given** SMTP failure
**When** digest send fails
**Then** the failure is logged; assess output is still written (digest is best-effort unless `--digest-strict`)

## Epic 5: Ticket artifact gate

Validates ticket files before any browser submission. Standalone via `--check-tickets`.

### Story 5.1: Ticket naming contract + directory scanner

As Simon,
I want a defined ticket directory and naming format,
So that the tool can reliably match tickets to claim dates.

**Acceptance Criteria:**

**Given** the `ticket/` directory (configurable path)
**When** scanned
**Then** only files matching `<MM-DD-TICKET_NUMBER>` with extension `.jpg`, `.jpeg`, `.png`, or `.pdf` are accepted (FR23, FR24)

**Given** a file named `07-10-ABC123.pdf`
**When** parsed
**Then** journey month=07, day=10, ticket_number=ABC123

**Given** a misnamed file (e.g. `ticket.pdf`, `2026-07-10.pdf`)
**When** scanned
**Then** it is listed as invalid with the expected format shown (FR24)

### Story 5.2: Claim-to-ticket matcher

As Simon,
I want every claim date to have a matching ticket before filing,
So that I never submit a claim without proof attached.

**Acceptance Criteria:**

**Given** claim rows for dates 07-08, 07-09, 07-10
**When** tickets exist for 07-08 and 07-10 only
**Then** the matcher reports 07-09 as missing and returns failure (FR25)

**Given** multiple ticket files for the same date (e.g. `07-10-A.pdf`, `07-10-B.jpg`)
**When** matched
**Then** any one valid file satisfies that date

**Given** all claim dates covered
**When** matched
**Then** a mapping of `claim_date → ticket_file_path` is returned for the submission adapter (FR28)

### Story 5.3: CLI ticket prerequisite gate

As Simon,
I want `--check-tickets` to validate tickets without filing,
So that I can fix naming gaps before a filing run.

**Acceptance Criteria:**

**Given** `python -m trainline --check-tickets`
**When** tickets are missing or misnamed
**Then** exit code is non-zero with a human-readable list of problems (FR25)

**Given** all tickets present
**When** `--check-tickets` runs against current claims output
**Then** exit code 0 with a summary count

**Given** the full filing pipeline (Epic 6)
**When** ticket gate fails
**Then** no browser submission is attempted

## Epic 6: SWR auto-filing (single command)

Adds the `claim_submission` adapter seam. Delivers the core Release 2 pain relief.

### Story 6.1: SWR field mapping at submit time

As Simon,
I want CRS codes and HSP reasons mapped to SWR form values during submission,
So that auto-filled forms match what the site expects (OQ3).

**Acceptance Criteria:**

**Given** origin CRS `WAT`
**When** mapped for the SWR form
**Then** the value is `London Waterloo` (FR27)

**Given** origin CRS `GOD`
**When** mapped
**Then** the value is `Godalming`

**Given** a cancelled claim row (`reason` from HSP `late_canc_reason`)
**When** mapped
**Then** SWR delay reason = `Train cancelled`

**Given** an actual-late claim row
**When** mapped
**Then** SWR delay reason = `Delayed en route`

**Given** the raw HSP reason code
**When** mapped
**Then** it is preserved in the audit log even though the form gets the category

### Story 6.2: Playwright submission adapter — single claim

As Simon,
I want one claim row auto-filled and submitted on the SWR site,
So that manual copy-paste is eliminated for a single journey.

**Acceptance Criteria:**

**Given** a `Claim`, field mapping, and matching ticket file path
**When** `submit_claim(claim, ticket_path)` runs under `@live`
**Then** the SWR Delay Repay form is filled with journey date, stations, scheduled/actual times, delay reason, and ticket upload (FR26, FR28)

**Given** an injectable browser/page fixture
**When** tested offline
**Then** the adapter fills the expected fields without a live network call (NFR8)

**Given** SWR credentials in config/env (never in repo)
**When** the adapter starts
**Then** it reuses or establishes an authenticated session

**Given** submission succeeds
**When** the page shows a confirmation/reference
**Then** that reference is returned to the caller (FR29)

### Story 6.3: Batch auto-file all claims + audit log

As Simon,
I want every emitted claim row filed automatically with a persistent audit trail,
So that I trust the engine to handle the full week and can review what was submitted.

**Acceptance Criteria:**

**Given** N claim rows from a run
**When** batch submission runs
**Then** all N rows are submitted (FR26)

**Given** each submission attempt
**When** it completes (success or failure)
**Then** an append-only JSONL audit entry is written: timestamp, date, direction, outcome, SWR reference, raw reason code (FR29, NFR10)

**Given** one row fails mid-batch
**When** the failure occurs
**Then** the error is logged, remaining rows still attempt, and the run summary reports partial success

### Story 6.4: Single-command assess → gate → file pipeline

As Simon,
I want one command that assesses, checks tickets, files everything, emails the digest, and logs the audit,
So that weekly Delay Repay is fully hands-off.

**Acceptance Criteria:**

**Given** `python -m trainline --file` (or config `auto_file: true`)
**When** run
**Then** the pipeline executes: assess → write CSV/JSON → ticket gate → batch submit → audit log → digest email (FR30)

**Given** ticket gate failure
**When** `--file` runs
**Then** assess output is still written but submission is skipped with a clear error (FR25)

**Given** `--assess-only` (default behaviour preserved from Release 1)
**When** run
**Then** no ticket check or submission occurs — Release 1 behaviour unchanged

**Given** a successful `--file` run
**When** complete
**Then** stdout prints a summary: claims found, filed, failed, audit log path

---

## Release 3 — Local weekly ops loop (approved 2026-07-17)

**Dependency:** Epic 6 (SWR auto-filing) must pass before Epic 7 implementation starts.
**Runtime:** Local Windows + Ollama + Task Scheduler only.
**Cancelled:** AWS Lambda / cloud API / Terraform — explicitly dropped (local vision model is sufficient).

### Release 3 Functional Requirements

FR32: A scheduled weekly job runs on Friday, or on the next power-on after a missed Friday (catch-up for that Friday's window).
FR33: The assessment window is always the **previous** Mon–Fri five-day week relative to the anchor Friday (e.g. run Fri 17 Jul or later catch-up → assess Mon 6 Jul – Fri 10 Jul). Partial weeks are not special-cased — always five weekdays.
FR34: The weekly job chain is: assess lookback window → classify ticket inbox (Ollama) → match tickets to claims → auto-file eligible claims (Epic 6) → send ops email (last).
FR35: Ops email is sent via **Gmail API** (OAuth), ported from `financeTracker_SW` patterns — not SMTP app-password as the long-term path (SMTP may remain as legacy until Gmail API is live).
FR36: Ops email **Table 1 — this run:** late/claimable trains (same optimiser logic); tickets transformed/matched against those trains; rejection list with short reason + file path; newly filed claims and still-open claims.
FR37: Ops email **Table 2 — follow-up:** all previously actioned claims that are not yet reported as successful in the last digest; status from Gmail inbox lookup (received / paid / failed / still in flight). Placeholder matchers until first live SWR confirmation emails are observed.
FR38: Claim success is three-stage: (1) SWR submit success (Epic 6), (2) inbox confirmation that the claim was received, (3) follow-up ~1 week later for payment confirmation.
FR39: Idempotent weekly runs — re-running the same anchor Friday does not duplicate filing or re-report already-successful claims in Table 2.
FR40: Gmail OAuth client id/secret and token path live under `creds/trainConfig.txt` (gitignored); token file on disk; never committed.

### Release 3 Non-Functional Requirements

NFR11: Gmail unit tests are offline-first (mocked Google client); live Gmail tests are `@gmail` / opt-in.
NFR12: Windows Task Scheduler script is first-class (PowerShell) — no cloud scheduler.
NFR13: Catch-up after missed Friday uses the same anchor-Friday window (FR33), not a newly completed week.

### Release 3 FR Coverage Map

FR32–FR33, FR39: Epic 7 — schedule + window
FR34–FR36: Epic 7 — weekly chain + Table 1
FR37–FR38: Epic 7 — claim lifecycle + Table 2 (inbox placeholders)
FR40, NFR11: Epic 7 — Gmail API adapter port

## Epic 7: Weekly local ops loop (schedule + Gmail + lifecycle email)

So that every week you get one email covering last week's late trains, ticket intake, filing, and claim follow-up — without opening the machine on a fixed hour if it was asleep.

**Depends on:** Epic 6 done (auto-file available).

### Story 7.1: Gmail API adapter (port from financeTracker_SW)

As a developer,
I want Gmail OAuth + send/search behind a hexagonal adapter,
So that digests and claim-status lookups use the same Google API as financeTracker.

**Acceptance Criteria:**

**Given** offline unit tests (mocked Google client)
**When** run
**Then** auth scopes include readonly + send; token load/refresh/store work against a file path; search and send are covered (NFR11)

**Given** `## Gmail API ##` keys in `trainConfig.txt` + token file
**When** `python -m trainline --gmail-auth` (or equivalent)
**Then** InstalledAppFlow completes and writes the token file (FR40)

**Given** no Gmail credentials
**When** digest send is requested
**Then** a clear error explains how to auth; assess/classify output is still written

### Story 7.2: Prior-week window + Friday catch-up scheduler

As Simon,
I want the job to target Mon–Fri of the week before the anchor Friday,
So that Friday (or later power-on) never analyses the incomplete current week.

**Acceptance Criteria:**

**Given** as_of = Fri 17 Jul 2026
**When** window is computed
**Then** range is Mon 6 Jul – Fri 10 Jul (FR33)

**Given** as_of = Mon 20 Jul 2026 (missed Friday)
**When** window is computed
**Then** range is still Mon 6 Jul – Fri 10 Jul (NFR13)

**Given** Windows Task Scheduler / power-on script
**When** the machine starts on/after Friday
**Then** the weekly command runs once for that anchor Friday if not already completed (FR32, FR39)

### Story 7.3: Weekly chain orchestration

As Simon,
I want one command that assesses → classifies tickets → files → emails,
So that the ops loop is a single scheduled entry point.

**Acceptance Criteria:**

**Given** `python -m trainline --weekly-ops` (name TBD)
**When** run
**Then** order is assess → classify → ticket match/file (Epic 6) → Gmail ops email last (FR34)

**Given** classify rejects
**When** email is rendered
**Then** each rejection includes short reason + path (FR36)

### Story 7.4: Ops email Tables 1 and 2

As Simon,
I want Table 1 for this week's new/open work and Table 2 for follow-up on earlier claims,
So that I see both action needed now and payment outcomes later.

**Acceptance Criteria:**

**Given** a weekly run with claimable rows and ticket outcomes
**When** email is sent
**Then** Table 1 lists late trains, matched tickets, rejections (reason+path), newly filed + open claims (FR36)

**Given** prior actioned claims not yet reported successful
**When** email is sent
**Then** Table 2 lists them with status received / paid / failed / in flight (FR37)

**Given** a claim already reported successful in the last digest
**When** Table 2 is built
**Then** that claim is omitted (FR37, FR39)

**Given** first live SWR confirmation emails are not yet characterised
**When** inbox matchers run
**Then** placeholder rules are used and documented for refinement after first real filing (FR38)

### Story 7.5: Claim lifecycle state store

As Simon,
I want durable local state for filed / received / paid / reported,
So that Table 2 and idempotent runs stay correct across weeks.

**Acceptance Criteria:**

**Given** a successful Epic 6 file
**When** audit completes
**Then** claim lifecycle state records submitted + timestamp (FR38)

**Given** Gmail search finds a confirmation/payment (or placeholder)
**When** state updates
**Then** Table 2 reflects the new status on the next digest (FR37)
