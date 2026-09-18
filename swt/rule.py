"""The dry-day rule, dry-day-v2 (01_SPEC.md §5.2–5.3). Pure function: no I/O.

EA, 28 Aug 2024: "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as
no rainfall above 0.25mm on that day and the preceding 24 hours."

dry-day-v2 (18 Sep 2026) changes one thing from v1: a gauge that has stopped reporting rain is skipped when
choosing which gauge to use, exactly as a gauge with too few readings is. A stuck gauge reads 0.00 mm however
hard it rains, which would otherwise produce a dry day flag carrying the strongest possible evidence line.
Deciding whether a gauge is stuck is the caller's job (see `gauge_unusable`); the rule itself is unchanged.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

RULE_VERSION = "dry-day-v2"
DRY_THRESHOLD_MM = Decimal("0.25")
READINGS_EXPECTED = 192
READINGS_REQUIRED = 176
PENDING_PERIOD = timedelta(hours=72)
FINAL_AFTER = timedelta(days=14)

ISO = "%Y-%m-%dT%H:%M:%SZ"


def _parse(iso):
    return datetime.strptime(iso, ISO).replace(tzinfo=timezone.utc)


def _text(d):
    return format(d.normalize(), "f")


def classify_event(start_utc, gauge_candidates, rain_lookup, now_utc, rule_version=RULE_VERSION,
                   gauge_unusable=None):
    """Classify one event by its start.

    gauge_candidates: gauges within 10 km, nearest first, each {gauge_id, label, distance_km}.
    rain_lookup(gauge_id, "YYYY-MM-DD") -> {total_mm, max15_mm, n_readings} or None.
    gauge_unusable(gauge_id, "YYYY-MM-DD") -> a reason string for a gauge that has stopped reporting rain,
        or None when the gauge can be used (dry-day-v2).
    """
    start = _parse(start_utc)
    day = start.date()
    window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(days=1)
    window_end = window_start + timedelta(days=2)
    now = _parse(now_utc)

    result = {
        "day_utc": day.isoformat(),
        "window_start_utc": window_start.strftime(ISO),
        "window_end_utc": window_end.strftime(ISO),
        "gauge_id": "", "gauge_label": "", "gauge_distance_km": "",
        "rain_day_mm": "", "rain_prev24_mm": "", "rain_window_total_mm": "", "rain_window_max15_mm": "",
        "n_readings_present": "", "n_readings_expected": str(READINGS_EXPECTED),
        "n_gauges_skipped_stuck": "0",
        "verdict": "", "verdict_basis": "total", "rule_version": rule_version, "is_final": "false",
    }

    if not gauge_candidates:
        result.update(verdict="no_gauge_within_10km", is_final="true")
        return result

    prev_day = (day - timedelta(days=1)).isoformat()
    skipped = 0
    for gauge in gauge_candidates:
        if gauge_unusable and gauge_unusable(gauge["gauge_id"], day.isoformat()):
            skipped += 1
            result["n_gauges_skipped_stuck"] = str(skipped)
            continue
        prev, same = rain_lookup(gauge["gauge_id"], prev_day), rain_lookup(gauge["gauge_id"], day.isoformat())
        n = sum(int(r["n_readings"]) for r in (prev, same) if r)
        if n < READINGS_REQUIRED:
            continue
        prev_total, day_total = Decimal(str(prev["total_mm"])), Decimal(str(same["total_mm"]))
        total = prev_total + day_total
        maxima = [Decimal(str(r["max15_mm"])) for r in (prev, same) if r["max15_mm"] not in ("", None)]
        verdict = "dry_day" if total <= DRY_THRESHOLD_MM else "not_dry"
        is_final = (n == READINGS_EXPECTED and now >= window_end + PENDING_PERIOD) or now >= window_end + FINAL_AFTER
        result.update(
            gauge_id=gauge["gauge_id"], gauge_label=gauge["label"], gauge_distance_km=f"{gauge['distance_km']:.2f}",
            rain_day_mm=_text(day_total), rain_prev24_mm=_text(prev_total), rain_window_total_mm=_text(total),
            rain_window_max15_mm=_text(max(maxima)) if maxima else "", n_readings_present=str(n),
            verdict=verdict, is_final="true" if is_final else "false")
        return result

    result["verdict"] = "pending_rain_data" if now < window_end + PENDING_PERIOD else "insufficient_readings"
    return result
