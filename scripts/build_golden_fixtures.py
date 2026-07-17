"""Build tests/fixtures/tickets/golden from cherry-picked ready_to_claim photos."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tickets" / "processed" / "ready_to_claim"
REJ = ROOT / "tickets" / "processed" / "rejected"
DST = ROOT / "tests" / "fixtures" / "tickets" / "golden"
OLD_DATE_CASES = ROOT / "tests" / "fixtures" / "tickets" / "date_cases"

# source filename -> (dest stem, expected record)
# Drops: 03-26-bodalming (worse outward dup of 04-11), 09-17-Travelcard (worse of pair),
#        10-28-Start (dup of 10-22 week), 10-10 kept only as reject sample.
PICKS: list[tuple[str, str, dict]] = [
    # Day returns / singles
    (
        "01-31-yaiiag.jpg",
        "day_return_2025-01-06_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2025-01-06",
            "date_print": "06-JNR-25",
            "quality": "gold",
        },
    ),
    (
        "01-31-Terminals.jpg",
        "day_return_2025-01-07_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2025-01-07",
            "date_print": "07-JNR-25",
            "quality": "ok",
            "notes": "Flash glare on centre; still readable",
        },
    ),
    (
        "04-11-terminals.jpg",
        "day_return_2024-03-26_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2024-03-26",
            "date_print": "26-MCH-24",
            "quality": "gold",
            "notes": "Preferred over 03-26-bodalming (finger + stacked ticket)",
        },
    ),
    (
        "03-26-Terminals.jpg",
        "day_return_2024-03-26_terminals_god.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "return",
            "origin": "London Terminals",
            "destination": "Godalming",
            "journey_date": "2024-03-26",
            "date_print": "26-MCH-24",
            "quality": "ok",
            "notes": "Thumb on corner; fields clear",
        },
    ),
    (
        "04-30-Terminals.jpg",
        "day_return_2019-04-30_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2019-04-30",
            "date_print": "30-APR-19",
            "quality": "ok",
            "notes": "Left glare on price/logo",
        },
    ),
    (
        "05-09-Terminals.jpg",
        "day_return_2019-05-09_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2019-05-09",
            "date_print": "09-MAY-19",
            "quality": "gold",
        },
    ),
    (
        "09-11-Clase.jpg",
        "day_return_2018-09-03_terminals_god.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "return",
            "origin": "London Terminals",
            "destination": "Godalming",
            "journey_date": "2018-09-03",
            "date_print": "03-SEP-18",
            "quality": "gold",
        },
    ),
    (
        "11-06-Terminals.jpg",
        "day_single_2019-11-06_terminals_god.jpg",
        {
            "kind": "anytime_day_single",
            "portion": None,
            "origin": "London Terminals",
            "destination": "Godalming",
            "journey_date": "2019-11-06",
            "date_print": "06-NOV-19",
            "quality": "gold",
        },
    ),
    # Day travelcards
    (
        "05-16-Start.jpg",
        "day_tc_2019-05-16_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-05-16",
            "start_date": "2019-05-16",
            "valid_until": "2019-05-16",
            "date_print": "16-MAY-19",
            "quality": "gold",
        },
    ),
    (
        "05-28-Start.jpg",
        "day_tc_2019-05-28_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-05-28",
            "start_date": "2019-05-28",
            "valid_until": "2019-05-28",
            "date_print": "28-MAY-19",
            "quality": "gold",
        },
    ),
    (
        "07-03-Start.jpg",
        "day_tc_2019-07-03_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-07-03",
            "start_date": "2019-07-03",
            "valid_until": "2019-07-03",
            "date_print": "03-JLY-19",
            "quality": "gold",
        },
    ),
    (
        "07-04-Start.jpg",
        "day_tc_2019-07-04_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-07-04",
            "start_date": "2019-07-04",
            "valid_until": "2019-07-04",
            "date_print": "04-JLY-19",
            "quality": "gold",
        },
    ),
    (
        "07-18-Picket.jpg",
        "day_tc_2019-07-18_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-07-18",
            "start_date": "2019-07-18",
            "valid_until": "2019-07-18",
            "date_print": "18-JLY-19",
            "quality": "ok",
            "notes": "Left glare; text clear",
        },
    ),
    (
        "09-27-lravelcard.jpg",
        "day_tc_2022-09-27_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2022-09-27",
            "start_date": "2022-09-27",
            "valid_until": "2022-09-27",
            "date_print": "27-SEP-22",
            "quality": "ok",
            "notes": "Finger on edge",
        },
    ),
    (
        "10-29-Start.jpg",
        "day_tc_2019-10-29_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-10-29",
            "start_date": "2019-10-29",
            "valid_until": "2019-10-29",
            "date_print": "29-OCT-19",
            "quality": "gold",
        },
    ),
    (
        "10-30-Start.jpg",
        "day_tc_2019-10-30_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-10-30",
            "start_date": "2019-10-30",
            "valid_until": "2019-10-30",
            "date_print": "30-OCT-19",
            "quality": "gold",
        },
    ),
    (
        "11-08-Start.jpg",
        "day_tc_2019-11-07_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-11-07",
            "start_date": "2019-11-07",
            "valid_until": "2019-11-07",
            "date_print": "07-NOV-19",
            "quality": "gold",
            "notes": "Was misnamed 11-08 from bad OCR",
        },
    ),
    (
        "11-15-Start.jpg",
        "day_tc_2023-11-15_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2023-11-15",
            "start_date": "2023-11-15",
            "valid_until": "2023-11-15",
            "date_print": "15-NOV-23",
            "quality": "gold",
        },
    ),
    (
        "11-21-ricept.jpg",
        "day_tc_2019-11-01_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-11-01",
            "start_date": "2019-11-01",
            "valid_until": "2019-11-01",
            "date_print": "01-NOV-19",
            "quality": "ok",
            "notes": "Centre glare; was misnamed 11-21",
        },
    ),
    # Weekly travelcards — journey_date = start_date
    (
        "02-07-lraelcad.jpg",
        "weekly_2020-01-27_to_2020-02-02_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2020-01-27",
            "start_date": "2020-01-27",
            "valid_until": "2020-02-02",
            "start_print": "27-JNR-20",
            "until_print": "02-FBY-20",
            "quality": "gold",
        },
    ),
    (
        "02-07-TRVLCD.jpg",
        "weekly_2020-01-20_to_2020-01-26_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2020-01-20",
            "start_date": "2020-01-20",
            "valid_until": "2020-01-26",
            "start_print": "20-JNR-20",
            "until_print": "26-JNR-20",
            "quality": "gold",
        },
    ),
    (
        "04-04-Start.jpg",
        "weekly_2019-04-04_to_2019-04-10_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-04-04",
            "start_date": "2019-04-04",
            "valid_until": "2019-04-10",
            "start_print": "04-APR-19",
            "until_print": "10-APR-19",
            "quality": "gold",
        },
    ),
    (
        "09-17-TRVLCD.jpg",
        "weekly_2018-09-11_to_2018-09-17_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-09-11",
            "start_date": "2018-09-11",
            "valid_until": "2018-09-17",
            "start_print": "11-SEP-18",
            "until_print": "17-SEP-18",
            "quality": "gold",
            "notes": "Preferred over 09-17-Travelcard.jpg duplicate",
        },
    ),
    (
        "09-22-raelcord.jpg",
        "weekly_2019-09-16_to_2019-09-22_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-09-16",
            "start_date": "2019-09-16",
            "valid_until": "2019-09-22",
            "start_print": "16-SEP-19",
            "until_print": "22-SEP-19",
            "quality": "ok",
            "notes": "Right-side glare",
        },
    ),
    (
        "09-23-Travelcard.jpg",
        "weekly_2019-09-23_to_2019-09-29_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-09-23",
            "start_date": "2019-09-23",
            "valid_until": "2019-09-29",
            "start_print": "23-SEP-19",
            "until_print": "29-SEP-19",
            "quality": "gold",
        },
    ),
    (
        "09-24-Start.jpg",
        "weekly_2018-09-18_to_2018-09-24_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-09-18",
            "start_date": "2018-09-18",
            "valid_until": "2018-09-24",
            "start_print": "18-SEP-18",
            "until_print": "24-SEP-18",
            "quality": "gold",
        },
    ),
    (
        "09-25-tuPpe.jpg",
        "weekly_2018-09-25_to_2018-10-01_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-09-25",
            "start_date": "2018-09-25",
            "valid_until": "2018-10-01",
            "start_print": "25-SEP-18",
            "until_print": "01-OCT-18",
            "quality": "gold",
        },
    ),
    (
        "10-21-INDDS333.jpg",
        "weekly_2018-10-15_to_2018-10-21_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-10-15",
            "start_date": "2018-10-15",
            "valid_until": "2018-10-21",
            "start_print": "15-OCT-18",
            "until_print": "21-OCT-18",
            "quality": "gold",
        },
    ),
    (
        "10-22-Start.jpg",
        "weekly_2018-10-22_to_2018-10-28_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-10-22",
            "start_date": "2018-10-22",
            "valid_until": "2018-10-28",
            "start_print": "22-OCT-18",
            "until_print": "28-OCT-18",
            "quality": "gold",
            "notes": "Preferred over 10-28-Start.jpg duplicate",
        },
    ),
    (
        "11-05-Start.jpg",
        "weekly_2018-11-05_to_2018-11-11_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-11-05",
            "start_date": "2018-11-05",
            "valid_until": "2018-11-11",
            "start_print": "05-NOV-18",
            "until_print": "11-NOV-18",
            "quality": "gold",
        },
    ),
    (
        "11-21-Start.jpg",
        "weekly_2019-09-30_to_2019-10-06_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-09-30",
            "start_date": "2019-09-30",
            "valid_until": "2019-10-06",
            "start_print": "30-SEP-19",
            "until_print": "06-OCT-19",
            "quality": "gold",
            "notes": "Was misnamed 11-21 from bad OCR",
        },
    ),
]

# Rescued from processed/rejected/unreadable-* (earlier OCR failed; human-readable GOD tickets).
# Skip near-duplicates of ready golden set (same journey week/day already covered).
UNREADABLE_RESCUES: list[tuple[str, str, dict]] = [
    (
        "unreadable-20260716-150152-16thjulytrain.jpg",
        "day_tc_2019-07-16_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-07-16",
            "start_date": "2019-07-16",
            "valid_until": "2019-07-16",
            "date_print": "16-JLY-19",
            "quality": "ok",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-21stmay.jpg",
        "day_tc_2019-05-21_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-05-21",
            "start_date": "2019-05-21",
            "valid_until": "2019-05-21",
            "date_print": "21-MAY-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-june3rd.jpg",
        "day_tc_2019-06-03_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-06-03",
            "start_date": "2019-06-03",
            "valid_until": "2019-06-03",
            "date_print": "03-JUN-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-7thmay.jpg",
        "day_return_2019-05-07_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2019-05-07",
            "date_print": "07-MAY-19",
            "quality": "ok",
            "rescued_from": "unreadable",
            "notes": "Left glare",
        },
    ),
    (
        "unreadable-20260716-150152-5thjulytrain.jpg",
        "day_tc_2019-07-05_god_zones.jpg",
        {
            "kind": "anytime_day_travelcard",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-07-05",
            "start_date": "2019-07-05",
            "valid_until": "2019-07-05",
            "date_print": "05-JLY-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-09-15thsep.jpg",
        "weekly_2019-09-09_to_2019-09-15_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-09-09",
            "start_date": "2019-09-09",
            "valid_until": "2019-09-15",
            "start_print": "09-SEP-19",
            "until_print": "15-SEP-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-11thapril.jpg",
        "weekly_2019-04-11_to_2019-04-17_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-04-11",
            "start_date": "2019-04-11",
            "valid_until": "2019-04-17",
            "start_print": "11-APR-19",
            "until_print": "17-APR-19",
            "quality": "ok",
            "rescued_from": "unreadable",
            "notes": "Left glare",
        },
    ),
    (
        "unreadable-20260716-150152-19thnov.jpg",
        "weekly_2018-11-13_to_2018-11-19_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-11-13",
            "start_date": "2018-11-13",
            "valid_until": "2018-11-19",
            "start_print": "13-NOV-18",
            "until_print": "19-NOV-18",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-2-8sep.jpg",
        "weekly_2019-09-02_to_2019-09-08_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-09-02",
            "start_date": "2019-09-02",
            "valid_until": "2019-09-08",
            "start_print": "02-SEP-19",
            "until_print": "08-SEP-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-4thnov.jpg",
        "weekly_2018-10-29_to_2018-11-04_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2018-10-29",
            "start_date": "2018-10-29",
            "valid_until": "2018-11-04",
            "start_print": "29-OCT-18",
            "until_print": "04-NOV-18",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-20250131_125918.jpg",
        "day_return_2025-01-14_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2025-01-14",
            "date_print": "14-JNR-25",
            "quality": "ok",
            "rescued_from": "unreadable",
            "notes": "Flash glare over GOD text — still readable",
        },
    ),
    (
        "unreadable-20260716-150152-20250131_125928.jpg",
        "day_return_2025-01-09_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2025-01-09",
            "date_print": "09-JNR-25",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-20250131_125938.jpg",
        "day_return_2025-01-08_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2025-01-08",
            "date_print": "08-JNR-25",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-20191215_163215.jpg",
        "weekly_2019-11-11_to_2019-11-17_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2019-11-11",
            "start_date": "2019-11-11",
            "valid_until": "2019-11-17",
            "start_print": "11-NOV-19",
            "until_print": "17-NOV-19",
            "quality": "gold",
            "rescued_from": "unreadable",
        },
    ),
    (
        "unreadable-20260716-150152-20200123_123152.jpg",
        "weekly_2020-01-06_to_2020-01-12_god_zones.jpg",
        {
            "kind": "travelcard_7day",
            "origin": "Godalming",
            "destination": "London Zones 1-6",
            "journey_date": "2020-01-06",
            "start_date": "2020-01-06",
            "valid_until": "2020-01-12",
            "start_print": "06-JNR-20",
            "until_print": "12-JNR-20",
            "quality": "ok",
            "rescued_from": "unreadable",
            "notes": "Glare on GODALMING",
        },
    ),
    (
        "unreadable-20260716-150152-20240726_175456.jpg",
        "day_return_2024-07-26_god_terminals.jpg",
        {
            "kind": "anytime_day_return",
            "portion": "outward",
            "origin": "Godalming",
            "destination": "London Terminals",
            "journey_date": "2024-07-26",
            "date_print": "26-JLY-24",
            "quality": "gold",
            "rescued_from": "unreadable",
            "notes": "Upside-down photo; Off-Peak Day Return",
        },
    ),
]

# True rejects for upload-fail / wrong-doc tests (not journey tickets we want to accept)
REJECT_EXTRA: list[tuple[Path, str, dict]] = [
    (
        SRC / "10-10-Terminals.jpg",
        "reject_multi_ticket_cropped.jpg",
        {
            "kind": "reject",
            "gate": "image_quality",
            "fail_reasons": ["multiple_tickets", "cropped_incomplete"],
            "quality": "reject",
            "notes": "Two tickets; bottom clipped — re-upload single full tickets",
            "source_ready_name": "10-10-Terminals.jpg",
            "transcript": "",
        },
    ),
    (
        REJ / "unreadable-20260716-150152-20241010_084338.jpg",
        "reject_multi_ticket_day_tc.jpg",
        {
            "kind": "reject",
            "gate": "image_quality",
            "fail_reasons": ["multiple_tickets", "cropped_incomplete"],
            "quality": "reject",
            "notes": "Two tickets in frame; bottom clipped",
            "source_rejected_name": "unreadable-…-20241010_084338.jpg",
            "transcript": "",
        },
    ),
    (
        REJ / "unreadable-20260716-150152-20170324_090543.jpg",
        "reject_receipt_not_ticket.jpg",
        {
            "kind": "reject",
            "gate": "content",
            "fail_reasons": ["wrong_document_receipt"],
            "quality": "reject",
            "notes": "NOT VALID FOR TRAVEL receipt — not a journey ticket",
            "transcript": (
                "RECEIPT NOT VALID FOR TRAVEL 2 RAIL TICKETS Date 13-MCH-17 "
                "Amount £17-00 Issuing office LONDON M'BONE Vat Reg no. 667-3877-77"
            ),
        },
    ),
    (
        REJ / "unreadable-20260716-150152-guildfordburgishill.jpg",
        "reject_sales_voucher.jpg",
        {
            "kind": "reject",
            "gate": "content",
            "fail_reasons": ["wrong_document_voucher"],
            "quality": "reject",
            "notes": "Debit/credit sales voucher — no route for claim",
            "transcript": (
                "DEBIT/CREDIT CARD SALES VOUCHER Qty 001 Description TICKET "
                "Total £31.00 Date 29-SEP-17 Issuing Office GUILDFORD "
                "CARDHOLDER'S COPY Authorised Sale Confirmed"
            ),
        },
    ),
    (
        REJ / "unreadable-20260716-150152-Office Lens 20170116-085304.jpg",
        "reject_wrong_route_chesterfield.jpg",
        {
            "kind": "reject",
            "gate": "content",
            "fail_reasons": ["wrong_route", "obstruction_scribble"],
            "quality": "reject",
            "notes": "Chesterfield→London Terminals + ink scribble",
            "transcript": (
                "Off-Peak Return from Chesterfield to London Terminals "
                "Valid 03-JNR-17 until 02-FBY-17 Adult Standard Class"
            ),
        },
    ),
    (
        REJ / "Not_valid_Route-20260716-150152-burgishillchristchurch.jpg",
        "reject_wrong_route_burgess_christchurch.jpg",
        {
            "kind": "reject",
            "gate": "content",
            "fail_reasons": ["wrong_route"],
            "quality": "reject",
            "notes": "Confirmed non-GOD route",
            "transcript": (
                "Anytime Day Return from Guildford to Burgess Hill "
                "Date of travel 16-JUL-2024 Adult Standard Class"
            ),
        },
    ),
]


def _transcript_for(rec: dict) -> str:
    """Synthetic OCR transcript that the parser must accept (contract tests)."""
    origin = rec.get("origin", "")
    dest = rec.get("destination", "")
    kind = rec.get("kind", "")
    if kind == "reject":
        return ""
    if kind == "travelcard_7day":
        return (
            f"Travelcard STD TRVLCD-00M07D Start date {rec['start_print']} "
            f"Valid until {rec['until_print']} "
            f"{origin.upper()} * & {dest.upper()} ANY PERMITTED"
        )
    if kind == "anytime_day_travelcard":
        return (
            f"Day Travelcard STD ANYTIME DAY TC Start date {rec['date_print']} "
            f"Valid until {rec['date_print']} "
            f"{origin.upper()} * & {dest.upper()} ANY PERMITTED"
        )
    # day return / single
    return (
        f"Valid for one journey from {origin} to {dest} "
        f"Date of travel {rec['date_print']} Adult Standard Class"
    )


def _copy_accept(
    src: Path,
    dest_name: str,
    rec: dict,
    expected: dict,
    *,
    source_key: str,
    source_name: str,
) -> None:
    if not src.is_file():
        raise SystemExit(f"Missing source file: {src}")
    dest = DST / dest_name
    shutil.copy2(src, dest)
    entry = dict(rec)
    entry[source_key] = source_name
    entry["transcript"] = _transcript_for(rec)
    expected["accept"][dest_name] = entry
    print(f"accept  {dest_name}")


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"Missing source dir: {SRC}")
    DST.mkdir(parents=True, exist_ok=True)
    # Clear previous accept jpgs so rebuild is authoritative
    for old in DST.glob("*.jpg"):
        old.unlink()
    reject_dir = DST / "reject"
    reject_dir.mkdir(exist_ok=True)
    for old in reject_dir.glob("*"):
        if old.is_file():
            old.unlink()

    expected: dict = {
        "_meta": {
            "description": (
                "Cherry-picked golden ticket photos for parser + future vision OCR. "
                "Includes rescues from earlier 'unreadable' rejects that are human-readable. "
                "Dropped ready dups: 03-26-bodalming, 09-17-Travelcard, 10-28-Start. "
                "Skipped unreadable dups of ready set (e.g. 09-17 week, 07-NOV day TC, 15-NOV-23)."
            ),
            "dropped": [
                "03-26-bodalming.jpg",
                "09-17-Travelcard.jpg",
                "10-28-Start.jpg",
            ],
            "skipped_unreadable_dups": [
                "20180917_143806.jpg",
                "2019_11_21 15_49 Office Lens.jpg",
                "20231115_211213.jpg",
                "20191108_105041.jpg",
            ],
            "reupload_requested": [
                "PDFs (2-8sep.pdf, 2021_10_19 Office Lens.pdf) — convert to JPG/PNG",
                "Multi-ticket frames — one ticket per photo, full card in frame",
            ],
        },
        "accept": {},
        "reject": {},
    }

    for src_name, dest_name, rec in PICKS:
        _copy_accept(
            SRC / src_name,
            dest_name,
            rec,
            expected,
            source_key="source_ready_name",
            source_name=src_name,
        )

    for src_name, dest_name, rec in UNREADABLE_RESCUES:
        _copy_accept(
            REJ / src_name,
            dest_name,
            rec,
            expected,
            source_key="source_rejected_name",
            source_name=src_name,
        )

    for src, dest_name, rec in REJECT_EXTRA:
        if not src.is_file():
            raise SystemExit(f"Missing reject source: {src}")
        dest = reject_dir / dest_name
        shutil.copy2(src, dest)
        expected["reject"][dest_name] = dict(rec)
        print(f"reject  {dest_name}")

    (DST / "expected.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {DST / 'expected.json'}")
    print(f"accept={len(expected['accept'])} reject={len(expected['reject'])}")

    if OLD_DATE_CASES.exists():
        readme = OLD_DATE_CASES / "README.md"
        readme.write_text(
            "Superseded by ``../golden/`` (cherry-picked full set).\n"
            "Kept files here may be removed; use golden/expected.json.\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
