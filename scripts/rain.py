#!/usr/bin/env python3
"""EA Hydrology API rainfall -> daily per-gauge totals (01_SPEC.md §6).

--refresh-gauges rewrites data/rain/gauges.csv from the stations endpoint (stations with a
15-minute rainfall measure and coordinates). Then, for every gauge, one readings request covers
the N UTC days before today; data/rain/daily/{date}.csv is rewritten for each of those days.
Hydrology `dateTime` values carry no time zone and are treated as UTC (verified at step 1.8).

Exit codes: 0 ok (gauges that still fail after retries are listed and their existing rows kept),
1 gauges.csv missing without --refresh-gauges, 2 network error (stations list or every gauge failed).
"""
import argparse
import csv
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_csv, write_csv  # noqa: E402
from swt.timeutil import now_iso  # noqa: E402

API = "https://environment.data.gov.uk/hydrology/id"
MEASURE_SUFFIX = "-rainfall-t-900-mm-qualified"
MAX_REQUESTS_PER_SECOND = 5
RETRY_STATUSES = {403, 429}

GAUGE_FIELDS = ["gauge_id", "measure_id", "label", "latitude", "longitude", "date_opened", "fetched_utc"]
DAILY_FIELDS = ["date", "gauge_id", "total_mm", "max15_mm", "n_readings", "n_unchecked", "n_good",
                "n_other_quality", "fetched_utc"]


class RateLimiter:
    def __init__(self, per_second):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_start)
            self.next_start = start + self.interval
        time.sleep(max(0.0, start - now))


def http_get(url, params, limiter):
    """GET with three retries and backoff on 5xx, 403/429 (the API refuses some requests under load, then
    serves the same URL normally) or connection errors. Returns a Response or raises."""
    last = None
    for attempt in range(4):
        limiter.wait()
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code < 500 and r.status_code not in RETRY_STATUSES:
                r.raise_for_status()
                return r
            last = f"{r.status_code} {r.reason}"
        except requests.HTTPError:
            raise
        except requests.RequestException as e:
            last = str(e)
        if attempt < 3:
            time.sleep(2 ** (attempt + 1))
    raise requests.RequestException(f"{url}: {last}")


def with_unchanged_fetched_utc(new_row, old_row, now):
    """Keep the previous fetched_utc when nothing else in the row changed, so unchanged data makes no diff."""
    if old_row and all(old_row.get(k) == v for k, v in new_row.items()):
        return dict(new_row, fetched_utc=old_row["fetched_utc"])
    return dict(new_row, fetched_utc=now)


# ---------------------------------------------------------------- gauges

def refresh_gauges(gauges_path, limiter, now):
    r = http_get(f"{API}/stations", {"observedProperty": "rainfall", "_limit": 5000}, limiter)
    items = r.json()["items"]
    old = {g["gauge_id"]: g for g in read_csv(gauges_path)}
    rows = []
    for station in items:
        measures = [m["@id"] if isinstance(m, dict) else m for m in station.get("measures") or []]
        measure = next((m.rsplit("/", 1)[-1] for m in measures if m.endswith(MEASURE_SUFFIX)), None)
        if measure is None or station.get("lat") is None or station.get("long") is None:
            continue
        row = {"gauge_id": station["notation"], "measure_id": measure, "label": station.get("label") or "",
               "latitude": f"{float(station['lat']):.6f}", "longitude": f"{float(station['long']):.6f}",
               "date_opened": station.get("dateOpened") or ""}
        rows.append(with_unchanged_fetched_utc(row, old.get(row["gauge_id"]), now))
    write_csv(gauges_path, rows, GAUGE_FIELDS, lambda g: g["gauge_id"])
    print(f"stations listed={len(items)} gauges kept={len(rows)}")
    return rows


# ---------------------------------------------------------------- readings

def decimal_text(d):
    return format(d.normalize(), "f")


