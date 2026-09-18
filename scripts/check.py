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


def site_checks():
    """Runs CHECK 1.11's parts and returns the findings, so the acceptance table can reuse them."""
    import collections
    import html5lib
    import re
    from html5lib.html5parser import ParseError

    site = ROOT / "site"
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

    hits = []
    for path in site.rglob("*"):
        if path.is_file() and path.suffix in (".html", ".csv", ".js", ".css", ".svg", ".txt", ".json"):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            hits += [(path.relative_to(site).as_posix(), w) for w in FORBIDDEN_WORDS if w in text]
    print(f"(e) forbidden words {FORBIDDEN_WORDS} in site/: {len(hits)} hits {hits[:5]}")

    missing_head = []
    for page, tree in trees.items():
        title = next((el.text for el in tree.iter("title")), "") or ""
        metas = {el.get("name"): el.get("content") for el in tree.iter("meta") if el.get("name")}
        if not title.strip() or not (metas.get("description") or "").strip() or metas.get("robots") != "noindex":
            missing_head.append(page.relative_to(site).as_posix())
    print(f"(f) pages missing <title>, meta description or noindex: {len(missing_head)} {missing_head[:5]}")

    return {"pages": len(pages), "parse_errors": parse_errors, "root_relative": root_relative, "broken": broken,
            "links_checked": checked, "missing_pages": missing, "extra_pages": extra, "event_pages": len(actual_files),
            "mismatches": mismatches, "league_cells": league_checked, "forbidden": hits, "missing_head": missing_head,
            "trees": trees, "site": site}


def step_1_11(args):
    r = site_checks()
    ok = not (r["parse_errors"] or r["root_relative"] or r["broken"] or r["missing_pages"] or r["extra_pages"]
              or r["mismatches"] or r["forbidden"] or r["missing_head"])
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


def design_checks():
    import functools
    import http.server
    import re
    import threading
    from playwright.sync_api import sync_playwright  # imported here only: the deploy job does not install Playwright

    report = {"contrast": [], "scroll": {}, "headline_ok": None, "pill_ok": None}
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    root_block = re.search(r":root\s*\{([^}]*)\}", css).group(1)
    palette = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", root_block))
    print("contrast ratios (WCAG, from style.css :root):")
    for fg, bg in CONTRAST_PAIRS:
        ratio = contrast_ratio(palette[fg], palette[bg])
        passed = ratio >= 4.5
        report["contrast"].append((fg, bg, round(ratio, 2), passed))
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
                        report["scroll"][name] = (scroll_width, passed)
                        line += f" (<= 390: {passed})"
                    if name == "index" and width == 1440:
                        box = page.locator(".hero-title").bounding_box()
                        headline_ok = box is not None and box["y"] >= 0 and box["y"] + box["height"] <= height
                        pill = page.locator(".nav .pill")
                        pill_box = pill.bounding_box()
                        pill_ok = pill.is_visible() and pill_box is not None and pill_box["y"] + pill_box["height"] <= height
                        report["headline_ok"], report["pill_ok"] = headline_ok, pill_ok
                        line +=  (f"; hero headline top={box['y']:.0f} bottom={box['y'] + box['height']:.0f} "
                                 f"(fully above the fold: {headline_ok}); nav pill visible: {pill_ok}")
                    print(line)
                page.close()
            browser.close()
    finally:
        server.shutdown()
    return report


def step_1_13(args):
    r = design_checks()
    ok = (all(c[3] for c in r["contrast"]) and all(v[1] for v in r["scroll"].values())
          and r["headline_ok"] and r["pill_ok"])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- step 1.14

