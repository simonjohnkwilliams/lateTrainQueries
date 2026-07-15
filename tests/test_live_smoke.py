"""Live HSP smoke + schema checks (Phase C quality loop).

Opt-in via ``pytest -m live`` with ``HSP_CREDENTIALS_FILE`` pointing at
``creds/trainConfig.txt`` (never committed). Credentials are loaded at runtime
only through ``adapters.config.load_credentials`` — nothing is hardcoded.

Successful responses are written under ``live-capture/`` (gitignore'd) so they
can be eyeballed against ``tests/fixtures/`` mocks.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.hsp_schema import assert_details_schema, assert_metrics_schema
from trainline.adapters.config import CredentialsError, load_hsp_credentials
from trainline.adapters.hsp_client import (
    HspClient,
    SERVICE_DETAILS_URL,
    SERVICE_METRICS_URL,
    extract_rids,
    map_service_details,
)
from trainline.engine.models import Direction

AUTH_HINT = (
    "HSP returned HTTP 401 Unauthorized. Check that "
    "HSP_CREDENTIALS_FILE points at creds/trainConfig.txt and that the "
    "[configuration] username=/password= are valid Open Rail Data / HSP "
    "credentials (not Darwin/KB keys from the same portal dump)."
)


def _post_expecting_ok(client, url, payload):
    from requests import HTTPError
    try:
        return client.post_json(url, payload)
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            raise AssertionError(AUTH_HINT) from exc
        raise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = PROJECT_ROOT / "live-capture"


def _require_live_client():
    try:
        creds = load_hsp_credentials()
    except CredentialsError as exc:
        pytest.skip(str(exc))
    return HspClient(
        creds.username, creds.password,
        service_metrics_url=creds.service_metrics_url,
        service_details_url=creds.service_details_url,
    )


def _recent_weekday(offset_days: int = 3) -> str:
    """A weekday a few days ago — still inside typical HSP retention."""
    day = date.today() - timedelta(days=offset_days)
    while day.weekday() >= 5:  # Sat/Sun
        day -= timedelta(days=1)
    return day.isoformat()


def _save_capture(name: str, body: dict) -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / name
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


@pytest.mark.live
def test_live_credentials_file_loads_and_authenticates():
    """Creds env + INI format work; a narrow metrics call returns 200 + schema."""
    client = _require_live_client()
    day = _recent_weekday()
    body = _post_expecting_ok(client, SERVICE_METRICS_URL, {
        "from_loc": "GOD", "to_loc": "WAT",
        "from_time": "0700", "to_time": "0900",
        "from_date": day, "to_date": day,
        "days": "WEEKDAY",
    })
    assert_metrics_schema(body)
    _save_capture(f"live_metrics_GOD_WAT_{day}.json", body)


@pytest.mark.live
def test_live_service_details_schema_and_maps_to_service():
    """Fetch one RID via details; schema matches mocks; maps to a Service."""
    client = _require_live_client()
    day = _recent_weekday()
    metrics = client.fetch_service_metrics(
        "GOD", "WAT", "0700", "0900", day, day)
    assert_metrics_schema(metrics)
    rids = extract_rids(metrics)
    if not rids:
        pytest.skip(f"no RIDs for GOD->WAT on {day} in 0700-0900")
    rid = rids[0]
    details = client.fetch_service_details(rid)
    assert_details_schema(details)
    _save_capture(f"live_details_{rid}.json", details)

    service = map_service_details(
        details, "GOD", "WAT", Direction.OUTBOUND, date=day)
    assert service is not None
    assert service.rid == rid
    assert service.origin == "GOD"
    assert service.destination == "WAT"
    assert isinstance(service.scheduled_departure, int)
    assert isinstance(service.scheduled_arrival, int)


@pytest.mark.live
def test_live_both_endpoints_polite_smoke():
    """Tiny both-direction smoke: credentials + expected response shape."""
    client = _require_live_client()
    day = _recent_weekday()
    out = client.fetch_service_metrics("GOD", "WAT", "0700", "0800", day, day)
    inn = client.fetch_service_metrics("WAT", "GOD", "1700", "1800", day, day)
    assert_metrics_schema(out)
    assert_metrics_schema(inn)
    _save_capture(f"live_metrics_outbound_{day}.json", out)
    _save_capture(f"live_metrics_inbound_{day}.json", inn)

@pytest.mark.live
def test_live_nrdp_portal_login_before_hsp():
    """Portal username/password must authenticate at NRDP /authenticate.

    HSP uses the same National Rail Data Portal account (HTTP Basic Auth).
    Darwin/KB section usernames are not used for HSP.
    """
    import requests
    try:
        creds = load_hsp_credentials()
    except CredentialsError as exc:
        pytest.skip(str(exc))
    verify = os.environ.get("REQUESTS_CA_BUNDLE") or True
    resp = requests.post(
        "https://opendata.nationalrail.co.uk/authenticate",
        data={"username": creds.username, "password": creds.password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=verify,
        timeout=30,
    )
    if resp.status_code == 401:
        raise AssertionError(
            "National Rail Data Portal rejected the portal username/password "
            "used for HSP (from [configuration], or Username/Password under "
            "the HSP section if set). Verify login at "
            "https://opendata.nationalrail.co.uk/ and that HSP is subscribed. "
            "Darwin/KB credentials in other sections are not used for HSP."
        )
    assert resp.ok, f"NRDP authenticate unexpected status {resp.status_code}"
    body = resp.json()
    assert body.get("token"), "NRDP authenticate response missing token"
