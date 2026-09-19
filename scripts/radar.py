#!/usr/bin/env python3
"""Met Office UK rainfall radar (03_PHASE2_RADAR_PLAN.md).

    radar.py inspect PATH         print every attribute of an ODIM_H5 radar file
    radar.py fetch DATE [--out D] download one day's frames to a directory (default .cache/radar/DATE)
    radar.py day DATE             accumulate a UTC day's frames and sample every overflow ->
                                  data/radar/daily/DATE.csv.gz

The composite is published every 15 minutes at
s3://met-office-radar-obs-data/radar/YYYY/MM/DD/YYYYMMDDHHMM_ODIM_ng_radar_rainrate_composite_1km_UK.h5
(public, no credentials). Licence: "British Crown copyright 2024-2025, the Met Office, is licensed under CC BY-SA".

Exit codes: 0 ok, 1 bad input, 2 network error.
"""
import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BUCKET = "https://met-office-radar-obs-data.s3.eu-west-2.amazonaws.com"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_day(day):
    """Every key under radar/YYYY/MM/DD/, following continuation tokens."""
    keys, token = [], None
    while True:
        params = {"list-type": "2", "prefix": f"radar/{day:%Y/%m/%d}/"}
        if token:
            params["continuation-token"] = token
        r = requests.get(BUCKET, params=params, timeout=120)
        r.raise_for_status()
        tree = ET.fromstring(r.text)
        keys += [el.text for el in tree.findall("s3:Contents/s3:Key", S3_NS)]
        token = (tree.findtext("s3:NextContinuationToken", namespaces=S3_NS)
                 if tree.findtext("s3:IsTruncated", namespaces=S3_NS) == "true" else None)
        if not token:
            return sorted(keys)


def download(key, target):
    """Download one key with three retries; returns the local path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(3):
        try:
            r = requests.get(f"{BUCKET}/{key}", timeout=180)
            r.raise_for_status()
            target.write_bytes(r.content)
            return target
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** (attempt + 1))
    raise OSError(f"{key}: {last}")


def show(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def inspect(path):
    import h5py

    groups = ["/what", "/where", "/how", "/dataset1/what", "/dataset1/where", "/dataset1/how",
              "/dataset1/data1/what", "/dataset1/data1/how"]
    with h5py.File(path, "r") as f:
        print(f"file: {path} ({path.stat().st_size} bytes)")
        print(f"top-level groups: {list(f.keys())}")
        for name in groups:
            if name not in f:
                print(f"\n{name}: absent")
                continue
            print(f"\n{name}:")
            for key, value in sorted(f[name].attrs.items()):
                print(f"  {key} = {show(value)!r}")
        data = f.get("/dataset1/data1/data")
        if data is None:
            print("\n/dataset1/data1/data: absent")
            return 1
        print(f"\n/dataset1/data1/data: shape={data.shape} dtype={data.dtype}")
    return 0


DAILY_FIELDS = ["date", "overflow_key", "radar_total_mm", "radar_max15_mm", "radar_3x3_max_total_mm", "n_frames",
                "fetched_utc"]


def accumulate_day(day, cache_dir, keep_files=False):
    """(total_mm, max15_mm, valid_frames_per_pixel, meta, n_frames) for one UTC day."""
    import numpy as np

    sys.path.insert(0, str(ROOT))
    from swt.radar import accum_15min, load_frame

    keys = list_day(day)
    total = max15 = valid = None
    meta = None
    n_frames = 0
    for key in keys:
        path = cache_dir / key.rsplit("/", 1)[-1]
        if not path.exists():
            download(key, path)
        rate, frame_meta = load_frame(path)
        if not keep_files:
            path.unlink()
        accum = accum_15min(rate)
        present = ~np.isnan(accum)
        if total is None:
            total = np.zeros_like(accum)
            max15 = np.zeros_like(accum)
            valid = np.zeros(accum.shape, dtype="int16")
            meta = frame_meta
        total = np.where(present, total + np.nan_to_num(accum), total)
        max15 = np.where(present, np.maximum(max15, np.nan_to_num(accum)), max15)
        valid += present
        n_frames += 1
    if total is None:
        return None
    return total, max15, valid, meta, n_frames


def sample_overflows(total, max15, valid, meta, day, n_frames, overflows, now):
    """One row per overflow: nearest pixel, plus the 3x3 neighbourhood maximum of the day's total."""
    import numpy as np

    sys.path.insert(0, str(ROOT))
    from swt.radar import Grid

    grid = Grid(meta["where"], meta["origin"])
    rows = []
    for o in overflows:
        row = {"date": day.isoformat(), "overflow_key": o["overflow_key"], "radar_total_mm": "",
               "radar_max15_mm": "", "radar_3x3_max_total_mm": "", "n_frames": str(n_frames),
               "fetched_utc": now}
        try:
            lat, lon = float(o["latitude"]), float(o["longitude"])
        except (TypeError, ValueError):
            rows.append(row)
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            r, c = grid.to_pixel(lat, lon)
            if grid.in_bounds(r, c) and valid[r, c] > 0:
                r0, r1 = max(0, r - 1), min(grid.ysize, r + 2)
                c0, c1 = max(0, c - 1), min(grid.xsize, c + 2)
                block = total[r0:r1, c0:c1]
                block_valid = valid[r0:r1, c0:c1] > 0
                row["radar_total_mm"] = f"{float(total[r, c]):.2f}"
                row["radar_max15_mm"] = f"{float(max15[r, c]):.2f}"
                row["radar_3x3_max_total_mm"] = f"{float(np.max(block[block_valid])):.2f}"
        rows.append(row)
    return sorted(rows, key=lambda r: r["overflow_key"])


