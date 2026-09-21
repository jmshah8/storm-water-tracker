#!/usr/bin/env python3
"""Build the static site into site/ from the committed data (01_SPEC.md §7–8).

Every number shown on a page is also written as a data-value attribute (checked by check.py --step 1.11).
All internal links are relative. The footer's "last poll" time comes from the poll workflow's latest
successful run (GitHub API); if that cannot be read, the footer says when the discharge data last changed.

Exit codes: 0 ok, 1 build failed (e.g. an event page slug collision that cannot be resolved), 2 network error.
"""
import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.geo import nearest_gauges  # noqa: E402
from swt.io import read_csv, read_json  # noqa: E402

COMPANIES = [
    ("anglian", "Anglian Water"), ("northumbrian", "Northumbrian Water"), ("severn-trent", "Severn Trent Water"),
    ("southern", "Southern Water"), ("south-west", "South West Water"), ("thames", "Thames Water"),
    ("united-utilities", "United Utilities"), ("wessex", "Wessex Water"), ("yorkshire", "Yorkshire Water"),
    ("st-connect", "ST Connect"),
]
COMPANY_NAMES = dict(COMPANIES)
EVENTS_PER_PAGE = 200
COMPANY_SPILLS_PER_PAGE = 100
LATEST_SPILLS = 20
HYDROLOGY = "https://environment.data.gov.uk/hydrology/id"
RADAR_THRESHOLD_MM = 0.25   # the same threshold as the rule, applied to the radar's 3x3 maximum
EA_RULE = ("A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as "
           "no rainfall above 0.25mm on that day and the preceding 24 hours.")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PAGE_EVENT_VERDICTS = ("dry_day", "pending_rain_data")


# ---------------------------------------------------------------- formatting

