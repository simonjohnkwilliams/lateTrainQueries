# Addendum — Late Train Query Engine

Depth captured during Discovery that belongs downstream (PRD / architecture),
kept out of the 1-page brief.

## SWR Delay Repay band table (to confirm against current SWR policy)

| Arrival delay | Payout |
|---------------|--------|
| 0–14 min | Nothing (not claimable) |
| 15–29 min | 25% of the single fare |
| 30–59 min | 50% of the single fare |
| 60–119 min | 100% of the single fare |
| 120+ min | 100% of the return fare |

Delay is always measured at the **destination arrival** (WAT for outbound, GOD
for inbound).

## The per-day optimisation, precisely

Inputs for a given date D:
- `OUT` = all GOD→WAT services on D, each with scheduled departure, scheduled
  arrival at WAT, actual arrival at WAT (or cancelled).
- `IN`  = all WAT→GOD services on D, likewise to GOD.

Steps:
1. For every service compute `delay = actual_arrival − scheduled_arrival` at its
   destination; map to a band; discard sub-15-min (band = none).
2. `feasible(out, in)` ⇔ `in.actual_departure_WAT > out.actual_arrival_WAT`.
   (Uses actual arrival — when Simon would really be free to travel back.)
3. Search all feasible (out, in) pairs plus the single-leg options (out-only,
   in-only) and choose the combination with the **maximum total payout**
   (sum of bands).
4. **Tie-break** equal totals toward the **earliest outbound** departure, then
   earliest inbound.
5. Result is 0, 1, or 2 claim rows for the day.

### Worked examples (Simon's own)
- Two 16-min-late outbounds at 07:00 and 08:00 (both 25%) → pick **07:00**
  (equal band, earliest).
- 07:00 is 16 min (25%) vs 08:00 is 39 min (50%) → pick **08:00** (higher band
  beats earliness).
- Total payout is the objective: a lone higher-band leg only beats an
  early-outbound-plus-claimable-return combination when its payout strictly
  exceeds the combination's total. (The two numeric examples above show the
  within-leg tie-break; this shows the cross-leg one.)

## Cancellation handling (fallback only)

- Actual late trains always take precedence over cancellation-derived claims —
  they're easier to compute and less disputable.
- When a cancelled train is the best available candidate for a leg:
  `delay = actual_arrival(next catchable service) − scheduled_arrival(cancelled service)`
  where "next catchable" is the earliest service departing at/after the
  cancelled train's scheduled departure that actually ran.
- Requires the HSP `late_canc_reason` / cancellation signal; needs real recorded
  fixtures to pin down the JSON shape.

## Roadmap detail & architecture seams

MVP is a **pure core** — `f(journeys, HSP data) → claimable combinations` — with
no I/O knowledge, so it runs identically as a CLI now and a Lambda later.
Everything else sits behind an interface so later phases are additive:

| Concern | MVP | Later |
|---------|-----|-------|
| Storage | local disk (structured file) | S3 / DynamoDB |
| Notification | none / file | email digest |
| Claim submission | manual (Simon types it) | Playwright/Selenium auto-fill |
| Ticket ingest | config (route/window) | upload → photo + OCR |
| Trigger | run by hand | AWS API endpoint → Lambda on photo |

Explicitly **not** in scope until the dependent automation exists: any AWS
provisioning or Terraform.

## Rejected / superseded

- **Journey-matching** ("which train did I actually catch") — rejected; the
  product optimises over all services, not actual journeys.
- **Single timed tickets** — was assumed early in Discovery, corrected: Simon
  buys **open day returns**.
- Current engine's `>1 min` threshold, both-legs-late drop, and worst-per-day
  pick — superseded by the claimable-delay model.
