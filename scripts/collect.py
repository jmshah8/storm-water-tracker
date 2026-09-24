#!/usr/bin/env python3
"""Poll the ten storm-overflow feeds, detect changes and upsert events (01_SPEC.md §4).

Writes data/overflows.csv, data/status_snapshot.json, data/events/YYYY-MM.csv,
data/offline/YYYY-MM.csv and (on the first ever run) data/meta.json launch_utc.

Exit codes: 0 ok (with or without changes), 2 network/parse error or schema drift.
"""
import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sources  # noqa: E402
from swt.io import read_csv, read_json, write_csv, write_json  # noqa: E402
from swt.timeutil import iso_to_ms, ms_to_iso, now_iso  # noqa: E402

RULE_VERSION = "dry-day-v1"
NEAR_DUPLICATE_MS = 15 * 60 * 1000

OVERFLOW_FIELDS = ["overflow_key", "company_slug", "company_name", "source_id", "latitude", "longitude",
                   "receiving_watercourse", "first_seen_utc", "last_seen_utc"]
EVENT_FIELDS = ["event_id", "overflow_key", "company_slug", "start_utc", "end_utc", "duration_min", "source",
                "first_observed_utc", "last_observed_utc", "end_observed"]
OFFLINE_FIELDS = ["overflow_key", "company_slug", "offline_start_utc", "offline_end_utc", "offline_end_source",
                  "first_observed_utc", "last_observed_utc"]
# Only what change detection needs, times cut to whole seconds: some feeds add random milliseconds to
# unchanged times on every refresh, and LastUpdated is re-stamped on every refresh (GATE 1 decision).
SNAPSHOT_FIELDS = ["status", "status_start_ms", "latest_event_start_ms", "latest_event_end_ms"]
# South West Water's service answered "Retry after 60 sec" on 2026-09-24; wait that long when the
# server does not name a figure itself. The cap keeps a poll inside the workflow's 10-minute timeout.
RATE_LIMIT_WAIT_S = 60
RATE_LIMIT_MAX_WAIT_S = 90
# A whole poll may spend at most this long waiting out rate limits. Polls run in their own lane with
# cancel-in-progress false, so a run that crawled towards the 10-minute job timeout would delay the
# next poll behind it. Better to give up, exit 2 and let the next run ten minutes later try again.
RATE_LIMIT_BUDGET_S = 180
_rate_limit_spent = 0.0


class FetchError(Exception):
    """A 4xx that means the dataset itself has moved — worth re-resolving the layer."""


class RateLimited(Exception):
    """A 429. The layer is fine; the server is asking us to slow down, so wait rather than re-resolve."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ---------------------------------------------------------------- fetching

def retry_after_seconds(response):
    """The server's own Retry-After, when it sends one. Seconds only; these services do not send dates."""
    try:
        value = float(response.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def spend_rate_limit_wait(retry_after):
    """Wait out a rate limit if this run can still afford to. False means the budget is gone."""
    global _rate_limit_spent
    wait = min(retry_after or RATE_LIMIT_WAIT_S, RATE_LIMIT_MAX_WAIT_S)
    if _rate_limit_spent + wait > RATE_LIMIT_BUDGET_S:
        return False
    _rate_limit_spent += wait
    time.sleep(wait)
    return True


def query_page(layer_url, offset, count):
    params = {"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json",
              "resultOffset": offset, "resultRecordCount": count}
    last = None
    for attempt in range(3):
        try:
            r = requests.get(layer_url + "/query", params=params, timeout=60)
            # 429 is the company's own ArcGIS quota, not a broken layer: it arrives both as an HTTP
            # status and, on some of these services, as HTTP 200 carrying an error object. Either way
            # the right answer is to wait the time the server asks for, not to re-resolve the dataset.
            if r.status_code == 429:
                raise RateLimited("HTTP 429", retry_after_seconds(r))
            if 400 <= r.status_code < 500:
                raise FetchError(f"HTTP {r.status_code}")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                code = int(data["error"].get("code", 0))
                if code == 429:
                    raise RateLimited(f"ArcGIS error {data['error']}", retry_after_seconds(r))
                if 400 <= code < 500:
                    raise FetchError(f"ArcGIS error {data['error']}")
                raise ValueError(f"ArcGIS error {data['error']}")
            return data
        except FetchError:
            raise
        except RateLimited as e:
            last = e
            if attempt == 2 or not spend_rate_limit_wait(e.retry_after):
                break
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 ** (attempt + 1))
    raise OSError(f"{layer_url}: {last}")


