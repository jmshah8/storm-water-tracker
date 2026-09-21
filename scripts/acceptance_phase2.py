#!/usr/bin/env python3
"""Phase 2 acceptance (05_CHECKS_AND_ACCEPTANCE.md, items R1-R10): one row per item, printed as a table.

Radar is a second opinion only. R7 is the item that proves it: the classifier is run twice on a frozen
copy of data/, once with the radar daily files present and once with them removed, and the verdict of
every event is compared. The helpers come from scripts/check.py so the numbers are computed the same way.

Exit codes: 0 every item passed, 1 an item failed, 2 network error.
"""
import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check import NetworkError, get_json, read_csv, read_json_file, site_checks, step_2_3  # noqa: E402,F401
from swt.io import read_csv as _read_csv  # noqa: E402,F401  (same helper; check.py re-exports it)

import radar as radar_cli  # noqa: E402  (scripts/radar.py: the bucket listing)

CITIES = {"London": (51.5074, -0.1278), "Manchester": (53.4808, -2.2426), "Newcastle": (54.9783, -1.6178),
          "Plymouth": (50.3755, -4.1427), "Norwich": (52.6309, 1.2974)}
FRAMES_COMPLETE = 92          # 03_PHASE2_RADAR_PLAN.md step 2.4: a day is "complete" at >= 92 of 96 frames
# Upstream gaps: the Met Office bucket itself holds zero keys for these UTC days. Verified live by R4 below;
# they are listed as gaps, never silently excused.
KNOWN_UPSTREAM_GAPS = ("2024-12-13", "2024-12-14")


def newest_grid():
    """The most recent .npz written by `radar.py day --save-grid` (git-ignored, under .cache/)."""
    saved = sorted((ROOT / ".cache").glob("radar_*.npz"))
    return saved[-1] if saved else None


def bucket_keys(day):
    """Every radar key the Met Office bucket holds for one UTC day."""
    try:
        return radar_cli.list_day(day)
    except (requests.RequestException, OSError) as e:
        raise NetworkError(f"bucket listing for {day}: {e}")


