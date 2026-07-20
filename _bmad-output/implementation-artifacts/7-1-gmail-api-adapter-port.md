---
story_key: 7-1-gmail-api-adapter-port
epic: 7
status: review
created: 2026-07-20
baseline_commit: 9cdfd10
---

# Story 7.1: Gmail API adapter (port from financeTracker_SW)

Status: review

## Story

As a developer,
I want Gmail OAuth + send/search behind a hexagonal adapter,
So that digests and claim-status lookups use the same Google API as financeTracker.

## Acceptance Criteria

1. **Offline unit tests (mocked Google client).** Auth scopes include `gmail.readonly` + `gmail.send`; token load/refresh/store work against a file path; search and send are covered (NFR11).
2. **`--gmail-auth`.** With `## Gmail API ##` keys in `trainConfig.txt`, InstalledAppFlow completes and writes the token file (FR40). Must work under AVG TLS (`creds/ca-bundle.pem` → httplib2 `ca_certs` + `REQUESTS_CA_BUNDLE` for token exchange).
3. **Missing credentials.** When digest send is requested without Gmail token/config, a clear error explains how to auth; assess/classify output is still written.
4. **Claim-status mail characterised (FR38 prep).** Offline fixtures + parser for SWR Delay Repay emails; live `@gmail` test finds RECEIVED / Approved / PAYMENT SENT for `SWR-0218-108-579`. (Wiring into Table 2 is Stories 7.4 / 7.5.)

## Already landed (do not reimplement)

| Area | Location |
| --- | --- |
| OAuth scopes + file token | `trainline/adapters/gmail/auth.py` |
| `--gmail-auth` CLI | `trainline/cli.py` → `_run_gmail_auth` |
| Config load | `load_gmail_config` in `adapters/config.py` (`## Gmail API ##`) |
| Search / get / send client | `trainline/adapters/gmail/client.py` (AVG CA via httplib2) |
| Offline client/auth tests | `tests/test_gmail_client.py`, `tests/test_gmail_auth.py`, `tests/test_gmail_config.py` |
| SWR claim mail parser + fixtures | `adapters/gmail/claim_mail.py`, `tests/fixtures/swr_claim_mail/`, `tests/test_swr_claim_mail.py` |
| Live inbox characterisation | `tests/test_live_gmail_claim_mail.py` (`pytest -m gmail`) — **PASSED** 2026-07-20 |
| FR38 contract note | `_bmad-output/implementation-artifacts/epic-7-fr38-inbox-contract-2026-07-20.md` |

### Observed SWR email contract (lock this in stories 7.4/7.5)

- **From:** `No-replySWRDR@firstcustomercontact.com`
- **Subject:** `South Western Railway Delay Repay - Claim {SWR-####-###-###} - {RECEIVED|Approved|PAYMENT SENT}`
- **Stages:** `received` → `approved` → `paid` (`ClaimMailStage`)
- **Successful for Table 2 omission:** only after `paid` / `PAYMENT SENT`

## Tasks / Subtasks

- [x] Wire **digest send** path to prefer Gmail API (`GmailClient.send_message`) when Gmail config+token present; keep SMTP as legacy fallback until removed (FR35). Do **not** import `config` from `notification` — duck-type or pass client from CLI (AD-2).
- [x] On missing Gmail creds when Gmail send is selected: clear message mentioning `python -m trainline --gmail-auth`; do not fail assess/classify writes.
- [x] Ensure `_run_gmail_auth` / `GmailClient` always apply project `creds/ca-bundle.pem` without requiring the user to set env vars manually.
- [x] Pin `google-auth-httplib2` + `httplib2` in `requirements-dev.txt` (already added).
- [x] Optional: thin live smoke `@gmail` that sends a one-line test message to `DIGEST_TO` (opt-in only).
- [x] Mark story ready for review in `sprint-status.yaml` when AC1–AC3 green.

## Dev Notes

### Architecture guardrails

- **AD-2:** `notification` must not import `gmail` or `config`. CLI (composition root) loads config, builds `GmailClient`, passes a send callable / duck-typed transport into digest send.
- **AD-8:** Weekly orchestration stays in CLI (Story 7.3); this story only completes the adapter + digest transport seam.
- **NFR3:** Gmail discovery uses **httplib2**, which ignores `REQUESTS_CA_BUNDLE` alone — always pass `ca_certs=` from `creds/ca-bundle.pem` (see `client._ca_certs_path`). Token exchange uses `requests` → set `REQUESTS_CA_BUNDLE` in `auth._inject_truststore`.
- **NFR11:** Default `pytest` excludes `@live`, `@vision`, `@gmail`.

### Anti-patterns to avoid

- Do not put claim lifecycle state or Table 2 rendering in this story (7.4 / 7.5).
- Do not hard-code claim id `SWR-0218-108-579` outside fixtures / live characterisation tests.
- Do not disable TLS verify (`verify=False` / `disable_ssl_certificate_validation`).

### How to run

```powershell
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
python -m trainline --gmail-auth
pytest tests/test_gmail_client.py tests/test_gmail_auth.py tests/test_swr_claim_mail.py tests/test_digest_gmail_transport.py -q
pytest -m gmail tests/test_live_gmail_claim_mail.py tests/test_live_gmail_digest_send.py -v
```

### References

- Epics: Story 7.1 AC; FR35, FR40, NFR11, FR37–FR38 (characterisation only)
- Architecture: AD-2, AD-8, NFR3 parallel for Gmail
- Prior port: `financeTracker_SW` `finance_copilot/gmail/{auth,client}.py` (SQLAlchemy token → file token here)
- Inbox contract: `epic-7-fr38-inbox-contract-2026-07-20.md`

## Dev Agent Record

### Implementation Plan

- Prefer Gmail in CLI composition root (`_try_gmail_digest_transport` → injectable `transport` into `send_digest`); SMTP remains legacy when Gmail config absent.
- Keep AD-2: `notification` unchanged (duck-typed headers + transport); no gmail/config imports there.
- Missing Gmail token with Gmail keys present → best-effort message mentioning `--gmail-auth`, assess writes preserved (exit 0 unless `--digest-strict`).
- Neither Gmail nor SMTP → exit 2 with auth hint.

### Debug Log

- Initial RED: digest still SMTP-only (`EmailConfigError` without SMTP_*).
- Test bug: double `capsys.readouterr()` discarded stderr; fixed to single capture.

### Completion Notes

- Wired digest send to prefer `GmailClient.send_message` when `## Gmail API ##` + token present; SMTP fallback when Gmail not configured (FR35).
- Clear `--gmail-auth` guidance on missing token/config; assess/classify still written (AC3).
- Confirmed/extended CA bundle auto-apply tests for auth `_inject_truststore` and client `_ca_certs_path` (NFR3).
- Deps already pinned in `requirements-dev.txt`; added opt-in `@gmail` send smoke.
- Offline suite: 393 passed, 73 deselected (`@live`/`@vision`/`@gmail`).

## File List

- `trainline/cli.py`
- `tests/test_digest_gmail_transport.py`
- `tests/test_gmail_auth.py`
- `tests/test_gmail_client.py`
- `tests/test_live_gmail_digest_send.py`
- `_bmad-output/implementation-artifacts/7-1-gmail-api-adapter-port.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-20: Prefer Gmail API for digest send (SMTP legacy fallback); missing-cred auth hint; CA-bundle tests; live Gmail send smoke; status → review.
