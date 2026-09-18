#!/usr/bin/env python3
"""Met Office UK rainfall radar (03_PHASE2_RADAR_PLAN.md).

    radar.py inspect PATH        print every attribute of an ODIM_H5 radar file
    radar.py fetch DATE [--out D] download one day's frames to a directory (default .cache/radar/DATE)

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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect", help="print an ODIM_H5 file's attributes")
    p_inspect.add_argument("path")
    p_fetch = sub.add_parser("fetch", help="download one UTC day's frames")
    p_fetch.add_argument("date")
    p_fetch.add_argument("--out")
    p_fetch.add_argument("--only", help="download just this HHMM frame")
    args = ap.parse_args()

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
