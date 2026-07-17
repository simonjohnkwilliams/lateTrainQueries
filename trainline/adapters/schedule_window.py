"""Friday-anchored prior Mon–Fri working week (Epic 7 / FR33, NFR13)."""
from __future__ import annotations

from datetime import date, timedelta


def anchor_friday(as_of: date) -> date:
    """Most recent Friday on or before ``as_of`` (weekday Mon=0 … Fri=4)."""
    delta = (as_of.weekday() - 4) % 7
    return as_of - timedelta(days=delta)


def prior_working_week(as_of: date) -> tuple[date, date]:
    """Return ``(monday, friday)`` for the week *before* the anchor Friday's week.

    Example: as_of Fri 17 Jul 2026 (or Sat/Mon catch-up) → Mon 6 Jul – Fri 10 Jul.
    """
    friday = anchor_friday(as_of)
    this_monday = friday - timedelta(days=4)
    prev_monday = this_monday - timedelta(days=7)
    prev_friday = prev_monday + timedelta(days=4)
    return prev_monday, prev_friday
