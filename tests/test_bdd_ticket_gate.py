"""Acceptance tests for Epic 5 ticket gate (Stories 5.1–5.3)."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from trainline import cli
from trainline.adapters.ticket_gate import (
    EXPECTED_FORMAT,
    ScanResult,
    TicketFile,
    match_tickets_to_claims,
    scan_ticket_dir,
)
from trainline.engine.models import Band, Claim, Direction

scenarios("features/ticket_gate.feature")


@pytest.fixture
def world(tmp_path):
    return {
        "tmp": tmp_path,
        "ticket_dir": tmp_path / "ticket",
        "scan": None,
        "claims": [],
        "match": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "out_dir": tmp_path / "Results",
    }


def _claim(date: str) -> Claim:
    return Claim(
        date=date,
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=480,
        scheduled_arrival=540,
        actual_arrival=560,
        delay=20,
        band=Band.B15_29,
    )


@given(parsers.parse('a ticket directory with files "{names}"'))
def ticket_files(world, names):
    d = world["ticket_dir"]
    d.mkdir(parents=True, exist_ok=True)
    for name in names.split(","):
        name = name.strip()
        (d / name).write_bytes(b"x")


@given(parsers.parse('claims for dates "{dates}"'))
def claims_dates(world, dates):
    world["claims"] = [_claim(d.strip()) for d in dates.split(",") if d.strip()]


@given(parsers.parse('valid tickets for "{mmdds}"'))
def valid_tickets(world, mmdds):
    d = world["ticket_dir"]
    d.mkdir(parents=True, exist_ok=True)
    valid = []
    for mm_dd in mmdds.split(","):
        mm_dd = mm_dd.strip()
        name = f"{mm_dd}-T.pdf"
        path = d / name
        path.write_bytes(b"x")
        month, day = mm_dd.split("-")
        valid.append(TicketFile(
            path=path, month=month, day=day, ticket_number="T", mm_dd=mm_dd))
    world["scan"] = ScanResult(valid=tuple(valid), invalid=())


@given(parsers.parse('claims JSON with dates "{dates}"'))
def claims_json(world, dates):
    out = world["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for date in dates.split(","):
        date = date.strip()
        rows.append({
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
        })
    (out / "claims.json").write_text(json.dumps(rows), encoding="utf-8")
    (out / "claims.csv").write_text("date\n", encoding="utf-8")


@when("the ticket directory is scanned")
def do_scan(world):
    world["scan"] = scan_ticket_dir(world["ticket_dir"])


@when("tickets are matched to claims")
def do_match(world):
    world["match"] = match_tickets_to_claims(world["claims"], world["scan"])


@when("I run --check-tickets against that output")
def run_check(world):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        world["exit_code"] = cli.main([
            "--check-tickets",
            "--out-dir", str(world["out_dir"]),
            "--ticket-dir", str(world["ticket_dir"]),
        ])
    world["stdout"] = out.getvalue()
    world["stderr"] = err.getvalue()


@then(parsers.parse('one valid ticket is found for "{mm_dd}"'))
def one_valid(world, mm_dd):
    assert len(world["scan"].valid) == 1
    assert world["scan"].valid[0].mm_dd == mm_dd


@then(parsers.parse('invalid files include "{a}" and "{b}"'))
def invalid_include(world, a, b):
    names = {p.name for p, _ in world["scan"].invalid}
    assert a in names and b in names


@then("each invalid reason mentions the expected format")
def invalid_format(world):
    for _path, reason in world["scan"].invalid:
        assert EXPECTED_FORMAT in reason


@then("matching fails")
def match_fails(world):
    assert world["match"].ok is False


@then(parsers.parse('missing dates include "{date}"'))
def missing_include(world, date):
    assert date in world["match"].missing_dates


@then(parsers.parse('the mapping covers "{dates}"'))
def mapping_covers(world, dates):
    for date in dates.split(","):
        assert date.strip() in world["match"].mapping


@then("the command exits with a non-zero status")
def nonzero(world):
    assert world["exit_code"] not in (0, None), world["stderr"]


@then("the command exits successfully")
def ok(world):
    assert world["exit_code"] == 0, world["stderr"]


@then(parsers.parse('stderr mentions missing date "{date}"'))
def stderr_missing(world, date):
    assert date in world["stderr"]


@then(parsers.parse('stderr mentions misnamed file "{name}"'))
def stderr_misnamed(world, name):
    assert name in world["stderr"]
    assert EXPECTED_FORMAT in world["stderr"]
