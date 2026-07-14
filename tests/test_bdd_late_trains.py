"""Step definitions for tests/features/late_trains.feature.

The offline scenarios exercise the late-train pipeline (download, parse, write
CSV) with `requests.post` stubbed out, so they replicate the real journey
without needing credentials or network. The live scenario in
live_hsp_api.feature has its steps in test_bdd_live.py.
"""
import json
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

import JsonArgs
import TestFileGenerator as tfg

scenarios("features/late_trains.feature")


# ---------------------------------------------------------------------------
# Test world: a single sandbox folder the pipeline writes into.
# ---------------------------------------------------------------------------
@pytest.fixture
def world(tmp_path, monkeypatch):
    metrics_dir = tmp_path / "metrics"
    details_dir = tmp_path / "details"
    results_dir = tmp_path / "Results"
    metrics_dir.mkdir()
    details_dir.mkdir()
    results_dir.mkdir()

    # writeLateTrainsToFile writes to os.getcwd()/Results/<name>.csv, so cd in.
    monkeypatch.chdir(tmp_path)

    return {
        "metrics_dir": str(metrics_dir),
        "details_dir": str(details_dir),
        "results_dir": str(results_dir),
        "service_details": [],   # responses keyed by rid
        "service_metrics": None,
        "csv_path": str(results_dir / "outboundLateTrains.csv"),
    }


def _service_details(date_str, depart_actual, arrive_scheduled, arrive_actual,
                     depart_station="GOD", arrive_station="WAT",
                     depart_scheduled="0727", rid=None):
    # The real Darwin HSP API populates gbtt_pta/actual_ta at the origin as
    # well (mirroring gbtt_ptd/actual_td), which the pipeline depends on —
    # trimToRouteOnlyDictionary requires *both* the departure and arrival
    # records to clear the > 1 minute lateness threshold.
    return {
        "serviceAttributesDetails": {
            "date_of_service": date_str,
            "rid": rid or f"{date_str.replace('-', '')}{depart_scheduled}001",
            "locations": [
                {
                    "location": depart_station,
                    "gbtt_ptd": depart_scheduled,
                    "gbtt_pta": depart_scheduled,
                    "actual_td": depart_actual,
                    "actual_ta": depart_actual,
                    "late_canc_reason": "",
                },
                {
                    "location": arrive_station,
                    "gbtt_ptd": "",
                    "gbtt_pta": arrive_scheduled,
                    "actual_td": "",
                    "actual_ta": arrive_actual,
                    "late_canc_reason": "",
                },
            ],
        }
    }


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------
@given("the HSP cache and Results directories are empty")
def empty_cache(world):
    assert os.listdir(world["metrics_dir"]) == []
    assert os.listdir(world["details_dir"]) == []
    assert os.listdir(world["results_dir"]) == []


@given(parsers.parse('the Darwin API returns one outbound service on "{day}"'))
def one_service(world, day):
    world["day"] = day
    world["service_metrics"] = {
        "Services": [{"serviceAttributesMetrics": {"rids": [f"rid-{day}"]}}]
    }


@given(parsers.parse(
    "the Darwin API returns two outbound services on \"{day}\""))
def two_services(world, day):
    world["day"] = day
    world["service_metrics"] = {
        "Services": [
            {"serviceAttributesMetrics": {"rids": [f"rid-{day}-a"]}},
            {"serviceAttributesMetrics": {"rids": [f"rid-{day}-b"]}},
        ]
    }


@given("that service has the WAT arrival 23 minutes late")
def arrival_23_late(world):
    # Train leaves GOD 2 min late (so the origin leg also clears the >1 min
    # threshold the pipeline uses) and arrives at WAT 23 min late.
    world["service_details"].append(
        _service_details(world["day"], "0729", "0830", "0853",
                         rid=f"rid-{world['day']}")
    )


@given("that service arrives at WAT exactly on time")
def arrival_on_time(world):
    world["service_details"].append(
        _service_details(world["day"], "0727", "0830", "0830",
                         rid=f"rid-{world['day']}")
    )


@given("that service arrives at WAT 1 minute late")
def arrival_one_late(world):
    world["service_details"].append(
        _service_details(world["day"], "0727", "0830", "0831",
                         rid=f"rid-{world['day']}")
    )


@given("one is 8 minutes late and the other is 41 minutes late")
def two_delays(world):
    day = world["day"]
    world["service_details"].extend([
        _service_details(day, "0729", "0830", "0838",
                         depart_scheduled="0727", rid=f"rid-{day}-a"),
        _service_details(day, "0815", "0915", "0956",
                         depart_scheduled="0810", rid=f"rid-{day}-b"),
    ])


