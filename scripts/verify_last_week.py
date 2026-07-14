"""One-off verification script.

Fetches the GOD->WAT services for the previous Mon-Fri from the live HSP API,
parses the raw responses independently of the pipeline, then runs the pipeline
against the *same* captured data and reports any disagreement.

Usage (from the project root):

    HSP_CREDENTIALS_FILE=creds/trainConfig.txt \
    REQUESTS_CA_BUNDLE=creds/ca-bundle.pem \
    python scripts/verify_last_week.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                              # so `from TrainLine import JsonArgs` works
sys.path.insert(0, os.path.join(ROOT, "TrainLine"))   # so `from LateObject import LateObject` works

import TestFileGenerator as tfg  # noqa: E402
from LateObject import LateObject  # noqa: E402

WINDOW_START = "0700"
WINDOW_END = "0930"
DEPART = "GOD"
ARRIVE = "WAT"


def last_weekdays(today: date) -> list[date]:
    """Return Mon..Fri of the calendar week before `today`."""
    days_since_monday = today.weekday()  # Mon=0, Sun=6
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    return [last_monday + timedelta(days=i) for i in range(5)]


def compute_delay(actual_ta: str, scheduled_pta: str) -> int | None:
    if not actual_ta or not scheduled_pta:
        return None
    return LateObject.calculate_delay(actual_ta, scheduled_pta)


def fetch_week(out_dir: str, days: list[date]) -> None:
    metrics_dir = os.path.join(out_dir, "metrics")
    details_dir = os.path.join(out_dir, "details")
    os.makedirs(metrics_dir, exist_ok=True)
    os.makedirs(details_dir, exist_ok=True)
    metrics_prefix = os.path.join(metrics_dir, "m_")
    details_prefix = os.path.join(details_dir, "d_")

    # writeServiceMetricsTestData walks `days_difference` days back from to_date,
    # so to fetch Mon..Fri pass to_date=Fri, days_difference=5.
    tfg.writeServiceMetricsTestData(
        DEPART, ARRIVE, WINDOW_START, WINDOW_END,
        days[-1], len(days), metrics_prefix,
    )

    rids = tfg.generatePidList(metrics_dir)
    print(f"\n  -> {len(rids)} RIDs returned across the week")
    tfg.writeAttributeMessageTestData(rids, details_prefix)


def parse_raw_truth(details_dir: str) -> dict[str, list[dict]]:
    by_day: dict[str, list[dict]] = {}
    for fname in sorted(os.listdir(details_dir)):
        with open(os.path.join(details_dir, fname)) as fh:
            data = json.load(fh)
        sad = data.get("serviceAttributesDetails")
        if not sad:
            continue
        day = sad.get("date_of_service")
        rid = sad.get("rid")
        locs = sad.get("locations", [])
        god = next((l for l in locs if l.get("location") == DEPART), None)
        wat = next((l for l in locs if l.get("location") == ARRIVE), None)
        if not god or not wat:
            continue
        by_day.setdefault(day, []).append({
            "rid": rid,
            "god_ptd": god.get("gbtt_ptd", ""),
            "god_pta": god.get("gbtt_pta", ""),
            "god_actual_ta": god.get("actual_ta", ""),
            "god_delay": compute_delay(god.get("actual_ta", ""),
                                       god.get("gbtt_pta", "")),
            "wat_pta": wat.get("gbtt_pta", ""),
            "wat_actual_ta": wat.get("actual_ta", ""),
            "wat_delay": compute_delay(wat.get("actual_ta", ""),
                                       wat.get("gbtt_pta", "")),
            "wat_reason": wat.get("late_canc_reason", ""),
        })
    for services in by_day.values():
        services.sort(key=lambda s: s["god_ptd"])
    return by_day


def run_pipeline(details_dir: str) -> dict:
    all_details = tfg.generateAttrbuteDictionary(details_dir)
    route_dict = tfg.trimToRouteOnlyDictionary(all_details, DEPART, ARRIVE)
    return tfg.getLatestTrainObject(route_dict)


def report(days: list[date], by_day: dict, pipeline_out: dict) -> int:
    """Print a per-day comparison; return number of discrepancies found."""
    discrepancies = 0
    print("\n" + "=" * 78)
    print(f"Verification: {DEPART}->{ARRIVE} {WINDOW_START}-{WINDOW_END} "
          f"for {days[0]}..{days[-1]}")
    print("=" * 78)

    for d in days:
        ds = d.isoformat()
        services = by_day.get(ds, [])
        print(f"\n--- {ds} ({d.strftime('%A')}) ---")
        if not services:
            print("  (no GOD/WAT services returned by HSP for this day)")
            continue

        print(f"  {'rid':>15}  {'god_ptd':>7}  "
              f"{'GOD':>5}  {'WAT':>5}  reason")
        for s in services:
            god = "-" if s["god_delay"] is None else f"{s['god_delay']:>3}m"
            wat = "-" if s["wat_delay"] is None else f"{s['wat_delay']:>3}m"
            print(f"  {s['rid']:>15}  {s['god_ptd']:>7}  "
                  f"{god:>5}  {wat:>5}  {s['wat_reason']}")

        # Raw ground truth — worst WAT delay across services with valid data.
        worst = max(
            (s for s in services if s["wat_delay"] is not None),
            key=lambda s: s["wat_delay"],
            default=None,
        )
        if worst is None:
            raw_summary = "(no service has both gbtt_pta and actual_ta at WAT)"
        else:
            raw_summary = (f"train {worst['god_ptd']} (rid {worst['rid']}), "
                           f"{worst['wat_delay']} min late at WAT")

        # Pipeline output for the day.
        pair = pipeline_out.get(ds)
        if pair is None:
            pipe_summary = "no row written"
        else:
            depart = pair[0] if pair[0].departureStation else pair[1]
            arrive = pair[0] if not pair[0].departureStation else pair[1]
            pipe_summary = (f"train {depart.gbtt_ptd}, "
                            f"{arrive.delay_time} min late at WAT")

        print(f"  RAW worst:        {raw_summary}")
        print(f"  PIPELINE picked:  {pipe_summary}")

        # Diagnose disagreements.
        if pair is None and worst is not None and worst["wat_delay"] > 1:
            discrepancies += 1
            # Why did the pipeline drop the day? Check the >1 min threshold at
            # GOD for the worst service (and any others that beat 1 min at WAT).
            reasons = []
            late_at_wat = [s for s in services
                           if s["wat_delay"] is not None and s["wat_delay"] > 1]
            for s in late_at_wat:
                if s["god_delay"] is None or s["god_delay"] <= 1:
                    reasons.append(
                        f"    - train {s['god_ptd']} ({s['wat_delay']} min "
                        f"late at WAT) dropped: GOD delay = {s['god_delay']} "
                        f"(needs > 1)")
            for line in reasons:
                print(f"  DISCREPANCY:")
                print(line)

        elif pair is not None and worst is not None:
            arrive = pair[0] if not pair[0].departureStation else pair[1]
            if arrive.delay_time != worst["wat_delay"]:
                discrepancies += 1
                print("  DISCREPANCY:")
                print(f"    Pipeline reports {arrive.delay_time} min but raw "
                      f"worst is {worst['wat_delay']} min — different train "
                      f"picked.")

    print("\n" + "=" * 78)
    print(f"Total discrepancies: {discrepancies}")
    print("=" * 78)
    return discrepancies


def main() -> int:
    today = date.today()
    days = last_weekdays(today)
    print(f"Verifying {DEPART}->{ARRIVE} for "
          f"{days[0]} ({days[0].strftime('%A')}) "
          f"to {days[-1]} ({days[-1].strftime('%A')}).")
    out_dir = os.path.join(ROOT, "verify-out")
    fetch_week(out_dir, days)
    by_day = parse_raw_truth(os.path.join(out_dir, "details"))
    pipeline_out = run_pipeline(os.path.join(out_dir, "details"))
    report(days, by_day, pipeline_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
