"""Offline tests for Gmail config loading (FR40)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.config import GmailConfigError, load_gmail_config


@pytest.mark.offline
def test_load_gmail_config_from_credentials_file(tmp_path):
    cred = tmp_path / "trainConfig.txt"
    cred.write_text(
        "[configuration]\nusername=u\npassword=p\n\n"
        "## Gmail API ##\n"
        "GOOGLE_CLIENT_ID=cid\n"
        "GOOGLE_CLIENT_SECRET=csecret\n"
        "GMAIL_TOKEN_PATH=gmail_token.json\n"
        "DIGEST_TO=me@example.com\n",
        encoding="utf-8",
    )
    cfg = load_gmail_config(environ={}, credentials_path=str(cred))
    assert cfg.client_id == "cid"
    assert cfg.client_secret == "csecret"
    assert cfg.digest_to == "me@example.com"
    assert cfg.token_path == (tmp_path / "gmail_token.json").resolve()


@pytest.mark.offline
def test_load_gmail_config_missing_raises(tmp_path):
    cred = tmp_path / "trainConfig.txt"
    cred.write_text("[configuration]\nusername=u\npassword=p\n", encoding="utf-8")
    with pytest.raises(GmailConfigError, match="incomplete"):
        load_gmail_config(environ={}, credentials_path=str(cred))
