"""GmailClient — thin Gmail API wrapper with retry (financeTracker_SW port)."""
from __future__ import annotations

import base64
import time
from email.message import EmailMessage
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from trainline.adapters.gmail.errors import GmailError

_MAX_ATTEMPTS = 4
_BACKOFF_DELAYS = (1, 4, 16)
_MAX_PAGE_SIZE = 500


class GmailClient:
    """Typed wrapper over Gmail API v1 (search + send)."""

    def __init__(self, credentials: Credentials) -> None:
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        self._svc = build("gmail", "v1", credentials=credentials)

    def search_messages(self, query: str, max_results: int = 500) -> list[dict[str, Any]]:
        page_size = min(max_results, _MAX_PAGE_SIZE)
        collected: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            remaining = max_results - len(collected)
            if remaining <= 0:
                break
            kwargs: dict[str, Any] = {
                "userId": "me",
                "q": query,
                "maxResults": min(page_size, remaining),
            }
            if page_token is not None:
                kwargs["pageToken"] = page_token
            response = self._execute(self._svc.users().messages().list(**kwargs))
            messages = response.get("messages", [])
            collected.extend(messages)
            page_token = response.get("nextPageToken")
            if not page_token or not messages:
                break
        return collected

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._execute(
            self._svc.users().messages().get(
                userId="me", id=message_id, format="full"
            )
        )

    def send_message(self, message: EmailMessage) -> dict[str, Any]:
        """Send an ``EmailMessage`` via ``users.messages.send``."""
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        return self._execute(
            self._svc.users().messages().send(
                userId="me", body={"raw": raw}
            )
        )

    def _execute(self, request: Any) -> dict[str, Any]:
        last_error: HttpError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return request.execute()
            except HttpError as exc:
                status = exc.resp.status
                if status == 429 or status >= 500:
                    last_error = exc
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(_BACKOFF_DELAYS[attempt])
                    continue
                raise GmailError(str(exc)) from exc
        raise GmailError(str(last_error)) from last_error
