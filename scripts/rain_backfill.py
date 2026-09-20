#!/usr/bin/env python3
"""Drive the Phase 3 historic rainfall back-fill (step 3.4).

Dispatches `thames-history.yml` job `rain-backfill` one month at a time, keeping
a fixed number of months in flight (01_SPEC.md 2.2, amended 20 Sep 2026: at most
three concurrent runs, each pacing itself at <= 5 requests/second).

A month is finished when every one of its UTC days inside the back-fill window has
a file under data/rain/daily/. The driver re-reads that directory after every poll,
so it is resumable: stop it and start it again and it picks up what is left.

This Mac drops its network connection for minutes at a time, so every `gh` call is
retried for up to --network-patience seconds before the driver gives up.

Exit codes: 0 all months present, 1 a month failed twice, 2 network gave out.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = "thames-history.yml"


def run(cmd, patience, check=True):
    """Run a command, retrying while the network is down."""
    deadline = time.time() + patience
    while True:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0 or not check:
            return p
        transient = any(s in (p.stderr or "") for s in (
            "error connecting", "connection reset", "RemoteDisconnected",
            "timeout", "TLS handshake", "could not resolve host", "502", "503",
        ))
        if not transient or time.time() > deadline:
            return p
        print(f"  network: {p.stderr.strip().splitlines()[-1][:120]} — retrying in 30 s", flush=True)
        time.sleep(30)


def months_in_window(data: Path, start: date, end: date):
    """Months (YYYY-MM) with at least one day missing between start and end inclusive."""
    have = {f.name[:10] for f in (data / "rain" / "daily").glob("*.csv")}
    pending, d = [], start
    while d <= end:
        if d.isoformat() not in have and d.strftime("%Y-%m") not in pending:
            pending.append(d.strftime("%Y-%m"))
        d += timedelta(days=1)
    return pending


def newest_dispatch_id(patience):
    p = run(["gh", "run", "list", "--workflow", WORKFLOW, "--event", "workflow_dispatch",
             "--limit", "5", "--json", "databaseId,createdAt"], patience)
    if p.returncode != 0:
        return None
    runs = json.loads(p.stdout or "[]")
    return max((r["databaseId"] for r in runs), default=None)


def run_state(run_id, patience):
    p = run(["gh", "run", "view", str(run_id), "--json", "status,conclusion"], patience)
    if p.returncode != 0:
        return None, None
    d = json.loads(p.stdout or "{}")
    return d.get("status"), d.get("conclusion")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--lanes", type=int, default=3, help="months in flight at once (default 3)")
    ap.add_argument("--start", default="2022-03-31", help="first UTC day to back-fill (default 2022-03-31)")
    ap.add_argument("--end", default=None, help="last UTC day (default: 3 days ago, the Hydrology lag)")
    ap.add_argument("--poll", type=int, default=120, help="seconds between polls (default 120)")
    ap.add_argument("--network-patience", type=int, default=1200,
                    help="seconds to keep retrying a gh call while the network is down (default 1200)")
    ap.add_argument("--dry-run", action="store_true", help="list the months that would be dispatched and stop")
    args = ap.parse_args()

    data = Path(args.data)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=3)

    queue = months_in_window(data, start, end)
    print(f"{len(queue)} months to back-fill: {queue[0]} -> {queue[-1]}" if queue else "nothing to do", flush=True)
    if args.dry_run or not queue:
        for m in queue:
            print(m)
        return 0

    lanes = {}       # month -> run id
    attempts = {}    # month -> times dispatched
    done = []

    while queue or lanes:
        # A run's files only appear here once it has pushed, so refresh before judging.
        run(["git", "-C", str(ROOT), "pull", "--rebase", "--autostash", "-q"], args.network_patience, check=False)
        still_missing = set(months_in_window(data, start, end))

        for month, run_id in list(lanes.items()):
            status, conclusion = run_state(run_id, args.network_patience)
            if status is None:
                print(f"  {month}: cannot read run {run_id}, will look again", flush=True)
                continue
            if status != "completed":
                continue
            del lanes[month]
            if month not in still_missing:
                done.append(month)
                print(f"  {month}: done ({conclusion}) — {len(done)} months in, {len(queue) + len(lanes)} left", flush=True)
            elif attempts[month] < 2:
                queue.insert(0, month)
                print(f"  {month}: {conclusion} and days still missing — re-queued", flush=True)
            else:
                print(f"  {month}: failed twice ({conclusion}), run {run_id}", file=sys.stderr, flush=True)
                return 1

        while queue and len(lanes) < args.lanes:
            month = queue.pop(0)
            if month not in still_missing:
                print(f"  {month}: already complete, skipped", flush=True)
                continue
            p = run(["gh", "workflow", "run", WORKFLOW, "-f", "job=rain-backfill", "-f", f"month={month}"],
                    args.network_patience)
            if p.returncode != 0:
                print(f"dispatch failed for {month}: {p.stderr.strip()[:200]}", file=sys.stderr, flush=True)
                return 2
            time.sleep(8)  # let the run register before asking for its id
            run_id = newest_dispatch_id(args.network_patience)
            if run_id is None:
                print(f"dispatched {month} but could not read its run id", file=sys.stderr, flush=True)
                return 2
            lanes[month] = run_id
            attempts[month] = attempts.get(month, 0) + 1
            print(f"  {month}: dispatched, run {run_id} ({len(lanes)}/{args.lanes} lanes busy)", flush=True)

        if queue or lanes:
            time.sleep(args.poll)

    missing = months_in_window(data, start, end)
    if missing:
        print(f"finished with {len(missing)} months still incomplete: {missing}", file=sys.stderr)
        return 1
    print(f"all {len(done)} months back-filled", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