def write_daily(path, rows):
    """Deterministic gzip CSV, written to a temp file then renamed."""
    import csv
    import gzip
    import io

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # mtime=0 keeps the gzip header identical between runs, so unchanged data produces no git diff
    with open(tmp, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DAILY_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    tmp.replace(path)


def run_day(args):
    from datetime import date, datetime, timezone

    sys.path.insert(0, str(ROOT))
    from swt.io import read_csv

    try:
        day = date.fromisoformat(args.date)
    except ValueError:
        print(f"bad date: {args.date}", file=sys.stderr)
        return 1
    overflows = read_csv(ROOT / "data" / "overflows.csv")
    if not overflows:
        print("data/overflows.csv is missing or empty", file=sys.stderr)
        return 1
    cache_dir = ROOT / ".cache" / "radar" / args.date
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        accumulated = accumulate_day(day, cache_dir, keep_files=args.keep_files)
    except (requests.RequestException, ET.ParseError, OSError) as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2
    if accumulated is None:
        # The Met Office archive itself has gaps (e.g. 13 and 14 Dec 2024 hold no files at all). That is a
        # day with no radar, not an error: write nothing and let the caller carry on to the next day.
        print(f"{args.date}: no radar frames published for this day; nothing written")
        return 0
    total, max15, valid, meta, n_frames = accumulated
    rows = sample_overflows(total, max15, valid, meta, day, n_frames, overflows, now)
    out = ROOT / "data" / "radar" / "daily" / f"{args.date}.csv.gz"
    write_daily(out, rows)
    sampled = sum(1 for r in rows if r["radar_total_mm"])
    print(f"{args.date}: frames {n_frames}/96; overflows {len(rows)}, sampled {sampled}; "
          f"{out.relative_to(ROOT)} {out.stat().st_size} bytes")
    if args.save_grid:
        import numpy as np
        grid_path = Path(args.save_grid)
        grid_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(grid_path, total=total, max15=max15, valid=valid,
                            where=repr(meta["where"]), origin=str(meta["origin"]), n_frames=n_frames)
        print(f"grid saved to {grid_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect", help="print an ODIM_H5 file's attributes")
    p_inspect.add_argument("path")
    p_fetch = sub.add_parser("fetch", help="download one UTC day's frames")
    p_fetch.add_argument("date")
    p_fetch.add_argument("--out")
    p_fetch.add_argument("--only", help="download just this HHMM frame")
    p_day = sub.add_parser("day", help="accumulate one UTC day and sample every overflow")
    p_day.add_argument("date")
    p_day.add_argument("--save-grid", help="also write the accumulated grids to an .npz (for checks)")
    p_day.add_argument("--keep-files", action="store_true", help="keep the downloaded frames in .cache")
    args = ap.parse_args()

    if args.command == "day":
        return run_day(args)

    if args.command == "inspect":
        path = Path(args.path)
        if not path.exists():
            print(f"{path} does not exist", file=sys.stderr)
            return 1
        return inspect(path)

    from datetime import date
    try:
        day = date.fromisoformat(args.date)
    except ValueError:
        print(f"bad date: {args.date}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else ROOT / ".cache" / "radar" / args.date
    try:
        keys = list_day(day)
        if args.only:
            keys = [k for k in keys if re.search(rf"/\d{{8}}{args.only}_", k)]
        for key in keys:
            target = out / key.rsplit("/", 1)[-1]
            if not target.exists():
                download(key, target)
            print(target)
    except (requests.RequestException, ET.ParseError, OSError) as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
