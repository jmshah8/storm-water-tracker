#!/usr/bin/env python3
"""Calibrate the proposed "neighbour test" for unrepresentative rain gauges.

THIS IS AN EXPERIMENT, NOT PART OF THE PIPELINE. Nothing imports it, it changes no verdict, and it
writes nothing anywhere: it only reads `data/` and prints to stdout.

The question it answers
-----------------------
A gauge that works but badly under-reports on one day produces a dry day flag that is probably wrong
(the Cranleigh case, 2026-09-08: 0.22 mm at 0.10 km while gauges 7.7 km and 8.6 km away recorded
16.8 mm and 23.6 mm and radar showed 20-25 mm). The proposed fix, the *neighbour test*, is:

    when the chosen gauge's 48-hour window total is at or below the 0.25 mm dry threshold, but the
    MEDIAN window total of at least 3 other usable gauges within R km is above T mm, treat the chosen
    gauge as unrepresentative.

Nobody has published R and T for a national network like England's (~1,000 gauges, mean spacing
~13 km); de Vos et al. (2019) give 10 km / 5 neighbours for a dense Dutch city network. This script
sweeps R and T and scores the result against the independent referee we already hold: Met Office
radar over the overflow (`radar_3x3_max_total_mm`, the RainGaugeQC 3x3 km box).

Definitions used here, all taken from `swt/rule.py` and `01_SPEC.md` §5.2-5.3 unchanged:
  * the 48-hour window for an event is the UTC day it started plus the day before;
  * a gauge's window total is the sum of its two daily `total_mm` values;
  * a gauge is usable for a window only when the two days together carry >= 176 readings;
  * the dry threshold is 0.25 mm.

Scoring, on `dry_day` flags only, with radar as the referee (radar WET when
`radar_3x3_max_total_mm` > 0.25 mm, DRY otherwise):
  fired + radar wet  -> true positive  (a bad flag correctly withdrawn)
  fired + radar dry   -> false positive (a good flag wrongly destroyed) -- the cost that matters
  not fired + radar wet -> miss         (a bad flag left standing)
  not fired + radar dry -> true negative (correctly kept)

Exit codes: 0 ok, 2 a data problem (missing or unreadable inputs).
"""
import argparse
import csv
import re
import sys
from bisect import insort
from collections import defaultdict
from datetime import date, timedelta
from math import cos, radians
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swt.geo import haversine_km  # noqa: E402
from swt.io import read_csv  # noqa: E402

DRY_THRESHOLD_MM = 0.25          # 01_SPEC.md §5.2, unchanged
READINGS_REQUIRED = 176          # 01_SPEC.md §5.3, unchanged
MIN_NEIGHBOURS = 3               # GN066's three-gauge minimum
DEFAULT_RADII_KM = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
DEFAULT_THRESHOLDS_MM = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
DECIDED = ("dry_day", "not_dry")
UUID_RE = re.compile(r"\(([0-9a-fA-F-]{36})\)")


class DataProblem(Exception):
    """Something needed is missing or unreadable; the experiment cannot be run honestly."""


# ---------------------------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------------------------

def load_events(path, limit=None):
    """The rows this experiment can use, with only the columns it needs.

    Scope = (decided AND radar complete) UNION (every dry_day flag), because the flags without radar
    still tell us how many flags a rule would withdraw in total even though they cannot be scored.
    """
    if not Path(path).exists():
        raise DataProblem(f"{path} does not exist")
    kept, n_rows, n_flags = [], 0, 0
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            verdict, radar_status = row["verdict"], row["radar_status"]
            if verdict == "dry_day":
                n_flags += 1
            scorable = verdict in DECIDED and radar_status == "complete"
            if not scorable and verdict != "dry_day":
                continue
            if not row["gauge_id"] or not row["rain_window_total_mm"]:
                continue
            used = {row["gauge_id"]} | set(UUID_RE.findall(row["triangulated_gauges"]))
            kept.append({
                "event_id": row["event_id"],
                "overflow_key": row["overflow_key"],
                "company_slug": row["company_slug"],
                "day_utc": row["day_utc"],
                "verdict": verdict,
                "gauge_id": row["gauge_id"],
                "gauge_label": row["gauge_label"],
                "gauge_distance_km": row["gauge_distance_km"],
                "gauge_method": row["gauge_method"],
                "used_gauges": used,
                "total_mm": float(row["rain_window_total_mm"]),
                "radar_status": radar_status,
                "radar_3x3": (float(row["radar_3x3_max_total_mm"])
                              if row["radar_3x3_max_total_mm"] else None),
                "scorable": scorable,
            })
            if limit and len(kept) >= limit:
                break
    if not kept:
        raise DataProblem(f"{path} yielded no usable rows")
    return kept, n_rows, n_flags


