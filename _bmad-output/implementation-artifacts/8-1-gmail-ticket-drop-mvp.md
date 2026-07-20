---
story_key: 8-1-gmail-ticket-drop-mvp
epic: 8
status: review
created: 2026-07-20
depends_on: [7-1]
---

# Story 8.1: Gmail ticket drop MVP

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As Simon,
I want to email myself a ticket photo and have it land in `tickets/unclassified/`,
So that I never USB-copy tickets again.

## Acceptance Criteria

1. **Ingest CLI.** `python -m trainline --ingest-ticket-mail` searches Gmail for ticket-drop messages, downloads image attachments, and writes them under `tickets/unclassified/` (FR41, FR43, FR45).
2. **Match convention.** Messages match a configurable subject prefix (default **`TICKET`**) and/or Gmail label (default **`trainline-ticket`**). Document the phone-side subject line clearly in Dev Notes / stderr on dry success.
3. **Mark processed.** After a successful save of ≥1 image from a message, mark that message so it is not ingested again (add label `trainline-ticket-ingested` and/or remove `UNREAD` via Gmail modify API) (FR42 for mail-level idempotency).
4. **Weekly-ops hook.** `--weekly-ops` runs ingest **first** (before assess → classify → file → email). Ingest soft-fail (warn + continue) for “no matching mail”; hard fail (auth/config/API) returns non-zero and must **not** write the weekly complete marker (FR39).
5. **Offline tests.** Mocked Gmail client: fixture MIME with `image/jpeg` attachment → file appears under a temp `unclassified/`; second ingest of same message id is a no-op; non-image attachment skipped without crash (FR44 light — content-hash dedup is Story 8.2).
6. **Scope / re-auth.** Add `gmail.modify` to `GMAIL_SCOPES` (keep readonly + send). Document that Simon must re-run `python -m trainline --gmail-auth` once after this story. Never commit tokens (FR45).

## Tasks / Subtasks

