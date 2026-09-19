#!/usr/bin/env python3
"""Thames Water open data: history back to April 2022 (04_PHASE3_THAMES_BACKTEST_PLAN.md).

    thames_history.py probe [--pages N]   confirm the API contract, the earliest date and the
                                          timezone of `datetime`, by comparing Start alerts with the
                                          discharges we recorded live from the National Storm Overflow Hub
    thames_history.py pull --from DATE --to DATE
                                          page back through /alerts into data/thames_history/alerts_raw.csv.gz
                                          (columns as returned plus fetched_utc, de-duplicated, sorted);
                                          re-running only adds rows

The API needs no credentials (verified 19 Sep 2026); 01_SPEC.md §2.6's cloudhub host is dead.
Requests too close together return HTTP 429 or an empty `items` list, so they are paced and retried:
an empty list is never treated as "no data".

Exit codes: 0 ok, 1 inconclusive, 2 network error.
"""
import argparse
import csv
import gzip
import io
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_csv  # noqa: E402

BASE = "https://api.thameswater.co.uk/opendata/v2/discharge"
PAGE = 1000               # the API's maximum; 5000 returns HTTP 500
PACE_SECONDS = 4.0        # requests closer than this start returning 429 or empty lists
OFFSETS_MIN = range(-120, 121, 15)


class ThamesError(Exception):
    pass


