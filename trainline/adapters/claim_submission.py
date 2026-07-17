"""Claim submission adapter — SWR Delay Repay filing (AD-15, FR26–FR29).

Owns browser fill/submit and the append-only filing audit log. Injectable
``BrowserSession`` for offline tests (NFR8). May import ``engine.models`` only
among trainline packages (AD-2) — mapping is applied by the composition root.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from trainline.engine.models import Claim

DEFAULT_AUDIT_PATH = Path("Results") / "filing-audit.jsonl"
SWR_DELAY_REPAY_URL = "https://delayrepay.southwesternrailway.com/"


class MappedFormFields(Protocol):
    """Structural form payload (``SwrFormFields`` or any duck type — AD-2)."""

    journey_date: str
    origin_station: str
    destination_station: str
    scheduled_departure: str
    scheduled_arrival: str
    actual_arrival: str
    delay_reason: str
    raw_reason_code: str | None


@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    claim_date: str
    direction: str
    swr_reference: str | None = None
    error: str | None = None
    raw_reason_code: str | None = None


@dataclass(frozen=True)
class BatchResult:
    results: tuple[SubmitResult, ...] = ()
    audit_path: Path | None = None

    @property
    def filed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


class BrowserSession(Protocol):
    """Injectable browser seam for offline / live submission."""

    def submit_delay_repay(
        self,
        fields: MappedFormFields,
        ticket_path: Path,
    ) -> str:
        """Fill form, upload ticket, submit. Return SWR confirmation/reference."""
        ...


@dataclass
class FakeBrowserSession:
    """Offline stub: records fills; returns a fake reference (NFR8)."""

    fills: list[dict] = field(default_factory=list)
    fail_dates: set[str] = field(default_factory=set)
    next_ref: int = 1

    def submit_delay_repay(
        self,
        fields: MappedFormFields,
        ticket_path: Path,
    ) -> str:
        if fields.journey_date in self.fail_dates:
            raise RuntimeError(f"fake submit failure for {fields.journey_date}")
        if not Path(ticket_path).is_file():
            raise FileNotFoundError(f"ticket not found: {ticket_path}")
        ref = f"FAKE-SWR-{self.next_ref:04d}"
        self.next_ref += 1
        self.fills.append({
            "journey_date": fields.journey_date,
            "origin_station": fields.origin_station,
            "destination_station": fields.destination_station,
            "scheduled_departure": fields.scheduled_departure,
            "scheduled_arrival": fields.scheduled_arrival,
            "actual_arrival": fields.actual_arrival,
            "delay_reason": fields.delay_reason,
            "ticket_path": str(ticket_path),
            "swr_reference": ref,
        })
        return ref


@dataclass(frozen=True)
class PlaywrightBrowserSession:
    """Live Playwright session (Story 6.2). Selectors are placeholders for OQ4.

    Instantiation requires ``playwright`` installed. Offline tests must use
    ``FakeBrowserSession`` instead.
    """

    headless: bool = True
    base_url: str = SWR_DELAY_REPAY_URL

    def submit_delay_repay(
        self,
        fields: MappedFormFields,
        ticket_path: Path,
    ) -> str:
        from playwright.sync_api import sync_playwright

        ticket_path = Path(ticket_path)
        if not ticket_path.is_file():
            raise FileNotFoundError(f"ticket not found: {ticket_path}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                page = browser.new_page()
                page.goto(self.base_url, wait_until="domcontentloaded")
                # Placeholder selectors — refine against live form (OQ3/OQ4).
                # Prefer role/label queries; fall back to common name attrs.
                _fill_if_present(page, [
                    'input[name="journeyDate"]',
                    'input[name="journey_date"]',
                    '#journeyDate',
                ], fields.journey_date)
                _fill_if_present(page, [
                    'input[name="origin"]',
                    'input[name="fromStation"]',
                    '#origin',
                ], fields.origin_station)
                _fill_if_present(page, [
                    'input[name="destination"]',
                    'input[name="toStation"]',
                    '#destination',
                ], fields.destination_station)
                _fill_if_present(page, [
                    'input[name="scheduledDeparture"]',
                    'input[name="scheduled_departure"]',
                ], fields.scheduled_departure)
                _fill_if_present(page, [
                    'input[name="scheduledArrival"]',
                    'input[name="scheduled_arrival"]',
                ], fields.scheduled_arrival)
                _fill_if_present(page, [
                    'input[name="actualArrival"]',
                    'input[name="actual_arrival"]',
                ], fields.actual_arrival)
                _select_if_present(page, [
                    'select[name="delayReason"]',
                    'select[name="delay_reason"]',
                ], fields.delay_reason)
                _upload_if_present(page, [
                    'input[type="file"]',
                    'input[name="ticket"]',
                ], ticket_path)
                # Do not auto-click Submit on live until OQ4 session/2FA is resolved;
                # return a marker that the form was filled.
                return f"FILLED-{fields.journey_date}"
            finally:
                browser.close()


def _fill_if_present(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.fill(value)
            return True
    return False


def _select_if_present(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            try:
                loc.first.select_option(label=value)
            except Exception:
                loc.first.select_option(value=value)
            return True
    return False


def _upload_if_present(page, selectors: list[str], path: Path) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.set_input_files(str(path))
            return True
    return False


def append_audit_entry(audit_path: Path, entry: dict) -> None:
    """Append one JSON object line to the audit log (NFR10)."""
    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def submit_claim(
    claim: Claim,
    fields: MappedFormFields,
    ticket_path: Path,
    session: BrowserSession,
    *,
    audit_path: Path | None = None,
    now: datetime | None = None,
) -> SubmitResult:
    """Submit one claim via ``session``; always write an audit line when path set."""
    when = now or datetime.now(timezone.utc)
    ticket_path = Path(ticket_path)
    try:
        ref = session.submit_delay_repay(fields, ticket_path)
        result = SubmitResult(
            ok=True,
            claim_date=claim.date,
            direction=claim.direction.value,
            swr_reference=ref,
            raw_reason_code=fields.raw_reason_code,
        )
    except Exception as exc:
        result = SubmitResult(
            ok=False,
            claim_date=claim.date,
            direction=claim.direction.value,
            error=str(exc),
            raw_reason_code=fields.raw_reason_code,
        )
    if audit_path is not None:
        append_audit_entry(Path(audit_path), {
            "timestamp": when.isoformat(),
            "date": result.claim_date,
            "direction": result.direction,
            "outcome": "success" if result.ok else "failure",
            "swr_reference": result.swr_reference,
            "raw_reason_code": result.raw_reason_code,
            "error": result.error,
        })
    return result


def submit_all_claims(
    items: list[tuple[Claim, MappedFormFields, Path]],
    session: BrowserSession,
    *,
    audit_path: Path | str | None = None,
    now: datetime | None = None,
) -> BatchResult:
    """Submit every item; one failure does not stop the rest (FR26, FR29)."""
    path = Path(audit_path) if audit_path is not None else DEFAULT_AUDIT_PATH
    results: list[SubmitResult] = []
    for claim, fields, ticket in items:
        results.append(
            submit_claim(
                claim,
                fields,
                ticket,
                session,
                audit_path=path,
                now=now,
            )
        )
    return BatchResult(results=tuple(results), audit_path=path)
