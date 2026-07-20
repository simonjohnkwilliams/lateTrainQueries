"""Live Gmail lookup for characterised SWR claim emails (opt-in ``@gmail``).

Requires ``## Gmail API ##`` in ``creds/trainConfig.txt`` and a token from
``python -m trainline --gmail-auth``.

Run::

    $env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\\trainConfig.txt).Path
    pytest -m gmail tests/test_live_gmail_claim_mail.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.swr_claim_mail.samples import CLAIM_ID
from trainline.adapters.config import GmailConfigError, load_gmail_config
from trainline.adapters.gmail import GmailClient, GmailConfig, get_credentials
from trainline.adapters.gmail.claim_mail import (
    ClaimMailStage,
    parse_gmail_message,
    swr_claim_search_query,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_gmail_client() -> GmailClient:
    creds_path = PROJECT_ROOT / "creds" / "trainConfig.txt"
    path = str(creds_path) if creds_path.is_file() else None
    try:
        file_cfg = load_gmail_config(credentials_path=path)
    except GmailConfigError as exc:
        pytest.skip(str(exc))
    cfg = GmailConfig(
        client_id=file_cfg.client_id,
        client_secret=file_cfg.client_secret,
        token_path=file_cfg.token_path,
        digest_to=file_cfg.digest_to,
    )
    if not cfg.token_path.is_file():
        pytest.skip(f"No Gmail token at {cfg.token_path}; run --gmail-auth")
    return GmailClient(get_credentials(cfg))


@pytest.mark.gmail
def test_live_inbox_has_three_swr_claim_stages_for_0218_108_579():
    """Find RECEIVED / Approved / PAYMENT SENT for the first live claim."""
    client = _require_gmail_client()
    hits = client.search_messages(swr_claim_search_query(CLAIM_ID), max_results=20)
    assert hits, f"No Gmail hits for {CLAIM_ID}"

    stages: set[ClaimMailStage] = set()
    amounts: set[str] = set()
    for hit in hits:
        msg = client.get_message(hit["id"])
        parsed = parse_gmail_message(msg)
        if parsed is None:
            continue
        assert parsed.claim_id == CLAIM_ID
        stages.add(parsed.stage)
        if parsed.amount_gbp:
            amounts.add(parsed.amount_gbp)

    assert ClaimMailStage.RECEIVED in stages
    assert ClaimMailStage.APPROVED in stages
    assert ClaimMailStage.PAYMENT_SENT in stages
    assert "1.57" in amounts
