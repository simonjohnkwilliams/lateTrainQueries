"""Composition root (AD-8) - the only MVP orchestrator.

Wires config -> hsp_client -> engine.optimise -> storage (+ optional digest)
and nothing else orchestrates. A future Lambda handler would be a second
composition root calling the same ``engine.optimise``; orchestration never
moves into the engine.

MVP one-liner: ``python -m trainline`` analyses the last week of weekdays and
writes ``Results/claims.csv`` + ``Results/claims.json``. Credentials default to
``creds/trainConfig.txt`` when ``HSP_CREDENTIALS_FILE`` is unset.
"""
from __future__ import annotations

import argparse
import logging
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from trainline.adapters import storage
from trainline.adapters.claim_submission import (
    DEFAULT_AUDIT_PATH,
    FakeBrowserSession,
    PlaywrightBrowserSession,
    submit_all_claims,
)
from trainline.adapters.config import (
    EmailConfigError,
    default_config,
    load_email_config,
    load_hsp_credentials,
    make_config,
)
from trainline.adapters.hsp_client import HspClient, fetch_day
from trainline.adapters.notification import digest_subject, render_digest, send_digest
from trainline.adapters.swr_mapping import map_claim_for_swr
from trainline.adapters.ticket_gate import (
    filter_claims_not_already_claimed,
    format_match_errors,
    gate_blocks_filing,
    load_claim_dates_from_json,
    match_tickets_to_claims,
    move_to_claimed,
    resolve_ticket_scan_dir,
    scan_ticket_dir,
)
from trainline.adapters.ticket_intake import (
    classify_unclassified,
    tickets_layout,
)
from trainline.adapters.ollama_vision import (
    DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL,
    FALLBACK_MODEL as OLLAMA_FALLBACK_MODEL,
    OllamaVisionOcrEngine,
    ensure_ollama_reachable,
    list_ollama_models,
)
from trainline.engine.models import FetchStatus
from trainline.engine.optimiser import optimise

# MVP default: one working week of weekday analysis ending yesterday.
DEFAULT_DAYS_BACK = 5

# Injectable SMTP transport for offline tests (Story 4.3). ``None`` => real SMTP.
_digest_transport = None

# Injectable browser factory for ``--file`` offline tests (Story 6.4).
# ``None`` => FakeBrowserSession, or Playwright when ``--live-submit``.
_file_browser_factory = None


def _today() -> date:
    """Clock seam for tests."""
    return date.today()


def _default_credentials_path() -> str | None:
    """Prefer ``creds/trainConfig.txt`` under the current working directory."""
    candidate = Path.cwd() / "creds" / "trainConfig.txt"
    if candidate.is_file():
        return str(candidate)
    working = Path.cwd() / "creds" / "workingConfig.txt"
    if working.is_file():
        return str(working)
    return None


def _batches(items, size):
    size = max(1, int(size))
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _weekdays_inclusive(start: date, end: date) -> list[str]:
    if start > end:
        raise ValueError(
            f"from-date {start.isoformat()} is after to-date {end.isoformat()}")
    days: list[str] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def lookback_weekdays(config, today: date | None = None) -> list[str]:
    """ISO weekdays ending at ``config.to_date`` (or yesterday), length lookback."""
    if config.to_date:
        end = datetime.strptime(config.to_date, "%Y-%m-%d").date()
    else:
        end = (today or _today()) - timedelta(days=1)
    days: list[str] = []
    cursor = end
    while len(days) < config.lookback_days:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    days.reverse()
    return days


