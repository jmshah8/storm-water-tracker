"""Deterministic CSV and JSON read/write helpers (UTF-8, \\n line endings, sorted)."""
import csv
import json
from pathlib import Path


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames, sort_key):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in sorted(rows, key=sort_key):
            writer.writerow(row)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")


def load_events(data):
    """Every event the classifier reads: data/events/*.csv then the Thames pre-launch history.

    One row per event_id. The two sets were de-duplicated once when the history was back-filled
    (step 3.3), but the Hub keeps republishing old Thames discharges into data/events long after
    that back-fill, so the same discharge can arrive from both sources. Where it does, the Hub row
    wins: the Hub is the specified primary source (01_SPEC.md §2) and the history only fills what
    the Hub does not carry. events_overlap.csv is validation only and is never classified.
    """
    data = Path(data)
    rows = [r for p in sorted((data / "events").glob("*.csv")) for r in read_csv(p)]
    rows += read_csv(data / "thames_history" / "events_pre_launch.csv")
    seen, out = set(), []
    for r in rows:
        if r["event_id"] not in seen:
            seen.add(r["event_id"])
            out.append(r)
    return out