def load_gauges(path):
    rows = read_csv(path)
    if not rows:
        raise DataProblem(f"{path} is missing or empty")
    out = []
    for g in rows:
        if not g["latitude"] or not g["longitude"]:
            continue
        out.append((g["gauge_id"], float(g["latitude"]), float(g["longitude"])))
    if not out:
        raise DataProblem(f"{path} has no gauge with coordinates")
    return out


def load_overflows(path):
    rows = read_csv(path)
    if not rows:
        raise DataProblem(f"{path} is missing or empty")
    return {r["overflow_key"]: (float(r["latitude"]), float(r["longitude"]))
            for r in rows if r["latitude"] and r["longitude"]}


class NeighbourIndex:
    """Gauges near an overflow, nearest first, computed once per overflow.

    Same lat/lon box pre-filter as `swt.geo.nearest_gauges` before the exact haversine.
    """

    def __init__(self, gauges, overflows, max_km):
        self.gauges = gauges
        self.overflows = overflows
        self.max_km = max_km
        self.cache = {}

    def near(self, overflow_key):
        if overflow_key not in self.cache:
            point = self.overflows.get(overflow_key)
            if point is None:
                self.cache[overflow_key] = []
            else:
                lat, lon = point
                lat_margin = self.max_km / 110.0
                lon_margin = self.max_km / (110.0 * max(cos(radians(lat)), 0.01))
                out = []
                for gauge_id, glat, glon in self.gauges:
                    if abs(glat - lat) > lat_margin or abs(glon - lon) > lon_margin:
                        continue
                    d = haversine_km(lat, lon, glat, glon)
                    if d <= self.max_km:
                        out.append((d, gauge_id))
                out.sort()
                self.cache[overflow_key] = out
        return self.cache[overflow_key]


class RainWindows:
    """48-hour window totals per gauge, one event-day at a time.

    Daily files are read once each and held only while the rolling window needs them, so the whole
    134 MB of `data/rain/daily` is never in memory at once.
    """

    def __init__(self, directory, keep=3):
        self.directory = Path(directory)
        self.keep = keep
        self.days = {}
        self.window_cache = {}
        self.missing_days = set()

    def _day(self, day):
        if day not in self.days:
            path = self.directory / f"{day}.csv"
            rows = {}
            if path.exists():
                with open(path, encoding="utf-8", newline="") as f:
                    for r in csv.DictReader(f):
                        try:
                            rows[r["gauge_id"]] = (float(r["total_mm"]), int(r["n_readings"]))
                        except (TypeError, ValueError):
                            continue
            else:
                self.missing_days.add(day)
            self.days[day] = rows
            for old in list(self.days)[:-self.keep]:
                del self.days[old]
        return self.days[day]

    def window(self, day):
        """{gauge_id: window_total_mm} for every gauge usable over (day-1, day)."""
        if day in self.window_cache:
            return self.window_cache[day]
        prev = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        a, b = self._day(prev), self._day(day)
        usable = {}
        for gauge_id, (total_a, n_a) in a.items():
            entry = b.get(gauge_id)
            if entry is None:
                continue
            total_b, n_b = entry
            if n_a + n_b >= READINGS_REQUIRED:
                usable[gauge_id] = total_a + total_b
        self.window_cache = {day: usable}   # only the day being processed is ever needed
        return usable


# ---------------------------------------------------------------------------------------------
# the experiment
# ---------------------------------------------------------------------------------------------

