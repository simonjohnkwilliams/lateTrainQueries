# Epic 9 Context: Claim follow-up until paid

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

After SWR filing, prior claims appear in the weekly ops email (Table 2) as they move through received → approved → paid, and paid claims drop off once they have been reported in a sent digest — closing the “did I get paid?” gap without re-reporting the same paid claim.

## Stories

- Story 9.1: Claim lifecycle store
- Story 9.2: Record submitted on successful live file
- Story 9.3: Gmail lifecycle refresh via claim_mail
- Story 9.4: Table 2 in ops email + weekly chain

## Requirements & Constraints

- Durable local claim status keyed by SWR claim id (`SWR-####-###-###`); seed from successful live filings.
- Persist only: `submitted` | `received` | `approved` | `paid` | `failed`. Monotonic advance: `submitted` < `received` < `approved` < `paid`; `failed` is terminal (no further advance, no regression).
- Inbox stages from `No-replySWRDR@firstcustomercontact.com` map: `RECEIVED` → `received`, `Approved` → `approved`, `PAYMENT SENT` → `paid`.
- Table 2 lists open follow-up claims (claim id, journey date, status). Omit a paid claim only after it was included in a successfully sent digest (`reported_paid_at` set); paid-but-not-yet-reported rows stay visible.
- Filing audit JSONL remains append-only history — never rewrite it as mutable status.
- Lifecycle refresh is best-effort: Gmail/parse failures warn and continue; Table 1 email is not skipped. Weekly completion marker only after the ops email send succeeds.
- `--file` alone may record `submitted` but does not require Gmail refresh. Explicit SWR failure-mail → `failed` stays deferred until a real failure sample exists.
- Offline-first tests; live Gmail paths `@gmail` opt-in. Test-first per story.

## Technical Decisions

- **Claim lifecycle store (AD-18):** New adapter `claim_lifecycle` owns current status. Default path `Results/claim-lifecycle.json` (single JSON object map). Record fields: `claim_id`, `status`, `date`, `direction`, optional `amount_gbp`, `updated_at`, `reported_paid_at` (ISO or null). JSON file assumed until concurrency appears. Display label `in_flight` for store `submitted` is presentation only — not a persisted value.
- **Mutation ownership (AD-19):** Only `cli` mutates lifecycle. On successful live file: `record_submitted(...)`. Before ops email: Gmail search → pure `parse_swr_claim_mail` / `parse_gmail_message` → `apply_stage(claim_id, stage)`. Store does not import Gmail; `claim_mail` stays pure string→DTO. Optional audit backfill is a cli helper using audit `swr_reference` only. No adapter imports another adapter.
- **Ops email Table 1 + Table 2 (AD-20):** One weekly ops email. `ops_email.render_ops_email` stays a pure renderer (no Gmail/lifecycle I/O). Cli builds Table 2 from `open_for_table2()` (rows with `reported_paid_at` null). After successful send, `mark_reported_paid()` for every Table 2 row sent with status `paid`.
- **Weekly chain (AD-21):** `--weekly-ops` order: ticket ingest → assess → classify → file → **lifecycle refresh** → ops email (Table 1 + Table 2) → `mark_reported_paid` for paid rows included → completion marker.
- Hexagonal layering unchanged: composition root in `cli`; adapters may import `engine.models` only.

## UX & Interaction Patterns

- Table 2 in the ops email shows claim id, journey date, and status.
- Store `submitted` displays as `in_flight` in the email only.
- Surface `approved` as its own status (do not collapse into `in_flight`).

## Cross-Story Dependencies

- Implement in order: 9.1 → 9.2 → 9.3 → 9.4 (no forward deps).
- Supersedes deferred Epic 7 stories 7.4 / 7.5 — use 9.1–9.4 instead.
- Builds on existing pure claim-mail parser, ops email Table 1 renderer, `--weekly-ops` chain, and filing audit; does not redesign those seams.