def resolve_run_dates(
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    days_back: int | None = None,
    lookback_days: int | None = None,
    today: date | None = None,
) -> list[str]:
    """Resolve the weekday dates a run will analyse.

    Precedence:
      1. ``from_date`` / ``to_date`` concrete ISO range (weekdays inclusive)
      2. ``days_back`` or ``lookback_days`` count of weekdays ending at
         ``to_date`` or yesterday
      3. Default ``DEFAULT_DAYS_BACK`` (5) - last week's workdays
    """
    today = today or _today()
    if from_date or to_date:
        end = (
            datetime.strptime(to_date, "%Y-%m-%d").date()
            if to_date else today - timedelta(days=1)
        )
        start = (
            datetime.strptime(from_date, "%Y-%m-%d").date()
            if from_date else end
        )
        return _weekdays_inclusive(start, end)

    count = days_back if days_back is not None else lookback_days
    if count is None:
        count = DEFAULT_DAYS_BACK
    cfg = make_config(to_date=to_date, lookback_days=count)
    return lookback_weekdays(cfg, today=today)


def build_client(session=None, cache_dir=None, credentials_path=None):
    """Construct an authenticated HspClient from the credentials file (FR17)."""
    path = credentials_path or os.environ.get("HSP_CREDENTIALS_FILE")
    if not path:
        path = _default_credentials_path()
    creds = load_hsp_credentials(path)
    return HspClient(
        creds.username, creds.password, session=session, cache_dir=cache_dir,
        service_metrics_url=creds.service_metrics_url,
        service_details_url=creds.service_details_url,
    )


def _progress(msg: str) -> None:
    """User-visible progress on stderr (keeps stdout free for JSON summaries)."""
    print(msg, file=sys.stderr, flush=True)