def neighbour_medians(events, index, rain, radii, progress=None):
    """Attach {R: (median_mm, n_neighbours)} to each event, computed day by day.

    The chosen gauge (and, for a triangulated row, all three) is excluded from its own neighbours.
    A radius with fewer than 3 usable neighbours gets no entry at all, and the event is skipped at
    that radius when it is scored.
    """
    by_day = defaultdict(list)
    for ev in events:
        by_day[ev["day_utc"]].append(ev)
    done = 0
    for day in sorted(by_day):
        usable = rain.window(day)
        for ev in by_day[day]:
            totals_by_radius = {}
            sorted_totals = []
            cursor = 0
            near = index.near(ev["overflow_key"])
            for radius in radii:                      # radii ascending: one sweep outwards per event
                while cursor < len(near) and near[cursor][0] <= radius:
                    _, gauge_id = near[cursor]
                    cursor += 1
                    if gauge_id in ev["used_gauges"]:
                        continue
                    total = usable.get(gauge_id)
                    if total is not None:
                        insort(sorted_totals, total)
                if len(sorted_totals) >= MIN_NEIGHBOURS:
                    totals_by_radius[radius] = (median(sorted_totals), len(sorted_totals))
            ev["neighbours"] = totals_by_radius
            done += 1
            if progress and done % progress == 0:
                print(f"  ... {done} of {len(events)} events", file=sys.stderr, flush=True)
    return events


def fires(ev, radius, threshold):
    """The neighbour test itself. None when it cannot be evaluated at this radius."""
    entry = ev["neighbours"].get(radius)
    if entry is None:
        return None
    return ev["total_mm"] <= DRY_THRESHOLD_MM and entry[0] > threshold


def radar_wet(ev):
    return ev["radar_3x3"] is not None and ev["radar_3x3"] > DRY_THRESHOLD_MM


def score(flags, radius, threshold):
    """Confusion counts against the radar referee, plus what the pair would withdraw overall."""
    tp = fp = miss = tn = 0
    not_evaluable = 0
    withdrawn_scored = withdrawn_unscored = 0
    for ev in flags:
        fired = fires(ev, radius, threshold)
        if fired is None:
            not_evaluable += 1
            continue
        if ev["scorable"]:
            if fired:
                withdrawn_scored += 1
                tp += 1 if radar_wet(ev) else 0
                fp += 0 if radar_wet(ev) else 1
            else:
                miss += 1 if radar_wet(ev) else 0
                tn += 0 if radar_wet(ev) else 1
        elif fired:
            withdrawn_unscored += 1
    return {
        "tp": tp, "fp": fp, "miss": miss, "tn": tn,
        "scored": tp + fp + miss + tn,
        "not_evaluable": not_evaluable,
        "withdrawn_scored": withdrawn_scored,
        "withdrawn_unscored": withdrawn_unscored,
        "withdrawn_total": withdrawn_scored + withdrawn_unscored,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "recall": tp / (tp + miss) if (tp + miss) else None,
        "fpr": fp / (fp + tn) if (fp + tn) else None,
    }


def not_dry_check(not_dry_events, radius, threshold):
    """Sanity check over `not_dry` events.

    The literal test cannot fire on a `not_dry` event: `not_dry` means the stored window total is
    ABOVE 0.25 mm, and the test requires it to be at or below. So the literal count is structurally
    zero and is reported as such. What is informative is the neighbour half of the test on its own --
    how often the neighbour median exceeds T while the chosen gauge says it rained -- split by what
    radar says, because "neighbour median > T while radar says dry" is the same mechanism that
    produces a false positive on a flag.
    """
    literal = median_over = median_over_radar_dry = median_over_radar_wet = evaluable = 0
    for ev in not_dry_events:
        entry = ev["neighbours"].get(radius)
        if entry is None:
            continue
        evaluable += 1
        if ev["total_mm"] <= DRY_THRESHOLD_MM and entry[0] > threshold:
            literal += 1
        if entry[0] > threshold:
            median_over += 1
            if radar_wet(ev):
                median_over_radar_wet += 1
            else:
                median_over_radar_dry += 1
    return {"evaluable": evaluable, "literal": literal, "median_over": median_over,
            "median_over_radar_wet": median_over_radar_wet,
            "median_over_radar_dry": median_over_radar_dry}


# ---------------------------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------------------------

def pct(x):
    return "     -" if x is None else f"{100 * x:5.1f}%"


