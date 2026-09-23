"""Tests for swt.io.load_events: one row per event_id across the two classifier inputs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.io import load_events  # noqa: E402

HEADER = ("event_id,overflow_key,company_slug,start_utc,end_utc,duration_min,source,"
          "first_observed_utc,last_observed_utc,end_observed\n")


def row(event_id, source, observed):
    return (f"{event_id},thames:TWL00453,thames,2026-09-12T12:00:00Z,2026-09-12T12:45:00Z,45,"
            f"{source},{observed},{observed},true\n")


def build(tmp_path, events, history):
    (tmp_path / "events").mkdir()
    (tmp_path / "events" / "2026-09.csv").write_text(HEADER + "".join(events))
    (tmp_path / "thames_history").mkdir()
    (tmp_path / "thames_history" / "events_pre_launch.csv").write_text(HEADER + "".join(history))
    return tmp_path


def test_hub_row_wins_when_both_sources_hold_the_same_event(tmp_path):
    """The Hub republishes old Thames discharges after the back-fill; that must not double-count."""
    data = build(tmp_path,
                 [row("thames:A:1", "hub", "2026-09-21T08:00:27Z")],
                 [row("thames:A:1", "thames_api", "2026-09-19T20:01:39Z")])
    rows = load_events(data)
    assert [r["event_id"] for r in rows] == ["thames:A:1"]
    assert rows[0]["source"] == "hub"


def test_events_unique_to_either_source_are_all_kept(tmp_path):
    data = build(tmp_path,
                 [row("thames:A:1", "hub", "2026-09-21T08:00:27Z")],
                 [row("thames:B:2", "thames_api", "2026-09-19T20:01:39Z")])
    assert sorted(r["event_id"] for r in load_events(data)) == ["thames:A:1", "thames:B:2"]


def test_missing_history_file_is_not_an_error(tmp_path):
    (tmp_path / "events").mkdir()
    (tmp_path / "events" / "2026-09.csv").write_text(HEADER + row("thames:A:1", "hub", "x"))
    assert [r["event_id"] for r in load_events(tmp_path)] == ["thames:A:1"]