def _configure_cli_logging() -> None:
    """INFO logging to stderr for every CLI entry path (assess, classify, check)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )


def run(config, dates, out_csv, out_json, *, client=None, session=None,
        cache_dir=None, credentials_path=None):
    """Run the pipeline end-to-end and write CSV + JSON claim files.

    Returns ``(summary, day_results)`` so the composition root can render a
    digest (Story 4.3) without re-fetching.
    """
    if client is None:
        _progress("Loading credentials and building HSP client...")
        client = build_client(session=session, cache_dir=cache_dir,
                              credentials_path=credentials_path)

    dates = list(dates)
    total = len(dates)
    _progress(
        f"Fetching {total} weekday(s) {dates[0]}..{dates[-1]} "
        f"(batch_size={config.batch_size}, cache={cache_dir or 'off'}). "
        "First run can take several minutes; re-runs use the cache."
    )
    fetched = []
    done = 0
    for batch_i, batch in enumerate(_batches(dates, config.batch_size), start=1):
        _progress(f"Batch {batch_i}: {', '.join(batch)}")
        for day in batch:
            done += 1
            _progress(f"[{done}/{total}] Fetching {day} "
                      f"({config.origin}<->{config.destination})...")
            day_fetch = fetch_day(
                client, day, config.origin, config.destination,
                config.outbound_window, config.inbound_window)
            fetched.append(day_fetch)
            status = day_fetch.status.value
            _progress(
                f"[{done}/{total}] {day} -> {status} "
                f"(out={len(day_fetch.outbound)} in={len(day_fetch.inbound)})"
            )

    _progress("Optimising claimable days...")
    day_results = optimise(fetched, config)
    claims = [claim for day_result in day_results for claim in day_result.claims]
    _progress(f"Writing {len(claims)} claim row(s) to {out_csv} and {out_json}...")
    storage.write_claims(claims, out_csv, out_json)
    return summarise(day_results), day_results


def summarise(day_results) -> dict:
    analysed = [d for d in day_results if d.status is FetchStatus.OK]
    not_analysed = [d for d in day_results if d.status is not FetchStatus.OK]
    claimable_days = [d for d in analysed if d.claims]
    return {
        "days_total": len(day_results),
        "analysed": len(analysed),
        "not_analysed": [d.date for d in not_analysed],
        "claimable_days": len(claimable_days),
        "total_claims": sum(len(d.claims) for d in day_results),
        "dates": [d.date for d in day_results],
    }


def _maybe_send_digest(day_results, *, strict: bool, credentials_path: str | None = None) -> int:
    """Send weekly digest. Returns 0 on success/best-effort fail; 1/2 on hard fail."""
    try:
        email_cfg = load_email_config(credentials_path=credentials_path)
    except EmailConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    html, text = render_digest(day_results)
    subject = digest_subject(day_results)
    try:
        send_digest(
            subject, html, text, email_cfg, transport=_digest_transport)
    except Exception as exc:  # noqa: BLE001 - digest is best-effort unless strict
        if strict:
            logging.error("Digest send failed (--digest-strict): %s", exc)
            print(f"Digest send failed: {exc}", file=sys.stderr)
            return 1
        logging.warning("Digest send failed (best-effort): %s", exc)
        print(f"Digest send failed (continuing): {exc}", file=sys.stderr)
        return 0
    _progress(f"Digest sent to {email_cfg.digest_to}")
    return 0


def _run_check_tickets(*, out_dir: Path, ticket_dir: Path) -> int:
    """Standalone ticket gate against existing claims.json (Story 5.3)."""
    _progress(f"Ticket gate: scanning {ticket_dir.resolve()}")
    _progress(f"Claims file: {(out_dir / 'claims.json').resolve()}")
    json_path = out_dir / "claims.json"
    if not json_path.is_file():
        _progress(
            f"ERROR: No claims file at {json_path} - run an assess first "
            f"or pass --out-dir"
        )
        return 2
    try:
        claims = load_claim_dates_from_json(json_path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        _progress(f"ERROR: Cannot read claims from {json_path}: {exc}")
        return 2
    dates = sorted({c.date for c in claims})
    _progress(f"Loaded {len(claims)} claim row(s) covering {len(dates)} date(s)")
    scan = scan_ticket_dir(ticket_dir)
    if scan.missing_directory:
        _progress(f"WARNING: ticket directory does not exist: {ticket_dir}")
    else:
        _progress(
            f"Found {len(scan.valid)} valid ticket file(s), "
            f"{len(scan.invalid)} misnamed"
        )
    result = match_tickets_to_claims(claims, scan)
    report = format_match_errors(result)
    # Success summary on stdout (tests / piping); failures and progress on stderr.
    if result.ok:
        print(report)
        _progress("Ticket gate PASSED - all claim dates have matching tickets.")
        return 0
    print(report, file=sys.stderr)
    _progress("Ticket gate FAILED - fix missing/misnamed tickets before --file.")
    return 1 if gate_blocks_filing(result) else 0


def _run_classify_tickets(*, tickets_root: Path, ocr=None) -> int:
    """OCR-classify ``unclassified/`` into ready_to_claim / rejected (Epic 5b)."""
    layout = tickets_layout(tickets_root)
    layout.ensure()
    root = layout.root.resolve()
    _progress(f"Ticket OCR classify - root: {root}")
    _progress(f"  inbox:     {layout.unclassified}")
    _progress(f"  ready:     {layout.ready_to_claim}")
    _progress(f"  rejected:  {layout.rejected}")
    _progress(f"  claimed:   {layout.claimed}")

    pending = sorted(
        p for p in layout.unclassified.iterdir()
        if p.is_file() and p.suffix.casefold() in {".jpg", ".jpeg", ".png", ".pdf"}
    )
    if not pending:
        _progress(
            "Nothing to do: unclassified/ is empty.\n"
            "  Drop ticket photos/PDFs into that folder, then re-run:\n"
            "    python -m trainline --classify-tickets\n"
            f"  Tip: copy from sample-tickets/ if you want a dry run."
        )
        ready_n = sum(1 for _ in layout.ready_to_claim.glob("*") if _.is_file())
        rejected_n = sum(1 for _ in layout.rejected.glob("*") if _.is_file())
        _progress(
            f"Current inventory - ready_to_claim: {ready_n}, rejected: {rejected_n}"
        )
        return 0

    if ocr is not None:
        engine = ocr
        engine_label = type(ocr).__name__
    else:
        if not ensure_ollama_reachable():
            _progress(
                "ERROR: Ollama is not reachable at http://127.0.0.1:11434\n"
                "  Start Ollama, then: ollama pull qwen2.5vl:7b\n"
                "  ollama create trainline-ticket -f "
                "trainline/adapters/ollama/Modelfile.ticket-reader"
            )
            return 2
        names = list_ollama_models()
        model = OLLAMA_DEFAULT_MODEL
        if model not in names and f"{model}:latest" not in names:
            if OLLAMA_FALLBACK_MODEL in names:
                model = OLLAMA_FALLBACK_MODEL
                _progress(
                    f"Note: '{OLLAMA_DEFAULT_MODEL}' not found — using {model}. "
                    "Create the tuned model with:\n"
                    "  ollama create trainline-ticket -f "
                    "trainline/adapters/ollama/Modelfile.ticket-reader"
                )
            else:
                _progress(
                    f"ERROR: neither '{OLLAMA_DEFAULT_MODEL}' nor "
                    f"'{OLLAMA_FALLBACK_MODEL}' is installed.\n"
                    "  ollama pull qwen2.5vl:7b\n"
                    "  ollama create trainline-ticket -f "
                    "trainline/adapters/ollama/Modelfile.ticket-reader"
                )
                return 2
        engine = OllamaVisionOcrEngine(model=model)
        engine_label = f"ollama:{model}"

    _progress(f"Found {len(pending)} file(s) to classify via {engine_label}...")

    def _on_progress(index, total, path, phase, item):
        if phase == "start":
            _progress(f"[{index}/{total}] reading {path.name}...")
        elif phase == "done" and item is not None:
            label = {
                "ready": "READY",
                "rejected_unreadable": "REJECT unreadable",
                "rejected_route": "REJECT wrong route",
                "rejected_document": "REJECT wrong document",
                "rejected_no_date": "REJECT no journey date",
            }.get(item.outcome, item.outcome)
            detail = f" ({item.detail})" if item.detail else ""
            _progress(
                f"[{index}/{total}] {label}: {path.name} -> {item.destination.name}"
                f"{detail}"
            )

    try:
        summary = classify_unclassified(layout, engine, on_progress=_on_progress)
    except RuntimeError as exc:
        _progress(f"ERROR: {exc}")
        return 2

    _progress(
        f"Done. Classified {len(summary.items)} file(s): "
        f"{summary.ready} ready, {summary.rejected} rejected."
    )
    if summary.rejected:
        _progress(
            "Rejected files need attention under processed/rejected/ "
            "(unreadable image quality, wrong route, or missing journey date)."
        )
        report = layout.rejected / "unreadable_report.txt"
        if report.exists():
            _progress(
                f"Unreadable detail report: {report} "
                "(resolution / lighting / OCR confidence / rotation hints)."
            )
    if summary.ready:
        _progress(
            "Next: python -m trainline --check-tickets "
            "(after an assess has written Results/claims.json)"
        )
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="trainline",
        description=(
            "Late Train Query Engine - compute optimal Delay Repay claims "
            "for GOD<->WAT. Default: last 5 weekdays (last week's work)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m trainline\n"
            "  python -m trainline --days-back 3\n"
            "  python -m trainline --from-date 2026-07-07 --to-date 2026-07-11\n"
            "  python -m trainline --digest\n"
            "  python -m trainline --file --from-date 2026-07-10 --to-date 2026-07-10\n"
        ),
    )
    parser.add_argument("--origin", help="Outbound origin CRS (default GOD)")
    parser.add_argument("--destination", help="Outbound destination CRS (default WAT)")
    parser.add_argument(
        "--days-back", type=int, dest="days_back",
        help=f"Number of weekdays ending yesterday (default {DEFAULT_DAYS_BACK})",
    )
    parser.add_argument(
        "--lookback-days", type=int, dest="lookback_days",
        help="Alias for --days-back",
    )
    parser.add_argument(
        "--from-date", dest="from_date",
        help="ISO start date YYYY-MM-DD (inclusive; weekdays only)",
    )
    parser.add_argument(
        "--to-date", dest="to_date",
        help="ISO end date YYYY-MM-DD (inclusive; default yesterday)",
    )
    parser.add_argument("--batch-size", type=int, dest="batch_size",
                        help="Max days fetched per batch (default 3)")
    parser.add_argument(
        "--no-cancellations", dest="no_cancellations", action="store_true",
        help=(
            "Exclude cancellation-derived claims (next-catchable delay). "
            "By default a cancelled train that has no actual-late alternative "
            "on the same leg is claimed via the next train you could catch."
        ),
    )
    parser.add_argument("--out-dir", default="Results",
                        help="Directory for claims.csv / claims.json")
    parser.add_argument("--cache-dir", default=".hsp-cache",
                        help="On-disk HSP response cache directory")
    parser.add_argument(
        "--credentials-file",
        help="Credentials file (default: HSP_CREDENTIALS_FILE or creds/trainConfig.txt)",
    )
    digest = parser.add_mutually_exclusive_group()
    digest.add_argument(
        "--digest", dest="digest", action="store_true",
        help="Send weekly digest email after a successful assess (FR22)",
    )
    digest.add_argument(
        "--no-digest", dest="no_digest", action="store_true",
        help="Do not send digest even if config send_digest is true",
    )
    parser.add_argument(
        "--digest-strict", dest="digest_strict", action="store_true",
        help="Fail the run if digest SMTP send fails (default: best-effort)",
    )
    parser.add_argument(
        "--ticket-dir", dest="ticket_dir", default=None,
        help=(
            "Ticket scan directory for --check-tickets "
            "(default: tickets/processed/ready_to_claim or legacy ticket/)"
        ),
    )
    parser.add_argument(
        "--tickets-root", dest="tickets_root", default=None,
        help="Root of unclassified/processed/claimed tree (default: tickets/)",
    )
    parser.add_argument(
        "--check-tickets", dest="check_tickets", action="store_true",
        help=(
            "Validate ready_to_claim (or --ticket-dir) against claims.json "
            "in --out-dir and exit (no HSP fetch; FR25)"
        ),
    )
    parser.add_argument(
        "--classify-tickets", dest="classify_tickets", action="store_true",
        help=(
            "Classify tickets/unclassified into processed/ready_to_claim "
            "or processed/rejected via Ollama vision (Epic 5b)"
        ),
    )
    parser.add_argument(
        "--gmail-auth", dest="gmail_auth", action="store_true",
        help=(
            "Run Google OAuth consent and store Gmail API token "
            "(Epic 7; requires ## Gmail API ## in credentials file)"
        ),
    )
    parser.add_argument(
        "--file", dest="auto_file", action="store_true",
        help=(
            "After assess: ticket gate → map → batch submit → audit "
            "(FakeBrowser by default; use --live-submit for Playwright)"
        ),
    )
    parser.add_argument(
        "--live-submit", dest="live_submit", action="store_true",
        help="With --file: use Playwright against SWR (requires playwright + OQ4)",
    )
    parser.add_argument(
        "--audit-path", dest="audit_path", default=None,
        help=f"JSONL filing audit path (default: {DEFAULT_AUDIT_PATH})",
    )
    return parser.parse_args(argv)


def _resolve_browser_session(*, live_submit: bool):
    """Composition-root browser seam (Fake offline; Playwright when live)."""
    if _file_browser_factory is not None:
        return _file_browser_factory()
    if live_submit:
        return PlaywrightBrowserSession(headless=True)
    return FakeBrowserSession()


def _file_claims(
    day_results,
    *,
    ticket_dir: Path,
    tickets_root: Path,
    audit_path: Path,
    live_submit: bool,
) -> tuple[int, dict]:
    """Ticket gate → map → batch submit → move claimed. Returns (exit_code, summary)."""
    claims = [c for day in day_results for c in day.claims]
    file_summary = {
        "claims_found": len(claims),
        "filed": 0,
        "failed": 0,
        "skipped_already_claimed": 0,
        "audit_path": str(audit_path),
        "gate_ok": True,
        "browser": "live" if live_submit else "fake",
    }
    if not claims:
        _progress("No claims to file.")
        return 0, file_summary

    layout = tickets_layout(tickets_root)
    layout.ensure()
    _progress(f"Ticket gate: scanning {ticket_dir.resolve()}")
    scan = scan_ticket_dir(ticket_dir)
    if scan.missing_directory:
        _progress(f"WARNING: ticket directory does not exist: {ticket_dir}")
    result = match_tickets_to_claims(claims, scan)
    report = format_match_errors(result)
    if gate_blocks_filing(result):
        print(report, file=sys.stderr)
        _progress("Ticket gate FAILED - assess output kept; submission skipped.")
        file_summary["gate_ok"] = False
        return 1, file_summary
    print(report)
    _progress("Ticket gate PASSED.")

    before = len(claims)
    claims = filter_claims_not_already_claimed(claims, layout.claimed)
    skipped = before - len(claims)
    file_summary["skipped_already_claimed"] = skipped
    if skipped:
        _progress(f"Skipping {skipped} claim(s) already under claimed/")
    if not claims:
        _progress("Nothing left to file after claimed/ filter.")
        return 0, file_summary

    items = []
    for claim in claims:
        ticket = result.mapping.get(claim.date)
        if ticket is None:
            _progress(f"ERROR: no ticket mapped for {claim.date}")
            file_summary["gate_ok"] = False
            return 1, file_summary
        items.append((claim, map_claim_for_swr(claim), Path(ticket)))

    if not live_submit:
        _progress(
            "Filing via FakeBrowserSession (dry-run / offline). "
            "Pass --live-submit for Playwright against SWR (OQ4)."
        )
    else:
        _progress("Filing via Playwright (live SWR; OQ4 session/2FA still open).")

    session = _resolve_browser_session(live_submit=live_submit)
    batch = submit_all_claims(items, session, audit_path=audit_path)
    file_summary["filed"] = batch.filed
    file_summary["failed"] = batch.failed
    _progress(
        f"Filing done: {batch.filed} filed, {batch.failed} failed "
        f"(audit: {audit_path})"
    )

    moved: set[str] = set()
    for submit_result, (_claim, _fields, ticket) in zip(batch.results, items):
        if not submit_result.ok:
            continue
        key = str(ticket.resolve())
        if key in moved:
            continue
        if not ticket.is_file():
            continue
        dest = move_to_claimed(ticket, layout.claimed)
        moved.add(key)
        _progress(f"Moved ticket -> {dest}")

    exit_code = 1 if batch.failed else 0
    return exit_code, file_summary


def _run_gmail_auth() -> int:
    """One-shot InstalledAppFlow → write token file (Story 7.1)."""
    from trainline.adapters.config import GmailConfigError, load_gmail_config
    from trainline.adapters.gmail import (
        GmailConfig,
        run_auth_flow,
        store_credentials,
    )

    cred_path = os.environ.get("HSP_CREDENTIALS_FILE")
    try:
        cfg = load_gmail_config(credentials_path=cred_path)
    except GmailConfigError as exc:
        _progress(f"ERROR: {exc}")
        return 2
    gmail_cfg = GmailConfig(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        token_path=cfg.token_path,
        digest_to=cfg.digest_to,
    )
    _progress("Opening browser for Google OAuth (Gmail readonly + send)...")
    try:
        creds = run_auth_flow(gmail_cfg)
        store_credentials(creds, gmail_cfg)
    except Exception as exc:
        _progress(f"ERROR: Gmail auth failed: {exc}")
        return 2
    _progress(f"Gmail token saved to {gmail_cfg.token_path}")
    _progress(f"Digest recipient: {gmail_cfg.digest_to}")
    return 0


def main(argv=None) -> int:
    """CLI entry: config → hsp_client → optimise → storage → optional digest (AD-8)."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _configure_cli_logging()

    tickets_root = Path(args.tickets_root) if args.tickets_root else Path("tickets")
    out_dir = Path(args.out_dir)

    if args.classify_tickets:
        return _run_classify_tickets(tickets_root=tickets_root)

    if getattr(args, "gmail_auth", False):
        return _run_gmail_auth()

    ticket_dir = resolve_ticket_scan_dir(
        ticket_dir=args.ticket_dir,
        tickets_root=tickets_root,
    )

    if args.check_tickets:
        return _run_check_tickets(out_dir=out_dir, ticket_dir=ticket_dir)

    if args.days_back is not None and args.lookback_days is not None:
        print("Use only one of --days-back or --lookback-days", file=sys.stderr)
        return 2
    if (args.from_date or args.to_date) and (
            args.days_back is not None or args.lookback_days is not None):
        print(
            "Do not combine --from-date/--to-date with --days-back/--lookback-days",
            file=sys.stderr,
        )
        return 2

    overrides = {}
    for key in ("origin", "destination", "batch_size"):
        value = getattr(args, key)
        if value is not None:
            overrides[key] = value
    days_back = args.days_back if args.days_back is not None else args.lookback_days
    if days_back is not None:
        overrides["lookback_days"] = days_back
    elif not (args.from_date or args.to_date):
        overrides["lookback_days"] = DEFAULT_DAYS_BACK
    if args.to_date:
        overrides["to_date"] = args.to_date
    if args.no_cancellations:
        overrides["enable_cancellation_fallback"] = False
    if args.digest:
        overrides["send_digest"] = True
    if args.no_digest:
        overrides["send_digest"] = False
    if args.ticket_dir is not None:
        overrides["ticket_dir"] = args.ticket_dir
    if args.tickets_root is not None:
        overrides["tickets_root"] = args.tickets_root
    config = make_config(**overrides) if overrides else default_config()
    ticket_dir = resolve_ticket_scan_dir(
        ticket_dir=config.ticket_dir if args.ticket_dir else None,
        tickets_root=config.tickets_root,
    )

    try:
        dates = resolve_run_dates(
            from_date=args.from_date,
            to_date=args.to_date,
            days_back=days_back,
            lookback_days=None if days_back is not None else (
                None if (args.from_date or args.to_date) else DEFAULT_DAYS_BACK
            ),
            today=_today(),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not dates:
        print("No weekdays in the selected range.", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = str(out_dir / "claims.csv")
    out_json = str(out_dir / "claims.json")

    creds_path = args.credentials_file
    if not creds_path and not os.environ.get("HSP_CREDENTIALS_FILE"):
        creds_path = _default_credentials_path()

    _progress(f"Analysing dates: {', '.join(dates)}")
    if creds_path:
        _progress(f"Credentials file: {creds_path}")
    elif os.environ.get("HSP_CREDENTIALS_FILE"):
        _progress(f"Credentials file: {os.environ['HSP_CREDENTIALS_FILE']}")

    summary, day_results = run(
        config, dates, out_csv, out_json,
        cache_dir=args.cache_dir,
        credentials_path=creds_path,
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    if summary["not_analysed"]:
        print("Not analysed (FETCH_FAILED):", ", ".join(summary["not_analysed"]))

    file_rc = 0
    file_summary = None
    if args.auto_file:
        audit_path = Path(args.audit_path) if args.audit_path else (
            out_dir / "filing-audit.jsonl"
        )
        file_rc, file_summary = _file_claims(
            day_results,
            ticket_dir=ticket_dir,
            tickets_root=tickets_root,
            audit_path=audit_path,
            live_submit=bool(args.live_submit),
        )
        print(json.dumps({"filing": file_summary}, indent=2))

    want_digest = config.send_digest and not args.no_digest
    if want_digest:
        digest_rc = _maybe_send_digest(
            day_results, strict=args.digest_strict, credentials_path=creds_path)
        if digest_rc != 0:
            return digest_rc
    return file_rc if args.auto_file else 0


if __name__ == "__main__":
    raise SystemExit(main())