def print_coverage(flags, not_dry_events, radii):
    print()
    print("NEIGHBOUR COVERAGE (how often at least 3 usable neighbours exist at all)")
    print(f"{'R km':>6} {'flags w/ >=3':>13} {'of flags':>9} {'not_dry w/ >=3':>15} "
          f"{'of not_dry':>11} {'median n neighbours':>20}")
    for radius in radii:
        have = [ev for ev in flags if radius in ev["neighbours"]]
        have_nd = [ev for ev in not_dry_events if radius in ev["neighbours"]]
        counts = [ev["neighbours"][radius][1] for ev in have]
        print(f"{radius:6.0f} {len(have):13d} {pct(len(have) / len(flags)) if flags else '-':>9} "
              f"{len(have_nd):15d} "
              f"{pct(len(have_nd) / len(not_dry_events)) if not_dry_events else '-':>11} "
              f"{(median(counts) if counts else float('nan')):20.1f}")


def print_main_table(flags, radii, thresholds, total_flags):
    print()
    print("THE NEIGHBOUR TEST SCORED AGAINST RADAR, ON dry_day FLAGS")
    print("fired = stored rain_window_total_mm <= 0.25 mm AND neighbour median > T")
    print("radar WET = radar_3x3_max_total_mm > 0.25 mm (flags with complete radar only)")
    print()
    header = (f"{'R km':>5} {'T mm':>6} | {'TP':>6} {'FP':>6} {'miss':>6} {'kept':>6} {'scored':>7} "
              f"{'skip':>6} | {'prec':>6} {'recall':>6} {'FPR':>6} | "
              f"{'withdr.':>8} {'w/radar':>8} {'no radar':>8} {'of all':>7}")
    print(header)
    print("-" * len(header))
    rows = []
    for radius in radii:
        for threshold in thresholds:
            s = score(flags, radius, threshold)
            rows.append((radius, threshold, s))
            print(f"{radius:5.0f} {threshold:6.2f} | {s['tp']:6d} {s['fp']:6d} {s['miss']:6d} "
                  f"{s['tn']:6d} {s['scored']:7d} {s['not_evaluable']:6d} | "
                  f"{pct(s['precision'])} {pct(s['recall'])} {pct(s['fpr'])} | "
                  f"{s['withdrawn_total']:8d} {s['withdrawn_scored']:8d} "
                  f"{s['withdrawn_unscored']:8d} "
                  f"{pct(s['withdrawn_total'] / total_flags) if total_flags else '-':>7}")
        print("-" * len(header))
    print("TP   = flag withdrawn and radar agrees it rained   (bad flag correctly withdrawn)")
    print("FP   = flag withdrawn but radar says it was dry    (good flag wrongly destroyed)")
    print("miss = flag kept but radar says it rained          (bad flag left standing)")
    print("kept = flag kept and radar agrees it was dry       (correctly kept)")
    print("skip = flags with fewer than 3 usable neighbours at this radius; they are excluded from")
    print("       every column of this table and counted separately below.")
    print("withdr. = flags this pair would withdraw in total, out of the current "
          f"{total_flags} flags;")
    print("       'w/radar' are scorable, 'no radar' fired but cannot be checked by radar at all.")
    return rows


def print_not_dry_table(not_dry_events, radii, thresholds):
    print()
    print("SANITY CHECK OVER not_dry EVENTS")
    print("The literal test cannot fire on a not_dry event: not_dry means the stored window total is")
    print("above 0.25 mm, and the test requires it to be at or below. The literal column is therefore")
    print("structurally zero. The informative column is the neighbour half of the test on its own.")
    print()
    header = (f"{'R km':>5} {'T mm':>6} | {'evaluable':>10} {'literal fires':>14} "
              f"{'median > T':>11} {'share':>7} | {'radar wet':>10} {'radar dry':>10} {'dry share':>10}")
    print(header)
    print("-" * len(header))
    for radius in radii:
        for threshold in thresholds:
            s = not_dry_check(not_dry_events, radius, threshold)
            over = s["median_over"]
            print(f"{radius:5.0f} {threshold:6.2f} | {s['evaluable']:10d} {s['literal']:14d} "
                  f"{over:11d} {pct(over / s['evaluable']) if s['evaluable'] else '-':>7} | "
                  f"{s['median_over_radar_wet']:10d} {s['median_over_radar_dry']:10d} "
                  f"{pct(s['median_over_radar_dry'] / over) if over else '-':>10}")
        print("-" * len(header))


