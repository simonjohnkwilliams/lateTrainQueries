---
title: Late Train Query Engine — PRD
status: final
created: 2026-07-14
updated: 2026-07-14
---

# Late Train Query Engine — PRD

## 1. Overview

A personal tool that computes, for each weekday, the **most valuable Delay Repay
claim(s)** Simon can legitimately make on his Godalming ⇄ Waterloo (GOD ⇄ WAT)
commute, and stores them in a form ready to file on the SWR site.

It queries the National Rail HSP (Historic Service Performance) API for what
actually ran on the route, then runs a **payout-maximising optimisation** over
*every* train that day — not the trains Simon caught, but the trains he *could*
have caught on an **open day return** ticket. The MVP produces correct,
hand-fileable claim data. The long game (roadmap, §8) is a photograph-to-payout
pipeline that files claims automatically.

**Why now / why this rewrite.** No product today answers the real question —
*"given everything that ran on my route this week, what is the maximum I can
legitimately claim, and what do I type into the SWR form?"* A working tool
already exists but solves the wrong problem: it flags any train >1 min late (not
claimable), collapses each day to a single "worst" train, and silently drops a
day unless *both* legs were late — so it reports noise and misses money. This PRD
replaces that behaviour with the claimable-delay model in §4.

## 2. Goals & Success Metrics

**Goals**

1. Recover the **maximum legitimately claimable amount** from the commute with
   minimal manual effort.
2. **Correctness first** — never surface a non-claimable or infeasible
   combination; never miss a claimable day.

**Success metrics (MVP)**

| # | Metric | Target |
|---|--------|--------|
| SM1 | For a chosen week, every claim row the tool emits checks out when Simon verifies it against the SWR site before filing | 100% of emitted rows valid |
| SM2 | On a periodic spot-check, days the tool emitted nothing for that manual inspection of the same HSP data finds claimable | 0 missed in the sampled week |
| SM3 | Manual effort per week to produce fileable claim data | Run one command, eyeball the output |

**Counter-metrics (guard against gaming SM1/SM2)**

| # | Counter-metric | Intent |
|---|----------------|--------|
| CM1 | Non-claimable / infeasible rows emitted | 0 — do not inflate SM2 by emitting speculative rows |
| CM2 | Rows requiring manual correction before filing | 0 — "valid" means fileable as-is, not "close enough" |

## 3. Users & Context

**Simon — the sole user.** A software engineer who commutes GOD ⇄ WAT roughly
two weekdays a week on **open day return** tickets (valid on any train, both
directions, that day — which is what makes the "any train I could have caught"
premise valid). A CLI/script is an acceptable interface; the value is in the
correctness of the answer, not the UI. No other users, no auth, no
multi-tenancy.

## 4. The Claimable-Delay Model (the heart of the product)

For each weekday in the lookback window, over **all** GOD→WAT and WAT→GOD
services:

