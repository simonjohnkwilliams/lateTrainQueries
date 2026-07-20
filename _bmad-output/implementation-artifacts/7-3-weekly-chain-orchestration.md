---
story_key: 7-3-weekly-chain-orchestration
epic: 7
status: ready-for-dev
created: 2026-07-20
depends_on: [7-1, 7-2]
---

# Story 7.3: Weekly chain orchestration

Status: ready-for-dev

## Story

As Simon,
I want one command that assesses → classifies tickets → files → emails,
So that the ops loop is a single scheduled entry point.

## Acceptance Criteria

1. **Single entrypoint.** `python -m trainline --weekly-ops` (or `--weekly`) runs in order: assess prior-week window → classify ticket inbox (Ollama) → ticket match / auto-file (Epic 6 `--file` path) → Gmail ops email **last** (FR34).
2. **Window from 7.2.** Assess dates come from `prior_week_window(as_of)` — not the current incomplete week.
3. **Classify rejects surface in email payload.** Each rejection carries short reason + file path for Table 1 (FR36) — rendering may land in 7.4; this story must **collect** the structured outcomes.
4. **Idempotency hook.** After a successful full run for an anchor Friday, write/consume the completion marker from Story 7.2 so Task Scheduler re-entry no-ops (FR39). Partial failure must **not** mark complete.
5. **Human reCAPTCHA policy.** Live file step follows Epic 6 policy (headed fill-to-Review + human captcha/Submit). Weekly dry-run / FakeBrowser mode must still exercise the chain offline.

## Tasks

- [ ] Add CLI flag `--weekly-ops` (name locked: prefer `--weekly-ops`).
- [ ] Composition-root function that sequences existing CLI pieces (reuse assess / classify / file helpers; do not duplicate optimiser).
- [ ] Pass structured run result into ops-email renderer (7.4) — stub ok if 7.4 not merged yet (print JSON summary).
- [ ] Offline test: fake adapters assert call order assess → classify → file → email.
- [ ] Document PowerShell one-liner for Task Scheduler calling `--weekly-ops`.

## Dev Notes

### Guardrails

- **AD-8:** Orchestration lives only in `cli.py` (or a thin `trainline/weekly_ops.py` imported solely by CLI) — not in `engine`.
- **AD-2:** Do not have `gmail` import `claim_submission` or vice versa; CLI wires both.
- Reuse Epic 6 `--file` live/fake paths; do not invent a second filing stack.
- OQ4: unattended Submit is blocked by reCAPTCHA — weekly live runs are attended or FakeBrowser for CI.

### Anti-patterns

- Do not assess “today’s week” when catching up after Friday.
- Do not send ops email before file attempt completes (success or recorded skip).
- Do not commit tokens / lifecycle DB files.

### Automated tests (pre-written)

| File | Notes |
| --- | --- |
| `tests/test_weekly_ops_cli.py` | Skip until `--weekly-ops` exists; asserts call order + window + no marker on fail |

### References

- Epics Story 7.3; FR34, FR36 (payload), FR39
- Stories 7.1 (Gmail send), 7.2 (window + marker), 6.4 (`--file` pipeline)
- Close-out: `epic-6-closeout-2026-07-17.md` (human captcha gate)
- Sign-off: `manual-validation-checklist-epic-7.md`