"""Gmail-specific exception hierarchy (port from financeTracker_SW)."""
from __future__ import annotations


class GmailError(Exception):
    """Raised when a Gmail API call fails after retries are exhausted."""


class GmailAuthError(GmailError):
    """Gmail OAuth failure or missing credentials."""
