"""Epic 9 / Story 9.4 — CLI Table 2 build + mark_reported_paid (AD-20)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline import cli
from trainline.adapters.claim_lifecycle import LifecycleStore


def _seed_store(path: Path) -> LifecycleStore:
    store = LifecycleStore(path)
    store.record_submitted(
        "SWR-0001-000-001", date="2026-07-01", direction="outbound"
    )
    store.record_submitted(
        "SWR-0002-000-002", date="2026-07-02", direction="inbound"
    )
    store.record_submitted(
        "SWR-0003-000-003", date="2026-07-03", direction="outbound"
    )
    # Advance 0002 to approved, 0003 to paid (not yet reported)
    store.apply_stage("SWR-0002-000-002", "received")
    store.apply_stage("SWR-0002-000-002", "approved")
    store.apply_stage("SWR-0003-000-003", "received")
    store.apply_stage("SWR-0003-000-003", "approved")
    store.apply_stage("SWR-0003-000-003", "paid")
    return store


@pytest.mark.offline
def test_build_table2_displays_submitted_as_in_flight(tmp_path):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path)
    rows, paid_ids = cli._build_table2(out_dir=tmp_path)
    statuses = {r["claim_id"]: r["status"] for r in rows}
    assert statuses["SWR-0001-000-001"] == "in_flight"
    assert statuses["SWR-0002-000-002"] == "approved"
    assert statuses["SWR-0003-000-003"] == "paid"
    assert paid_ids == ["SWR-0003-000-003"]


@pytest.mark.offline
def test_build_table2_omits_reported_paid(tmp_path):
    path = tmp_path / "claim-lifecycle.json"
    store = _seed_store(path)
    store.mark_reported_paid(["SWR-0003-000-003"])
    rows, paid_ids = cli._build_table2(out_dir=tmp_path)
    claim_ids = {r["claim_id"] for r in rows}
    assert "SWR-0003-000-003" not in claim_ids
    assert paid_ids == []
    # The other two remain
    assert "SWR-0001-000-001" in claim_ids
    assert "SWR-0002-000-002" in claim_ids


@pytest.mark.offline
def test_build_table2_empty_when_no_store(tmp_path):
    rows, paid_ids = cli._build_table2(out_dir=tmp_path)
    assert rows == []
    assert paid_ids == []


@pytest.mark.offline
def test_mark_paid_reported_after_email_stamps_only_paid_sent(tmp_path):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path)
    cli._mark_paid_reported_after_email(
        out_dir=tmp_path, claim_ids=["SWR-0003-000-003"]
    )
    store = LifecycleStore(path)
    paid = store.get("SWR-0003-000-003")
    assert paid.reported_paid_at is not None
    # Non-paid rows are untouched
    assert store.get("SWR-0001-000-001").reported_paid_at is None
    assert store.get("SWR-0002-000-002").reported_paid_at is None


@pytest.mark.offline
def test_mark_paid_reported_after_email_no_op_for_empty(tmp_path):
    path = tmp_path / "claim-lifecycle.json"
    store = _seed_store(path)
    cli._mark_paid_reported_after_email(out_dir=tmp_path, claim_ids=[])
    # No store reload needed — same in-memory snapshot untouched
    assert store.get("SWR-0003-000-003").reported_paid_at is None


@pytest.mark.offline
def test_run_weekly_ops_email_returns_paid_ids_and_table2_renders(
    tmp_path, monkeypatch
):
    """End-to-end: lifecycle store -> ``_run_weekly_ops_email`` -> sink file
    contains Table 2 + paid claim ids are returned for marking."""
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path)

    sink = tmp_path / "ops-email.txt"
    monkeypatch.setenv("TRAINLINE_OPS_EMAIL_FILE", str(sink))

    rc, paid_ids = cli._run_weekly_ops_email(
        day_results=[],
        credentials_path=None,
        strict=False,
        filing_summary={},
        anchor_friday="2026-07-31",
        out_dir=tmp_path,
    )
    assert rc == 0
    assert paid_ids == ["SWR-0003-000-003"]
    body = sink.read_text(encoding="utf-8").casefold()
    assert "table 2" in body
    assert "in_flight" in body
    assert "swr-0003-000-003" in body
    assert "paid" in body


@pytest.mark.offline
def test_weekly_chain_marks_paid_after_email_success(monkeypatch, tmp_path):
    """Full ``--weekly-ops`` happy path: paid row is marked reported after
    a successful email send (Story 9.4 acceptance)."""
    path = tmp_path / "Results" / "claim-lifecycle.json"
    path.parent.mkdir(parents=True)
    store = LifecycleStore(path)
    store.record_submitted(
        "SWR-0003-000-003", date="2026-07-03", direction="outbound"
    )
    store.apply_stage("SWR-0003-000-003", "received")
    store.apply_stage("SWR-0003-000-003", "approved")
    store.apply_stage("SWR-0003-000-003", "paid")

    sink = tmp_path / "ops-email.txt"
    monkeypatch.setenv("TRAINLINE_OPS_EMAIL_FILE", str(sink))
    monkeypatch.setenv("TRAINLINE_SKIP_TICKET_INGEST", "1")

    monkeypatch.setattr(cli, "_run_weekly_assess", lambda **kw: (0, []))
    monkeypatch.setattr(cli, "_run_weekly_classify", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_file", lambda **kw: (0, {}))
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )

    rc = cli.main(
        [
            "--weekly-ops",
            "--out-dir",
            str(tmp_path / "Results"),
            "--tickets-root",
            str(tmp_path / "tickets"),
        ]
    )
    assert rc == 0
    after = LifecycleStore(path).get("SWR-0003-000-003")
    assert after.reported_paid_at is not None


@pytest.mark.offline
def test_weekly_chain_does_not_mark_paid_when_email_fails(
    monkeypatch, tmp_path, capsys
):
    path = tmp_path / "Results" / "claim-lifecycle.json"
    path.parent.mkdir(parents=True)
    store = LifecycleStore(path)
    store.record_submitted(
        "SWR-0003-000-003", date="2026-07-03", direction="outbound"
    )
    store.apply_stage("SWR-0003-000-003", "received")
    store.apply_stage("SWR-0003-000-003", "approved")
    store.apply_stage("SWR-0003-000-003", "paid")

    monkeypatch.setenv("TRAINLINE_SKIP_TICKET_INGEST", "1")
    monkeypatch.setattr(cli, "_run_weekly_assess", lambda **kw: (0, []))
    monkeypatch.setattr(cli, "_run_weekly_classify", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_file", lambda **kw: (0, {}))
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )

    # Force the email step to "fail" by pointing the sink at an unwritable
    # path: instead, swap in a failing email function returning non-zero rc.
    def _failing_email(**kw):
        return 1, ["SWR-0003-000-003"]

    monkeypatch.setattr(cli, "_run_weekly_ops_email", _failing_email)

    rc = cli.main(
        [
            "--weekly-ops",
            "--out-dir",
            str(tmp_path / "Results"),
            "--tickets-root",
            str(tmp_path / "tickets"),
            "--digest-strict",
        ]
    )
    assert rc != 0
    after = LifecycleStore(path).get("SWR-0003-000-003")
    assert after.reported_paid_at is None
