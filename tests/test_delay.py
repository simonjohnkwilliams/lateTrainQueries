"""Story 1.3: delay, band, and payout (FR6, FR7, AD-4, AD-11).

Offline unit tests — no network or credentials (NFR2). ``calculate_delay``
operates on origin-day-relative integer minutes; the HHMM parsing/+1440 roll is
``hsp_client``'s job (Story 2.3), so the cross-midnight case here builds ints.
"""
import pytest

from trainline.engine.delay import band, calculate_delay, payout
from trainline.engine.models import Band


# --- calculate_delay (FR6) --------------------------------------------------
@pytest.mark.offline
def test_on_time_is_zero():
    assert calculate_delay(510, 510) == 0


@pytest.mark.offline
def test_early_clamps_to_zero():
    assert calculate_delay(505, 510) == 0


@pytest.mark.offline
def test_late_is_positive_difference():
    assert calculate_delay(533, 510) == 23


@pytest.mark.offline
def test_cross_midnight_uses_origin_day_relative_minutes():
    # 23:50 -> 00:15 next day. Origin-day-relative: scheduled arrival 00:15 =
    # 15 + 1440 = 1455; actual 00:20 = 20 + 1440 = 1460 -> 5 min late.
    scheduled_arrival = 15 + 1440
    actual_arrival = 20 + 1440
    assert calculate_delay(actual_arrival, scheduled_arrival) == 5
    # A naive HHMM subtraction (15 - 2350) would give -2335; this must not happen.
    assert calculate_delay(actual_arrival, scheduled_arrival) > 0


# --- band (FR7) -------------------------------------------------------------
@pytest.mark.offline
@pytest.mark.parametrize(
    "delay_min,expected",
    [
        (0, Band.NONE),
        (14, Band.NONE),
        (15, Band.B15_29),
        (16, Band.B15_29),
        (29, Band.B15_29),
        (30, Band.B30_59),
        (59, Band.B30_59),
        (60, Band.B60_119),
        (119, Band.B60_119),
        (120, Band.B120_PLUS),
        (500, Band.B120_PLUS),
    ],
)
def test_band_boundaries(delay_min, expected):
    assert band(delay_min) == expected


# --- payout (AC2, AC3; AD-11) ----------------------------------------------
@pytest.mark.offline
def test_sixteen_minutes_bands_and_pays_12_5():
    # AC2: a 16-minute-late arrival -> 15-29 band, payout 12.5.
    assert band(16) is Band.B15_29
    assert payout(band(16)) == 12.5


@pytest.mark.offline
def test_sub_15_is_none_and_pays_zero_without_crashing():
    # AC3: sub-15 -> Band.NONE, payout 0, no exception.
    assert band(14) is Band.NONE
    assert payout(Band.NONE) == 0


@pytest.mark.offline
@pytest.mark.parametrize(
    "b,expected",
    [
        (Band.NONE, 0.0),
        (Band.B15_29, 12.5),
        (Band.B30_59, 25.0),
        (Band.B60_119, 50.0),
        (Band.B120_PLUS, 100.0),
    ],
)
def test_payout_table_open_day_return(b, expected):
    assert payout(b) == expected


@pytest.mark.offline
def test_payout_returns_float():
    # Decided 2026-07-14: payout is float (12.5 is not an int).
    assert isinstance(payout(Band.B15_29), float)
