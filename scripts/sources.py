#!/usr/bin/env python3
"""Resolve the ten National Storm Overflow Hub datasets to ArcGIS query endpoints.

For each company (01_SPEC.md §2.1): fetch the ArcGIS item, read its Feature Service
URL and licence, read layer 0's schema, map its fields to the ten logical names
(case-insensitive, plus the LatestEventFinish alias), check the Status coded-value
domain, record maxRecordCount/supportsPagination and the record count, and write
scripts/sources_resolved.json.

Exit codes: 0 ok, 1 a company failed its check, 2 network/parse error.
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

SOURCES = [
    ("anglian", "Anglian Water", "333c5c0600f94757b134b276ac4ad8b0"),
    ("northumbrian", "Northumbrian Water", "2d91e4a41b884c9a9dd58dec4ee49b75"),
    ("severn-trent", "Severn Trent Water", "9c5edb37e19044738373137ac76feea2"),
    ("southern", "Southern Water", "7f5ee61ab15d4c79a3f708ccf448a810"),
    ("south-west", "South West Water", "cabfce76b72a4a278a33d737c0708d42"),
    ("thames", "Thames Water", "216f455c4435450693cf1d0d0ecf6023"),
    ("united-utilities", "United Utilities", "8225548a267f4a408c36a91b6e0f5a1c"),
    ("wessex", "Wessex Water", "632885799ff946cd86200f07b7f175fb"),
    ("yorkshire", "Yorkshire Water", "7f575862a2254a4aaba62573e1012731"),
    ("st-connect", "ST Connect", "63295ca00e8741fd9d0cd02bd5301d9d"),
]

LOGICAL_FIELDS = [
    "Id", "Company", "Status", "StatusStart", "LatestEventStart",
    "LatestEventEnd", "Longitude", "Latitude", "ReceivingWaterCourse", "LastUpdated",
]
ALIASES = {"LatestEventEnd": ["LatestEventEnd", "LatestEventFinish"]}
EXPECTED_STATUS_CODES = {1: "start", 0: "stop", -1: "offline"}

DEFAULT_OUT = Path(__file__).resolve().parent / "sources_resolved.json"


class NetworkError(Exception):
    pass


def get_json(url, params=None):
    """GET a JSON document; retry three times with backoff, then raise NetworkError."""
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "error" in data:
                raise NetworkError(f"{url}: ArcGIS error {data['error']}")
            return data
        except (requests.RequestException, ValueError, NetworkError) as e:
            last = e
            time.sleep(2 ** (attempt + 1))
    raise NetworkError(f"{url}: {last}")


def map_fields(field_names):
    """Map logical field names to the layer's actual names. Returns (map, unmapped)."""
    by_lower = {name.lower(): name for name in field_names}
    mapping, unmapped = {}, []
    for logical in LOGICAL_FIELDS:
        for candidate in ALIASES.get(logical, [logical]):
            if candidate.lower() in by_lower:
                mapping[logical] = by_lower[candidate.lower()]
                break
        else:
            unmapped.append(logical)
    return mapping, unmapped


def check_domain(field):
    """Return 'ok', 'absent' or 'different:<codes>' for the Status field's domain."""
    domain = field.get("domain")
    if not domain or domain.get("type") != "codedValue":
        return "absent"
    codes = {cv["code"]: str(cv["name"]).lower() for cv in domain.get("codedValues", [])}
    if codes == EXPECTED_STATUS_CODES:
        return "ok"
    return "different:" + json.dumps(codes, sort_keys=True)


def plain_text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def resolve_one(slug, name, item_id):
    item = get_json(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}", {"f": "json"})
    service_url = item.get("url")
    if not service_url:
        raise NetworkError(f"{slug}: item {item_id} has no url")
    layer_url = service_url.rstrip("/") + "/0"
    layer = get_json(layer_url, {"f": "pjson"})
    fields = layer.get("fields") or []
    mapping, unmapped = map_fields([f["name"] for f in fields])
    status_field = next((f for f in fields if f["name"] == mapping.get("Status")), {})
    domain = check_domain(status_field) if status_field else "absent"
    count = get_json(layer_url + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count")
    return {
        "company_name": name,
        "item_id": item_id,
        "service_url": service_url,
        "layer_url": layer_url,
        "license_info": plain_text(item.get("licenseInfo")),
        "field_map": mapping,
        "unmapped_fields": unmapped,
        "status_domain": domain,
        "max_record_count": layer.get("maxRecordCount"),
        "supports_pagination": bool((layer.get("advancedQueryCapabilities") or {}).get("supportsPagination")),
        "count": count,
    }


def resolve_all():
    return {slug: resolve_one(slug, name, item_id) for slug, name, item_id in SOURCES}


def load_sources(path=DEFAULT_OUT):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def company_ok(r):
    return not r["unmapped_fields"] and not r["status_domain"].startswith("different") and r["supports_pagination"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="where to write the resolved JSON")
    args = ap.parse_args()
    try:
        resolved = resolve_all()
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(resolved, f, sort_keys=True, indent=2)
        f.write("\n")

    total = 0
    failed = False
    for slug, _, _ in SOURCES:
        r = resolved[slug]
        fields = "mapped" if not r["unmapped_fields"] else "UNMAPPED:" + ",".join(r["unmapped_fields"])
        pagination = "true" if r["supports_pagination"] else "false"
        print(f"{slug:17} fields={fields} domain={r['status_domain']} pagination={pagination} "
              f"maxRecordCount={r['max_record_count']} count={r['count']} licenseInfo={r['license_info']!r}")
        non_canonical = {k: v for k, v in r["field_map"].items() if k != v}
        if non_canonical:
            print(f"{'':17} alias map: {json.dumps(non_canonical, sort_keys=True)}")
        total += r["count"] or 0
        failed = failed or not company_ok(r)
    print(f"total count = {total}")
    if not 13000 <= total <= 15500:
        print("total outside 13,000-15,500")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
