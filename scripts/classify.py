#!/usr/bin/env python3
"""Classify every event with the dry-day rule (01_SPEC.md §5) and write the classification CSVs.

Reads data/events, data/overflows.csv, data/rain/gauges.csv, data/rain/daily, and (phase 2)
data/radar/daily. The radar columns are a second opinion only: they never change a verdict.
Re-evaluates every event
whose previous verdict is not final (final verdicts are kept unless --force); appends flips between
dry_day and not_dry to verdict_changes.csv; writes all_events_classified.csv and dry_day_spills.csv.

Exit codes: 0 ok, 1 input files missing.
"""
import argparse
import csv
import gzip
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.geo import nearest_gauges  # noqa: E402
from swt.io import read_csv, write_csv  # noqa: E402
from swt.rule import RULE_VERSION, classify_event  # noqa: E402
from swt.timeutil import now_iso  # noqa: E402

COPIED = ["event_id", "overflow_key", "company_slug", "start_utc", "end_utc", "duration_min", "source"]
FIELDS = COPIED + [
    "day_utc", "window_start_utc", "window_end_utc", "gauge_id", "gauge_label", "gauge_distance_km",
    "gauge_method", "triangulated_gauges",
    "rain_day_mm", "rain_prev24_mm", "rain_window_total_mm", "rain_window_max15_mm",
    "n_readings_present", "n_readings_expected", "n_gauges_skipped_stuck", "verdict", "verdict_basis",
    "rule_version", "classified_utc",
    "radar_window_total_mm", "radar_3x3_max_total_mm", "radar_status", "is_final"]
CHANGE_FIELDS = ["event_id", "from_verdict", "to_verdict", "changed_utc", "n_readings_present"]
DECIDED = {"dry_day", "not_dry"}
RADAR_COMPLETE_FRAMES = 92
# dry-day-v2: a gauge is treated as stuck when it has recorded nothing at all for this long while other
# evidence says it rained.
STUCK_LOOKBACK_DAYS = 30
STUCK_MIN_COMPLETE_DAYS = 5        # as much history as we hold early on; the test leans on the evidence below
STUCK_NEIGHBOUR_KM = 20.0
STUCK_EVIDENCE_MM = 1.0
STUCK_MIN_NEIGHBOURS = 2           # two independent gauges, so one faulty gauge or one local shower is not enough
# dry-day-v3: how far out the three gauges of GN066's triangulation may sit when nothing is within 10 km.
# The same 20 km the stuck-gauge test already uses, so the rule carries one distance, not two.
TRIANGULATE_KM = 20.0


class StuckGauges:
    """Which gauges have stopped reporting rain (dry-day-v2).

    A gauge counts as stuck for a day when, over the 30 days ending that day, it has at least 10 complete days
    and recorded 0.00 mm on every one of them, and something independent says it rained in that period: a gauge
    within 20 km recording more than 1 mm, or (passed in per event) radar over the overflow.
    """

    def __init__(self, gauges, rain):
        self.by_gauge = defaultdict(dict)
        for (gauge_id, day), row in rain.items():
            self.by_gauge[gauge_id][day] = row
        self.neighbours = {}
        for g in gauges:
            near = nearest_gauges(float(g["latitude"]), float(g["longitude"]), gauges, max_km=STUCK_NEIGHBOUR_KM)
            self.neighbours[g["gauge_id"]] = [n["gauge_id"] for n in near if n["gauge_id"] != g["gauge_id"]]
        self.cache = {}

    def _window_days(self, day):
        end = date.fromisoformat(day)
        return [(end - timedelta(days=i)).isoformat() for i in range(STUCK_LOOKBACK_DAYS)]

    def silent(self, gauge_id, day):
        """(True, days) when the gauge has a long run of complete days with no rain at all."""
        key = (gauge_id, day)
        if key not in self.cache:
            days = [d for d in self._window_days(day)
                    if (row := self.by_gauge[gauge_id].get(d)) and int(row["n_readings"]) >= 88]
            silent = (len(days) >= STUCK_MIN_COMPLETE_DAYS
                      and all(float(self.by_gauge[gauge_id][d]["total_mm"]) == 0 for d in days))
            self.cache[key] = (silent, days)
        return self.cache[key]

    def neighbour_rain(self, gauge_id, days):
        """True when at least two gauges within 20 km recorded real rain on days this gauge recorded nothing."""
        wet = 0
        for neighbour in self.neighbours.get(gauge_id, []):
            for d in days:
                row = self.by_gauge[neighbour].get(d)
                if row and int(row["n_readings"]) >= 88 and float(row["total_mm"]) > STUCK_EVIDENCE_MM:
                    wet += 1
                    break
            if wet >= STUCK_MIN_NEIGHBOURS:
                return True
        return False

    def checker(self, radar_mm):
        """A gauge_unusable(gauge_id, day) callback for one event; radar_mm is its radar window total or None."""
        def unusable(gauge_id, day):
            silent, days = self.silent(gauge_id, day)
            if not silent:
                return None
            if self.neighbour_rain(gauge_id, days):
                return (f"recorded no rain on any of its {len(days)} complete days while at least "
                        f"{STUCK_MIN_NEIGHBOURS} gauges within {STUCK_NEIGHBOUR_KM:.0f} km recorded rain")
            if radar_mm is not None and radar_mm > STUCK_EVIDENCE_MM:
                return (f"recorded no rain on any of its {len(days)} complete days while radar recorded "
                        f"{radar_mm:.1f} mm over the overflow")
            return None
        return unusable