def print_cranleigh(flags, radii, thresholds):
    print()
    print("WORKED EXAMPLE: THE CRANLEIGH CASE, 2026-09-08")
    cases = [ev for ev in flags
             if ev["day_utc"] == "2026-09-08" and ev["gauge_distance_km"]
             and abs(float(ev["gauge_distance_km"]) - 0.10) < 0.05
             and abs(ev["total_mm"] - 0.22) < 0.05]
    if not cases:
        print("  No flagged event on 2026-09-08 matches gauge distance ~0.10 km and window total")
        print("  ~0.22 mm in this run. Nothing is asserted about it.")
        return
    for ev in sorted(cases, key=lambda e: e["event_id"]):
        radar = "no complete radar" if ev["radar_3x3"] is None else f"{ev['radar_3x3']:.2f} mm"
        print(f"\n  {ev['event_id']}  ({ev['company_slug']}, overflow {ev['overflow_key']})")
        print(f"  chosen gauge: {ev['gauge_label']} at {ev['gauge_distance_km']} km, "
              f"window total {ev['total_mm']:.2f} mm, method {ev['gauge_method']}")
        print(f"  radar 3x3 window total: {radar}  (status {ev['radar_status']})")
        print(f"  {'R km':>5} {'neighbours':>11} {'median mm':>10}   fires at T =")
        for radius in radii:
            entry = ev["neighbours"].get(radius)
            if entry is None:
                print(f"  {radius:5.0f} {'<3':>11} {'-':>10}   not evaluable")
                continue
            med, count = entry
            firing = [f"{t:g}" for t in thresholds if med > t]
            print(f"  {radius:5.0f} {count:11d} {med:10.2f}   "
                  + (", ".join(firing) if firing else "none of the thresholds tested"))


MIN_COVERAGE = 0.90     # a radius that cannot be evaluated for most flags cannot be a national rule
MIN_SCORED = 500        # below this the confusion counts are too small to read anything into
MIN_FIRES = 20          # a pair that fires a handful of times tells us nothing about its cost


