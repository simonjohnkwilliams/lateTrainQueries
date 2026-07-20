---
story_key: 8-2-dedup-naming-safety
epic: 8
status: review
created: 2026-07-20
depends_on: [8-1]
---

# Story 8.2: Dedup, naming, and safety

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a developer,
I want stable names and hash dedup,
So that classify never sees duplicate junk.

## Acceptance Criteria

1. **Content-hash dedup (FR42).** Two deliveries of identical image bytes (same mail twice before label, or Gmail + folder later) result in **one** file under `tickets/unclassified/` (or the second write is skipped with a clear log line).
2. **Stable naming (FR43).** Saved names are sortable and safe: prefer `YYYYMMDD-HHMMSS-<shortHash>-<sanitizedOriginal>` or document the chosen scheme; no path separators / spaces that break Windows or classify.
3. **Non-image / empty skip (FR44).** Non-image MIME, zero-byte, or corrupt/empty attachments are skipped and logged; ingest exits **0** (not a hard failure).
4. **Cross-source ready.** Dedup store is keyed by content hash (and optionally Gmail `messageId:attachmentId`) so Story 8.3 folder ingest can share the same helper without importing Gmail (AD-2).
5. **Offline tests.** Fixture bytes written twice → single file; `.txt` / empty part skipped; hash collision on different names still dedups.

## Tasks / Subtasks

- [x] Add small pure helper module (AC: #1, #4) — e.g. `trainline/adapters/ticket_drop.py` or under `gmail/` only if Gmail-specific; prefer **neutral** adapter so folder watcher reuses it
  - [x] `content_hash(data: bytes) -> str` (sha256 hex truncated ok)
  - [x] `unique_drop_path(dest_dir, data, original_name) -> Path | None` — returns None if hash already present
  - [x] Persist seen hashes under gitignored state (e.g. `Results/ticket-drop-hashes.json` or sidecar `.drop-hashes` under tickets root) — never commit
- [x] Wire into Gmail ingest from 8.1 (AC: #1–#3) — replace naive `-2` suffix collision with hash gate
- [x] Sanitize filenames (AC: #2) — strip path components; allow `[A-Za-z0-9._-]`; map others to `_`
- [x] Offline tests `tests/test_ticket_drop_dedup.py` (AC: #5)
- [x] Document hash store path in Dev Notes / `.gitignore` if new path outside `Results/` / `tickets/`

## Dev Notes

### Depends on 8.1

Implement **after** `--ingest-ticket-mail` exists. If 8.1 only has message-label idempotency, this story hardens byte-level dedup.

### Architecture

- **AD-2:** Dedup helper must not import `gmail` or `ticket_intake`. CLI/gmail ingest passes `bytes` + `Path`.
- Prefer one shared module used by mail ingest (8.1) and folder ingest (8.3).

### Anti-patterns

- Do not delete existing unclassified files that classify already owns without hash proof.
- Do not store full image blobs in the hash index — hashes + optional source ids only.
- Do not require network for tests.

### References

- Epics Story 8.2; FR42–FR44
- Story 8.1: `_bmad-output/implementation-artifacts/8-1-gmail-ticket-drop-mvp.md`
- `ticket_intake.tickets_layout` — destination only via CLI

## Dev Agent Record

### Completion Notes List

### File List
