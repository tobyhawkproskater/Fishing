"""MCP server exposing the fishing knowledge base + live weather/marine tools.

Run with:
    python -m fishing.server

Or register in Claude Desktop / Claude Code via stdio.
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import kb
from .distance import distance as _distance
from .report import format_report_markdown, generate_report as _generate_report
from .stations import SPOTS, WATERS, resolve_water, water_to_dict
from .weather import (
    ndbc_latest,
    noaa_tides,
    nws_forecast,
    nws_marine_forecast,
    open_meteo,
)

mcp = FastMCP("mcp-fishing")


# --- Knowledge base tools ----------------------------------------------------

@mcp.tool()
def list_waters() -> list[dict]:
    """List every water (marine area, river, lake) known to the system."""
    return [water_to_dict(w) for w in WATERS.values()]


@mcp.tool()
def list_spots() -> list[dict]:
    """List named launch ramps and fishing spots."""
    return [{"key": k, **s.__dict__} for k, s in SPOTS.items()]


@mcp.tool()
def get_places() -> list[dict]:
    """Home and cabin addresses from Key facts.docx."""
    return kb.places()


@mcp.tool()
def get_boat() -> Optional[dict]:
    """Boat specs from Key facts.docx."""
    return kb.boat()


@mcp.tool()
def get_regulations(water: str, source: str = "both") -> dict:
    """Search current + proposed fishing regulations for a water.

    `source`: "current", "proposed", or "both".
    """
    return kb.regulations(water, source)


@mcp.tool()
def get_gear(use: Optional[str] = None) -> list[dict]:
    """Gear inventory. Optional filter on the Use column."""
    return kb.gear(use)


@mcp.tool()
def get_maps(water: Optional[str] = None, query: Optional[str] = None,
             kind: Optional[str] = None) -> list[dict]:
    """Cross-reference fishing-map PDFs (John's Sporting Goods, etc.).

    `water`: filter by a water key / spot / place tag (e.g. "ma9", "snohomish",
    "mukilteo"). `query`: free-text match on title/filename/extracted text.
    `kind`: filter by document type ("map", "guide", "newsletter", "coupon").
    Each map includes its `source_url`, `local_path`, and cross-reference tags.
    """
    return kb.maps(water=water, query=query, kind=kind)


# --- Distance ---------------------------------------------------------------

@mcp.tool()
def get_distance(from_place: str, to_place: str) -> dict:
    """Great-circle distance between two known names (home, cabin, water key, spot key)."""
    return _distance(from_place, to_place)


# --- Weather / marine / tides ------------------------------------------------

@mcp.tool()
def get_forecast(water: str, hourly: bool = False) -> dict:
    """NOAA NWS forecast for the water's lat/lon."""
    w = resolve_water(water)
    if not w:
        return {"error": f"Unknown water: {water!r}"}
    return nws_forecast(w.lat, w.lon, hourly=hourly)


@mcp.tool()
def get_marine_forecast(water: str) -> dict:
    """NWS marine zone forecast (text) for a marine water (MA9, MA10)."""
    w = resolve_water(water)
    if not w or w.kind != "marine":
        return {"error": f"{water!r} is not a marine water"}
    if not w.nws_zone:
        return {"error": f"No NWS marine zone registered for {w.name}"}
    return nws_marine_forecast(w.nws_zone)


@mcp.tool()
def get_tides(water: str, date: Optional[str] = None, days: int = 2) -> dict:
    """NOAA tide predictions (high/low) for the marine water's tide station."""
    w = resolve_water(water)
    if not w or not w.tide_station:
        return {"error": f"No tide station for {water!r}"}
    return noaa_tides(w.tide_station, date=date, days=days)


@mcp.tool()
def get_buoys(water: str) -> list[dict]:
    """Latest NDBC buoy observations near a water."""
    w = resolve_water(water)
    if not w or not w.ndbc_buoys:
        return [{"error": f"No buoys registered for {water!r}"}]
    return [ndbc_latest(b) for b in w.ndbc_buoys]


@mcp.tool()
def get_wind(water: str, hours: int = 48) -> dict:
    """Open-Meteo hourly wind/gust/temp/precip for the water's lat/lon."""
    w = resolve_water(water)
    if not w:
        return {"error": f"Unknown water: {water!r}"}
    return open_meteo(w.lat, w.lon, hours=hours)


# --- Composite report --------------------------------------------------------

@mcp.tool()
def generate_report(water: str, date: Optional[str] = None,
                    from_place: str = "home", as_markdown: bool = True) -> dict:
    """One-shot fishing report: rules + forecast + wind + (marine: tides + buoys).

    Returns a dict with `data` (structured) and optional `markdown` (human-readable).
    """
    rep = _generate_report(water, date=date, from_place=from_place)
    out = {"data": rep}
    if as_markdown:
        out["markdown"] = format_report_markdown(rep)
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