def parse_iso(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fmt_datetime(iso):
    if not iso:
        return ""
    d = parse_iso(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {d:%H:%M} UTC"


def fmt_datetime_seconds(iso):
    if not iso:
        return ""
    d = parse_iso(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {d:%H:%M:%S} UTC"


def fmt_date(value):
    if not value:
        return ""
    d = date.fromisoformat(value[:10]) if isinstance(value, str) else value
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def thin(n):
    """Thousands separated by a thin space, for prose (§7.7)."""
    return f"{int(n):,}".replace(",", " ")


def duration_seconds(ev):
    if not ev["end_utc"]:
        return None
    return int((parse_iso(ev["end_utc"]) - parse_iso(ev["start_utc"])).total_seconds())


def fmt_duration(seconds):
    """Exact length from the published start and end times (both to the second)."""
    if seconds is None:
        return "No end time published yet"
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m} min {s} s" if s else f"{m} min"
    days, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = ([f"{days} d"] if days else []) + [f"{h} h", f"{m} min"]
    return " ".join(parts)


def safe_id(event_id):
    return re.sub(r"[^A-Za-z0-9_-]", "_", event_id)


def slug_map(event_ids):
    """event_id -> page slug; collisions after slugging get -2, -3 ... in event_id order."""
    out, used = {}, set()
    groups = defaultdict(list)
    for eid in sorted(event_ids):
        groups[safe_id(eid)].append(eid)
    for base, eids in sorted(groups.items()):
        for i, eid in enumerate(eids):
            slug = base if i == 0 else f"{base}-{i + 1}"
            if slug in used:
                raise ValueError(f"event page slug collision cannot be resolved: {slug}")
            used.add(slug)
            out[eid] = slug
    return out


def radar_coverage(frames):
    """What the radar archive actually holds: first day, last day and the days missing in between.

    The Met Office bucket keeps a rolling two years and has gaps of its own near its oldest edge, so the
    Method page states the cover rather than implying it is complete.
    """
    from datetime import date as _date, timedelta as _timedelta

    if not frames:
        return {"first": "", "last": "", "missing": [], "n_days": 0}
    days = sorted(frames)
    first, last = _date.fromisoformat(days[0]), _date.fromisoformat(days[-1])
    held, missing, day = set(days), [], first
    while day <= last:
        if day.isoformat() not in held:
            missing.append(day.isoformat())
        day += _timedelta(days=1)
    return {"first": days[0], "last": days[-1], "missing": missing, "n_days": len(days)}


def radar_label(row):
    """'radar_agrees' / 'radar_disagrees' for a dry day flag with complete radar; '' otherwise (03 plan §2.4).

    Derived at build time only: the radar never changes a verdict.
    """
    if row["verdict"] != "dry_day" or row["radar_status"] != "complete" or not row["radar_3x3_max_total_mm"]:
        return ""
    return "radar_agrees" if float(row["radar_3x3_max_total_mm"]) <= RADAR_THRESHOLD_MM else "radar_disagrees"


def radar_frames(data):
    """{date: n_frames} read from the first row of each radar daily file."""
    import csv
    import gzip

    frames = {}
    for path in sorted((data / "radar" / "daily").glob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            first = next(csv.DictReader(f), None)
        if first:
            frames[path.name[:-len(".csv.gz")]] = first["n_frames"]
    return frames


def per_100(dry, overflows):
    return f"{dry * 100 / overflows:.1f}" if overflows else "0.0"


# ---------------------------------------------------------------- periods

def periods(today, launch_day):
    """(key, label, start, end) with start/end inclusive UTC dates; nothing before launch_day."""
    out = []
    start30, end30 = today - timedelta(days=30), today - timedelta(days=1)
    s = max(start30, launch_day)
    label = "Last 30 days"
    if s > start30:
        label += f" (partial, from {fmt_date(launch_day)})"
    out.append(("last30", label, s, end30))
    jan1 = date(today.year, 1, 1)
    s = max(jan1, launch_day)
    label = "This year" + (f" (partial, from {fmt_date(launch_day)})" if s > jan1 else "")
    out.append(("year", label, s, today))
    return out


def in_period(row, start, end):
    return start.isoformat() <= row["day_utc"] <= end.isoformat()


# ---------------------------------------------------------------- last-run times

def latest_workflow_run(workflow_file):
    """Most recent successful run's start time (ISO Z) of a workflow in this repository, or None."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        try:
            remote = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True,
                                    text=True, check=True).stdout.strip()
            m = re.search(r"github\.com[:/](.+?/.+?)(?:\.git)?$", remote)
            repo = m.group(1) if m else None
        except (OSError, subprocess.CalledProcessError):
            repo = None
    if not repo:
        return None
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            token = None
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs",
                         params={"status": "success", "per_page": 1}, headers=headers, timeout=30)
        runs = r.json().get("workflow_runs", []) if r.ok else []
    except (requests.RequestException, ValueError):
        return None
    return runs[0]["run_started_at"] if runs else None


# ---------------------------------------------------------------- hero visual

HERO_WIDTH, HERO_HEIGHT, HERO_PAD = 900, 1100, 20
HERO_MAX_DASHES = 4500
HERO_LABEL = ("Storm overflows in England drawn as dashes; highlighted dashes are dry day spills in the last 30 days")
FAINT, FLAG = "#4a4a4f", "#d9b26a"  # --faint and --flag (01_SPEC.md §7.1); an <img> cannot read CSS variables


def valid_coords(o):
    try:
        lat, lon = float(o["latitude"]), float(o["longitude"])
    except (KeyError, ValueError):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def write_hero(overflows, rows, today, launch_day, path):
    """England as dashes at overflow coordinates (01_SPEC.md §7.5, plan step 1.12). Returns (dashes, flagged)."""
    points = {k: valid_coords(o) for k, o in overflows.items()}
    points = {k: p for k, p in points.items() if p}
    mean_lat = sum(p[0] for p in points.values()) / len(points)
    kx = math.cos(math.radians(mean_lat))
    xs = [p[1] * kx for p in points.values()]
    ys = [p[0] for p in points.values()]
    scale = min((HERO_WIDTH - 2 * HERO_PAD) / (max(xs) - min(xs)), (HERO_HEIGHT - 2 * HERO_PAD) / (max(ys) - min(ys)))
    off_x = (HERO_WIDTH - (max(xs) - min(xs)) * scale) / 2
    off_y = (HERO_HEIGHT - (max(ys) - min(ys)) * scale) / 2

    def project(lat, lon):
        return off_x + (lon * kx - min(xs)) * scale, off_y + (max(ys) - lat) * scale

    _, _, start, end = periods(today, launch_day)[0]
    flagged = sorted({r["overflow_key"] for r in rows if r["verdict"] == "dry_day" and in_period(r, start, end)
                      and r["overflow_key"] in points})
    keys = sorted(points)
    step = math.ceil(len(keys) / HERO_MAX_DASHES)
    sample = [k for k in keys[::step] if k not in set(flagged)]
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {HERO_WIDTH} {HERO_HEIGHT}" role="img" '
             f'aria-label="{HERO_LABEL}">', f'<g fill="{FAINT}">']
    for k in sample:
        x, y = project(*points[k])
        lines.append(f'<rect x="{x - 1.5:.1f}" y="{y - 0.5:.1f}" width="3" height="1"/>')
    lines += ["</g>", f'<g fill="{FLAG}">']
    for k in flagged:
        x, y = project(*points[k])
        lines.append(f'<rect x="{x - 2.5:.1f}" y="{y - 0.5:.1f}" width="5" height="1"/>')
    lines += ["</g>", "</svg>"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(sample), len(flagged)


# ---------------------------------------------------------------- build

def build(out_dir, hero_only=False):
    data = ROOT / "data"
    meta = read_json(data / "meta.json")
    overflows = {r["overflow_key"]: r for r in read_csv(data / "overflows.csv")}
    rows = read_csv(data / "classification" / "all_events_classified.csv")
    events = {r["event_id"]: r for p in sorted((data / "events").glob("*.csv")) for r in read_csv(p)}
    history = data / "thames_history" / "events_pre_launch.csv"   # phase 3: Thames' own record before launch
    if history.exists():
        events.update({r["event_id"]: r for r in read_csv(history)})
    gauges = read_csv(data / "rain" / "gauges.csv")
    gauge_by_id = {g["gauge_id"]: g for g in gauges}
    rain = {}
    for p in sorted((data / "rain" / "daily").glob("*.csv")):
        for r in read_csv(p):
            rain[(r["gauge_id"], r["date"])] = r

    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = now.date()
    launch_utc = meta["launch_utc"]
    launch_day = date.fromisoformat(launch_utc[:10])
    site_url = meta["site_url"]

    hero = write_hero(overflows, rows, today, launch_day, ROOT / "static" / "england-overflows.svg")
    print(f"hero: {hero[0]} dashes, {hero[1]} flagged (dry day spills in the last 30 days)")
    if hero_only:
        return 0

    for r in rows:
        r["overflow"] = overflows.get(r["overflow_key"], {})
        r["company_name"] = COMPANY_NAMES.get(r["company_slug"], r["company_slug"])
        r["duration_s"] = duration_seconds(r)
        r["duration_text"] = fmt_duration(r["duration_s"])
        r["watercourse"] = r["overflow"].get("receiving_watercourse", "").strip()
        r["radar_label"] = radar_label(r)

    page_rows = [r for r in rows if r["verdict"] in PAGE_EVENT_VERDICTS]
    slugs = slug_map([r["event_id"] for r in page_rows])
    for r in page_rows:
        r["slug"] = slugs[r["event_id"]]

    # footer times
    last_poll = latest_workflow_run("poll.yml")
    discharge_changed = max([v for o in overflows.values() for v in (o["first_seen_utc"], o["last_seen_utc"])]
                            + [v for e in events.values() for v in (e["first_observed_utc"], e["last_observed_utc"])])
    rain_changed = max((r["fetched_utc"] for r in rain.values()), default="")
    classified = max((r["classified_utc"] for r in rows), default="")
    footer = {
        "poll_label": "Last poll" if last_poll else "Discharge data last changed",
        "poll": fmt_datetime(last_poll or discharge_changed),
        "rain": fmt_datetime(rain_changed), "classified": fmt_datetime(classified),
    }

    # counts
    period_list = periods(today, launch_day)
    overflow_counts = Counter(o["company_slug"] for o in overflows.values())
    dry_rows = sorted([r for r in rows if r["verdict"] == "dry_day"], key=lambda r: (r["start_utc"], r["event_id"]),
                      reverse=True)
    last_dry = {}
    for r in dry_rows:
        last_dry.setdefault(r["company_slug"], r["day_utc"])

    league = {}
    tiles = {}
    for key, label, start, end in period_list:
        in_p = [r for r in rows if in_period(r, start, end)]
        ev_c = Counter(r["company_slug"] for r in in_p)
        dry_c = Counter(r["company_slug"] for r in in_p if r["verdict"] == "dry_day")
        checked_c = Counter(r["company_slug"] for r in in_p if r["radar_label"])
        agree_c = Counter(r["company_slug"] for r in in_p if r["radar_label"] == "radar_agrees")
        league[key] = {
            "key": key, "label": label, "start": start, "end": end,
            "rows": [{"slug": slug, "name": name, "overflows": overflow_counts[slug], "events": ev_c[slug],
                      "dry": dry_c[slug], "per100": per_100(dry_c[slug], overflow_counts[slug]),
                      "last_dry": last_dry.get(slug, ""), "last_dry_text": fmt_date(last_dry.get(slug, "")),
                      "radar_agrees": agree_c[slug], "radar_checked": checked_c[slug],
                      "radar_share": f"{agree_c[slug] * 100 / checked_c[slug]:.0f}" if checked_c[slug] else ""}
                     for slug, name in COMPANIES],
        }
        tiles[key] = {"dry": sum(dry_c.values()), "events": len(in_p)}

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True, undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters.update(dt=fmt_datetime, dts=fmt_datetime_seconds, d=fmt_date, thin=thin)
    frames = radar_frames(data)
    common = {"radar_frames": frames, "has_radar": bool(frames), "footer": footer, "site_url": site_url, "build_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "launch_utc": launch_utc, "launch_date": fmt_date(launch_day), "rule_version": meta["rule_version"],
              "ea_rule": EA_RULE, "n_overflows": len(overflows), "hero_svg": (ROOT / "static" /
                                                                               "england-overflows.svg").exists()}

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    shutil.copytree(ROOT / "static", out_dir / "static", ignore=shutil.ignore_patterns(".gitkeep"))

    def render(template, path, **ctx):
        depth = path.count("/")
        html = env.get_template(template).render(root="../" * depth, path=path, **common, **ctx)
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    def pages(items, per_page, base):
        """[(path, items, page_no, n_pages)] with base.html, base-2.html, ..."""
        chunks = [items[i:i + per_page] for i in range(0, len(items), per_page)] or [[]]
        stem = base[:-len(".html")]
        return [(base if i == 0 else f"{stem}-{i + 1}.html", chunk, i + 1, len(chunks))
                for i, chunk in enumerate(chunks)]

    def page_name(base, n):
        stem = base.rsplit("/", 1)[-1][:-len(".html")]
        return f"{stem}.html" if n == 1 else f"{stem}-{n}.html"

    render("index.html", "index.html", active="overview", tiles=tiles, league=league,
           latest=dry_rows[:LATEST_SPILLS], periods=period_list)
    render("companies_index.html", "companies/index.html", active="companies", league=league, periods=period_list)

    # company pages
    months = []
    m = date(launch_day.year, launch_day.month, 1)
    while m <= today:
        months.append(m)
        m = date(m.year + (m.month // 12), m.month % 12 + 1, 1)
    csv_dir = out_dir / "data" / "classification" / "companies"
    csv_dir.mkdir(parents=True, exist_ok=True)
    all_classified = (data / "classification" / "all_events_classified.csv").read_text(encoding="utf-8").splitlines(True)
    for slug, name in COMPANIES:
        company_rows = [r for r in rows if r["company_slug"] == slug]
        monthly = []
        for m in reversed(months):
            start = max(m, launch_day)
            end = date(m.year + (m.month // 12), m.month % 12 + 1, 1) - timedelta(days=1)
            in_m = [r for r in company_rows if in_period(r, start, end)]
            dry = sum(1 for r in in_m if r["verdict"] == "dry_day")
            complete = sum(1 for r in in_m if r["verdict"] in ("dry_day", "not_dry") and r["n_readings_present"] == "192")
            label = f"{MONTHS[m.month - 1]} {m.year}" + (f" (partial, from {fmt_date(launch_day)})" if start > m else "")
            monthly.append({"label": label, "events": len(in_m), "dry": dry,
                            "per100": per_100(dry, overflow_counts[slug]),
                            "complete_share": f"{complete * 100 / len(in_m):.0f}" if in_m else ""})
        company_dry = [r for r in dry_rows if r["company_slug"] == slug]
        header, body = all_classified[0], [line for line in all_classified[1:] if line.split(",")[2] == slug]
        (csv_dir / f"{slug}.csv").write_text(header + "".join(body), encoding="utf-8")
        for path, chunk, n, total in pages(company_dry, COMPANY_SPILLS_PER_PAGE, f"companies/{slug}.html"):
            render("company.html", path, active="companies", slug=slug, name=name, overflows=overflow_counts[slug],
                   monthly=monthly, spills=chunk, page_no=n, n_pages=total, n_spills=len(company_dry),
                   page_name=lambda k, s=slug: page_name(f"companies/{s}.html", k))

    # events index
    listed = sorted(page_rows, key=lambda r: (r["start_utc"], r["event_id"]), reverse=True)
    for path, chunk, n, total in pages(listed, EVENTS_PER_PAGE, "events/index.html"):
        render("events_index.html", path, active="events", events=chunk, page_no=n, n_pages=total,
               n_dry=sum(1 for r in listed if r["verdict"] == "dry_day"),
               n_pending=sum(1 for r in listed if r["verdict"] == "pending_rain_data"),
               page_name=lambda k: page_name("events/index.html", k))

    # event pages
    for r in page_rows:
        prev_day = (date.fromisoformat(r["day_utc"]) - timedelta(days=1)).isoformat()
        gauge = gauge_by_id.get(r["gauge_id"])
        quality = None
        if gauge:
            days = [rain.get((gauge["gauge_id"], d)) for d in (prev_day, r["day_utc"])]
            quality = {k: sum(int(x[k]) for x in days if x) for k in ("n_unchecked", "n_good", "n_other_quality")}
        o = r["overflow"]
        nearest = []
        if not gauge and o.get("latitude") and o.get("longitude"):
            nearest = nearest_gauges(float(o["latitude"]), float(o["longitude"]), gauges)[:3]
        reproduce = [(g["label"], f"{g['distance_km']:.2f}", f"{HYDROLOGY}/measures/{g['measure_id']}/readings"
                      f"?mineq-date={prev_day}&max-date={r['window_end_utc'][:10]}") for g in nearest]
        if gauge:
            reproduce = [(gauge["label"], r["gauge_distance_km"], f"{HYDROLOGY}/measures/{gauge['measure_id']}/readings"
                          f"?mineq-date={prev_day}&max-date={r['window_end_utc'][:10]}")]
        render("event.html", f"events/{r['slug']}.html", active="events", ev=r, o=o, quality=quality,
               reproduce=reproduce, prev_day=prev_day, event_detail=events.get(r["event_id"], {}))

    render("method.html", "method.html", active="method",
           n_no_coords=sum(1 for o in overflows.values() if not o["latitude"] or not o["longitude"]),
           n_st_connect=overflow_counts["st-connect"], radar_cover=radar_coverage(frames))
    data_files = sorted(p.relative_to(data).as_posix() for p in (data / "classification").glob("*.csv"))
    data_files += sorted(p.relative_to(data).as_posix() for p in (data / "events").glob("*.csv"))
    data_files += ["overflows.csv", "rain/gauges.csv"]
    for rel in data_files:
        (out_dir / "data" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(data / rel, out_dir / "data" / rel)
    render("data.html", "data.html", active="data", data_files=data_files,
           company_csvs=[(slug, name) for slug, name in COMPANIES])
    render("about.html", "about.html", active="about")
    return len(page_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--hero-only", action="store_true", help="only regenerate static/england-overflows.svg")
    args = ap.parse_args()
    try:
        n = build(Path(args.out), hero_only=args.hero_only)
        if args.hero_only:
            return 0
    except ValueError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    print(f"built {args.out} with {n} event pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
