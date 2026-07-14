"""HSP API adapter — auth, AVG-TLS, injectable transport (Story 2.1).

The HTTP call is an injectable seam: the client takes a ``session`` (default
``requests.Session()``), so tests pass a fake and run offline with no network or
credentials (NFR2). HTTP basic auth is applied from supplied credentials;
credential *loading* from ``HSP_CREDENTIALS_FILE`` lives in ``adapters.config``
(FR17), and the composition root passes them in.

NFR3 (AVG TLS interception): ``REQUESTS_CA_BUNDLE`` is honoured for verification
so requests verify under AVG's MITM. ``verify`` is never disabled.

Later stories add ``serviceMetrics``/``serviceDetails`` fetching (2.2/2.3), the
response cache (2.4), and the per-day fetch-failure rollup (2.5). May import
``engine.models`` only within the package (AD-2).
"""
from __future__ import annotations

import json
import os

import requests

from trainline.engine.models import Direction, Service

HSP_BASE_URL = "https://hsp-prod.rockshore.net/api/v1"
SERVICE_METRICS_URL = f"{HSP_BASE_URL}/serviceMetrics"
SERVICE_DETAILS_URL = f"{HSP_BASE_URL}/serviceDetails"


class HspClient:
    """Authenticated HSP HTTP client over an injectable transport."""

    def __init__(self, username: str, password: str, session=None,
                 cache_dir=None, force_refresh: bool = False):
        self._auth = (username, password)
        self._session = session if session is not None else requests.Session()
        self._cache_dir = cache_dir  # None disables caching
        self._force_refresh = force_refresh

    def clear_cache(self) -> None:
        """Remove all cached responses (the FR4 force-refresh mechanism)."""
        if not self._cache_dir or not os.path.isdir(self._cache_dir):
            return
        for name in os.listdir(self._cache_dir):
            if name.endswith(".json"):
                os.remove(os.path.join(self._cache_dir, name))

    def _cached_post(self, cache_key: str, url: str, payload: dict) -> dict:
        """POST via the on-disk cache (NFR4).

        On a cache hit (and not force_refresh) the cached response is returned
        and no API call is made. Only *successful* responses are cached —
        ``post_json`` raises before any write, so a failed fetch is never
        persisted as a success (supports the AD-5 fetch-failure contract).
        """
        if not self._cache_dir:
            return self.post_json(url, payload)
        path = os.path.join(self._cache_dir, cache_key)
        if not self._force_refresh and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        data = self.post_json(url, payload)
        os.makedirs(self._cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return data

    def post_json(self, url: str, payload: dict) -> dict:
        """POST ``payload`` as JSON with basic auth; return the parsed body.

        Honours ``REQUESTS_CA_BUNDLE`` (NFR3) and never disables TLS verification.
        """
        kwargs = {"json": payload, "auth": self._auth}
        ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE")
        if ca_bundle:
            kwargs["verify"] = ca_bundle
        response = self._session.post(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def fetch_service_metrics(self, from_loc, to_loc, from_time, to_time,
                              from_date, to_date):
        """POST serviceMetrics for one direction/window/date range (FR1).

        Body shape is exactly what the HSP API expects, including
        ``days: 'WEEKDAY'``. Both directions are queried by calling this with the
        origin/destination swapped (the composition root does that, FR1).
        """
        payload = {
            "from_loc": from_loc,
            "to_loc": to_loc,
            "from_time": from_time,
            "to_time": to_time,
            "from_date": from_date,
            "to_date": to_date,
            "days": "WEEKDAY",
        }
        cache_key = (f"metrics_{from_loc}_{to_loc}_{from_date}_{to_date}"
                     f"_{from_time}_{to_time}.json")
        return self._cached_post(cache_key, SERVICE_METRICS_URL, payload)

    def fetch_service_details(self, rid: str) -> dict:
        """POST serviceDetails for a single RID (FR2). Body is ``{"rid": rid}``.

        Cached per RID (NFR4): a RID already fetched is served from disk.
        """
        return self._cached_post(f"details_{rid}.json", SERVICE_DETAILS_URL,
                                 {"rid": rid})


def extract_rids(metrics_response: dict) -> list[str]:
    """Return **all** RIDs in a serviceMetrics response (FR3), order-preserving.

    The old code took ``rids[0]`` only and silently dropped services; this
    returns every ``Services[].serviceAttributesMetrics.rids`` entry, de-duped.
    """
    rids: list[str] = []
    seen: set[str] = set()
    for service in metrics_response.get("Services", []):
        for rid in service.get("serviceAttributesMetrics", {}).get("rids", []):
            if rid not in seen:
                seen.add(rid)
                rids.append(rid)
    return rids


def _raw_minutes(hhmm):
    """HHMM string → minutes-past-midnight int, or None for empty."""
    if not hhmm:
        return None
    return int(hhmm[:2]) * 60 + int(hhmm[2:4])


def _parse_locations(locations):
    """Convert each calling point's HHMM times to origin-day-relative minutes.

    Walks the calling points in order; when a scheduled time drops below the
    running maximum it has rolled past midnight, so +1440 is applied from there
    on (AD-4). Empty times map to None (AD-3).
    """
    parsed = []
    day_offset = 0
    last = None
    for loc in locations:
        sched = loc.get("gbtt_pta") or loc.get("gbtt_ptd")
        rep = _raw_minutes(sched)
        if rep is not None:
            candidate = rep + day_offset
            if last is not None and candidate < last:
                day_offset += 1440
                candidate = rep + day_offset
            last = candidate

        def _rel(field):
            raw = _raw_minutes(loc.get(field))
            return None if raw is None else raw + day_offset

        parsed.append({
            "location": loc.get("location"),
            "gbtt_ptd": _rel("gbtt_ptd"),
            "gbtt_pta": _rel("gbtt_pta"),
            "actual_td": _rel("actual_td"),
            "actual_ta": _rel("actual_ta"),
            "reason": loc.get("late_canc_reason") or None,
        })
    return parsed


def _find(parsed, crs):
    for loc in parsed:
        if loc["location"] == crs:
            return loc
    return None


def map_service_details(response, origin, destination, direction, date=None):
    """Map a raw serviceDetails response to a domain ``Service`` (AD-3, AD-4).

    ``origin``/``destination`` are the route leg's CRS codes; calling points are
    selected by CRS, never by list position (services may start elsewhere, e.g.
    HAV). Returns ``None`` if this service does not serve both route stops.

    Empty actual times map to ``None`` (AD-3). Empty actuals plus a
    ``late_canc_reason`` set ``cancelled=True`` and carry the reason as the raw
    signal only — no fallback delay is computed here (AD-6).
    """
    sad = response.get("serviceAttributesDetails") or {}
    parsed = _parse_locations(sad.get("locations", []))
    origin_loc = _find(parsed, origin)
    destination_loc = _find(parsed, destination)
    if origin_loc is None or destination_loc is None:
        return None

    scheduled_departure = origin_loc["gbtt_ptd"]
    scheduled_arrival = destination_loc["gbtt_pta"]
    if scheduled_departure is None or scheduled_arrival is None:
        return None

    actual_arrival = destination_loc["actual_ta"]
    reason = destination_loc["reason"] or origin_loc["reason"]
    cancelled = actual_arrival is None and reason is not None

    return Service(
        rid=sad.get("rid"),
        direction=direction if isinstance(direction, Direction) else Direction(direction),
        origin=origin,
        destination=destination,
        date=date or sad.get("date_of_service"),
        scheduled_departure=scheduled_departure,
        scheduled_arrival=scheduled_arrival,
        actual_departure=origin_loc["actual_td"],
        actual_arrival=actual_arrival,
        cancelled=cancelled,
        reason=reason,
    )
