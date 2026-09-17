#!/usr/bin/env python3
"""Checks from the build plan, by step id: python scripts/check.py --step 1.8

Exit codes: 0 check passed, 1 check failed or inconclusive, 2 network error.
"""
import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_csv  # noqa: E402

HYDROLOGY = "https://environment.data.gov.uk/hydrology/id"
FLOOD_MONITORING = "https://environment.data.gov.uk/flood-monitoring/id"


class NetworkError(Exception):
    pass


def get_json(url, params=None):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code in (403, 429) or r.status_code >= 500:
                last = f"{r.status_code} {r.reason}"
            else:
                r.raise_for_status()
                return r.json()
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as e:
            last = str(e)
        time.sleep(2 ** (attempt + 1))
    raise NetworkError(f"{url}: {last}")


# ---------------------------------------------------------------- step 1.8

MIN_GAUGES = 5
MIN_DAY_TOTAL_MM = 5.0
OFFSETS_MIN = range(-120, 121, 15)
RT_MEASURE_SUFFIX = "-rainfall-tipping_bucket_raingauge-t-15_min-mm"


def is_bst(day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=ZoneInfo("Europe/London")).utcoffset() != timedelta(0)


def series(items, stamp_key, tz_suffix):
    """{UTC datetime: value} from API items; Hydrology stamps have no zone and are read as UTC here."""
    out = {}
    for item in items:
        value = item.get("value")
        if value is None or value == "":
            continue
        stamp = item[stamp_key]
        if tz_suffix and not stamp.endswith("Z"):
            raise ValueError(f"real-time timestamp without Z: {stamp}")
        out[datetime.fromisoformat(stamp.rstrip("Z")).replace(tzinfo=timezone.utc)] = float(value)
    return out


