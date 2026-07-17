# Epic 6 close-out (2026-07-17)

Live filing confirmed after human reCAPTCHA.

## Live claim

- **Claim ID:** `SWR-0218-108-579`
- **Status:** In Progress
- **Travel date:** 16/07/2026
- **Journey:** Godalming → London Waterloo, 09:41–10:32
- **Delay band:** Between 15–29 minutes
- **Compensation:** BACS
- **Ticket type/medium:** Return / Paper (correct)
- **Ticket price / number filed:** were **placeholder** `12.50` / `12345` — **wrong**.
  Live submit now **requires** `ticket_price` + `ticket_reference` from
  `## SWR Delay Repay ##` or `SWR_TICKET_PRICE` / `SWR_TICKET_REFERENCE`.
  OCR extraction of fare + 5-digit ref is a follow-up.

## OQ3 — form mapping

Resolved. Live Angular Material wizard selectors validated; file upload must use
the "Upload a ticket" file-chooser; delay-band selection auto-advances to Ticket;
Confirm with saved BACS often jumps to Review.

## OQ4 — unattended Submit

**Policy:** auto-fill to Review → Windows alert + bring Chromium forward →
human solves reCAPTCHA and clicks Submit. No fully unattended Submit while
Google reCAPTCHA remains on the portal. `--live-submit` uses headed mode +
`human_captcha_wait_seconds` (default 600 via `SWR_CAPTCHA_WAIT_SECONDS`).

## OQ2 — payout / stacking

Resolved from this filing + SWR published return table:

- **15–29 min on a return ticket:** 12.5% of the return fare.
- **Outbound + inbound same day:** SWR allows **two separate claims** (no
  stacking cap). Keep `RunConfig.per_day_cap = None`.
