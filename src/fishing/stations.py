"""Registry of waters → coords, NWS zones, NOAA tide stations, NDBC buoys.

All lat/lon are decimal degrees (negative = W).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(frozen=True)
class Water:
    key: str            # canonical lower-case key
    name: str           # display name
    kind: str           # "marine" | "river" | "lake"
    lat: float
    lon: float
    nws_zone: Optional[str] = None      # marine forecast zone (e.g. PZZ135)
    tide_station: Optional[str] = None  # NOAA CO-OPS station id
    ndbc_buoys: tuple[str, ...] = ()    # nearby NDBC station ids
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Spot:
    """A named launch / fishing spot (subset of a Water)."""
    name: str
    water_key: str
    lat: float
    lon: float


# Home / cabin. Coordinates rounded to ~1 km city-level precision so the
# repository can be public without exposing exact street addresses; the
# resulting distance KPIs are still accurate within a mile.
PLACES = {
    "home":  (47.71, -122.09),   # Redmond, WA
    "cabin": (47.97, -122.45),   # Clinton, WA (Whidbey – Useless Bay)
}

WATERS: dict[str, Water] = {
    "ma8_2": Water(
        key="ma8_2",
        name="Marine Area 8-2 (Sandy Point)",
        kind="marine",
        lat=48.040, lon=-122.376,
        nws_zone="PZZ135",
        tide_station="9447659",        # Everett, across Possession Sound from Sandy Point
        ndbc_buoys=("WPOW1",),
        aliases=("ma8-2", "marine area 8-2", "area 8-2", "sandy point"),
    ),
    "ma9": Water(
        key="ma9",
        name="Marine Area 9 (Admiralty Inlet)",
        kind="marine",
        lat=47.97, lon=-122.65,
        nws_zone="PZZ133",
        tide_station="9445526",        # Hansville (north Kitsap, mouth of Admiralty Inlet)
        ndbc_buoys=("SISW1", "WPOW1"), # Smith Island + West Point (BUSW1 feed is retired)
        aliases=("marine area 9", "admiralty", "admiralty inlet"),
    ),
    "ma10": Water(
        key="ma10",
        name="Marine Area 10 (Seattle/Bremerton)",
        kind="marine",
        lat=47.62, lon=-122.45,
        nws_zone="PZZ135",
        tide_station="9447130",        # Seattle
        ndbc_buoys=("WPOW1",),         # West Point
        aliases=("marine area 10", "seattle", "bremerton", "central puget"),
    ),
    "skykomish": Water(
        key="skykomish",
        name="Skykomish River",
        kind="river",
        lat=47.8640, lon=-121.8120,    # near Sultan
        ndbc_buoys=(),
        aliases=("sky", "skykomish river"),
    ),
    "snohomish": Water(
        key="snohomish",
        name="Snohomish River",
        kind="river",
        lat=47.9130, lon=-122.0990,    # near Snohomish
        aliases=("snohomish river",),
    ),
    "snoqualmie": Water(
        key="snoqualmie",
        name="Snoqualmie River",
        kind="river",
        lat=47.6520, lon=-121.9170,    # near Carnation
        aliases=("snoq", "snoqualmie river"),
    ),
    "lake_sammamish": Water(
        key="lake_sammamish",
        name="Lake Sammamish",
        kind="lake",
        lat=47.5940, lon=-122.0850,
        aliases=("sammamish", "lake sammamish"),
    ),
}

# Useful launches / fishing spots
SPOTS: dict[str, Spot] = {
    "bush_point":     Spot("Bush Point (MA9)", "ma9",  47.9080, -122.6090),
    "point_no_point": Spot("Point No Point (MA9)", "ma9", 47.9120, -122.5260),
    "mutiny_bay":     Spot("Mutiny Bay (MA9)", "ma9", 47.9620, -122.5550),
    "double_bluff":   Spot("Double Bluff (MA9)", "ma9", 47.9700, -122.5180),
    "shilshole":      Spot("Shilshole Bay (MA10)", "ma10", 47.6790, -122.4080),
    "jefferson_head": Spot("Jefferson Head (MA10)", "ma10", 47.7460, -122.4530),
    "issaquah_ramp":  Spot("Issaquah Lake Sammamish Ramp", "lake_sammamish", 47.5510, -122.0660),
}


def resolve_water(name: str) -> Optional[Water]:
    """Case-insensitive lookup by key, name, or alias."""
    n = name.strip().lower()
    if n in WATERS:
        return WATERS[n]
    for w in WATERS.values():
        if w.name.lower() == n or n in w.aliases:
            return w
        if n in w.name.lower():
            return w
    return None


def water_to_dict(w: Water) -> dict:
    return asdict(w)
