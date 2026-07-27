"""Story 6.4 — ``--file`` pipeline offline CLI checks."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tests._fakes import FakeResponse, FakeSession, FakeSmtpTransport
from trainline import cli
from trainline.adapters.claim_submission import FakeBrowserSession
from trainline.adapters.hsp_client import HspClient


def _stub_metrics(rids):
    return {"Services": [{"serviceAttributesMetrics": {"rids": [r]}} for r in rids]}


def _stub_details(rid, day, dep_hhmm, arr_hhmm, actual_arr_hhmm):
    return {
        "serviceAttributesDetails": {
            "date_of_service": day,
            "rid": rid,
            "locations": [
                {
                    "location": "GOD",
                    "gbtt_ptd": dep_hhmm,
                    "gbtt_pta": "",
                    "actual_td": dep_hhmm,
                    "actual_ta": "",
                    "late_canc_reason": "",
                },
                {
                    "location": "WAT",
                    "gbtt_ptd": "",
                    "gbtt_pta": arr_hhmm,
                    "actual_td": "",
                    "actual_ta": actual_arr_hhmm,
                    "late_canc_reason": "",
                },
            ],
        }
    }


def _wire_claimable_hsp(monkeypatch, tmp_path, day="2026-07-10"):
    details = _stub_details("rid-late", day, "0708", "0753", "0818")

    def handler(url, kw):
        if "serviceMetrics" in url:
            if kw["json"]["from_loc"] == "GOD":
                return FakeResponse(_stub_metrics(["rid-late"]))
            return FakeResponse(_stub_metrics([]))
        return FakeResponse(details)

    fake_http = FakeSession(handler=handler)

    def fake_build(session=None, cache_dir=None, credentials_path=None):
        from trainline.adapters.config import load_hsp_credentials

        load_hsp_credentials(credentials_path)
        return HspClient("u", "p", session=fake_http, cache_dir=cache_dir)

    monkeypatch.setattr(cli, "build_client", fake_build)
    creds = tmp_path / "creds" / "trainConfig.txt"
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n", encoding="utf-8"
    )
    monkeypatch.setattr(cli, "_default_credentials_path", lambda: str(creds))
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)


@pytest.mark.offline
def test_help_lists_file_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--file" in help_text
    assert "--live-submit" in help_text
    assert "--audit-path" in help_text


@pytest.mark.offline
def test_file_gate_blocks_submit_but_writes_claims(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _wire_claimable_hsp(monkeypatch, tmp_path)
    # ready_to_claim empty → gate fails
    ready = tmp_path / "tickets" / "processed" / "ready_to_claim"
    ready.mkdir(parents=True)

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "--file",
            "--strict-all-tickets",
            "--from-date", "2026-07-10",
            "--to-date", "2026-07-10",
            "--out-dir", "Results",
            "--cache-dir", str(tmp_path / "cache"),
            "--tickets-root", str(tmp_path / "tickets"),
        ])
    assert code == 1, err.getvalue()
    assert (tmp_path / "Results" / "claims.json").is_file()
    assert not (tmp_path / "Results" / "filing-audit.jsonl").exists()
    payload = out.getvalue()
    assert '"gate_ok": false' in payload.replace(" ", "") or '"gate_ok": false' in payload


@pytest.mark.offline
def test_file_happy_path_fake_browser_audit_and_claimed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _wire_claimable_hsp(monkeypatch, tmp_path)
    ready = tmp_path / "tickets" / "processed" / "ready_to_claim"
    claimed = tmp_path / "tickets" / "claimed"
    ready.mkdir(parents=True)
    claimed.mkdir(parents=True)
    ticket = ready / "07-10-ABC123.jpg"
    ticket.write_bytes(b"ticket-bytes")

    session = FakeBrowserSession()
    monkeypatch.setattr(cli, "_file_browser_factory", lambda: session)
    transport = FakeSmtpTransport()
    monkeypatch.setattr(cli, "_digest_transport", transport)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "s3cret")
    monkeypatch.setenv("DIGEST_TO", "simon@example.test")

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "--file",
            "--digest",
            "--from-date", "2026-07-10",
            "--to-date", "2026-07-10",
            "--out-dir", "Results",
            "--cache-dir", str(tmp_path / "cache"),
            "--tickets-root", str(tmp_path / "tickets"),
        ])
    assert code == 0, err.getvalue()
    audit = tmp_path / "Results" / "filing-audit.jsonl"
    assert audit.is_file()
    entry = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["outcome"] == "success"
    assert entry["swr_reference"]
    assert not ticket.exists()
    moved = list(claimed.glob("07-10-*"))
    assert len(moved) == 1
    assert len(session.fills) == 1
    assert len(transport.sent) == 1
    assert '"filed": 1' in out.getvalue() or '"filed":1' in out.getvalue().replace(" ", "")


@pytest.mark.offline
def test_assess_without_file_does_not_submit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _wire_claimable_hsp(monkeypatch, tmp_path)
    ready = tmp_path / "tickets" / "processed" / "ready_to_claim"
    ready.mkdir(parents=True)
    (ready / "07-10-ABC.jpg").write_bytes(b"x")
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return FakeBrowserSession()

    monkeypatch.setattr(cli, "_file_browser_factory", factory)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "--from-date", "2026-07-10",
            "--to-date", "2026-07-10",
            "--out-dir", "Results",
            "--cache-dir", str(tmp_path / "cache"),
        ])
    assert code == 0, err.getvalue()
    assert calls["n"] == 0
    assert not (tmp_path / "Results" / "filing-audit.jsonl").exists()
