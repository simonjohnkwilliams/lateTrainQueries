"""Unit tests for SWR booking confirmation PDF text parse (offline)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trainline.booking_pdf import (
    booking_leg_transcript,
    is_swr_booking_confirmation_text,
    parse_swr_booking_pdf,
    parse_swr_booking_text,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tickets" / "booking"
FIXTURE_PDF = FIXTURE_DIR / "B-SWR-TDV0MXMTS.pdf"
FIXTURE_TXT = FIXTURE_DIR / "B-SWR-TDV0MXMTS.txt"

SAMPLE_TEXT = """\
SRBYE8PNEF3
24 Jul 2026 Out: GOD - LON
GODALMING LONDON TERMINALS
Anytime Day Return ANY PERMITTED
Ticket Number SRBYE8PNEF3
Price £38.80
Purchased on 24 July 2026
NRS Booking Reference KY469162
Booking Reference
B-SWR-TDV0MXMTS

SRBYE8PNEF3
24 Jul 2026 Ret: LON - GOD
LONDON TERMINALS GODALMING
Ticket Number SRBYE8PNEF3
Price £38.80
Booking Reference
B-SWR-TDV0MXMTS
"""


@pytest.mark.offline
def test_parse_booking_text_extracts_price_ref_and_both_legs():
    conf = parse_swr_booking_text(SAMPLE_TEXT)
    assert conf is not None
    assert conf.ticket_number == "SRBYE8PNEF3"
    assert conf.price == "38.80"
    assert conf.booking_reference == "B-SWR-TDV0MXMTS"
    assert conf.nrs_reference == "KY469162"
    assert len(conf.legs) == 2
    assert conf.legs[0].portion == "outward"
    assert conf.legs[0].origin == "GOD"
    assert conf.legs[0].destination == "LON"
    assert conf.legs[0].travel_date == date(2026, 7, 24)
    assert conf.legs[1].portion == "return"
    assert conf.legs[1].origin == "LON"
    assert conf.legs[1].destination == "GOD"


@pytest.mark.offline
def test_parse_booking_text_handles_replacement_pound():
    text = SAMPLE_TEXT.replace("£", "\ufffd")
    conf = parse_swr_booking_text(text)
    assert conf is not None
    assert conf.price == "38.80"


@pytest.mark.offline
def test_non_booking_text_returns_none():
    assert parse_swr_booking_text("random PDF without booking fields") is None
    assert not is_swr_booking_confirmation_text("TICKET photo only")


@pytest.mark.offline
def test_leg_transcript_feeds_existing_price_parser():
    from trainline.adapters.ticket_intake import (
        is_god_wat_route,
        parse_ticket_price,
        parse_ticket_reference,
        resolve_journey_date,
    )

    conf = parse_swr_booking_text(SAMPLE_TEXT)
    assert conf is not None
    transcript = booking_leg_transcript(conf, conf.legs[0])
    assert parse_ticket_price(transcript) == "38.80"
    assert parse_ticket_reference(transcript) == "SRBYE8PNEF3"
    assert is_god_wat_route(transcript)
    journey = resolve_journey_date(transcript, "booking.pdf")
    assert journey is not None
    assert journey.date() == date(2026, 7, 24)


@pytest.mark.offline
def test_parse_real_fixture_pdf_when_present():
    if not FIXTURE_PDF.is_file():
        pytest.skip("booking PDF fixture not present")
    conf = parse_swr_booking_pdf(FIXTURE_PDF)
    assert conf is not None
    assert conf.ticket_number == "SRBYE8PNEF3"
    assert conf.price == "38.80"
    assert len(conf.legs) == 2


@pytest.mark.offline
def test_fixture_txt_matches_parser_when_present():
    if not FIXTURE_TXT.is_file():
        pytest.skip("booking txt fixture not present")
    conf = parse_swr_booking_text(FIXTURE_TXT.read_text(encoding="utf-8"))
    assert conf is not None
    assert conf.price == "38.80"
