"""Acceptance tests for Story 6.4 ``--file`` pipeline.

Maps one-to-one to ``tests/features/file_pipeline.feature``.
"""
from __future__ import annotations

import io
import json
import shlex
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests._fakes import FakeResponse, FakeSession, FakeSmtpTransport
from trainline import cli
from trainline.adapters.claim_submission import FakeBrowserSession
from trainline.adapters.hsp_client import HspClient

scenarios("features/file_pipeline.feature")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SMTP = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO")


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


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))
    for key in REQUIRED_SMTP + ("DIGEST_FROM",):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cli, "_digest_transport", None)
    monkeypatch.setattr(cli, "_file_browser_factory", None)
    return {
        "today": date(2026, 7, 15),
        "tmp": tmp_path,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "browser": None,
        "transport": None,
        "ticket_path": None,
    }


@given(parsers.parse('today is "{iso}"'))
def set_today(world, iso, monkeypatch):
    world["today"] = date.fromisoformat(iso)
    monkeypatch.setattr(cli, "_today", lambda: world["today"])


@given(parsers.parse('a stubbed week with a 25-minute-late outbound on "{day}"'))
def stub_claimable(world, day, monkeypatch):
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


@given("credentials are discoverable at the default project path")
def default_creds(world, monkeypatch):
    creds = world["tmp"] / "creds" / "trainConfig.txt"
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text(
        "[configuration]\nusername=alice@example.com\npassword=secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr(cli, "_default_credentials_path", lambda: str(creds))


@given(parsers.parse('ready_to_claim has a ticket for "{day}"'))
def ready_ticket(world, day):
    root = world["tmp"] / "tickets"
    ready = root / "processed" / "ready_to_claim"
    claimed = root / "claimed"
    ready.mkdir(parents=True, exist_ok=True)
    claimed.mkdir(parents=True, exist_ok=True)
    _y, month, day_part = day.split("-")
    path = ready / f"{month}-{day_part}-BDD.jpg"
    path.write_bytes(b"ticket")
    world["ticket_path"] = path


@given("ready_to_claim is empty")
def ready_empty(world):
    ready = world["tmp"] / "tickets" / "processed" / "ready_to_claim"
    ready.mkdir(parents=True, exist_ok=True)
    (world["tmp"] / "tickets" / "claimed").mkdir(parents=True, exist_ok=True)


@given("a recording fake browser is installed")
def recording_browser(world, monkeypatch):
    browser = FakeBrowserSession()
    world["browser"] = browser
    monkeypatch.setattr(cli, "_file_browser_factory", lambda: browser)


@given("valid SMTP environment variables are set")
def smtp_env(world, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "s3cret")
    monkeypatch.setenv("DIGEST_TO", "simon@example.test")


@given("a recording digest transport is installed")
def recording_transport(world, monkeypatch):
    transport = FakeSmtpTransport()
    world["transport"] = transport
    monkeypatch.setattr(cli, "_digest_transport", transport)


@when(parsers.parse("I run the MVP command with args {argv}"))
def run_with_argv(world, argv):
    args = shlex.split(argv)
    # Ensure tickets root is under tmp (cwd already tmp)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        world["exit_code"] = cli.main(args)
    world["stdout"] = out.getvalue()
    world["stderr"] = err.getvalue()


@then("the command exits successfully")
def exits_ok(world):
    assert world["exit_code"] == 0, world["stderr"]


@then("the command exits with a non-zero status")
def exits_nonzero(world):
    assert world["exit_code"] not in (0, None), world["stderr"]


@then(parsers.parse('claim files are written under "{dirname}"'))
def claims_written(world, dirname):
    base = world["tmp"] / dirname
    assert (base / "claims.csv").is_file()
    assert (base / "claims.json").is_file()


@then("the filing audit has one success line")
def audit_ok(world):
    audit = world["tmp"] / "Results" / "filing-audit.jsonl"
    assert audit.is_file()
    lines = [ln for ln in audit.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["outcome"] == "success"


@then("the ticket moved to claimed")
def ticket_claimed(world):
    assert world["ticket_path"] is not None
    assert not world["ticket_path"].exists()
    claimed = list((world["tmp"] / "tickets" / "claimed").glob("*-BDD.jpg"))
    assert len(claimed) == 1


@then("one digest email was sent")
def one_digest(world):
    assert isinstance(world["transport"], FakeSmtpTransport)
    assert len(world["transport"].sent) == 1


@then("no filing audit was written")
def no_audit(world):
    assert not (world["tmp"] / "Results" / "filing-audit.jsonl").exists()


@then("the fake browser was not used")
def browser_idle(world):
    assert world["browser"] is not None
    assert world["browser"].fills == []