- **Claimable** = arrival delay at the destination ≥ 15 min (SWR "Delay Repay
  15"). Delay is always measured at **destination arrival** — WAT for outbound,
  GOD for inbound.
- Each claimable service maps to an SWR **payout band**, and each band has a
  numeric `payout` percentage — the optimiser maximises the **numeric** total,
  not ordinal labels (see the band table and `payout(band)` in
  [`addendum.md`](./addendum.md); open day return → the return-ticket band
  track).
- For the day, pick **one outbound + one inbound** to **maximise total payout**,
  subject to feasibility: the chosen inbound must depart WAT **after** the chosen
  outbound's *actual* arrival at WAT (you can't return before you've arrived).
  Whether both legs of one open day return may be claimed, and what each band is
  a percentage *of*, is subject to **OQ2** (§9).
- Candidates include single-leg options (outbound-only, inbound-only), so the
  result is **0, 1, or 2 claim rows per day**.
- **Tie-break** equal totals by (1) **fewer claim rows** (less to file for the
  same money), then (2) **earliest outbound**, then (3) earliest inbound (keeps
  return options open). See FR10.
- **Cancellations** are a *fallback* candidate only; an actual late train always
  wins over a cancellation-derived claim.

The precise algorithm, worked examples, the full band table, and cancellation
mechanics live in [`addendum.md`](./addendum.md).

### 4.1 Glossary

- **Claimable** — a service whose arrival delay at its destination is ≥ 15 min.
- **Band** — the SWR delay range a claimable service falls in (15–29, 30–59,
  60–119, 120+ min).
- **Payout** — the numeric percentage a band pays for the held ticket type; the
  optimiser's objective sums these. Defined in the addendum.
- **Feasible pair** — an (outbound, inbound) pair where the inbound departs WAT
  after the outbound's *actual* arrival at WAT.
- **Single-leg option** — claiming only the outbound *or* only the inbound.
- **Next catchable service** — for a cancelled train, the earliest service
  departing at/after its scheduled departure that actually ran (cancellation
  fallback only).
- **Open day return** — a ticket valid on any train, both directions, that day —
  the basis for "any train Simon could have caught".

## 5. Functional Requirements

FRs are grouped by capability. IDs are stable and globally numbered.

### 5.1 Data acquisition (HSP)

- **FR1** — For each weekday in the lookback window, query HSP `serviceMetrics`
  for all services on the configured route/time window, in both directions
  (outbound and inbound).
- **FR2** — For every service returned, query HSP `serviceDetails` to obtain
  scheduled and actual times per calling point (`gbtt_ptd`/`gbtt_pta` scheduled,
  `actual_td`/`actual_ta` actual, within `locations[]`, keyed by
  `date_of_service`).
- **FR3** — Extract **all** RIDs for a service, not just the first, so no service
  on the route is silently dropped. _(Current code takes `rids[0]` only.)_
- **FR4** — Cache raw HSP responses to disk and reuse them on re-run for the same
  day/service, so re-runs don't re-hit the API. Provide a way to force a
  refresh (clear cache).
- **FR5** — Tolerate per-day/per-service API failures: a failed day/service is
  logged and skipped without aborting the whole run. _(A skipped day must be
  visible, not silently treated as "nothing to claim" — see CM/SM2.)_

### 5.2 Claimable-delay optimisation engine (core)

- **FR6** — Compute arrival delay in minutes at the destination for every
  service; early/on-time clamps to 0.
- **FR7** — Classify each service into an SWR band from its destination delay;
  discard sub-15-min services (band = none).
- **FR8** — Determine feasibility of an (outbound, inbound) pair:
  `inbound actual departure from WAT > outbound actual arrival at WAT` (strict;
  equal times are treated as **not** feasible). MVP applies **no interchange
  buffer** at WAT — a same-minute turnaround is out of scope to model.
- **FR9** — Over all feasible pairs plus single-leg options, select the
  combination with **maximum total payout** — the numeric sum of `payout(band)`
  (see addendum), not a comparison of ordinal band labels — emitting 0, 1, or 2
  claim rows for the day.
- **FR10** — Break ties on equal total payout deterministically: (a) fewer claim
  rows (less to file for the same money), then (b) earliest outbound departure,
  then (c) earliest inbound departure. This covers pair-vs-pair, single-vs-single,
  and pair-vs-single ties.
- **FR11** — The optimisation core is a **pure function** —
  `f(services, config) → claim rows` — with no knowledge of disk, network,
  email, browser, or cloud. All I/O sits behind interfaces (see §7).

### 5.3 Cancellation handling (fallback)

- **FR12** — When a cancelled service is the best available candidate for a leg,
  compute its claim as
  `delay = actual_arrival(next catchable service) − scheduled_arrival(cancelled service)`,
  where "next catchable" is the earliest service departing at/after the cancelled
  train's scheduled departure that actually ran. Actual late trains always take
  precedence over cancellation-derived claims.
  _Blocked on OQ1 (no HSP cancellation flag, no fixture) — see §9._

### 5.4 Claim output

- **FR13** — For each emitted claim, output the fields the SWR form needs:
  journey date, origin → destination, scheduled departure, scheduled arrival,
  actual arrival, delay (min), band, and delay/cancellation reason
  (`late_canc_reason` when present).
- **FR14** — Store output to disk as **both CSV** (human-checkable, one row per
  claim) **and JSON** (structured, for later phases to consume). MVP surfaces
  the **band**, not a £ figure.
- **FR15** — Output is grouped/sorted so a week reads at a glance (by date, then
  direction).

### 5.5 Configuration

- **FR16** — Route (origin/destination CRS codes), time windows per direction,
  and the date/lookback window are **driven by config**, not hard-coded.
  _(Current `getJson` does not actually parse the documented positional CLI
  args; this FR makes route/window genuinely configurable — default GOD ⇄ WAT.)_
- **FR17** — HSP credentials are read from an external file whose path comes from
  `HSP_CREDENTIALS_FILE`; credentials never live in the repo.
- **FR18** — The data model must not preclude **season tickets** later (different
  band track), even though MVP assumes open day return.

### 5.6 Correctness harness

- **FR19** — A test suite encodes the **new** claimable-delay behaviour (15-min
  threshold, per-day payout optimisation, feasibility, tie-break, 0/1/2 rows).
- **FR20** — Tests that lock in the **old** model (>1-min threshold, both-legs
  drop, worst-per-day pick) are **rewritten** to the new model, not kept as a
  regression baseline. _(Affected: `tests/test_late_train_pipeline.py` and the
  `late_trains.feature` offline/recorded scenarios.)_
- **FR21** — Offline tests run with no network and no credentials by default;
  optimisation logic is covered by fixtures grounded in real HSP responses.

## 6. Non-Functional Requirements

- **NFR1 — Correctness is the top priority.** A wrong claim (over- or
  under-claim) is worse than a slow run. The model must be deterministic and
  test-covered.
- **NFR2 — Offline-first testing.** The default test invocation needs no network
  and no secrets; live API tests are opt-in and skip cleanly without credentials.
- **NFR3 — Runs on Simon's Windows machine under AVG TLS interception** — the
  documented project-local CA-bundle workaround (`REQUESTS_CA_BUNDLE`) must keep
  working; cloud runners won't need it.
- **NFR4 — Idempotent, cache-friendly runs.** Re-running a week does not re-hit
  the API for already-fetched days and produces the same output.
- **NFR5 — Scale is trivial** (one route, ~5 weekdays, tens of services/day) —
  no performance engineering required beyond the response cache.
- **NFR6 — Implemented in Python**, matching the existing codebase and the HSP
  `requests` integration.

## 7. Architecture Constraints & Seams

The MVP is built as a **pure optimisation core** (FR11) with every side-effect
behind an interface, so later roadmap phases are additive rather than rewrites:
**storage**, **notification**, **claim submission**, and **ticket ingest** are
each a seam. This is a design constraint on the MVP, *not* a licence to build the
later phases now.

**Explicitly out of scope until the automation that needs it exists:** any AWS
provisioning or Terraform. The seams/technical-how detail lives in
[`addendum.md`](./addendum.md).

## 8. Scope & Roadmap

**MVP (in scope)**

- The claimable-delay optimisation engine (FR6–FR11) producing correct per-day
  claim data.
- HSP data acquisition + caching (FR1–FR5).
- Config-driven route/window (FR16–FR18).
- CSV + JSON output of SWR form fields (FR13–FR15).
- The new-model test suite (FR19–FR21).

**Out / later (roadmap, built additively behind the §7 seams, roughly in order)**

1. Email digest of the week's claims.
2. Automated filing on the SWR site (Playwright/Selenium).
3. Ticket upload mechanism.
4. Photo → OCR → assess → auto-claim (the endgame trigger).
5. Cloud deployment — AWS Lambda behind an API endpoint, invoked on ticket photo.
6. Season-ticket support (different band track; data model already allows it per
   FR18).

**Cancellation fallback (FR12)** is MVP-adjacent but gated on OQ1.

## 9. Open Questions & Assumptions

- **OQ1 (blocks FR12).** HSP exposes no cancellation flag — only free-text
  `late_canc_reason` and empty `actual_ta`/`actual_td` — and no recorded fixture
  contains a cancelled train. Capture a real cancelled-service fixture before
  implementing the fallback, to pin down the JSON shape.
- **OQ2 (owner: Simon; revisit: next real filing).** Three linked open points on
  the payout model, none blocking MVP structure but all affecting the numbers:
  (a) the open-day-return band track (12.5 / 25 / 50 / 100%) is derived from
  published SWR policy, not yet verified against a real claim; (b) what each band
  is a percentage *of* — the single-journey fare or the return fare; (c) whether
  SWR pays **two** separate claims (outbound + inbound) on one open day return,
  or caps at the ticket value. The optimiser sums two claims (FR9), so if (c) is
  capped the objective must cap too. SM1 (Simon verifies every row against the
  SWR site before filing) catches any over-claim in the meantime. _[ASSUMPTION]_
- **OQ3.** SWR form field mapping (FR13) is based on the published form; validate
  the exact fields against the live form before the automation phase (a
  screenshot would help then).
- **[ASSUMPTION]** MVP surfaces the SWR **band**, not a £ payout, and this is
  sufficient for now (confirmed with Simon).
- **[ASSUMPTION]** Claims are filed within SWR's **28-day** window; the tool is
  run often enough (e.g. weekly) that this is not a system constraint.

## 10. References

- Source brief: `../../briefs/brief-Late-Train-Query-Engine-2026-07-14/brief.md`
- HSP API: https://wiki.openraildata.com/index.php/HSP
- SWR Delay Repay: https://www.southwesternrailway.com/contact-and-help/delay-repay
