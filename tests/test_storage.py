"""Story 3.2: storage — Claim -> CSV + JSON, sorted (FR13, FR14, FR15).

Offline; writes to tmp_path.
"""
import csv
import json

import pytest

from trainline.adapters import storage
from trainline.engine.models import Band, Claim, Direction


def _claim(date, direction, dep, band=Band.B15_29, delay=20, reason=None):
    origin, destination = (("GOD", "WAT") if direction is Direction.OUTBOUND
                           else ("WAT", "GOD"))
    return Claim(
        date=date, direction=direction, origin=origin, destination=destination,
        scheduled_departure=dep, scheduled_arrival=dep + 60,
        actual_arrival=dep + 60 + delay, delay=delay, band=band, reason=reason,
    )


@pytest.mark.offline
def test_csv_rows_carry_all_swr_form_fields(tmp_path):
    claim = _claim("2026-05-28", Direction.OUTBOUND, 7 * 60 + 8,
                   band=Band.B15_29, delay=23, reason="Signal failure")
    csv_path = tmp_path / "claims.csv"
    json_path = tmp_path / "claims.json"
    storage.write_claims([claim], str(csv_path), str(json_path))

    with open(csv_path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-05-28"
    assert row["direction"] == "outbound"
    assert row["origin"] == "GOD"
    assert row["destination"] == "WAT"
    assert row["scheduled_departure"] == "07:08"
    assert row["scheduled_arrival"] == "08:08"
    assert row["actual_arrival"] == "08:31"
    assert row["delay_min"] == "23"
    assert row["band"] == "15-29"
    assert row["reason"] == "Signal failure"


@pytest.mark.offline
def test_both_csv_and_json_written_and_surface_band_not_pounds(tmp_path):
    claim = _claim("2026-05-28", Direction.INBOUND, 18 * 60, band=Band.B30_59, delay=35)
    csv_path = tmp_path / "claims.csv"
    json_path = tmp_path / "claims.json"
    storage.write_claims([claim], str(csv_path), str(json_path))

    assert csv_path.exists() and json_path.exists()
    data = json.loads(json_path.read_text())
    assert data[0]["band"] == "30-59"
    # No monetary figure anywhere in the output.
    blob = csv_path.read_text() + json_path.read_text()
    assert "£" not in blob


@pytest.mark.offline
def test_hhmm_formatting_wraps_past_midnight(tmp_path):
    # actual arrival 00:20 next day = 20 + 1440 minutes -> "00:20".
    claim = Claim(
        date="2026-05-28", direction=Direction.OUTBOUND, origin="GOD",
        destination="WAT", scheduled_departure=23 * 60 + 50,
        scheduled_arrival=15 + 1440, actual_arrival=20 + 1440, delay=5,
        band=Band.NONE, reason=None,
    )
    csv_path = tmp_path / "c.csv"
    json_path = tmp_path / "c.json"
    storage.write_claims([claim], str(csv_path), str(json_path))
    row = json.loads(json_path.read_text())[0]
    assert row["scheduled_arrival"] == "00:15"
    assert row["actual_arrival"] == "00:20"


@pytest.mark.offline
def test_sorted_by_date_then_direction(tmp_path):
    claims = [
        _claim("2026-05-28", Direction.INBOUND, 18 * 60),
        _claim("2026-05-27", Direction.INBOUND, 18 * 60),
        _claim("2026-05-28", Direction.OUTBOUND, 7 * 60),
        _claim("2026-05-27", Direction.OUTBOUND, 7 * 60),
    ]
    csv_path = tmp_path / "c.csv"
    json_path = tmp_path / "c.json"
    ordered = storage.write_claims(claims, str(csv_path), str(json_path))
    got = [(c.date, c.direction.value) for c in ordered]
    assert got == [
        ("2026-05-27", "outbound"),
        ("2026-05-27", "inbound"),
        ("2026-05-28", "outbound"),
        ("2026-05-28", "inbound"),
    ]


@pytest.mark.offline
def test_empty_claims_writes_header_only(tmp_path):
    csv_path = tmp_path / "c.csv"
    json_path = tmp_path / "c.json"
    storage.write_claims([], str(csv_path), str(json_path))
    with open(csv_path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [storage.CSV_FIELDS]  # header only
    assert json.loads(json_path.read_text()) == []


@pytest.mark.offline
def test_csv_and_json_rows_agree(tmp_path):
    claims = [
        _claim("2026-05-28", Direction.INBOUND, 18 * 60, band=Band.B60_119, delay=70),
        _claim("2026-05-27", Direction.OUTBOUND, 7 * 60, band=Band.B15_29, delay=18),
    ]
    csv_path = tmp_path / "c.csv"
    json_path = tmp_path / "c.json"
    storage.write_claims(claims, str(csv_path), str(json_path))
    with open(csv_path, newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    json_rows = json.loads(json_path.read_text())
    # DictReader values are always strings; normalise JSON for comparison.
    normalised_json = [
        {k: (str(v) if k == "delay_min" else v) for k, v in row.items()}
        for row in json_rows
    ]
    assert csv_rows == normalised_json
    assert [r["date"] for r in csv_rows] == ["2026-05-27", "2026-05-28"]
