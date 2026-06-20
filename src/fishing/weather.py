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


# --- Multi-model Open-Meteo (ECMWF + GFS + ICON ensemble) -------------------

OPEN_METEO_MODELS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless")


def open_meteo_multi(
    lat: float, lon: float, hours: int = 168,
    models: tuple[str, ...] = OPEN_METEO_MODELS,
) -> dict:
    """Open-Meteo with multiple NWP models. Wind/gust/dir averaged across models;
    temp/precip taken from the first responding model.

    Returns the same row shape as `open_meteo`, plus a `models_used` list.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
        "forecast_hours": min(hours, 168),
        "timezone": "America/Los_Angeles",
        "models": ",".join(models),
    }
    try:
        with _client() as c:
            r = c.get("https://api.open-meteo.com/v1/forecast", params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        return {"source": "Open-Meteo (multi)", "error": str(e)}

    h = data.get("hourly", {})
    times = h.get("time", [])
    rows: list[dict] = []
    models_used: list[str] = []
    import math

    # Detect which models actually returned data (suffixed keys exist).
    for m in models:
        if f"wind_speed_10m_{m}" in h:
            models_used.append(m)
    if not models_used:
        # Single-model response (Open-Meteo collapses suffixes when only one
        # model is requested or returned). Fall back to plain keys.
        models_used = list(models[:1])
        wind_keys = ["wind_speed_10m"]
        gust_keys = ["wind_gusts_10m"]
        dir_keys = ["wind_direction_10m"]
    else:
        wind_keys = [f"wind_speed_10m_{m}" for m in models_used]
        gust_keys = [f"wind_gusts_10m_{m}" for m in models_used]
        dir_keys = [f"wind_direction_10m_{m}" for m in models_used]

    temp_arr = h.get("temperature_2m") or h.get(f"temperature_2m_{models_used[0]}", [])
    precip_arr = h.get("precipitation") or h.get(f"precipitation_{models_used[0]}", [])

    def _mean(vals: list[Optional[float]]) -> Optional[float]:
        nums = [v for v in vals if v is not None]
        return sum(nums) / len(nums) if nums else None

    def _circ_mean(degs: list[Optional[float]]) -> Optional[float]:
        rads = [math.radians(d) for d in degs if d is not None]
        if not rads:
            return None
        sx = sum(math.sin(r) for r in rads) / len(rads)
        cx = sum(math.cos(r) for r in rads) / len(rads)
        return (math.degrees(math.atan2(sx, cx)) + 360.0) % 360.0

    for i, t in enumerate(times):
        winds = [h.get(k, [None])[i] for k in wind_keys]
        gusts = [h.get(k, [None])[i] for k in gust_keys]
        dirs = [h.get(k, [None])[i] for k in dir_keys]
        rows.append({
            "time": t,
            "temp_f": temp_arr[i] if i < len(temp_arr) else None,
            "precip_in": precip_arr[i] if i < len(precip_arr) else None,
            "wind_mph": _mean(winds),
            "gust_mph": _mean(gusts),
            "wind_dir_deg": _circ_mean(dirs),
        })
    return {
        "source": "Open-Meteo (multi)",
        "lat": lat, "lon": lon,
        "models_used": models_used,
        "hours": rows,
    }


# --- NWS NDFD gridded hourly forecast ---------------------------------------

def nws_gridpoints_hourly(lat: float, lon: float, hours: int = 168) -> dict:
    """Hourly wind + gust + direction expanded from the NWS gridpoints feed.

    NWS publishes wind values over variable-length validTime windows
    (PT1H..PT12H). We expand each window to per-hour rows so the data joins
    cleanly with Open-Meteo on the same hour keys (local Pacific time).
    """
    import math

    def _expand(values: list[dict]) -> dict[dt.datetime, float]:
        out: dict[dt.datetime, float] = {}
        for v in values:
            vt = v.get("validTime", "")
            if "/" not in vt:
                continue
            start_s, dur = vt.split("/", 1)
            try:
                t0 = dt.datetime.fromisoformat(start_s.replace("Z", "+00:00"))
            except ValueError:
                continue
            # Parse ISO 8601 duration (e.g. PT3H, PT1H30M, P1DT2H). We only
            # care about days/hours; minutes round to nearest hour.
            days = 0
            hours_d = 0
            mins = 0
            num = ""
            in_time = False
            for ch in dur:
                if ch == "P":
                    continue
                if ch == "T":
                    in_time = True
                    continue
                if ch.isdigit():
                    num += ch
                else:
                    n = int(num) if num else 0
                    num = ""
                    if ch == "D":
                        days = n
                    elif ch == "H" and in_time:
                        hours_d = n
                    elif ch == "M" and in_time:
                        mins = n
            total_h = days * 24 + hours_d + (1 if mins >= 30 else 0)
            total_h = max(total_h, 1)
            val = v.get("value")
            if val is None:
                continue
            for k in range(total_h):
                out[t0 + dt.timedelta(hours=k)] = float(val)
        return out

    try:
        with _client() as c:
            pt = c.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
            pt.raise_for_status()
            grid_url = pt.json()["properties"]["forecastGridData"]
            gd = c.get(grid_url)
            gd.raise_for_status()
            props = gd.json()["properties"]
    except httpx.HTTPError as e:
        return {"source": "NWS gridpoints", "error": str(e)}
    except (KeyError, ValueError) as e:
        return {"source": "NWS gridpoints", "error": f"parse: {e}"}

    wind_uom = props.get("windSpeed", {}).get("uom", "")
    gust_uom = props.get("windGust", {}).get("uom", "")
    # NWS reports wind in km/h by default. Convert to mph if needed.
    def _to_mph(v: Optional[float], uom: str) -> Optional[float]:
        if v is None:
            return None
        if "km_h-1" in uom or "km" in uom:
            return v * 0.6213711922
        if "m_s-1" in uom or uom.endswith("m/s"):
            return v * 2.2369362921
        return v  # assume mph

    wind_map = _expand(props.get("windSpeed", {}).get("values", []))
    gust_map = _expand(props.get("windGust", {}).get("values", []))
    dir_map = _expand(props.get("windDirection", {}).get("values", []))

    try:
        from zoneinfo import ZoneInfo
        local_tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        local_tz = dt.timezone(dt.timedelta(hours=-8))

    rows: list[dict] = []
    now_utc = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for k in range(hours):
        t_utc = now_utc + dt.timedelta(hours=k)
        t_local = t_utc.astimezone(local_tz)
        rows.append({
            "time": t_local.strftime("%Y-%m-%dT%H:00"),
            "wind_mph": _to_mph(wind_map.get(t_utc), wind_uom),
            "gust_mph": _to_mph(gust_map.get(t_utc), gust_uom),
            "wind_dir_deg": dir_map.get(t_utc),
        })
    return {"source": "NWS gridpoints", "lat": lat, "lon": lon, "hours": rows}


# --- Blended wind forecast --------------------------------------------------

def wind_blend(lat: float, lon: float, hours: int = 168) -> dict:
    """Wind forecast: HRRR + ECMWF 50/50 mean for 0-48h, ECMWF primary 48-168h.

    Source waterfall, applied per-hour and per-field:
      1. Mean of HRRR (NOAA 3km CONUS) + ECMWF IFS 0.25\u00b0 for hours <= 48.
         HRRR resolves Puget Sound microclimate but tends to run hot on
         sustained afternoon onshore wind; ECMWF (what Windy shows by
         default) under-resolves microclimate but is well-calibrated on the
         basin-mean. The 50/50 mean splits the difference and tracks the
         user's field reference (Windy) more closely.
      2. ECMWF IFS 0.25\u00b0 for hours 48-168.
      3. Mean of GFS + ICON (Open-Meteo) + NWS gridpoints fills any gap.
    Direction uses circular mean when falling back.

    Returns the same row shape as `open_meteo`, with `sources` listing the
    feeds that contributed and the role each played.
    """
    import math

    hrrr = open_meteo_multi(lat, lon, hours=min(hours, 48), models=("gfs_hrrr",))
    ecmwf = open_meteo_multi(lat, lon, hours=hours, models=("ecmwf_ifs025",))
    others = open_meteo_multi(lat, lon, hours=hours,
                              models=("gfs_seamless", "icon_seamless"))
    nws = nws_gridpoints_hourly(lat, lon, hours=hours)

    hrrr_hours = {r["time"]: r for r in hrrr.get("hours", [])}
    ecmwf_hours = {r["time"]: r for r in ecmwf.get("hours", [])}
    other_hours = {r["time"]: r for r in others.get("hours", [])}
    nws_hours = {r["time"]: r for r in nws.get("hours", [])}

    hrrr_ok = "error" not in hrrr and hrrr_hours
    ecmwf_ok = "error" not in ecmwf and ecmwf_hours
    fallback_sources: list[str] = []
    if "error" not in others and other_hours:
        fallback_sources.append("Open-Meteo (" + "+".join(others.get("models_used", [])) + ")")
    if "error" not in nws and nws_hours:
        fallback_sources.append("NWS gridpoints")

    sources: list[str] = []
    if hrrr_ok and ecmwf_ok:
        sources.append("HRRR + ECMWF 50/50 mean (primary 0-48 h)")
        sources.append("ECMWF IFS 0.25\u00b0 (primary 48-168 h)")
    elif hrrr_ok:
        sources.append("NOAA HRRR 3 km (primary 0-48 h)")
    elif ecmwf_ok:
        sources.append("ECMWF IFS 0.25\u00b0 (primary)")
    sources.extend(f"{s} (fallback)" for s in fallback_sources)

    def _mean(vals: list[Optional[float]]) -> Optional[float]:
        nums = [v for v in vals if v is not None]
        return sum(nums) / len(nums) if nums else None

    def _circ_mean(degs: list[Optional[float]]) -> Optional[float]:
        rads = [math.radians(d) for d in degs if d is not None]
        if not rads:
            return None
        sx = sum(math.sin(r) for r in rads) / len(rads)
        cx = sum(math.cos(r) for r in rads) / len(rads)
        return (math.degrees(math.atan2(sx, cx)) + 360.0) % 360.0

    # If every source failed, fall through to single-model Open-Meteo so the
    # report still renders rather than throwing.
    if not (hrrr_ok or ecmwf_ok or fallback_sources):
        return open_meteo(lat, lon, hours=hours)

    # Determine "now" so we can decide HRRR-eligible hours (<=48h ahead). Time
    # keys are local Pacific naive strings ("YYYY-MM-DDTHH:00"); compare in
    # local naive time.
    try:
        from zoneinfo import ZoneInfo
        now_local = dt.datetime.now(ZoneInfo("America/Los_Angeles")).replace(
            tzinfo=None, minute=0, second=0, microsecond=0)
    except Exception:
        now_local = dt.datetime.now().replace(minute=0, second=0, microsecond=0)

    def _pick(field: str, h_r: dict, e_r: dict, o_r: dict, n_r: dict,
              hours_ahead: float, circ: bool = False) -> Optional[float]:
        # 0-48 h: prefer the mean of HRRR + ECMWF (matches Windy's ECMWF view
        # while keeping HRRR's microclimate signal). Fall back to whichever
        # single primary is available.
        if hours_ahead <= 48 and hrrr_ok and ecmwf_ok:
            hv = h_r.get(field)
            ev = e_r.get(field)
            if hv is not None and ev is not None:
                return _circ_mean([hv, ev]) if circ else (hv + ev) / 2.0
            if hv is not None:
                return hv
            if ev is not None:
                return ev
        if hrrr_ok and hours_ahead <= 48 and h_r.get(field) is not None:
            return h_r[field]
        if ecmwf_ok and e_r.get(field) is not None:
            return e_r[field]
        vals = [o_r.get(field), n_r.get(field)]
        return _circ_mean(vals) if circ else _mean(vals)

    keys = sorted(set(hrrr_hours) | set(ecmwf_hours) | set(other_hours) | set(nws_hours))
    rows: list[dict] = []
    for k in keys:
        h_r = hrrr_hours.get(k, {})
        e_r = ecmwf_hours.get(k, {})
        o_r = other_hours.get(k, {})
        n_r = nws_hours.get(k, {})
        try:
            ahead = (dt.datetime.fromisoformat(k) - now_local).total_seconds() / 3600.0
        except ValueError:
            ahead = 0.0
        rows.append({
            "time": k,
            # Temp/precip: HRRR best near-term, ECMWF beyond, else Open-Meteo blend.
            "temp_f": _pick("temp_f", h_r, e_r, o_r, n_r, ahead),
            "precip_in": _pick("precip_in", h_r, e_r, o_r, n_r, ahead),
            "wind_mph": _pick("wind_mph", h_r, e_r, o_r, n_r, ahead),
            "gust_mph": _pick("gust_mph", h_r, e_r, o_r, n_r, ahead),
            "wind_dir_deg": _pick("wind_dir_deg", h_r, e_r, o_r, n_r, ahead, circ=True),
        })

    primary_parts = []
    if hrrr_ok and ecmwf_ok:
        primary_parts.append("HRRR+ECMWF mean 0-48h")
        primary_parts.append("ECMWF 48-168h")
    elif hrrr_ok:
        primary_parts.append("HRRR 0-48h")
    elif ecmwf_ok:
        primary_parts.append("ECMWF")
    primary_label = " + ".join(primary_parts) if primary_parts else "fallback only"

    return {
        "source": f"{primary_label}" + (f" + {' + '.join(fallback_sources)}" if fallback_sources else ""),
        "lat": lat, "lon": lon,
        "sources": sources,
        "primary": primary_label,
        "hours": rows,
    }