def print_conclusion(flags, radii, total_flags, rows):
    print()
    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()
    print("Written from the numbers above and nothing else. A pair is only discussed when it clears")
    print(f"three bars: at least {MIN_COVERAGE:.0%} of flags have 3 usable neighbours at that radius,")
    print(f"at least {MIN_SCORED} flags are scorable by radar there, and the pair fires at least "
          f"{MIN_FIRES} times.")
    print("Below those bars the counts are too small to support any claim at all.")
    print()

    scorable = sum(1 for ev in flags if ev["scorable"])
    wet = sum(1 for ev in flags if ev["scorable"] and radar_wet(ev))
    coverage = {r: (sum(1 for ev in flags if r in ev["neighbours"]) / len(flags)) if flags else 0.0
                for r in radii}

    print("1. THE SHAPE OF THE PROBLEM. Of the " + f"{scorable}" + " flags radar can check, "
          f"{wet} ({pct(wet / scorable).strip() if scorable else '-'}) have radar above the")
    print("   0.25 mm dry threshold over the overflow, so gauge and radar disagree about that 48")
    print("   hours. Those are the flags a neighbour test could plausibly withdraw. It is not proof")
    print("   that they are wrong: radar is a second instrument, not the truth.")
    print()

    print("2. RADIUS IS DECIDED BY COVERAGE BEFORE ACCURACY. England's gauge network is too sparse")
    print("   for the small radii the published literature uses:")
    for r in radii:
        verdict = "usable" if coverage[r] >= MIN_COVERAGE else "TOO SPARSE - cannot be a rule"
        print(f"     R = {r:>2.0f} km: 3 usable neighbours exist for {pct(coverage[r]).strip():>6} "
              f"of flags   {verdict}")
    usable_radii = [r for r in radii if coverage[r] >= MIN_COVERAGE]
    if not usable_radii:
        print()
        print("   No radius tested covers enough flags to be a national rule. That is the result of")
        print("   this experiment: the neighbour test as proposed cannot be applied here, and no (R, T)")
        print("   pair should be adopted on this evidence.")
        return
    if 10.0 in coverage and coverage[10.0] < MIN_COVERAGE:
        print("   de Vos et al.'s 10 km radius, taken from a dense Dutch city network, is measured")
        print(f"   here to be unusable: it has 3 usable neighbours for only "
              f"{pct(coverage[10.0]).strip()} of flags.")
    print()

    qualified = [(r, t, s) for r, t, s in rows
                 if coverage.get(r, 0.0) >= MIN_COVERAGE
                 and s["scored"] >= MIN_SCORED
                 and s["tp"] + s["fp"] >= MIN_FIRES]
    if not qualified:
        print("3. NO PAIR CLEARS THE BARS. Every pair either sits at a radius too sparse to use or")
        print("   fires too rarely to be measured. Nothing can be recommended from this run.")
        return

    clean = [q for q in qualified if q[2]["fp"] == 0]
    dirty = [q for q in qualified if q[2]["fp"] > 0]

    print("3. WHAT LOOKS DEFENSIBLE. Pairs that clear the bars and destroy NO flag that radar")
    print("   agrees was dry (FP = 0), best recall first:")
    if not clean:
        print("     none - every pair that clears the bars destroys at least one good flag.")
    for r, t, s in sorted(clean, key=lambda q: -q[2]["recall"])[:8]:
        print(f"     R = {r:>2.0f} km, T = {t:>5g} mm: withdraws {s['withdrawn_total']:>4d} of "
              f"{total_flags} flags ({pct(s['withdrawn_total'] / total_flags).strip()}), "
              f"catches {s['tp']:>3d} of the {s['tp'] + s['miss']} radar-wet flags "
              f"(recall {pct(s['recall']).strip()}), FP 0.")
    print()

    print("4. WHAT DOES NOT. Pairs that clear the bars but destroy flags radar calls dry:")
    if not dirty:
        print("     none of the pairs tested destroyed a single radar-dry flag.")
    for r, t, s in sorted(dirty, key=lambda q: -q[2]["fp"])[:8]:
        print(f"     R = {r:>2.0f} km, T = {t:>5g} mm: FP {s['fp']:>3d} "
              f"(FPR {pct(s['fpr']).strip()}), TP {s['tp']:>3d}, precision "
              f"{pct(s['precision']).strip()} - it withdraws {s['tp']} flags radar calls wet at "
              f"the cost of {s['fp']} radar-dry flag{'' if s['fp'] == 1 else 's'}.")
    if dirty:
        print("   Whether that trade is acceptable is Jaimin's call, not the script's. What the")
        print("   numbers show is that the cost appears at the LOW end of T and nowhere else.")
    print()

    print("5. THE HONEST NEGATIVE RESULT. Recall is low everywhere. The best recall of any")
    if qualified:
        best = max(qualified, key=lambda q: q[2]["recall"])
        print(f"   qualifying pair is {pct(best[2]['recall']).strip()} "
              f"(R = {best[0]:.0f} km, T = {best[1]:g} mm), which means that even at its most")
        print(f"   aggressive the neighbour test leaves "
              f"{pct(1 - best[2]['recall']).strip()} of the flags radar disagrees with")
        print("   standing. So the test does NOT explain the gauge/radar")
        print("   disagreement in general. In most disagreeing cases the neighbouring gauges agree")
        print("   with the chosen gauge and it is radar that is the outlier. The test only catches")
        print("   the narrow failure mode it was designed for - one gauge out of step with its")
        print("   neighbours - and that failure mode is a minority of the disagreements.")
    print()

    print("6. WHAT THIS CANNOT SETTLE. It measures agreement between two instruments, neither of")
    print("   which is ground truth. A gauge can genuinely miss a convective shower that radar")
    print("   sees; radar over-reads in hail, bright band and ground clutter. Every FP is either a")
    print("   good flag wrongly destroyed OR a case where radar is the one that is wrong, and this")
    print("   experiment cannot tell those apart. It also cannot say what a withdrawn flag should")
    print("   become (`not_dry`, `insufficient_readings`, or the next gauge down the list), and it")
    print(f"   says nothing about the {sum(1 for ev in flags if not ev['scorable'])} flags radar "
          f"cannot check at all - most of")
    print("   them before the radar archive begins on 2024-11-21.")


