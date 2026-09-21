#!/usr/bin/env python3
"""Phase 3 acceptance (05_CHECKS_AND_ACCEPTANCE.md, items T1-T8): one row per item, printed as a table.

Phase 3 is the Thames Water back-test: the company's own alert stream since April 2022, run through the
unchanged dry-day-v1 rule. Nothing here is copied from the step reports — the location mapping (T2), the
overlap validation (T3) and the back-test numbers (T6) are recomputed from data/thames_history, data/events
and the live Thames API, and the flags in T5 are re-fetched from the EA Hydrology API. The plan's own
checks are reused where they exist rather than written a second time: T4 is `check.py --step 3.4`, and
T5/T6/T7 are parts (d)/(a)-(b)/(c) of `check.py --step 3.5`.

Exit codes: 0 every item passed, 1 an item failed, 2 network error.
"""
import argparse
import collections
import contextlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _check_module():
    """The one live copy of scripts/check.py.

    When check.py itself is the script being run it is `__main__`, and a plain `import check` would load a
    second copy whose NetworkError is a different class — so an exception raised here would sail straight
    past check.py's own handler. Reuse the running module when that is what it is.
    """
    running = sys.modules.get("__main__")
    if getattr(running, "__file__", "").endswith("check.py"):
        return running
    import check as fresh
    return fresh


_check = _check_module()
NetworkError = _check.NetworkError
read_csv = _check.read_csv
read_json_file = _check.read_json_file
step_3_4 = _check.step_3_4
step_3_5 = _check.step_3_5

import thames_history as tw  # noqa: E402  (scripts/thames_history.py: the API client and the mapping)

# T1: what CHECK 3.1 says must be written down — endpoints, headers, pagination, earliest date, the
# timezone of `datetime`. Each fact is looked for verbatim in NOTES_FOR_JAIMIN.md.
CONTRACT_FACTS = [
    ("base URL", r"https://api\.thameswater\.co\.uk/opendata/v2/discharge"),
    ("/alerts endpoint", r"`/alerts`"),
    ("/status endpoint", r"`/status`"),
    ("headers / credentials", r"needs no credentials"),
    ("pagination", r"`limit` max 1000.*`offset` pages"),
    ("earliest alert date", r"earliest 2022-04-01T00:00:00|from 2022-04-01T00:00:00"),
    ("`datetime` timezone", r"`datetime` is (?:therefore )?UTC"),
    ("timezone evidence", r"223 match a discharge"),
]
# T8: the same secret patterns acceptance item E1 uses, plus the Thames credential names step 3.0 would
# have created had the API needed any.
SECRET_PATTERN = "client_secret|netlify_auth|nfp_|TW_CLIENT_ID|TW_CLIENT_SECRET"
# A workflow line naming a GitHub secret carries no value (it is substituted at run time), and the three
# files that hold the search pattern itself are not leaks either.
SECRET_ALLOWED = re.compile(r"^\.github/workflows/[^:]+:\d+:\s*[A-Z_]+: \$\{\{ secrets\.[A-Z_]+ \}\}\s*$"
                            r"|^scripts/(?:check|acceptance_phase3)\.py:\d+:")
THIN_OVERLAP = 20      # below this many overlap-period events the window is too thin to judge on its own


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), **kw)


def captured(fn, args=None):
    """Run one of check.py's step functions, returning (exit code, everything it printed)."""
    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        code = fn(args if args is not None else argparse.Namespace())
    return code, buffer.getvalue()


def live_contract():
    """One unauthenticated request to each endpoint NOTES records, to confirm the contract still holds."""
    try:
        status = tw.get("status", {"limit": 5})["items"]
        alerts = tw.get("alerts", {"limit": 5})["items"]
    except tw.ThamesError as e:
        raise NetworkError(f"thames api: {e}")
    stamps = [a["datetime"] for a in alerts]
    zone_marker = any(s.endswith("Z") or "+" in s[10:] for s in stamps)
    return (f"live and unauthenticated (no headers but Accept): /status returned {len(status)} items with "
            f"uniqueId present on {sum(1 for s in status if s.get('uniqueId'))}; /alerts returned "
            f"{len(alerts)} items, newest {max(stamps)}, timezone marker in `datetime`: {zone_marker}")


