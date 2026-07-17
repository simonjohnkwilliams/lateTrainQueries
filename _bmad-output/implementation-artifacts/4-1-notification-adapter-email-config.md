---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 4.1: Notification adapter + email config

Status: done

## Story

As Simon,
I want email settings loaded from config/env,
so that digest credentials stay out of the repo and the notification seam is ready.

## Acceptance Criteria

1. **Missing config is reported clearly.** If digest is requested without SMTP settings, error names the missing keys (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO`). *(R2-NFR3 / NFR9; Epic AC)*
2. **Hexagonal boundary.** `trainline/adapters/notification.py` imports `engine.models` only among engine modules (no `hsp_client`, `claim_submission`, `config`, or other adapters). Import-boundary test extended with `notification` in `ADAPTER_NAMES`. *(R2-NFR1 / NFR7, AD-2)*
3. **Injectable transport.** `send_digest(subject, body_html, body_text, …)` accepts an optional transport for offline tests — no real SMTP. *(R2-NFR2, AD-13)*
4. **SMTP send works.** With valid config, a test message is delivered via the configured SMTP server (or fake transport in unit tests). *(Epic AC; AD-13)*

> **TDD (AD-12):** Write each AC as a failing `@offline` test / Gherkin scenario first, watch it fail, then implement. No criterion ships without a test. Default `pytest` stays offline (no network, no secrets).

## Tasks / Subtasks

- [x] **Task 1 — Email config loader (AC: 1)**
  - [x] In `trainline/adapters/config.py`, add frozen `EmailConfig` (`smtp_host`, `smtp_port: int`, `smtp_user`, `smtp_password`, `digest_to`; optional `digest_from` defaulting to `smtp_user` when unset).
  - [x] Add `EmailConfigError` and `load_email_config()` reading env vars `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO` (and optional `DIGEST_FROM`).
  - [x] Missing/blank required keys → single error listing **all** missing key names (not just the first). Invalid `SMTP_PORT` (non-int) → clear error naming `SMTP_PORT`.
  - [x] Never log password values. Credentials never in repo (FR17 / NFR9).
- [x] **Task 2 — Notification adapter seam (AC: 2, 3, 4)**
  - [x] Create `trainline/adapters/notification.py` with `send_digest(subject, body_html, body_text, config, *, transport=None)`.
  - [x] Build a multipart MIME message (text + HTML) via stdlib `email.message`; From = `digest_from` or `smtp_user`; To = `digest_to`.
  - [x] Default transport: stdlib `smtplib.SMTP` (connect → optional STARTTLS on port 587 → login → `send_message`). Adapters may use `smtplib`; engine must not (`FORBIDDEN_IO` already lists it).
  - [x] If `transport` is provided, call `transport(msg, config)` and **do not** open a real SMTP connection (offline seam, mirror HSP `session=`).
  - [x] **AD-2:** `notification` must not import `config`, `hsp_client`, `storage`, or any other adapter. Accept `config` by duck-typing (`smtp_host`, `smtp_port`, …). May import `engine.models` only if needed (4.1 likely needs none).
- [x] **Task 3 — Boundary + package registration (AC: 2)**
  - [x] Extend `ADAPTER_NAMES` in `tests/test_import_boundaries.py` with `"notification"`.
  - [x] Add `trainline.adapters.notification` to `MODULES` in `tests/test_package_imports.py`.
- [x] **Task 4 — Tests first (AC: 1–4)** — see Testing standards below.
  - [x] Unit: `tests/test_email_config.py`, `tests/test_notification.py` (+ `FakeSmtpTransport` in `tests/_fakes.py` or local).
  - [x] Acceptance BDD: `tests/features/notification.feature` + `tests/test_bdd_notification.py` mapping 1:1 to ACs.
  - [x] Confirm red → green; full suite offline green; import-boundary green.

## Dev Notes

### Why this story exists
Release 2 opens with the **notification** adapter (AD-13) so weekly digest (FR22) has a clean SMTP seam before content (4.2) or CLI wiring (4.3). Standalone value: credentials hygiene + injectable transport proven offline.

### Architecture constraints (must follow)
- **AD-1:** engine stays pure — no `smtplib` / email I/O in `engine/`.
- **AD-2 / AD-9:** adapters never import other adapters. `notification` ↛ `config`; cli (later 4.3) loads `EmailConfig` and passes it in.
- **AD-8:** this story does **not** wire CLI/`--digest` — that is Story 4.3. Only the seam + loader.
- **AD-13:** `send_digest(subject, html, text)` is the sole email entry point; transport injectable; credentials from env/config only.
- **NFR2 / NFR9:** offline default; SMTP secrets from env only, never committed.

### API sketch (authoritative for this story)

```python
# config.py
@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    digest_to: str
    digest_from: str | None = None  # None => use smtp_user at send time

class EmailConfigError(Exception): ...

def load_email_config(environ=None) -> EmailConfig:
    """Read SMTP_* / DIGEST_* from environ (default os.environ)."""

# notification.py
def send_digest(subject: str, body_html: str, body_text: str, config, *, transport=None) -> None:
    """Send digest. transport(msg, config) if given; else real SMTP."""
```

### Files being created / touched
- **UPDATE** `trainline/adapters/config.py` — add `EmailConfig`, `EmailConfigError`, `load_email_config`.
- **CREATE** `trainline/adapters/notification.py` — `send_digest`.
- **UPDATE** `tests/test_import_boundaries.py` — `ADAPTER_NAMES`.
- **UPDATE** `tests/test_package_imports.py` — `MODULES`.
- **UPDATE** `tests/_fakes.py` — optional `FakeSmtpTransport`.
- **CREATE** `tests/test_email_config.py`, `tests/test_notification.py`.
- **CREATE** `tests/features/notification.feature`, `tests/test_bdd_notification.py`.
- **DO NOT** change `cli.py` digest flags yet (Story 4.3).
- **DO NOT** add PyPI SMTP deps — stdlib only.

### Previous story intelligence (Release 1 patterns to copy)
- Credential errors name the missing env/file/keys (`CredentialsError` in config) — mirror for `EmailConfigError`.
- HSP injectable `session=` in `HspClient` — mirror as `transport=` on `send_digest`.
- Fake transport recorded in `tests/_fakes.py` (`FakeSession`) — add SMTP fake alongside.
- Import-boundary AST tests already forbid `smtplib` under `engine/`.

### Testing standards (AD-12)
- `@pytest.mark.offline` everywhere for 4.1; no `@live` SMTP unless later requested.
- **AC1:** unset all five → error message contains each of `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO`; partial set lists only the missing ones; bad port fails clearly.
- **AC2:** `notification.py` AST-clean vs other adapters; package imports; extend `ADAPTER_NAMES`.
- **AC3/AC4:** fake transport receives `EmailMessage` with correct Subject/From/To and both text + HTML parts; without transport injection, unit tests must not open network (always inject fake in offline tests). Real SMTP is manual/live only — out of default suite.
- BDD scenarios cover the Given/When/Then from epics.md Story 4.1.

### Out of scope (later stories)
- Digest HTML/text content from claims (4.2).
- `--digest` / `--no-digest` / `--digest-strict` CLI (4.3).
- Wiring after assess run (4.3 / 6.4).

### References
- [Source: `_bmad-output/planning-artifacts/epics.md` — Story 4.1]
- [Source: ARCHITECTURE-SPINE.md — AD-2, AD-13]
- [Source: prd addendum — Notification env table]
- [Source: FR22, NFR7, NFR9]

## Dev Agent Record

### Agent Model Used

Composer (Cursor Agent)

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- Implemented `EmailConfig` / `load_email_config` / `EmailConfigError` in config; `send_digest` with injectable transport in notification (AD-13).
- AD-2 preserved: notification does not import config (duck-typed settings).
- Tests: unit + BDD acceptance; FakeSmtpTransport; import-boundary + package imports updated.
- Full offline suite: 179 passed, 17 deselected (live).
- Code review patches: SMTP_SSL for 465, timeout=30, port range 1..65535, assert STARTTLS, strip blank digest_from, strengthen import-alias AD-2 detection.

### File List

- `trainline/adapters/config.py` (modified)
- `trainline/adapters/notification.py` (created)
- `tests/_fakes.py` (modified)
- `tests/test_email_config.py` (created)
- `tests/test_notification.py` (created)
- `tests/features/notification.feature` (created)
- `tests/test_bdd_notification.py` (created)
- `tests/test_import_boundaries.py` (modified)
- `tests/test_package_imports.py` (modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/4-1-notification-adapter-email-config.md` (modified)

## Change Log

- 2026-07-16: Story enriched for Release 2 implementation (CS).
- 2026-07-16: Implemented notification adapter + email config; status → review.
