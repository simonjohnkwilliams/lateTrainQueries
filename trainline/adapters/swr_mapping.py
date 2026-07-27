"""SWR form field mapping at submit time (Story 6.1, FR27, OQ3).

Pure helpers — no browser imports. May import ``engine.models`` only (AD-2).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trainline.engine.models import Claim

# Extensible CRS → SWR station display names (FR27).
DEFAULT_CRS_NAMES: dict[str, str] = {
    "WAT": "London Waterloo",
    "GOD": "Godalming",
}

SWR_REASON_CANCELLED = "Train cancelled"
SWR_REASON_DELAYED = "Delayed en route"

# Live portal delay-duration cards (captured 2026-07-17).
SWR_DELAY_BAND_LABELS = {
    "B15_29": "Between 15 - 29 minutes",
    "B30_59": "Between 30 - 59 minutes",
    "B60_119": "Between 60 - 119 minutes",
    "B120_PLUS": "120 minutes or more",
}


@dataclass(frozen=True)
class SwrFormFields:
    """Values ready to type into the SWR Delay Repay form."""

    journey_date: str  # YYYY-MM-DD
    origin_station: str
    destination_station: str
    scheduled_departure: str  # HH:MM
    scheduled_arrival: str
    actual_arrival: str
    delay_reason: str  # SWR category
    raw_reason_code: str | None  # HSP late_canc_reason for audit only
    delay_min: int
    delay_band_label: str = SWR_DELAY_BAND_LABELS["B15_29"]
    ticket_medium: str = "Paper"  # aria: Select Paper as your ticket type
    ticket_duration: str = "Return"
    ticket_price: str = ""
    ticket_reference: str = ""


def _hhmm(minutes: int) -> str:
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def station_name(crs: str, names: dict[str, str] | None = None) -> str:
    table = names if names is not None else DEFAULT_CRS_NAMES
    key = (crs or "").strip().upper()
    if key in table:
        return table[key]
    return (crs or "").strip()


def delay_reason_category(claim: Claim) -> str:
    """Map claim to SWR delay-reason dropdown value."""
    # Cancellation fallback preserves HSP late_canc_reason on Claim.reason
    if claim.reason:
        return SWR_REASON_CANCELLED
    return SWR_REASON_DELAYED


def delay_band_label(band) -> str:
    """Map ``engine.models.Band`` to the live SWR delay-duration card text."""
    from trainline.engine.models import Band

    if band is Band.B30_59:
        return SWR_DELAY_BAND_LABELS["B30_59"]
    if band is Band.B60_119:
        return SWR_DELAY_BAND_LABELS["B60_119"]
    if band is Band.B120_PLUS:
        return SWR_DELAY_BAND_LABELS["B120_PLUS"]
    return SWR_DELAY_BAND_LABELS["B15_29"]


def leaving_at_search_slot(hhmm: str) -> str:
    """Floor ``HH:MM`` to the prior 15-minute Leaving-at autocomplete slot."""
    hour_s, min_s = hhmm.strip().split(":", 1)
    total = int(hour_s) * 60 + int(min_s)
    slot = (total // 15) * 15 % 1440
    return f"{slot // 60:02d}:{slot % 60:02d}"


def ticket_medium_for_path(ticket_path: Path | str) -> str:
    """SWR ticket-type control: PDFs are e-tickets; photos are paper."""
    suffix = Path(ticket_path).suffix.casefold()
    if suffix == ".pdf":
        return "E-ticket/M-ticket"
    return "Paper"


def map_claim_for_swr(
    claim: Claim,
    *,
    crs_names: dict[str, str] | None = None,
    ticket_price: str = "",
    ticket_reference: str = "",
    ticket_medium: str = "Paper",
    ticket_duration: str = "Return",
) -> SwrFormFields:
    """Pure ``Claim`` → SWR form fields (FR27).

    ``ticket_price`` / ``ticket_reference`` default empty — callers must pass
    real values for live submit (do not invent 12.50 / 12345).
    """
    return SwrFormFields(
        journey_date=claim.date,
        origin_station=station_name(claim.origin, crs_names),
        destination_station=station_name(claim.destination, crs_names),
        scheduled_departure=_hhmm(claim.scheduled_departure),
        scheduled_arrival=_hhmm(claim.scheduled_arrival),
        actual_arrival=_hhmm(claim.actual_arrival),
        delay_reason=delay_reason_category(claim),
        raw_reason_code=claim.reason,
        delay_min=claim.delay,
        delay_band_label=delay_band_label(claim.band),
        ticket_medium=ticket_medium,
        ticket_duration=ticket_duration,
        ticket_price=ticket_price,
        ticket_reference=ticket_reference,
    )
