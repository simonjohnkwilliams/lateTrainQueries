---
title: Late Train Query Engine — PRD
status: final
created: 2026-07-14
updated: 2026-07-16
release: 2
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
hand-fileable claim data. **Release 1 (v1.0.0)** delivered this MVP. **Release 2**
adds weekly email digest, ticket-artifact gating, and hands-off SWR auto-filing.
The long game (roadmap, §8) remains photograph-to-payout with minimal
intervention.

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
| SM3 | Manual effort per week to produce fileable claim data | Release 1: one command, eyeball output. Release 2: one `--file` command, audit log only |
| SM4 | Claims filed without manual copy-paste into SWR | 100% of emitted rows auto-submitted when `--file` runs and tickets present |

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
  _OQ1 resolved (2026-07-15): real cancelled-service fixtures captured; fallback
  enabled by default, opt out with `--no-cancellations` — see §9._

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

### 5.7 Release 2 — Notification, ticket gate, and auto-filing

_Released 1 (v1.0.0) shipped FR1–FR21. Release 2 adds FR22–FR31._

- **FR22** — After a claims run, send an email digest summarising the week's
  claimable rows (dates, directions, bands, delays).
- **FR23** — Ticket artifacts live in a configurable `ticket/` directory; each
  file is a photo (`.jpg`/`.jpeg`/`.png`) or PDF of a digital ticket.
- **FR24** — Ticket files follow the naming contract
  `<MM-DD-TICKET_NUMBER>` (e.g. `07-10-ABC123`); misnamed files are rejected
  with a clear error listing invalid names.
- **FR25** — Before auto-filing, every claim row's journey date must have at
  least one correctly named ticket file; missing tickets hard-error with a list
  of gaps. Standalone `--check-tickets` validates without filing.
- **FR26** — Auto-submit all emitted claim rows to the SWR Delay Repay site via
  **Playwright** browser automation.
- **FR27** — Map CRS codes → station names and HSP `reason` → SWR delay-reason
  category at submit time (OQ3 follow-up); raw HSP code preserved in audit log.
- **FR28** — Attach/upload the matching ticket file per claim during SWR form
  submission.
- **FR29** — Write an append-only audit log (JSONL) of every filing attempt:
  timestamp, journey date, direction, outcome, SWR reference if available, raw
  reason code.
- **FR30** — A single CLI command (`--file`) runs assess → write output →
  ticket gate → batch submit → audit log → digest email.
- **FR31** — Release 1 assess-only behaviour preserved as default
  (`python -m trainline` without `--file`).

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

### Release 2 non-functional requirements

- **NFR7 — Adapter boundaries hold.** New `notification`, `ticket_gate`, and
  `claim_submission` adapters follow AD-2: no adapter imports another adapter.
- **NFR8 — Browser tests offline-first.** Playwright submission tests use
  injectable page fixtures / recorded HTML; live SWR tests are `@live` gated.
- **NFR9 — Credential hygiene.** SMTP and SWR login credentials come from
  config/env, never committed (same pattern as FR17).
- **NFR10 — Audit durability.** Filing audit log is append-only JSONL on local
  disk; partial batch failure does not corrupt prior entries.

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

**Release 1 — MVP (shipped v1.0.0, 2026-07-16)**

- FR1–FR21 as listed above. Cancellation fallback (FR12) enabled by default
  (OQ1 resolved 2026-07-15).

**Release 2 — Hands-off filing (in scope, approved 2026-07-16)**

- Weekly email digest (FR22).
- Ticket artifact gate — naming contract + prerequisite check (FR23–FR25).
- SWR auto-filing via Playwright — all rows, audit log, single `--file`
  command (FR26–FR31).
- Epics 4–6; see `../../epics.md`.

**Deferred past Release 2**

1. ~~Photo → OCR → auto-read ticket contents~~ — **delivered locally via Ollama** (Epic 5b / vision gate).
2. ~~AWS Lambda / cloud API endpoint~~ — **CANCELLED (2026-07-17).** Product runs locally (Windows + Ollama + Task Scheduler); no cloud deploy planned.
3. Season-ticket band track (FR18 data model ready; logic deferred).
4. ~~Ticket ingest adapter (auto-discover tickets without manual naming)~~ — largely covered by Ollama classify + folder workflow.

**Release 3 — Local weekly ops loop (approved 2026-07-17)**

- Friday / catch-up schedule for **prior** Mon–Fri week (FR32–FR33).
- Chain: assess → classify → file (Epic 6) → Gmail ops email (FR34–FR36).
- Claim lifecycle via Gmail inbox: received → paid, with Table 2 follow-up (FR37–FR38).
- Gmail API port from financeTracker_SW (FR40).
- See `../../epics.md` Epic 7. **Blocked on Epic 6.**

## 9. Open Questions & Assumptions

- **OQ1 — RESOLVED (2026-07-15).** HSP exposes no cancellation flag — a cancelled
  service is signalled by empty `actual_ta`/`actual_td` at every calling point
  plus a `late_canc_reason` code. Real cancelled-service fixtures are now captured
  (`tests/fixtures/recorded_details_cancelled_*.json`, e.g. the 2026-07-10 18:30
  Waterloo→Portsmouth Harbour, `late_canc_reason` "911"). `map_service_details`
  maps this shape to `Service.cancelled=True`, and the AD-6 fallback is validated
  against it by `tests/test_cancellation_recorded.py`. FR12 is therefore
  **enabled by default** in `RunConfig`; the CLI `--no-cancellations` flag opts
  out. Actual-late trains still take precedence over cancellation-derived claims.
- **OQ2 (owner: Simon; revisit: next real filing).** Three linked open points on
  the payout model, none blocking MVP structure but all affecting the numbers:
  (a) the open-day-return band track (12.5 / 25 / 50 / 100%) is derived from
  published SWR policy, not yet verified against a real claim; (b) what each band
  is a percentage *of* — the single-journey fare or the return fare; (c) whether
  SWR pays **two** separate claims (outbound + inbound) on one open day return,
  or caps at the ticket value. The optimiser sums two claims (FR9), so if (c) is
  capped the objective must cap too. SM1 (Simon verifies every row against the
  SWR site before filing) catches any over-claim in the meantime. _[ASSUMPTION]_
- **OQ3 — VALIDATED (2026-07-15); mapping in Release 2 (FR27).** CSV→form
  field mapping confirmed against published SWR Delay Repay form. Release 2
  maps at submit time: CRS→station name, HSP reason→SWR category; raw code kept
  in audit log. Full mapping table in [`addendum.md`](./addendum.md).
- **OQ4 (owner: Simon; revisit: first `--file` live run).** SWR session handling
  — whether login persists across batch submissions, and whether 2FA blocks
  unattended filing.
- **[ASSUMPTION]** MVP surfaces the SWR **band**, not a £ payout, and this is
  sufficient for now (confirmed with Simon).
- **[ASSUMPTION]** Claims are filed within SWR's **28-day** window; the tool is
  run often enough (e.g. weekly) that this is not a system constraint.

## 10. References

- Source brief: `../../briefs/brief-Late-Train-Query-Engine-2026-07-14/brief.md`
- HSP API: https://wiki.openraildata.com/index.php/HSP
- SWR Delay Repay: https://www.southwesternrailway.com/contact-and-help/delay-repay
