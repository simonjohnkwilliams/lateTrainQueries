"""Delay arithmetic, banding, and payout — sole owner of delay math (AD-4, AD-11).

``calculate_delay`` is the only place times are subtracted (AD-4). Inputs are
already-normalised origin-day-relative integer minutes; the HSP ``HHMM``-string
→ minutes conversion (including the post-midnight +1440 roll) is done in
``adapters.hsp_client`` (Story 2.3) — no string parsing happens here.

``payout(band) -> float`` on the open-day-return track (decided 2026-07-14):
NONE→0.0, 15-29→12.5, 30-59→25.0, 60-119→50.0, 120+→100.0. Imports nothing I/O (AD-1).
"""
from __future__ import annotations

from trainline.engine.models import Band

# Lower inclusive bound (minutes late at destination) → band. Ordered high→low.
_BAND_THRESHOLDS = (
    (120, Band.B120_PLUS),
    (60, Band.B60_119),
    (30, Band.B30_59),
    (15, Band.B15_29),
)

# Open-day-return payout track (percentage of fare), per PRD addendum.
_PAYOUT = {
    Band.NONE: 0.0,
    Band.B15_29: 12.5,
    Band.B30_59: 25.0,
    Band.B60_119: 50.0,
    Band.B120_PLUS: 100.0,
}


def calculate_delay(actual: int, scheduled: int) -> int:
    """Minutes late at a calling point; early/on-time clamps to 0 (FR6).

    Both arguments are origin-day-relative integer minutes (AD-4), so a
    cross-midnight leg (e.g. scheduled 00:15 == 1455, i.e. 15 + 1440) subtracts
    correctly rather than yielding -1435 / +1445.
    """
    return max(0, actual - scheduled)


def band(delay_min: int) -> Band:
    """Classify a destination-arrival delay into an SWR band (FR7).

    Sub-15-min → ``Band.NONE`` (not claimable).
    """
    for threshold, banding in _BAND_THRESHOLDS:
        if delay_min >= threshold:
            return banding
    return Band.NONE


def payout(band: Band) -> float:
    """Numeric payout percentage for a band on the open-day-return track (AD-11).

    ``payout(Band.NONE) == 0`` (no crash on a sub-threshold service). The
    optimiser maximises the sum of these values, not ordinal band labels (FR9).
    """
    return _PAYOUT[band]
