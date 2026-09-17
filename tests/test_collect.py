"""Tests for scripts/collect.py (01_SPEC.md §4). No network: fixtures only."""
import filecmp
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import read_csv, read_json  # noqa: E402
from swt.timeutil import iso_to_ms  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
SOURCES = FIXTURES / "sources_fixture.json"
SNAPSHOT_A = FIXTURES / "snapshot_a.json"
NOW_1 = "2026-01-01T00:00:00Z"
NOW_2 = "2026-01-01T00:10:00Z"


def collect(data_dir, fixture, now):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "collect.py"), "--sources", str(SOURCES),
         "--fixture", str(fixture), "--data", str(data_dir), "--now", now],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def snapshot_a():
    return json.loads(SNAPSHOT_A.read_text())


def write_fixture(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def attrs(fixture, slug, source_id):
    return next(f["attributes"] for f in fixture[slug]["features"] if f["attributes"]["Id"] == source_id)


def events(data_dir):
    rows = []
    for path in sorted((Path(data_dir) / "events").glob("*.csv")):
        rows.extend(read_csv(path))
    return {r["event_id"]: r for r in rows}


def offline(data_dir):
    rows = []
    for path in sorted((Path(data_dir) / "offline").glob("*.csv")):
        rows.extend(read_csv(path))
    return rows


def test_new_overflows(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    overflows = {r["overflow_key"]: r for r in read_csv(data / "overflows.csv")}
    assert sorted(overflows) == ["south-west:SWW001", "st-connect:STC001", "thames:TW001", "thames:TW002",
                                 "thames:TW003"]
    tw1 = overflows["thames:TW001"]
    assert tw1["company_name"] == "Thames Water"
    assert tw1["source_id"] == "TW001"
    assert (tw1["latitude"], tw1["longitude"]) == ("51.507200", "-0.127600")
    assert tw1["receiving_watercourse"] == "River Thames"
    assert tw1["first_seen_utc"] == tw1["last_seen_utc"] == NOW_1
    assert read_json(data / "meta.json")["launch_utc"] == NOW_1


def test_new_event_with_end(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    ev = events(data)[f"thames:TW001:{iso_to_ms('2025-12-31T10:00:00Z')}"]
    assert ev["start_utc"] == "2025-12-31T10:00:00Z"
    assert ev["end_utc"] == "2025-12-31T12:00:00Z"
    assert ev["duration_min"] == "120"
    assert ev["end_observed"] == "true"
    assert ev["source"] == "hub"
    assert ev["first_observed_utc"] == ev["last_observed_utc"] == NOW_1
    assert (data / "events" / "2025-12.csv").exists()


def test_ongoing_event_then_end_appears(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    event_id = f"thames:TW002:{iso_to_ms('2025-12-31T22:00:00Z')}"
    ev = events(data)[event_id]
    assert ev["end_utc"] == "" and ev["duration_min"] == ""

    fx = snapshot_a()
    a = attrs(fx, "thames", "TW002")
    a["Status"] = 0
    a["StatusStart"] = a["LatestEventEnd"] = iso_to_ms("2026-01-01T00:05:00Z")
    collect(data, write_fixture(tmp_path, "b.json", fx), NOW_2)
    ev = events(data)[event_id]
    assert ev["end_utc"] == "2026-01-01T00:05:00Z"
    assert ev["duration_min"] == "125"
    assert ev["end_observed"] == "true"
    assert ev["first_observed_utc"] == NOW_1
    assert ev["last_observed_utc"] == NOW_2


def test_near_duplicate_start_keeps_event_id(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    original_id = f"thames:TW001:{iso_to_ms('2025-12-31T10:00:00Z')}"

    fx = snapshot_a()
    attrs(fx, "thames", "TW001")["LatestEventStart"] = iso_to_ms("2025-12-31T10:10:00Z")
    stdout = collect(data, write_fixture(tmp_path, "b.json", fx), NOW_2)
    tw1_events = [e for e in events(data).values() if e["overflow_key"] == "thames:TW001"]
    assert [e["event_id"] for e in tw1_events] == [original_id]
    assert tw1_events[0]["start_utc"] == "2025-12-31T10:10:00Z"
    assert tw1_events[0]["duration_min"] == "110"
    assert tw1_events[0]["last_observed_utc"] == NOW_2
    assert "retimed_starts=1" in stdout.splitlines()


def test_inferred_end_when_newer_event_appears(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    old_id = f"thames:TW002:{iso_to_ms('2025-12-31T22:00:00Z')}"

    fx = snapshot_a()
    a = attrs(fx, "thames", "TW002")
    a["StatusStart"] = a["LatestEventStart"] = iso_to_ms("2026-01-01T00:08:00Z")
    collect(data, write_fixture(tmp_path, "b.json", fx), NOW_2)
    evs = events(data)
    old = evs[old_id]
    assert old["end_utc"] == "2026-01-01T00:08:00Z"
    assert old["end_observed"] == "false"
    assert old["duration_min"] == "128"
    new = evs[f"thames:TW002:{iso_to_ms('2026-01-01T00:08:00Z')}"]
    assert new["end_utc"] == "" and new["first_observed_utc"] == NOW_2
    assert (data / "events" / "2026-01.csv").exists()


def test_offline_open_then_close(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    assert offline(data) == [{"overflow_key": "thames:TW003", "company_slug": "thames",
                              "offline_start_utc": "2025-12-30T08:00:00Z", "offline_end_utc": "",
                              "first_observed_utc": NOW_1, "last_observed_utc": NOW_1}]

    fx = snapshot_a()
    a = attrs(fx, "thames", "TW003")
    a["Status"] = 0
    a["StatusStart"] = iso_to_ms("2026-01-01T00:03:00Z")
    collect(data, write_fixture(tmp_path, "b.json", fx), NOW_2)
    periods = offline(data)
    assert len(periods) == 1
    assert periods[0]["offline_end_utc"] == "2026-01-01T00:03:00Z"
    assert periods[0]["last_observed_utc"] == NOW_2


def test_camelcase_and_latest_event_finish_aliases(tmp_path):
    data = tmp_path / "data"
    collect(data, SNAPSHOT_A, NOW_1)
    evs = events(data)
    sww = evs[f"south-west:SWW001:{iso_to_ms('2025-12-29T06:15:00Z')}"]
    assert (sww["start_utc"], sww["end_utc"], sww["duration_min"]) == (
        "2025-12-29T06:15:00Z", "2025-12-29T09:30:00Z", "195")
    stc = evs[f"st-connect:STC001:{iso_to_ms('2025-12-28T14:00:00Z')}"]
    assert (stc["start_utc"], stc["end_utc"], stc["duration_min"]) == (
        "2025-12-28T14:00:00Z", "2025-12-28T15:45:00Z", "105")
    snap = read_json(data / "status_snapshot.json")
    assert snap["south-west:SWW001"]["status"] == 0
    assert snap["st-connect:STC001"]["latest_event_end_ms"] == iso_to_ms("2025-12-28T15:45:00Z")


def test_determinism(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    collect(first, SNAPSHOT_A, NOW_1)
    collect(second, SNAPSHOT_A, NOW_1)
    comparison = filecmp.dircmp(first, second)

    def assert_identical(cmp):
        assert not cmp.left_only and not cmp.right_only and not cmp.funny_files
        _, mismatch, errors = filecmp.cmpfiles(cmp.left, cmp.right, cmp.common_files, shallow=False)
        assert not mismatch and not errors
        for sub in cmp.subdirs.values():
            assert_identical(sub)

    assert_identical(comparison)
    raw = (first / "overflows.csv").read_bytes()
    assert b"\r\n" not in raw
