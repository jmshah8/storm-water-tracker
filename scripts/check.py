#!/usr/bin/env python3
"""Checks from the build plan, by step id: python scripts/check.py --step 1.8

Exit codes: 0 check passed, 1 check failed or inconclusive, 2 network error.
"""
import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_csv  # noqa: E402

HYDROLOGY = "https://environment.data.gov.uk/hydrology/id"
FLOOD_MONITORING = "https://environment.data.gov.uk/flood-monitoring/id"


class NetworkError(Exception):
    pass


def get_json(url, params=None):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code in (403, 429) or r.status_code >= 500:
                last = f"{r.status_code} {r.reason}"
            else:
                r.raise_for_status()
                return r.json()
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as e:
            last = str(e)
        time.sleep(2 ** (attempt + 1))
    raise NetworkError(f"{url}: {last}")


# ---------------------------------------------------------------- step 1.8

MIN_GAUGES = 5
MIN_DAY_TOTAL_MM = 5.0
OFFSETS_MIN = range(-120, 121, 15)
RT_MEASURE_SUFFIX = "-rainfall-tipping_bucket_raingauge-t-15_min-mm"


def is_bst(day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=ZoneInfo("Europe/London")).utcoffset() != timedelta(0)


def series(items, stamp_key, tz_suffix):
    """{UTC datetime: value} from API items; Hydrology stamps have no zone and are read as UTC here."""
    out = {}
    for item in items:
        value = item.get("value")
        if value is None or value == "":
            continue
        stamp = item[stamp_key]
        if tz_suffix and not stamp.endswith("Z"):
            raise ValueError(f"real-time timestamp without Z: {stamp}")
        out[datetime.fromisoformat(stamp.rstrip("Z")).replace(tzinfo=timezone.utc)] = float(value)
    return out


