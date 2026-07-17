---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 4.3: CLI digest integration

Status: done

## Story

As Simon,
I want the digest sent automatically after a successful assess run,
so that I get a weekly nudge without a separate command.

## Acceptance Criteria

1. **`--digest` sends email.** After assess completes, digest is sent when flag or config `send_digest: true`. *(FR22)*
2. **Default off.** Without flag/config, no email; assess output unchanged from Release 1.
3. **Best-effort by default.** SMTP failure logs warning; run still succeeds. `--digest-strict` fails the run on send error.
4. **BDD scenario.** Offline BDD covers digest rendering + CLI flag wiring (fake notification transport).

## Tasks / Subtasks

- [x] Wire `--digest` / `--no-digest` / `--digest-strict` in `cli.py`
- [x] `RunConfig.send_digest` (default False)
- [x] `run()` returns `(summary, day_results)`; digest after storage write
- [x] Injectable `_digest_transport` for offline tests
- [x] BDD: `tests/features/digest.feature` + `tests/test_bdd_digest.py`

## Dev Agent Record

### Completion Notes List

- Default assess-only preserved (no `--digest` → no email).
- Missing SMTP with `--digest` → exit 2 naming keys; claims still written.
- Best-effort vs `--digest-strict` covered offline with failing fake transport.
- Full suite: 191 passed, 17 deselected.

### File List

- `trainline/cli.py`
- `trainline/adapters/config.py` (`send_digest` on RunConfig)
- `tests/features/digest.feature`
- `tests/test_bdd_digest.py`
- `tests/test_cli.py`
- `tests/test_bdd_pipeline.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-16: CLI digest integration implemented; done.
