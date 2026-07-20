"""Gmail OAuth — file-token port of financeTracker_SW ``gmail/auth.py``.

Stores Google ``Credentials.to_json()`` on disk (path from ``GmailConfig``),
not in SQLAlchemy. Scopes: readonly (inbox claim status) + send (ops digest).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from trainline.adapters.gmail.errors import GmailAuthError

GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
)

_REFRESH_SKEW_SECONDS = 60
_lock = threading.Lock()


@dataclass(frozen=True)
class GmailConfig:
    client_id: str
    client_secret: str
    token_path: Path
    digest_to: str


def _inject_truststore() -> None:
    """Honour OS/AVG TLS interception for Google HTTPS (same as HSP / client)."""
    import os
    from pathlib import Path

    # Prefer project CA bundle (AVG MITM) so ``requests`` used by google-auth verifies.
    ca = Path("creds") / "ca-bundle.pem"
    if ca.is_file():
        ca_path = str(ca.resolve())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("CURL_CA_BUNDLE", ca_path)
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def run_auth_flow(config: GmailConfig) -> Credentials:
    """Installed-app OAuth consent; returns fresh credentials."""
    _inject_truststore()
    client_config: dict[str, Any] = {
        "installed": {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(
        client_config, scopes=list(GMAIL_SCOPES)
    )
    return flow.run_local_server(port=0)


def store_credentials(creds: Credentials, config: GmailConfig) -> None:
    """Persist credentials JSON to ``config.token_path``."""
    config.token_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(creds.to_json(), encoding="utf-8")


def get_credentials(config: GmailConfig) -> Credentials:
    """Load token file; refresh when within skew of expiry."""
    if not config.token_path.is_file():
        raise GmailAuthError(
            "No Gmail credentials stored. Run: python -m trainline --gmail-auth"
        )
    raw = json.loads(config.token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(raw)

    with _lock:
        expiry = creds.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry is not None and (
            expiry - datetime.now(UTC)
        ) < timedelta(seconds=_REFRESH_SKEW_SECONDS):
            _inject_truststore()
            creds.refresh(Request())
            store_credentials(creds, config)
    return creds