def aggregate(csv_text, days):
    """Per-day aggregates for one gauge from a readings CSV. Returns (dict day -> row fields, duplicates)."""
    acc = {}
    seen = set()
    duplicates = 0
    for rec in csv.DictReader(io.StringIO(csv_text)):
        stamp = rec["dateTime"]
        day = stamp[:10]
        if day not in days:
            continue
        if stamp in seen:
            duplicates += 1
            continue
        seen.add(stamp)
        a = acc.setdefault(day, {"total": Decimal(0), "max": None, "n": 0, "unchecked": 0, "good": 0, "other": 0})
        if rec["value"] in ("", "null"):
            continue
        try:
            value = Decimal(rec["value"])
        except InvalidOperation:
            a["other"] += 1
            continue
        if value < 0:
            a["other"] += 1
            continue
        a["total"] += value
        a["max"] = value if a["max"] is None else max(a["max"], value)
        a["n"] += 1
        quality = rec.get("quality", "")
        if quality == "Unchecked":
            a["unchecked"] += 1
        elif quality == "Good":
            a["good"] += 1
        else:
            a["other"] += 1
    out = {}
    for day, a in acc.items():
        if a["n"] == 0 and a["other"] == 0:
            continue
        out[day] = {"total_mm": decimal_text(a["total"]),
                    "max15_mm": "" if a["max"] is None else decimal_text(a["max"]),
                    "n_readings": str(a["n"]), "n_unchecked": str(a["unchecked"]), "n_good": str(a["good"]),
                    "n_other_quality": str(a["other"])}
    return out, duplicates


def fetch_gauge(gauge, first_day, end_day, days, limiter):
    params = {"mineq-date": first_day.isoformat(), "max-date": end_day.isoformat(), "_format": "csv",
              "_limit": 100000}
    try:
        r = http_get(f"{API}/measures/{gauge['measure_id']}/readings", params, limiter)
        return gauge["gauge_id"], aggregate(r.text, days), None
    except (requests.RequestException, KeyError, csv.Error) as e:
        return gauge["gauge_id"], None, str(e)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--refresh-gauges", action="store_true", help="rewrite gauges.csv from the stations endpoint")
    ap.add_argument("--days", type=int, default=15, help="number of UTC days before today to fetch (default 15)")
    ap.add_argument("--range", nargs=2, metavar=("START", "END"),
                    help="fetch a historic window instead: START inclusive, END exclusive (phase 3)")
    args = ap.parse_args()

    data = Path(args.data)
    gauges_path = data / "rain" / "gauges.csv"
    daily_dir = data / "rain" / "daily"
    now = now_iso()
    limiter = RateLimiter(MAX_REQUESTS_PER_SECOND)

    if args.refresh_gauges:
        try:
            gauges = refresh_gauges(gauges_path, limiter, now)
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"network error listing stations: {e}", file=sys.stderr)
            return 2
    else:
        gauges = read_csv(gauges_path)
        if not gauges:
            print(f"{gauges_path} is missing or empty; run with --refresh-gauges", file=sys.stderr)
            return 1

    if args.range:
        try:
            first_day = datetime.strptime(args.range[0], "%Y-%m-%d").date()
            today = datetime.strptime(args.range[1], "%Y-%m-%d").date()   # exclusive, like max-date
        except ValueError:
            print("--range takes two YYYY-MM-DD dates", file=sys.stderr)
            return 1
        if today <= first_day:
            print("--range END must be after START", file=sys.stderr)
            return 1
    else:
        today = datetime.now(timezone.utc).date()
        first_day = today - timedelta(days=args.days)
    span = (today - first_day).days
    day_list = [(first_day + timedelta(days=i)).isoformat() for i in range(span)]
    days = set(day_list)

    with ThreadPoolExecutor(max_workers=MAX_REQUESTS_PER_SECOND) as pool:
        results = list(pool.map(lambda g: fetch_gauge(g, first_day, today, days, limiter), gauges))

    failed = {gid: err for gid, _, err in results if err}
    fetched = {gid: res for gid, res, err in results if not err}
    duplicates = sum(res[1] for res in fetched.values())
    if not fetched:
        print("network error: every gauge failed", file=sys.stderr)
        return 2

    for day in day_list:
        path = daily_dir / f"{day}.csv"
        old = {r["gauge_id"]: r for r in read_csv(path)}
        rows = [r for gid, r in old.items() if gid in failed]
        for gid, (per_day, _) in fetched.items():
            if day in per_day:
                row = dict({"date": day, "gauge_id": gid}, **per_day[day])
                rows.append(with_unchanged_fetched_utc(row, old.get(gid), now))
        write_csv(path, rows, DAILY_FIELDS, lambda r: r["gauge_id"])

    print(f"window {day_list[0]}..{day_list[-1]} gauges={len(gauges)} fetched={len(fetched)} failed={len(failed)} "
          f"duplicate_timestamps_skipped={duplicates}")
    for gid, err in sorted(failed.items()):
        print(f"failed {gid}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
