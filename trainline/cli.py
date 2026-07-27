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
from trainline.adapters.swr_mapping import map_claim_for_swr, ticket_medium_for_path
from trainline.adapters.ticket_gate import (
    filter_claims_not_already_claimed,
    filter_claims_to_ticketed_dates,
    format_match_errors,
    gate_blocks_filing,
    load_claim_dates_from_json,
    load_ticket_meta,
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
    """Clock seam for tests and sign-off (``TRAINLINE_AS_OF=YYYY-MM-DD``)."""
    raw = (os.environ.get("TRAINLINE_AS_OF") or "").strip()
    if raw:
        return date.fromisoformat(raw)
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


_GMAIL_AUTH_HINT = (
    "Gmail digest requires OAuth. Run: python -m trainline --gmail-auth "
    "(needs ## Gmail API ## keys in the credentials file)"
)


class _GmailDigestHeaders:
    """Duck-typed digest headers for ``send_digest`` (Gmail path; AD-2)."""

    def __init__(self, digest_to: str, digest_from: str | None = None) -> None:
        self.digest_to = digest_to
        self.digest_from = digest_from
        self.smtp_user = digest_to
        self.smtp_host = ""
        self.smtp_port = 0
        self.smtp_password = ""


def _try_gmail_digest_transport(credentials_path: str | None):
    """Prefer Gmail API when configured.

    Returns ``(header_config, transport)`` or ``None`` if Gmail is not configured.
    Raises ``GmailAuthError`` when Gmail keys exist but the token is missing/unusable.
    """
    from trainline.adapters.config import GmailConfigError, load_gmail_config
    from trainline.adapters.gmail.auth import GmailConfig, get_credentials
    from trainline.adapters.gmail.client import GmailClient

    try:
        file_cfg = load_gmail_config(credentials_path=credentials_path)
    except GmailConfigError:
        return None

    gmail_cfg = GmailConfig(
        client_id=file_cfg.client_id,
        client_secret=file_cfg.client_secret,
        token_path=file_cfg.token_path,
        digest_to=file_cfg.digest_to,
    )
    creds = get_credentials(gmail_cfg)
    client = GmailClient(creds)

    def transport(msg, _config):
        client.send_message(msg)

    return _GmailDigestHeaders(file_cfg.digest_to), transport


def _maybe_send_digest(day_results, *, strict: bool, credentials_path: str | None = None) -> int:
    """Send weekly digest via Gmail API (preferred) or SMTP fallback.

    Returns 0 on success/best-effort fail; 1/2 on hard fail. Assess/classify
    output is written before this runs — digest failure must not undo that.
    """
    from trainline.adapters.gmail.errors import GmailAuthError

    html, text = render_digest(day_results)
    subject = digest_subject(day_results)

    # Offline test seam: injected transport keeps the SMTP config path (Story 4.3).
    if _digest_transport is not None:
        try:
            email_cfg = load_email_config(credentials_path=credentials_path)
        except EmailConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return _dispatch_digest(
            subject, html, text, email_cfg, _digest_transport, strict=strict)

    try:
        prepared = _try_gmail_digest_transport(credentials_path)
    except GmailAuthError as exc:
        msg = str(exc).strip() or _GMAIL_AUTH_HINT
        if "gmail-auth" not in msg.casefold():
            msg = f"{msg}\n{_GMAIL_AUTH_HINT}"
        if strict:
            logging.error("Digest send failed (--digest-strict): %s", msg)
            print(f"Digest send failed: {msg}", file=sys.stderr)
            return 1
        logging.warning("Digest send failed (best-effort): %s", msg)
        print(f"Digest send failed (continuing): {msg}", file=sys.stderr)
        return 0

    if prepared is not None:
        email_cfg, transport = prepared
        return _dispatch_digest(
            subject, html, text, email_cfg, transport, strict=strict)

    # Legacy SMTP until Gmail is fully adopted (FR35).
    try:
        email_cfg = load_email_config(credentials_path=credentials_path)
    except EmailConfigError as exc:
        print(f"{exc}\n{_GMAIL_AUTH_HINT}", file=sys.stderr)
        return 2
    return _dispatch_digest(
        subject, html, text, email_cfg, None, strict=strict)


def _dispatch_digest(subject, html, text, email_cfg, transport, *, strict: bool) -> int:
    try:
        send_digest(subject, html, text, email_cfg, transport=transport)
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
        "--weekly-ops", dest="weekly_ops", action="store_true",
        help=(
            "Friday/catch-up chain: prior-week assess → classify → file → "
            "digest (FR32–FR34); skips if anchor Friday marker present (FR39)"
        ),
    )
    parser.add_argument(
        "--weekly-status", dest="weekly_status", action="store_true",
        help="Print anchor Friday, prior-week window, and completion marker state",
    )
    parser.add_argument(
        "--weekly-ops-force", dest="weekly_ops_force", action="store_true",
        help="With --weekly-ops: ignore existing completion marker and re-run",
    )
    parser.add_argument(
        "--allow-partial-tickets",
        dest="allow_partial_tickets",
        action="store_true",
        default=True,
        help=(
            "File only claim dates that have tickets; skip the rest "
            "(default for --weekly-ops / --file)"
        ),
    )
    parser.add_argument(
        "--strict-all-tickets",
        dest="allow_partial_tickets",
        action="store_false",
        help=(
            "Require a ticket for every claimable date before filing "
            "(legacy FR25 whole-week gate)"
        ),
    )
    parser.add_argument(
        "--ingest-ticket-mail", dest="ingest_ticket_mail", action="store_true",
        help=(
            "Download ticket photos from Gmail (subject TICKET…) into "
            "tickets/unclassified/ (Epic 8)"
        ),
    )
    parser.add_argument(
        "--ingest-ticket-folder", dest="ingest_ticket_folder", action="store_true",
        help=(
            "Drain tickets/inbox/ images into tickets/unclassified/ "
            "(Syncthing/OneDrive path; Epic 8.3)"
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
        import os

        from trainline.adapters.config import SwrConfigError, load_swr_credentials

        try:
            swr = load_swr_credentials()
        except SwrConfigError as exc:
            raise RuntimeError(str(exc)) from exc
        wait_s = int(os.environ.get("SWR_CAPTCHA_WAIT_SECONDS", "600"))
        # OQ4: never unattended Submit — headed Review + human reCAPTCHA.
        return PlaywrightBrowserSession(
            username=swr.username,
            password=swr.password,
            base_url=swr.base_url,
            headless=False,
            click_submit=False,
            dry_run_to_review=False,
            human_captcha_wait_seconds=wait_s,
        )
    return FakeBrowserSession()


def _claim_lifecycle_path(audit_path: Path) -> Path:
    """Lifecycle store lives alongside the filing audit log (AD-18, AD-19)."""
    return Path(audit_path).parent / "claim-lifecycle.json"


def _record_lifecycle_submissions(audit_path: Path, batch, items) -> None:
    """CLI-only mutation (AD-19): record ``submitted`` for successful SWR files.

    Captcha abandon (``ok=False``) and non-SWR refs (``FAKE-*``,
    ``SUBMITTED-*``) never reach ``normalize_claim_id`` and are skipped.
    """
    from trainline.adapters.claim_lifecycle import LifecycleStore
    from trainline.adapters.gmail.claim_mail import normalize_claim_id

    store: LifecycleStore | None = None
    for submit_result, (claim, _fields, _ticket) in zip(batch.results, items):
        if not submit_result.ok:
            continue
        claim_id = normalize_claim_id(submit_result.swr_reference or "")
        if claim_id is None:
            continue
        if store is None:
            store = LifecycleStore(_claim_lifecycle_path(audit_path))
        store.record_submitted(
            claim_id,
            date=claim.date,
            direction=claim.direction.value,
        )


def _file_claims(
    day_results,
    *,
    ticket_dir: Path,
    tickets_root: Path,
    audit_path: Path,
    live_submit: bool,
    allow_partial_tickets: bool = True,
) -> tuple[int, dict]:
    """Ticket gate → map → batch submit → move claimed. Returns (exit_code, summary).

    Default ``allow_partial_tickets=True``: file only claim dates that have
    tickets; skip the rest (no whole-week FR25 block).
    """
    from trainline.adapters.ticket_gate import claim_date_to_mm_dd

    all_claims = [c for day in day_results for c in day.claims]
    claim_dates = sorted({c.date for c in all_claims})
    claims = list(all_claims)
    file_summary: dict = {
        "claims_found": len(claims),
        "filed": 0,
        "failed": 0,
        "skipped_already_claimed": 0,
        "skipped_no_ticket": [],
        "newly_filed": [],
        "surplus_tickets": [],
        "audit_path": str(audit_path),
        "gate_ok": True,
        "browser": "live" if live_submit else "fake",
    }
    layout = tickets_layout(tickets_root)
    layout.ensure()

    _progress(f"Ticket gate: scanning {ticket_dir.resolve()}")
    scan = scan_ticket_dir(ticket_dir)
    if scan.missing_directory:
        _progress(f"WARNING: ticket directory does not exist: {ticket_dir}")

    # Surplus: ready tickets whose MM-DD has no claimable delay that day
    claim_mm = {claim_date_to_mm_dd(d) for d in claim_dates}
    surplus = []
    for ticket in scan.valid:
        if ticket.mm_dd not in claim_mm:
            year = (claim_dates[0][:4] if claim_dates else "2026")
            surplus.append(
                {
                    "date": f"{year}-{ticket.mm_dd}",
                    "path": str(ticket.path),
                    "mm_dd": ticket.mm_dd,
                }
            )
    # Prefer ISO year from window if we can map mm-dd
    for row in surplus:
        mm, dd = row["mm_dd"].split("-")
        matched = next(
            (d for d in claim_dates if d[5:] == f"{mm}-{dd}"),
            None,
        )
        # No claim that day — use any claim year in window or leave stamped
        if claim_dates:
            row["date"] = f"{claim_dates[0][:4]}-{mm}-{dd}"
        if matched:
            row["date"] = matched
    file_summary["surplus_tickets"] = surplus

    if not claims:
        _progress("No claims to file.")
        return 0, file_summary

    before = len(claims)
    claims = filter_claims_not_already_claimed(claims, layout.claimed)
    skipped = before - len(claims)
    file_summary["skipped_already_claimed"] = skipped
    if skipped:
        _progress(f"Skipping {skipped} claim(s) already under claimed/")
    if not claims:
        _progress("Nothing left to file after claimed/ filter.")
        return 0, file_summary

    if allow_partial_tickets:
        claims, dropped = filter_claims_to_ticketed_dates(claims, scan)
        file_summary["skipped_no_ticket"] = list(dropped)
        if dropped:
            _progress(
                "Partial tickets: skipping claim date(s) without files: "
                + ", ".join(dropped)
            )
        if not claims:
            _progress(
                "No ticketed claims to file this run — continuing to ops email."
            )
            return 0, file_summary
    else:
        # Strict: every claim date needs a ticket
        result = match_tickets_to_claims(claims, scan)
        if gate_blocks_filing(result):
            print(format_match_errors(result), file=sys.stderr)
            _progress("Ticket gate FAILED - assess output kept; submission skipped.")
            file_summary["gate_ok"] = False
            file_summary["skipped_no_ticket"] = list(result.missing_dates)
            return 1, file_summary

    result = match_tickets_to_claims(claims, scan)
    report = format_match_errors(result)
    if gate_blocks_filing(result):
        print(report, file=sys.stderr)
        _progress("Ticket gate FAILED - assess output kept; submission skipped.")
        file_summary["gate_ok"] = False
        return 1, file_summary
    print(report)
    _progress("Ticket gate PASSED.")

    from trainline.adapters.config import load_ticket_form_defaults

    ticket_defaults = load_ticket_form_defaults()
    if live_submit and (
        not ticket_defaults.ticket_price or not ticket_defaults.ticket_reference
    ):
        # Sidecar from classify may still supply per-ticket values below.
        pass

    items = []
    for claim in claims:
        ticket = result.mapping.get(claim.date)
        if ticket is None:
            _progress(f"ERROR: no ticket mapped for {claim.date}")
            file_summary["gate_ok"] = False
            return 1, file_summary
        meta = load_ticket_meta(ticket)
        price = meta.get("ticket_price") or ticket_defaults.ticket_price
        reference = meta.get("ticket_reference") or ticket_defaults.ticket_reference
        if live_submit and (not price or not reference):
            _progress(
                f"ERROR: live submit needs ticket_price and ticket_reference for "
                f"{ticket.name} (OCR sidecar or SWR_TICKET_PRICE / "
                f"SWR_TICKET_REFERENCE / ## SWR Delay Repay ##)."
            )
            file_summary["gate_ok"] = False
            return 1, file_summary
        # Booking confirmation PDFs are e-tickets; paper photos stay Paper.
        ticket_path = Path(ticket)
        items.append(
            (
                claim,
                map_claim_for_swr(
                    claim,
                    ticket_price=price,
                    ticket_reference=reference,
                    ticket_medium=ticket_medium_for_path(ticket_path),
                ),
                ticket_path,
            )
        )

    if not live_submit:
        _progress(
            "Filing via FakeBrowserSession (dry-run / offline). "
            "Pass --live-submit for Playwright against SWR "
            "(human reCAPTCHA gate; see OQ4)."
        )
    else:
        _progress(
            "Filing via Playwright (live SWR). "
            "Auto-fill to Review; human solves reCAPTCHA + Submit (OQ4)."
        )

    session = _resolve_browser_session(live_submit=live_submit)
    batch = submit_all_claims(items, session, audit_path=audit_path)
    file_summary["filed"] = batch.filed
    file_summary["failed"] = batch.failed
    newly = []
    for submit_result, (claim, _fields, ticket) in zip(batch.results, items):
        newly.append(
            {
                "date": claim.date,
                "direction": claim.direction.value,
                "outcome": "filed" if submit_result.ok else "failed",
                "reference": submit_result.swr_reference,
                "ticket": ticket.name,
            }
        )
    file_summary["newly_filed"] = newly
    _record_lifecycle_submissions(audit_path, batch, items)
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


def _weekly_state_dir(out_dir: Path) -> Path:
    return Path(out_dir) / "weekly"


def _print_weekly_status(*, out_dir: Path, as_of: date | None = None) -> int:
    """Print window + marker for Task Scheduler verification (FR32/FR33/FR39)."""
    from trainline.adapters.schedule_window import anchor_friday, prior_working_week
    from trainline.adapters.weekly_marker import is_complete, marker_path

    as_of = as_of or _today()
    anchor = anchor_friday(as_of)
    start, end = prior_working_week(as_of)
    state = _weekly_state_dir(out_dir)
    done = is_complete(state, anchor)
    payload = {
        "as_of": as_of.isoformat(),
        "anchor_friday": anchor.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "marker_path": str(marker_path(state, anchor)),
        "complete": done,
    }
    print(json.dumps(payload, indent=2))
    _progress(
        f"Weekly status: anchor {anchor.isoformat()} window "
        f"{start.isoformat()}..{end.isoformat()} complete={done}"
    )
    return 0


def _run_weekly_assess(
    *,
    dates: list[str],
    out_dir: Path,
    cache_dir: str,
    credentials_path: str | None,
    config,
) -> tuple[int, list]:
    """Assess prior-week dates; returns (exit_code, day_results)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = str(out_dir / "claims.csv")
    out_json = str(out_dir / "claims.json")
    _progress(f"Weekly assess dates: {', '.join(dates)}")
    summary, day_results = run(
        config,
        dates,
        out_csv,
        out_json,
        cache_dir=cache_dir,
        credentials_path=credentials_path,
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    return 0, day_results


def _run_weekly_classify(*, tickets_root: Path) -> int:
    return _run_classify_tickets(tickets_root=tickets_root)


def _run_weekly_file(
    *,
    day_results,
    ticket_dir: Path,
    tickets_root: Path,
    out_dir: Path,
    live_submit: bool,
    audit_path: Path | None,
    allow_partial_tickets: bool = True,
) -> tuple[int, dict]:
    audit = audit_path or (Path(out_dir) / "filing-audit.jsonl")
    file_rc, file_summary = _file_claims(
        day_results,
        ticket_dir=ticket_dir,
        tickets_root=tickets_root,
        audit_path=audit,
        live_submit=live_submit,
        allow_partial_tickets=allow_partial_tickets,
    )
    print(json.dumps({"filing": file_summary}, indent=2))
    return file_rc, file_summary


def _claimable_rows_for_ops(day_results) -> list[dict]:
    from trainline.adapters.notification import BAND_LABEL
    from trainline.engine.models import FetchStatus

    rows = []
    for day in day_results:
        if day.status is not FetchStatus.OK:
            continue
        for c in day.claims:
            rows.append(
                {
                    "date": c.date,
                    "direction": c.direction.value,
                    "band": BAND_LABEL[c.band],
                    "route": f"{c.origin}->{c.destination}",
                    "delay": c.delay,
                }
            )
    return rows


def _run_weekly_ops_email(
    *,
    day_results,
    credentials_path: str | None,
    strict: bool,
    filing_summary: dict | None = None,
    anchor_friday: str | None = None,
) -> int:
    """Send ops email last (FR34/FR36 Table 1). Table 2 deferred."""
    from trainline.adapters.ops_email import ops_email_subject, render_ops_email

    filing_summary = filing_summary or {}
    claimable = _claimable_rows_for_ops(day_results)
    skipped = filing_summary.get("skipped_no_ticket") or []
    if isinstance(skipped, int):
        skipped = []
    table1 = {
        "claimable": claimable,
        "newly_filed": list(filing_summary.get("newly_filed") or []),
        "skipped_no_ticket": list(skipped),
        "surplus_tickets": list(filing_summary.get("surplus_tickets") or []),
        "rejections": list(filing_summary.get("rejections") or []),
    }
    anchor = anchor_friday or "unknown"
    html, text = render_ops_email(table1=table1, table2=None, anchor_friday=anchor)
    subject = ops_email_subject(
        anchor_friday=anchor,
        filed=int(filing_summary.get("filed") or 0),
        claimable=len(claimable),
    )

    # Dry / sandbox: write email to disk instead of sending (non-impactful).
    sink = (os.environ.get("TRAINLINE_OPS_EMAIL_FILE") or "").strip()
    if sink:
        path = Path(sink)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"Subject: {subject}\n\n{text}\n\n--- HTML ---\n{html}\n",
            encoding="utf-8",
        )
        _progress(f"Ops email written to {path} (TRAINLINE_OPS_EMAIL_FILE)")
        return 0

    # Reuse digest transport path with pre-rendered body
    from trainline.adapters.config import EmailConfigError, load_email_config

    try:
        prepared = _try_gmail_digest_transport(credentials_path)
        if prepared is not None:
            gmail_headers, transport = prepared
            send_digest(subject, html, text, gmail_headers, transport=transport)
            _progress(f"Ops email sent to {gmail_headers.digest_to}")
            return 0
        email_cfg = load_email_config(credentials_path=credentials_path)
        send_digest(subject, html, text, email_cfg)
        _progress(f"Ops email sent to {email_cfg.digest_to}")
        return 0
    except EmailConfigError as exc:
        _progress(f"Ops email skipped: {exc}")
        return 1 if strict else 0
    except Exception as exc:
        _progress(f"Ops email failed: {exc}")
        return 1 if strict else 0


def _ticket_drop_hash_path(out_dir: Path) -> Path:
    return Path(out_dir) / "ticket-drop-hashes.json"


def _is_insufficient_gmail_scope(exc: BaseException) -> bool:
    msg = str(exc).casefold()
    return (
        "insufficient" in msg
        or "authentication scopes" in msg
        or "403" in msg and "permission" in msg
    )


def _ingest_from_gmail_client(
    client,
    *,
    dest_dir: Path,
    hash_store_path: Path,
    subject_prefix: str = "TICKET",
    label: str | None = None,
    ingested_label: str = "trainline-ticket-ingested",
    presence_roots: list[Path] | None = None,
) -> int:
    """Save Gmail ticket attachments into ``dest_dir`` (composition helper).

    Label/modify is best-effort: missing ``gmail.modify`` must not block
    downloads (hash store still dedups). Re-auth restores label idempotency.
    Also ingests ``SWR Booking Confirmation`` PDFs (Updates category).
    """
    from trainline.adapters.gmail.errors import GmailError
    from trainline.adapters.gmail.ticket_mail import (
        build_booking_confirmation_mail_query,
        build_ticket_mail_query,
        extract_image_attachments,
        message_subject,
        subject_matches_booking_confirmation,
        subject_matches_ticket_prefix,
    )
    from trainline.adapters.ticket_drop import DropHashStore, unique_drop_path

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    roots = [Path(p) for p in (presence_roots or [dest_dir])]
    store = DropHashStore(hash_store_path)

    ingested_id: str | None = None
    try:
        ingested_id = client.ensure_label_id(ingested_label)
    except GmailError as exc:
        if not _is_insufficient_gmail_scope(exc):
            raise
        _progress(
            "WARNING: cannot create/read Gmail labels (need gmail.modify). "
            "Saving attachments anyway; re-run: python -m trainline --gmail-auth"
        )

    def _file_message(mid: str) -> None:
        """Mark ingested + archive out of inbox (remove INBOX/UNREAD)."""
        if ingested_id is None:
            _progress(
                f"WARNING: cannot file message {mid} (no label id / scopes). "
                "Re-run: python -m trainline --gmail-auth"
            )
            return
        try:
            client.modify_message(
                mid,
                add_label_ids=[ingested_id],
                remove_label_ids=["INBOX", "UNREAD"],
            )
        except GmailError as exc:
            if not _is_insufficient_gmail_scope(exc):
                raise
            _progress(
                "WARNING: could not file message out of inbox "
                f"({mid}). Re-run: python -m trainline --gmail-auth"
            )

    def _save_hits(
        hits: list,
        *,
        accept_subject,
        query_label: str,
    ) -> tuple[int, int, int]:
        saved = duplicates = skipped = 0
        _progress(f"{query_label}: {len(hits)} message(s)")
        for hit in hits:
            mid = hit.get("id")
            if not mid:
                continue
            msg = client.get_message(mid)
            subject = message_subject(msg)
            if not accept_subject(subject):
                skipped += 1
                _progress(
                    f"Skipping non-matching subject ({mid}): {subject!r}"
                )
                continue
            refs = extract_image_attachments(msg)
            if not refs:
                skipped += 1
                _file_message(mid)
                continue
            for ref in refs:
                data = client.get_attachment(mid, ref.attachment_id)
                if not data:
                    skipped += 1
                    continue
                path = unique_drop_path(
                    dest_dir,
                    data,
                    ref.filename,
                    store=store,
                    presence_roots=roots,
                )
                if path is None:
                    duplicates += 1
                    continue
                path.write_bytes(data)
                saved += 1
                _progress(f"Saved ticket attachment -> {path}")
            _file_message(mid)
        return saved, duplicates, skipped

    ticket_query = build_ticket_mail_query(
        subject_prefix=subject_prefix,
        label=label,
        ingested_label=ingested_label,
    )
    _progress(f"Ticket mail query: {ticket_query}")
    ticket_hits = client.search_messages(ticket_query, max_results=100)

    def _accept_ticket(subject: str) -> bool:
        if label is not None:
            return True
        return subject_matches_ticket_prefix(subject, prefix=subject_prefix)

    saved, duplicates, skipped = _save_hits(
        ticket_hits,
        accept_subject=_accept_ticket,
        query_label="Primary TICKET mail",
    )

    booking_query = build_booking_confirmation_mail_query()
    _progress(f"Booking confirmation query: {booking_query}")
    booking_hits = client.search_messages(booking_query, max_results=50)
    b_saved, b_dupes, b_skipped = _save_hits(
        booking_hits,
        accept_subject=subject_matches_booking_confirmation,
        query_label="SWR booking confirmation",
    )
    saved += b_saved
    duplicates += b_dupes
    skipped += b_skipped

    _progress(
        f"Ticket mail ingest: saved={saved} duplicates={duplicates} skipped={skipped}"
    )
    return 0


def _run_ingest_ticket_mail(
    *,
    tickets_root: Path,
    out_dir: Path,
    credentials_path: str | None,
) -> int:
    """CLI entry: Gmail → tickets/unclassified/ (Epic 8.1)."""
    from trainline.adapters.config import GmailConfigError, load_gmail_config
    from trainline.adapters.gmail import GmailClient, GmailConfig, get_credentials
    from trainline.adapters.gmail.errors import GmailAuthError, GmailError

    layout = tickets_layout(tickets_root)
    layout.ensure()
    try:
        file_cfg = load_gmail_config(credentials_path=credentials_path)
    except GmailConfigError as exc:
        _progress(f"ERROR: {exc}")
        _progress(
            "Hint: add ## Gmail API ## keys, then: python -m trainline --gmail-auth"
        )
        return 2
    gmail_cfg = GmailConfig(
        client_id=file_cfg.client_id,
        client_secret=file_cfg.client_secret,
        token_path=file_cfg.token_path,
        digest_to=file_cfg.digest_to,
    )
    try:
        from trainline.adapters.gmail.auth import token_missing_required_scopes

        creds = get_credentials(gmail_cfg)
        if token_missing_required_scopes(getattr(creds, "scopes", None)):
            _progress(
                "WARNING: Gmail token scopes incomplete (need gmail.modify). "
                "Ingest will download without labeling until you re-auth: "
                "python -m trainline --gmail-auth"
            )
        client = GmailClient(creds)
        return _ingest_from_gmail_client(
            client,
            dest_dir=layout.unclassified,
            hash_store_path=_ticket_drop_hash_path(out_dir),
            subject_prefix=os.environ.get("TICKET_MAIL_SUBJECT_PREFIX", "TICKET"),
            label=(os.environ.get("TICKET_MAIL_LABEL") or "").strip() or None,
            ingested_label=os.environ.get(
                "TICKET_MAIL_INGESTED_LABEL", "trainline-ticket-ingested"
            ),
            presence_roots=[
                layout.unclassified,
                layout.ready_to_claim,
                layout.rejected,
                layout.claimed,
            ],
        )
    except GmailAuthError as exc:
        _progress(f"ERROR: {exc}")
        _progress(
            "If you just upgraded scopes, re-run: python -m trainline --gmail-auth"
        )
        return 2
    except GmailError as exc:
        msg = str(exc)
        _progress(f"ERROR: Gmail ingest failed: {msg}")
        if "insufficient" in msg.casefold() or "403" in msg:
            _progress(
                "Scopes may need gmail.modify — run: python -m trainline --gmail-auth"
            )
        return 2


def _run_ingest_ticket_folder(
    *,
    tickets_root: Path,
    out_dir: Path,
) -> int:
    """Drain tickets/inbox → unclassified (Epic 8.3)."""
    from trainline.adapters.ticket_drop import ingest_folder_images

    layout = tickets_layout(tickets_root)
    layout.ensure()
    summary = ingest_folder_images(
        inbox_dir=layout.inbox,
        dest_dir=layout.unclassified,
        processed_dir=layout.inbox_processed,
        hash_store_path=_ticket_drop_hash_path(out_dir),
    )
    _progress(
        f"Folder ingest: saved={summary.saved} duplicates={summary.duplicates} "
        f"skipped={summary.skipped}"
    )
    return 0


def _mark_weekly_complete(state_dir: Path, anchor: date) -> None:
    from trainline.adapters.weekly_marker import mark_complete

    path = mark_complete(state_dir, anchor)
    _progress(f"Weekly marker written: {path}")


def _run_weekly_ops(
    *,
    out_dir: Path,
    tickets_root: Path,
    ticket_dir: Path,
    cache_dir: str,
    credentials_path: str | None,
    live_submit: bool,
    force: bool,
    digest_strict: bool,
    audit_path: Path | None = None,
    allow_partial_tickets: bool = True,
) -> int:
    """Composition root for Friday / catch-up weekly chain (FR32–FR34, FR39)."""
    from trainline.adapters.schedule_window import anchor_friday, prior_working_week
    from trainline.adapters.weekly_marker import is_complete

    as_of = _today()
    anchor = anchor_friday(as_of)
    start, end = prior_working_week(as_of)
    dates = _weekdays_inclusive(start, end)
    state_dir = _weekly_state_dir(out_dir)

    _progress(
        f"Weekly ops: as_of={as_of.isoformat()} anchor={anchor.isoformat()} "
        f"window={start.isoformat()}..{end.isoformat()}"
    )

    if not force and is_complete(state_dir, anchor):
        _progress(
            f"Already complete for anchor {anchor.isoformat()} — skipping (FR39). "
            "Use --weekly-ops-force to re-run."
        )
        return 0

    config = default_config()
    # Force digest on for the weekly chain (ops email last).
    from dataclasses import replace

    config = replace(config, send_digest=True)

    if (os.environ.get("TRAINLINE_SKIP_TICKET_INGEST") or "").strip() in {
        "1",
        "true",
        "yes",
    }:
        _progress("Skipping ticket-mail ingest (TRAINLINE_SKIP_TICKET_INGEST)")
    else:
        ingest_rc = _run_ingest_ticket_mail(
            tickets_root=tickets_root,
            out_dir=out_dir,
            credentials_path=credentials_path,
        )
        if ingest_rc != 0:
            _progress("Weekly ops: ticket-mail ingest failed — not marking complete")
            return ingest_rc

    assess_rc, day_results = _run_weekly_assess(
        dates=dates,
        out_dir=out_dir,
        cache_dir=cache_dir,
        credentials_path=credentials_path,
        config=config,
    )
    if assess_rc != 0:
        return assess_rc

    classify_rc = _run_weekly_classify(tickets_root=tickets_root)
    if classify_rc != 0:
        _progress("Weekly ops: classify failed — not marking complete")
        return classify_rc

    file_rc, file_summary = _run_weekly_file(
        day_results=day_results,
        ticket_dir=ticket_dir,
        tickets_root=tickets_root,
        out_dir=out_dir,
        live_submit=live_submit,
        audit_path=audit_path,
        allow_partial_tickets=allow_partial_tickets,
    )
    if file_rc != 0:
        _progress("Weekly ops: file step failed — not marking complete")
        return file_rc

    email_rc = _run_weekly_ops_email(
        day_results=day_results,
        credentials_path=credentials_path,
        strict=digest_strict,
        filing_summary=file_summary,
        anchor_friday=anchor.isoformat(),
    )
    if email_rc != 0:
        _progress("Weekly ops: email failed — not marking complete")
        return email_rc

    _mark_weekly_complete(state_dir, anchor)
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

    if getattr(args, "weekly_status", False):
        return _print_weekly_status(out_dir=out_dir)

    creds_path_early = args.credentials_file
    if not creds_path_early and not os.environ.get("HSP_CREDENTIALS_FILE"):
        creds_path_early = _default_credentials_path()

    if getattr(args, "ingest_ticket_mail", False):
        return _run_ingest_ticket_mail(
            tickets_root=tickets_root,
            out_dir=out_dir,
            credentials_path=creds_path_early,
        )

    if getattr(args, "ingest_ticket_folder", False):
        return _run_ingest_ticket_folder(
            tickets_root=tickets_root,
            out_dir=out_dir,
        )

    ticket_dir = resolve_ticket_scan_dir(
        ticket_dir=args.ticket_dir,
        tickets_root=tickets_root,
    )

    if getattr(args, "weekly_ops", False):
        audit_path = Path(args.audit_path) if args.audit_path else None
        return _run_weekly_ops(
            out_dir=out_dir,
            tickets_root=tickets_root,
            ticket_dir=ticket_dir,
            cache_dir=args.cache_dir,
            credentials_path=creds_path_early,
            live_submit=bool(args.live_submit),
            force=bool(getattr(args, "weekly_ops_force", False)),
            digest_strict=bool(args.digest_strict),
            audit_path=audit_path,
            allow_partial_tickets=bool(
                getattr(args, "allow_partial_tickets", False)
            ),
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
            allow_partial_tickets=bool(
                getattr(args, "allow_partial_tickets", False)
            ),
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
