"""Step definitions for tests/features/live_hsp_api.feature.

This is the only test that makes real HTTP calls to hsp-prod.rockshore.net.
It is tagged @live and skipped by default (see pytest.ini addopts). To run it
in CI, set HSP_CREDENTIALS_FILE to a config file with Open Rail Data creds
and override the marker filter: `python -m pytest -m live`.
"""
import configparser
import json
import os
from datetime import date, timedelta

import pytest
from pytest_bdd import given, scenarios, then, when

import TestFileGenerator as tfg

scenarios("features/live_hsp_api.feature")


@pytest.fixture
def live_world(tmp_path, monkeypatch):
    metrics_dir = tmp_path / "metrics"
    details_dir = tmp_path / "details"
    results_dir = tmp_path / "Results"
    metrics_dir.mkdir()
    details_dir.mkdir()
    results_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    return {
        "metrics_dir": str(metrics_dir),
        "details_dir": str(details_dir),
        "csv_path": str(results_dir / "outboundLateTrains.csv"),
        "metrics_files": [],
        "details_files": [],
    }


@given("HSP credentials are available via the HSP_CREDENTIALS_FILE env var")
def creds_available():
    path = os.environ.get("HSP_CREDENTIALS_FILE")
    if not path or not os.path.isfile(path):
        pytest.skip("HSP_CREDENTIALS_FILE is not set or file is missing — "
                    "the live scenario needs Open Rail Data credentials")
    # Validate INI structure up-front so the failure mode here is clearer than
    # configparser blowing up deep inside requests.
    cfg = configparser.ConfigParser()
    cfg.read(path)
    if not cfg.has_section("configuration"):
        pytest.skip(f"{path} is missing a [configuration] section")
    if not cfg.has_option("configuration", "username") or \
       not cfg.has_option("configuration", "password"):
        pytest.skip(f"{path} must contain username= and password= keys")


@when("I run the late-train pipeline for a single weekday window of GOD to WAT")
def run_live(live_world):
    metrics_prefix = os.path.join(live_world["metrics_dir"], "metrics_")
    details_prefix = os.path.join(live_world["details_dir"], "details_")

    # Use a weekday from two weeks ago so the HSP archive is settled.
    target = date.today() - timedelta(days=14)
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    live_world["target_date"] = target

    tfg.writeServiceMetricsTestData(
        "GOD", "WAT", "0700", "0900",
        target, 1, metrics_prefix,
    )
    live_world["metrics_files"] = sorted(os.listdir(live_world["metrics_dir"]))

    rids = tfg.generatePidList(live_world["metrics_dir"])
    live_world["rids"] = rids
    # Keep the live request volume small for CI politeness.
    tfg.writeAttributeMessageTestData(rids[:3], details_prefix)
    live_world["details_files"] = sorted(os.listdir(live_world["details_dir"]))

    all_details = tfg.generateAttrbuteDictionary(live_world["details_dir"])
    route_dict = tfg.trimToRouteOnlyDictionary(all_details, "GOD", "WAT")
    latest = tfg.getLatestTrainObject(route_dict)
    tfg.writeLateTrainsToFile("outboundLateTrains", latest, "WAT")


@then("a serviceMetrics JSON file is written for that day")
def metrics_file_written(live_world):
    assert live_world["metrics_files"], (
        "no serviceMetrics file was written — check HSP credentials are valid "
        "and hsp-prod.rockshore.net is reachable"
    )
    # Confirm the saved file is parseable JSON with the expected outer shape.
    first = os.path.join(live_world["metrics_dir"], live_world["metrics_files"][0])
    with open(first) as fh:
        payload = json.load(fh)
    assert "Services" in payload, f"unexpected payload shape: {list(payload)}"


@then("a serviceDetails JSON file is written for at least one service")
def details_file_written(live_world):
    if not live_world["rids"]:
        pytest.skip("HSP returned zero services for the chosen window — "
                    "try a different weekday or a wider time range")
    assert live_world["details_files"], (
        "no serviceDetails file was written despite RIDs being available"
    )
    first = os.path.join(live_world["details_dir"], live_world["details_files"][0])
    with open(first) as fh:
        payload = json.load(fh)
    assert "serviceAttributesDetails" in payload, (
        f"unexpected serviceDetails shape: {list(payload)}"
    )


@then("the outbound CSV header line is written")
def csv_header_written(live_world):
    assert os.path.isfile(live_world["csv_path"]), \
        "Results/outboundLateTrains.csv was never written"
    with open(live_world["csv_path"]) as fh:
        first_line = fh.readline().strip()
    assert first_line == "Outbound Train To WAT", \
        f"unexpected first line: {first_line!r}"
