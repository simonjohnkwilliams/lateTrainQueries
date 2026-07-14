"""Tests for JsonArgs.getJson — the function that produces the run config for
both legs (outbound GOD→WAT and inbound WAT→GOD) when called with no extra CLI
args, and otherwise passes-through a user-supplied dict.
"""
from datetime import date, timedelta

import JsonArgs


class TestGetJsonDefaults:
    def test_single_arg_returns_outbound_and_inbound_legs(self):
        # When sys.argv has only the script name (length 1), getJson returns
        # the default GOD↔WAT config dictionary.
        cfg = JsonArgs.getJson(["TestFileGenerator.py"])
        assert set(cfg.keys()) == {JsonArgs.OUTBOUND_JOURNEY, JsonArgs.INBOUND_JOURNEY}

    def test_outbound_is_god_to_wat_morning(self):
        cfg = JsonArgs.getJson(["script"])
        outbound = cfg[JsonArgs.OUTBOUND_JOURNEY]
        assert outbound[JsonArgs.DEPARTURE_STATION] == "GOD"
        assert outbound[JsonArgs.TO_LOCATION_STRING] == "WAT"
        assert outbound[JsonArgs.START_TIME] == "0400"
        assert outbound[JsonArgs.END_TIME] == "1300"
        assert outbound[JsonArgs.RESULT_FILE_STRING] == JsonArgs.RESULT_FILE_OUTBOUND

    def test_inbound_is_wat_to_god_afternoon(self):
        cfg = JsonArgs.getJson(["script"])
        inbound = cfg[JsonArgs.INBOUND_JOURNEY]
        assert inbound[JsonArgs.DEPARTURE_STATION] == "WAT"
        assert inbound[JsonArgs.TO_LOCATION_STRING] == "GOD"
        assert inbound[JsonArgs.START_TIME] == "1200"
        assert inbound[JsonArgs.END_TIME] == "2359"
        assert inbound[JsonArgs.RESULT_FILE_STRING] == JsonArgs.RESULT_FILE_INBOUND

    def test_default_start_date_is_two_days_ago(self):
        cfg = JsonArgs.getJson(["script"])
        expected = date.today() - timedelta(days=2)
        assert cfg[JsonArgs.OUTBOUND_JOURNEY][JsonArgs.START_DATE_STRING] == expected
        assert cfg[JsonArgs.INBOUND_JOURNEY][JsonArgs.START_DATE_STRING] == expected

    def test_default_days_back_window(self):
        cfg = JsonArgs.getJson(["script"])
        assert cfg[JsonArgs.OUTBOUND_JOURNEY][JsonArgs.DAYS_BACK_STRING] == JsonArgs.DAYS_BACK
        assert JsonArgs.DAYS_BACK == 9  # locked: one week + buffer

    def test_clear_old_data_flag_defaults_true(self):
        cfg = JsonArgs.getJson(["script"])
        assert cfg[JsonArgs.OUTBOUND_JOURNEY][JsonArgs.CLEAR_OLD_DATA_STRING] is True
        assert cfg[JsonArgs.INBOUND_JOURNEY][JsonArgs.CLEAR_OLD_DATA_STRING] is True


class TestGetJsonOverrides:
    def test_custom_dict_is_returned_with_date_defaulted_when_none(self):
        supplied = {
            JsonArgs.START_DATE_STRING: None,
            JsonArgs.DAYS_BACK_STRING: None,
            JsonArgs.DEPARTURE_STATION: "GOD",
        }
        result = JsonArgs.getJson(supplied)
        assert result[JsonArgs.START_DATE_STRING] == date.today()
        assert result[JsonArgs.DAYS_BACK_STRING] == JsonArgs.DAYS_BACK

    def test_custom_dict_preserves_supplied_values(self):
        supplied = {
            JsonArgs.START_DATE_STRING: date(2020, 6, 1),
            JsonArgs.DAYS_BACK_STRING: 3,
            JsonArgs.DEPARTURE_STATION: "WAT",
        }
        result = JsonArgs.getJson(supplied)
        assert result[JsonArgs.START_DATE_STRING] == date(2020, 6, 1)
        assert result[JsonArgs.DAYS_BACK_STRING] == 3
        assert result[JsonArgs.DEPARTURE_STATION] == "WAT"