def launch_moment():
    """The launch instant from data/meta.json, as UTC."""
    return tw.to_utc(read_json_file(ROOT / "data" / "meta.json")["launch_utc"].rstrip("Z"))


def hub_thames_starts():
    """{overflow_key: [start times]} for every Thames discharge we recorded ourselves from the Hub."""
    starts = collections.defaultdict(list)
    for path in sorted((ROOT / "data" / "events").glob("*.csv")):
        for ev in read_csv(path):
            if ev["company_slug"] == "thames":
                starts[ev["overflow_key"]].append(tw.to_utc(ev["start_utc"].rstrip("Z")))
    return starts


def within(moment, others):
    return any(abs(moment - other) <= tw.NEAR_DUPLICATE for other in others)


def acceptance_phase3(args):
    """05_CHECKS_AND_ACCEPTANCE.md Phase 3: T1-T8."""
    results = []

    def add(item, expected, observed, status):
        results.append((item, expected, observed, status))
        print(f"  {item:4} {status:6} {observed}")

    data = ROOT / "data"
    history = data / "thames_history"
    now = datetime.now(timezone.utc)

    print("The API contract")
    notes_lines = (ROOT / "NOTES_FOR_JAIMIN.md").read_text(encoding="utf-8").splitlines()
    lines_used, absent = set(), []
    for label, pattern in CONTRACT_FACTS:
        hits = [i + 1 for i, line in enumerate(notes_lines) if re.search(pattern, line)]
        if hits:
            lines_used.add(hits[0])
        else:
            absent.append(label)
    live = live_contract()
    add("T1", "present", f"NOTES_FOR_JAIMIN.md records {len(CONTRACT_FACTS) - len(absent)} of "
        f"{len(CONTRACT_FACTS)} contract facts (endpoints, headers, pagination, earliest date, the "
        f"`datetime` timezone and its evidence) on lines {sorted(lines_used)}; missing: "
        f"{absent or 'none'}; step 3.0's credentials do not exist because the API needs none — {live}",
        "PASS" if not absent else "FAIL")

    print("Location mapping")
    alerts = tw.read_raw(tw.RAW_PATH)
    if not alerts:
        add("T2", ">= 90%", f"{tw.RAW_PATH.relative_to(ROOT)} is missing or empty", "FAIL")
        add("T3", ">= 90%", "no alerts to validate", "FAIL")
    else:
        try:
            mapping, how, unmatched = tw.location_map(alerts)
        except tw.ThamesError as e:
            raise NetworkError(f"thames /status: {e}")
        total = sum(how.values())
        matched = how["by id"] + how["by coordinates"]
        share = 100.0 * matched / total if total else 0.0
        add("T2", ">= 90%", f"{matched} of {total} API locations mapped to a Hub overflow ({share:.1f}%): "
            f"by id {how['by id']}, by coordinates within {tw.COORD_MATCH_M:.0f} m "
            f"{how['by coordinates']}; unmatched {how['unmatched']} "
            f"{[u[0] for u in unmatched[:3]]}", "PASS" if share >= 90 else "FAIL")

        print("Overlap validation")
        launch = launch_moment()
        events, _ = tw.build_events(alerts, mapping, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        hub_starts = hub_thames_starts()
        api_starts = collections.defaultdict(list)
        for ev in events:
            api_starts[ev["overflow_key"]].append(tw.to_utc(ev["start_utc"].rstrip("Z")))
        overlap = [ev for ev in events if tw.to_utc(ev["start_utc"].rstrip("Z")) >= launch]
        overlap_matched = sum(1 for ev in overlap
                              if within(tw.to_utc(ev["start_utc"].rstrip("Z")),
                                        hub_starts.get(ev["overflow_key"], ())))
        overlap_rate = 100.0 * overlap_matched / len(overlap) if overlap else 0.0
        # At launch the Hub gave us the latest pre-launch discharge for every Thames overflow. Those seeded
        # events are Hub events too, and a far larger sample than the overlap window, which is only as old
        # as our own record. thames_history.py's CHECK 3.3(b) judges on them whenever the overlap window is
        # thinner than THIN_OVERLAP events; this item follows the same rule and reports both rates.
        seeded = [(key, start) for key, starts in hub_starts.items() for start in starts if start < launch]
        seeded_matched = sum(1 for key, start in seeded if within(start, api_starts.get(key, ())))
        seeded_rate = 100.0 * seeded_matched / len(seeded) if seeded else 0.0
        on_file = len(read_csv(history / "events_overlap.csv")) if (history / "events_overlap.csv").exists() else 0
        judged = overlap_rate if len(overlap) >= THIN_OVERLAP else seeded_rate
        which = "overlap window" if len(overlap) >= THIN_OVERLAP else "seeded Hub events"
        add("T3", ">= 90%", f"overlap window (starts at or after launch {launch:%Y-%m-%dT%H:%M:%SZ}): "
            f"{overlap_matched} of {len(overlap)} Thames API events match a Hub event we recorded within "
            f"15 min ({overlap_rate:.1f}%); events_overlap.csv on disk holds {on_file}; seeded Hub events "
            f"(the latest pre-launch discharge for every Thames overflow): {seeded_matched} of "
            f"{len(seeded)} appear in the API history within 15 min ({seeded_rate:.1f}%); judged on the "
            f"{which} because the overlap window holds {len(overlap)} events (< {THIN_OVERLAP} is too thin)",
            "PASS" if judged >= 90 else "FAIL")

    print("Historic rainfall")
    code, text = captured(step_3_4)
    days = re.search(r"\(a\) days from (\S+) to (\S+): (\d+); files present: (\d+); missing: (\d+) (\[[^\]]*\])",
                     text)
    years = re.findall(r"^\s+(\d{4}):\s+([\d,]+) of\s+([\d,]+) gauge-days \(\s*([\d.]+)%\)", text, re.M)
    by_year = ("; ".join(f"{y} {share}% of {total} gauge-days" for y, _, total, share in years)
               or "not parsed from check.py --step 3.4's output")
    add("T4", "yes", (f"{days.group(1)} to {days.group(2)}: {days.group(3)} days, {days.group(4)} daily files "
                      f"present, {days.group(5)} missing {days.group(6)}; n_readings >= 88: {by_year}")
        if days else f"check.py --step 3.4 printed nothing to parse: {text.strip()[:200]}",
        "PASS" if code == 0 and days else "FAIL")

    print("The back-test page")
    page = ROOT / "site" / "thames-backtest.html"
    if not page.exists():
        for item in ("T5", "T6", "T7"):
            add(item, "see 05_CHECKS_AND_ACCEPTANCE.md",
                f"{page.relative_to(ROOT)} is missing; run scripts/build_site.py first", "FAIL")
    else:
        code, text = captured(step_3_5)
        figures = re.search(r"\(a\) figures on the page: (\d+); recomputed from the CSV: (\d+); missing from "
                            r"the page: (\d+) (\[[^\]]*\]); on the page but not recomputed: (\d+) (\[[^\]]*\])",
                            text)
        mismatches = re.search(r"\(b\) mismatches: (\d+)", text)
        bad_lines = re.findall(r"^    (\([^\n]*recomputed[^\n]*)$", text, re.M)
        cautions = re.search(r"\(c\) required cautions present: (\d+) of (\d+); missing: (\[[^\]]*\])", text)
        samples = re.findall(r"^    (\S+) start (\S+) (\S+): recomputed ([\d.]+) mm vs stored ([\d.]+) mm; "
                             r"dry: (True|False)$", text, re.M)

        wrong = [(event_id, got, stored, dry) for event_id, _start, _method, got, stored, dry in samples
                 if abs(Decimal(got) - Decimal(stored)) > Decimal("0.01") or Decimal(got) > Decimal("0.25")
                 or dry != "True"]
        methods = collections.Counter(m for _i, _s, m, _g, _st, _d in samples)
        add("T5", "all within 0.01 mm and <= 0.25", f"{len(samples)} random pre-launch Thames dry_day events "
            f"re-fetched from the Hydrology API ({dict(methods)}); recomputed totals "
            f"{[s[3] for s in samples]} mm against stored {[s[4] for s in samples]} mm; outside 0.01 mm or "
            f"above 0.25 mm: {len(wrong)} {[w[0] for w in wrong[:3]]}",
            "PASS" if samples and not wrong else "FAIL")

        page_ok = bool(figures) and figures.group(3) == "0" and bool(mismatches) and mismatches.group(1) == "0"
        add("T6", "exact", (f"{figures.group(1)} data-value figures on thames-backtest.html, {figures.group(2)} "
                            f"recomputed from all_events_classified.csv; missing from the page "
                            f"{figures.group(3)} {figures.group(4)}; on the page but not recomputed "
                            f"{figures.group(5)} {figures.group(6)}; mismatches {mismatches.group(1)} "
                            f"{bad_lines[:2]}") if figures and mismatches
            else f"check.py --step 3.5 printed nothing to parse: {text.strip()[:200]}",
            "PASS" if page_ok else "FAIL")

        add("T7", "present", (f"required cautions on the page: {cautions.group(1)} of {cautions.group(2)} "
                              f"(the Guardian FOI figures, \"unverified figures\", the monitor rollout, the "
                              f"company's own unaudited alerts, and the \"back-test of the method\" line); "
                              f"missing: {cautions.group(3)}") if cautions else "no cautions line to parse",
            "PASS" if cautions and cautions.group(3) == "[]" else "FAIL")

    print("Secrets")
    grep = run(["git", "grep", "-inE", SECRET_PATTERN, "--", ".", ":!build-pack", ":!NOTES_FOR_JAIMIN.md"])
    hits = [line for line in grep.stdout.splitlines() if not SECRET_ALLOWED.match(line)]
    ignored = ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    tracked_env = bool(run(["git", "ls-files", ".env"]).stdout.strip())
    referenced = set()
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        referenced |= set(re.findall(r"secrets\.([A-Z0-9_]+)", path.read_text(encoding="utf-8")))
    gh = run(["gh", "secret", "list", "--json", "name"])
    if gh.returncode != 0:
        raise NetworkError(f"gh secret list failed: {gh.stderr.strip()[:200]}")
    in_actions = {s["name"] for s in json.loads(gh.stdout or "[]")}
    absent_secrets = sorted(referenced - in_actions)
    thames_secrets = sorted(n for n in in_actions | referenced if n.startswith("TW_"))
    thames_note = (str(thames_secrets) if thames_secrets else
                   "none, and none are needed — the Thames API is open (step 3.0 cancelled, 19 Sep 2026), "
                   "so there is no TW_CLIENT_ID/TW_CLIENT_SECRET to hold")
    add("T8", "yes", f"secret-pattern hits beyond GitHub secret references and this check: {len(hits)} "
        f"{hits[:3]}; .env ignored: {ignored}, tracked: {tracked_env}; secrets the workflows reference: "
        f"{sorted(referenced)}; present in Actions: {sorted(in_actions)}; referenced but absent from "
        f"Actions: {absent_secrets or 'none'}; Thames credentials: {thames_note}",
        "PASS" if not hits and ignored and not tracked_env and not absent_secrets else "FAIL")

    print("\n| item | expected | observed | result |")
    print("|---|---|---|---|")
    for item, expected, observed, status in results:
        print(f"| {item} | {expected} | {observed} | {status} |")
    counts = collections.Counter(r[3] for r in results)
    print(f"\n{dict(counts)}")
    return 0 if not counts["FAIL"] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args = ap.parse_args()
    try:
        return acceptance_phase3(args)
    except NetworkError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
