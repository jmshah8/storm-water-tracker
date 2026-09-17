"""Distances on WGS84 coordinates."""
import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_gauges(lat, lon, gauges, max_km=10.0):
    """Gauges (dicts with latitude/longitude) within max_km, nearest first, each with distance_km added."""
    # A 1-degree latitude band is ~111 km; skip gauges that cannot be within max_km before the exact distance.
    lat_margin = max_km / 110.0
    lon_margin = max_km / (110.0 * max(math.cos(math.radians(lat)), 0.01))
    out = []
    for g in gauges:
        glat, glon = float(g["latitude"]), float(g["longitude"])
        if abs(glat - lat) > lat_margin or abs(glon - lon) > lon_margin:
            continue
        d = haversine_km(lat, lon, glat, glon)
        if d <= max_km:
            out.append(dict(g, distance_km=d))
    return sorted(out, key=lambda g: (g["distance_km"], g["gauge_id"]))
