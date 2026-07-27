"""SWR booking-confirmation PDF text extraction (no vision).

Digital wallet screenshots often omit fare. The emailed ``SWR Booking
Confirmation`` PDF has a text layer with ticket number, price, and Out/Ret
legs — parse that instead of asking Ollama to OCR a raster.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class BookingLeg:
    portion: str  # outward | return
    origin: str
    destination: str
    travel_date: date


@dataclass(frozen=True)
class SwrBookingConfirmation:
    ticket_number: str
    price: str  # digits.decimal, e.g. "38.80"
    booking_reference: str
    legs: tuple[BookingLeg, ...]
    nrs_reference: str | None = None


_PRICE_RE = re.compile(
    r"Price\s*[:\s]*[£\u00a3\ufffd]?\s*(\d+[.,]\d{2})",
    re.IGNORECASE,
)
_TICKET_NUMBER_RE = re.compile(
    r"Ticket\s+Number\s+([A-Za-z0-9-]{5,})",
    re.IGNORECASE,
)
_BOOKING_REF_RE = re.compile(
    r"Booking\s+Reference\s+(B-SWR-[A-Z0-9]+)",
    re.IGNORECASE,
)
_NRS_RE = re.compile(
    r"NRS\s+Booking\s+Reference\s+([A-Z0-9]+)",
    re.IGNORECASE,
)
_LEG_HEADER_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+(?P<year>\d{4})\s+"
    r"(?P<kind>Out|Ret)\s*:\s*(?P<from>[A-Z]{3})\s*-\s*(?P<to>[A-Z]{3})",
    re.IGNORECASE,
)
_MONTH = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def extract_pdf_text(path: Path) -> str:
    """Pull text layer from a PDF (pdfplumber). Empty if unreadable."""
    path = Path(path)
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "pdfplumber is required to read booking confirmation PDFs"
        ) from exc
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def is_swr_booking_confirmation_text(text: str) -> bool:
    t = text or ""
    if not _BOOKING_REF_RE.search(t) and "B-SWR-" not in t.upper():
        return False
    if not _TICKET_NUMBER_RE.search(t):
        return False
    return bool(_LEG_HEADER_RE.search(t) or _PRICE_RE.search(t))


def parse_swr_booking_text(text: str) -> SwrBookingConfirmation | None:
    """Parse extracted PDF text into structured booking fields."""
    if not (text or "").strip():
        return None
    if not is_swr_booking_confirmation_text(text):
        return None

    price_m = _PRICE_RE.search(text)
    ticket_m = _TICKET_NUMBER_RE.search(text)
    booking_m = _BOOKING_REF_RE.search(text)
    if not price_m or not ticket_m or not booking_m:
        return None

    legs: list[BookingLeg] = []
    seen: set[tuple[str, str, str, date]] = set()
    for m in _LEG_HEADER_RE.finditer(text):
        mon = _MONTH[m.group("mon").casefold()[:3]]
        travel = date(int(m.group("year")), mon, int(m.group("day")))
        kind = m.group("kind").casefold()
        portion = "outward" if kind.startswith("out") else "return"
        origin = m.group("from").upper()
        dest = m.group("to").upper()
        key = (portion, origin, dest, travel)
        if key in seen:
            continue
        seen.add(key)
        legs.append(
            BookingLeg(
                portion=portion,
                origin=origin,
                destination=dest,
                travel_date=travel,
            )
        )
    if not legs:
        return None

    nrs_m = _NRS_RE.search(text)
    return SwrBookingConfirmation(
        ticket_number=ticket_m.group(1).strip().upper(),
        price=price_m.group(1).replace(",", "."),
        booking_reference=booking_m.group(1).strip().upper(),
        legs=tuple(legs),
        nrs_reference=(nrs_m.group(1).strip().upper() if nrs_m else None),
    )


def parse_swr_booking_pdf(path: Path) -> SwrBookingConfirmation | None:
    path = Path(path)
    if path.suffix.casefold() != ".pdf":
        return None
    try:
        text = extract_pdf_text(path)
    except Exception:
        return None
    return parse_swr_booking_text(text)


def leg_station_names(leg: BookingLeg) -> tuple[str, str]:
    """Map CRS codes used on SWR PDFs to OCR-friendly station names."""
    names = {
        "GOD": "Godalming",
        "LON": "London Terminals",
        "WAT": "London Waterloo",
        "GLD": "Guildford",
    }
    return names.get(leg.origin, leg.origin), names.get(
        leg.destination, leg.destination
    )


def booking_leg_transcript(conf: SwrBookingConfirmation, leg: BookingLeg) -> str:
    """Synthetic OCR transcript so existing classify/meta parsers work."""
    origin, dest = leg_station_names(leg)
    travel = leg.travel_date.strftime("%d %b %Y")
    portion_label = "Outward" if leg.portion == "outward" else "Return"
    return (
        f"SWR Booking Confirmation eTicket\n"
        f"{portion_label}: {leg.origin} - {leg.destination}\n"
        f"{origin} {dest}\n"
        f"Anytime Day Return\n"
        f"Date of travel {travel}\n"
        f"Ticket Number {conf.ticket_number}\n"
        f"Price £{conf.price}\n"
        f"Booking Reference {conf.booking_reference}\n"
    )


def portion_suffix(portion: str) -> str:
    return "OUT" if portion == "outward" else "RET"


def journey_datetime(leg: BookingLeg) -> datetime:
    return datetime(leg.travel_date.year, leg.travel_date.month, leg.travel_date.day)
