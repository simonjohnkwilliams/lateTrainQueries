"""Notification adapter — SMTP weekly digest seam (AD-13, FR22).

``send_digest`` is the sole email entry point. Transport is injectable for
offline tests (no real SMTP). Credentials come from env via ``EmailConfig``
loaded by the composition root — this module must not import other adapters
(AD-2); ``config`` is duck-typed (``smtp_host``, ``smtp_port``, …).

``render_digest`` / ``digest_subject`` are pure presentation over
``engine.models.DayResult`` (Story 4.2) — no I/O.
"""
from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from trainline.engine.models import Band, FetchStatus

# Presentation labels — mirror storage CSV (do not import storage; AD-2).
BAND_LABEL = {
    Band.NONE: "none",
    Band.B15_29: "15-29",
    Band.B30_59: "30-59",
    Band.B60_119: "60-119",
    Band.B120_PLUS: "120+",
}
_BAND_LABEL = BAND_LABEL  # backwards-compatible alias


def digest_subject(day_results) -> str:
    """Stable subject line including claimable-row count."""
    n = sum(len(d.claims) for d in day_results if d.status is FetchStatus.OK)
    if n == 0:
        return "Delay Repay digest: no claimable rows"
    return f"Delay Repay digest: {n} claimable row{'s' if n != 1 else ''}"


def render_digest(day_results) -> tuple[str, str]:
    """Render ``(body_html, body_text)`` summarising a run (FR22, AD-5).

    Claim rows list date, direction, band, origin→destination, delay_min.
    ``FETCH_FAILED`` days appear under "Not analysed", distinct from clean
    no-claim days. Zero claims → an explicit no-claimable-rows message.
    """
    results = list(day_results)
    claims = [
        c
        for d in results
        if d.status is FetchStatus.OK
        for c in d.claims
    ]
    failed = [d.date for d in results if d.status is FetchStatus.FETCH_FAILED]

    text = _render_text(claims, failed)
    body_html = _render_html(claims, failed)
    return body_html, text


def _render_text(claims, failed_dates) -> str:
    lines = ["Weekly Delay Repay digest", ""]
    if not claims:
        lines.append("No claimable rows found.")
        lines.append("")
    else:
        lines.append("Claimable rows:")
        lines.append(
            f"{'date':<12} {'dir':<10} {'band':<8} {'route':<15} {'delay':>5}")
        lines.append("-" * 54)
        for c in claims:
            route = f"{c.origin}->{c.destination}"
            lines.append(
                f"{c.date:<12} {c.direction.value:<10} "
                f"{_BAND_LABEL[c.band]:<8} {route:<15} {c.delay:>5}"
            )
        lines.append("")
    if failed_dates:
        lines.append("Not analysed (FETCH_FAILED):")
        for date in failed_dates:
            lines.append(f"  {date}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_html(claims, failed_dates) -> str:
    parts = ["<html><body>", "<h1>Weekly Delay Repay digest</h1>"]
    if not claims:
        parts.append("<p><strong>No claimable rows found.</strong></p>")
    else:
        parts.append("<h2>Claimable rows</h2>")
        parts.append(
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<thead><tr>"
            "<th>date</th><th>direction</th><th>band</th>"
            "<th>route</th><th>delay_min</th>"
            "</tr></thead><tbody>"
        )
        for c in claims:
            route = f"{html.escape(c.origin)}→{html.escape(c.destination)}"
            parts.append(
                "<tr>"
                f"<td>{html.escape(c.date)}</td>"
                f"<td>{html.escape(c.direction.value)}</td>"
                f"<td>{html.escape(_BAND_LABEL[c.band])}</td>"
                f"<td>{route}</td>"
                f"<td>{c.delay}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
    if failed_dates:
        parts.append("<h2>Not analysed (FETCH_FAILED)</h2>")
        parts.append("<ul>")
        for date in failed_dates:
            parts.append(f"<li>{html.escape(date)}</li>")
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def send_digest(
    subject: str,
    body_html: str,
    body_text: str,
    config,
    *,
    transport=None,
) -> None:
    """Send a digest email via SMTP or an injected ``transport(msg, config)``.

    ``config`` must expose ``smtp_host``, ``smtp_port``, ``smtp_user``,
    ``smtp_password``, ``digest_to``, and optionally ``digest_from``.

    Default transport: port 465 uses ``SMTP_SSL``; port 587 uses STARTTLS;
    other ports use plain SMTP (no automatic upgrade).
    """
    from_addr = (getattr(config, "digest_from", None) or "").strip() or config.smtp_user
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = config.digest_to
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    if transport is not None:
        transport(msg, config)
        return

    host, port = config.smtp_host, config.smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(config.smtp_user, config.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if port == 587:
            smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)
