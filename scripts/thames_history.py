#!/usr/bin/env python3
"""Thames Water open data: history back to April 2022 (04_PHASE3_THAMES_BACKTEST_PLAN.md).

    thames_history.py probe [--pages N]   confirm the API contract, the earliest date and the
                                          timezone of `datetime`, by comparing Start alerts with the
                                          discharges we recorded live from the National Storm Overflow Hub
    thames_history.py events              turn the raw alerts into events, map them to Hub overflows and
                                          split them at launch (pre-launch history vs the overlap period)
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
    newest_held = max((r["datetime"] for r in existing), default="")
    print(f"existing rows: {len(existing)} (newest {newest_held or 'none'}); pulling {args.start} .. {args.end}"
          + ("; full walk" if args.full else "; stopping once the archive we already hold is reached"))

    added, page = 0, args.start_offset // PAGE
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
        print(f"    offset {page * PAGE:6}: {len(batch):5} records {min(stamps)} .. {max(stamps)}; new {fresh}",
              flush=True)
        page += 1
        # save as we go: this walks years of history, and an interrupted run must not lose everything
        if page % args.checkpoint_every == 0:
            write_raw(RAW_PATH, list(seen.values()))
            print(f"    checkpoint: {len(seen)} rows written", flush=True)
        if len(batch) < PAGE or min(stamps)[:10] < args.start:
            break
        # Routine runs only need what is new. Once a page is entirely older than the newest row we already
        # hold, everything below it is already in the file, so stop rather than page through years of
        # history (deep offsets are also where the API starts returning empty pages).
        if not args.full and newest_held and max(stamps) < newest_held:
            print(f"    caught up with the archive already held ({newest_held}); stopping", flush=True)
            break

    rows = list(seen.values())
    write_raw(RAW_PATH, rows)
    size = RAW_PATH.stat().st_size
    print(f"rows now {len(rows)} (added {added}); {RAW_PATH.relative_to(ROOT)} {size / 1024 / 1024:.2f} MB")
    if size > 20 * 1024 * 1024:
        print("file is larger than 20 MB — stop and report (plan step 3.2)")
        return 1
    return 0


EVENT_FIELDS = ["event_id", "overflow_key", "company_slug", "start_utc", "end_utc", "duration_min", "source",
                "first_observed_utc", "last_observed_utc", "end_observed"]
OFFLINE_FIELDS = ["overflow_key", "company_slug", "offline_start_utc", "offline_end_utc", "offline_end_source",
                  "first_observed_utc", "last_observed_utc", "source"]
NEAR_DUPLICATE = timedelta(minutes=15)
COORD_MATCH_M = 100.0


def to_utc(stamp):
    """Thames `datetime` has no zone; step 3.1 showed it is UTC (0-minute shift, 223 matches vs 9)."""
    return datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def location_map(alerts):
    """(locationName, permitNumber) -> overflow_key, plus a report of how each was matched."""
    from swt.geo import haversine_km
    import pyproj

    hub = [o for o in read_csv(ROOT / "data" / "overflows.csv") if o["company_slug"] == "thames"]
    by_id = {o["source_id"]: o for o in hub}

    status = get("status", {"limit": PAGE})["items"]
    while True:
        more = get("status", {"limit": PAGE, "offset": len(status)})["items"] if len(status) % PAGE == 0 else []
        if not more:
            break
        status += more
    by_pair = {}
    for s in status:
        if s.get("uniqueId"):
            by_pair.setdefault((s["locationName"], s["permitNumber"]), s["uniqueId"])

    to_wgs84 = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    mapping, how = {}, Counter()
    unmatched = []
    for pair in {(a["locationName"], a["permitNumber"]) for a in alerts}:
        overflow_id = by_pair.get(pair)
        if overflow_id and overflow_id in by_id:
            mapping[pair] = f"thames:{overflow_id}"
            how["by id"] += 1
            continue
        sample = next(a for a in alerts if (a["locationName"], a["permitNumber"]) == pair)
        try:
            lon, lat = to_wgs84.transform(float(sample["x"]), float(sample["y"]))
        except (TypeError, ValueError):
            lon = lat = None
        best = None
        if lat is not None:
            for o in hub:
                if not o["latitude"]:
                    continue
                metres = haversine_km(lat, lon, float(o["latitude"]), float(o["longitude"])) * 1000
                if best is None or metres < best[0]:
                    best = (metres, o["source_id"])
        if best and best[0] <= COORD_MATCH_M:
            mapping[pair] = f"thames:{best[1]}"
            how["by coordinates"] += 1
        else:
            mapping[pair] = f"thames:TWAPI:{pair[0]}"
            how["unmatched"] += 1
            unmatched.append((pair[0], pair[1], f"{best[0]:.0f} m to nearest" if best else "no coordinates"))
    return mapping, how, unmatched


def build_events(alerts, mapping, fetched):
    """Pair Start with the next Stop per location; Start followed by Start closes the first (inferred)."""
    events, offline = [], []
    by_location = defaultdict(list)
    for a in alerts:
        by_location[(a["locationName"], a["permitNumber"])].append(a)

    for pair, records in by_location.items():
        overflow_key = mapping[pair]
        records.sort(key=lambda a: a["datetime"])
        open_start = open_offline = None
        for a in records:
            when = to_utc(a["datetime"])
            kind = a["alertType"]
            if kind == "Start":
                if open_start is not None:       # a Start with no Stop: close it at this one
                    events.append(make_event(overflow_key, open_start, when, False, fetched))
                open_start = when
            elif kind == "Stop":
                if open_start is not None:
                    events.append(make_event(overflow_key, open_start, when, True, fetched))
                    open_start = None
            elif kind == "Offline start":
                open_offline = when
            elif kind == "Offline stop" and open_offline is not None:
                offline.append({"overflow_key": overflow_key, "company_slug": "thames",
                                "offline_start_utc": iso(open_offline), "offline_end_utc": iso(when),
                                "offline_end_source": "feed", "first_observed_utc": fetched,
                                "last_observed_utc": fetched, "source": "thames_api"})
                open_offline = None
        if open_start is not None:               # still discharging at the end of the archive
            events.append(make_event(overflow_key, open_start, None, None, fetched))
        if open_offline is not None:
            offline.append({"overflow_key": overflow_key, "company_slug": "thames",
                            "offline_start_utc": iso(open_offline), "offline_end_utc": "",
                            "offline_end_source": "", "first_observed_utc": fetched,
                            "last_observed_utc": fetched, "source": "thames_api"})
    return events, offline


def make_event(overflow_key, start, end, observed, fetched):
    start_ms = int(start.timestamp() * 1000)
    duration = "" if end is None else str(int((end - start).total_seconds() // 60))
    return {"event_id": f"{overflow_key}:{start_ms}", "overflow_key": overflow_key, "company_slug": "thames",
            "start_utc": iso(start), "end_utc": "" if end is None else iso(end), "duration_min": duration,
            "source": "thames_api", "first_observed_utc": fetched, "last_observed_utc": fetched,
            "end_observed": "" if observed is None else ("true" if observed else "false")}


def events_command(args):
    from swt.io import write_csv
    from swt.timeutil import now_iso

    fetched = now_iso()
    alerts = read_raw(RAW_PATH)
    if not alerts:
        print(f"{RAW_PATH} is missing or empty; run `pull` first", file=sys.stderr)
        return 1
    print(f"alerts: {len(alerts):,} from {min(a['datetime'] for a in alerts)} to "
          f"{max(a['datetime'] for a in alerts)}")

    mapping, how, unmatched = location_map(alerts)
    total = sum(how.values())
    print(f"\n(a) locations mapped: {total}; " + ", ".join(f"{k} {v} ({v / total:.0%})" for k, v in how.items()))
    for name, permit, note in unmatched[:15]:
        print(f"    unmatched: {name} ({permit}) — {note}")

    events, offline = build_events(alerts, mapping, fetched)
    print(f"\nevents built: {len(events):,}; offline periods: {len(offline):,}")

    launch = datetime.strptime(read_json_meta()["launch_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    hub_starts = defaultdict(list)
    for path in sorted((ROOT / "data" / "events").glob("*.csv")):
        for ev in read_csv(path):
            if ev["company_slug"] == "thames":
                hub_starts[ev["overflow_key"]].append(to_utc(ev["start_utc"].rstrip("Z")))

    # Split at launch first. Events from the overlap period are kept whole in events_overlap.csv: matching
    # them against what we recorded live is the validation in check (b). Only the pre-launch history is
    # de-duplicated against the events the Hub seeded us with at launch, so event ids stay unique.
    pre, overlap, dropped = [], [], 0
    for ev in events:
        start = to_utc(ev["start_utc"].rstrip("Z"))
        if start >= launch:
            overlap.append(ev)
            continue
        if any(abs(start - h) <= NEAR_DUPLICATE for h in hub_starts.get(ev["overflow_key"], ())):
            dropped += 1
            continue
        pre.append(ev)

    out = ROOT / "data" / "thames_history"
    write_csv(out / "events_pre_launch.csv", pre, EVENT_FIELDS, lambda r: r["event_id"])
    write_csv(out / "events_overlap.csv", overlap, EVENT_FIELDS, lambda r: r["event_id"])
    write_csv(out / "offline_pre_launch.csv", offline, OFFLINE_FIELDS,
              lambda r: (r["overflow_key"], r["offline_start_utc"]))
    print(f"(c) events dropped as duplicates of Hub rows: {dropped}")
    print(f"    events_pre_launch.csv: {len(pre):,}; events_overlap.csv: {len(overlap):,}")

    # (b) overlap validation against what we recorded live
    matched = 0
    for ev in overlap:
        start = to_utc(ev["start_utc"].rstrip("Z"))
        if any(abs(start - h) <= NEAR_DUPLICATE for h in hub_starts.get(ev["overflow_key"], ())):
            matched += 1
    rate = matched / len(overlap) if overlap else 0
    print(f"(b) overlap validation: {matched} of {len(overlap)} Thames events since launch match a discharge "
          f"we recorded from the Hub within 15 minutes ({rate:.0%}; pass >= 90%)")

    # The overlap window is only as old as our own record, so it is a thin sample. The seeded events are a
    # much larger independent check: at launch the Hub gave us the latest pre-launch discharge for every
    # Thames overflow, and each one should appear in this history.
    api_starts = defaultdict(list)
    for ev in events:
        api_starts[ev["overflow_key"]].append(to_utc(ev["start_utc"].rstrip("Z")))
    seeded = [(key, start) for key, starts in hub_starts.items() for start in starts if start < launch]
    seeded_matched = sum(1 for key, start in seeded
                         if any(abs(start - a) <= NEAR_DUPLICATE for a in api_starts.get(key, ())))
    seeded_rate = seeded_matched / len(seeded) if seeded else 0
    print(f"    seeded-event validation: {seeded_matched} of {len(seeded)} pre-launch Thames discharges the Hub "
          f"gave us at launch appear in this history ({seeded_rate:.0%})")

    hub_ids = {ev["event_id"] for path in sorted((ROOT / "data" / "events").glob("*.csv")) for ev in read_csv(path)}
    clash = hub_ids & {e["event_id"] for e in pre}
    print(f"(d) event_id collisions with data/events: {len(clash)}")

    months = Counter(e["start_utc"][:7] for e in pre)
    print("(e) pre-launch events by month:")
    for month in sorted(months):
        print(f"    {month}: {months[month]}")

    ok = (how["unmatched"] / total <= 0.10) and not clash \
        and (rate >= 0.90 if len(overlap) >= 20 else seeded_rate >= 0.90)
    print("PASS" if ok else "FAIL — GATE 3.3")
    return 0 if ok else 1


def read_json_meta():
    import json
    with open(ROOT / "data" / "meta.json", encoding="utf-8") as f:
        return json.load(f)


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
    q.add_argument("--start-offset", type=int, default=0, help="resume paging from this offset")
    q.add_argument("--checkpoint-every", type=int, default=10, help="write the file every N pages")
    sub.add_parser("events", help="turn the raw alerts into events mapped to Hub overflows")
    q.add_argument("--full", action="store_true",
                   help="walk the whole archive back to --from instead of stopping once caught up")
    args = ap.parse_args()
    try:
        if args.command == "probe":
            return probe(args)
        return events_command(args) if args.command == "events" else pull(args)
    except ThamesError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
