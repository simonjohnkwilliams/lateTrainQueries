"""Headed live submit with human reCAPTCHA (Option A: 2026-07-16 outbound).

Opens Chromium, drives the wizard to Review, then waits for you to solve
reCAPTCHA and click Submit claim. Prints the confirmation reference when done.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trainline.adapters.claim_submission import PlaywrightBrowserSession, submit_claim
from trainline.adapters.config import load_swr_credentials
from trainline.adapters.swr_mapping import map_claim_for_swr
from trainline.engine.models import Band, Claim, Direction


def main() -> int:
    if not os.environ.get("HSP_CREDENTIALS_FILE"):
        os.environ["HSP_CREDENTIALS_FILE"] = str(ROOT / "creds" / "trainConfig.txt")
    ready = ROOT / "tickets/processed/ready_to_claim/07-16-e2e-delivery.jpg"
    if not ready.is_file():
        raise SystemExit(f"missing ticket image: {ready}")
    row = json.loads((ROOT / "Results/claims.json").read_text(encoding="utf-8"))[0]
    claim = Claim(
        date=row["date"],
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=9 * 60 + 41,
        scheduled_arrival=10 * 60 + 32,
        actual_arrival=10 * 60 + 50,
        delay=18,
        band=Band.B15_29,
        reason=row.get("reason"),
    )
    fields = map_claim_for_swr(claim)
    swr = load_swr_credentials()
    wait_s = int(os.environ.get("SWR_CAPTCHA_WAIT_SECONDS", "600"))
    session = PlaywrightBrowserSession(
        username=swr.username,
        password=swr.password,
        base_url=swr.base_url,
        headless=False,
        click_submit=False,
        human_captcha_wait_seconds=wait_s,
    )
    print(
        f"Driving to Review; a Windows alert will pop when captcha is needed "
        f"(wait up to {wait_s}s)…",
        flush=True,
    )
    result = submit_claim(
        claim,
        fields,
        ready,
        session,
        audit_path=ROOT / "Results" / "filing-audit.jsonl",
    )
    print("ok", result.ok, "ref", result.swr_reference, "err", result.error)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
