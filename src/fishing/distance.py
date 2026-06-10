"""Great-circle distance helpers and named-place resolution."""
from __future__ import annotations

import math
from typing import Optional

from .stations import PLACES, SPOTS, WATERS, resolve_water


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def resolve_point(name: str) -> Optional[tuple[float, float, str]]:
    """Resolve a name to (lat, lon, display_name). Checks places, spots, waters."""
    n = name.strip().lower().replace(" ", "_")
    if n in PLACES:
        lat, lon = PLACES[n]
        return lat, lon, n
    if n in SPOTS:
        s = SPOTS[n]
        return s.lat, s.lon, s.name
    w = resolve_water(name)
    if w:
        return w.lat, w.lon, w.name
    return None


def distance(from_name: str, to_name: str) -> dict:
    a = resolve_point(from_name)
    b = resolve_point(to_name)
    if not a:
        return {"error": f"Unknown location: {from_name!r}"}
    if not b:
        return {"error": f"Unknown location: {to_name!r}"}
    km = haversine_km(a[0], a[1], b[0], b[1])
    return {
        "from": a[2], "to": b[2],
        "km": round(km, 1),
        "miles": round(km * 0.621371, 1),
        "note": "Straight-line (great-circle) distance — not driving distance.",
    }
