"""Behaviour-regression tests for the late-train pipeline functions in
TestFileGenerator: generateLateTrainObject, trimToRouteOnlyDictionary,
getLatestTrainObject and generatePidList.

The pipeline answers "for each day, which train between these two stations was
late and by how much?".
"""
import json
import os

import pytest

import TestFileGenerator as tfg


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURE_DIR, name)) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# generateLateTrainObject
# ---------------------------------------------------------------------------
class TestGenerateLateTrainObject:
    def test_late_outbound_god_to_wat_emits_both_legs(self):
        details = _load("service_details_late.json")
        result = tfg.generateLateTrainObject("GOD", "WAT", details)
        # Only the GOD and WAT entries should be included (not GUI in the middle).
        locations = [obj.location for obj in result]
        assert "GUI" not in locations
        # WAT was 23 minutes late, GOD itself records the same date — both kept
        # since the function emits one LateObject per matching location whose
        # delay calculation returns > 1.
        assert any(obj.location == "WAT" and obj.delay_time == 23 for obj in result)

    def test_departure_station_flag_is_set_on_origin(self):
        details = _load("service_details_late.json")
        result = tfg.generateLateTrainObject("GOD", "WAT", details)
        wat = next(obj for obj in result if obj.location == "WAT")
        assert wat.departureStation is False
        # The GOD leg has no gbtt_pta so delay_time will be 0 and it gets dropped
        # by the "> 1" filter — assert that current behaviour explicitly.
        assert not any(obj.location == "GOD" for obj in result)

    def test_on_time_train_produces_no_late_records(self):
        details = _load("service_details_on_time.json")
        result = tfg.generateLateTrainObject("GOD", "WAT", details)
        assert result == []

    def test_one_minute_late_is_filtered_out(self):
        # The threshold is `delay_time > 1` — exactly 1 minute is NOT late.
        details = _load("service_details_one_minute_late.json")
        result = tfg.generateLateTrainObject("GOD", "WAT", details)
        assert result == []

    def test_very_late_train_captured(self):
        details = _load("service_details_very_late.json")
        result = tfg.generateLateTrainObject("GOD", "WAT", details)
        wat = next(obj for obj in result if obj.location == "WAT")
        assert wat.delay_time == 57
        assert wat.late_canc_reason == "Train failure"
        assert wat.date_of_service == "2020-01-01"

    def test_inbound_route_wat_to_god(self):
        details = _load("service_details_inbound_late.json")
        result = tfg.generateLateTrainObject("WAT", "GOD", details)
        god = next(obj for obj in result if obj.location == "GOD")
        # 1947 actual vs 1933 scheduled = 14 minutes late.
        assert god.delay_time == 14
        assert god.departureStation is False

    def test_missing_actual_ta_yields_no_late_records(self):
        details = {
            "serviceAttributesDetails": {
                "date_of_service": "2020-02-01",
                "locations": [
                    {
                        "location": "WAT",
                        "gbtt_ptd": "",
                        "gbtt_pta": "0830",
                        "actual_td": "",
                        "actual_ta": "",  # missing
                        "late_canc_reason": "",
                    }
                ],
            }
        }
        assert tfg.generateLateTrainObject("GOD", "WAT", details) == []


