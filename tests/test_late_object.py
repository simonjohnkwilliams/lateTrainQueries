"""Behaviour-regression tests for LateObject.calculate_delay.

This is the core "is it late" math: it takes two HHMM strings (actual and
scheduled arrival) and returns a non-negative integer of minutes late.
"""
import pytest

from LateObject import LateObject


class TestCalculateDelay:
    def test_on_time_returns_zero(self):
        assert LateObject.calculate_delay("0830", "0830") == 0

    def test_one_minute_late(self):
        assert LateObject.calculate_delay("0831", "0830") == 1

    def test_typical_commuter_delay(self):
        # 0853 actual vs 0830 scheduled = 23 minutes late
        assert LateObject.calculate_delay("0853", "0830") == 23

    def test_large_delay_over_an_hour(self):
        # 1012 actual vs 0915 scheduled = 57 minutes late
        assert LateObject.calculate_delay("1012", "0915") == 57

    def test_early_train_clamped_to_zero(self):
        # Arrived 5 minutes early — not "late", so result is 0 not -5
        assert LateObject.calculate_delay("0825", "0830") == 0

    def test_significantly_early_train_still_zero(self):
        assert LateObject.calculate_delay("0700", "0830") == 0

    def test_return_type_is_int_when_late(self):
        result = LateObject.calculate_delay("0831", "0830")
        assert isinstance(result, int)

    def test_seconds_are_ignored_input_is_hhmm(self):
        # The function slices [:2] for hours, [2:4] for minutes,
        # so trailing characters beyond position 4 are ignored.
        assert LateObject.calculate_delay("083100", "0830") == 1

    @pytest.mark.parametrize(
        "actual,scheduled,expected",
        [
            ("0830", "0830", 0),
            ("0831", "0830", 1),
            ("0900", "0830", 30),
            ("1000", "0830", 90),
            ("0829", "0830", 0),
        ],
    )
    def test_parametrised_cases(self, actual, scheduled, expected):
        assert LateObject.calculate_delay(actual, scheduled) == expected