# ---------------------------------------------------------------------------
# When — drive the pipeline with mocked HTTP
# ---------------------------------------------------------------------------
@when("I run the late-train report for GOD to WAT")
def run_pipeline(world):
    metrics_prefix = os.path.join(world["metrics_dir"], "metrics_")
    details_prefix = os.path.join(world["details_dir"], "details_")

    metrics_response = MagicMock()
    metrics_response.json.return_value = world["service_metrics"]
    metrics_response.raise_for_status.return_value = None

    details_iter = iter(world["service_details"])

    def fake_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if "serviceMetrics" in url:
            resp.json.return_value = world["service_metrics"]
        else:
            resp.json.return_value = next(details_iter)
        return resp

    with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
         patch.object(tfg.requests, "post", side_effect=fake_post):
        # 1) Download metrics for one day.
        tfg.writeServiceMetricsTestData(
            "GOD", "WAT", "0400", "1300",
            date.fromisoformat(world["day"]), 1, metrics_prefix,
        )
        # 2) Extract RIDs and download details.
        rids = tfg.generatePidList(world["metrics_dir"])
        tfg.writeAttributeMessageTestData(rids, details_prefix)
        # 3) Parse downloaded details and build the late-train dictionary.
        all_details = tfg.generateAttrbuteDictionary(world["details_dir"])
        route_dict = tfg.trimToRouteOnlyDictionary(all_details, "GOD", "WAT")
        latest = tfg.getLatestTrainObject(route_dict)
        # 4) Write the CSV.
        tfg.writeLateTrainsToFile("outboundLateTrains", latest, "WAT")


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------
@then("the outbound CSV exists")
def csv_exists(world):
    assert os.path.isfile(world["csv_path"])


@then(parsers.parse('the outbound CSV contains the row "{row}"'))
def csv_contains_row(world, row):
    with open(world["csv_path"]) as fh:
        lines = [line.rstrip() for line in fh]
    assert row in lines, f"row {row!r} not in {lines!r}"


@then("the outbound CSV contains no delay rows")
def csv_no_delay_rows(world):
    with open(world["csv_path"]) as fh:
        lines = [line.rstrip() for line in fh if line.strip()]
    # Header + column titles only — two lines total.
    assert len(lines) == 2, f"expected only headers, got {lines!r}"


@then(parsers.parse(
    'the outbound CSV reports a delay of {minutes:d} minutes for "{day}"'))
def csv_delay_for_day(world, minutes, day):
    with open(world["csv_path"]) as fh:
        rows = [line.rstrip().split(",") for line in fh if "," in line]
    day_row = next((r for r in rows if r[0] == day), None)
    assert day_row is not None, f"no row for {day} in {rows!r}"
    assert int(day_row[2]) == minutes, f"got {day_row}, wanted {minutes} min"
    world["last_day_row"] = day_row


@then(parsers.parse('the departure time on that row is "{time}"'))
def csv_departure_time(world, time):
    row = world.get("last_day_row")
    assert row is not None, "no day row recorded — the preceding step must run first"
    assert row[1] == time, f"departure time was {row[1]!r}, expected {time!r}"


# ---------------------------------------------------------------------------
# @recorded: drive the pipeline from JSON captured from the live HSP API.
# ---------------------------------------------------------------------------
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@given(parsers.parse('the recorded GOD-WAT response set from "{day}"'))
def recorded_response_set(world, day):
    world["recorded_day"] = day
    metrics_path = os.path.join(
        FIXTURE_DIR, f"recorded_metrics_{day}.json")
    with open(metrics_path) as fh:
        world["service_metrics"] = json.load(fh)
    world["recorded_details"] = {}
    for fname in os.listdir(FIXTURE_DIR):
        if fname.startswith("recorded_details_") and fname.endswith(".json"):
            with open(os.path.join(FIXTURE_DIR, fname)) as fh:
                payload = json.load(fh)
            rid = payload["serviceAttributesDetails"]["rid"]
            world["recorded_details"][rid] = payload


@when("I run the late-train report for GOD to WAT against the recorded set")
def run_pipeline_from_recorded(world):
    metrics_prefix = os.path.join(world["metrics_dir"], "metrics_")
    details_prefix = os.path.join(world["details_dir"], "details_")

    def fake_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if "serviceMetrics" in url:
            resp.json.return_value = world["service_metrics"]
        else:
            rid = kwargs["json"]["rid"]
            resp.json.return_value = world["recorded_details"][rid]
        return resp

    with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
         patch.object(tfg.requests, "post", side_effect=fake_post):
        tfg.writeServiceMetricsTestData(
            "GOD", "WAT", "0700", "0900",
            date.fromisoformat(world["recorded_day"]), 1, metrics_prefix,
        )
        rids = tfg.generatePidList(world["metrics_dir"])
        tfg.writeAttributeMessageTestData(rids, details_prefix)
        all_details = tfg.generateAttrbuteDictionary(world["details_dir"])
        route_dict = tfg.trimToRouteOnlyDictionary(all_details, "GOD", "WAT")
        latest = tfg.getLatestTrainObject(route_dict)
        tfg.writeLateTrainsToFile("outboundLateTrains", latest, "WAT")