def get(path, params, attempts=5):
    """One paced request, retried on 429, 5xx and on a suspicious empty page."""
    last = None
    for attempt in range(attempts):
        time.sleep(PACE_SECONDS)
        try:
            r = requests.get(f"{BASE}/{path}", params=params, timeout=120,
                             headers={"Accept": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()
                payload = r.json()
                if payload.get("items"):
                    return payload
                last = "empty items"
        except (requests.RequestException, ValueError) as e:
            last = str(e)
        time.sleep(2 ** attempt)
    raise ThamesError(f"{path} {params}: {last} after {attempts} attempts")


def page_alerts(pages):
    """Newest-first pages of alerts; returns (items, per-page summary)."""
    items, summary = [], []
    for page in range(pages):
        payload = get("alerts", {"limit": PAGE, "offset": page * PAGE})
        batch = payload["items"]
        items += batch
        stamps = [x["datetime"] for x in batch]
        summary.append((page * PAGE, len(batch), min(stamps), max(stamps)))
        if len(batch) < PAGE:
            break
    return items, summary


RAW_PATH = ROOT / "data" / "thames_history" / "alerts_raw.csv.gz"
RAW_FIELDS = ["datetime", "locationName", "permitNumber", "locationGridRef", "x", "y",
              "receivingWaterCourse", "alertType", "fetched_utc"]


def read_raw(path):
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_raw(path, rows):
    """Deterministic gzip CSV (mtime fixed), sorted by datetime then location."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    rows = sorted(rows, key=lambda r: (r["datetime"], r["locationName"], r["alertType"], r["permitNumber"]))
    with open(tmp, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RAW_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    tmp.replace(path)


def identity(row):
    """Everything the API returned, so an exact duplicate is dropped but a real repeat alert is kept."""
    return tuple(str(row.get(k, "")) for k in RAW_FIELDS if k != "fetched_utc")


def pull(args):
    from swt.timeutil import now_iso

    now = now_iso()
    existing = read_raw(RAW_PATH)
    seen = {identity(r): r for r in existing}
    print(f"existing rows: {len(existing)}; pulling {args.start} .. {args.end}")

    added, page = 0, 0
    while True:
        payload = get("alerts", {"limit": PAGE, "offset": page * PAGE})
        batch = payload["items"]
        stamps = [x["datetime"] for x in batch]
        fresh = 0
        for item in batch:
            if not (args.start <= item["datetime"][:10] <= args.end):
                continue
            row = {k: str(item.get(k, "")) for k in RAW_FIELDS if k != "fetched_utc"}
            row["fetched_utc"] = now
            key = identity(row)
            if key not in seen:
                seen[key] = row
                fresh += 1
        added += fresh
        print(f"    offset {page * PAGE:6}: {len(batch):5} records {min(stamps)} .. {max(stamps)}; new {fresh}")
        page += 1
        if len(batch) < PAGE or min(stamps)[:10] < args.start:
            break

    rows = list(seen.values())
    write_raw(RAW_PATH, rows)
    size = RAW_PATH.stat().st_size
    print(f"rows now {len(rows)} (added {added}); {RAW_PATH.relative_to(ROOT)} {size / 1024 / 1024:.2f} MB")
    if size > 20 * 1024 * 1024:
        print("file is larger than 20 MB — stop and report (plan step 3.2)")
        return 1
    return 0


def probe(args):
    print(f"base {BASE}; paging {PAGE} at a time, {PACE_SECONDS:.0f} s apart")

    status = get("status", {"limit": PAGE})["items"]
    while len(status) % PAGE == 0:
        more = get("status", {"limit": PAGE, "offset": len(status)})["items"]
        status += more
        if len(more) < PAGE:
            break
    print(f"\n/status: {len(status)} overflows; fields: {sorted(status[0])}")
    with_id = [s for s in status if s.get("uniqueId")]
    print(f"    with a uniqueId: {len(with_id)}; statuses: {dict(Counter(s['alertStatus'] for s in status))}")

    # do those ids match the National Storm Overflow Hub ids we already collect?
    ours = {o["source_id"]: o for o in read_csv(ROOT / "data" / "overflows.csv")
            if o["company_slug"] == "thames"}
    shared = {s["uniqueId"] for s in with_id} & set(ours)
    print(f"    Thames overflows we already track by the same id: {len(shared)} of {len(with_id)} "
          f"(we hold {len(ours)} Thames overflows)")

    # alerts carry locationName + permitNumber but no uniqueId, so build the join from /status
    by_pair = defaultdict(set)
    for s in with_id:
        by_pair[(s["locationName"], s["permitNumber"])].add(s["uniqueId"])
    ambiguous = {k: v for k, v in by_pair.items() if len(v) > 1}
    print(f"    (locationName, permitNumber) pairs: {len(by_pair)}; ambiguous (more than one id): {len(ambiguous)}")

    alerts, summary = page_alerts(args.pages)
    print(f"\n/alerts: {len(alerts)} records over {len(summary)} pages; fields: {sorted(alerts[0])}")
    for offset, count, oldest, newest in summary:
        print(f"    offset {offset:6}: {count:5} records, {oldest} .. {newest}")
    print(f"    alert types: {dict(Counter(a['alertType'] for a in alerts))}")
    stamps = [a["datetime"] for a in alerts]
    print(f"    oldest reached: {min(stamps)}; newest: {max(stamps)}")
    print(f"    timezone marker present in datetime: {any(s.endswith('Z') or '+' in s[10:] for s in stamps)}")

    # ---- timezone: compare Start alerts with the discharges we recorded live from the Hub
    hub = defaultdict(list)
    for path in sorted((ROOT / "data" / "events").glob("*.csv")):
        for ev in read_csv(path):
            if ev["company_slug"] == "thames":
                hub[ev["overflow_key"].split(":", 1)[1]].append(
                    datetime.strptime(ev["start_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
    starts = []
    for a in alerts:
        if a["alertType"] != "Start":
            continue
        ids = by_pair.get((a["locationName"], a["permitNumber"]), set())
        if len(ids) != 1:
            continue
        overflow_id = next(iter(ids))
        if overflow_id in hub:
            starts.append((overflow_id, datetime.fromisoformat(a["datetime"]).replace(tzinfo=timezone.utc)))
    print(f"\ntimezone check: {len(starts)} Start alerts belong to overflows we also recorded from the Hub")

    scores = {}
    for shift in OFFSETS_MIN:
        matched = 0
        for overflow_id, stamp in starts:
            shifted = stamp - timedelta(minutes=shift)
            if any(abs((shifted - h).total_seconds()) <= 300 for h in hub[overflow_id]):
                matched += 1
        scores[shift] = matched
    for shift in sorted(scores, key=lambda s: (-scores[s], abs(s)))[:4]:
        print(f"    shift {shift:+4d} min: {scores[shift]} of {len(starts)} Start alerts match a recorded "
              f"discharge within 5 minutes")
    best = max(scores, key=lambda s: (scores[s], -abs(s)))
    if not starts or scores[best] == 0:
        print("INCONCLUSIVE: no overlap yet between Thames alerts and our own recorded discharges")
        return 1
    runner_up = max((s for s in scores if s != best), key=lambda s: scores[s])
    print(f"\nbest shift {best:+d} min ({scores[best]} matches) vs next best {runner_up:+d} min "
          f"({scores[runner_up]} matches)")
    if scores[best] < 2 * max(scores[runner_up], 1):
        print("INCONCLUSIVE: no clear winner — GATE 3.1")
        return 1
    print(f"PASS: Thames `datetime` is {'UTC' if best == 0 else f'UTC{best / 60:+.0f}h (local time)'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe", help="confirm the API contract and the timezone of datetime")
    p.add_argument("--pages", type=int, default=3, help="how many pages of alerts to read (1000 each)")
    q = sub.add_parser("pull", help="page back through /alerts into data/thames_history/alerts_raw.csv.gz")
    q.add_argument("--from", dest="start", default="2022-04-01")
    q.add_argument("--to", dest="end", default=datetime.now(timezone.utc).date().isoformat())
    args = ap.parse_args()
    try:
        return probe(args) if args.command == "probe" else pull(args)
    except ThamesError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
