---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.5: CLI --classify-tickets + config paths

Status: done

## Story

As Simon, I want `python -m trainline --classify-tickets` to batch-process `tickets/unclassified`.

## Acceptance Criteria

1. `--classify-tickets` / `--tickets-root` on CLI.
2. `RunConfig.tickets_root` + default `ticket_dir` = `tickets/processed/ready_to_claim`.

## File List

- `trainline/cli.py`
- `trainline/adapters/config.py`
- `tests/test_classify_tickets_cli.py`
