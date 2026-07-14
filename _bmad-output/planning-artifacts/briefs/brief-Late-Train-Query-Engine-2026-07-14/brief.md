---
title: Late Train Query Engine — Product Brief
status: final
created: 2026-07-14
updated: 2026-07-14
---

# Late Train Query Engine — Product Brief

## Executive Summary

A personal tool that works out, for each weekday, the **most valuable
Delay Repay claim(s)** Simon can make on his Godalming ⇄ Waterloo commute, and
presents them in a form ready to file on the SWR website. It queries the
National Rail HSP API for historic service performance and runs a
**payout-maximising optimisation** over every train on the route — not the
trains Simon actually caught, but the trains he *could* have caught on an open
day return. The immediate goal is **correct claim data he can file by hand**;
the long-term goal is a photograph-to-payout pipeline that files claims
automatically.

## Problem Statement

Simon commutes GOD⇄WAT ~2 days/week on **open day return** tickets and is
entitled to Delay Repay when trains run late, but:

- Working out which trains were delayed enough to claim, on which days, and in
  what combination, is tedious to do by hand across a week.
- The **existing tool solves the wrong problem**: it flags any train >1 minute
  late (not claimable), collapses each day to a single "worst" train, and
  silently drops days unless *both* legs were late — so it both reports noise
  and misses money.

There is no product today that answers the real question: *"Given everything
that ran on my route this week, what is the maximum I can legitimately claim,
and what do I type into the SWR form?"*

## Goals & Success Criteria

1. **Recover the maximum claimable amount** from the commute with minimal manual
   effort.
2. **Correctness first** — never surface a non-claimable or infeasible
   combination; never miss a claimable day.
3. **MVP success:** for any chosen week, the tool outputs the optimal claimable
   outbound+inbound combination per day, and every row checks out when Simon
   verifies it against the SWR site before filing.

## Target User

Simon — the sole user. A software engineer, so a CLI/script MVP is fine; the
value is in the correctness of the answer, not the interface.

## The Claimable-Delay Model (the heart of the product)

For each weekday in the lookback window, over **all** GOD→WAT and WAT→GOD
services:

- **Claimable** = arrival delay at destination ≥ 15 min (banded per SWR — see
  the addendum for the band/payout table).
- Pick **one outbound + one inbound** to **maximise total payout for the day**,
  subject to the inbound departing WAT **after** the chosen outbound's *actual*
  arrival at WAT (you can't return before you've arrived).
- **Tie-break:** earliest outbound (keeps return options open).
- **Cancellations** are a *fallback* candidate only — actual late trains always
  win (mechanics in the addendum).
- Emit **0, 1, or 2 claims per day.**

The precise algorithm, worked examples, and SWR band table live in
[`addendum.md`](./addendum.md).

## Scope — MVP (In)

- The optimisation engine above, producing correct per-day claim data.
- Output the fields the SWR form needs (date, origin→dest, scheduled departure,
  scheduled/actual arrival, delay, band, reason) **stored to disk** for easy
  checking.
- Route driven by config (GOD⇄WAT today, not hard-coded).
- A test suite that encodes the **new** claimable-delay behaviour.

## Scope — Out / Later (the roadmap)

Built additively behind clean seams, roughly in order:

1. **Email digest** of the week's claims.
2. **Automated filing** on the SWR site via Playwright/Selenium.
3. **Ticket upload** mechanism.
4. **Photo → OCR → assess → auto-claim** — the endgame trigger.
5. **Cloud deployment** — AWS Lambda behind an API endpoint, invoked when Simon
   photographs a ticket.

## Constraints & Assumptions

- **Architecture principle (agreed):** design the *seams* for the endgame now —
  a pure optimisation core with no knowledge of disk/email/AWS/browser, and I/O
  (storage, notification, claim-submission, ticket-ingest) behind interfaces —
  but **build only the MVP**. **No AWS/Terraform provisioning** until the
  automation that needs it exists.
- **Ticket type:** open day return (valid on any train, both directions, that
  day) → the "any train I could have caught" premise is fully valid. Season
  ticket possible later; data model must not preclude it.
- Python; depends on the National Rail HSP API.
- Local dev is subject to AVG TLS interception (documented CA-bundle workaround);
  cloud runners won't need it.

## Risks & Open Questions

- **The existing test suite guards the behaviour we're deliberately replacing**
  (>1 min / both-legs / worst-per-day). Those tests must be rewritten to the new
  model rather than treated as a regression baseline.
- **HSP data quality** for cancellations (missing actual times) makes the
  fallback calculation the fiddliest part — needs real recorded fixtures.
- **Payout amounts** depend on ticket price; MVP surfaces the *band*, not a £
  figure — confirm that's enough for now (assumed yes).
- **SWR form field mapping** should be validated against the live form before
  the automation phase (a screenshot would help when we get there).
