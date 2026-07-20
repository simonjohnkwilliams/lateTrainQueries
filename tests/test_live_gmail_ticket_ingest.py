"""Live Gmail ticket-mail ingest smoke (opt-in ``@gmail``).

Sends nothing — only searches for subject:TICKET mail and would save attachments.
Safe to run after you have emailed yourself a TICKET photo.

    pytest -m gmail tests/test_live_gmail_ticket_ingest.py -v -o addopts=
"""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.config import GmailConfigError, load_gmail_config
from trainline.adapters.gmail import GmailClient, GmailConfig, get_credentials
from trainline.adapters.gmail.ticket_mail import build_ticket_mail_query
from trainline import cli

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_gmail_client() -> GmailClient:
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
    return GmailClient(get_credentials(cfg))


@pytest.mark.gmail
def test_live_ticket_mail_query_runs_without_error():
    """Smoke: search API accepts the ticket query (0 hits is OK)."""
    client = _require_gmail_client()
    q = build_ticket_mail_query(subject_prefix="TICKET", label=None)
    hits = client.search_messages(q, max_results=5)
    assert isinstance(hits, list)


@pytest.mark.gmail
def test_live_ingest_ticket_mail_cli(tmp_path, monkeypatch):
    """Run real ingest into a temp tickets root (needs modify scope + optional mail)."""
    monkeypatch.chdir(tmp_path)
    tickets = tmp_path / "tickets"
    out = tmp_path / "Results"
    # Point credentials at project creds
    creds = PROJECT_ROOT / "creds" / "trainConfig.txt"
    if not creds.is_file():
        pytest.skip("no trainConfig.txt")
    ca = PROJECT_ROOT / "creds" / "ca-bundle.pem"
    if ca.is_file():
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca.resolve()))
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(creds.resolve()))
    rc = cli.main([
        "--ingest-ticket-mail",
        "--tickets-root", str(tickets),
        "--out-dir", str(out),
        "--credentials-file", str(creds),
    ])
    # 0 = ok (even if zero messages); 2 = auth/config
    if rc == 2:
        pytest.skip("Gmail auth/config failed — re-run --gmail-auth with modify scope")
    assert rc == 0
    assert (tickets / "unclassified").is_dir()
