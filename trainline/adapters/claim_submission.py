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
    """Offline stub: records wizard fills; returns a fake reference (NFR8)."""

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
            "delay_band_label": getattr(
                fields, "delay_band_label", "Between 15 - 29 minutes"
            ),
            "ticket_path": str(ticket_path),
            "ticket_reference": getattr(fields, "ticket_reference", ""),
            "ticket_price": getattr(fields, "ticket_price", ""),
            "wizard_steps": (
                "login", "journey", "ticket", "compensation", "review", "submit"
            ),
            "swr_reference": ref,
        })
        return ref


@dataclass
class PlaywrightBrowserSession:
    """Live SWR Delay Repay wizard (login → Review → optional Submit).

    Selectors match the Angular Material portal captured 2026-07-17
    (``tests/fixtures/swr_portal_contract.py``). Credentials are injected by
    the composition root (AD-2 — does not import ``config``).
    """

    username: str
    password: str
    headless: bool = True
    base_url: str = SWR_DELAY_REPAY_URL
    click_submit: bool = True
    # When False, stop on Review and return REVIEW-READY-… (dry probe).
    dry_run_to_review: bool = False
    # When >0, leave Review open for a human to solve reCAPTCHA + Submit
    # (headed recommended). Polls until confirmation or timeout.
    human_captcha_wait_seconds: int = 0

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
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                return _run_swr_wizard(
                    page,
                    fields=fields,
                    ticket_path=ticket_path,
                    username=self.username,
                    password=self.password,
                    base_url=self.base_url.rstrip("/"),
                    click_submit=(
                        self.click_submit
                        and not self.dry_run_to_review
                        and self.human_captcha_wait_seconds <= 0
                    ),
                    dry_run_to_review=self.dry_run_to_review,
                    human_captcha_wait_seconds=self.human_captcha_wait_seconds,
                )
            finally:
                browser.close()


def _attr(fields: MappedFormFields, name: str, default: str) -> str:
    return str(getattr(fields, name, default) or default)


