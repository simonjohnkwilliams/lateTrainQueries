"""Composition root (AD-8) - the only MVP orchestrator.

Wires config -> hsp_client -> engine.optimise -> storage and nothing else
orchestrates. A future Lambda handler would be a second composition root calling
the same ``engine.optimise``; orchestration never moves into the engine.

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
from trainline.adapters.config import default_config, load_hsp_credentials, make_config
from trainline.adapters.hsp_client import HspClient, fetch_day
from trainline.engine.models import FetchStatus
from trainline.engine.optimiser import optimise

# MVP default: one working week of weekday analysis ending yesterday.
DEFAULT_DAYS_BACK = 5


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
    """User-visible progress on stderr (keeps stdout free for the JSON summary)."""
    print(msg, file=sys.stderr, flush=True)


def run(config, dates, out_csv, out_json, *, client=None, session=None,
        cache_dir=None, credentials_path=None):
    """Run the pipeline end-to-end and write CSV + JSON claim files."""
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
    return summarise(day_results)


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
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """CLI entry: config → hsp_client → optimise → storage (AD-8)."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])

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
    # Persist chosen lookback on config for batching summary clarity
    days_back = args.days_back if args.days_back is not None else args.lookback_days
    if days_back is not None:
        overrides["lookback_days"] = days_back
    elif not (args.from_date or args.to_date):
        overrides["lookback_days"] = DEFAULT_DAYS_BACK
    if args.to_date:
        overrides["to_date"] = args.to_date
    if args.no_cancellations:
        overrides["enable_cancellation_fallback"] = False
    config = make_config(**overrides) if overrides else default_config()

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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    _progress(f"Analysing dates: {', '.join(dates)}")
    if creds_path:
        _progress(f"Credentials file: {creds_path}")
    elif os.environ.get("HSP_CREDENTIALS_FILE"):
        _progress(f"Credentials file: {os.environ['HSP_CREDENTIALS_FILE']}")

    summary = run(
        config, dates, out_csv, out_json,
        cache_dir=args.cache_dir,
        credentials_path=creds_path,
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")
    if summary["not_analysed"]:
        print("Not analysed (FETCH_FAILED):", ", ".join(summary["not_analysed"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
