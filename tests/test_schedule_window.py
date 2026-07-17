"""Prior Mon–Fri week relative to anchor Friday (Epic 7 / FR33)."""
from __future__ import annotations

from datetime import date

import pytest

from trainline.adapters.schedule_window import (
    anchor_friday,
    prior_working_week,
)


@pytest.mark.offline
@pytest.mark.parametrize(
    "as_of, start, end",
    [
        (date(2026, 7, 17), date(2026, 7, 6), date(2026, 7, 10)),  # Friday
        (date(2026, 7, 18), date(2026, 7, 6), date(2026, 7, 10)),  # Sat catch-up
        (date(2026, 7, 20), date(2026, 7, 6), date(2026, 7, 10)),  # Mon catch-up
        (date(2026, 7, 24), date(2026, 7, 13), date(2026, 7, 17)),  # next Friday
    ],
)
def test_prior_working_week_examples(as_of, start, end):
    assert prior_working_week(as_of) == (start, end)


@pytest.mark.offline
def test_anchor_friday_is_most_recent_friday_on_or_before():
    assert anchor_friday(date(2026, 7, 17)) == date(2026, 7, 17)
    assert anchor_friday(date(2026, 7, 20)) == date(2026, 7, 17)
    assert anchor_friday(date(2026, 7, 16)) == date(2026, 7, 10)  # Thursday → prior Fri