def fetch_company(slug, src):
    """Return (source entry used, list of attribute dicts). Re-resolves once on a 4xx."""
    for attempt in range(2):
        try:
            features, offset = [], 0
            while True:
                page = query_page(src["layer_url"], offset, src["max_record_count"])
                batch = page.get("features") or []
                features.extend(f["attributes"] for f in batch)
                offset += len(batch)
                if not page.get("exceededTransferLimit") or not batch:
                    return src, features
        except FetchError as e:
            if attempt == 1:
                raise OSError(f"{slug}: {e} after re-resolving")
            print(f"{slug}: {e}; re-resolving the dataset", file=sys.stderr)
            src = sources.resolve_one(slug, src["company_name"], src["item_id"])


# ---------------------------------------------------------------- normalising

def normalise(slug, attrs, field_map):
    def get(logical):
        return attrs.get(field_map[logical])

    def as_int(v):
        return None if v is None else int(v)

    lat, lon = get("Latitude"), get("Longitude")
    return {
        "overflow_key": f"{slug}:{get('Id')}",
        "source_id": str(get("Id")),
        "status": as_int(get("Status")),
        "status_start_ms": as_int(get("StatusStart")),
        "latest_event_start_ms": as_int(get("LatestEventStart")),
        "latest_event_end_ms": as_int(get("LatestEventEnd")),
        "latitude": "" if lat is None else f"{float(lat):.6f}",
        "longitude": "" if lon is None else f"{float(lon):.6f}",
        "receiving_watercourse": "" if get("ReceivingWaterCourse") is None else str(get("ReceivingWaterCourse")),
    }


def whole_second(ms):
    return None if ms is None else ms - ms % 1000