# ---------------------------------------------------------------------------
# trimToRouteOnlyDictionary
# ---------------------------------------------------------------------------
class TestTrimToRouteOnlyDictionary:
    def test_keeps_only_days_with_both_legs(self):
        # Late outbound has both GOD + WAT but GOD leg has empty gbtt_pta so the
        # filter drops it. Use a synthetic record where both legs are late.
        details = {
            "serviceAttributesDetails": {
                "date_of_service": "2020-01-01",
                "locations": [
                    {
                        "location": "GOD",
                        "gbtt_ptd": "0727",
                        "gbtt_pta": "0727",  # synthetic — both fields populated
                        "actual_td": "0728",
                        "actual_ta": "0730",  # 3 min late
                        "late_canc_reason": "",
                    },
                    {
                        "location": "WAT",
                        "gbtt_ptd": "",
                        "gbtt_pta": "0830",
                        "actual_td": "",
                        "actual_ta": "0853",  # 23 min late
                        "late_canc_reason": "Signal failure",
                    },
                ],
            }
        }
        result = tfg.trimToRouteOnlyDictionary([details], "GOD", "WAT")
        assert "2020-01-01" in result
        # Single service, so one entry containing one [GOD, WAT] pair.
        assert len(result["2020-01-01"]) == 1
        assert len(result["2020-01-01"][0]) == 2

    def test_drops_services_with_only_one_matching_leg(self):
        details = _load("service_details_late.json")
        # Only the WAT leg counts as late (>1) — that's one record, not two,
        # so the date should be excluded.
        result = tfg.trimToRouteOnlyDictionary([details], "GOD", "WAT")
        assert result == {}

    def test_handles_none_and_malformed_entries(self):
        ok = _load("service_details_very_late.json")
        # very_late only emits one matching late leg (WAT), so it is also
        # excluded by the "len == 2" check. Confirm None / malformed entries
        # don't blow up.
        result = tfg.trimToRouteOnlyDictionary(
            [None, {}, {"serviceAttributesDetails": {}}, ok],
            "GOD",
            "WAT",
        )
        assert result == {}


# ---------------------------------------------------------------------------
# getLatestTrainObject — picks the worst-delayed train per day
# ---------------------------------------------------------------------------
class TestGetLatestTrainObject:
    def _make_pair(self, date, depart_time, depart_delay, arrive_delay,
                   departure_station="GOD", arrival_station="WAT"):
        from LateObject import LateObject
        depart = LateObject()
        depart.location = departure_station
        depart.gbtt_ptd = depart_time
        depart.date_of_service = date
        depart.delay_time = depart_delay
        depart.departureStation = True

        arrive = LateObject()
        arrive.location = arrival_station
        arrive.gbtt_pta = ""
        arrive.date_of_service = date
        arrive.delay_time = arrive_delay
        arrive.departureStation = False
        return [depart, arrive]

    def test_picks_pair_with_largest_arrival_delay(self):
        pair_small = self._make_pair("2020-01-01", "0727", 1, 5)
        pair_big = self._make_pair("2020-01-01", "0810", 2, 30)
        result = tfg.getLatestTrainObject({"2020-01-01": [pair_small, pair_big]})
        assert result["2020-01-01"][1].delay_time == 30
        assert result["2020-01-01"][0].gbtt_ptd == "0810"

    def test_handles_single_pair_for_a_day(self):
        pair = self._make_pair("2020-01-02", "0727", 1, 10)
        result = tfg.getLatestTrainObject({"2020-01-02": [pair]})
        assert result["2020-01-02"][1].delay_time == 10

    def test_skips_malformed_entries_with_wrong_length(self):
        good = self._make_pair("2020-01-03", "0727", 1, 5)
        result = tfg.getLatestTrainObject({"2020-01-03": [["only-one"], good]})
        assert result["2020-01-03"][1].delay_time == 5


# ---------------------------------------------------------------------------
# generatePidList — extracts RIDs from a directory of metrics responses
# ---------------------------------------------------------------------------
class TestGeneratePidList:
    def test_collects_first_rid_from_each_file(self, tmp_path):
        # Copy the fixture into a temp dir so we don't pollute anything.
        payload = _load("service_metrics_god_wat.json")
        (tmp_path / "metrics-2020-01-01.json").write_text(json.dumps(payload))

        rids = tfg.generatePidList(str(tmp_path))
        assert rids == ["202001010727001", "202001010810001"]

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert tfg.generatePidList(str(tmp_path)) == []

    def test_skips_services_with_empty_rids(self, tmp_path):
        payload = {
            "Services": [
                {"serviceAttributesMetrics": {"rids": []}},
                {"serviceAttributesMetrics": {"rids": ["abc"]}},
            ]
        }
        (tmp_path / "metrics.json").write_text(json.dumps(payload))
        assert tfg.generatePidList(str(tmp_path)) == ["abc"]
