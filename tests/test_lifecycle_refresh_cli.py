"""Epic 9 / Story 9.3 — Gmail lifecycle refresh via claim_mail (FR38)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline import cli
from trainline.adapters.claim_lifecycle import LifecycleStore


def _gmail_message(*, mid: str, subject: str, body: str = "") -> dict:
    """Build a minimal Gmail ``format=full`` message dict for the parser."""
    import base64

    body_b64 = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii")
    return {
        "id": mid,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "no-replyswrdr@firstcustomercontact.com"},
            ],
            "mimeType": "text/plain",
            "body": {"data": body_b64},
        },
        "snippet": body[:80],
    }


class _FakeGmailClient:
    """Search→get_message stub keyed by claim id."""

    def __init__(self, messages_by_claim: dict[str, list[dict]]):
        self._by_claim = messages_by_claim
        self.search_calls: list[str] = []

    def search_messages(self, query: str, max_results: int = 500) -> list[dict]:
        self.search_calls.append(query)
        for cid, msgs in self._by_claim.items():
            if cid in query:
                return msgs
        return []

    def get_message(self, message_id: str) -> dict:
        for msgs in self._by_claim.values():
            for m in msgs:
                if m["id"] == message_id:
                    return m
        raise KeyError(message_id)


def _seed_store(path: Path, claim_id: str, status: str = "submitted") -> LifecycleStore:
    store = LifecycleStore(path)
    if status == "submitted":
        store.record_submitted(claim_id, date="2026-07-10", direction="outbound")
    elif status == "received":
        store.record_submitted(claim_id, date="2026-07-10", direction="outbound")
        store.apply_stage(claim_id, "received")
    elif status == "approved":
        store.record_submitted(claim_id, date="2026-07-10", direction="outbound")
        store.apply_stage(claim_id, "received")
        store.apply_stage(claim_id, "approved")
    return store


@pytest.mark.offline
def test_refresh_advances_submitted_to_received(tmp_path, monkeypatch):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path, "SWR-0218-108-579", "submitted")
    client = _FakeGmailClient(
        {
            "SWR-0218-108-579": [
                _gmail_message(
                    mid="m1",
                    subject=(
                        "South Western Railway Delay Repay - Claim "
                        "SWR-0218-108-579 - Received"
                    ),
                )
            ]
        }
    )
    rc = cli._refresh_claim_lifecycle(
        lifecycle_path=path,
        credentials_path=None,
        client=client,
    )
    assert rc == 0
    assert LifecycleStore(path).get("SWR-0218-108-579").status == "received"


@pytest.mark.offline
def test_refresh_advances_to_paid_across_messages(tmp_path, monkeypatch):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path, "SWR-0218-108-579", "submitted")
    client = _FakeGmailClient(
        {
            "SWR-0218-108-579": [
                _gmail_message(
                    mid="m1",
                    subject=(
                        "South Western Railway Delay Repay - Claim "
                        "SWR-0218-108-579 - Received"
                    ),
                ),
                _gmail_message(
                    mid="m2",
                    subject=(
                        "South Western Railway Delay Repay - Claim "
                        "SWR-0218-108-579 - Approved"
                    ),
                ),
                _gmail_message(
                    mid="m3",
                    subject=(
                        "South Western Railway Delay Repay - Claim "
                        "SWR-0218-108-579 - Payment Sent"
                    ),
                ),
            ]
        }
    )
    cli._refresh_claim_lifecycle(
        lifecycle_path=path, credentials_path=None, client=client
    )
    assert LifecycleStore(path).get("SWR-0218-108-579").status == "paid"


@pytest.mark.offline
def test_refresh_skips_unknown_stage(tmp_path, monkeypatch):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path, "SWR-0218-108-579", "submitted")
    client = _FakeGmailClient(
        {
            "SWR-0218-108-579": [
                _gmail_message(
                    mid="m1",
                    subject=(
                        "South Western Railway Delay Repay - Claim "
                        "SWR-0218-108-579 - Something Else"
                    ),
                )
            ]
        }
    )
    cli._refresh_claim_lifecycle(
        lifecycle_path=path, credentials_path=None, client=client
    )
    assert LifecycleStore(path).get("SWR-0218-108-579").status == "submitted"


@pytest.mark.offline
def test_refresh_no_gmail_client_returns_zero_and_leaves_store(tmp_path, monkeypatch):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path, "SWR-0218-108-579", "submitted")
    # No client and no factory -> refresh is a no-op
    monkeypatch.setattr(cli, "_lifecycle_gmail_client_factory", None)
    rc = cli._refresh_claim_lifecycle(
        lifecycle_path=path,
        credentials_path=None,
        client=None,
    )
    assert rc == 0
    assert LifecycleStore(path).get("SWR-0218-108-579").status == "submitted"


@pytest.mark.offline
def test_refresh_search_failure_warns_and_continues(tmp_path, monkeypatch, capsys):
    path = tmp_path / "claim-lifecycle.json"
    _seed_store(path, "SWR-0218-108-579", "submitted")

    class _BrokenClient:
        def search_messages(self, query, max_results=500):
            raise RuntimeError("network down")

    rc = cli._refresh_claim_lifecycle(
        lifecycle_path=path,
        credentials_path=None,
        client=_BrokenClient(),
    )
    assert rc == 0
    err = capsys.readouterr().err.casefold()
    assert "warning" in err or "refresh failed" in err
    assert LifecycleStore(path).get("SWR-0218-108-579").status == "submitted"


@pytest.mark.offline
def test_refresh_skips_already_reported_paid(tmp_path, monkeypatch):
    """A paid claim already reported (``reported_paid_at`` set) leaves Table 2,
    so refresh should not bother searching for it again."""
    path = tmp_path / "claim-lifecycle.json"
    store = LifecycleStore(path)
    store.record_submitted("SWR-0218-108-579", date="2026-07-10", direction="outbound")
    store.apply_stage("SWR-0218-108-579", "received")
    store.apply_stage("SWR-0218-108-579", "approved")
    store.apply_stage("SWR-0218-108-579", "paid")
    store.mark_reported_paid(["SWR-0218-108-579"])

    client = _FakeGmailClient({"SWR-0218-108-579": []})
    cli._refresh_claim_lifecycle(
        lifecycle_path=path, credentials_path=None, client=client
    )
    assert client.search_calls == []
