"""GmailClient — thin Gmail API wrapper with retry (financeTracker_SW port)."""
from __future__ import annotations

import base64
import os
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import google_auth_httplib2
import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from trainline.adapters.gmail.errors import GmailError

_MAX_ATTEMPTS = 4
_BACKOFF_DELAYS = (1, 4, 16)
_MAX_PAGE_SIZE = 500


def _ca_certs_path() -> str | None:
    """AVG/project CA bundle for httplib2 (does not honour REQUESTS_CA_BUNDLE alone)."""
    env = (os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or "").strip()
    if env and Path(env).is_file():
        return env
    local = Path("creds") / "ca-bundle.pem"
    if local.is_file():
        return str(local.resolve())
    return None


class GmailClient:
    """Typed wrapper over Gmail API v1 (search + send)."""

    def __init__(self, credentials: Credentials) -> None:
        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:
            pass
        ca = _ca_certs_path()
        http = httplib2.Http(ca_certs=ca) if ca else httplib2.Http()
        authed = google_auth_httplib2.AuthorizedHttp(credentials, http=http)
        self._svc = build("gmail", "v1", http=authed, cache_discovery=False)

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

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download a single attachment body (users.messages.attachments.get)."""
        response = self._execute(
            self._svc.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            )
        )
        data = response.get("data") or ""
        # Gmail uses URL-safe base64 without padding
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def list_labels(self) -> list[dict[str, Any]]:
        response = self._execute(self._svc.users().labels().list(userId="me"))
        return list(response.get("labels", []))

    def ensure_label_id(self, name: str) -> str:
        """Return label id for ``name``, creating the label if missing."""
        for label in self.list_labels():
            if label.get("name") == name:
                return str(label["id"])
        created = self._execute(
            self._svc.users().labels().create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
        )
        return str(created["id"])

    def modify_message(
        self,
        message_id: str,
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if add_label_ids:
            body["addLabelIds"] = list(add_label_ids)
        if remove_label_ids:
            body["removeLabelIds"] = list(remove_label_ids)
        return self._execute(
            self._svc.users().messages().modify(
                userId="me", id=message_id, body=body
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