class RadarDays:
    """Reads data/radar/daily/{date}.csv.gz on demand, keeping only the last few days in memory."""

    def __init__(self, directory, keep=3):
        self.directory = Path(directory)
        self.keep = keep
        self.cache = {}

    def day(self, day):
        """{overflow_key: row} for that UTC day, or None when the file does not exist."""
        if day not in self.cache:
            path = self.directory / f"{day}.csv.gz"
            if path.exists():
                with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                    self.cache[day] = {r["overflow_key"]: r for r in csv.DictReader(f)}
            else:
                self.cache[day] = None
            for old in list(self.cache)[:-self.keep]:
                del self.cache[old]
        return self.cache[day]

    def window(self, overflow_key, day_utc):
        """Radar totals over the same 48-hour window as the rule (03 plan step 2.4)."""
        previous = (date.fromisoformat(day_utc) - timedelta(days=1)).isoformat()
        rows = [(self.day(d) or {}).get(overflow_key) for d in (previous, day_utc)]
        if any(r is None for r in rows):
            return {"radar_window_total_mm": "", "radar_3x3_max_total_mm": "", "radar_status": "missing"}
        if any(not r["radar_total_mm"] for r in rows):
            return {"radar_window_total_mm": "", "radar_3x3_max_total_mm": "", "radar_status": "missing"}
        complete = all(int(r["n_frames"]) >= RADAR_COMPLETE_FRAMES for r in rows)
        return {
            "radar_window_total_mm": f"{sum(float(r['radar_total_mm']) for r in rows):.2f}",
            "radar_3x3_max_total_mm": f"{sum(float(r['radar_3x3_max_total_mm']) for r in rows):.2f}",
            "radar_status": "complete" if complete else "partial",
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--force", action="store_true", help="re-classify events whose verdict is already final")
    args = ap.parse_args()

    data = Path(args.data)
    out_dir = data / "classification"
    now = now_iso()

    overflows = {r["overflow_key"]: r for r in read_csv(data / "overflows.csv")}
    gauges = read_csv(data / "rain" / "gauges.csv")
    events = [r for p in sorted((data / "events").glob("*.csv")) for r in read_csv(p)]
    # Phase 3: Thames Water's own history back to April 2022, already de-duplicated against the events the
    # Hub seeded at launch. events_overlap.csv is validation only and is never classified.
    history = data / "thames_history" / "events_pre_launch.csv"
    if history.exists():
        events += read_csv(history)
    if not overflows or not gauges:
        print("overflows.csv or rain/gauges.csv is missing or empty", file=sys.stderr)
        return 1

    rain = {}
    for path in sorted((data / "rain" / "daily").glob("*.csv")):
        for r in read_csv(path):
            rain[(r["gauge_id"], r["date"])] = r

    def rain_lookup(gauge_id, day):
        return rain.get((gauge_id, day))

    candidates_cache = {}

    def candidates(overflow_key):
        """(gauges within 10 km, gauges within the triangulation radius), both nearest first."""
        if overflow_key not in candidates_cache:
            o = overflows.get(overflow_key)
            if not o or not o["latitude"] or not o["longitude"]:
                candidates_cache[overflow_key] = ([], [])
            else:
                lat, lon = float(o["latitude"]), float(o["longitude"])
                far = nearest_gauges(lat, lon, gauges, max_km=TRIANGULATE_KM)
                candidates_cache[overflow_key] = ([g for g in far if g["distance_km"] <= 10.0], far)
        return candidates_cache[overflow_key]

    radar = RadarDays(data / "radar" / "daily")
    stuck = StuckGauges(gauges, rain)
    events.sort(key=lambda e: (e["start_utc"], e["event_id"]))  # so the radar day cache only needs a few days
    previous = {r["event_id"]: r for r in read_csv(out_dir / "all_events_classified.csv")}
    changes = read_csv(out_dir / "verdict_changes.csv")
    rows, kept_final, flips = [], 0, 0
    for ev in events:
        old = previous.get(ev["event_id"])
        if old and old["is_final"] == "true" and not args.force:
            # a final verdict never changes, but its radar second opinion can still arrive or improve
            kept = dict(old, **{k: ev[k] for k in COPIED})
            kept.update(radar.window(ev["overflow_key"], old["day_utc"]))
            if any(kept[k] != old[k] for k in ("radar_window_total_mm", "radar_3x3_max_total_mm", "radar_status")):
                kept["classified_utc"] = now
            rows.append(kept)
            kept_final += 1
            continue
        day_utc = ev["start_utc"][:10]
        radar_window = radar.window(ev["overflow_key"], day_utc)
        radar_mm = (float(radar_window["radar_3x3_max_total_mm"])
                    if radar_window["radar_status"] == "complete" and radar_window["radar_3x3_max_total_mm"]
                    else None)
        near, far = candidates(ev["overflow_key"])
        result = classify_event(ev["start_utc"], near, rain_lookup, now, RULE_VERSION,
                                gauge_unusable=stuck.checker(radar_mm), far_candidates=far)
        row = {k: ev[k] for k in COPIED}
        row.update(result)
        row.update(radar_window)
        # classified_utc moves only when the classification itself changed, so an hourly run over unchanged
        # inputs produces no diff.
        unchanged = old and all(old.get(k) == row[k] for k in row)
        row["classified_utc"] = old["classified_utc"] if unchanged else now
        if old and old["verdict"] in DECIDED and row["verdict"] in DECIDED and old["verdict"] != row["verdict"]:
            changes.append({"event_id": ev["event_id"], "from_verdict": old["verdict"], "to_verdict": row["verdict"],
                            "changed_utc": now, "n_readings_present": row["n_readings_present"]})
            flips += 1
        rows.append(row)

    write_csv(out_dir / "all_events_classified.csv", rows, FIELDS, lambda r: r["event_id"])
    write_csv(out_dir / "dry_day_spills.csv", [r for r in rows if r["verdict"] == "dry_day"], FIELDS,
              lambda r: r["event_id"])
    write_csv(out_dir / "verdict_changes.csv", changes, CHANGE_FIELDS, lambda r: (r["event_id"], r["changed_utc"]))

    skipped_rows = sum(1 for r in rows if r.get("n_gauges_skipped_stuck", "0") not in ("0", ""))
    counts, radar_counts = {}, {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        radar_counts[r["radar_status"]] = radar_counts.get(r["radar_status"], 0) + 1
    print(f"events={len(rows)} kept_final={kept_final} flips={flips} stuck_gauge_skips={skipped_rows} "
          + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + " | radar " + " ".join(f"{k}={v}" for k, v in sorted(radar_counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
