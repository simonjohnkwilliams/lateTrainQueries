"""Shared HSP response schema checks (live smoke + offline fixture fidelity).

These validators encode the structural contract ``hsp_client`` and the recorded
fixtures rely on. Live tests confirm the real API still matches; offline tests
confirm committed fixtures stay aligned with that contract.
"""
from __future__ import annotations


def assert_metrics_schema(body: dict) -> None:
    """``serviceMetrics`` body must expose ``Services`` with RID lists."""
    assert isinstance(body, dict), "metrics response must be a JSON object"
    assert "Services" in body, "metrics response missing 'Services'"
    assert isinstance(body["Services"], list), "'Services' must be a list"
    for service in body["Services"]:
        assert isinstance(service, dict), "each Services entry must be an object"
        sam = service.get("serviceAttributesMetrics")
        assert isinstance(sam, dict), "missing serviceAttributesMetrics"
        assert "rids" in sam, "serviceAttributesMetrics.rids required"
        assert isinstance(sam["rids"], list), "rids must be a list"
        for rid in sam["rids"]:
            assert isinstance(rid, str) and rid, "each rid must be a non-empty str"


def assert_details_schema(body: dict) -> None:
    """``serviceDetails`` body must expose calling-point location times."""
    assert isinstance(body, dict), "details response must be a JSON object"
    sad = body.get("serviceAttributesDetails")
    assert isinstance(sad, dict), "missing serviceAttributesDetails"
    assert isinstance(sad.get("rid"), str) and sad["rid"], "rid required"
    assert isinstance(sad.get("date_of_service"), str), "date_of_service required"
    locations = sad.get("locations")
    assert isinstance(locations, list) and locations, "locations must be a non-empty list"
    for loc in locations:
        assert isinstance(loc, dict), "each location must be an object"
        assert isinstance(loc.get("location"), str) and loc["location"], "CRS required"
        for field in ("gbtt_ptd", "gbtt_pta", "actual_td", "actual_ta", "late_canc_reason"):
            assert field in loc, f"location missing '{field}'"
            assert isinstance(loc[field], str), f"'{field}' must be a string (may be empty)"