def method_checks():
    """Every [method] quote in 06_SOURCES.md appears verbatim in the HTML-unescaped text of site/method.html,
    and every [method] link appears as an href. Only runs of spaces are normalised; quotes are never altered."""
    import html
    import html5lib
    import re

    sources = (ROOT / "build-pack" / "06_SOURCES.md").read_text(encoding="utf-8").splitlines()
    quotes, links = [], []
    for line in sources:
        if "`[method]`" not in line:
            continue
        m = re.match(r'\s*\d+\.\s+`\[method\]`.*?—\s+(https?://\S+)', line)
        if m:
            links.append(m.group(1))
            continue
        m = re.match(r'\s*-\s+`\[method\]`\s+"(.*)"', line)
        if m:
            # the quote is the text inside the first pair of straight double quotes after the tag
            quotes.append(re.match(r'([^"]*)"', m.group(1) + '"').group(1))

    raw = (ROOT / "site" / "method.html").read_text(encoding="utf-8")
    tree = html5lib.parse(raw, namespaceHTMLElements=False)
    text = re.sub(r" +", " ", html.unescape(" ".join(tree.find(".//body").itertext())).replace("\n", " "))
    hrefs = {el.get("href") for el in tree.iter("a") if el.get("href")}

    missing_quotes = [q for q in quotes if re.sub(r" +", " ", q) not in text]
    missing_links = [u for u in links if u not in hrefs]
    print(f"[method] quotes in 06_SOURCES.md: {len(quotes)}; missing from method.html: {len(missing_quotes)}")
    for q in quotes:
        print(f"    {'MISSING' if q in missing_quotes else 'ok     '} {q}")
    print(f"[method] links in 06_SOURCES.md: {len(links)}; missing as href: {len(missing_links)}")
    for u in links:
        print(f"    {'MISSING' if u in missing_links else 'ok     '} {u}")
    return {"quotes": quotes, "links": links, "missing_quotes": missing_quotes, "missing_links": missing_links,
            "text": text}


def step_1_14(args):
    r = method_checks()
    ok = not r["missing_quotes"] and not r["missing_links"]
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- acceptance: phase 1

def _rows_by(path_glob):
    return [r for p in sorted(path_glob) for r in read_csv(p)]


