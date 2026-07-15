"""Offline: committed fixtures match the HSP schema used by live smoke tests."""
import json
import os

import pytest

from tests.hsp_schema import assert_details_schema, assert_metrics_schema

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.mark.offline
def test_recorded_metrics_fixture_matches_schema():
    path = os.path.join(FIXTURE_DIR, "recorded_metrics_2026-05-28.json")
    body = json.load(open(path, encoding="utf-8"))
    assert_metrics_schema(body)


@pytest.mark.offline
def test_stub_metrics_fixture_matches_schema():
    path = os.path.join(FIXTURE_DIR, "service_metrics_god_wat.json")
    body = json.load(open(path, encoding="utf-8"))
    assert_metrics_schema(body)


@pytest.mark.offline
@pytest.mark.parametrize("name", [
    "service_details_on_time.json",
    "service_details_late.json",
    "service_details_inbound_late.json",
    "service_details_very_late.json",
    "service_details_one_minute_late.json",
    "recorded_details_202605287679554.json",
    "recorded_details_202605287679538.json",
    "recorded_details_202605287684064.json",
])
def test_details_fixtures_match_schema(name):
    path = os.path.join(FIXTURE_DIR, name)
    body = json.load(open(path, encoding="utf-8"))
    assert_details_schema(body)
