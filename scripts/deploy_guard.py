#!/usr/bin/env python3
"""Netlify credit budget guard and deploy log (01_SPEC.md §9.2).

Check before a deploy:   deploy_guard.py --kind prod|alias --override true|false
    Refuses (exit 1) a production deploy when data/deploy_log.json already has 8 `prod` entries in the
    current UTC calendar month, unless --override true.
Record after a deploy:   deploy_guard.py --record deploy.json --kind prod|alias --run-url URL [--message TEXT]
    Appends {utc, kind, run_url, message, deploy_url} from the Netlify CLI's --json output; keeps the log
    sorted by utc.

Exit codes: 0 ok, 1 refused or bad input.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_json  # noqa: E402

PROD_PER_MONTH = 8
DEFAULT_LOG = ROOT / "data" / "deploy_log.json"


def prod_this_month(log, now):
    month = now.strftime("%Y-%m")
    return sum(1 for e in log if e["kind"] == "prod" and e["utc"][:7] == month)


def check(log, kind, override, now):
    """(allowed, message)"""
    if kind == "alias":
        return True, "alias deploy: no production budget used"
    used = prod_this_month(log, now)
    if used >= PROD_PER_MONTH and not override:
        return False, (f"refused: {used} production deploys already this month ({now:%Y-%m}); the limit is "
                       f"{PROD_PER_MONTH}. Re-run with override_budget only if Jaimin has approved it.")
    note = " (override given)" if used >= PROD_PER_MONTH else ""
    return True, f"production deploy {used + 1} of {PROD_PER_MONTH} this month{note}"


def record(log, cli_output, kind, run_url, message, now):
    entry = {"utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "kind": kind, "run_url": run_url, "message": message,
             "deploy_url": cli_output["deploy_url"]}
    return sorted(log + [entry], key=lambda e: e["utc"])


def write_log(path, log):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(log, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", required=True, choices=["prod", "alias"])
    ap.add_argument("--override", default="false", choices=["true", "false"])
    ap.add_argument("--record", metavar="CLI_JSON", help="Netlify CLI --json output file to append to the log")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--message", default="")
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    log = read_json(args.log, default=[])
    if args.record:
        try:
            cli_output = json.loads(Path(args.record).read_text(encoding="utf-8"))
            log = record(log, cli_output, args.kind, args.run_url, args.message, now)
        except (OSError, ValueError, KeyError) as e:
            print(f"cannot record deploy: {e}", file=sys.stderr)
            return 1
        write_log(args.log, log)
        print(f"recorded {args.kind} deploy: {log[-1]['deploy_url'] if log else ''}")
        return 0

    allowed, message = check(log, args.kind, args.override == "true", now)
    print(message)
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
