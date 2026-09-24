#!/usr/bin/env python3
"""Fetch the nine official regions of England and store them for the map page.

Source: Office for National Statistics Open Geography Portal, "Regions (December 2022) Boundaries
EN BUC" (BUC = ultra generalised, clipped to the coastline — the smallest version, which is what a
900-pixel map needs). These are the ITL1 regions, formerly the Government Office Regions: North
East, North West, Yorkshire and The Humber, East Midlands, West Midlands, East of England, London,
South East, South West.

Supplied under the Open Government Licence v3.0. The two copyright statements the ONS requires
(https://www.ons.gov.uk/methodology/geography/licences) are carried on the site's Method page and
in its footer:
    Source: Office for National Statistics licensed under the Open Government Licence v.3.0
    Contains OS data (c) Crown copyright and database right 2022

The result is committed to data/geo/regions.geojson so the site build never needs the network and
every build draws exactly the same coastline. Re-run this only to move to a newer boundary release.

Exit codes: 0 ok, 1 the response was not the nine regions, 2 network error.
"""
import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
       "Regions_December_2022_EN_BUC/FeatureServer/0/query")
PARAMS = {"where": "1=1", "outFields": "RGN22CD,RGN22NM", "outSR": "4326", "f": "geojson"}
EXPECTED = 9
OUT = ROOT / "data" / "geo" / "regions.geojson"


def fetch():
    last = None
    for attempt in range(3):
        try:
            r = requests.get(URL, params=PARAMS, timeout=120)
            if r.status_code >= 500 or r.status_code in (403, 429):
                last = f"{r.status_code} {r.reason}"
            else:
                r.raise_for_status()
                return r.json()
        except requests.RequestException as e:
            last = str(e)
        print(f"attempt {attempt + 1} failed ({last}), retrying", file=sys.stderr)
    print(f"could not fetch the region boundaries: {last}", file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    data = fetch()
    if data is None:
        return 2
    features = data.get("features", [])
    names = sorted(f["properties"].get("RGN22NM", "") for f in features)
    if len(features) != EXPECTED or not all(names):
        print(f"expected {EXPECTED} named regions, got {len(features)}: {names}", file=sys.stderr)
        return 1

    # Keep only what the map draws, and write it sorted and indented so the diff is reviewable.
    slim = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"code": f["properties"]["RGN22CD"], "name": f["properties"]["RGN22NM"]},
         "geometry": f["geometry"]}
        for f in sorted(features, key=lambda f: f["properties"]["RGN22CD"])]}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(slim, fh, sort_keys=True, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {path} with {len(features)} regions: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
