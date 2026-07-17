"""Story 3.3: end-to-end pipeline acceptance/behaviour tests (AD-8, AD-5, FR21).

Drives cli.run through the injectable transport seam so it runs entirely offline
(NFR2). The @recorded scenario grounds the whole pipeline in real Darwin data.
"""
import glob
import json
import os

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests._fakes import FakeResponse, FakeSession
from trainline.adapters.config import default_config
from trainline.adapters.hsp_client import HspClient
from trainline import cli

scenarios("features/claims_pipeline.feature")

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def world(tmp_path):
    return {
        "csv": str(tmp_path / "claims.csv"),
        "json": str(tmp_path / "claims.json"),
        "handler": None,
        "dates": ["2026-05-28"],
        "summary": None,
    }


# --- Stub builders ----------------------------------------------------------
def _stub_metrics(rids):
    return {"Services": [{"serviceAttributesMetrics": {"rids": [r]}} for r in rids]}


def _stub_details(rid, date, dep_hhmm, arr_hhmm, actual_arr_hhmm):
    return {
        "serviceAttributesDetails": {
            "date_of_service": date, "rid": rid,
            "locations": [
                {"location": "GOD", "gbtt_ptd": dep_hhmm, "gbtt_pta": "",
                 "actual_td": dep_hhmm, "actual_ta": "", "late_canc_reason": ""},
                {"location": "WAT", "gbtt_ptd": "", "gbtt_pta": arr_hhmm,
                 "actual_td": "", "actual_ta": actual_arr_hhmm,
                 "late_canc_reason": ""},
            ],
        }
    }


# --- Givens -----------------------------------------------------------------
@given(parsers.parse('a stubbed week with a 25-minute-late outbound on "{day}"'))
def stub_claimable(world, day):
    world["dates"] = [day]
    details = _stub_details("rid-late", day, "0708", "0753", "0818")  # 25 min late

    def handler(url, kw):
        if "serviceMetrics" in url:
            if kw["json"]["from_loc"] == "GOD":
                return FakeResponse(_stub_metrics(["rid-late"]))
            return FakeResponse(_stub_metrics([]))  # no inbound services
        return FakeResponse(details)

    world["handler"] = handler


@given(parsers.parse('a stubbed week where "{day}" fails to fetch'))
def stub_failure(world, day):
    world["dates"] = [day]

    def handler(url, kw):
        return FakeResponse({}, status_error=RuntimeError("HSP down"))

    world["handler"] = handler


@given(parsers.parse('the recorded GOD-WAT fixtures from "{day}"'))
def recorded(world, day):
    world["dates"] = [day]
    metrics = json.load(open(os.path.join(FIXTURE_DIR, f"recorded_metrics_{day}.json")))
    details = {}
    for path in glob.glob(os.path.join(FIXTURE_DIR, "recorded_details_*.json")):
        doc = json.load(open(path))
        details[doc["serviceAttributesDetails"]["rid"]] = doc

    def handler(url, kw):
        if "serviceMetrics" in url:
            if kw["json"]["from_loc"] == "GOD":
                return FakeResponse(metrics)
            return FakeResponse({"Services": []})  # no recorded inbound set
        return FakeResponse(details[kw["json"]["rid"]])

    world["handler"] = handler


# --- When -------------------------------------------------------------------
@when("I run the claim pipeline for that week")
@when("I run the claim pipeline for that day")
def run_pipeline(world):
    session = FakeSession(handler=world["handler"])
    client = HspClient("u", "p", session=session)
    world["summary"], _day_results = cli.run(
        default_config(), world["dates"], world["csv"], world["json"],
        client=client)


# --- Thens ------------------------------------------------------------------
@then("a CSV and a JSON claim file are written")
def files_written(world):
    assert os.path.isfile(world["csv"])
    assert os.path.isfile(world["json"])


@then(parsers.parse('the output contains a claim for "{day}"'))
def output_has_claim(world, day):
    rows = json.loads(open(world["json"]).read())
    assert any(r["date"] == day for r in rows)
    assert world["summary"]["total_claims"] >= 1


@then(parsers.parse('the day "{day}" is reported as not analysed'))
def day_not_analysed(world, day):
    assert day in world["summary"]["not_analysed"]


@then("it is not counted as a clean no-claim day")
def not_a_no_claim(world):
    # not_analysed days are excluded from the analysed count (AD-5).
    assert world["summary"]["analysed"] == 0
    assert world["summary"]["claimable_days"] == 0


@then(parsers.parse('the day "{day}" is analysed with zero claims'))
def analysed_zero_claims(world, day):
    assert day not in world["summary"]["not_analysed"]
    assert world["summary"]["analysed"] == 1
    assert world["summary"]["total_claims"] == 0
