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

import os

import requests

HSP_BASE_URL = "https://hsp-prod.rockshore.net/api/v1"
SERVICE_METRICS_URL = f"{HSP_BASE_URL}/serviceMetrics"
SERVICE_DETAILS_URL = f"{HSP_BASE_URL}/serviceDetails"


class HspClient:
    """Authenticated HSP HTTP client over an injectable transport."""

    def __init__(self, username: str, password: str, session=None):
        self._auth = (username, password)
        self._session = session if session is not None else requests.Session()

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
