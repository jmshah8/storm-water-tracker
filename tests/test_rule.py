"""Tests for swt/rule.py, dry-day-v3 (01_SPEC.md §5.2–5.3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swt.geo import haversine_km, nearest_gauges  # noqa: E402
from swt.rule import RULE_VERSION, classify_event  # noqa: E402

START = "2026-09-10T14:00:00Z"          # day D = 2026-09-10; window 09-09T00:00Z .. 09-11T00:00Z
NOW_EARLY = "2026-09-12T00:00:00Z"      # < window_end + 72 h
NOW_AFTER_72H = "2026-09-14T00:00:00Z"  # = window_end + 72 h
NOW_AFTER_14D = "2026-09-25T00:00:00Z"  # = window_end + 14 days

NEAR = {"gauge_id": "near", "label": "Near gauge", "distance_km": 2.0}
FAR = {"gauge_id": "far", "label": "Far gauge", "distance_km": 7.5}


def rain(table):
    """table: {(gauge_id, date): (total_mm, max15_mm, n_readings)}"""
    def lookup(gauge_id, day):
        row = table.get((gauge_id, day))
        return None if row is None else {"total_mm": row[0], "max15_mm": row[1], "n_readings": row[2]}
    return lookup


def both_days(gauge_id, prev, day, prev_day="2026-09-09", same_day="2026-09-10"):
    return {(gauge_id, prev_day): prev, (gauge_id, same_day): day}


def test_total_exactly_threshold_is_dry_day():
    r = classify_event(START, [NEAR], rain(both_days("near", ("0.05", "0.05", 96), ("0.2", "0.2", 96))), NOW_EARLY)
    assert r["rain_window_total_mm"] == "0.25"
    assert r["verdict"] == "dry_day"


def test_total_just_above_threshold_is_not_dry():
    r = classify_event(START, [NEAR], rain(both_days("near", ("0.06", "0.06", 96), ("0.2", "0.2", 96))), NOW_EARLY)
    assert r["rain_window_total_mm"] == "0.26"
    assert r["verdict"] == "not_dry"


def test_total_rule_not_max15_rule():
    # a single 15-minute reading of 0.30 and nothing else: total 0.30 > 0.25 -> not_dry
    r = classify_event(START, [NEAR], rain(both_days("near", ("0", "0", 96), ("0.30", "0.30", 96))), NOW_EARLY)
    assert (r["rain_window_total_mm"], r["rain_window_max15_mm"]) == ("0.3", "0.3")
    assert r["verdict"] == "not_dry"


def test_nearest_gauge_with_too_few_readings_is_skipped():
    table = both_days("near", ("0", "0", 74), ("0", "0", 96))            # 170 readings
    table.update(both_days("far", ("1.2", "0.4", 96), ("0", "0", 96)))  # 192 readings
    r = classify_event(START, [NEAR, FAR], rain(table), NOW_EARLY)
    assert (r["gauge_id"], r["gauge_label"], r["gauge_distance_km"]) == ("far", "Far gauge", "7.50")
    assert r["n_readings_present"] == "192"
    assert r["verdict"] == "not_dry"


def test_no_gauge_within_10km():
    r = classify_event(START, [], rain({}), NOW_EARLY)
    assert r["verdict"] == "no_gauge_within_10km"
    assert r["is_final"] == "true"
    assert r["gauge_id"] == ""


def test_pending_before_72_hours_after_window():
    table = both_days("near", ("0", "0", 96), ("0", "0", 40))
    r = classify_event(START, [NEAR], rain(table), NOW_EARLY)
    assert r["verdict"] == "pending_rain_data"
    assert r["is_final"] == "false"


def test_insufficient_readings_from_72_hours_after_window():
    table = both_days("near", ("0", "0", 96), ("0", "0", 40))
    r = classify_event(START, [NEAR], rain(table), NOW_AFTER_72H)
    assert r["verdict"] == "insufficient_readings"
    assert r["is_final"] == "false"


def test_pending_is_decided_by_time_not_by_missing_files():
    r = classify_event(START, [NEAR], rain({}), NOW_EARLY)
    assert r["verdict"] == "pending_rain_data"


def test_utc_day_boundary():
    before = classify_event("2026-09-10T23:59:59Z", [NEAR], rain({}), NOW_EARLY)
    after = classify_event("2026-09-11T00:00:00Z", [NEAR], rain({}), NOW_EARLY)
    assert (before["day_utc"], before["window_start_utc"], before["window_end_utc"]) == (
        "2026-09-10", "2026-09-09T00:00:00Z", "2026-09-11T00:00:00Z")
    assert (after["day_utc"], after["window_start_utc"], after["window_end_utc"]) == (
        "2026-09-11", "2026-09-10T00:00:00Z", "2026-09-12T00:00:00Z")
    # rain on 09-09 is in the window for the 23:59:59 event only
    table = both_days("near", ("3.0", "1.0", 96), ("0", "0", 96))
    table[("near", "2026-09-11")] = ("0", "0", 96)
    assert classify_event("2026-09-10T23:59:59Z", [NEAR], rain(table), NOW_AFTER_14D)["verdict"] == "not_dry"
    assert classify_event("2026-09-11T00:00:00Z", [NEAR], rain(table), NOW_AFTER_14D)["verdict"] == "dry_day"


def test_basis_and_version_echoed():
    r = classify_event(START, [NEAR], rain(both_days("near", ("0", "0", 96), ("0", "0", 96))), NOW_EARLY,
                       rule_version=RULE_VERSION)
    assert r["verdict_basis"] == "total"
    assert r["rule_version"] == RULE_VERSION
    assert r["n_readings_expected"] == "192"


def test_is_final():
    partial = rain(both_days("near", ("0", "0", 84), ("0", "0", 96)))   # 180 readings
    complete = rain(both_days("near", ("0", "0", 96), ("0", "0", 96)))  # 192 readings
    assert classify_event(START, [NEAR], partial, NOW_AFTER_72H)["is_final"] == "false"
    assert classify_event(START, [NEAR], complete, NOW_EARLY)["is_final"] == "false"
    assert classify_event(START, [NEAR], complete, NOW_AFTER_72H)["is_final"] == "true"
    assert classify_event(START, [NEAR], partial, NOW_AFTER_14D)["is_final"] == "true"


def test_stuck_gauge_is_skipped(tmp_path=None):
    """dry-day-v2: a gauge that has stopped reporting rain is skipped, like one with too few readings."""
    table = both_days("near", ("0", "0", 96), ("0", "0", 96))        # the stuck gauge: says dry
    table.update(both_days("far", ("1.2", "0.4", 96), ("0", "0", 96)))  # a working gauge: says it rained
    stuck = lambda gauge_id, day: "stuck" if gauge_id == "near" else None  # noqa: E731

    without = classify_event(START, [NEAR, FAR], rain(table), NOW_EARLY)
    assert (without["verdict"], without["gauge_id"], without["n_gauges_skipped_stuck"]) == ("dry_day", "near", "0")

    with_check = classify_event(START, [NEAR, FAR], rain(table), NOW_EARLY, gauge_unusable=stuck)
    assert with_check["verdict"] == "not_dry"
    assert with_check["gauge_id"] == "far"
    assert with_check["n_gauges_skipped_stuck"] == "1"


def test_all_gauges_stuck_leaves_the_event_unclassified():
    table = both_days("near", ("0", "0", 96), ("0", "0", 96))
    everything_stuck = lambda gauge_id, day: "stuck"  # noqa: E731
    early = classify_event(START, [NEAR], rain(table), NOW_EARLY, gauge_unusable=everything_stuck)
    late = classify_event(START, [NEAR], rain(table), NOW_AFTER_72H, gauge_unusable=everything_stuck)
    assert early["verdict"] == "pending_rain_data"
    assert late["verdict"] == "insufficient_readings"
    assert late["n_gauges_skipped_stuck"] == "1"


def test_rule_version_is_v3():
    r = classify_event(START, [NEAR], rain(both_days("near", ("0", "0", 96), ("0", "0", 96))), NOW_EARLY)
    assert r["rule_version"] == "dry-day-v3"


# dry-day-v3: GN066's "where there is no nearby rain gauge, the three closest gauges can be triangulated".

THREE_FAR = [{"gauge_id": "g1", "label": "One", "distance_km": 12.0},
             {"gauge_id": "g2", "label": "Two", "distance_km": 15.0},
             {"gauge_id": "g3", "label": "Three", "distance_km": 18.0}]


def three_gauge_rain(totals):
    table = {}
    for g, total in zip(THREE_FAR, totals):
        table.update(both_days(g["gauge_id"], ("0", "0", 96), (total, total, 96)))
    return rain(table)


def test_nearby_gauge_is_used_alone_even_when_far_gauges_exist():
    # An overflow with a gauge inside 10 km never triangulates: GN066 triangulates only in its absence.
    r = classify_event(START, [NEAR], rain(both_days("near", ("0.1", "0.1", 96), ("0.1", "0.1", 96))),
                       NOW_EARLY, far_candidates=THREE_FAR)
    assert r["gauge_method"] == "nearest"
    assert r["gauge_id"] == "near"
    assert r["triangulated_gauges"] == ""
    assert r["verdict"] == "dry_day"


def test_no_nearby_gauge_triangulates_three_closest():
    r = classify_event(START, [], three_gauge_rain(("3", "0", "0")), NOW_EARLY, far_candidates=THREE_FAR)
    assert r["gauge_method"] == "triangulated_3"
    assert r["gauge_id"] == "g1"          # the nearest of the three is the one the evidence line links
    assert r["gauge_distance_km"] == "12.00"
    assert r["triangulated_gauges"].count("|") == 2
    # 3 mm at 12 km, 0 mm at 15 km and 0 mm at 18 km, weighted by 1/distance
    assert r["rain_window_total_mm"] == "1.216"   # 3 x (1/12) / (1/12 + 1/15 + 1/18)
    assert r["verdict"] == "not_dry"
    assert r["n_readings_present"] == "192"


def test_triangulation_needs_three_usable_gauges():
    table = {}
    table.update(both_days("g1", ("0", "0", 96), ("0", "0", 96)))
    table.update(both_days("g2", ("0", "0", 96), ("0", "0", 96)))
    r = classify_event(START, [], rain(table), NOW_EARLY, far_candidates=THREE_FAR)
    assert r["verdict"] == "no_gauge_within_10km"
    assert r["gauge_method"] == ""


def test_triangulation_skips_a_stuck_gauge():
    four = THREE_FAR + [{"gauge_id": "g4", "label": "Four", "distance_km": 19.0}]
    table = {}
    for g in four:
        table.update(both_days(g["gauge_id"], ("0", "0", 96), ("0", "0", 96)))
    r = classify_event(START, [], rain(table), NOW_EARLY, far_candidates=four,
                       gauge_unusable=lambda gid, day: "stuck" if gid == "g1" else None)
    assert r["gauge_method"] == "triangulated_3"
    assert r["gauge_id"] == "g2"
    assert "Four" in r["triangulated_gauges"]


def test_no_gauge_at_all_still_has_no_verdict():
    r = classify_event(START, [], rain({}), NOW_EARLY, far_candidates=[])
    assert r["verdict"] == "no_gauge_within_10km"


def test_geo():
    # London to Oxford is about 83 km
    assert 82 < haversine_km(51.5072, -0.1276, 51.752, -1.2577) < 84
    gauges = [{"gauge_id": "a", "latitude": "51.5500", "longitude": "-0.1276"},   # ~4.7 km north
              {"gauge_id": "b", "latitude": "51.5200", "longitude": "-0.1276"},   # ~1.4 km north
              {"gauge_id": "c", "latitude": "51.7000", "longitude": "-0.1276"}]   # ~21 km north
    near = nearest_gauges(51.5072, -0.1276, gauges)
    assert [g["gauge_id"] for g in near] == ["b", "a"]