def _floor_leaving_slot(hhmm: str) -> str:
    hour_s, min_s = hhmm.strip().split(":", 1)
    total = int(hour_s) * 60 + int(min_s)
    slot = (total // 15) * 15 % 1440
    return f"{slot // 60:02d}:{slot % 60:02d}"


def _fill_autocomplete(page, role_name: str, value: str) -> None:
    import re

    field = page.get_by_role("combobox", name=role_name, exact=True)
    field.click()
    field.fill("")
    field.type(value, delay=40)
    page.wait_for_timeout(1200)
    opt = page.locator("mat-option, .mat-mdc-option").filter(
        has_text=re.compile(re.escape(value), re.I)
    )
    if opt.count():
        opt.first.click()
    else:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
    page.wait_for_timeout(300)


def _click_step_next(page, label: str) -> None:
    """Click the labelled matStepperNext control (not ticket-carousel navigate_next)."""
    import re

    pattern = re.compile(re.escape(label), re.I)
    btn = page.locator("button[matsteppernext], button.mat-stepper-next").filter(
        has_text=pattern
    )
    target = None
    for i in range(btn.count()):
        el = btn.nth(i)
        if el.is_visible():
            target = el
            break
    if target is None:
        raise RuntimeError(f"no visible matStepperNext labelled {label!r}")
    target.click(timeout=30000)
    page.wait_for_timeout(2500)


def _run_swr_wizard(
    page,
    *,
    fields: MappedFormFields,
    ticket_path: Path,
    username: str,
    password: str,
    base_url: str,
    click_submit: bool,
    dry_run_to_review: bool,
    human_captcha_wait_seconds: int = 0,
) -> str:
    import re

    page.goto(f"{base_url}/en/login", wait_until="domcontentloaded", timeout=90000)
    page.locator("input[type=email]").first.fill(username)
    page.locator("input[type=password]").first.fill(password)
    page.locator("#submit-button").click()
    page.wait_for_url("**/en/account**", timeout=60000)

    page.goto(f"{base_url}/en/make-claim", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)

    # Travel date — readonly mat-datepicker; pick day-of-month.
    day = str(int(fields.journey_date.split("-")[2]))
    year, month, _ = fields.journey_date.split("-")
    page.get_by_role("textbox", name="Travel date").click()
    page.locator("mat-calendar, .mat-datepicker-content").first.wait_for(
        state="visible", timeout=15000
    )
    # Prefer aria-label e.g. "16 July 2026"
    month_name = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )[int(month) - 1]
    labelled = page.get_by_label(re.compile(rf"{day}\s+{month_name}\s+{year}", re.I))
    if labelled.count():
        labelled.first.click()
    else:
        page.locator(
            "button.mat-calendar-body-cell, .mat-calendar-body-cell"
        ).filter(has_text=re.compile(rf"^{day}$")).first.click()
    # Datepicker overlay must close before From/To are clickable.
    try:
        page.locator("mat-calendar, .mat-datepicker-content").first.wait_for(
            state="hidden", timeout=10000
        )
    except Exception:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.wait_for_timeout(300)

    _fill_autocomplete(page, "From", fields.origin_station)
    _fill_autocomplete(page, "To", fields.destination_station)

    leaving_slot = _floor_leaving_slot(fields.scheduled_departure)
    leaving = page.locator("input[aria-label*='Time']")
    leaving.first.click()
    leaving.first.fill("")
    leaving.first.type(leaving_slot, delay=30)
    page.wait_for_timeout(600)
    time_opt = page.locator("mat-option, .mat-mdc-option").filter(
        has_text=re.compile(rf"^{re.escape(leaving_slot)}$")
    )
    if time_opt.count():
        time_opt.first.click()
    else:
        page.keyboard.press("Enter")
    page.wait_for_timeout(300)

    page.locator("#find-journey").click()
    page.wait_for_timeout(5000)

    service = page.locator("sr-journey-card").filter(
        has_text=re.compile(re.escape(fields.scheduled_departure))
    )
    if service.count() == 0:
        raise RuntimeError(
            f"no sr-journey-card for departure {fields.scheduled_departure}"
        )
    service.first.click()
    page.get_by_text("Your selected journey", exact=False).first.wait_for(
        state="visible", timeout=15000
    )

    band_label = _attr(fields, "delay_band_label", "Between 15 - 29 minutes")
    band = page.locator("mat-card.delay-duration-card").filter(
        has_text=re.compile(re.escape(band_label), re.I)
    )
    band.first.wait_for(state="visible", timeout=15000)
    band.first.click()
    # Selecting a delay band advances the stepper to Ticket automatically.
    ticket_heading = page.get_by_text("Ticket details", exact=False).first
    try:
        ticket_heading.wait_for(state="visible", timeout=8000)
    except Exception:
        _click_step_next(page, "Ticket")
        ticket_heading.wait_for(state="visible", timeout=20000)
    page.wait_for_timeout(500)

    page.get_by_text("No", exact=True).first.click()
    page.wait_for_timeout(1000)

    medium = _attr(fields, "ticket_medium", "Paper")
    page.get_by_label(
        re.compile(rf"Select {re.escape(medium)} as your ticket type", re.I)
    ).first.click()
    page.wait_for_timeout(1000)

    duration = _attr(fields, "ticket_duration", "Return")
    dur = page.get_by_text(duration, exact=False)
    if dur.count() and dur.first.is_visible():
        dur.first.click()
        page.wait_for_timeout(800)

    files = page.locator("input[type=file]")
    if files.count() == 0:
        raise RuntimeError("ticket file input not found after medium/duration")
    # Angular upload control ignores direct set_input_files on the hidden input;
    # drive the visible "Upload a ticket" button via the file chooser.
    upload_btn = page.get_by_role("button", name=re.compile(r"Upload a ticket", re.I))
    if upload_btn.count() and upload_btn.first.is_visible():
        with page.expect_file_chooser(timeout=10000) as fc_info:
            upload_btn.first.click()
        fc_info.value.set_files(str(ticket_path))
    else:
        files.first.set_input_files(str(ticket_path))
    # Paper photos say "Image uploaded…"; e-ticket PDFs may omit "Image".
    page.get_by_text(
        re.compile(r"(Image )?uploaded successfully", re.I)
    ).first.wait_for(state="visible", timeout=20000)
    page.wait_for_timeout(500)

    price = _attr(fields, "ticket_price", "")
    if not price.strip():
        raise RuntimeError(
            "ticket_price missing — set SWR_TICKET_PRICE or ticket_price under "
            "## SWR Delay Repay ## (live filing must not invent a fare)"
        )
    price_box = page.locator("mat-form-field").filter(
        has_text=re.compile(r"Price", re.I)
    ).locator("input")
    if price_box.count():
        price_box.first.click()
        price_box.first.fill("")
        price_box.first.type(price, delay=25)
        page.keyboard.press("Tab")

    ref = _attr(fields, "ticket_reference", "")
    if not ref.strip():
        raise RuntimeError(
            "ticket_reference missing — set SWR_TICKET_REFERENCE or "
            "ticket_reference under ## SWR Delay Repay ## "
            "(5-digit number / booking ref; do not invent 12345)"
        )
    ref_box = page.locator("mat-form-field").filter(
        has_text=re.compile(r"Ticket number|booking reference", re.I)
    ).locator("input")
    if ref_box.count():
        ref_box.first.click()
        ref_box.first.fill("")
        ref_box.first.type(ref, delay=25)
        page.keyboard.press("Tab")

    confirm = page.locator("button:visible").filter(
        has_text=re.compile(r"Confirm", re.I)
    )
    if confirm.count() == 0:
        confirm = page.get_by_role("button", name=re.compile(r"Confirm", re.I))
    confirm.last.click()
    page.wait_for_timeout(2000)

    # With a saved BACS method, Confirm often jumps straight to Review.
    submit = page.get_by_role("button", name=re.compile(r"Submit claim", re.I))
    try:
        submit.first.wait_for(state="visible", timeout=8000)
    except Exception:
        try:
            _click_step_next(page, "Compensation")
        except RuntimeError:
            pass
        try:
            submit.first.wait_for(state="visible", timeout=5000)
        except Exception:
            try:
                _click_step_next(page, "Review claim")
            except RuntimeError:
                _click_step_next(page, "Review")
            submit.first.wait_for(state="visible", timeout=15000)

    if dry_run_to_review or not click_submit:
        if human_captcha_wait_seconds > 0:
            return _wait_for_human_submit(
                page,
                fields.journey_date,
                timeout_seconds=human_captcha_wait_seconds,
            )
        return f"REVIEW-READY-{fields.journey_date}"

    submit.first.click()
    page.wait_for_timeout(8000)
    return _extract_confirmation_reference(page, fields.journey_date)


