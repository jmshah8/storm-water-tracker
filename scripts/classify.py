#!/usr/bin/env python3
"""Classify every event with the dry-day rule (01_SPEC.md §5) and write the classification CSVs.

Reads data/events, data/overflows.csv, data/rain/gauges.csv, data/rain/daily. Re-evaluates every event
whose previous verdict is not final (final verdicts are kept unless --force); appends flips between
dry_day and not_dry to verdict_changes.csv; writes all_events_classified.csv and dry_day_spills.csv.

Exit codes: 0 ok, 1 input files missing.
"""
import argparse
import sys
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
    "rain_day_mm", "rain_prev24_mm", "rain_window_total_mm", "rain_window_max15_mm",
    "n_readings_present", "n_readings_expected", "verdict", "verdict_basis", "rule_version", "classified_utc",
    "radar_window_total_mm", "radar_3x3_max_total_mm", "radar_status", "is_final"]
CHANGE_FIELDS = ["event_id", "from_verdict", "to_verdict", "changed_utc", "n_readings_present"]
DECIDED = {"dry_day", "not_dry"}


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
        if overflow_key not in candidates_cache:
            o = overflows.get(overflow_key)
            if not o or not o["latitude"] or not o["longitude"]:
                candidates_cache[overflow_key] = []
            else:
                candidates_cache[overflow_key] = nearest_gauges(float(o["latitude"]), float(o["longitude"]), gauges)
        return candidates_cache[overflow_key]

    previous = {r["event_id"]: r for r in read_csv(out_dir / "all_events_classified.csv")}
    changes = read_csv(out_dir / "verdict_changes.csv")
    rows, kept_final, flips = [], 0, 0
    for ev in events:
        old = previous.get(ev["event_id"])
        if old and old["is_final"] == "true" and not args.force:
            rows.append(dict(old, **{k: ev[k] for k in COPIED}))
            kept_final += 1
            continue
        result = classify_event(ev["start_utc"], candidates(ev["overflow_key"]), rain_lookup, now, RULE_VERSION)
        row = {k: ev[k] for k in COPIED}
        row.update(result)
        row.update(radar_window_total_mm="", radar_3x3_max_total_mm="", radar_status="")
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

    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"events={len(rows)} kept_final={kept_final} flips={flips} "
          + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
