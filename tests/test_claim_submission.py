"""Stories 6.2–6.3 — claim submission + audit (offline fake browser)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainline.adapters.claim_submission import (
    FakeBrowserSession,
    submit_all_claims,
    submit_claim,
)
from trainline.adapters.swr_mapping import map_claim_for_swr
from trainline.engine.models import Band, Claim, Direction


def _claim(date="2026-07-10", **kwargs) -> Claim:
    base = dict(
        date=date,
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=7 * 60,
        scheduled_arrival=8 * 60,
        actual_arrival=8 * 60 + 20,
        delay=20,
        band=Band.B15_29,
        reason=None,
    )
    base.update(kwargs)
    return Claim(**base)


@pytest.mark.offline
def test_fake_browser_fills_fields_and_returns_reference(tmp_path):
    ticket = tmp_path / "07-10-ABC123.jpg"
    ticket.write_bytes(b"ticket")
    claim = _claim()
    fields = map_claim_for_swr(claim)
    session = FakeBrowserSession()
    result = submit_claim(claim, fields, ticket, session, audit_path=None)
    assert result.ok
    assert result.swr_reference == "FAKE-SWR-0001"
    assert session.fills[0]["origin_station"] == "Godalming"
    assert session.fills[0]["ticket_path"] == str(ticket)


@pytest.mark.offline
def test_submit_writes_audit_jsonl(tmp_path):
    ticket = tmp_path / "07-10-ABC.jpg"
    ticket.write_bytes(b"x")
    audit = tmp_path / "filing-audit.jsonl"
    claim = _claim(reason="911")
    fields = map_claim_for_swr(claim)
    result = submit_claim(
        claim, fields, ticket, FakeBrowserSession(), audit_path=audit
    )
    assert result.ok
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["outcome"] == "success"
    assert entry["date"] == "2026-07-10"
    assert entry["raw_reason_code"] == "911"
    assert entry["swr_reference"]


@pytest.mark.offline
def test_batch_continues_after_one_failure(tmp_path):
    t1 = tmp_path / "07-09-A.jpg"
    t2 = tmp_path / "07-10-B.jpg"
    t1.write_bytes(b"a")
    t2.write_bytes(b"b")
    c1 = _claim(date="2026-07-09")
    c2 = _claim(date="2026-07-10")
    session = FakeBrowserSession(fail_dates={"2026-07-09"})
    audit = tmp_path / "audit.jsonl"
    batch = submit_all_claims(
        [
            (c1, map_claim_for_swr(c1), t1),
            (c2, map_claim_for_swr(c2), t2),
        ],
        session,
        audit_path=audit,
    )
    assert batch.filed == 1
    assert batch.failed == 1
    assert len(batch.results) == 2
    entries = [
        json.loads(line)
        for line in audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 2
    outcomes = {e["date"]: e["outcome"] for e in entries}
    assert outcomes["2026-07-09"] == "failure"
    assert outcomes["2026-07-10"] == "success"