def best_offset(rt, hy, day):
    """For each shift o, compare real-time slot t with Hydrology stamp t - o over the 96 slots of `day`."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    slots = [start + timedelta(minutes=15 * i) for i in range(96)]
    scores = {}
    for o in OFFSETS_MIN:
        pairs = [(rt[t], hy[t - timedelta(minutes=o)]) for t in slots if t in rt and t - timedelta(minutes=o) in hy]
        if len(pairs) < 80:
            continue
        diff = sum(abs(a - b) for a, b in pairs)
        exact = sum(1 for a, b in pairs if abs(a - b) < 1e-6)
        scores[o] = (round(diff, 3), exact, len(pairs))
    if not scores:
        return None, scores
    ranked = sorted(scores, key=lambda o: (scores[o][0], -scores[o][1]))
    if len(ranked) > 1 and scores[ranked[0]][0] == scores[ranked[1]][0]:
        return "tie", scores
    return ranked[0], scores


def step_1_8(args):
    gauges = read_csv(ROOT / "data" / "rain" / "gauges.csv")
    hy_stations = get_json(f"{HYDROLOGY}/stations", {"observedProperty": "rainfall", "_limit": 5000})["items"]
    ref_by_gauge = {s["notation"]: s.get("stationReference") for s in hy_stations}
    rt_stations = get_json(f"{FLOOD_MONITORING}/stations", {"parameter": "rainfall", "_limit": 5000})["items"]
    rt_measure = {}
    for s in rt_stations:
        measures = s.get("measures") or []
        measures = measures if isinstance(measures, list) else [measures]
        for m in measures:
            mid = m["@id"] if isinstance(m, dict) else m
            if mid.endswith(RT_MEASURE_SUFFIX) and s.get("stationReference"):
                rt_measure[s["stationReference"]] = mid.rsplit("/", 1)[-1]
    matched = {g["gauge_id"]: g for g in gauges if ref_by_gauge.get(g["gauge_id"]) in rt_measure}
    print(f"Hydrology gauges: {len(gauges)}; real-time 15-min total measures: {len(rt_measure)}; "
          f"matched by stationReference: {len(matched)}")

    today = datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=27)
    chosen_day, candidates = None, []
    for path in sorted((ROOT / "data" / "rain" / "daily").glob("*.csv"), reverse=True):
        day = date.fromisoformat(path.stem)
        if day < earliest or day >= today - timedelta(days=1) or not is_bst(day):
            continue
        wet = [r for r in read_csv(path) if r["gauge_id"] in matched and int(r["n_readings"]) == 96
               and float(r["total_mm"]) >= MIN_DAY_TOTAL_MM]
        if len(wet) >= MIN_GAUGES:
            chosen_day = day
            candidates = sorted(wet, key=lambda r: -float(r["total_mm"]))
            break
    if chosen_day is None:
        print("INCONCLUSIVE: no BST day inside the real-time window with >= 5 matched gauges recording >= 5 mm")
        return 1
    print(f"sample day: {chosen_day} (BST in effect: {is_bst(chosen_day)}); "
          f"{len(candidates)} matched gauges with >= {MIN_DAY_TOTAL_MM} mm and 96 readings")

    results = []
    for row in candidates:
        if len(results) >= 8:
            break
        gauge = matched[row["gauge_id"]]
        ref = ref_by_gauge[gauge["gauge_id"]]
        rt_items = []
        for d in (chosen_day - timedelta(days=1), chosen_day, chosen_day + timedelta(days=1)):
            url = f"{FLOOD_MONITORING}/measures/{rt_measure[ref]}/readings"
            rt_items += get_json(url, {"date": d.isoformat(), "_limit": 500})["items"]
        hy_url = f"{HYDROLOGY}/measures/{gauge['measure_id']}/readings"
        hy_params = {"mineq-date": (chosen_day - timedelta(days=1)).isoformat(),
                     "max-date": (chosen_day + timedelta(days=2)).isoformat(), "_limit": 2000}
        hy_items = get_json(hy_url, hy_params)["items"]
        rt, hy = series(rt_items, "dateTime", True), series(hy_items, "dateTime", False)
        day_start = datetime(chosen_day.year, chosen_day.month, chosen_day.day, tzinfo=timezone.utc)
        rt_total = sum(v for t, v in rt.items() if day_start <= t < day_start + timedelta(days=1))
        if rt_total < MIN_DAY_TOTAL_MM:
            print(f"  skip {gauge['label']} ({ref}): real-time total {rt_total:.1f} mm < {MIN_DAY_TOTAL_MM} mm")
            continue
        offset, scores = best_offset(rt, hy, chosen_day)
        if offset is None:
            print(f"  skip {gauge['label']} ({ref}): too few overlapping readings")
            continue
        s0, s60 = scores.get(0), scores.get(60)
        print(f"  {gauge['label']} (ref {ref}): real-time {rt_total:.1f} mm, Hydrology {row['total_mm']} mm; "
              f"best offset = {offset if offset == 'tie' else f'{offset:+d} min'}; "
              f"at 0 h |diff|={s0[0]} mm exact {s0[1]}/{s0[2]}; at +1 h |diff|={s60[0]} mm exact {s60[1]}/{s60[2]}")
        print(f"    real-time: {FLOOD_MONITORING}/measures/{rt_measure[ref]}/readings?date={chosen_day}")
        print(f"    hydrology: {hy_url}?mineq-date={hy_params['mineq-date']}&max-date={hy_params['max-date']}")
        results.append(offset)

    print(f"gauges compared: {len(results)}; offsets: {results}")
    if len(results) < MIN_GAUGES:
        print(f"INCONCLUSIVE: fewer than {MIN_GAUGES} gauges could be compared")
        return 1
    if len(set(results)) == 1 and results[0] == 0:
        print(f"PASS: Hydrology API dateTime confirmed UTC on {chosen_day} (BST day)")
        return 0
    print("NOT CONFIRMED: offsets are not all 0 h — GATE 1.8")
    return 1


STEPS = {"1.8": step_1_8}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", required=True, choices=sorted(STEPS))
    args = ap.parse_args()
    try:
        return STEPS[args.step](args)
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