def _wait_for_human_submit(page, journey_date: str, *, timeout_seconds: int) -> str:
    """Poll until the human completes reCAPTCHA + Submit on Review."""
    import time

    _alert_human_captcha_needed(page)
    print(
        "SWR Review is open — solve reCAPTCHA and click Submit claim in the browser.",
        flush=True,
    )
    deadline = time.monotonic() + max(30, timeout_seconds)
    while time.monotonic() < deadline:
        try:
            return _extract_confirmation_reference(page, journey_date)
        except RuntimeError:
            page.wait_for_timeout(2000)
    raise RuntimeError(
        f"timed out after {timeout_seconds}s waiting for human Submit/confirmation"
    )


def _alert_human_captcha_needed(page) -> None:
    """Bring the browser forward and show a non-blocking Windows alert."""
    import threading

    marker = "SWR Delay Repay — CAPTCHA needed"
    try:
        page.evaluate(
            """(title) => { document.title = title; }""",
            marker,
        )
    except Exception:
        pass
    try:
        page.bring_to_front()
    except Exception:
        pass
    _focus_window_by_title(marker)
    _beep_attention()

    def _message_box() -> None:
        try:
            import ctypes

            MB_ICONWARNING = 0x00000030
            MB_TOPMOST = 0x00040000
            MB_SETFOREGROUND = 0x00010000
            ctypes.windll.user32.MessageBoxW(
                0,
                "Chromium is on the SWR Review page.\n\n"
                "1. Solve the reCAPTCHA\n"
                "2. Click Submit claim\n\n"
                "This window can be closed after you start — filing will continue.",
                marker,
                MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND,
            )
        except Exception:
            pass

    threading.Thread(target=_message_box, daemon=True).start()


def _beep_attention() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


def _focus_window_by_title(title_substr: str) -> None:
    """Best-effort: restore + foreground the Chromium window on Windows."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_substr.casefold() in buf.value.casefold():
                found.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        if not found:
            return
        hwnd = found[0]
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        current = kernel32.GetCurrentThreadId()
        other = user32.GetWindowThreadProcessId(foreground, None)
        user32.AttachThreadInput(current, other, True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(current, other, False)
    except Exception:
        pass


def _extract_confirmation_reference(page, journey_date: str) -> str:
    """Parse confirmation after Submit; never treat nav chrome as a reference."""
    import re as _re

    still_submit = page.get_by_role("button", name=_re.compile(r"Submit claim", _re.I))
    submit_visible = bool(
        still_submit.count() and still_submit.first.is_visible()
    )
    return parse_swr_confirmation(
        page.inner_text("body"),
        page.url,
        journey_date,
        submit_still_visible=submit_visible,
    )


def parse_swr_confirmation(
    body: str,
    url: str,
    journey_date: str,
    *,
    submit_still_visible: bool,
) -> str:
    """Pure confirmation parser (unit-tested)."""
    import re as _re

    if submit_still_visible:
        raise RuntimeError(
            "Submit clicked but Review/Submit still visible "
            "(likely reCAPTCHA or validation); url=" + url
        )

    # Live portal claim ids look like SWR-0218-108-579 (confirmed 2026-07-17).
    m_swr = _re.search(r"\b(SWR-\d{4}-\d{3}-\d{3})\b", body, _re.I)
    if m_swr:
        return m_swr.group(1).upper()

    patterns = (
        r"(?:claim\s*(?:reference|number|#)|reference\s*(?:number|#)?)\s*[:\s]*([A-Z0-9][A-Z0-9-]{4,})",
        r"confirmation\s*(?:number|#|ref(?:erence)?)?\s*[:\s]*([A-Z0-9][A-Z0-9-]{4,})",
    )
    reject = {"automated", "claims", "submit", "review", "ticket", "journey"}
    for pat in patterns:
        for m in _re.finditer(pat, body, _re.I):
            token = m.group(1).strip()
            if token.casefold() in reject:
                continue
            if token.casefold().startswith("submit"):
                continue
            return token

    conf_tokens = ("thank you", "has been submitted", "claim submitted", "confirmation")
    body_l = body.casefold()
    if any(t in body_l for t in conf_tokens) or "make-claim" not in url:
        return f"SUBMITTED-{journey_date}"
    raise RuntimeError(
        "Submit clicked but confirmation not detected; url=" + url
    )


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
