"""Storage adapter — Claim -> CSV + JSON, sorted (FR13, FR14, FR15).

The only place a ``Claim`` is serialised (AD-3). Writes both a human-checkable
CSV (one row per claim) and a structured JSON file. Internal times are integer
origin-day-relative minutes (AD-4); storage formats them back to ``HH:MM`` for
output. MVP surfaces the band, not a £ figure (AD-11).

May import ``engine.models`` only (AD-2) — it does not import ``engine.delay``,
so it renders the band as a delay-range label rather than re-deriving a payout.
"""
from __future__ import annotations

import csv
import json

from trainline.engine.models import Band, Claim, Direction

CSV_FIELDS = [
    "date",
    "direction",
    "origin",
    "destination",
    "scheduled_departure",
    "scheduled_arrival",
    "actual_arrival",
    "delay_min",
    "band",
    "reason",
]

# Human-readable band label (the SWR delay range). Presentation only — no payout.
_BAND_LABEL = {
    Band.NONE: "none",
    Band.B15_29: "15-29",
    Band.B30_59: "30-59",
    Band.B60_119: "60-119",
    Band.B120_PLUS: "120+",
}

_DIRECTION_ORDER = {Direction.OUTBOUND: 0, Direction.INBOUND: 1}


def _hhmm(minutes: int | None) -> str:
    """Origin-day-relative minutes -> ``HH:MM`` (wrapping past midnight).

    ``None`` (cancelled/unarrived) renders as an empty string — defensive; claim
    rows normally carry concrete actuals after engine filtering.
    """
    if minutes is None:
        return ""
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def claim_to_row(claim: Claim) -> dict:
    """A single claim as an ordered dict of SWR-form fields (FR13)."""
    return {
        "date": claim.date,
        "direction": claim.direction.value,
        "origin": claim.origin,
        "destination": claim.destination,
        "scheduled_departure": _hhmm(claim.scheduled_departure),
        "scheduled_arrival": _hhmm(claim.scheduled_arrival),
        "actual_arrival": _hhmm(claim.actual_arrival),
        "delay_min": claim.delay,
        "band": _BAND_LABEL[claim.band],
        "reason": claim.reason or "",
    }


def sort_claims(claims) -> list[Claim]:
    """Sort by date, then direction (outbound before inbound), then departure (FR15)."""
    return sorted(
        claims,
        key=lambda c: (c.date, _DIRECTION_ORDER[c.direction], c.scheduled_departure),
    )


def write_claims(claims, csv_path, json_path) -> list[Claim]:
    """Write claims to both CSV and JSON, sorted for a week-at-a-glance read.

    Returns the ordered claims. Surfaces the band (not £) per FR14/AD-11.
    """
    ordered = sort_claims(claims)
    rows = [claim_to_row(c) for c in ordered]

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    return ordered