def acceptance_phase1(args):
    """05_CHECKS_AND_ACCEPTANCE.md Phase 1: one row per item, printed as a table."""
    import collections
    import html
    import json
    import random
    import re
    import subprocess
    from decimal import Decimal

    data = ROOT / "data"
    results = []

    def add(item, expected, observed, status):
        results.append((item, expected, observed, status))
        print(f"  {item:4} {status:6} {observed}")

    def run(cmd, **kw):
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), **kw)

    meta = read_json_file(data / "meta.json")
    launch_day = date.fromisoformat(meta["launch_utc"][:10])
    overflows = {o["overflow_key"]: o for o in read_csv(data / "overflows.csv")}
    events = _rows_by((data / "events").glob("*.csv"))
    rows = read_csv(data / "classification" / "all_events_classified.csv")
    gauges = {g["gauge_id"]: g for g in read_csv(data / "rain" / "gauges.csv")}
    now = datetime.now(timezone.utc)

    print("A. Correctness of the rule")
    r = run([sys.executable, "-m", "pytest", "-q", "tests/test_rule.py"])
    add("A1", "pass", r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-200:],
        "PASS" if r.returncode == 0 else "FAIL")

    def recompute(sample, want_dry):
        bad = []
        for row in sample:
            gauge = gauges.get(row["gauge_id"])
            url = f"{HYDROLOGY}/measures/{gauge['measure_id']}/readings"
            items = get_json(url, {"mineq-date": row["window_start_utc"][:10], "max-date": row["window_end_utc"][:10],
                                   "_limit": 2000})["items"]
            values = {i["dateTime"]: Decimal(str(i["value"])) for i in items
                      if i.get("value") not in (None, "") and float(i["value"]) >= 0}
            total = sum(values.values(), Decimal(0))
            within = abs(total - Decimal(row["rain_window_total_mm"])) <= Decimal("0.01")
            side = total <= Decimal("0.25") if want_dry else total > Decimal("0.25")
            if not (within and side):
                bad.append(f"{row['event_id']}: recomputed {total} vs stored {row['rain_window_total_mm']}")
        return bad

    random.seed()
    dry = [r for r in rows if r["verdict"] == "dry_day"]
    not_dry = [r for r in rows if r["verdict"] == "not_dry"]
    sample_dry = random.sample(dry, min(10, len(dry)))
    sample_not = random.sample(not_dry, min(10, len(not_dry)))
    bad = recompute(sample_dry, True)
    add("A2", "all within 0.01 mm and <= 0.25", f"{len(sample_dry)} recomputed, {len(bad)} mismatched {bad[:3]}",
        "PASS" if not bad else "FAIL")
    bad = recompute(sample_not, False)
    add("A3", "all within 0.01 mm and > 0.25", f"{len(sample_not)} recomputed, {len(bad)} mismatched {bad[:3]}",
        "PASS" if not bad else "FAIL")

    notes = (ROOT / "NOTES_FOR_JAIMIN.md").read_text(encoding="utf-8")
    method_text = method_checks()["text"]
    tz_note = "Hydrology API dateTime confirmed UTC on 2026-09-15" in notes
    tz_page = "Hydrology API times are therefore UTC" in method_text and "15 September 2026" in method_text
    add("A4", "present, offset 0 h", f"NOTES: {tz_note}; Method page: {tz_page}",
        "PASS" if tz_note and tz_page else "FAIL")

    bad_readings = [r["event_id"] for r in dry if int(r["n_readings_present"] or 0) < 176]
    bad_final = []
    for r in rows:
        window_end = datetime.strptime(r["window_end_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        n = int(r["n_readings_present"] or 0)
        if r["verdict"] == "no_gauge_within_10km":
            expect = True
        elif r["verdict"] in ("dry_day", "not_dry"):
            expect = (n == 192 and now >= window_end + timedelta(hours=72)) or now >= window_end + timedelta(days=14)
        else:
            expect = False
        if (r["is_final"] == "true") != expect:
            bad_final.append(r["event_id"])
    add("A5", "0 violations", f"dry_day with < 176 readings: {len(bad_readings)}; is_final violations: {len(bad_final)}",
        "PASS" if not bad_readings and not bad_final else "FAIL")
    far = [r["event_id"] for r in dry if float(r["gauge_distance_km"]) > 10.0]
    add("A6", "0 violations", f"dry_day with gauge > 10.0 km: {len(far)}", "PASS" if not far else "FAIL")
    ids = [r["event_id"] for r in rows]
    add("A7", "counts equal", f"events {len(events)}, classified rows {len(rows)}, unique {len(set(ids))}",
        "PASS" if len(events) == len(rows) == len(set(ids)) else "FAIL")

    print("B. Correctness of the collector")
    srcs = read_json_file(ROOT / "scripts" / "sources_resolved.json")
    live = 0
    for slug, src in srcs.items():
        live += get_json(src["layer_url"] + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    drift = (len(overflows) - live) / live * 100
    add("B1", "within +-2%", f"overflows.csv {len(overflows)} vs live feeds {live} ({drift:+.2f}%)",
        "PASS" if abs(drift) <= 2 else "FAIL")
    event_ids = [e["event_id"] for e in events]
    add("B2", "yes", f"{len(event_ids)} event ids, {len(set(event_ids))} unique",
        "PASS" if len(event_ids) == len(set(event_ids)) else "FAIL")
    backwards = [e["event_id"] for e in events if e["end_utc"] and e["end_utc"] < e["start_utc"]]
    add("B3", "0", f"events with end before start: {len(backwards)}", "PASS" if not backwards else "FAIL")
    ended = [e for e in events if e["end_utc"]]
    inferred = [e for e in ended if e["end_observed"] == "false"]
    share = len(inferred) / len(ended) * 100 if ended else 0
    add("B4", "report; expect < 5%", f"end_observed=false: {len(inferred)} of {len(ended)} ended events ({share:.2f}%)",
        "PASS" if share < 5 else "FAIL")
    import shutil as _shutil
    tmp = ROOT / ".cache" / "acceptance"
    _shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "a").mkdir(parents=True)
    (tmp / "b").mkdir(parents=True)
    fixture = ["--sources", "tests/fixtures/sources_fixture.json", "--fixture", "tests/fixtures/snapshot_a.json",
               "--now", "2026-01-01T00:00:00Z"]
    run([sys.executable, "scripts/collect.py", *fixture, "--data", str(tmp / "a")])
    run([sys.executable, "scripts/collect.py", *fixture, "--data", str(tmp / "b")])
    diff = run(["diff", "-r", str(tmp / "a"), str(tmp / "b")])
    add("B5", "identical output", "identical" if diff.returncode == 0 else diff.stdout[:200],
        "PASS" if diff.returncode == 0 else "FAIL")
    since = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    gh = run(["gh", "run", "list", "--workflow", "poll", "--limit", "300", "--json",
              "status,conclusion,createdAt"])
    runs = [r for r in json.loads(gh.stdout or "[]") if r["createdAt"] >= since]
    done = [r for r in runs if r["status"] == "completed" and r["conclusion"] != "cancelled"]
    success = [r for r in done if r["conclusion"] == "success"]
    pct = len(success) / len(done) * 100 if done else 0
    add("B6", ">= 97%", f"{len(success)} of {len(done)} non-cancelled poll runs in 48 h succeeded ({pct:.1f}%); "
        f"{len(runs) - len(done)} cancelled/running", "PASS" if done and pct >= 97 else "FAIL")
    changes = read_csv(data / "classification" / "verdict_changes.csv")
    flips = [c for c in changes if c["from_verdict"] == "dry_day" and c["to_verdict"] == "not_dry"]
    add("B7", "report", f"dry_day -> not_dry flips since launch: {len(flips)} (all changes: {len(changes)})", "INFO")

    print("C. Site integrity")
    site = site_checks()
    add("C1", "0 errors", f"{site['pages']} pages, {len(site['parse_errors'])} parse errors",
        "PASS" if not site["parse_errors"] else "FAIL")
    add("C2", "0 broken", f"{site['links_checked']} internal links, {len(site['broken'])} broken, "
        f"{len(site['root_relative'])} root-relative",
        "PASS" if not site["broken"] and not site["root_relative"] else "FAIL")
    add("C3", "exact", f"{site['league_cells']} league cells + tiles compared, {len(site['mismatches'])} mismatches",
        "PASS" if not site["mismatches"] else "FAIL")
    add("C4", "0", f"forbidden words found: {len(site['forbidden'])}", "PASS" if not site["forbidden"] else "FAIL")
    add("C5", "yes", f"{site['event_pages']} event pages; missing {len(site['missing_pages'])}, "
        f"extra {len(site['extra_pages'])}",
        "PASS" if not site["missing_pages"] and not site["extra_pages"] else "FAIL")
    m = method_checks()
    add("C6", "0 missing", f"{len(m['quotes'])} quotes, {len(m['links'])} links; missing "
        f"{len(m['missing_quotes'])} / {len(m['missing_links'])}",
        "PASS" if not m["missing_quotes"] and not m["missing_links"] else "FAIL")

    log = read_json_file(data / "deploy_log.json")
    last = max(log, key=lambda e: e["utc"]) if log else None
    footer = re.search(r"Last poll: (.*?) · Rain data last updated: (.*?) · Last classification change: (.*?)<",
                       (ROOT / "site" / "index.html").read_text(encoding="utf-8"))
    if last and footer:
        def parse_footer(t):
            return datetime.strptime(html.unescape(t).replace(" UTC", ""), "%d %b %Y, %H:%M").replace(
                tzinfo=timezone.utc)
        deploy_at = datetime.strptime(last["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        build_utc = re.search(r'name="swt-build-utc" content="([^"]+)"',
                              (ROOT / "site" / "index.html").read_text(encoding="utf-8")).group(1)
        built_at = datetime.strptime(build_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        poll_gap = (built_at - parse_footer(footer.group(1))).total_seconds() / 3600
        rain_gap = (built_at - parse_footer(footer.group(2))).total_seconds() / 3600
        add("C7", "poll within 2 h, rain within 26 h of the build",
            f"footer vs its own build ({build_utc}): poll {poll_gap:+.1f} h, rain {rain_gap:+.1f} h; "
            f"last deploy {last['kind']} {last['utc']} ({(now - deploy_at).total_seconds() / 3600:.1f} h ago)",
            "PASS" if poll_gap <= 2 and rain_gap <= 26 else "FAIL")
    else:
        add("C7", "consistent", "no deploy log entry or no footer found", "FAIL")

    site_url = meta["site_url"]
    try:
        resp = requests.get(site_url, timeout=60)
        body_ok = "storm water tracker" not in resp.text.lower()
        add("C8", "Netlify access page, no wordmark", f"HTTP {resp.status_code} from {site_url}; wordmark present: "
            f"{not body_ok}; logged-in view confirmed by Jaimin on 17 Sep 2026", "PASS" if body_ok else "FAIL")
    except requests.RequestException as e:
        add("C8", "Netlify access page", f"request failed: {e}", "FAIL")

    months = set()
    for path in (ROOT / "site" / "companies").glob("*.html"):
        months |= set(re.findall(r"<th scope=\"row\">([A-Z][a-z]{2} \d{4})", path.read_text(encoding="utf-8")))
    early = [m for m in months if datetime.strptime(m, "%b %Y").date() < date(launch_day.year, launch_day.month, 1)]
    partial = f"{launch_day:%b} {launch_day.year} (partial, from" in \
        (ROOT / "site" / "companies" / "anglian.html").read_text(encoding="utf-8")
    add("C9", "no period before launch; launch month labelled partial",
        f"months shown: {sorted(months)}; before launch month: {len(early)}; launch month labelled partial: {partial}",
        "PASS" if not early and partial else "FAIL")

    netlify = run(["npx", "--yes", "netlify-cli@27", "sites:list", "--json"])
    repo_url = "unknown"
    try:
        sites = json.loads(netlify.stdout[netlify.stdout.index("["):])
        for entry in sites:
            if entry.get("name") == site_url.split("//")[1].split(".")[0]:
                repo_url = (entry.get("build_settings") or {}).get("repo_url")
    except (ValueError, IndexError):
        pass
    add("C10", "no linked repo; Private production and previews",
        f"build_settings.repo_url = {repo_url!r}; visibility must be confirmed by Jaimin in the Netlify UI",
        "PASS" if repo_url in (None, "", "null") else "MANUAL")

    month = now.strftime("%Y-%m")
    prod = [e for e in log if e["kind"] == "prod" and e["utc"][:7] == month]
    fields_ok = all(set(e) == {"utc", "kind", "run_url", "message", "deploy_url"} for e in log)
    guard = run([sys.executable, "-m", "pytest", "-q", "tests/test_deploy_guard.py"])
    add("C11", "<= 8 prod this month; all fields; guard tests pass",
        f"prod this month: {len(prod)}; entries {len(log)} all with the five fields: {fields_ok}; "
        f"deploy_guard tests: {'pass' if guard.returncode == 0 else 'FAIL'}",
        "PASS" if len(prod) <= 8 and fields_ok and guard.returncode == 0 else "FAIL")
    credits = re.findall(r"credits? (?:remaining|after)[^\n]*?(\d+) of 300|credits remaining[^\n]*?= (\d+)", notes)
    add("C12", "report", f"latest credit readings recorded in NOTES: {credits[-3:]}; Jaimin reads the current figure "
        f"at acceptance", "MANUAL")

    print("D. Design")
    design = design_checks()
    worst = min(c[2] for c in design["contrast"])
    add("D1", "all >= 4.5:1", f"lowest ratio {worst}:1 across {len(design['contrast'])} pairs",
        "PASS" if all(c[3] for c in design["contrast"]) else "FAIL")
    add("D2", "yes", "; ".join(f"{k} {v[0]}px" for k, v in design["scroll"].items()),
        "PASS" if all(v[1] for v in design["scroll"].values()) else "FAIL")
    add("D3", "yes", f"hero headline above the fold: {design['headline_ok']}; nav pill visible: {design['pill_ok']}",
        "PASS" if design["headline_ok"] and design["pill_ok"] else "FAIL")
    palette = {"#0b0b0c", "#121214", "#262629", "#ececec", "#8b8b90", "#4a4a4f", "#d9b26a", "#5b4a2a", "#ffffff",
               "#000000", "rgba(255,255,255,0.03)"}
    stray = []
    for path in [ROOT / "static" / "style.css"] + sorted((ROOT / "templates").glob("*.html")):
        text = path.read_text(encoding="utf-8")
        for hit in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", text):
            if hit.lower().replace(" ", "") not in palette:
                stray.append(f"{path.name}: {hit}")
    add("D4", "only the eleven values", f"colour literals outside the palette: {len(stray)} {stray[:5]}",
        "PASS" if not stray else "FAIL")
    external = set()
    for page, tree in site["trees"].items():
        for el in tree.iter("script"):
            if el.get("src") and re.match(r"^(https?:)?//", el.get("src")):
                external.add(el.get("src"))
        for el in tree.iter("link"):
            href = el.get("href") or ""
            # only stylesheets count here; canonical and preconnect links are not fetched resources
            if el.get("rel") == "stylesheet" and re.match(r"^(https?:)?//", href) \
                    and "fonts.googleapis.com" not in href:
                external.add(href)
    add("D5", "none except Google Fonts CSS", f"external scripts/stylesheets: {sorted(external) or 'none'}",
        "PASS" if not external else "FAIL")
    add("D6", "accepted", "GATE 3, 17 Sep 2026: \"The site looks good. Really like it.\""
        if "The site looks good" in notes else "not recorded in NOTES",
        "PASS" if "The site looks good" in notes else "FAIL")

    print("E. Hygiene")
    secrets = run(["git", "grep", "-inE", "client_secret|netlify_auth|nfp_", "--", ".", ":!build-pack",
                   ":!NOTES_FOR_JAIMIN.md"])
    # Two matches carry no secret value and are expected (Jaimin's decision, 18 Sep 2026): the workflow line that
    # names the GitHub secret (the value is substituted at run time and never stored), and this file, which
    # contains the search pattern itself. Anything else is a failure.
    expected = re.compile(r"^\.github/workflows/[^:]+:\d+:\s*[A-Z_]+: \$\{\{ secrets\.[A-Z_]+ \}\}\s*$"
                          r"|^scripts/check\.py:\d+:")
    hits = [line for line in secrets.stdout.splitlines() if not expected.match(line)]
    ignored = ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    tracked_env = run(["git", "ls-files", ".env"]).stdout.strip()
    add("E1", "clean", f"secret-pattern hits beyond GitHub secret references and this check: {len(hits)} {hits[:3]}; "
        f".env ignored: {ignored}, tracked: {bool(tracked_env)}",
        "PASS" if not hits and ignored and not tracked_env else "FAIL")
    open_markers = notes.count("[OPEN]")
    add("E2", "0", f"[OPEN] markers in NOTES_FOR_JAIMIN.md: {open_markers}", "PASS" if not open_markers else "FAIL")
    required = {"UTC assumption": "We use UTC calendar days", "BST verification date": "15 September 2026",
                "10 km assumption": "within 10 km", "total vs max": "We use the total",
                "provisional vs final": "A verdict is final when it can no longer change",
                "the lag": "typically appears one to three days", "what can be missed": "never seen",
                "Hub not audited": "has not undergone an audit process",
                "launch-date caveat": "Our complete record begins on",
                "ST Connect placeholder": "placeholder feed"}
    missing_e3 = [k for k, v in required.items() if v not in method_text]
    add("E3", "all present", f"missing Method-page statements: {missing_e3 or 'none'}",
        "PASS" if not missing_e3 else "FAIL")
    data_text = (ROOT / "site" / "data.html").read_text(encoding="utf-8")
    e4 = [k for k, v in {"site CC BY 4.0": "own content and data files: CC BY 4.0",
                         "Hub CC BY 4.0": "National Storm Overflow Hub (Stream), CC BY 4.0",
                         "EA OGL v3": "Open Government Licence v3.0"}.items() if v not in data_text]
    add("E4", "present", f"missing licence statements on the Data page: {e4 or 'none'}", "PASS" if not e4 else "FAIL")

    print("\n| item | expected | observed | result |")
    print("|---|---|---|---|")
    for item, expected, observed, status in results:
        print(f"| {item} | {expected} | {observed} | {status} |")
    counts = collections.Counter(r[3] for r in results)
    print(f"\n{dict(counts)}")
    return 0 if not counts["FAIL"] else 1


def read_json_file(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


STEPS = {"1.8": step_1_8, "1.9": step_1_9, "1.11": step_1_11, "1.13": step_1_13, "1.14": step_1_14}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=sorted(STEPS))
    ap.add_argument("--acceptance", choices=["phase1"])
    args = ap.parse_args()
    if not args.step and not args.acceptance:
        ap.error("give --step or --acceptance")
    try:
        return acceptance_phase1(args) if args.acceptance else STEPS[args.step](args)
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
