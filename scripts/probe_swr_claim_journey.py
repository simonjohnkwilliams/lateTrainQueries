"""Live SWR Delay Repay journey probe (dry — stops before Submit).

Writes sanitized HTML/screenshots under live-capture/swr-journey/.
Never prints credential values.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trainline.adapters.config import _find_section, parse_credentials_file

OUT = ROOT / "live-capture" / "swr-journey"
OUT.mkdir(parents=True, exist_ok=True)

# Option A: newest ticket photo + last claimable weekday
TRAVEL_DATE = "16/07/2026"  # UK display
FROM_STATION = "Godalming"
TO_STATION = "London Waterloo"
LEAVING_AT = "09:30"  # SWR leaving-at autocomplete uses 15-min slots; HSP was 09:41


def _creds():
    path = os.environ.get("HSP_CREDENTIALS_FILE")
    sections = parse_credentials_file(path)
    hit = (
        _find_section(sections, "swr", "login")
        or _find_section(sections, "swr", "delay")
        or _find_section(sections, "swr")
    )
    if not hit:
        raise SystemExit("No ## SWR … ## section found")
    vals = hit[1]
    user = (vals.get("swr_username") or vals.get("username") or vals.get("email") or "").strip()
    password = (vals.get("swr_password") or vals.get("password") or "").strip()
    base = (vals.get("url") or "https://delayrepay.southwesternrailway.com/").strip()
    if not user or not password:
        raise SystemExit("SWR username/password missing")
    return user, password, base.rstrip("/")


def _sanitize(html: str) -> str:
    html = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "REDACTED@example.com",
        html,
    )
    return html


def dump(page, name: str) -> None:
    page.wait_for_timeout(800)
    raw = page.content()
    (OUT / f"{name}.html").write_text(_sanitize(raw), encoding="utf-8")
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print(f"DUMP {name} url={page.url}")


def fill_autocomplete(page, label: str, value: str) -> None:
    field = page.get_by_role("combobox", name=label, exact=True)
    field.click()
    field.fill("")
    field.type(value, delay=50)
    page.wait_for_timeout(1500)
    opt = page.locator(
        f"[id^=mat-autocomplete] mat-option, .mat-mdc-option, mat-option"
    ).filter(has_text=re.compile(re.escape(value), re.I))
    if opt.count() == 0:
        opt = page.get_by_role("option", name=re.compile(re.escape(value), re.I))
    if opt.count():
        opt.first.click()
    else:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
    page.wait_for_timeout(400)


def main() -> int:
    from playwright.sync_api import sync_playwright

    user, password, base = _creds()
    print(f"base={base} user_len={len(user)} pass_len={len(password)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(f"{base}/en/login", wait_until="domcontentloaded", timeout=90000)
        dump(page, "01_login")
        page.locator("input[type=email]").first.fill(user)
        page.locator("input[type=password]").first.fill(password)
        page.locator("#submit-button").click()
        page.wait_for_url("**/en/account**", timeout=60000)
        dump(page, "02_account")

        page.goto(f"{base}/en/make-claim", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        dump(page, "03_make_claim_initial")

        # Travel date is a readonly mat-datepicker (min/max = ~28-day window).
        date_box = page.get_by_role("textbox", name="Travel date")
        date_box.click()
        page.wait_for_timeout(600)
        # Pick day 16 in the open calendar (July 2026 for Option A).
        cal = page.locator("mat-calendar, .mat-datepicker-content")
        day = page.locator(
            "button.mat-calendar-body-cell, .mat-calendar-body-cell"
        ).filter(has_text=re.compile(r"^16$"))
        if day.count() == 0:
            # Fallback: aria-label often "16 July 2026"
            day = page.get_by_label(re.compile(r"16.*July.*2026", re.I))
        day.first.click()
        page.wait_for_timeout(500)
        dump(page, "03b_date_picked")

        fill_autocomplete(page, "From", FROM_STATION)
        fill_autocomplete(page, "To", TO_STATION)

        leaving = page.get_by_role("combobox", name=re.compile(r"Leaving at|Time:", re.I))
        if leaving.count() == 0:
            leaving = page.locator("input[aria-label*='Time']")
        leaving.first.click()
        leaving.first.fill("")
        leaving.first.type(LEAVING_AT, delay=40)
        page.wait_for_timeout(800)
        time_opt = page.locator("mat-option, .mat-mdc-option").filter(
            has_text=re.compile(rf"^{re.escape(LEAVING_AT)}$")
        )
        if time_opt.count():
            time_opt.first.click()
        else:
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)
        dump(page, "04_journey_filled")

        page.locator("#find-journey").click()
        page.wait_for_timeout(6000)
        dump(page, "05_journey_search_results")

        # Select the matching service card (HSP outbound was 09:41).
        service = page.locator("sr-journey-card").filter(has_text=re.compile(r"09:41"))
        if service.count() == 0:
            service = page.locator("mat-card").filter(has_text=re.compile(r"09:41\s*-\s*10:32"))
        print(f"service_cards={service.count()}")
        service.first.click()
        print("selected service 09:41")
        page.wait_for_timeout(2000)
        # Confirm selection surfaced
        selected = page.get_by_text("Your selected journey", exact=False)
        try:
            selected.first.wait_for(state="visible", timeout=10000)
            print("selected journey panel visible")
        except Exception as exc:
            print("selected journey panel NOT visible:", exc)
            dump(page, "05b_service_selected")
            raise
        dump(page, "05b_service_selected")

        # Then pick delay-duration card.
        band = page.locator("mat-card.delay-duration-card").filter(
            has_text=re.compile(r"15\s*-\s*29", re.I)
        )
        band.first.wait_for(state="visible", timeout=20000)
        band.first.scroll_into_view_if_needed()
        band.first.click()
        print("selected delay band 15-29")
        page.wait_for_timeout(800)
        dump(page, "06_delay_band_selected")

        # Advance to Ticket
        ticket_btn = page.get_by_role("button", name=re.compile(r"Ticket", re.I))
        if ticket_btn.count():
            ticket_btn.last.click()
            page.wait_for_timeout(3000)
        dump(page, "07_ticket_step")

        # Single ticket path
        page.get_by_text("No", exact=True).first.click()
        page.wait_for_timeout(1500)
        dump(page, "07b_ticket_single")

        # Ticket medium — sample photos are paper day returns.
        paper = page.get_by_label(re.compile(r"Select Paper as your ticket type", re.I))
        if paper.count() == 0:
            paper = page.locator(".ticket-medium, [role=option]").filter(
                has_text=re.compile(r"Paper", re.I)
            )
        paper.first.click()
        page.wait_for_timeout(1500)
        dump(page, "07c_ticket_type")

        # Duration / class cards if shown (Anytime day return etc.)
        for label in (
            "Anytime Day Return",
            "Anytime Day Single",
            "Off-Peak Day Return",
            "Day Return",
            "Return",
        ):
            opt = page.get_by_text(label, exact=False)
            if opt.count() and opt.first.is_visible():
                opt.first.click()
                print("selected ticket duration", label)
                page.wait_for_timeout(1000)
                break
        dump(page, "07d_ticket_duration")

        ticket_path = ROOT / "sample-tickets" / "20250131_125953.jpg"
        if not ticket_path.is_file():
            ticket_path = (
                ROOT / "tests" / "fixtures" / "tickets" / "golden"
                / "day_return_2025-01-07_god_terminals.jpg"
            )
        file_inputs = page.locator("input[type=file]")
        print(f"file_inputs={file_inputs.count()} ticket={ticket_path.name}")
        if file_inputs.count() == 0:
            browse = page.get_by_text(re.compile(r"Browse|Upload|Choose file|Add photo", re.I))
            if browse.count():
                browse.first.click()
                page.wait_for_timeout(1000)
            file_inputs = page.locator("input[type=file]")
            print(f"file_inputs_after_browse={file_inputs.count()}")
        if file_inputs.count() and ticket_path.is_file():
            file_inputs.first.set_input_files(str(ticket_path))
            page.wait_for_timeout(2500)
        dump(page, "08_ticket_uploaded")

        # Required ticket metadata. Ticket number must satisfy SWR validation
        # ("5-digit number, collection or booking reference").
        price_box = page.locator("mat-form-field").filter(
            has_text=re.compile(r"Price", re.I)
        ).locator("input")
        if price_box.count():
            price_box.first.click()
            price_box.first.fill("")
            price_box.first.type("12.50", delay=30)
            page.keyboard.press("Tab")
        ticket_id = page.locator("mat-form-field").filter(
            has_text=re.compile(r"Ticket number|booking reference", re.I)
        ).locator("input")
        if ticket_id.count():
            ticket_id.first.click()
            ticket_id.first.fill("")
            ticket_id.first.type("12345", delay=30)
            page.keyboard.press("Tab")
        dump(page, "08b_ticket_fields")

        confirm = page.get_by_role("button", name=re.compile(r"Confirm", re.I))
        if confirm.count():
            confirm.last.click()
            page.wait_for_timeout(2000)
        dump(page, "08c_ticket_confirmed")

        page.get_by_role("button", name=re.compile(r"Compensation", re.I)).last.click()
        page.wait_for_timeout(4000)
        dump(page, "09_compensation_step")

        review_btn = page.get_by_role("button", name=re.compile(r"Review", re.I))
        if review_btn.count() and review_btn.last.is_visible():
            print("CLICK Review")
            review_btn.last.click()
            page.wait_for_timeout(4000)
        dump(page, "10_review_pre_submit")

        submit = page.get_by_role("button", name=re.compile(r"Submit claim", re.I))
        captcha = page.locator(
            "textarea[name=g-recaptcha-response], iframe[src*=recaptcha], .g-recaptcha"
        )
        print(f"submit_buttons={submit.count()} captcha_nodes={captcha.count()}")
        if submit.count():
            print("Submit claim button visible — dry stop (not clicking)")
        print("STOP before Submit (dry probe)")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
