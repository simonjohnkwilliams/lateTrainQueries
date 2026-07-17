"""Live SMTP digest smoke (opt-in).

Loads SMTP from env and/or ``creds/trainConfig.txt`` (via ``HSP_CREDENTIALS_FILE``
or default path). Never runs in default ``pytest``. Skips if SMTP settings absent.

Gmail: use an App Password in ``SMTP_PASSWORD`` (spaces optional).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trainline.adapters.config import EmailConfigError, load_email_config
from trainline.adapters.notification import digest_subject, render_digest, send_digest
from trainline.engine.models import DayResult, FetchStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_smtp():
    creds = PROJECT_ROOT / "creds" / "trainConfig.txt"
    path = str(creds) if creds.is_file() else None
    try:
        return load_email_config(credentials_path=path)
    except EmailConfigError as exc:
        pytest.skip(str(exc))


@pytest.mark.live
def test_live_digest_smtp_delivers_test_message():
    """Manual case 2: real SMTP delivers a tiny digest (check DIGEST_TO inbox)."""
    cfg = _require_smtp()
    day_results = [
        DayResult(date=date.today().isoformat(), status=FetchStatus.OK, claims=()),
    ]
    html, text = render_digest(day_results)
    subject = digest_subject(day_results) + " [live smoke]"
    send_digest(subject, html, text, cfg)
    assert "@" in cfg.digest_to
    assert cfg.smtp_host
