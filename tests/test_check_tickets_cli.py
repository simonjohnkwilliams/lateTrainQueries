"""Epic 5 manual cases — fully automated offline CLI checks (tmp dirs only).

Creates and tears down ticket folders / claims.json under ``tmp_path`` so default
``pytest`` never touches the real ``ticket/`` or ``Results/`` trees.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tests._fakes import FakeResponse, FakeSession
from trainline import cli
from trainline.adapters.hsp_client import HspClient
from trainline.adapters.ticket_gate import EXPECTED_FORMAT


def _write_claims_json(out_dir: Path, dates: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "date": date,
            "direction": "outbound",
            "origin": "GOD",
            "destination": "WAT",
            "scheduled_departure": "08:00",
            "scheduled_arrival": "09:00",
            "actual_arrival": "09:20",
            "delay_min": 20,
            "band": "15-29",
            "reason": "",
        }
        for date in dates
    ]
    path = out_dir / "claims.json"
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out_dir / "claims.csv").write_text("date\n", encoding="utf-8")
    return path


def _run_check(out_dir: Path, ticket_dir: Path | None = None) -> tuple[int, str, str]:
    argv = ["--check-tickets", "--out-dir", str(out_dir)]
    if ticket_dir is not None:
        argv.extend(["--ticket-dir", str(ticket_dir)])
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# --- Manual case 1: missing dir / gaps --------------------------------------

@pytest.mark.offline
def test_check_tickets_missing_directory_lists_gaps(tmp_path):
    out_dir = tmp_path / "Results"
    _write_claims_json(out_dir, ["2026-07-10", "2026-07-13"])
    missing = tmp_path / "ticket"  # never created

    code, _out, err = _run_check(out_dir, missing)
    assert code != 0
    assert "2026-07-10" in err
    assert "2026-07-13" in err
    assert "not found" in err.casefold() or "missing" in err.casefold()


@pytest.mark.offline
def test_check_tickets_empty_ticket_dir_lists_gaps(tmp_path):
    out_dir = tmp_path / "Results"
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()
    _write_claims_json(out_dir, ["2026-07-10", "2026-07-15"])

    code, _out, err = _run_check(out_dir, ticket_dir)
    assert code != 0
    assert "2026-07-10" in err
    assert "2026-07-15" in err


# --- Manual case 2: misnamed file -------------------------------------------

@pytest.mark.offline
def test_check_tickets_reports_misnamed_file(tmp_path):
    out_dir = tmp_path / "Results"
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()
    (ticket_dir / "ticket.pdf").write_bytes(b"%PDF")
    (ticket_dir / "2026-07-10.jpg").write_bytes(b"x")
    _write_claims_json(out_dir, ["2026-07-10"])

    code, _out, err = _run_check(out_dir, ticket_dir)
    assert code != 0
    assert "ticket.pdf" in err
    assert "2026-07-10.jpg" in err or "2026-07-10" in err
    assert EXPECTED_FORMAT in err
    assert "2026-07-10" in err  # still missing a valid ticket for the claim date


# --- Manual case 3: happy path ----------------------------------------------

@pytest.mark.offline
def test_check_tickets_happy_path_all_dates_covered(tmp_path):
    out_dir = tmp_path / "Results"
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()
    dates = ["2026-07-10", "2026-07-13", "2026-07-14", "2026-07-15"]
    _write_claims_json(out_dir, dates)
    for iso in dates:
        _y, month, day = iso.split("-")
        (ticket_dir / f"{month}-{day}-AUTO.pdf").write_bytes(b"%PDF")

    code, out, err = _run_check(out_dir, ticket_dir)
    assert code == 0, err
    assert "All claim dates have matching ticket files" in out


# --- Manual case 4: custom --ticket-dir -------------------------------------

@pytest.mark.offline
def test_check_tickets_custom_ticket_dir(tmp_path):
    out_dir = tmp_path / "Results"
    custom = tmp_path / "my-tickets"
    custom.mkdir()
    (custom / "07-10-XYZ.pdf").write_bytes(b"%PDF")
    # Default ticket/ exists but is empty — must use --ticket-dir
    (tmp_path / "ticket").mkdir()
    _write_claims_json(out_dir, ["2026-07-10"])

    code, out, err = _run_check(out_dir, custom)
    assert code == 0, err
    assert "All claim dates" in out


# --- Manual case 5: assess-only unchanged -----------------------------------

@pytest.mark.offline
def test_assess_only_does_not_require_tickets(tmp_path, monkeypatch):
    """Plain assess writes claims without consulting ticket/."""
    monkeypatch.chdir(tmp_path)

    def handler(url, kw):
        if "serviceMetrics" in url:
            return FakeResponse({"Services": []})
        return FakeResponse({"serviceAttributesDetails": {}})

    session = FakeSession(handler=handler)

    def fake_build(session=None, cache_dir=None, credentials_path=None):
        from trainline.adapters.config import load_hsp_credentials
        load_hsp_credentials(credentials_path)
        return HspClient("u", "p", session=session, cache_dir=cache_dir)

    monkeypatch.setattr(cli, "build_client", fake_build)
    creds = tmp_path / "creds" / "trainConfig.txt"
    creds.parent.mkdir(parents=True)
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_default_credentials_path", lambda: str(creds))

    # No ticket directory at all
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "--from-date", "2026-07-10",
            "--to-date", "2026-07-10",
            "--out-dir", "Results",
            "--cache-dir", str(tmp_path / "cache"),
        ])
    assert code == 0, err.getvalue()
    assert (tmp_path / "Results" / "claims.json").is_file()
    assert not (tmp_path / "ticket").exists()


@pytest.mark.offline
def test_check_tickets_without_claims_json_fails_clearly(tmp_path):
    out_dir = tmp_path / "Results"
    out_dir.mkdir()
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()

    code, _out, err = _run_check(out_dir, ticket_dir)
    assert code != 0
    assert "claims" in err.casefold()
