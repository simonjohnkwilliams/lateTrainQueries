"""SWR form field mapping at submit time (Story 6.1, FR27, OQ3).

Pure helpers — no browser imports. May import ``engine.models`` only (AD-2).
"""
from __future__ import annotations

from dataclasses import dataclass

from trainline.engine.models import Claim

# Extensible CRS → SWR station display names (FR27).
DEFAULT_CRS_NAMES: dict[str, str] = {
    "WAT": "London Waterloo",
    "GOD": "Godalming",
}

SWR_REASON_CANCELLED = "Train cancelled"
SWR_REASON_DELAYED = "Delayed en route"


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


def map_claim_for_swr(
    claim: Claim,
    *,
    crs_names: dict[str, str] | None = None,
) -> SwrFormFields:
    """Pure ``Claim`` → SWR form fields (FR27)."""
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
    )