def duration_min(start_ms, end_ms):
    return str((end_ms - start_ms + 30000) // 60000)


# ---------------------------------------------------------------- the run

def month_of(iso):
    return iso[:7]


def load_rows(directory):
    rows = []
    for path in sorted(Path(directory).glob("*.csv")):
        rows.extend(read_csv(path))
    return rows


def write_by_month(directory, rows, fieldnames, month_fields, sort_key):
    """File each row by the UTC month of the first non-empty field in month_fields."""
    directory = Path(directory)
    groups = defaultdict(list)
    for row in rows:
        groups[month_of(next(row[f] for f in month_fields if row[f]))].append(row)
    for path in directory.glob("*.csv"):
        if path.stem not in groups:
            path.unlink()
    for month, month_rows in groups.items():
        write_csv(directory / f"{month}.csv", month_rows, fieldnames, sort_key)


def run(data_dir, srcs, feeds, now, stats):
    """Apply one poll. `feeds` maps company_slug -> list of attribute dicts."""
    data_dir = Path(data_dir)

    meta = read_json(data_dir / "meta.json")
    if meta is None:
        meta = {"launch_utc": None, "rule_version": RULE_VERSION, "site_url": ""}
    if meta.get("launch_utc") is None:
        meta["launch_utc"] = now

    overflows = {r["overflow_key"]: r for r in read_csv(data_dir / "overflows.csv")}
    snapshot = read_json(data_dir / "status_snapshot.json", default={})
    events = load_rows(data_dir / "events")
    offline = load_rows(data_dir / "offline")

    events_by_overflow = defaultdict(list)
    for ev in events:
        # An end earlier than its start is never kept (GATE 1 decision). A start re-timed past an end already
        # stored can create one at any time, including on events the feeds have since moved past, so every
        # event is checked on every run.
        if ev["end_utc"] and iso_to_ms(ev["end_utc"]) < iso_to_ms(ev["start_utc"]):
            ev["end_utc"] = ev["duration_min"] = ev["end_observed"] = ""
            stats["ends_before_start_cleared"] += 1
        events_by_overflow[ev["overflow_key"]].append(ev)
    offline_by_overflow = defaultdict(list)
    for period in offline:
        offline_by_overflow[period["overflow_key"]].append(period)

    for slug in sorted(feeds):
        src = srcs[slug]
        records = feeds[slug]
        stats[f"fetched:{slug}"] = len(records)
        if records:
            missing = [lg for lg, actual in src["field_map"].items() if actual not in records[0]]
            if missing:
                raise KeyError(f"{slug}: mapped field(s) absent from the feed: "
                               + ", ".join(f"{lg} ({src['field_map'][lg]})" for lg in missing))
        seen = {}
        for attrs in records:
            rec = normalise(slug, attrs, src["field_map"])
            key = rec["overflow_key"]
            if key in seen:
                stats["duplicate_id_records_skipped"] += 1
                if seen[key] != rec:
                    stats["duplicate_id_records_differing"] += 1
                continue
            seen[key] = rec
            apply_record(slug, src, rec, overflows, snapshot, events_by_overflow, offline_by_overflow, now,
                         stats)

    return meta, overflows, snapshot, events_by_overflow, offline_by_overflow


def apply_record(slug, src, rec, overflows, snapshot, events_by_overflow, offline_by_overflow, now, stats):
    key = rec["overflow_key"]
    core = {"status": rec["status"]}
    core.update({k: whole_second(rec[k]) for k in SNAPSHOT_FIELDS if k != "status"})
    previous = snapshot.get(key)

    # 4.2 overflows
    row = overflows.get(key)
    if row is None:
        overflows[key] = {"overflow_key": key, "company_slug": slug, "company_name": src["company_name"],
                          "source_id": rec["source_id"], "latitude": rec["latitude"],
                          "longitude": rec["longitude"], "receiving_watercourse": rec["receiving_watercourse"],
                          "first_seen_utc": now, "last_seen_utc": now}
        stats["new_overflows"] += 1
    else:
        changed = previous is None or any(previous.get(k) != core[k] for k in SNAPSHOT_FIELDS)
        for field in ("latitude", "longitude", "receiving_watercourse"):
            if row[field] != rec[field]:
                row[field] = rec[field]
                changed = True
        if changed:
            row["last_seen_utc"] = now
    snapshot[key] = core

    # 4.3 / 4.4 events
    start_ms, end_ms = rec["latest_event_start_ms"], rec["latest_event_end_ms"]
    if start_ms is not None:
        overflow_events = events_by_overflow[key]
        near = [ev for ev in overflow_events if abs(iso_to_ms(ev["start_utc"]) - start_ms) <= NEAR_DUPLICATE_MS]
        if near:
            event = min(near, key=lambda ev: (abs(iso_to_ms(ev["start_utc"]) - start_ms), ev["event_id"]))
            changed = False
            if event["start_utc"] != ms_to_iso(start_ms):
                event["start_utc"] = ms_to_iso(start_ms)
                if event["end_utc"]:
                    event["duration_min"] = duration_min(start_ms, iso_to_ms(event["end_utc"]))
                stats["retimed_starts"] += 1
                changed = True
        else:
            event = {"event_id": f"{key}:{start_ms}", "overflow_key": key, "company_slug": slug,
                     "start_utc": ms_to_iso(start_ms), "end_utc": "", "duration_min": "", "source": "hub",
                     "first_observed_utc": now, "last_observed_utc": now, "end_observed": ""}
            overflow_events.append(event)
            stats["new_events"] += 1
            changed = True
        # the same rule, applied in the run where a re-timed start moves past an end already stored
        if event["end_utc"] and iso_to_ms(event["end_utc"]) < iso_to_ms(event["start_utc"]):
            event["end_utc"] = event["duration_min"] = event["end_observed"] = ""
            stats["ends_before_start_cleared"] += 1
            changed = True
        if end_ms is not None and not event["end_utc"] and whole_second(end_ms) < iso_to_ms(event["start_utc"]):
            # The feed's end precedes the start (a data error); leave the end empty (GATE 1 decision).
            stats["ends_before_start_left_empty"] += 1
        elif end_ms is not None and not event["end_utc"]:
            event["end_utc"] = ms_to_iso(end_ms)
            event["duration_min"] = duration_min(start_ms, end_ms)
            event["end_observed"] = "true"
            stats["ends_observed"] += 1
            changed = True
        if changed:
            event["last_observed_utc"] = now

        current_start = iso_to_ms(event["start_utc"])
        for older in overflow_events:
            if older is not event and not older["end_utc"] and iso_to_ms(older["start_utc"]) < current_start:
                older["end_utc"] = event["start_utc"]
                older["duration_min"] = duration_min(iso_to_ms(older["start_utc"]), current_start)
                older["end_observed"] = "false"
                stats["ends_inferred"] += 1

    # 4.5 offline
    periods = offline_by_overflow[key]
    open_periods = [p for p in periods if not p["offline_end_utc"]]
    status_start = "" if rec["status_start_ms"] is None else ms_to_iso(rec["status_start_ms"])
    if rec["status"] == -1:
        if not open_periods:
            periods.append({"overflow_key": key, "company_slug": slug, "offline_start_utc": status_start,
                            "offline_end_utc": "", "offline_end_source": "", "first_observed_utc": now,
                            "last_observed_utc": now})
            stats["offline_opened"] += 1
            if not status_start:
                stats["offline_opened_without_status_start"] += 1
    elif rec["status"] in (0, 1) and open_periods:
        # Without a StatusStart, the end is the time this poll saw the monitor back (GATE 1 decision).
        for p in open_periods:
            p["offline_end_utc"] = status_start or now
            p["offline_end_source"] = "feed" if status_start else "collector"
            p["last_observed_utc"] = now
            stats["offline_closed"] += 1
            if not status_start:
                stats["offline_closed_at_collector_time"] += 1


def write_outputs(data_dir, meta, overflows, snapshot, events_by_overflow, offline_by_overflow):
    data_dir = Path(data_dir)
    write_json(data_dir / "meta.json", meta)
    write_csv(data_dir / "overflows.csv", overflows.values(), OVERFLOW_FIELDS, lambda r: r["overflow_key"])
    write_json(data_dir / "status_snapshot.json", snapshot)
    events = [ev for evs in events_by_overflow.values() for ev in evs]
    write_by_month(data_dir / "events", events, EVENT_FIELDS, ["start_utc"], lambda r: r["event_id"])
    periods = [p for ps in offline_by_overflow.values() for p in ps]
    write_by_month(data_dir / "offline", periods, OFFLINE_FIELDS, ["offline_start_utc", "first_observed_utc"],
                   lambda r: (r["overflow_key"], r["offline_start_utc"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=str(ROOT / "scripts" / "sources_resolved.json"))
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--dry-run", action="store_true", help="compute changes but write nothing")
    ap.add_argument("--fixture", help="JSON file of ArcGIS query responses keyed by company_slug (tests only)")
    ap.add_argument("--now", help="fix the clock, ISO 8601 UTC with Z")
    args = ap.parse_args()
    if args.fixture and not args.now:
        ap.error("--fixture requires --now")
    now = args.now or now_iso()

    stats = Counter()
    try:
        srcs = read_json(args.sources)
        if args.fixture:
            fixture = read_json(args.fixture)
            feeds = {slug: [f["attributes"] for f in resp["features"]] for slug, resp in fixture.items()}
        else:
            feeds = {}
            for slug in sorted(srcs):
                srcs[slug], feeds[slug] = fetch_company(slug, srcs[slug])
        result = run(args.data, srcs, feeds, now, stats)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not args.dry_run:
        write_outputs(args.data, *result)
    for name in sorted(stats):
        print(f"{name}={stats[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
