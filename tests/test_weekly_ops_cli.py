"""Epic 7 / Story 7.3 + 8.1 — ``--weekly-ops`` chain order (FR34, FR39)."""
from __future__ import annotations

from datetime import date

import pytest

from trainline import cli
from trainline.adapters.schedule_window import prior_working_week

_WEEKLY_ENV = (
    "TRAINLINE_SKIP_TICKET_INGEST",
    "TRAINLINE_OPS_EMAIL_FILE",
    "TRAINLINE_AS_OF",
    "TRAINLINE_TICKETS_ROOT",
)


@pytest.fixture(autouse=True)
def _clear_weekly_env(monkeypatch):
    for key in _WEEKLY_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.offline
def test_weekly_ops_call_order_ingest_assess_classify_file_email(monkeypatch, tmp_path):
    order: list[str] = []

    monkeypatch.setattr(
        cli, "_run_ingest_ticket_mail", lambda **kw: order.append("ingest") or 0
    )
    monkeypatch.setattr(
        cli,
        "_run_weekly_assess",
        lambda **kw: (order.append("assess") or 0, []),
    )
    monkeypatch.setattr(
        cli, "_run_weekly_classify", lambda **kw: order.append("classify") or 0
    )
    monkeypatch.setattr(
        cli, "_run_weekly_file", lambda **kw: order.append("file") or (0, {})
    )
    monkeypatch.setattr(
        cli, "_run_weekly_ops_email", lambda **kw: order.append("email") or 0
    )
    monkeypatch.setattr(cli, "_mark_weekly_complete", lambda *a, **k: None)
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )

    rc = cli.main(["--weekly-ops", "--out-dir", str(tmp_path / "Results")])
    assert rc == 0
    assert order == ["ingest", "assess", "classify", "file", "email"]


@pytest.mark.offline
def test_weekly_ops_uses_prior_working_week(monkeypatch, tmp_path):
    captured = {}

    def fake_assess(**kw):
        captured["dates"] = kw.get("dates")
        return 0, []

    monkeypatch.setattr(cli, "_run_ingest_ticket_mail", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_assess", fake_assess)
    monkeypatch.setattr(cli, "_run_weekly_classify", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_file", lambda **kw: (0, {}))
    monkeypatch.setattr(cli, "_run_weekly_ops_email", lambda **kw: 0)
    monkeypatch.setattr(cli, "_mark_weekly_complete", lambda *a, **k: None)
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 7, 17))

    cli.main(["--weekly-ops", "--out-dir", str(tmp_path / "Results")])
    start, end = prior_working_week(date(2026, 7, 17))
    assert captured["dates"][0] == start.isoformat()
    assert captured["dates"][-1] == end.isoformat()
    assert len(captured["dates"]) == 5


@pytest.mark.offline
def test_weekly_ops_partial_failure_does_not_mark_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_run_ingest_ticket_mail", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_assess", lambda **kw: (0, []))
    monkeypatch.setattr(cli, "_run_weekly_classify", lambda **kw: 0)
    monkeypatch.setattr(cli, "_run_weekly_file", lambda **kw: (1, {}))
    monkeypatch.setattr(cli, "_run_weekly_ops_email", lambda **kw: 0)
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )
    marked = {"n": 0}
    monkeypatch.setattr(
        cli, "_mark_weekly_complete", lambda *a, **k: marked.__setitem__("n", marked["n"] + 1)
    )
    rc = cli.main(["--weekly-ops", "--out-dir", str(tmp_path / "Results")])
    assert rc != 0
    assert marked["n"] == 0


@pytest.mark.offline
def test_weekly_ops_skips_when_marker_present(monkeypatch, tmp_path, capsys):
    order: list[str] = []
    monkeypatch.setattr(
        cli, "_run_ingest_ticket_mail", lambda **kw: order.append("ingest") or 0
    )
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: True
    )
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 7, 17))

    rc = cli.main(["--weekly-ops", "--out-dir", str(tmp_path / "Results")])
    assert rc == 0
    assert order == []
    err = capsys.readouterr().err.casefold()
    assert "skipping" in err or "already complete" in err


@pytest.mark.offline
def test_weekly_status_prints_window_and_marker(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 7, 20))
    rc = cli.main(["--weekly-status", "--out-dir", str(tmp_path / "Results")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-07-17" in out
    assert "2026-07-06" in out
    assert "2026-07-10" in out


@pytest.mark.offline
def test_today_respects_trainline_as_of_env(monkeypatch):
    monkeypatch.setenv("TRAINLINE_AS_OF", "2026-07-31")
    assert cli._today() == date(2026, 7, 31)
    monkeypatch.delenv("TRAINLINE_AS_OF")
    # Without env, seam returns real today (not asserted — clock).


@pytest.mark.offline
def test_weekly_ops_ingest_hard_fail_skips_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_run_ingest_ticket_mail", lambda **kw: 2)
    monkeypatch.setattr(
        "trainline.adapters.weekly_marker.is_complete", lambda *a, **k: False
    )
    marked = {"n": 0}
    monkeypatch.setattr(
        cli, "_mark_weekly_complete", lambda *a, **k: marked.__setitem__("n", 1)
    )
    order = []
    monkeypatch.setattr(
        cli, "_run_weekly_assess", lambda **kw: order.append("assess") or (0, [])
    )
    rc = cli.main(["--weekly-ops", "--out-dir", str(tmp_path / "Results")])
    assert rc == 2
    assert order == []
    assert marked["n"] == 0
