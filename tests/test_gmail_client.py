"""Unit tests for GmailClient (mocked Google API)."""
from __future__ import annotations

import base64
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError


def _http_error(status: int, content: bytes = b"error") -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=content)


@pytest.fixture
def mock_service():
    with patch("trainline.adapters.gmail.client.build") as mock_build:
        svc = MagicMock()
        mock_build.return_value = svc
        yield svc


def _client(mock_service):
    from google.oauth2.credentials import Credentials

    from trainline.adapters.gmail.client import GmailClient

    return GmailClient(MagicMock(spec=Credentials))


@pytest.mark.offline
def test_search_messages_returns_empty_when_no_messages_key(mock_service):
    mock_service.users().messages().list().execute.return_value = {}
    assert _client(mock_service).search_messages("subject:hello") == []


@pytest.mark.offline
def test_search_messages_paginates(mock_service):
    page1 = {"messages": [{"id": "1"}], "nextPageToken": "tok"}
    page2 = {"messages": [{"id": "2"}]}
    list_mock = MagicMock()
    list_mock.execute.side_effect = [page1, page2]
    mock_service.users().messages().list.return_value = list_mock
    result = _client(mock_service).search_messages("q", max_results=500)
    assert result == [{"id": "1"}, {"id": "2"}]


@pytest.mark.offline
def test_get_message_returns_payload(mock_service):
    fake = {"id": "m1", "payload": {"headers": []}}
    get_mock = MagicMock()
    get_mock.execute.return_value = fake
    mock_service.users().messages().get.return_value = get_mock
    assert _client(mock_service).get_message("m1") == fake


@pytest.mark.offline
def test_send_message_encodes_raw_rfc822(mock_service):
    send_mock = MagicMock()
    send_mock.execute.return_value = {"id": "sent1"}
    mock_service.users().messages().send.return_value = send_mock

    msg = EmailMessage()
    msg["To"] = "a@example.com"
    msg["From"] = "me@example.com"
    msg["Subject"] = "Test"
    msg.set_content("hello")

    result = _client(mock_service).send_message(msg)
    assert result["id"] == "sent1"
    body = mock_service.users().messages().send.call_args.kwargs.get("body")
    if body is None:
        body = mock_service.users().messages().send.call_args[1]["body"]
    raw = body["raw"]
    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    assert b"hello" in decoded
    assert b"Test" in decoded


@pytest.mark.offline
def test_execute_retries_on_429_then_succeeds(mock_service):
    list_mock = MagicMock()
    list_mock.execute.side_effect = [
        _http_error(429),
        {"messages": [{"id": "ok"}]},
    ]
    mock_service.users().messages().list.return_value = list_mock
    with patch("trainline.adapters.gmail.client.time.sleep"):
        result = _client(mock_service).search_messages("q")
    assert result == [{"id": "ok"}]
    assert list_mock.execute.call_count == 2


@pytest.mark.offline
def test_execute_raises_gmail_error_on_400(mock_service):
    from trainline.adapters.gmail.errors import GmailError

    list_mock = MagicMock()
    list_mock.execute.side_effect = _http_error(400)
    mock_service.users().messages().list.return_value = list_mock
    with pytest.raises(GmailError):
        _client(mock_service).search_messages("q")
