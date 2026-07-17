"""Acceptance tests for Story 4.3 CLI digest integration.

Maps one-to-one to ``tests/features/digest.feature``.
"""
from __future__ import annotations

import io
import shlex
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests._fakes import FakeResponse, FakeSession, FakeSmtpTransport
from trainline import cli
from trainline.adapters.hsp_client import HspClient

scenarios("features/digest.feature")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SMTP = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO")


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))
    for key in REQUIRED_SMTP + ("DIGEST_FROM",):
        monkeypatch.delenv(key, raising=False)
    # Default: no injected transport (digest must not send)
    monkeypatch.setattr(cli, "_digest_transport", None)
    return {
        "today": date(2026, 7, 15),
        "tmp": tmp_path,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "session": None,
        "transport": None,
    }


@given(parsers.parse('today is "{iso}"'))
def set_today(world, iso, monkeypatch):
    world["today"] = date.fromisoformat(iso)
    monkeypatch.setattr(cli, "_today", lambda: world["today"])


@given("a stub HSP transport that returns no claimable services")
def stub_transport(world, monkeypatch):
    def handler(url, kw):
        if "serviceMetrics" in url:
            return FakeResponse({"Services": []})
        return FakeResponse({"serviceAttributesDetails": {}})

    world["session"] = FakeSession(handler=handler)

    def fake_build(session=None, cache_dir=None, credentials_path=None):
        from trainline.adapters.config import load_hsp_credentials
        load_hsp_credentials(credentials_path)
        return HspClient("u", "p", session=world["session"], cache_dir=cache_dir)

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


@given("valid SMTP environment variables are set")
def smtp_env(world, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "s3cret")
    monkeypatch.setenv("DIGEST_TO", "simon@example.test")


@given("no email environment variables are set")
def no_smtp(world, monkeypatch):
    for key in REQUIRED_SMTP + ("DIGEST_FROM",):
        monkeypatch.delenv(key, raising=False)


@given("a recording digest transport is installed")
def recording_transport(world, monkeypatch):
    transport = FakeSmtpTransport()
    world["transport"] = transport
    monkeypatch.setattr(cli, "_digest_transport", transport)


@given("a failing digest transport is installed")
def failing_transport(world, monkeypatch):
    def boom(msg, config):
        raise OSError("SMTP connection refused")

    world["transport"] = boom
    monkeypatch.setattr(cli, "_digest_transport", boom)


@when(parsers.parse("I run the MVP command with args {argv}"))
def run_with_argv(world, argv):
    args = shlex.split(argv)
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


@then("one digest email was sent")
def one_digest(world):
    assert isinstance(world["transport"], FakeSmtpTransport)
    assert len(world["transport"].sent) == 1


@then("no digest email was sent")
def no_digest(world):
    assert isinstance(world["transport"], FakeSmtpTransport)
    assert len(world["transport"].sent) == 0


@then("the digest subject mentions claimable rows or none")
def subject_ok(world):
    msg, _ = world["transport"].sent[0]
    subj = msg["Subject"]
    assert "digest" in subj.casefold()
    assert "claimable" in subj.casefold()


@then("stderr names missing SMTP keys")
def stderr_smtp_keys(world):
    err = world["stderr"]
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO"):
        assert key in err, f"{key} not in stderr: {err!r}"
