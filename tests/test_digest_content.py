"""Story 4.2: weekly digest email content rendering (FR22, AD-5).

Pure ``render_digest`` — no SMTP.
"""
from __future__ import annotations

import pytest

from trainline.adapters.notification import digest_subject, render_digest
from trainline.engine.models import Band, Claim, DayResult, Direction, FetchStatus


def _claim(**overrides) -> Claim:
    base = dict(
        date="2026-07-10",
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=480,
        scheduled_arrival=540,
        actual_arrival=560,
        delay=20,
        band=Band.B15_29,
        reason="Late",
    )
    base.update(overrides)
    return Claim(**base)


@pytest.mark.offline
def test_render_lists_claim_fields():
    results = [
        DayResult(date="2026-07-10", status=FetchStatus.OK, claims=(_claim(),)),
    ]
    html, text = render_digest(results)
    for blob in (html, text):
        assert "2026-07-10" in blob
        assert "outbound" in blob
        assert "15-29" in blob
        assert "GOD" in blob and "WAT" in blob
        assert "20" in blob


@pytest.mark.offline
def test_fetch_failed_distinct_from_no_claim():
    results = [
        DayResult(date="2026-07-08", status=FetchStatus.OK, claims=()),
        DayResult(date="2026-07-09", status=FetchStatus.FETCH_FAILED, claims=()),
        DayResult(
            date="2026-07-10",
            status=FetchStatus.OK,
            claims=(_claim(date="2026-07-10"),),
        ),
    ]
    html, text = render_digest(results)
    for blob in (html, text):
        assert "not analysed" in blob.casefold() or "Not analysed" in blob
        assert "2026-07-09" in blob
        # Clean no-claim day must not be listed as not-analysed
        # (2026-07-08 may appear only if we list no-claim days — must NOT be under failure)
    # Failure section should mention 07-09; no-claim day must not be labeled failed
    assert "2026-07-09" in text
    failed_section = text[text.casefold().index("not analysed"):]
    assert "2026-07-09" in failed_section
    assert "2026-07-08" not in failed_section


@pytest.mark.offline
def test_zero_claims_explicit_message():
    results = [
        DayResult(date="2026-07-08", status=FetchStatus.OK, claims=()),
        DayResult(date="2026-07-09", status=FetchStatus.OK, claims=()),
    ]
    html, text = render_digest(results)
    for blob in (html, text):
        assert "no claimable" in blob.casefold()


@pytest.mark.offline
def test_html_and_text_both_nonempty():
    results = [
        DayResult(date="2026-07-10", status=FetchStatus.OK, claims=(_claim(),)),
    ]
    html, text = render_digest(results)
    assert "<" in html and "table" in html.casefold()
    assert "2026-07-10" in text
    assert "<" not in text  # plain text has no HTML tags


@pytest.mark.offline
def test_digest_subject_includes_claim_count():
    results = [
        DayResult(
            date="2026-07-10",
            status=FetchStatus.OK,
            claims=(_claim(), _claim(direction=Direction.INBOUND, origin="WAT",
                                     destination="GOD")),
        ),
    ]
    subj = digest_subject(results)
    assert "2" in subj
