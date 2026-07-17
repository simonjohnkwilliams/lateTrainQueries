# Golden ticket fixtures (cherry-picked + unreadable rescues)
#
# `golden/` — accept set + `reject/` samples for upload fail rules.
# `golden/expected.json` — ground truth (dates, route, quality, FakeOcr transcripts).
#
# Rebuild:
#   python scripts/build_golden_fixtures.py
#
# Accept includes:
#   - Best photos from `ready_to_claim`
#   - Human-readable tickets rescued from `rejected/unreadable-*` (earlier OCR false rejects)
#
# Reject samples: multi-ticket, receipt, sales voucher, wrong route.
#
# Re-upload still needed: PDFs; remaining multi-ticket / scribble / non-GOD docs.
#
# Journey date for weeklies = **start date**, not valid-until.
# APTIS months: JNR=Jan, FBY=Feb, MCH=Mar, JLY=Jul, DMR=Dec.
