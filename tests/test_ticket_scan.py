"""Story 5.1: ticket naming contract + directory scanner (FR23, FR24)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.ticket_gate import (
    EXPECTED_FORMAT,
    parse_ticket_filename,
    scan_ticket_dir,
)


@pytest.mark.offline
@pytest.mark.parametrize(
    "name, month, day, ticket",
    [
        ("07-10-ABC123.pdf", "07", "10", "ABC123"),
        ("07-10-ABC123.PDF", "07", "10", "ABC123"),
        ("12-01-ticket_1.jpg", "12", "01", "ticket_1"),
        ("01-31-X.jpeg", "01", "31", "X"),
        ("07-10-A-B.png", "07", "10", "A-B"),
    ],
)
def test_parse_valid_ticket_names(name, month, day, ticket):
    parsed = parse_ticket_filename(name)
    assert parsed is not None
    assert parsed.month == month
    assert parsed.day == day
    assert parsed.ticket_number == ticket
    assert parsed.mm_dd == f"{month}-{day}"


@pytest.mark.offline
@pytest.mark.parametrize(
    "name",
    [
        "ticket.pdf",
        "2026-07-10.pdf",
        "7-10-ABC.pdf",
        "07-10.pdf",
        "07-10-ABC123.txt",
        "07-10-ABC 123.pdf",
    ],
)
def test_parse_rejects_misnamed(name):
    assert parse_ticket_filename(name) is None


@pytest.mark.offline
def test_scan_separates_valid_and_invalid(tmp_path):
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()
    (ticket_dir / "07-10-ABC123.pdf").write_bytes(b"%PDF")
    (ticket_dir / "ticket.pdf").write_bytes(b"%PDF")
    (ticket_dir / "2026-07-10.jpg").write_bytes(b"x")
    (ticket_dir / "readme.txt").write_text("ignore", encoding="utf-8")

    scan = scan_ticket_dir(ticket_dir)
    assert len(scan.valid) == 1
    assert scan.valid[0].ticket_number == "ABC123"
    assert scan.valid[0].path.name == "07-10-ABC123.pdf"
    assert len(scan.invalid) == 3
    for path, reason in scan.invalid:
        assert EXPECTED_FORMAT in reason
        assert path.parent == ticket_dir


@pytest.mark.offline
def test_scan_missing_dir_returns_empty(tmp_path):
    scan = scan_ticket_dir(tmp_path / "nope")
    assert scan.valid == ()
    assert scan.invalid == ()
    assert scan.missing_directory is True


@pytest.mark.offline
def test_scan_ignores_subdirectories(tmp_path):
    ticket_dir = tmp_path / "ticket"
    ticket_dir.mkdir()
    (ticket_dir / "nested").mkdir()
    (ticket_dir / "nested" / "07-10-X.pdf").write_bytes(b"%PDF")
    (ticket_dir / "07-11-Y.pdf").write_bytes(b"%PDF")
    scan = scan_ticket_dir(ticket_dir)
    assert [t.mm_dd for t in scan.valid] == ["07-11"]
