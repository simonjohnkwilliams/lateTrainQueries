"""Epic 5b: OCR intake helpers + FakeOcr classify pipeline (offline)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from trainline.adapters.ticket_intake import (
    FakeOcrEngine,
    OcrResult,
    classify_unclassified,
    is_god_wat_route,
    is_readable,
    parse_journey_date,
    ready_filename,
    reject_filename,
    ticket_id_from_text_or_hash,
    tickets_layout,
)
from trainline.adapters.ticket_gate import (
    claimed_mm_dds,
    filter_claims_not_already_claimed,
    move_to_claimed,
)
from trainline.engine.models import Band, Claim, Direction


@pytest.mark.offline
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Godalming to London Waterloo", True),
        ("WATERLOO GODALMING", True),
        ("GOD WAT season", True),
        ("Godalming London Terminals 16/07/2024", True),
        ("GODALMING LONDON ZONES 1-6", True),
        ("Godalming LONDON CONES 1-6", True),  # OCR misread of ZONES
        ("dalming london zones 1-6", True),  # OCR dropped Go-
        ("Godalming london 20nes 1-6", True),  # Z→2 OCR slip
        ("Guildford to Burgess Hill", False),
        ("", False),
        ("Godalming only", False),
        ("London Zones 1-6 only", False),
        ("dalming only", False),
    ],
)
def test_is_god_wat_route(text, expected):
    assert is_god_wat_route(text) is expected


@pytest.mark.offline
def test_is_god_wat_route_reversed_ocr():
    # Upside-down OCR often yields reversed character order
    fwd = "godalming london zones 1-6"
    assert is_god_wat_route(fwd[::-1]) is True


@pytest.mark.offline
def test_strip_reject_prefix():
    from trainline.adapters.ticket_intake import strip_reject_prefix
    assert strip_reject_prefix(
        "Not_valid_Route-20260716-140607-20170324_090543.jpg"
    ) == "20170324_090543.jpg"
    assert strip_reject_prefix(
        "unreadable-20260716-140607-shot.jpg"
    ) == "shot.jpg"
    assert strip_reject_prefix("plain.jpg") == "plain.jpg"


@pytest.mark.offline
def test_diagnose_unreadable_empty_text(tmp_path):
    from trainline.adapters.ticket_intake import diagnose_unreadable
    from PIL import Image

    path = tmp_path / "dark.jpg"
    Image.new("RGB", (100, 100), (10, 10, 10)).save(path)
    detail = diagnose_unreadable(path, OcrResult("", 0.0))
    assert "resolution low" in detail
    assert "too dark" in detail or "OCR extracted no usable text" in detail
    assert "OCR extracted no usable text" in detail


@pytest.mark.offline
def test_classify_appends_unreadable_report(tmp_path):
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    (layout.unclassified / "blank.jpg").write_bytes(b"BLANK")
    ocr = FakeOcrEngine({"blank.jpg": OcrResult("", 0.0)})
    summary = classify_unclassified(layout, ocr, now=datetime(2026, 7, 16, 12, 0, 0))
    assert summary.rejected == 1
    report = layout.rejected / "unreadable_report.txt"
    assert report.exists()
    body = report.read_text(encoding="utf-8")
    assert "blank.jpg" in body or "unreadable-" in body
    assert summary.items[0].detail  # richer than empty


@pytest.mark.offline
def test_parse_journey_date_variants():
    assert parse_journey_date("Valid 16/07/2024 for travel").date().isoformat() == "2024-07-16"
    assert parse_journey_date("16 Jul 2024 Godalming").date().isoformat() == "2024-07-16"
    assert parse_journey_date("Date 2024-07-16").date().isoformat() == "2024-07-16"
    assert parse_journey_date("start date 02-sep-19 £128").date().isoformat() == "2019-09-02"
    assert parse_journey_date("19-nov-18 £116.30").date().isoformat() == "2018-11-19"
    assert parse_journey_date("yalid until 16-may=-19").date().isoformat() == "2019-05-16"
    assert parse_journey_date("18-jly-19 £39").date().isoformat() == "2019-07-18"
    # APTIS anti-fraud month codes printed on UK rail tickets
    assert parse_journey_date("07-JNR-25").date().isoformat() == "2025-01-07"
    assert parse_journey_date("06-JNR-25").date().isoformat() == "2025-01-06"
    assert parse_journey_date("02-FBY-20").date().isoformat() == "2020-02-02"
    assert parse_journey_date("27-JNR-20").date().isoformat() == "2020-01-27"
    assert parse_journey_date("26-MCH-24").date().isoformat() == "2024-03-26"
    assert parse_journey_date("15-DMR-19").date().isoformat() == "2019-12-15"
    assert parse_journey_date("no date here") is None


@pytest.mark.offline
def test_parse_ticket_dates_prefers_labels():
    from trainline.adapters.ticket_intake import parse_ticket_dates
    day = parse_ticket_dates(
        "Godalming to London Terminals Date of travel 07-JNR-25 Adult")
    assert day.date_of_travel is not None
    assert day.date_of_travel.date().isoformat() == "2025-01-07"
    assert day.primary.date().isoformat() == "2025-01-07"

    weekly = parse_ticket_dates(
        "TRVLCD-00M07D Start date 27-JNR-20 Valid until 02-FBY-20 "
        "GODALMING * & LONDON ZONES 1-6")
    assert weekly.start_date.date().isoformat() == "2020-01-27"
    assert weekly.valid_until.date().isoformat() == "2020-02-02"
    # Travelcard primary is start date (not valid-until)
    assert weekly.primary.date().isoformat() == "2020-01-27"

    iso_weekly = parse_ticket_dates(
        "Travelcard Start date 2019-09-23 Valid until 29 SEP 19 GODALMING")
    assert iso_weekly.start_date.date().isoformat() == "2019-09-23"
    assert iso_weekly.valid_until.date().isoformat() == "2019-09-29"
    assert iso_weekly.primary.date().isoformat() == "2019-09-23"


@pytest.mark.offline
def test_parse_journey_date_from_filename():
    from trainline.adapters.ticket_intake import parse_journey_date_from_filename
    # Camera / phone capture stamps must NEVER become journey dates
    assert parse_journey_date_from_filename("20250131_125945.jpg") is None
    assert parse_journey_date_from_filename("20191108_105052.jpg") is None
    assert parse_journey_date_from_filename("Office Lens 20170116-085304.jpg") is None
    assert parse_journey_date_from_filename(
        "2019_11_21 15_49 Office Lens.jpg") is None
    # Human descriptive names are OK
    assert parse_journey_date_from_filename("18thjuly2019.jpg").date().isoformat() == "2019-07-18"
    assert parse_journey_date_from_filename("11thapril.jpg") is None  # no year in name
    assert parse_journey_date_from_filename("train06112019.jpg").date().isoformat() == "2019-11-06"
    assert parse_journey_date_from_filename("shot.jpg") is None


@pytest.mark.offline
def test_resolve_ignores_phone_stamp_when_ocr_has_aptis_date():
    from trainline.adapters.ticket_intake import resolve_journey_date
    # The bug that produced 01-31-Terminals.jpg from a 07-JNR-25 ticket
    d = resolve_journey_date(
        "boda ming to london terminals date of travel 07-JNR-25",
        "20250131_125945.jpg",
    )
    assert d is not None and d.date().isoformat() == "2025-01-07"
    # Phone stamp alone must not invent a journey date
    assert resolve_journey_date("galaxy a54 5g junk", "20250131_125945.jpg") is None


@pytest.mark.offline
def test_resolve_journey_date_filename_day_month_plus_ocr_year():
    from trainline.adapters.ticket_intake import resolve_journey_date
    d = resolve_journey_date("ticket valid year 2019 zones", "21stmay.jpg")
    assert d is not None and d.date().isoformat() == "2019-05-21"
    d2 = resolve_journey_date("yalid until =19 zones", "june3rd.jpg")
    assert d2 is not None and d2.month == 6 and d2.day == 3 and d2.year == 2019


@pytest.mark.offline
def test_date_case_fixtures_ground_truth_offline():
    """Key APTIS cases still covered via golden expected set."""
    import json

    from trainline.adapters.ticket_intake import (
        is_god_wat_route,
        parse_ticket_dates,
        resolve_journey_date,
    )

    golden = Path(__file__).parent / "fixtures/tickets/golden/expected.json"
    data = json.loads(golden.read_text(encoding="utf-8"))
    keys = [
        "day_return_2025-01-07_god_terminals.jpg",
        "day_return_2025-01-06_god_terminals.jpg",
        "weekly_2020-01-27_to_2020-02-02_god_zones.jpg",
        "day_return_2024-03-26_god_terminals.jpg",
    ]
    for name in keys:
        rec = data["accept"][name]
        text = rec["transcript"]
        assert is_god_wat_route(text)
        got = resolve_journey_date(text, name)
        assert got is not None
        assert got.date().isoformat() == rec["journey_date"], name
        if rec.get("kind") == "travelcard_7day":
            td = parse_ticket_dates(text)
            assert td.start_date.date().isoformat() == rec["start_date"]
            assert td.valid_until.date().isoformat() == rec["valid_until"]


@pytest.mark.offline
def test_ready_and_reject_filenames():
    when = datetime(2026, 7, 16, 12, 30, 45)
    assert ready_filename(when, "ABC123", ".JPG") == "07-16-ABC123.jpg"
    assert reject_filename("unreadable", Path("shot.jpg"), when).startswith(
        "unreadable-20260716-123045-shot.jpg")
    assert reject_filename("Not_valid_Route", Path("x.png"), when).startswith(
        "Not_valid_Route-20260716-123045-")


@pytest.mark.offline
def test_is_clearly_wrong_route():
    from trainline.adapters.ticket_intake import is_clearly_wrong_route
    assert is_clearly_wrong_route("Guildford to Burgess Hill") is True
    assert is_clearly_wrong_route("Godalming London Zones 1-6") is False
    # Only one end visible — readability gap, not a proven wrong route
    assert is_clearly_wrong_route("london zones 1-6 travelcard") is False
    assert is_clearly_wrong_route("godalming anytime day") is False


@pytest.mark.offline
def test_classify_ambiguous_route_is_unreadable(tmp_path):
    """Missing journey ends → unreadable, not Not_valid_Route."""
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    (layout.unclassified / "partial.jpg").write_bytes(b"PARTIAL")
    ocr = FakeOcrEngine({
        "partial.jpg": OcrResult(
            "london zones 1-6 travelcard 16/07/2024", 70.0),
    })
    summary = classify_unclassified(
        layout, ocr, now=datetime(2026, 7, 16, 10, 0, 0))
    assert summary.ready == 0
    assert summary.items[0].outcome == "rejected_unreadable"
    assert "journey ends" in summary.items[0].detail
    assert not any(
        p.name.startswith("Not_valid_Route-")
        for p in layout.rejected.iterdir() if p.is_file()
    )


@pytest.mark.offline
def test_classify_ready_reject_unreadable_route(tmp_path):
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    (layout.unclassified / "good.jpg").write_bytes(b"GOOD")
    (layout.unclassified / "badroute.jpg").write_bytes(b"BAD")
    (layout.unclassified / "blank.jpg").write_bytes(b"BLANK")

    ocr = FakeOcrEngine({
        "good.jpg": OcrResult(
            "Godalming London Waterloo 16/07/2024 Ticket AB12CD", 80.0),
        "badroute.jpg": OcrResult(
            "Guildford Burgess Hill 16/07/2024", 80.0),
        "blank.jpg": OcrResult("", 0.0),
    })
    when = datetime(2026, 7, 16, 10, 0, 0)
    summary = classify_unclassified(layout, ocr, now=when)
    assert summary.ready == 1
    assert summary.rejected == 2
    assert list(layout.unclassified.iterdir()) == []
    ready = list(layout.ready_to_claim.iterdir())
    assert len(ready) == 1
    assert ready[0].name.startswith("07-16-")
    rejected = {p.name for p in layout.rejected.iterdir() if p.is_file()}
    assert any(n.startswith("Not_valid_Route-") for n in rejected)
    assert any(n.startswith("unreadable-") for n in rejected)
    assert (layout.rejected / "unreadable_report.txt").exists()


@pytest.mark.offline
def test_claimed_dedup_and_move(tmp_path):
    claimed = tmp_path / "claimed"
    claimed.mkdir()
    (claimed / "07-10-OLD.pdf").write_bytes(b"x")
    assert claimed_mm_dds(claimed) == {"07-10"}

    claims = [
        Claim(
            date="2026-07-10", direction=Direction.OUTBOUND,
            origin="GOD", destination="WAT",
            scheduled_departure=0, scheduled_arrival=0, actual_arrival=0,
            delay=20, band=Band.B15_29,
        ),
        Claim(
            date="2026-07-11", direction=Direction.OUTBOUND,
            origin="GOD", destination="WAT",
            scheduled_departure=0, scheduled_arrival=0, actual_arrival=0,
            delay=20, band=Band.B15_29,
        ),
    ]
    remaining = filter_claims_not_already_claimed(claims, claimed)
    assert [c.date for c in remaining] == ["2026-07-11"]

    ready = tmp_path / "07-11-NEW.pdf"
    ready.write_bytes(b"y")
    dest = move_to_claimed(ready, claimed)
    assert dest.parent == claimed
    assert not ready.exists()
    assert dest.exists()


@pytest.mark.offline
def test_ticket_id_hash_fallback(tmp_path):
    path = tmp_path / "f.jpg"
    path.write_bytes(b"abc")
    tid = ticket_id_from_text_or_hash("journey only 2024", path)
    assert len(tid) == 8
    assert tid.isalnum()
