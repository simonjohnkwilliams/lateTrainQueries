"""Patch golden expected.json reject entries with transcripts + gate tags."""
from __future__ import annotations

import json
from pathlib import Path

p = Path("tests/fixtures/tickets/golden/expected.json")
d = json.loads(p.read_text(encoding="utf-8"))

d["reject"]["reject_wrong_route_burgess_christchurch.jpg"].update({
    "gate": "content",
    "transcript": (
        "Anytime Day Return from Guildford to Burgess Hill "
        "Date of travel 16-JUL-2024 Adult Standard Class"
    ),
})
d["reject"]["reject_wrong_route_chesterfield.jpg"].update({
    "gate": "content",
    "transcript": (
        "Off-Peak Return from Chesterfield to London Terminals "
        "Valid 03-JNR-17 until 02-FBY-17 Adult Standard Class"
    ),
})
d["reject"]["reject_receipt_not_ticket.jpg"].update({
    "gate": "content",
    "transcript": (
        "RECEIPT NOT VALID FOR TRAVEL 2 RAIL TICKETS Date 13-MCH-17 "
        "Amount £17-00 Issuing office LONDON M'BONE Vat Reg no. 667-3877-77"
    ),
})
d["reject"]["reject_sales_voucher.jpg"].update({
    "gate": "content",
    "transcript": (
        "DEBIT/CREDIT CARD SALES VOUCHER Qty 001 Description TICKET "
        "Total £31.00 Date 29-SEP-17 Issuing Office GUILDFORD "
        "CARDHOLDER'S COPY Authorised Sale Confirmed"
    ),
})
d["reject"]["reject_multi_ticket_cropped.jpg"].update({
    "gate": "image_quality",
    "transcript": "",
})
d["reject"]["reject_multi_ticket_day_tc.jpg"].update({
    "gate": "image_quality",
    "transcript": "",
})

p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
print("ok")