def best_offset(rt, hy, day):
    """For each shift o, compare real-time slot t with Hydrology stamp t - o over the 96 slots of `day`."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    slots = [start + timedelta(minutes=15 * i) for i in range(96)]
    scores = {}
    for o in OFFSETS_MIN:
        pairs = [(rt[t], hy[t - timedelta(minutes=o)]) for t in slots if t in rt and t - timedelta(minutes=o) in hy]
        if len(pairs) < 80:
            continue
        diff = sum(abs(a - b) for a, b in pairs)
        exact = sum(1 for a, b in pairs if abs(a - b) < 1e-6)
        scores[o] = (round(diff, 3), exact, len(pairs))
    if not scores:
        return None, scores
    ranked = sorted(scores, key=lambda o: (scores[o][0], -scores[o][1]))
    if len(ranked) > 1 and scores[ranked[0]][0] == scores[ranked[1]][0]:
        return "tie", scores
    return ranked[0], scores


def step_1_8(args):
    gauges = read_csv(ROOT / "data" / "rain" / "gauges.csv")
    hy_stations = get_json(f"{HYDROLOGY}/stations", {"observedProperty": "rainfall", "_limit": 5000})["items"]
    ref_by_gauge = {s["notation"]: s.get("stationReference") for s in hy_stations}
    rt_stations = get_json(f"{FLOOD_MONITORING}/stations", {"parameter": "rainfall", "_limit": 5000})["items"]
    rt_measure = {}
    for s in rt_stations:
        measures = s.get("measures") or []
        measures = measures if isinstance(measures, list) else [measures]
        for m in measures:
            mid = m["@id"] if isinstance(m, dict) else m
            if mid.endswith(RT_MEASURE_SUFFIX) and s.get("stationReference"):
                rt_measure[s["stationReference"]] = mid.rsplit("/", 1)[-1]
    matched = {g["gauge_id"]: g for g in gauges if ref_by_gauge.get(g["gauge_id"]) in rt_measure}
    print(f"Hydrology gauges: {len(gauges)}; real-time 15-min total measures: {len(rt_measure)}; "
          f"matched by stationReference: {len(matched)}")

    today = datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=27)
    chosen_day, candidates = None, []
    for path in sorted((ROOT / "data" / "rain" / "daily").glob("*.csv"), reverse=True):
        day = date.fromisoformat(path.stem)
        if day < earliest or day >= today - timedelta(days=1) or not is_bst(day):
            continue
        wet = [r for r in read_csv(path) if r["gauge_id"] in matched and int(r["n_readings"]) == 96
               and float(r["total_mm"]) >= MIN_DAY_TOTAL_MM]
        if len(wet) >= MIN_GAUGES:
            chosen_day = day
            candidates = sorted(wet, key=lambda r: -float(r["total_mm"]))
            break
    if chosen_day is None:
        print("INCONCLUSIVE: no BST day inside the real-time window with >= 5 matched gauges recording >= 5 mm")
        return 1
    print(f"sample day: {chosen_day} (BST in effect: {is_bst(chosen_day)}); "
          f"{len(candidates)} matched gauges with >= {MIN_DAY_TOTAL_MM} mm and 96 readings")

    results = []
    for row in candidates:
        if len(results) >= 8:
            break
        gauge = matched[row["gauge_id"]]
        ref = ref_by_gauge[gauge["gauge_id"]]
        rt_items = []
        for d in (chosen_day - timedelta(days=1), chosen_day, chosen_day + timedelta(days=1)):
            url = f"{FLOOD_MONITORING}/measures/{rt_measure[ref]}/readings"
            rt_items += get_json(url, {"date": d.isoformat(), "_limit": 500})["items"]
        hy_url = f"{HYDROLOGY}/measures/{gauge['measure_id']}/readings"
        hy_params = {"mineq-date": (chosen_day - timedelta(days=1)).isoformat(),
                     "max-date": (chosen_day + timedelta(days=2)).isoformat(), "_limit": 2000}
        hy_items = get_json(hy_url, hy_params)["items"]
        rt, hy = series(rt_items, "dateTime", True), series(hy_items, "dateTime", False)
        day_start = datetime(chosen_day.year, chosen_day.month, chosen_day.day, tzinfo=timezone.utc)
        rt_total = sum(v for t, v in rt.items() if day_start <= t < day_start + timedelta(days=1))
        if rt_total < MIN_DAY_TOTAL_MM:
            print(f"  skip {gauge['label']} ({ref}): real-time total {rt_total:.1f} mm < {MIN_DAY_TOTAL_MM} mm")
            continue
        offset, scores = best_offset(rt, hy, chosen_day)
        if offset is None:
            print(f"  skip {gauge['label']} ({ref}): too few overlapping readings")
            continue
        s0, s60 = scores.get(0), scores.get(60)
        print(f"  {gauge['label']} (ref {ref}): real-time {rt_total:.1f} mm, Hydrology {row['total_mm']} mm; "
              f"best offset = {offset if offset == 'tie' else f'{offset:+d} min'}; "
              f"at 0 h |diff|={s0[0]} mm exact {s0[1]}/{s0[2]}; at +1 h |diff|={s60[0]} mm exact {s60[1]}/{s60[2]}")
        print(f"    real-time: {FLOOD_MONITORING}/measures/{rt_measure[ref]}/readings?date={chosen_day}")
        print(f"    hydrology: {hy_url}?mineq-date={hy_params['mineq-date']}&max-date={hy_params['max-date']}")
        results.append(offset)

    print(f"gauges compared: {len(results)}; offsets: {results}")
    if len(results) < MIN_GAUGES:
        print(f"INCONCLUSIVE: fewer than {MIN_GAUGES} gauges could be compared")
        return 1
    if len(set(results)) == 1 and results[0] == 0:
        print(f"PASS: Hydrology API dateTime confirmed UTC on {chosen_day} (BST day)")
        return 0
    print("NOT CONFIRMED: offsets are not all 0 h — GATE 1.8")
    return 1


# ---------------------------------------------------------------- step 1.9

DRY_DAY_REQUIRED = ["gauge_id", "gauge_distance_km", "rain_day_mm", "rain_prev24_mm", "rain_window_total_mm",
                    "rain_window_max15_mm", "n_readings_present"]


def step_1_9(args):
    import collections
    import random
    from decimal import Decimal

    ok = True
    cls_dir = ROOT / "data" / "classification"
    events = [r["event_id"] for p in sorted((ROOT / "data" / "events").glob("*.csv")) for r in read_csv(p)]
    rows = read_csv(cls_dir / "all_events_classified.csv")
    by_id = collections.Counter(r["event_id"] for r in rows)

    print("(b) verdicts:", dict(sorted(collections.Counter(r["verdict"] for r in rows).items())))
    print("    is_final:", dict(sorted(collections.Counter(r["is_final"] for r in rows).items())))
    one_row_each = sorted(by_id) == sorted(events) and all(v == 1 for v in by_id.values())
    all_have_verdict = all(r["verdict"] for r in rows)
    print(f"    events={len(events)} classified rows={len(rows)} exactly one row per event: {one_row_each}; "
          f"every row has a verdict: {all_have_verdict}")
    ok &= one_row_each and all_have_verdict

    dry = [r for r in rows if r["verdict"] == "dry_day"]
    missing = [(r["event_id"], [f for f in DRY_DAY_REQUIRED if not r[f]]) for r in dry
               if any(not r[f] for f in DRY_DAY_REQUIRED)]
    print(f"(c) dry_day rows: {len(dry)}; rows missing an evidence field: {len(missing)}")
    for event_id, fields in missing[:10]:
        print(f"    {event_id}: {fields}")
    ok &= not missing

    gauges = {g["gauge_id"]: g for g in read_csv(ROOT / "data" / "rain" / "gauges.csv")}
    sample = random.sample(dry, min(5, len(dry)))
    note = "" if len(dry) >= 5 else f" (only {len(dry)} dry_day events exist)"
    print(f"(d) independent recomputation for {len(sample)} random dry_day events{note}:")
    for r in sample:
        url = f"{HYDROLOGY}/measures/{gauges[r['gauge_id']]['measure_id']}/readings"
        params = {"mineq-date": r["window_start_utc"][:10], "max-date": r["window_end_utc"][:10], "_limit": 2000}
        items = get_json(url, params)["items"]
        values = {}
        for item in items:
            if item.get("value") not in (None, "") and float(item["value"]) >= 0:
                values[item["dateTime"]] = Decimal(str(item["value"]))
        total = sum(values.values(), Decimal(0))
        match = abs(total - Decimal(r["rain_window_total_mm"])) <= Decimal("0.01")
        dry_ok = total <= Decimal("0.25")
        print(f"    {r['event_id']} start {r['start_utc']} gauge {gauges[r['gauge_id']]['label']} "
              f"({r['gauge_distance_km']} km)")
        print(f"      {url}?mineq-date={params['mineq-date']}&max-date={params['max-date']}")
        print(f"      recomputed total {total} mm from {len(values)} readings; stored {r['rain_window_total_mm']} mm "
              f"from {r['n_readings_present']}; match within 0.01: {match}; <= 0.25: {dry_ok}")
        ok &= match and dry_ok

    changes_path = cls_dir / "verdict_changes.csv"
    header = changes_path.read_text(encoding="utf-8").splitlines()[0] if changes_path.exists() else ""
    header_ok = header == "event_id,from_verdict,to_verdict,changed_utc,n_readings_present"
    print(f"(e) verdict_changes.csv exists with header: {header_ok} ({header!r})")
    ok &= header_ok

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- step 1.11

FORBIDDEN_WORDS = ("illegal", "criminal", "guilty")
LEAGUE_COMPANIES = ["anglian", "northumbrian", "severn-trent", "southern", "south-west", "thames",
                    "united-utilities", "wessex", "yorkshire", "st-connect"]


def step_1_11(args):
    import collections
    import html5lib
    import re
    from html5lib.html5parser import ParseError

    site = ROOT / "site"
    ok = True
    pages = sorted(site.rglob("*.html"))
    parser = html5lib.HTMLParser(strict=True, namespaceHTMLElements=False)
    trees, parse_errors = {}, []
    for page in pages:
        try:
            trees[page] = parser.parse(page.read_text(encoding="utf-8"))
        except ParseError as e:
            parse_errors.append((page.relative_to(site).as_posix(), str(e)))
    print(f"(a) pages parsed: {len(pages)}; html5lib strict parse errors: {len(parse_errors)}")
    for rel, err in parse_errors[:10]:
        print(f"    {rel}: {err}")
    ok &= not parse_errors

    root_relative, broken, checked = [], [], 0
    for page, tree in trees.items():
        for el in tree.iter():
            for attr in ("href", "src"):
                url = el.get(attr)
                if url is None or re.match(r"^(https?:|mailto:|#)", url):
                    continue
                checked += 1
                if url.startswith("/"):
                    root_relative.append((page.relative_to(site).as_posix(), url))
                    continue
                target = (page.parent / url.split("#")[0].split("?")[0]).resolve()
                if not target.is_file() or site.resolve() not in target.parents:
                    broken.append((page.relative_to(site).as_posix(), url))
    print(f"(b) internal href/src checked: {checked}; root-relative: {len(root_relative)}; unresolved: {len(broken)}")
    for rel, url in (root_relative + broken)[:10]:
        print(f"    {rel}: {url}")
    ok &= not root_relative and not broken

    rows = read_csv(ROOT / "data" / "classification" / "all_events_classified.csv")
    expected_ids = {r["event_id"] for r in rows if r["verdict"] in ("dry_day", "pending_rain_data")}
    safe = collections.defaultdict(list)
    for eid in sorted(expected_ids):
        safe[re.sub(r"[^A-Za-z0-9_-]", "_", eid)].append(eid)
    expected_files = {f"{base}.html" if i == 0 else f"{base}-{i + 1}.html"
                      for base, eids in safe.items() for i, _ in enumerate(eids)}
    actual_files = {p.name for p in (site / "events").glob("*.html") if not re.match(r"^index(-\d+)?\.html$", p.name)}
    missing, extra = expected_files - actual_files, actual_files - expected_files
    print(f"(c) dry_day + pending_rain_data events: {len(expected_ids)}; event pages: {len(actual_files)}; "
          f"missing: {len(missing)}; extra: {len(extra)}")
    ok &= not missing and not extra

    def metrics(page):
        tree = trees[site / page]
        out = {}
        for el in tree.iter():
            if el.get("data-metric") and el.get("data-value") is not None:
                out.setdefault(el.get("data-metric"), el.get("data-value"))
        return out, tree

    meta = read_json_file(ROOT / "data" / "meta.json")
    overflows = read_csv(ROOT / "data" / "overflows.csv")
    index_tree = trees[site / "index.html"]
    build_utc = next(el.get("content") for el in index_tree.iter() if el.get("name") == "swt-build-utc")
    today = date.fromisoformat(build_utc[:10])
    launch_day = date.fromisoformat(meta["launch_utc"][:10])
    ranges = {"last30": (max(today - timedelta(days=30), launch_day), today - timedelta(days=1)),
              "year": (max(date(today.year, 1, 1), launch_day), today)}

    def within(r, key):
        start, end = ranges[key]
        return start.isoformat() <= r["day_utc"] <= end.isoformat()

    expected = {
        "tile-dry-last30": sum(1 for r in rows if r["verdict"] == "dry_day" and within(r, "last30")),
        "tile-dry-year": sum(1 for r in rows if r["verdict"] == "dry_day" and within(r, "year")),
        "tile-events-last30": sum(1 for r in rows if within(r, "last30")),
        "tile-overflows": len(overflows),
        "hero-overflows": len(overflows),
    }
    shown, _ = metrics("index.html")
    mismatches = [(k, v, shown.get(k)) for k, v in expected.items() if shown.get(k) != str(v)]
    print(f"(d) build date {today}; last30 {ranges['last30'][0]}..{ranges['last30'][1]}; "
          f"year {ranges['year'][0]}..{ranges['year'][1]}")
    print("    tiles expected:", expected)
    print("    tiles shown:   ", {k: shown.get(k) for k in expected})

    n_overflows = collections.Counter(o["company_slug"] for o in overflows)
    last_dry = {}
    for r in sorted(rows, key=lambda r: r["start_utc"]):
        if r["verdict"] == "dry_day":
            last_dry[r["company_slug"]] = r["day_utc"]
    league_checked = 0
    for page in ("index.html", "companies/index.html"):
        tree = trees[site / page]
        for table in (el for el in tree.iter("table") if el.get("data-league")):
            key = table.get("data-league")
            for tr in (el for el in table.iter("tr") if el.get("data-company")):
                slug = tr.get("data-company")
                in_p = [r for r in rows if r["company_slug"] == slug and within(r, key)]
                dry = sum(1 for r in in_p if r["verdict"] == "dry_day")
                exp = {"overflows": str(n_overflows[slug]), "events": str(len(in_p)), "dry": str(dry),
                       "per100": f"{dry * 100 / n_overflows[slug]:.1f}" if n_overflows[slug] else "0.0",
                       "last_dry": last_dry.get(slug, "")}
                got = {td.get("data-metric"): td.get("data-value") for td in tr.iter("td")}
                for k, v in exp.items():
                    league_checked += 1
                    if got.get(k) != v:
                        mismatches.append((f"{page} {key} {slug} {k}", v, got.get(k)))
    print(f"    league table cells checked: {league_checked}; mismatches (tiles + league): {len(mismatches)}")
    for m in mismatches[:10]:
        print(f"    {m[0]}: expected {m[1]!r}, shown {m[2]!r}")
    ok &= not mismatches and league_checked == 2 * 2 * len(LEAGUE_COMPANIES) * 5

    hits = []
    for path in site.rglob("*"):
        if path.is_file() and path.suffix in (".html", ".csv", ".js", ".css", ".svg", ".txt", ".json"):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            hits += [(path.relative_to(site).as_posix(), w) for w in FORBIDDEN_WORDS if w in text]
    print(f"(e) forbidden words {FORBIDDEN_WORDS} in site/: {len(hits)} hits {hits[:5]}")
    ok &= not hits

    missing_head = []
    for page, tree in trees.items():
        title = next((el.text for el in tree.iter("title")), "") or ""
        metas = {el.get("name"): el.get("content") for el in tree.iter("meta") if el.get("name")}
        if not title.strip() or not (metas.get("description") or "").strip() or metas.get("robots") != "noindex":
            missing_head.append(page.relative_to(site).as_posix())
    print(f"(f) pages missing <title>, meta description or noindex: {len(missing_head)} {missing_head[:5]}")
    ok &= not missing_head

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- step 1.13

CONTRAST_PAIRS = [("text", "bg"), ("muted", "bg"), ("flag", "bg"), ("text", "surface"), ("muted", "surface"),
                  ("flag", "surface"), ("black", "white")]


def relative_luminance(hex_colour):
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a, b):
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def step_1_13(args):
    import functools
    import http.server
    import re
    import threading
    from playwright.sync_api import sync_playwright  # imported here only: the deploy job does not install Playwright

    ok = True
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    root_block = re.search(r":root\s*\{([^}]*)\}", css).group(1)
    palette = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", root_block))
    print("contrast ratios (WCAG, from style.css :root):")
    for fg, bg in CONTRAST_PAIRS:
        ratio = contrast_ratio(palette[fg], palette[bg])
        passed = ratio >= 4.5
        ok &= passed
        print(f"    --{fg} {palette[fg]} on --{bg} {palette[bg]}: {ratio:.2f}:1 {'ok' if passed else 'FAIL'}")

    site = ROOT / "site"
    rows = read_csv(ROOT / "data" / "classification" / "all_events_classified.csv")
    dry = sorted((r for r in rows if r["verdict"] == "dry_day"), key=lambda r: r["start_utc"], reverse=True)
    sample = dry or [r for r in rows if r["verdict"] == "pending_rain_data"]
    event_page = "events/" + re.sub(r"[^A-Za-z0-9_-]", "_", sample[0]["event_id"]) + ".html"
    pages = [("index", "index.html"), ("company", "companies/anglian.html"), ("event", event_page),
             ("method", "method.html")]
    print(f"event page used: {event_page} ({sample[0]['verdict']})")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(QuietHandler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    shots = ROOT / "screenshots"
    shots.mkdir(exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                for name, path in pages:
                    page.goto(base + path, wait_until="networkidle")
                    page.evaluate("document.fonts.ready")
                    out = shots / f"{name}-{width}x{height}.png"
                    page.screenshot(path=str(out), full_page=True)
                    scroll_width = page.evaluate("document.documentElement.scrollWidth")
                    line = f"    {out.name}: scrollWidth={scroll_width}"
                    if width == 390:
                        passed = scroll_width <= 390
                        ok &= passed
                        line += f" (<= 390: {passed})"
                    if name == "index" and width == 1440:
                        box = page.locator(".hero-title").bounding_box()
                        headline_ok = box is not None and box["y"] >= 0 and box["y"] + box["height"] <= height
                        pill = page.locator(".nav .pill")
                        pill_box = pill.bounding_box()
                        pill_ok = pill.is_visible() and pill_box is not None and pill_box["y"] + pill_box["height"] <= height
                        ok &= headline_ok and pill_ok
                        line += (f"; hero headline top={box['y']:.0f} bottom={box['y'] + box['height']:.0f} "
                                 f"(fully above the fold: {headline_ok}); nav pill visible: {pill_ok}")
                    print(line)
                page.close()
            browser.close()
    finally:
        server.shutdown()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def read_json_file(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


STEPS = {"1.8": step_1_8, "1.9": step_1_9, "1.11": step_1_11, "1.13": step_1_13}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", required=True, choices=sorted(STEPS))
    args = ap.parse_args()
    try:
        return STEPS[args.step](args)
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
