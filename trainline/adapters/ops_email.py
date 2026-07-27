"""Ops email renderer — Table 1 this-run summary (FR36).

Table 2 (claim lifecycle follow-up, FR37) is deferred to a later epic.
Pure presentation — no network clients or config imports (AD-2).
"""
from __future__ import annotations

import html
from typing import Any


def ops_email_subject(*, anchor_friday: str, filed: int, claimable: int) -> str:
    return (
        f"Delay Repay weekly ops — {anchor_friday} "
        f"(filed {filed}, claimable {claimable})"
    )


def render_ops_email(
    *,
    table1: dict[str, Any],
    table2: list[dict[str, Any]] | None = None,
    anchor_friday: str,
) -> tuple[str, str]:
    """Render ``(html, text)`` for the weekly ops email.

    ``table1`` keys (all optional lists/dicts):
    claimable, newly_filed, skipped_no_ticket, surplus_tickets, rejections.
    ``table2`` omitted/empty → section skipped (deferred epic).
    """
    table2 = table2 or []
    text = _render_text(table1, table2, anchor_friday)
    body_html = _render_html(table1, table2, anchor_friday)
    return body_html, text


def _render_text(table1: dict[str, Any], table2: list, anchor: str) -> str:
    lines = [f"Delay Repay weekly ops — {anchor}", ""]
    claimable = list(table1.get("claimable") or [])
    if not claimable:
        lines.append("No claimable rows found.")
        lines.append("")
    else:
        lines.append("Claimable rows:")
        lines.append(
            f"{'date':<12} {'dir':<10} {'band':<8} {'route':<15} {'delay':>5}"
        )
        lines.append("-" * 54)
        for c in claimable:
            lines.append(
                f"{c.get('date',''):<12} {c.get('direction',''):<10} "
                f"{c.get('band',''):<8} {c.get('route',''):<15} "
                f"{c.get('delay', 0):>5}"
            )
        lines.append("")

    filed = list(table1.get("newly_filed") or [])
    lines.append("Newly filed this run:")
    if not filed:
        lines.append("  (none)")
    else:
        for row in filed:
            ref = row.get("reference") or row.get("claim_id") or ""
            lines.append(
                f"  {row.get('date')} {row.get('direction')} "
                f"{row.get('outcome', 'filed')} {ref}".rstrip()
            )
    lines.append("")

    skipped = list(table1.get("skipped_no_ticket") or [])
    lines.append("Skipped (no ticket for claim date):")
    if not skipped:
        lines.append("  (none)")
    else:
        for date in skipped:
            lines.append(f"  {date}")
    lines.append("")

    surplus = list(table1.get("surplus_tickets") or [])
    lines.append("Tickets with no matching late trains:")
    if not surplus:
        lines.append("  (none)")
    else:
        for row in surplus:
            lines.append(
                f"  {row.get('date', '')} {row.get('path', '')} "
                f"— no claimable delay that day"
            )
    lines.append("")

    rejections = list(table1.get("rejections") or [])
    if rejections:
        lines.append("Rejected tickets:")
        for row in rejections:
            lines.append(f"  {row.get('reason')} — {row.get('path')}")
        lines.append("")

    if table2:
        lines.append("Table 2 — follow-up (prior claims):")
        for row in table2:
            lines.append(
                f"  {row.get('journey_date')} {row.get('claim_id')} "
                f"{row.get('status')}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_html(table1: dict[str, Any], table2: list, anchor: str) -> str:
    parts = [
        "<html><body>",
        f"<h1>Delay Repay weekly ops — {html.escape(anchor)}</h1>",
    ]
    claimable = list(table1.get("claimable") or [])
    if not claimable:
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
        for c in claimable:
            parts.append(
                "<tr>"
                f"<td>{html.escape(str(c.get('date', '')))}</td>"
                f"<td>{html.escape(str(c.get('direction', '')))}</td>"
                f"<td>{html.escape(str(c.get('band', '')))}</td>"
                f"<td>{html.escape(str(c.get('route', '')))}</td>"
                f"<td>{html.escape(str(c.get('delay', '')))}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")

    parts.append("<h2>Newly filed this run</h2>")
    filed = list(table1.get("newly_filed") or [])
    if not filed:
        parts.append("<p>(none)</p>")
    else:
        parts.append("<ul>")
        for row in filed:
            ref = row.get("reference") or row.get("claim_id") or ""
            parts.append(
                "<li>"
                f"{html.escape(str(row.get('date', '')))} "
                f"{html.escape(str(row.get('direction', '')))} "
                f"{html.escape(str(row.get('outcome', 'filed')))} "
                f"{html.escape(str(ref))}"
                "</li>"
            )
        parts.append("</ul>")

    parts.append("<h2>Skipped (no ticket for claim date)</h2>")
    skipped = list(table1.get("skipped_no_ticket") or [])
    if not skipped:
        parts.append("<p>(none)</p>")
    else:
        parts.append("<ul>")
        for date in skipped:
            parts.append(f"<li>{html.escape(str(date))}</li>")
        parts.append("</ul>")

    parts.append("<h2>Tickets with no matching late trains</h2>")
    surplus = list(table1.get("surplus_tickets") or [])
    if not surplus:
        parts.append("<p>(none)</p>")
    else:
        parts.append("<ul>")
        for row in surplus:
            parts.append(
                "<li>"
                f"{html.escape(str(row.get('date', '')))} "
                f"{html.escape(str(row.get('path', '')))} "
                "— no claimable delay that day"
                "</li>"
            )
        parts.append("</ul>")

    rejections = list(table1.get("rejections") or [])
    if rejections:
        parts.append("<h2>Rejected tickets</h2><ul>")
        for row in rejections:
            parts.append(
                "<li>"
                f"{html.escape(str(row.get('reason', '')))} — "
                f"{html.escape(str(row.get('path', '')))}"
                "</li>"
            )
        parts.append("</ul>")

    if table2:
        parts.append("<h2>Table 2 — follow-up</h2><ul>")
        for row in table2:
            parts.append(
                "<li>"
                f"{html.escape(str(row.get('journey_date', '')))} "
                f"{html.escape(str(row.get('claim_id', '')))} "
                f"{html.escape(str(row.get('status', '')))}"
                "</li>"
            )
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)
