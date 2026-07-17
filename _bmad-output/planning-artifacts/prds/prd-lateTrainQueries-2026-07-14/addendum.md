# Addendum — Late Train Query Engine PRD

Depth captured during PRD discovery that belongs downstream (architecture /
implementation) or is reference detail too fine-grained for the PRD narrative.

## SWR Delay Repay band table

SWR pays a percentage of the fare **for the ticket type actually held**, so
single and return are separate tracks. Simon buys **open day returns** → use the
**return** column.

| Arrival delay | Single ticket | **Return ticket (open day return)** |
|---------------|---------------|-------------------------------------|
| 0–14 min | nothing | nothing |
| 15–29 min | 25% | **12.5%** |
| 30–59 min | 50% | **25%** |
| 60–119 min | 100% | **50%** |
| 120+ min | 100% (already capped) | **100% of return fare** |

- Delay is measured at **destination arrival** (WAT for outbound, GOD for
  inbound), not departure.
- Threshold is **Delay Repay 15** — nothing payable under 15 min.
- **Season tickets** (future, FR18): compensated at the single-journey proportion
  of the ticket's daily value (weekly 1/10, flexi 1/16, monthly 1/40, annual
  1/464), capped at the cost of two singles.

**`payout(band)` for the optimiser (open day return track).** The engine
maximises the numeric sum of these, not the ordinal band labels (PRD FR9):

| Band (destination delay) | `payout` |
|--------------------------|----------|
| none (0–14 min) | 0 |
| 15–29 min | 12.5 |
| 30–59 min | 25 |
| 60–119 min | 50 |
| 120+ min | 100 |

**Open OQ2 — payout base & claim stacking.** These percentages are of *a fare*,
but which one (single-journey vs return) is unconfirmed, and it is unconfirmed
whether SWR pays two separate claims (outbound + inbound) on one open day return
or caps at the ticket value. The optimiser sums two claims; if SWR caps, the
objective must cap too. Owner: Simon; resolve at the next real filing. Until
then, SM1 (verify every row against the SWR site before filing) is the safety
net.

> Correction vs. the brief's addendum: the brief's table (25/50/100/100) is
> correct for a **single** ticket. Because Simon holds an open day **return**,
> the payable percentages halve until the top band. The band **ordering** is
> unchanged, so the optimisation's "higher band wins" logic is unaffected — only
> the emitted percentage labels differ. **OQ2:** verify against one real claim.

## The per-day optimisation, precisely

Inputs for a given date D:
- `OUT` = all GOD→WAT services on D, each with scheduled departure, scheduled
  arrival at WAT, actual arrival at WAT (or cancelled).
- `IN` = all WAT→GOD services on D, likewise to GOD.

Steps:
1. For every service compute `delay = actual_arrival − scheduled_arrival` at its
   destination; map to a band; discard sub-15-min (band = none).
2. `feasible(out, in) ⇔ in.actual_departure_WAT > out.actual_arrival_WAT`
   (uses **actual** arrival — when Simon would really be free to travel back).
3. Search all feasible (out, in) pairs plus the single-leg options (out-only,
   in-only) and choose the combination with the **maximum total payout** (sum of
   bands).
4. **Tie-break** equal totals by (1) fewer claim rows, then (2) earliest
   outbound departure, then (3) earliest inbound (matches PRD FR10).
5. Result is 0, 1, or 2 claim rows for the day.

### Worked examples (Simon's own)
- Two 16-min-late outbounds at 07:00 and 08:00 (both 15–29 band, `payout` 12.5)
  → pick **07:00** (equal band, earliest).
- 07:00 is 16 min (12.5) vs 08:00 is 39 min (30–59 band, `payout` 25) → pick
  **08:00** (higher band beats earliness).
- Total payout is the objective: a lone higher-band leg only beats an
  early-outbound-plus-claimable-return combination when its `payout` strictly
  exceeds the combination's summed `payout`.

## Cancellation handling (fallback only) — FR12 / OQ1

- Actual late trains always take precedence over cancellation-derived claims —
  easier to compute and less disputable.
- When a cancelled train is the best available candidate for a leg:
  `delay = actual_arrival(next catchable service) − scheduled_arrival(cancelled service)`,
  "next catchable" = earliest service departing at/after the cancelled train's
  scheduled departure that actually ran.
- **Data gap (OQ1):** HSP has **no** dedicated cancellation flag or disruption
  code. The only signal is the free-text `late_canc_reason` field plus empty
  `actual_ta`/`actual_td`. None of the current recorded fixtures
  (`recorded_details_*.json`, all 2026-05-28) contain a cancelled service — they
  all ran. A real cancelled-service fixture is needed before implementing this.

## HSP JSON shape reference (grounded from fixtures + code)

