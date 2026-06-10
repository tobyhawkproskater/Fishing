"""Weather, marine forecast, tide, and buoy clients.

All sources are free and key-less:
- NOAA NWS API (api.weather.gov) — land + marine zone forecasts
- NOAA CO-OPS (api.tidesandcurrents.noaa.gov) — tide predictions
- NDBC (ndbc.noaa.gov) — buoy observations
- Open-Meteo (api.open-meteo.com) — hourly wind/temp fallback
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

UA = "mcp-fishing/0.2 (personal fishing report; contact: local)"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA, "Accept": "application/json"})


# --- NOAA NWS land forecast --------------------------------------------------

def nws_forecast(lat: float, lon: float, hourly: bool = False) -> dict:
    """Get NWS forecast for a lat/lon. Two-step: /points → /forecast(/hourly)."""
    try:
        with _client() as c:
            pt = c.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
            pt.raise_for_status()
            props = pt.json()["properties"]
            url = props["forecastHourly"] if hourly else props["forecast"]
            fc = c.get(url)
            fc.raise_for_status()
            periods = fc.json()["properties"]["periods"]
        return {
            "source": "NOAA NWS",
            "office": props.get("gridId"),
            "city": props.get("relativeLocation", {}).get("properties", {}).get("city"),
            "periods": periods[:24] if hourly else periods[:7],
        }
    except httpx.HTTPError as e:
        return {"source": "NOAA NWS", "error": str(e)}


# --- NOAA NWS marine zone ---------------------------------------------------

def nws_marine_forecast(zone: str) -> dict:
    """Plain-text marine forecast for a zone like 'PZZ133' or 'PZZ135'."""
    url = f"https://tgftp.nws.noaa.gov/data/forecasts/marine/coastal/pz/{zone.lower()}.txt"
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
        return {"source": "NOAA NWS Marine", "zone": zone.upper(), "text": r.text}
    except httpx.HTTPError as e:
        return {"source": "NOAA NWS Marine", "zone": zone.upper(), "error": str(e)}


# --- NOAA CO-OPS tides ------------------------------------------------------

def noaa_tides(station: str, date: Optional[str] = None, days: int = 2) -> dict:
    """High/low tide predictions for a station id (e.g. '9447130' = Seattle)."""
    begin = dt.date.fromisoformat(date) if date else dt.date.today()
    end = begin + dt.timedelta(days=days)
    params = {
        "product": "predictions",
        "application": "mcp-fishing",
        "datum": "MLLW",
        "station": station,
        "time_zone": "lst_ldt",
        "units": "english",
        "interval": "hilo",
        "format": "json",
        "begin_date": begin.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
    }
    try:
        with _client() as c:
            r = c.get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", params=params)
            r.raise_for_status()
            data = r.json()
        return {
            "source": "NOAA CO-OPS",
            "station": station,
            "begin": str(begin), "end": str(end),
            "tides": data.get("predictions", []),
        }
    except httpx.HTTPError as e:
        return {"source": "NOAA CO-OPS", "station": station, "error": str(e)}


# --- NDBC buoy observations -------------------------------------------------

def ndbc_latest(station: str) -> dict:
    """Most recent observation row from NDBC realtime2 feed."""
    url = f"https://www.ndbc.noaa.gov/data/realtime2/{station.upper()}.txt"
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
        lines = [ln for ln in r.text.splitlines() if ln.strip()]
        if len(lines) < 3:
            return {"source": "NDBC", "station": station, "error": "no data"}
        # First two lines are headers (#YY MM DD ... and #yr mo dy ...)
        headers = lines[0].lstrip("#").split()
        latest = lines[2].split()
        rec = dict(zip(headers, latest))
        ts = (
            f"{rec.get('YY')}-{rec.get('MM')}-{rec.get('DD')} "
            f"{rec.get('hh')}:{rec.get('mm')} UTC"
        )
        return {
            "source": "NDBC",
            "station": station.upper(),
            "observed_utc": ts,
            "wind_dir_deg": _f(rec.get("WDIR")),
            "wind_speed_mps": _f(rec.get("WSPD")),
            "wind_gust_mps": _f(rec.get("GST")),
            "wave_height_m": _f(rec.get("WVHT")),
            "air_temp_c": _f(rec.get("ATMP")),
            "water_temp_c": _f(rec.get("WTMP")),
            "pressure_hpa": _f(rec.get("PRES")),
        }
    except httpx.HTTPError as e:
        return {"source": "NDBC", "station": station, "error": str(e)}


def _f(v):
    if v is None or v in ("MM", "99.0", "999.0", "9999.0"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


# --- Open-Meteo wind --------------------------------------------------------

def open_meteo(lat: float, lon: float, hours: int = 48) -> dict:
    """Hourly wind + temp from Open-Meteo (no key required)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "forecast_hours": min(hours, 168),
        "timezone": "America/Los_Angeles",
    }
    try:
        with _client() as c:
            r = c.get("https://api.open-meteo.com/v1/forecast", params=params)
            r.raise_for_status()
            data = r.json()
        h = data.get("hourly", {})
        rows = []
        times = h.get("time", [])
        for i, t in enumerate(times):
            rows.append({
                "time": t,
                "temp_f": h.get("temperature_2m", [None])[i],
                "precip_in": h.get("precipitation", [None])[i],
                "wind_mph": h.get("wind_speed_10m", [None])[i],
                "gust_mph": h.get("wind_gusts_10m", [None])[i],
                "wind_dir_deg": h.get("wind_direction_10m", [None])[i],
            })
        return {"source": "Open-Meteo", "lat": lat, "lon": lon, "hours": rows}
    except httpx.HTTPError as e:
        return {"source": "Open-Meteo", "error": str(e)}