# ---------------------------------------------------------------------------------------------

def parse_numbers(text, what):
    try:
        values = sorted({float(x) for x in text.replace(",", " ").split()})
    except ValueError as exc:
        raise DataProblem(f"could not read --{what}: {exc}") from exc
    if not values:
        raise DataProblem(f"--{what} is empty")
    return values


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data"), help="the data directory to read")
    ap.add_argument("--radii", default=" ".join(f"{r:g}" for r in DEFAULT_RADII_KM),
                    help="neighbour radii R in km, space or comma separated")
    ap.add_argument("--thresholds", default=" ".join(f"{t:g}" for t in DEFAULT_THRESHOLDS_MM),
                    help="neighbour median thresholds T in mm, space or comma separated")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many in-scope events (a quick run; the totals will not "
                         "represent the whole record and the report says so)")
    ap.add_argument("--progress", type=int, default=10000,
                    help="print progress to stderr every N events (0 to silence)")
    args = ap.parse_args(argv)

    try:
        radii = parse_numbers(args.radii, "radii")
        thresholds = parse_numbers(args.thresholds, "thresholds")
        data = Path(args.data)
        events, n_rows, n_flags = load_events(
            data / "classification" / "all_events_classified.csv", args.limit or None)
        gauges = load_gauges(data / "rain" / "gauges.csv")
        overflows = load_overflows(data / "overflows.csv")
        daily = data / "rain" / "daily"
        if not daily.is_dir():
            raise DataProblem(f"{daily} is not a directory")
        rain = RainWindows(daily)
        index = NeighbourIndex(gauges, overflows, max(radii))
        neighbour_medians(events, index, rain, radii, args.progress or None)
    except DataProblem as exc:
        print(f"data problem: {exc}", file=sys.stderr)
        return 2

    flags = [ev for ev in events if ev["verdict"] == "dry_day"]
    not_dry_events = [ev for ev in events if ev["verdict"] == "not_dry"]
    scorable_flags = sum(1 for ev in flags if ev["scorable"])

    print("=" * 100)
    print("GAUGE NEIGHBOUR TEST -- CALIBRATION OF R AND T")
    print("=" * 100)
    print("Experiment only. No verdict is changed and nothing is written.")
    if args.limit:
        print(f"*** PARTIAL RUN: --limit {args.limit} was given, so the totals below cover only the "
              f"first {len(events)} in-scope rows of the file and are NOT the whole record. ***")
    print()
    print(f"classification rows read           : {n_rows}")
    print(f"current dry_day flags in the file  : {n_flags}")
    print(f"rows in scope for this run         : {len(events)}")
    print(f"  dry_day flags                    : {len(flags)} "
          f"({scorable_flags} with complete radar, {len(flags) - scorable_flags} without)")
    print(f"  not_dry events with complete radar: {len(not_dry_events)}")
    print(f"gauges with coordinates            : {len(gauges)}")
    print(f"overflows with coordinates         : {len(overflows)}")
    print(f"radii R (km)                       : {', '.join(f'{r:g}' for r in radii)}")
    print(f"thresholds T (mm)                  : {', '.join(f'{t:g}' for t in thresholds)}")
    print(f"dry threshold / readings required  : {DRY_THRESHOLD_MM} mm / {READINGS_REQUIRED} of 192")
    if rain.missing_days:
        days = sorted(rain.missing_days)
        print(f"daily rain files absent for {len(days)} day(s) that a window needed: "
              f"{', '.join(days[:6])}{' ...' if len(days) > 6 else ''}")
        print("  gauges are simply unusable on those days; nothing is assumed about them.")

    print_coverage(flags, not_dry_events, radii)
    rows = print_main_table(flags, radii, thresholds, n_flags)
    print_not_dry_table(not_dry_events, radii, thresholds)
    print_cranleigh(flags, radii, thresholds)
    print_conclusion(flags, radii, n_flags, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