**serviceMetrics** →
`{ header:{from_location,to_location}, Services:[ { serviceAttributesMetrics:{ origin_location, destination_location, gbtt_ptd, gbtt_pta, toc_code, matched_services, rids:[...] }, Metrics:[...] } ] }`.
Service RIDs live at `Services[].serviceAttributesMetrics.rids` (extract **all**,
not just `[0]` — FR3).

**serviceDetails** →
`{ serviceAttributesDetails:{ date_of_service, toc_code, rid, locations:[ { location, gbtt_ptd, gbtt_pta, actual_td, actual_ta, late_canc_reason } ] } }`.
- Scheduled: `gbtt_pta` (arr) / `gbtt_ptd` (dep). Actual: `actual_ta` / `actual_td`.
- Origin calling point has empty `gbtt_pta`/`actual_ta`; terminus has empty
  `gbtt_ptd`/`actual_td` — handle empties when computing per-leg delay.

Endpoints (POST): `https://hsp-prod.rockshore.net/api/v1/serviceMetrics` and
`.../serviceDetails`; `serviceMetrics` payload uses `days:'WEEKDAY'`.

## Architecture seams (design the seams now, build only MVP)

MVP is a **pure core** — `f(services, config) → claim rows` — with no I/O
knowledge, so it runs identically as a CLI now and a Lambda later. Everything
else sits behind an interface so later phases are additive:

| Concern | MVP | Later |
|---------|-----|-------|
| Storage | local disk (CSV + JSON) | S3 / DynamoDB |
| Notification | none / file | email digest |
| Claim submission | manual (Simon types it) | Playwright/Selenium auto-fill |
| Ticket ingest | config (route/window) | upload → photo + OCR |
| Trigger | run by hand (CLI) | AWS API endpoint → Lambda on photo |

Explicitly **not** in scope until the dependent automation exists: any AWS
provisioning or Terraform.

## Release 2 — adapter contracts (FR22–FR31)

### Notification (`adapters/notification.py`)

| Env / config | Purpose |
|--------------|---------|
| `SMTP_HOST`, `SMTP_PORT` | SMTP server |
| `SMTP_USER`, `SMTP_PASSWORD` | Auth (never in repo) |
| `DIGEST_TO` | Recipient address |
| `send_digest: true` or `--digest` | Trigger after assess |

Digest is best-effort by default; `--digest-strict` fails the run on SMTP error.

### Ticket gate (`adapters/ticket_gate.py`)

- Default directory: `ticket/` (override: `--ticket-dir` or config).
- Naming regex: `^(?P<month>\d{2})-(?P<day>\d{2})-(?P<ticket>[A-Za-z0-9_-]+)\.(jpg|jpeg|png|pdf)$`
- Match claim `YYYY-MM-DD` → `MM-DD` portion of filename.
- Multiple files per date: any one satisfies the date.

### Claim submission (`adapters/claim_submission.py`)

- **Playwright** (not Selenium) — binding decision 2026-07-16.
- Target: https://delayrepay.southwesternrailway.com/
- SWR credentials via env (`SWR_USERNAME`, `SWR_PASSWORD`) — never in repo.
- Injectable `BrowserContext` / page fixture for offline tests.
- `swr_mapping.py` (pure): CRS→name, reason→category.

### Filing audit log

- Path: `results/filing-audit.jsonl` (configurable).
- Append-only; one JSON object per line per submission attempt.
- Fields: `timestamp`, `date`, `direction`, `outcome`, `swr_reference`, `raw_reason`, `ticket_path`.

### CLI pipeline (`--file`)

```
assess → storage (CSV/JSON) → ticket_gate → claim_submission (batch) → audit log → notification (digest)
```

Default `python -m trainline` unchanged (assess-only). Ticket gate failure: write output, skip submit, non-zero exit.

## SWR claim form — field mapping & constraints (for FR13 / OQ3)

Published SWR online claim form requires: journey date; origin and destination;
scheduled and actual arrival times (or cancellation details); ticket details
(type/fare, and a barcode scan/photo for eTickets); and a payout method (BACS,
card, cheque, vouchers, or charity). Claims must be filed **within 28 days** of
the journey; SWR aims to process in ~10–20 working days. Validate exact field
names against the live form before the automation phase (OQ3).

## Rejected / superseded

- **Journey-matching** ("which train did I actually catch") — rejected; the
  product optimises over all services, not actual journeys.
- **Single timed tickets** — corrected during brief discovery: Simon buys open
  day returns (drives the return-ticket band track above).
- Current engine's `>1 min` threshold, both-legs-late drop, and worst-per-day
  pick — superseded by the claimable-delay model (FR6–FR11, FR20).

## Sources

- SWR Delay Repay: https://www.southwesternrailway.com/contact-and-help/delay-repay
- SWR Delay Repay portal: https://delayrepay.southwesternrailway.com/
- HSP API wiki: https://wiki.openraildata.com/index.php/HSP
