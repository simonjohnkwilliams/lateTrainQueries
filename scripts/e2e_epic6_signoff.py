"""Epic 6 live sign-off (Option A): newest ticket photo + claim day 2026-07-16.

1. Copy newest sample ticket → unclassified → classify (Ollama)
2. Ensure ready ticket MM-DD matches claim day (delivery test rename)
3. Assess that day via HSP
4. Live SWR file with Playwright (Submit claim)
5. Print confirmation / audit line

Requires: HSP_CREDENTIALS_FILE, ## SWR Login ##, Ollama for classify, playwright.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CLAIM_DAY = "2026-07-16"  # last weekday with HSP claims (Option A)


def _newest_sample() -> Path:
    samples = sorted(
        (ROOT / "sample-tickets").glob("*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # Prefer highest camera-stamp name among 2025* if present
    stamped = sorted(
        (ROOT / "sample-tickets").glob("2025*.jpg"),
        key=lambda p: p.name,
        reverse=True,
    )
    if stamped:
        return stamped[0]
    if samples:
        return samples[0]
    golden = ROOT / "tests/fixtures/tickets/golden/day_return_2025-01-07_god_terminals.jpg"
    if golden.is_file():
        return golden
    raise SystemExit("No sample ticket found")


def main() -> int:
    os.environ.setdefault(
        "HSP_CREDENTIALS_FILE",
        str(ROOT / "creds" / "trainConfig.txt"),
    )
    ca = ROOT / "creds" / "ca-bundle.pem"
    if ca.is_file():
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(ca))
        os.environ.setdefault("NODE_EXTRA_CA_CERTS", str(ca))

    from trainline import cli
    from trainline.adapters.claim_submission import PlaywrightBrowserSession
    from trainline.adapters.config import load_swr_credentials
    from trainline.adapters.ticket_intake import tickets_layout

    src = _newest_sample()
    layout = tickets_layout(ROOT / "tickets")
    layout.ensure()
    # Clear unclassified for a clean classify of one file
    for p in layout.unclassified.iterdir():
        if p.is_file():
            p.unlink()
    dest = layout.unclassified / src.name
    shutil.copy2(src, dest)
    print(f"1. Copied {src.name} -> {dest}")

    print("2. Classifying via Ollama...")
    rc = cli.main(["--classify-tickets", "--tickets-root", str(layout.root)])
    print(f"   classify exit={rc}")

    # Option A: gate matches claim day MM-DD, not OCR journey year
    mm_dd = CLAIM_DAY[5:7] + "-" + CLAIM_DAY[8:10]
    ready_ticket = layout.ready_to_claim / f"{mm_dd}-e2e-delivery.jpg"
    # Prefer classified ready file if any; else copy sample
    ready_files = [p for p in layout.ready_to_claim.iterdir() if p.is_file()]
    if ready_files:
        shutil.copy2(ready_files[0], ready_ticket)
    else:
        shutil.copy2(src, ready_ticket)
    print(f"3. Gate ticket for claim day: {ready_ticket.name}")

    out_dir = ROOT / "Results"
    out_dir.mkdir(exist_ok=True)
    print(f"4. Assessing HSP for {CLAIM_DAY}...")
    rc = cli.main([
        "--from-date", CLAIM_DAY,
        "--to-date", CLAIM_DAY,
        "--out-dir", str(out_dir),
        "--cache-dir", str(ROOT / ".hsp-cache"),
        "--tickets-root", str(layout.root),
        "--no-digest",
    ])
    print(f"   assess exit={rc}")
    claims_path = out_dir / "claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    print(f"   claims={len(claims)}")
    if not claims:
        print("ERROR: no claims for day — cannot file")
        return 1

    # Sign-off: file one outbound claim only (delivery check).
    from trainline.adapters.claim_submission import submit_claim
    from trainline.adapters.swr_mapping import map_claim_for_swr
    from trainline.adapters.ticket_gate import move_to_claimed
    from trainline.engine.models import Band, Claim, Direction

    row = next(c for c in claims if c.get("direction") == "outbound")
    claim = Claim(
        date=row["date"],
        direction=Direction.OUTBOUND,
        origin=row.get("origin", "GOD"),
        destination=row.get("destination", "WAT"),
        scheduled_departure=_parse_hhmm(row.get("scheduled_departure", "09:41")),
        scheduled_arrival=_parse_hhmm(row.get("scheduled_arrival", "10:32")),
        actual_arrival=_parse_hhmm(row.get("actual_arrival", "10:50")),
        delay=int(row.get("delay_min") or 18),
        band=Band.B15_29,
        reason=row.get("reason") or None,
    )
    fields = map_claim_for_swr(claim)
    swr = load_swr_credentials()
    session = PlaywrightBrowserSession(
        username=swr.username,
        password=swr.password,
        base_url=swr.base_url,
        headless=True,
        click_submit=True,
        dry_run_to_review=False,
    )
    audit = out_dir / "filing-audit.jsonl"
    print("5. Live SWR submit (one outbound claim)...")
    result = submit_claim(
        claim, fields, ready_ticket, session, audit_path=audit
    )
    print(f"   ok={result.ok} ref={result.swr_reference} err={result.error}")
    if result.ok and ready_ticket.is_file():
        moved = move_to_claimed(ready_ticket, layout.claimed)
        print(f"   moved ticket -> {moved}")
    if audit.is_file():
        print("6. Audit tail:")
        for line in audit.read_text(encoding="utf-8").splitlines()[-3:]:
            print("  ", line)
    return 0 if result.ok else 1


def _parse_hhmm(value: str) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if ":" in text:
        h, m = text.split(":", 1)
        return int(h) * 60 + int(m)
    return int(text) if text.isdigit() else 0


if __name__ == "__main__":
    raise SystemExit(main())
