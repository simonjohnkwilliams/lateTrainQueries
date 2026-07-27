"""Story 5.2: claim-to-ticket matcher (FR25)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.ticket_gate import (
    ScanResult,
    TicketFile,
    match_tickets_to_claims,
)
from trainline.engine.models import Band, Claim, Direction


def _claim(date: str, **kw) -> Claim:
    base = dict(
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
    base.update(kw)
    return Claim(**base)


def _ticket(mm_dd: str, name: str, root: Path) -> TicketFile:
    path = root / name
    month, day = mm_dd.split("-")
    ticket = name.rsplit(".", 1)[0].split("-", 2)[2]
    return TicketFile(
        path=path, month=month, day=day, ticket_number=ticket, mm_dd=mm_dd)


@pytest.mark.offline
def test_filter_claims_to_ticketed_dates_drops_missing(tmp_path):
    from trainline.adapters.ticket_gate import filter_claims_to_ticketed_dates

    root = tmp_path / "ticket"
    root.mkdir()
    scan = ScanResult(
        valid=(_ticket("07-24", "07-24-A.jpg", root),),
        invalid=(),
    )
    claims = [
        _claim("2026-07-20"),
        _claim("2026-07-24"),
        _claim("2026-07-24", direction=Direction.INBOUND),
    ]
    kept, dropped = filter_claims_to_ticketed_dates(claims, scan)
    assert [c.date for c in kept] == ["2026-07-24", "2026-07-24"]
    assert dropped == ("2026-07-20",)


@pytest.mark.offline
def test_missing_date_fails(tmp_path):
    root = tmp_path / "ticket"
    root.mkdir()
    for name in ("07-08-A.pdf", "07-10-B.pdf"):
        (root / name).write_bytes(b"x")
    scan = ScanResult(
        valid=(
            _ticket("07-08", "07-08-A.pdf", root),
            _ticket("07-10", "07-10-B.pdf", root),
        ),
        invalid=(),
    )
    claims = [
        _claim("2026-07-08"),
        _claim("2026-07-09"),
        _claim("2026-07-10"),
    ]
    result = match_tickets_to_claims(claims, scan)
    assert result.ok is False
    assert result.missing_dates == ("2026-07-09",)
    assert "2026-07-08" in result.mapping
    assert "2026-07-10" in result.mapping
    assert "2026-07-09" not in result.mapping


@pytest.mark.offline
def test_multiple_tickets_per_date_any_one_ok(tmp_path):
    root = tmp_path / "ticket"
    root.mkdir()
    scan = ScanResult(
        valid=(
            _ticket("07-10", "07-10-A.pdf", root),
            _ticket("07-10", "07-10-B.jpg", root),
        ),
        invalid=(),
    )
    result = match_tickets_to_claims([_claim("2026-07-10")], scan)
    assert result.ok is True
    assert result.missing_dates == ()
    assert result.mapping["2026-07-10"].name in {"07-10-A.pdf", "07-10-B.jpg"}


@pytest.mark.offline
def test_mapping_keys_are_iso_claim_dates(tmp_path):
    root = tmp_path / "ticket"
    root.mkdir()
    scan = ScanResult(
        valid=(_ticket("07-10", "07-10-ABC123.pdf", root),),
        invalid=(),
    )
    result = match_tickets_to_claims([_claim("2026-07-10")], scan)
    assert set(result.mapping) == {"2026-07-10"}
    assert isinstance(result.mapping["2026-07-10"], Path)


@pytest.mark.offline
def test_zero_claims_is_ok(tmp_path):
    result = match_tickets_to_claims([], ScanResult(valid=(), invalid=()))
    assert result.ok is True
    assert result.mapping == {}


@pytest.mark.offline
def test_invalid_files_surfaced_in_errors(tmp_path):
    bad = tmp_path / "ticket.pdf"
    scan = ScanResult(
        valid=(),
        invalid=((bad, f"misnamed ticket file {bad.name!r}; expected format hint"),),
    )
    result = match_tickets_to_claims([_claim("2026-07-10")], scan)
    assert result.ok is False
    assert any("ticket.pdf" in e for e in result.errors)
    assert result.invalid_files == scan.invalid


@pytest.mark.offline
def test_gate_blocks_filing_when_not_ok():
    from trainline.adapters.ticket_gate import MatchResult, gate_blocks_filing

    assert gate_blocks_filing(MatchResult(ok=False, missing_dates=("2026-07-09",)))
    assert not gate_blocks_filing(MatchResult(ok=True))