- [x] Extend `GmailClient` with attachment download + message modify (AC: #3, #6)
  - [x] `get_attachment(message_id, attachment_id) -> bytes`
  - [x] Walk `format=full` payload for parts with `filename` + `body.attachmentId` (image/*)
  - [x] `modify_message(message_id, *, add_label_ids=..., remove_label_ids=...)` (ensure ingested label exists)
  - [x] Update `GMAIL_SCOPES` to include `https://www.googleapis.com/auth/gmail.modify`
- [x] Pure(ish) ingest helpers in `trainline/adapters/gmail/` — **no** import of `ticket_intake` (AD-2) (AC: #1–#3)
  - [x] e.g. `ticket_mail.py`: query builder, part walk, choose save basename
  - [x] Accept destination `Path` for unclassified dir from CLI
- [x] CLI composition (AD-8) (AC: #1, #4)
  - [x] `--ingest-ticket-mail` (+ optional `--tickets-root`)
  - [x] `_run_ingest_ticket_mail(...)` loads Gmail config/creds, builds client, writes files, marks processed
  - [x] Call ingest at start of `_run_weekly_ops` before assess
- [x] Config knobs (optional env / `## Gmail API ##`) (AC: #2)
  - [x] `TICKET_MAIL_SUBJECT_PREFIX` default `TICKET`
  - [x] `TICKET_MAIL_LABEL` default `trainline-ticket` (search query)
  - [x] `TICKET_MAIL_INGESTED_LABEL` default `trainline-ticket-ingested`
- [x] Offline tests (AC: #5)
  - [x] `tests/test_ticket_mail_ingest.py` — mocked client + tmp unclassified
  - [x] Extend `tests/test_gmail_auth.py` scope assertions for `gmail.modify`
  - [x] Extend weekly-ops order test: ingest before assess
- [x] Do **not** implement daily Task Scheduler job here (Story 8.4); weekly-ops pre-hook is enough for Friday

## Dev Notes

### Locked product decisions (2026-07-20)

- Transport: **Gmail attachment drop** (not Syncthing for MVP).
- Cadence: **once daily** (8.4) + **always before Friday `--weekly-ops`** (this story hooks the latter).
- Subject convention for phone: start subject with **`TICKET`** (example: `TICKET GOD return 16 Jul`).

### Architecture compliance

- **AD-2:** `gmail` must not import `ticket_intake` / `config`. CLI loads `tickets_layout(root).unclassified`, passes `Path` into ingest.
- **AD-8:** Orchestration only in `cli.py` (or thin helper imported only by CLI).
- **NFR3:** Keep AVG CA path (`_ca_certs_path` / `_inject_truststore`) for all new Gmail HTTP calls.
- **NFR11 / NFR16:** Default pytest stays offline; any live ingest test is `@gmail` opt-in.

### Reuse — do not reinvent

| Existing | Use for |
| --- | --- |
| `GmailClient.search_messages` / `get_message` | Discover + load MIME |
| `claim_mail` payload walk pattern | Model attachment walk similarly (text-only today) |
| `tickets_layout(...).ensure()` + `layout.unclassified` | Destination dir only from CLI |
| `load_gmail_config` / `get_credentials` | Auth |
| `_run_weekly_ops` | Insert `_run_ingest_ticket_mail` as step 0 |

### Suggested Gmail search query

```
subject:TICKET has:attachment -label:trainline-ticket-ingested
```

Or with user label: `label:trainline-ticket has:attachment -label:trainline-ticket-ingested`.

Create labels via API if missing (`users.labels.create`) or document one-time manual create in Gmail UI.

### Attachment / filename rules (MVP)

- Accept: `.jpg`, `.jpeg`, `.png` (align with classify). PDF optional if trivial (classify supports it).
- Save name: prefer original attachment filename if safe (`[A-Za-z0-9._-]+`); else `ticket-{messageId}-{partIndex}.jpg`.
- Collision: if path exists, append `-2`, `-3`, … (content-hash dedup is **8.2**).

### Files likely touched

```
trainline/adapters/gmail/auth.py          # GMAIL_SCOPES += modify
trainline/adapters/gmail/client.py        # get_attachment, modify_message, maybe ensure_label
trainline/adapters/gmail/ticket_mail.py   # NEW — query + extract (no ticket_intake import)
trainline/adapters/gmail/__init__.py
trainline/cli.py                          # --ingest-ticket-mail + weekly-ops hook
trainline/adapters/config.py              # optional ticket-mail knobs (or env-only in CLI)
tests/test_ticket_mail_ingest.py          # NEW
tests/test_gmail_auth.py                  # scopes
tests/test_weekly_ops_cli.py              # ingest-first order
scripts/weekly_ops.ps1                    # unchanged if CLI hooks ingest
```

### UPDATE surfaces (preserve behavior)

- **`cli._run_weekly_ops`:** Today assess→classify→file→email→marker. Keep intact; only prepend ingest. Marker only after full success.
- **`GMAIL_SCOPES`:** Expanding scopes invalidates old refresh tokens until `--gmail-auth` — surface `insufficientPermissions` with that hint.
- **`GmailClient`:** Keep existing search/get/send contracts and retry policy.

### Anti-patterns

- Do not import `ticket_intake` from `gmail`.
- Do not disable TLS verify.
- Do not poll every 15 minutes (rejected cadence).
- Do not implement Syncthing watcher (8.3) or phone setup doc / daily schtask (8.4) here.
- Do not treat `gmail.readonly` as enough for labels — add `gmail.modify` and re-auth.

### Testing requirements

```powershell
pytest tests/test_ticket_mail_ingest.py tests/test_gmail_auth.py tests/test_weekly_ops_cli.py -q
# After --gmail-auth with new scopes (manual / live):
# pytest -m gmail -o addopts=   # existing live tests must still pass
```

Offline fixture: minimal Gmail `users.messages.get` JSON with one `parts[]` entry `filename=ticket.jpg`, `mimeType=image/jpeg`, `body.attachmentId=ATT1`; mock `attachments.get` to return base64url bytes of a tiny JPEG.

### Previous / adjacent intelligence

- Epic 7 Gmail port: file token, AVG CA, digest prefer Gmail — `7-1-gmail-api-adapter-port.md`, `epic-7-closeout-2026-07-20.md`.
- Weekly marker + `--weekly-ops` already land; ingest must not break marker semantics.
- Classify expects files in `tickets/unclassified/` then moves them — ingest only **writes**, never classifies.

### Git intelligence

Recent commits are Epic 6 OCR/filing focused; follow patterns in tree `adapters/gmail/*` and `tests/test_gmail_*.py`.

### References

- Epics: Story 8.1; FR41–FR45; NFR14–NFR16; cadence lock 2026-07-20
- Architecture: AD-2, AD-8, NFR3 (TLS), ARCHITECTURE-SPINE deferred “ticket ingest adapter”
- Prior: `trainline/adapters/gmail/{auth,client,claim_mail}.py`, `ticket_intake.tickets_layout`
- Close-out: `_bmad-output/implementation-artifacts/epic-7-closeout-2026-07-20.md`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
