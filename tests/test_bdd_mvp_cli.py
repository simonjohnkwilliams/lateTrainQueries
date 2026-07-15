"""Acceptance tests for the MVP one-liner CLI (offline).

Maps one-to-one to ``tests/features/mvp_cli.feature``.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests._fakes import FakeResponse, FakeSession
from trainline import cli
from trainline.adapters.hsp_client import HspClient

scenarios("features/mvp_cli.feature")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def world(tmp_path, monkeypatch):
    # Run as if CWD is a throwaway project root with Results/ under it.
    monkeypatch.chdir(tmp_path)
    # Ensure package still importable
    monkeypatch.syspath_prepend(str(PROJECT_ROOT))
    return {
        "today": date(2026, 7, 15),
        "tmp": tmp_path,
        "exit_code": None,
        "dates_seen": None,
        "stdout": "",
        "creds_path": None,
        "session": None,
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

    session = FakeSession(handler=handler)
    world["session"] = session

    real_build = cli.build_client

    def fake_build(session=None, cache_dir=None, credentials_path=None):
        # Still exercise credential resolution path.
        from trainline.adapters.config import load_hsp_credentials
        load_hsp_credentials(credentials_path)
        return HspClient("u", "p", session=world["session"], cache_dir=cache_dir)

    monkeypatch.setattr(cli, "build_client", fake_build)

    real_run = cli.run

    def tracking_run(config, dates, out_csv, out_json, **kwargs):
        world["dates_seen"] = list(dates)
        return real_run(config, dates, out_csv, out_json, **kwargs)

    monkeypatch.setattr(cli, "run", tracking_run)


@given("credentials are discoverable at the default project path")
def default_creds(world, monkeypatch):
    creds = world["tmp"] / "creds" / "trainConfig.txt"
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text(
        "[configuration]\nusername=alice@example.com\npassword=secret\n"
        "## Historical Service Performance (HSP) - API Information ##\n"
        "Service Metrics URL=https://hsp-prod.rockshore.net/api/v1/serviceMetrics\n"
        "Service Details URL=https://hsp-prod.rockshore.net/api/v1/serviceDetails\n",
        encoding="utf-8",
    )
    world["creds_path"] = creds
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr(cli, "_default_credentials_path", lambda: str(creds))


@given("HSP_CREDENTIALS_FILE is unset")
def unset_env(monkeypatch):
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)


@given(parsers.parse('credentials exist at "{rel}" relative to the project'))
def creds_at(world, monkeypatch, rel):
    path = world["tmp"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[configuration]\nusername=alice@example.com\npassword=secret\n",
        encoding="utf-8",
    )
    world["creds_path"] = path
    monkeypatch.setattr(cli, "_default_credentials_path", lambda: str(path))




@when("I run the MVP command")
def run_default(world, capsys):
    world["exit_code"] = cli.main([])
    world["stdout"] = capsys.readouterr().out


@when(parsers.parse("I run the MVP command with args {argv}"))
def run_with_argv(world, argv, capsys):
    import shlex
    args = shlex.split(argv)
    world["exit_code"] = cli.main(args)
    world["stdout"] = capsys.readouterr().out


@then("the analysed dates are the 5 weekdays ending yesterday")
def dates_last_week(world):
    assert world["dates_seen"] == [
        "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14",
    ]


@then("the analysed dates are exactly 3 weekdays ending yesterday")
def dates_three(world):
    assert world["dates_seen"] == ["2026-07-10", "2026-07-13", "2026-07-14"]


@then(parsers.parse('the analysed dates are "{csv}"'))
def dates_exact(world, csv):
    assert world["dates_seen"] == csv.split(",")


@then(parsers.parse('claim files are written under "{dirname}"'))
def files_written(world, dirname):
    out = world["tmp"] / dirname
    assert (out / "claims.csv").is_file()
    assert (out / "claims.json").is_file()
    assert json.loads((out / "claims.json").read_text(encoding="utf-8")) == []


@then("the command exits successfully")
def exit_ok(world):
    assert world["exit_code"] == 0
