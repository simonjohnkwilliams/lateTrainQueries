"""Live Gmail send smoke (opt-in ``@gmail``).

Sends a one-line test message to ``DIGEST_TO`` via Gmail API.
Requires ``## Gmail API ##`` + token from ``python -m trainline --gmail-auth``.

    pytest -m gmail tests/test_live_gmail_digest_send.py -v
"""
from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from trainline.adapters.config import GmailConfigError, load_gmail_config
from trainline.adapters.gmail import GmailClient, GmailConfig, get_credentials

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_gmail_client() -> tuple[GmailClient, str]:
    path = PROJECT_ROOT / "creds" / "trainConfig.txt"
    path_s = str(path) if path.is_file() else None
    try:
        file_cfg = load_gmail_config(credentials_path=path_s)
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
    return GmailClient(get_credentials(cfg)), file_cfg.digest_to


@pytest.mark.gmail
def test_live_gmail_send_one_line_to_digest_to():
    client, digest_to = _require_gmail_client()
    msg = EmailMessage()
    msg["To"] = digest_to
    msg["From"] = digest_to
    msg["Subject"] = "lateTrainQueries Gmail send smoke [opt-in]"
    msg.set_content("Gmail API send smoke — safe to delete.\n")
    result = client.send_message(msg)
    assert result.get("id"), result
