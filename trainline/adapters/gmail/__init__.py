"""Gmail adapter package — OAuth + API client for Epic 7 ops email."""
from trainline.adapters.gmail.auth import (
    GMAIL_SCOPES,
    GmailConfig,
    get_credentials,
    run_auth_flow,
    store_credentials,
)
from trainline.adapters.gmail.client import GmailClient
from trainline.adapters.gmail.errors import GmailAuthError, GmailError

__all__ = [
    "GMAIL_SCOPES",
    "GmailAuthError",
    "GmailClient",
    "GmailConfig",
    "GmailError",
    "get_credentials",
    "run_auth_flow",
    "store_credentials",
]
