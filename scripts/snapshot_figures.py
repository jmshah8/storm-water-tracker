#!/usr/bin/env python3
"""Print the figure block for PDF_BRIEF_FOR_COWORK.md §4, straight from the committed data.

The brief that Claude Cowork works from carries a dated snapshot of the site's numbers, because a
document cannot cite a figure that changes every ten minutes. This script regenerates that snapshot
so the brief is refreshed from the data rather than edited by hand.

Usage: python scripts/snapshot_figures.py       Exit codes: 0 ok, 1 data missing.
"""
import collections
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_site import COMPANIES, contested  # noqa: E402
from swt.io import read_csv, read_json  # noqa: E402


def main():
    data = ROOT / "data"
    rows = read_csv(data / "classification" / "all_events_classified.csv")
    overflows = read_csv(data / "overflows.csv")
    meta = read_json(data / "meta.json")
    if not rows or not overflows or not meta:
        print("data/ is missing the classification, overflows or meta file", file=sys.stderr)
        return 1

    launch = meta["launch_utc"][:10]
    live = [r for r in rows if r["day_utc"] >= launch]
    pre = [r for r in rows if r["day_utc"] < launch]
    every, in_live = collections.Counter(r["verdict"] for r in rows), collections.Counter(r["verdict"] for r in live)
    checkable = [r for r in rows if r["verdict"] == "dry_day" and r["radar_status"] == "complete"
                 and r["radar_3x3_max_total_mm"]]
    agrees = sum(1 for r in checkable if float(r["radar_3x3_max_total_mm"]) <= 0.25)
    complete = sum(1 for r in rows if r["verdict"] == "dry_day" and r["n_readings_present"] == "192")
    by_company = collections.Counter(r["company_slug"] for r in live
                                     if r["verdict"] == "dry_day" and not contested(r))
    radar_days = len(list((data / "radar" / "daily").glob("*.csv*"))) if (data / "radar" / "daily").exists() else 0
    now = datetime.datetime.now(datetime.timezone.utc)

    print(f"Snapshot taken {now:%d %B %Y}, {now:%H:%M} UTC.\n")
    print(f"Water companies covered | {len({o['company_slug'] for o in overflows})} (all of England)")
    print(f"Storm overflows tracked | {len(overflows):,}")
    print(f"Total discharges classified | {len(rows):,}")
    print(f"  since the record began ({launch}) | {len(live):,}")
    print(f"  Thames Water's own published history | {len(pre):,}")
    print(f"Rule version in force | {', '.join(sorted({r['rule_version'] for r in rows}))}")
    print(f"Radar days held | {radar_days}")
    print("\nAll classified:")
    for verdict, n in every.most_common():
        print(f"  {verdict} | {n:,}")
    print(f"  (contested by radar) | {sum(1 for r in rows if contested(r)):,}")
    print("\nLive record only:")
    for verdict, n in in_live.most_common():
        print(f"  {verdict} | {n:,}")
    print(f"  (contested by radar) | {sum(1 for r in live if contested(r)):,}")
    print("\nDry day spills by company, live record (uncontested):")
    for slug, name in COMPANIES:
        print(f"  {name} | {by_company.get(slug, 0):,}")
    print("\nQuality of the evidence:")
    if every["dry_day"]:
        print(f"  flags on a complete 192-of-192 window | {complete * 100 / every['dry_day']:.1f}%")
    if checkable:
        print(f"  flags the radar can check | {len(checkable):,}")
        print(f"  of those, radar agrees | {agrees:,} ({agrees * 100 / len(checkable):.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