def radar_day_frames():
    """{date string: n_frames} from data/radar/daily; n_frames is the same on every row of a file."""
    import csv
    import gzip

    out = {}
    for path in sorted((ROOT / "data" / "radar" / "daily").glob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            row = next(csv.DictReader(f), None)
        out[path.name[: -len(".csv.gz")]] = int(row["n_frames"]) if row else 0
    return out


def archive_coverage(now=None):
    """Radar archive coverage (03_PHASE2_RADAR_PLAN.md CHECK 2.6, and acceptance item R4).

    Every missing day is looked up in the Met Office bucket before it is judged: a day the bucket itself
    holds no keys for is an upstream gap and is reported, not excused; anything else is a real gap and fails.
    """
    now = now or datetime.now(timezone.utc)
    frames = radar_day_frames()
    oldest = date.fromisoformat(min(frames)) if frames else None
    yesterday = now.date() - timedelta(days=1)
    expected_days, day = [], oldest
    while day and day <= yesterday:
        expected_days.append(day.isoformat())
        day += timedelta(days=1)
    missing = [d for d in expected_days if d not in frames]
    upstream, real_gaps = [], []
    for d in missing:
        keys = bucket_keys(date.fromisoformat(d))
        (upstream if not keys else real_gaps).append(f"{d} ({len(keys)} keys upstream)")
    before_oldest = bucket_keys(oldest - timedelta(days=1)) if oldest else []
    partial = sorted((d, n) for d, n in frames.items() if n < FRAMES_COMPLETE)
    observed = (f"now {now:%Y-%m-%dT%H:%M:%SZ} (radar.yml samples the previous day at 07:30 UTC); "
                f"{oldest} to {yesterday}: {len(expected_days)} UTC days, {len(frames)} daily files; "
                f"missing {len(missing)}; upstream gaps (bucket holds zero keys) {upstream or 'none'}; "
                f"unexplained gaps {real_gaps or 'none'}; the day before the oldest "
                f"({oldest - timedelta(days=1)}) holds {len(before_oldest)} keys upstream; "
                f"days with < {FRAMES_COMPLETE} frames: {len(partial)} {partial[:6]}")
    return observed, ("PASS" if not real_gaps else "FAIL")


def frozen_inputs(work):
    """A frozen snapshot of the classifier's inputs: hard links, so nothing is duplicated and nothing moves.

    The writers in this project replace a file wholesale, so a hard link keeps the bytes this run started
    with. data/classification is copied properly instead, because classify.py writes into it.
    """
    frozen = work / "frozen"
    frozen.mkdir(parents=True)
    data = ROOT / "data"
    os.link(data / "overflows.csv", frozen / "overflows.csv")
    for name in ("events", "rain", "thames_history"):
        if (data / name).exists():
            shutil.copytree(data / name, frozen / name, copy_function=os.link)
    (frozen / "radar").mkdir()
    shutil.copytree(data / "radar" / "daily", frozen / "radar" / "daily", copy_function=os.link)
    return frozen


def classify_run(work, frozen, name, with_radar):
    """Run classify.py --force against the frozen inputs; returns (verdicts, tail of its output)."""
    run_dir = work / name
    run_dir.mkdir()
    for child in frozen.iterdir():
        if child.name == "radar":
            continue
        (run_dir / child.name).symlink_to(child)
    if with_radar:
        (run_dir / "radar").mkdir()
        (run_dir / "radar" / "daily").symlink_to(frozen / "radar" / "daily")
    shutil.copytree(ROOT / "data" / "classification", run_dir / "classification")
    proc = subprocess.run([sys.executable, "scripts/classify.py", "--data", str(run_dir), "--force"],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"classify.py failed in {name}: {proc.stderr.strip()[:300]}")
    verdicts = {r["event_id"]: r["verdict"]
                for r in read_csv(run_dir / "classification" / "all_events_classified.csv")}
    return verdicts, (proc.stdout.strip().splitlines() or [""])[-1]


def acceptance_phase2(args):
    """05_CHECKS_AND_ACCEPTANCE.md Phase 2: R1-R10."""
    results = []

    def add(item, expected, observed, status):
        results.append((item, expected, observed, status))
        print(f"  {item:4} {status:6} {observed}")

    def run(cmd, **kw):
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), **kw)

    now = datetime.now(timezone.utc)
    rows = read_csv(ROOT / "data" / "classification" / "all_events_classified.csv")

    print("Radar reader")
    r = run([sys.executable, "-m", "pytest", "-q", "tests/test_radar.py"])
    tests_pass = r.returncode == 0
    add("R1", "pass", (r.stdout.strip().splitlines() or [r.stderr[-200:]])[-1],
        "PASS" if tests_pass else "FAIL")

    grid_path = Path(args.grid) if args.grid else newest_grid()
    grid, grid_source = None, None
    if grid_path and grid_path.exists():
        import ast

        import numpy as np

        from swt.radar import Grid
        saved = np.load(grid_path, allow_pickle=False)
        grid = Grid(ast.literal_eval(str(saved["where"])), str(saved["origin"]))
        grid_source = f"grid from {grid_path.relative_to(ROOT)}"
    else:
        from swt.radar import Grid, load_frame
        day = (now - timedelta(days=2)).date()
        keys = bucket_keys(day)
        if not keys:
            raise NetworkError(f"no radar keys in the bucket for {day}")
        tmp = Path(tempfile.mkdtemp(prefix="swt-frame-"))
        try:
            frame = radar_cli.download(keys[len(keys) // 2], tmp / "frame.h5")
            _, meta = load_frame(frame)
            grid = Grid(meta["where"], meta["origin"])
            grid_source = f"grid from a live frame, {keys[len(keys) // 2]}"
        except OSError as e:
            raise NetworkError(str(e))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    pixels = {name: grid.to_pixel(lat, lon) for name, (lat, lon) in CITIES.items()}
    in_bounds = [name for name, (row, col) in pixels.items() if not grid.in_bounds(row, col)]
    by_lat = sorted(CITIES, key=lambda n: -CITIES[n][0])      # north first: rows must not decrease
    by_lon = sorted(CITIES, key=lambda n: CITIES[n][1])       # west first: columns must not decrease
    rows_ordered = [pixels[n][0] for n in by_lat] == sorted(pixels[n][0] for n in by_lat)
    cols_ordered = [pixels[n][1] for n in by_lon] == sorted(pixels[n][1] for n in by_lon)
    shown = ", ".join(f"{n} r{pixels[n][0]} c{pixels[n][1]}" for n in by_lat)
    geo_ok = not in_bounds and rows_ordered and cols_ordered
    add("R2", "5 cities in bounds and ordered correctly",
        f"{grid_source}; {shown}; out of bounds: {in_bounds or 'none'}; "
        f"north->south rows ordered: {rows_ordered}; west->east columns ordered: {cols_ordered}",
        "PASS" if geo_ok else "FAIL")

    print("Radar against the gauges")
    if grid_path and grid_path.exists():
        buffer = StringIO()
        import contextlib
        with contextlib.redirect_stdout(buffer):
            code = step_2_3(argparse.Namespace(grid=str(grid_path)))
        text = buffer.getvalue()
        correlation = re.search(r"rank correlation across (\d+) points: (-?[\d.]+)", text)
        median = re.search(r"median radar total at the (\d+) zero-rain gauges: ([\d.]+) mm", text)
        add("R3", "> 0.6", f"day {grid_path.stem.replace('radar_', '')}: "
            f"rank correlation {correlation.group(2) if correlation else '?'} over "
            f"{correlation.group(1) if correlation else '?'} points; median radar total at the "
            f"{median.group(1) if median else '?'} zero-rain gauges {median.group(2) if median else '?'} mm",
            "PASS" if code == 0 else "FAIL")
    else:
        add("R3", "> 0.6", "no saved radar grid (.cache/radar_*.npz) to sample; run "
            "scripts/radar.py day DATE --save-grid first", "FAIL")

    print("Archive coverage")
    observed, status = archive_coverage(now)
    add("R4", "0 missing (gaps listed if any)", observed, status)

    print("Site")
    site = site_checks()
    trees = site["trees"]
    site_dir = site["site"]
    wanted = [r for r in rows if r["verdict"] == "dry_day" and r["radar_status"] == "complete"]
    missing_pages, empty_pages = [], []
    for row in wanted:
        path = site_dir / "events" / f"{re.sub(r'[^A-Za-z0-9_-]', '_', row['event_id'])}.html"
        tree = trees.get(path)
        if tree is None:
            missing_pages.append(row["event_id"])
            continue
        block = {el.get("data-metric"): el.get("data-value") for el in tree.iter()
                 if (el.get("data-metric") or "").startswith("radar-")}
        if block.get("radar-window-total") in (None, "") or block.get("radar-3x3-max") in (None, "") \
                or not block.get("radar-label"):
            empty_pages.append((row["event_id"], block))
        elif block["radar-window-total"] != row["radar_window_total_mm"] \
                or block["radar-3x3-max"] != row["radar_3x3_max_total_mm"]:
            empty_pages.append((row["event_id"], block))
    add("R5", "yes", f"dry_day events with radar_status=complete: {len(wanted)}; pages missing: "
        f"{len(missing_pages)} {missing_pages[:3]}; pages without the radar block or with numbers that do not "
        f"match the CSV: {len(empty_pages)} {[e[0] for e in empty_pages[:3]]}",
        "PASS" if not missing_pages and not empty_pages else "FAIL")

    radar_cells = sum(1 for tree in trees.values() for el in tree.iter()
                      if el.get("data-metric") == "radar_agrees")
    radar_mismatches = [m for m in site["mismatches"] if str(m[0]).endswith("radar_agrees")]
    other_mismatches = [m for m in site["mismatches"] if not str(m[0]).endswith("radar_agrees")]
    add("R6", "exact", f"\"Radar agrees\" cells on the pages: {radar_cells}; recomputed from the CSV by "
        f"site_checks across {site['league_cells']} league cells; radar_agrees mismatches: "
        f"{len(radar_mismatches)} {radar_mismatches[:3]}; other (non-radar) mismatches in the same run: "
        f"{len(other_mismatches)}", "PASS" if not radar_mismatches else "FAIL")

    print("Radar never changes a verdict")
    work = Path(args.work) / f"acceptance_phase2_{now:%Y%m%dT%H%M%SZ}" if args.work \
        else Path(tempfile.mkdtemp(prefix="swt-acceptance-phase2-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        frozen = frozen_inputs(work)
        with_radar, summary_a = classify_run(work, frozen, "with_radar", True)
        without_radar, summary_b = classify_run(work, frozen, "without_radar", False)
        print(f"    with radar:    {summary_a}")
        print(f"    without radar: {summary_b}")
        only_a = set(with_radar) - set(without_radar)
        only_b = set(without_radar) - set(with_radar)
        differing = sorted(k for k in with_radar if k in without_radar and with_radar[k] != without_radar[k])
        add("R7", "0 differences", f"{len(with_radar)} events classified twice on a frozen copy of data/; "
            f"event ids only in one run: {len(only_a)}/{len(only_b)}; verdicts differing: {len(differing)} "
            f"{differing[:3]}", "PASS" if not differing and not only_a and not only_b else "FAIL")
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)

    print("Licensing and automation")
    data_text = (site_dir / "data.html").read_text(encoding="utf-8")
    share_alike = "licensed under CC BY-SA. Share-alike applies to these columns" in data_text
    footer_line = "Contains Met Office radar data © British Crown copyright, CC BY-SA."
    no_footer = [path.relative_to(site_dir).as_posix() for path in trees
                 if footer_line not in path.read_text(encoding="utf-8")]
    add("R8", "present", f"Data page states share-alike for the radar columns: {share_alike}; pages of "
        f"{len(trees)} without the Met Office footer attribution: {len(no_footer)} {no_footer[:3]}",
        "PASS" if share_alike and not no_footer else "FAIL")

    import json
    since = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    gh = run(["gh", "run", "list", "--workflow", "radar", "--limit", "300", "--json",
              "status,conclusion,createdAt"])
    if gh.returncode != 0:
        raise NetworkError(f"gh run list failed: {gh.stderr.strip()[:200]}")
    runs = [x for x in json.loads(gh.stdout or "[]") if x["createdAt"] >= since]
    done = [x for x in runs if x["status"] == "completed" and x["conclusion"] != "cancelled"]
    success = [x for x in done if x["conclusion"] == "success"]
    pct = len(success) / len(done) * 100 if done else 0
    cancelled = [x for x in runs if x["conclusion"] == "cancelled"]
    add("R9", ">= 90%", f"{len(success)} of {len(done)} non-cancelled radar runs in 7 days succeeded "
        f"({pct:.1f}%); {len(cancelled)} cancelled by the concurrency rule (01_SPEC.md §9.4, not failures); "
        f"{len(runs) - len(done) - len(cancelled)} still running",
        "PASS" if done and pct >= 90 else "FAIL")

    source = (ROOT / "swt" / "radar.py").read_text(encoding="utf-8")
    transformer = re.search(r"pyproj\.Transformer\.from_crs\(([^)]*)\)", source)
    always_xy = bool(transformer) and "always_xy=True" in transformer.group(1)
    add("R10", "yes", f"Transformer.from_crs({transformer.group(1) if transformer else 'not found'}) — "
        f"always_xy=True present: {always_xy}; tests/test_radar.py: "
        f"{'pass' if tests_pass else 'FAIL'}; five-city check (R2): {'pass' if geo_ok else 'FAIL'}",
        "PASS" if always_xy and tests_pass and geo_ok else "FAIL")

    print("\n| item | expected | observed | result |")
    print("|---|---|---|---|")
    for item, expected, observed, status in results:
        print(f"| {item} | {expected} | {observed} | {status} |")
    counts = collections.Counter(r[3] for r in results)
    print(f"\n{dict(counts)}")
    return 0 if not counts["FAIL"] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", help="the .npz written by scripts/radar.py day --save-grid "
                                   "(default: the newest .cache/radar_*.npz)")
    ap.add_argument("--work", help="directory for R7's frozen copy of data/ (default: a system temp directory)")
    ap.add_argument("--keep", action="store_true", help="keep R7's working directory for inspection")
    args = ap.parse_args()
    try:
        return acceptance_phase2(args)
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
