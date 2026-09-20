"""The dry-day rule, dry-day-v3 (01_SPEC.md §5.2–5.3). Pure function: no I/O.

EA, 28 Aug 2024: "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as
no rainfall above 0.25mm on that day and the preceding 24 hours."

dry-day-v2 (18 Sep 2026) changes one thing from v1: a gauge that has stopped reporting rain is skipped when
choosing which gauge to use, exactly as a gauge with too few readings is. A stuck gauge reads 0.00 mm however
hard it rains, which would otherwise produce a dry day flag carrying the strongest possible evidence line.
Deciding whether a gauge is stuck is the caller's job (see `gauge_unusable`); the rule itself is unchanged.

dry-day-v3 (20 Sep 2026) adds the one rainfall step a regulator has actually published. Natural Resources
Wales, GN066 v1.0 (26 Oct 2023), test 1 "Dry day discharges": "Use rain gauge data that is the most
representative for the SO. Where there is no nearby rain gauge, the three closest gauges can be triangulated."
So when no gauge lies within 10 km, the three closest usable gauges are triangulated by inverse distance
instead of the event being left without a verdict. Nothing else moves: the 0.25 mm threshold, the 48-hour
window and the completeness bar are all unchanged, and an overflow that does have a nearby gauge still uses
that gauge alone.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

RULE_VERSION = "dry-day-v3"
TRIANGULATE_GAUGES = 3             # GN066: "the three closest gauges can be triangulated"
MIN_WEIGHT_DISTANCE_KM = Decimal("0.1")   # a gauge on top of the overflow must not carry infinite weight
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


def _window_rain(gauge_id, rain_lookup, prev_day, day):
    """The 48-hour window for one gauge, or None when it does not have enough readings."""
    prev, same = rain_lookup(gauge_id, prev_day), rain_lookup(gauge_id, day)
    n = sum(int(r["n_readings"]) for r in (prev, same) if r)
    if n < READINGS_REQUIRED:
        return None
    maxima = [Decimal(str(r["max15_mm"])) for r in (prev, same) if r["max15_mm"] not in ("", None)]
    return {"prev_total": Decimal(str(prev["total_mm"])), "day_total": Decimal(str(same["total_mm"])),
            "max15": max(maxima) if maxima else None, "n_readings": n}


def _triangulate(gauges, rain_lookup, prev_day, day, gauge_unusable):
    """GN066's three closest gauges, weighted by inverse distance.

    Returns (rain, gauges_used) where rain has the same shape as _window_rain, or (None, []) when three
    usable gauges are not available. Weighting is 1/distance with distances below 100 m treated as 100 m,
    so a gauge beside the overflow dominates but never divides by zero.
    """
    used = []
    for g in gauges:
        if gauge_unusable and gauge_unusable(g["gauge_id"], day):
            continue
        rain = _window_rain(g["gauge_id"], rain_lookup, prev_day, day)
        if rain is None:
            continue
        used.append((g, rain))
        if len(used) == TRIANGULATE_GAUGES:
            break
    if len(used) < TRIANGULATE_GAUGES:
        return None, []

    weights = [Decimal(1) / max(Decimal(str(g["distance_km"])), MIN_WEIGHT_DISTANCE_KM) for g, _ in used]
    total_weight = sum(weights)

    def weighted(key):
        return (sum(w * r[key] for w, (_, r) in zip(weights, used)) / total_weight).quantize(Decimal("0.001"))

    maxima = [r["max15"] for _, r in used if r["max15"] is not None]
    return {"prev_total": weighted("prev_total"), "day_total": weighted("day_total"),
            # the wettest quarter-hour any of the three saw: a maximum is not an average of maxima
            "max15": max(maxima) if maxima else None,
            "n_readings": min(r["n_readings"] for _, r in used)}, used


def classify_event(start_utc, gauge_candidates, rain_lookup, now_utc, rule_version=RULE_VERSION,
                   gauge_unusable=None, far_candidates=None):
    """Classify one event by its start.

    gauge_candidates: gauges within 10 km, nearest first, each {gauge_id, label, distance_km}.
    far_candidates: gauges out to the triangulation radius, nearest first, used only when `gauge_candidates`
        is empty — GN066's "where there is no nearby rain gauge, the three closest gauges can be triangulated".
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
        "gauge_method": "", "triangulated_gauges": "",
        "rain_day_mm": "", "rain_prev24_mm": "", "rain_window_total_mm": "", "rain_window_max15_mm": "",
        "n_readings_present": "", "n_readings_expected": str(READINGS_EXPECTED),
        "n_gauges_skipped_stuck": "0",
        "verdict": "", "verdict_basis": "total", "rule_version": rule_version, "is_final": "false",
    }
    prev_day = (day - timedelta(days=1)).isoformat()
    today = day.isoformat()

    def decide(rain, gauge, method, used=()):
        total = rain["prev_total"] + rain["day_total"]
        n = rain["n_readings"]
        is_final = (n == READINGS_EXPECTED and now >= window_end + PENDING_PERIOD) or now >= window_end + FINAL_AFTER
        result.update(
            gauge_id=gauge["gauge_id"], gauge_label=gauge["label"],
            gauge_distance_km=f"{gauge['distance_km']:.2f}", gauge_method=method,
            triangulated_gauges="|".join(
                f"{g['label']} ({g['gauge_id']}) {g['distance_km']:.2f} km "
                f"{_text(r['prev_total'] + r['day_total'])} mm" for g, r in used),
            rain_day_mm=_text(rain["day_total"]), rain_prev24_mm=_text(rain["prev_total"]),
            rain_window_total_mm=_text(total),
            rain_window_max15_mm=_text(rain["max15"]) if rain["max15"] is not None else "",
            n_readings_present=str(n),
            verdict="dry_day" if total <= DRY_THRESHOLD_MM else "not_dry",
            is_final="true" if is_final else "false")
        return result

    if not gauge_candidates:
        # GN066: no nearby rain gauge, so triangulate the three closest instead of giving up.
        rain, used = _triangulate(far_candidates or [], rain_lookup, prev_day, today, gauge_unusable)
        if rain is None:
            result.update(verdict="no_gauge_within_10km", is_final="true")
            return result
        return decide(rain, used[0][0], "triangulated_3", used)

    skipped = 0
    for gauge in gauge_candidates:
        if gauge_unusable and gauge_unusable(gauge["gauge_id"], today):
            skipped += 1
            result["n_gauges_skipped_stuck"] = str(skipped)
            continue
        rain = _window_rain(gauge["gauge_id"], rain_lookup, prev_day, today)
        if rain is None:
            continue
        return decide(rain, gauge, "nearest")

    result["verdict"] = "pending_rain_data" if now < window_end + PENDING_PERIOD else "insufficient_readings"
    return result
