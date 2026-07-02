"""MA9-only 7-day report with a tide x weather fishability heatmap.

Scoring model (per hour, nautical dawn - nautical dusk, per water lat/lon):
    score = wind_score * precip_score * (0.4 + 0.6 * tide_score)
where
    tide_score   = 1.0 at slack (nearest H/L), linearly to 0 at the edge of
                   the per-side half-window (sized by the adjacent swing).
    wind_score   = min of two tier scores (the worse wins, so a calm-but-
                   gusty hour can't be mislabeled Prime):
                     sustained:  <10 / <15 / <25 / >=25 mph -> 1.0/0.7/0.3/0.0
                     gust:       <15 / <20 / <25 / >=30 mph -> 1.0/0.7/0.3/0.0
                   Sustained ceiling matches `_classify`'s GREEN cutoff so
                   a PRIME heatmap cell never sits above a YELLOW/RED tide
                   curve. Gust thresholds run higher because gust naturally
                   exceeds sustained; a brief puff to 14 mph over glass water
                   still scores 1.0.
    precip_score = 1.0 if <0.05 in/h, else 0.5

Tide is a soft modifier (0.4x .. 1.0x), not a hard multiplier: a glass-calm
mid-cycle hour earns ~0.4 (Marginal) so big-swing days don't read as
uniformly Good. Slack at the same conditions earns 1.0 (Prime).

In addition, each hour gets a *category* (used to highlight ideal slack
windows on the per-day tide wave):
    GREEN   slack window with wind < 10 mph AND gust < 20 mph
    YELLOW  slack window, wind 10-15 mph (gust < 20 mph)
    RED     slack window, but wind > 15 mph OR gust >= 20 mph
    OFF     outside the slack window

A separate per-day wind badge (GLASS / BREEZY / WINDY) summarizes the
daylight wind character so glass-calm days are obvious at a glance.

Slack is approximated by the nearest predicted high/low at Hansville
(NOAA CO-OPS 9445526), at the north tip of Kitsap Peninsula at the mouth
of Admiralty Inlet. The fishable half-window around each slack is sized
per side by the adjacent tide swing (see `_slack_half_windows`).

Run:
    python -m fishing.html_report_ma9
    python -m fishing.html_report_ma9 path\\out.html
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import ROOT, kb
from .distance import haversine_km
from .stations import PLACES, WATERS
from .weather import ndbc_latest, noaa_tides, nws_marine_forecast, open_meteo, wind_blend
from .html_loadout import LOADOUT_CSS, render_nav
from .html_report import (
    CSS, _deg_to_compass, _fmt, _h, _kind_tag, _render_buoy,
    _render_rules, _render_tides, _group_tides_by_day, _wind_cell_class,
)
from .sun import sun_times as _sun_times, hour_of_day as _hod, fmt_clock as _sun_clock

DAYS = 7
# Grid spans nautical dawn through nautical dusk at PNW latitudes year-round
# (summer nautical dawn ~3:30 AM, dusk ~10:55 PM). Cells outside a given day's
# actual first/last-light window are visually dimmed in the heatmap.
HOUR_START = 3   # 3 AM PT
HOUR_END = 22    # 10 PM PT inclusive label
WATER_KEY = "ma9"


# --- scoring -----------------------------------------------------------------
#
# Two scores per hour:
#   1. Continuous fishability `score` in [0..1]
#        = wind * precip * (0.4 + 0.6 * tide)
#      Wind/precip are hard multipliers (zero them and the hour is dead).
#      Tide is a soft modifier in [0.4 .. 1.0] -- flat-calm mid-cycle scores
#      0.4 (Marginal), slack with the same wind scores 1.0 (Prime).
#   2. Category in {GREEN, YELLOW, RED, OFF} -- slack window + wind tiers.
#      Used only to highlight slack segments on the per-day tide wave SVG.
#
# A separate day-level wind badge (GLASS / BREEZY / WINDY) signals whether
# the whole day is fishable regardless of tide phase.

CAT_GREEN, CAT_YELLOW, CAT_RED, CAT_OFF = "green", "yellow", "red", "off"


def _nearest_tide(hour_iso: str, tide_events: list[dict]) -> tuple[Optional[float], Optional[dict]]:
    """Return (minutes_from_hour_block_to_nearest_event, nearest_event).

    The cell is treated as the 60-minute block it represents
    ([hour, hour + 60 min)). A slack landing anywhere inside that block is
    0 minutes away; outside it, distance is measured to the nearest block
    edge. This keeps a slack at, say, 6:42 from being penalized just for not
    falling exactly on the clock hour -- the hour that contains slack gets
    full tide credit.
    """
    if not tide_events:
        return None, None
    start = dt.datetime.fromisoformat(hour_iso)
    end = start + dt.timedelta(minutes=60)
    best_dt = None
    best_ev = None
    for ev in tide_events:
        try:
            t = dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M")
        except Exception:
            continue
        if t < start:
            d = (start - t).total_seconds() / 60.0
        elif t > end:
            d = (t - end).total_seconds() / 60.0
        else:
            d = 0.0
        if best_dt is None or d < best_dt:
            best_dt = d
            best_ev = ev
    return best_dt, best_ev


def _window_for_swing(rng_ft: float) -> float:
    """Map swing magnitude (ft) to the half-window (min) for tide_score decay."""
    if rng_ft < 3.0:
        return 360.0
    if rng_ft < 6.0:
        return 180.0
    if rng_ft < 9.0:
        return 90.0
    return 45.0


def _slack_half_windows(ev: Optional[dict], tide_events: list[dict]) -> tuple[float, float]:
    """Return (before_window, after_window) in minutes around a slack event.

    Each side is sized independently by ITS adjacent swing -- the incoming
    swing (prev -> ev) sets how long *before* slack stays fishable, the
    outgoing swing (ev -> next) sets how long *after* slack stays fishable.
    This captures asymmetric tides: a 13 ft drop into slack followed by a
    4 ft rise out gives a tight ±45 min before-window but a generous ±6 hr
    after-window.

    Thresholds (per side): <3 ft -> 360 min, 3-6 -> 180, 6-9 -> 90, >=9 -> 45.
    Falls back to 60/60 if metadata can't be parsed, and mirrors a single
    neighbor when ev is at the edge of the event list.
    """
    if not ev:
        return 60.0, 60.0
    try:
        ev_t = dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M")
        ev_h = float(ev["v"])
    except (KeyError, TypeError, ValueError):
        return 60.0, 60.0
    parsed: list[tuple[dt.datetime, float]] = []
    for x in tide_events:
        try:
            parsed.append((dt.datetime.strptime(x["t"], "%Y-%m-%d %H:%M"), float(x["v"])))
        except (KeyError, TypeError, ValueError):
            continue
    parsed.sort()
    prev_h = next_h = None
    for t, h in parsed:
        if t < ev_t:
            prev_h = h
        elif t > ev_t and next_h is None:
            next_h = h
            break
    before = _window_for_swing(abs(ev_h - prev_h)) if prev_h is not None else None
    after = _window_for_swing(abs(next_h - ev_h)) if next_h is not None else None
    if before is None and after is None:
        return 60.0, 60.0
    if before is None:
        before = after
    if after is None:
        after = before
    return before, after


def _tide_score(minutes_to_slack: Optional[float], half_window_min: float = 60.0) -> float:
    """Linear decay from 1.0 at slack to 0.0 at +/- `half_window_min` minutes."""
    if minutes_to_slack is None or half_window_min <= 0:
        return 0.0
    if minutes_to_slack >= half_window_min:
        return 0.0
    return max(0.0, 1.0 - minutes_to_slack / half_window_min)


def _wind_score(wind_mph: Optional[float], gust_mph: Optional[float]) -> float:
    # Score sustained and gust separately, take the worse so a calm-but-gusty
    # hour (e.g. wind 4, gust 25) can't be mislabeled PRIME. Thresholds chosen
    # to align with `_classify` (heatmap PRIME requires the same wind/gust
    # ceiling as a GREEN tide-curve segment).
    #   Sustained:  <10 / <15 / <25 / >=25 mph -> 1.0 / 0.7 / 0.3 / 0.0
    #   Gust:       <15 / <20 / <25 / >=30 mph -> 1.0 / 0.7 / 0.3 / 0.0
    # Round to whole mph FIRST so the score matches the displayed gust value
    # (a gust of 14.6 is shown as "15" in tooltips and must score as 15, not
    # sneak under the <15 threshold as 14.6).
    w_raw = wind_mph if wind_mph is not None else 0.0
    g_raw = gust_mph if gust_mph is not None else w_raw
    w = int(round(w_raw))
    g = int(round(g_raw))
    if w < 10:   sw = 1.0
    elif w < 15: sw = 0.7
    elif w < 25: sw = 0.3
    else:        sw = 0.0
    if g < 15:   gw = 1.0
    elif g < 20: gw = 0.7
    elif g < 25: gw = 0.3
    else:        gw = 0.0
    return min(sw, gw)


def _precip_score(precip_in: Optional[float]) -> float:
    p = precip_in if precip_in is not None else 0.0
    return 1.0 if p < 0.05 else 0.5


def _window_heart(
    lo: float, hi: float, day_date: dt.date,
    cells: list[dict], tide_events: list[dict],
) -> Optional[tuple[dt.datetime, float, dict]]:
    """Return the score-weighted center-of-mass minute of a Prime/Good window.

    The fishable window is asymmetric (wide incoming lead-in, sharp outgoing
    drop), so the single peak minute sits near the trailing edge at slack.
    Scanning the window [lo, hi] (fractional hours) at 1-minute resolution and
    taking the centroid of the score curve pulls the marker into the heart of
    the bite — earlier than slack, where the good fishing is actually
    sustained. Slack distance is measured continuously (not quantized to the
    60-minute cell block) and wind/precip come from the hourly cell. Returns
    (minute, score_at_minute, hour_cell) or None.
    """
    parsed: list[tuple[dt.datetime, dict]] = []
    for ev in tide_events:
        try:
            parsed.append((dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M"), ev))
        except (KeyError, ValueError, TypeError):
            continue
    if not parsed:
        return None
    h0 = max(0, int(math.floor(lo)))
    h1 = min(23, int(math.ceil(hi)))
    samples: list[tuple[dt.datetime, float, dict]] = []
    num = 0.0  # sum of (minute-index * score)
    den = 0.0  # sum of score
    for hh in range(h0, h1 + 1):
        cell = next((c for c in cells if c["hour"] == hh), None)
        if cell is None:
            continue
        ws = cell.get("wind_score") or 0.0
        ps = cell.get("precip_score") or 0.0
        for mm in range(60):
            if not (lo <= hh + mm / 60.0 <= hi):
                continue
            m = dt.datetime.combine(day_date, dt.time(hh, mm))
            ev_t, ev = min(parsed, key=lambda p: abs((p[0] - m).total_seconds()))
            mins = abs((ev_t - m).total_seconds()) / 60.0
            before_win, after_win = _slack_half_windows(ev, tide_events)
            half_win = after_win if m >= ev_t else before_win
            ts = _tide_score(mins, half_win)
            score = ws * ps * (0.4 + 0.6 * ts)
            idx = hh * 60 + mm
            num += idx * score
            den += score
            samples.append((m, score, cell))
    if den <= 0 or not samples:
        return None
    centroid = num / den
    # Snap the centroid to the nearest scanned minute so the marker, its score,
    # and its hour cell all describe a real sampled instant.
    return min(samples, key=lambda s: abs((s[0].hour * 60 + s[0].minute) - centroid))


def _classify(in_slack: bool, wind_mph: Optional[float],
              gust_mph: Optional[float]) -> str:
    if not in_slack:
        return CAT_OFF
    w = wind_mph if wind_mph is not None else 0.0
    g = gust_mph if gust_mph is not None else 0.0
    if w > 15 or g >= 20:
        return CAT_RED
    if w >= 10:
        return CAT_YELLOW
    return CAT_GREEN


def _day_wind_badge(row: dict) -> tuple[str, str]:
    """Return (label, css_class) summarizing daylight wind for one day.

    Bands (max across daylight cells):
      GLASS   max wind <= 7 mph AND max gust < 10 mph
      WINDY   max wind > 15 mph OR max gust >= 25 mph
      BREEZY  everything in between
    """
    cells = row.get("cells") or []
    if not cells:
        return ("", "")
    max_w = max((c.get("wind_mph") or 0.0) for c in cells)
    max_g = max((c.get("gust_mph") or 0.0) for c in cells)
    if max_w <= 7 and max_g < 10:
        return ("GLASS", "glass")
    if max_w > 15 or max_g >= 25:
        return ("WINDY", "windy")
    return ("BREEZY", "breezy")


def _score_cell_class(score: float) -> tuple[str, str]:
    """Continuous score -> (background, foreground) for heatmap cells.
    Tiers: Prime / Good / Marginal / Poor / Terrible (green -> red gradient)."""
    if score >= 0.9:  return ("#107C10", "#FFFFFF")  # Prime     - saturated green
    if score >= 0.75: return ("#DFF6DD", "#0B6A0B")  # Good      - light green
    if score >= 0.5:  return ("#FFF4CE", "#5C4400")  # Marginal  - yellow
    if score >= 0.25: return ("#FED9B7", "#8A2900")  # Poor      - orange
    return ("#A4262C", "#FFFFFF")                    # Terrible  - red


def _fmt_clock(t: dt.datetime, with_minutes: bool = True) -> str:
    """12-hour clock label: 5:42a, 12:00p, 9p (when with_minutes=False)."""
    h12 = t.hour % 12 or 12
    suffix = "a" if t.hour < 12 else "p"
    if with_minutes:
        return f"{h12}:{t.minute:02d}{suffix}"
    return f"{h12}{suffix}"


def _fmt_iso_clock(iso: str, with_minutes: bool = True) -> str:
    """Format a 'HH:MM' substring of an ISO timestamp as a 12-hour clock."""
    try:
        hh, mm = iso[11:13], iso[14:16]
        h, m = int(hh), int(mm)
        h12 = h % 12 or 12
        suffix = "a" if h < 12 else "p"
        return f"{h12}:{m:02d}{suffix}" if with_minutes else f"{h12}{suffix}"
    except (ValueError, IndexError):
        return iso[11:16] if len(iso) >= 16 else iso


# --- core data assembly ------------------------------------------------------

# Stored outside kb/ and src/ so committing a refreshed cache from CI does not
# re-trigger the build workflow (its push filter watches kb/** and src/**).
TIDE_CACHE_PATH = ROOT / "data" / "tide_cache.json"


def _load_tide_cache() -> dict:
    """Load the persistent tide-prediction cache ({station: {timestamp: event}})."""
    try:
        raw = json.loads(TIDE_CACHE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_tide_cache(cache: dict) -> None:
    try:
        TIDE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TIDE_CACHE_PATH.write_text(
            json.dumps(cache, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass


def _assemble(start: dt.date) -> dict:
    def _get_tides_resilient(station: str, begin_iso: str, total_days: int) -> dict:
        """Fetch tides with a bulk call first, then day-sized fallbacks on timeout."""
        bulk = noaa_tides(station, date=begin_iso, days=total_days)
        if bulk.get("tides"):
            return bulk

        begin_d = dt.date.fromisoformat(begin_iso)
        merged: dict[str, dict] = {}
        last_error = bulk.get("error")
        # 1-day windows are slower but much less likely to 504.
        for i in range(total_days + 1):
            day_iso = (begin_d + dt.timedelta(days=i)).isoformat()
            part = noaa_tides(station, date=day_iso, days=1)
            rows = part.get("tides") or []
            if rows:
                for r in rows:
                    ts = r.get("t")
                    if ts:
                        merged[ts] = r
            elif part.get("error"):
                last_error = part.get("error")

        if merged:
            return {
                "source": "NOAA CO-OPS",
                "station": station,
                "begin": begin_iso,
                "end": str(begin_d + dt.timedelta(days=total_days)),
                "tides": [merged[k] for k in sorted(merged)],
            }
        return bulk if bulk.get("error") else {
            "source": "NOAA CO-OPS",
            "station": station,
            "error": last_error or "no tide data",
            "tides": [],
        }

    w = WATERS[WATER_KEY]
    om = wind_blend(w.lat, w.lon, hours=DAYS * 24)
    if "error" in om or not om.get("hours"):
        # Last-ditch fallback to single-source Open-Meteo if the blend failed.
        om = open_meteo(w.lat, w.lon, hours=DAYS * 24)
    hours = {h["time"]: h for h in om.get("hours", [])}

    # Pad ±1 day so cosine tide interpolation has bracketing events at the edges.
    tide_begin = (start - dt.timedelta(days=1)).isoformat()
    primary_tide_station = w.tide_station
    tides = _get_tides_resilient(primary_tide_station, tide_begin, DAYS + 2)
    tide_station_used = primary_tide_station
    # CO-OPS occasionally times out on Hansville. Fall back to Seattle so
    # scoring and colorized charts remain live instead of flat/stale.
    if tides.get("error") or not tides.get("tides"):
        backup_tide_station = "9447130"
        backup = _get_tides_resilient(backup_tide_station, tide_begin, DAYS + 2)
        if backup.get("tides"):
            tides = backup
            tide_station_used = backup_tide_station
    fetched = tides.get("tides", []) or []

    # Persistent tide cache. NOAA CO-OPS is intermittently down (504), but tide
    # PREDICTIONS are deterministic astronomy and never change, so a stored copy
    # is just as valid as a live one. Merge whatever we fetched into the cache
    # (per station, keyed by timestamp), prune stale rows, and backfill the
    # forecast window from it — so a partial or failed fetch still yields a
    # complete report instead of a flat ~0.40 heatmap.
    cache = _load_tide_cache()
    if fetched:
        bucket = cache.setdefault(tide_station_used, {})
        for ev in fetched:
            t = ev.get("t")
            if t:
                bucket[t] = ev
        keep_floor = (start - dt.timedelta(days=3)).isoformat()
        for station_bucket in cache.values():
            for key in [k for k in station_bucket if k[:10] < keep_floor]:
                del station_bucket[key]
        _save_tide_cache(cache)

    need_lo = (start - dt.timedelta(days=1)).isoformat()
    need_hi = (start + dt.timedelta(days=DAYS)).isoformat()
    merged: dict[str, dict] = {}
    for ev in cache.get(tide_station_used, {}).values():
        t = ev.get("t", "")
        if t and need_lo <= t[:10] <= need_hi:
            merged[t] = ev
    for ev in fetched:
        t = ev.get("t")
        if t:
            merged[t] = ev
    tide_events = [merged[k] for k in sorted(merged)]
    tide_from_cache = bool(tide_events) and len(tide_events) > len(fetched)

    grid: list[dict] = []
    all_windows: list[dict] = []

    for di in range(DAYS):
        day = start + dt.timedelta(days=di)
        sun = _sun_times(day, w.lat, w.lon)
        sun_row = {
            "nautical_dawn": sun["nautical_dawn"],
            "sunrise":       sun["sunrise"],
            "sunset":        sun["sunset"],
            "nautical_dusk": sun["nautical_dusk"],
            "nautical_dawn_h": _hod(sun["nautical_dawn"]),
            "sunrise_h":       _hod(sun["sunrise"]),
            "sunset_h":        _hod(sun["sunset"]),
            "nautical_dusk_h": _hod(sun["nautical_dusk"]),
        }
        row = {"date": day, "cells": [], "sun": sun_row}
        run: list[dict] = []
        for hr in range(HOUR_START, HOUR_END + 1):
            key = f"{day.isoformat()}T{hr:02d}:00"
            wx = hours.get(key, {})
            gust = wx.get("gust_mph")
            wind = wx.get("wind_mph")
            wdir = wx.get("wind_dir_deg")
            temp = wx.get("temp_f")
            precip = wx.get("precip_in")

            mins, t_ev = _nearest_tide(key, tide_events)
            before_win, after_win = _slack_half_windows(t_ev, tide_events)
            # Pick the window belonging to the side of slack this hour is on.
            half_win = before_win
            if t_ev is not None and mins is not None:
                try:
                    ev_t = dt.datetime.strptime(t_ev["t"], "%Y-%m-%d %H:%M")
                    hr_t = dt.datetime.fromisoformat(key)
                    half_win = after_win if hr_t >= ev_t else before_win
                except (KeyError, ValueError, TypeError):
                    half_win = max(before_win, after_win)
            in_slack = mins is not None and mins <= half_win
            ts = _tide_score(mins, half_win)
            ws = _wind_score(wind, gust)
            ps = _precip_score(precip)
            # Soft tide modifier: 0.4x mid-cycle, 1.0x at slack. Wind/precip
            # remain hard multipliers so a blown-out hour still scores zero.
            score = ws * ps * (0.4 + 0.6 * ts)
            category = _classify(in_slack, wind, gust)

            cell = {
                "time": key, "hour": hr, "score": score,
                "tide_score": ts, "wind_score": ws, "precip_score": ps,
                "slack_window_min": half_win,
                "category": category,
                "in_slack": in_slack, "minutes_to_slack": mins,
                "nearest_tide": t_ev,
                "wind_mph": wind, "gust_mph": gust, "wind_dir_deg": wdir,
                "temp_f": temp, "precip_in": precip,
            }
            row["cells"].append(cell)

            # Best-windows leaderboard = runs of hours with usable score.
            if score >= 0.75:
                run.append(cell)
            else:
                if run:
                    all_windows.append(_summarize_run(run))
                    run = []
        if run:
            all_windows.append(_summarize_run(run))
        grid.append(row)

    # Rank windows by sustained quality (area under the score curve), not just
    # peak height. A brief 0.95 flash now ranks below a longer 0.80 stretch.
    all_windows.sort(key=lambda r: (-r["quality"], -r["peak_score"], -r["hours"]))

    return {
        "water": w,
        "start": start,
        "end": start + dt.timedelta(days=DAYS - 1),
        "distance_home_mi": round(haversine_km(*PLACES["home"], w.lat, w.lon) * 0.621371, 1),
        "distance_cabin_mi": round(haversine_km(*PLACES["cabin"], w.lat, w.lon) * 0.621371, 1),
        "grid": grid,
        "tide_events": tide_events,
        "hours_raw": om.get("hours", []),
        "marine": nws_marine_forecast(w.nws_zone) if w.nws_zone else {},
        "buoys": [ndbc_latest(b) for b in w.ndbc_buoys],
        "windows": all_windows,
        "open_meteo_error": om.get("error"),
        "wind_sources": om.get("sources") or [om.get("source", "Open-Meteo")],
        "tides_error": tides.get("error"),
        "tide_station_used": tide_station_used,
        "tide_from_cache": tide_from_cache,
        "rules": kb.regulations("Marine Area 9"),
    }


def _summarize_run(run: list[dict]) -> dict:
    first = dt.datetime.fromisoformat(run[0]["time"])
    last = dt.datetime.fromisoformat(run[-1]["time"])
    peak = max(run, key=lambda c: c["score"])
    anchor = peak["nearest_tide"] or {}
    return {
        "date": first.date(),
        "start_hour": first.hour,
        "end_hour": last.hour,
        "hours": len(run),
        "peak_score": peak["score"],
        "quality": sum(c["score"] for c in run),
        "peak_time": peak["time"],
        "nearest_tide": anchor,
        "tide_kind": anchor.get("type"),
        "tide_time": _fmt_iso_clock(anchor.get("t") or "") if anchor.get("t") else "",
        "tide_height": anchor.get("v"),
        "max_gust": max((c["gust_mph"] or 0) for c in run),
        "max_wind": max((c["wind_mph"] or 0) for c in run),
        "avg_temp": round(sum((c["temp_f"] or 0) for c in run) / len(run), 1),
    }


# --- HTML rendering ----------------------------------------------------------

EXTRA_CSS = """
.heatmap{width:100%;border-collapse:separate;border-spacing:2px;font-size:11px;
         font-variant-numeric:tabular-nums;table-layout:fixed}
.heatmap th{background:#F3F2F1;color:var(--ms-text-secondary);font-weight:600;
            padding:4px 2px;font-size:11px;text-align:center}
.heatmap td{padding:6px 2px;text-align:center;border-radius:3px;cursor:help;
            font-weight:600;min-width:30px}
.heatmap td.label{background:#F3F2F1;color:var(--ms-text);text-align:left;
                  padding:6px 8px;font-weight:600;width:90px;border-radius:3px}
.heatmap td.tide-marker{outline:2px solid var(--ms-blue-darker);outline-offset:-2px}

.legend{display:flex;gap:6px;align-items:center;font-size:12px;margin:10px 0 14px;
        color:var(--ms-text-secondary);flex-wrap:wrap}
.legend .sw{display:inline-block;width:18px;height:14px;border-radius:3px;
            border:1px solid var(--ms-border);margin-right:4px;vertical-align:middle}

.window-list{list-style:none;padding:0;margin:0}
.window-list li{padding:8px 10px;border-bottom:1px solid var(--ms-divider);
                display:flex;justify-content:space-between;align-items:center;gap:10px}
.window-list li:last-child{border-bottom:none}
.window-list .when{font-weight:600;color:var(--ms-text)}
.window-list .why{color:var(--ms-text-secondary);font-size:12px}
.window-list .score{font-weight:700;color:var(--ms-blue-darker);font-size:13px}

.alert{padding:10px 14px;border-radius:4px;margin:10px 0;font-size:13px;
       border-left:4px solid var(--ms-orange);background:#FED9B7;color:#8A2900}
.alert.good{border-left-color:var(--ms-green);background:#DFF6DD;color:#0B6A0B}
.alert.info{border-left-color:var(--ms-blue);background:#DEECF9;color:var(--ms-blue-darker)}

.chart-legend{display:flex;flex-wrap:wrap;gap:14px;margin:8px 0 14px;font-size:12px;
              color:var(--ms-text-secondary)}
.chart-legend .swatch{display:inline-block;vertical-align:middle;margin-right:6px}
.chart-legend .line{display:inline-block;width:22px;height:0;border-top:2px solid;
                    vertical-align:middle;margin-right:6px}
.chart-legend .line.dashed{border-top-style:dashed}
.chart-legend .line.dotted{border-top-style:dotted;border-top-width:3px}
.chart-grid{display:grid;grid-template-columns:1fr;gap:14px}
.chart-card{background:#FFFFFF;border:1px solid var(--ms-border);border-radius:6px;
            padding:8px 12px;box-shadow:var(--shadow-sm);position:relative}
.chart-card svg{display:block;width:100%;height:auto}
.chart-card .day-badge{position:absolute;top:10px;right:14px;font-size:10px;
                       padding:3px 9px;border-radius:10px;font-weight:700;
                       letter-spacing:0.06em;border:1px solid transparent;
                       font-variant-numeric:tabular-nums;z-index:2}
.day-badge.glass{background:#DFF6DD;color:#0B6A0B;border-color:#92C593}
.day-badge.breezy{background:#FFF4CE;color:#5C4400;border-color:#E8C77A}
.day-badge.windy{background:#FED9B7;color:#8A2900;border-color:#E89F70}
"""


def _cell_tooltip(c: dict) -> str:
    parts = [f"{_fmt_iso_clock(c['time'])} \u00b7 score {c['score']:.2f} \u00b7 {c['category'].upper()}"]
    mins = c.get("minutes_to_slack")
    if c["nearest_tide"]:
        t = c["nearest_tide"]
        if mins is not None:
            parts.append(
                f"{int(mins)} min from {t.get('type')} @ {_fmt_iso_clock(t.get('t',''))} "
                f"({t.get('v')} ft)"
            )
    parts.append(
        f"wind {_fmt(c.get('wind_mph'),' mph',0)} "
        f"g{_fmt(c.get('gust_mph'),'',0)} "
        f"{_deg_to_compass(c.get('wind_dir_deg'))}"
    )
    if c.get("temp_f") is not None:
        parts.append(f"{c['temp_f']:.0f}\u00b0F")
    if c.get("precip_in"):
        parts.append(f"precip {c['precip_in']}\"")
    return " \u00b7 ".join(parts)


def _render_heatmap(grid: list[dict], tide_events: list[dict]) -> str:
    # Build hour headers
    hour_headers = "".join(
        f"<th>{h % 12 or 12}{'a' if h < 12 else 'p'}</th>"
        for h in range(HOUR_START, HOUR_END + 1)
    )
    # For tide-marker outline: mark cells whose hour matches a tide event hour
    tide_hours_by_day: dict[str, set[int]] = defaultdict(set)
    for ev in tide_events:
        t = ev.get("t", "")
        if len(t) >= 13:
            tide_hours_by_day[t[:10]].add(int(t[11:13]))

    rows = []
    for row in grid:
        day = row["date"]
        dlabel = day.strftime("%a %b %#d")
        cells = [f"<td class='label'>{dlabel}</td>"]
        sun = row.get("sun") or {}
        nd_h = sun.get("nautical_dawn_h")
        nu_h = sun.get("nautical_dusk_h")
        sr_h = sun.get("sunrise_h")
        ss_h = sun.get("sunset_h")
        for c in row["cells"]:
            bg, fg = _score_cell_class(c["score"])
            cls_parts = []
            if c["hour"] in tide_hours_by_day.get(day.isoformat(), set()):
                cls_parts.append("tide-marker")
            # Cell center is `hour + 0.5`. Anything fully outside nautical
            # dawn -> dusk is "night" (dark grey); anything between naut-dawn
            # and sunrise (or sunset and naut-dusk) is "twilight" (light grey).
            hr_mid = c["hour"] + 0.5
            style = f"background:{bg};color:{fg}"
            if nd_h is not None and nu_h is not None and (hr_mid < nd_h or hr_mid > nu_h):
                cls_parts.append("night")
                style = "background:#605E5C;color:#F3F2F1"
            elif sr_h is not None and ss_h is not None and (hr_mid < sr_h or hr_mid > ss_h):
                cls_parts.append("twilight")
                style = f"background:{bg};color:{fg};opacity:0.65"
            tip = _cell_tooltip(c)
            display = f"{c['score']:.2f}".lstrip("0") if c["score"] > 0 else ""
            cells.append(
                f"<td class='{' '.join(cls_parts)}' style='{style}' "
                f"title=\"{html.escape(tip)}\">{display}</td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    header = "<tr><th class='label'>Day</th>" + hour_headers + "</tr>"
    legend = (
        "<div class='legend'>"
        "<span><span class='sw' style='background:#107C10'></span>Prime (\u22650.9)</span>"
        "<span><span class='sw' style='background:#DFF6DD'></span>Good</span>"
        "<span><span class='sw' style='background:#FFF4CE'></span>Marginal</span>"
        "<span><span class='sw' style='background:#FED9B7'></span>Poor</span>"
        "<span><span class='sw' style='background:#A4262C'></span>Terrible</span>"
        "<span style='margin-left:14px'>"
        "<span class='sw' style='background:#fff;outline:2px solid #005A9E;outline-offset:-2px'></span>"
        "tide event hour</span>"
        "<span style='margin-left:14px'>"
        "<span class='sw' style='background:#605E5C'></span>night</span>"
        "<span><span class='sw' style='background:#DFF6DD;opacity:0.65'></span>twilight</span>"
        "</div>"
    )
    return legend + "<table class='heatmap'><thead>" + header + "</thead><tbody>" + "".join(rows) + "</tbody></table>"


def _render_window_list(windows: list[dict], limit: int = 8) -> str:
    if not windows:
        return "<p class='dim'>No qualifying windows in the next 7 days.</p>"
    items = []
    for w in windows[:limit]:
        date = w["date"].strftime("%a %b %#d")
        start = f"{w['start_hour'] % 12 or 12}{'a' if w['start_hour'] < 12 else 'p'}"
        end = f"{(w['end_hour']+1) % 12 or 12}{'a' if (w['end_hour']+1) < 12 else 'p'}"
        tide_str = (f"{w['tide_kind']} @ {w['tide_time']} ({w['tide_height']} ft)"
                    if w.get("tide_kind") else "\u2014")
        items.append(
            f"<li><div><span class='when'>{date} \u00b7 {start}\u2013{end}</span>"
            f"<div class='why'>Peak near {tide_str} \u00b7 max gust {w['max_gust']:.0f} mph"
            f" \u00b7 avg {w['avg_temp']:.0f}\u00b0F</div></div>"
            f"<span class='score'>{w['peak_score']:.2f}</span></li>"
        )
    return f"<ul class='window-list'>{''.join(items)}</ul>"


def _render_top_kpis(data: dict) -> str:
    windows = data["windows"]
    today = data["start"]
    best_today = max((w for w in windows if w["date"] == today),
                     key=lambda w: w["quality"], default=None)
    best_overall = windows[0] if windows else None

    ideal_hours = sum(1 for row in data["grid"] for c in row["cells"] if c["score"] >= 0.9)
    windy_hrs = sum(1 for row in data["grid"] for c in row["cells"]
                    if c.get("wind_score", 1.0) == 0 and c["in_slack"])

    def _fmt_window(w: Optional[dict]) -> tuple[str, str]:
        if not w:
            return ("\u2014", "")
        date = w["date"].strftime("%a")
        start = f"{w['start_hour'] % 12 or 12}{'a' if w['start_hour'] < 12 else 'p'}"
        end = f"{(w['end_hour']+1) % 12 or 12}{'a' if (w['end_hour']+1) < 12 else 'p'}"
        hrs = w["hours"]
        hr_lbl = "hr" if hrs == 1 else "hrs"
        return (f"{date} {start}\u2013{end}", f"peak {w['peak_score']:.2f} \u00b7 {hrs} {hr_lbl}")

    today_val, today_sub = _fmt_window(best_today)
    overall_val, overall_sub = _fmt_window(best_overall)

    kpis = [
        ("green",  "Best Today",       today_val,   today_sub),
        ("",       "Best This Week",   overall_val, overall_sub),
        ("purple", "Ideal Hours (7d)", str(ideal_hours), "score \u2265 0.9"),
        ("red" if windy_hrs else "",
                   "Windy Hours",  str(windy_hrs), "gust \u2265 25 mph in slack"),
    ]
    cells = []
    for cls, lbl, val, sub in kpis:
        cells.append(
            f"<div class='kpi {cls}'><div class='lbl'>{_h(lbl)}</div>"
            f"<div class='val'>{_h(val)}</div>"
            + (f"<div class='sub'>{_h(sub)}</div>" if sub else "")
            + "</div>"
        )
    return f"<div class='kpi-strip'>{''.join(cells)}</div>"


def _lingcod_alert(start: dt.date) -> str:
    season_end = dt.date(start.year, 6, 15)
    if start > season_end:
        return ""
    days_left = (season_end - start).days
    cls = "good" if days_left > 5 else ""
    return (f"<div class='alert {cls}'><strong>Lingcod season open</strong> "
            f"May 1\u2013June 15 (Hook & line · 26\u2033\u201336\u2033 slot · 1/day · descending device required). "
            f"{days_left} day(s) left in the 2025-26 season.</div>")


# --- Daily detail SVG (tide / wind / temp overlay) --------------------------

def _tide_at(events: list[tuple[dt.datetime, float]], target: dt.datetime) -> Optional[float]:
    """Cosine interp between consecutive H/L events. Returns None outside bracket."""
    prev = nxt = None
    for ev in events:
        if ev[0] <= target:
            prev = ev
        elif nxt is None:
            nxt = ev
            break
    if prev is None or nxt is None:
        return None
    span = (nxt[0] - prev[0]).total_seconds()
    if span <= 0:
        return prev[1]
    frac = (target - prev[0]).total_seconds() / span
    return prev[1] + (nxt[1] - prev[1]) * (1 - math.cos(math.pi * frac)) / 2


def _fmt_hour_label(hr: int) -> str:
    if hr == 0:
        return "12a"
    if hr < 12:
        return f"{hr}a"
    if hr == 12:
        return "12p"
    return f"{hr - 12}p"


def _render_daily_chart(day_date: dt.date, cells: list[dict],
                        hours_raw: list[dict],
                        events_dt: list[tuple[dt.datetime, float, str]],
                        tide_events: list[dict],
                        sun: Optional[dict] = None) -> str:
    """SVG: tide curve (blue area) + wind/gust (orange) + temp (purple) for one day."""
    W, H = 940, 272
    PL, PR, PT, PB = 50, 50, 78, 38
    IW, IH = W - PL - PR, H - PT - PB

    def x_of(hr_float: float) -> float:
        return PL + (hr_float / 24.0) * IW

    TIDE_MIN, TIDE_MAX = -5.0, 12.0
    def y_tide(v: float) -> float:
        return PT + IH - (v - TIDE_MIN) / (TIDE_MAX - TIDE_MIN) * IH

    WIND_MAX = 30.0
    def y_wind(v: float) -> float:
        return PT + IH - (v / WIND_MAX) * IH

    TEMP_MIN, TEMP_MAX = 40.0, 95.0
    def y_temp(v: float) -> float:
        return PT + IH - (v - TEMP_MIN) / (TEMP_MAX - TEMP_MIN) * IH

    parts: list[str] = []
    parts.append(
        f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' "
        f"role='img' aria-label='{day_date} detail'>"
    )

    # Title
    parts.append(
        f"<text x='{PL}' y='18' font-size='13' font-weight='700' "
        f"fill='var(--ms-text)'>{day_date.strftime('%A %b %#d')}</text>"
    )

    # (Score is now shown directly via the tide curve color, no separate strip.)

    # Non-daylight shading: three tiers based on real sun geometry for this
    # day at this water's lat/lon:
    #   0  -> nautical_dawn : deep night   (dark grey)
    #   nautical_dawn -> sunrise           : first-light twilight (light grey)
    #   sunrise       -> sunset            : full daylight (clear)
    #   sunset        -> nautical_dusk     : last-light twilight (light grey)
    #   nautical_dusk -> 24                : deep night (dark grey)
    # Falls back to the fixed HOUR_START/HOUR_END window if sun data missing.
    NIGHT_FILL, NIGHT_OP = "#8A8886", 0.35
    TWI_FILL,   TWI_OP   = "#C8C6C4", 0.35

    def _shade(x0: float, x1: float, fill: str, op: float) -> str:
        if x1 <= x0:
            return ""
        return (f"<rect x='{x0:.1f}' y='{PT}' width='{x1 - x0:.1f}' height='{IH}' "
                f"fill='{fill}' opacity='{op}'/>")

    if sun and all(sun.get(k) is not None for k in
                   ("nautical_dawn_h", "sunrise_h", "sunset_h", "nautical_dusk_h")):
        nd = sun["nautical_dawn_h"]
        sr = sun["sunrise_h"]
        ss = sun["sunset_h"]
        nu = sun["nautical_dusk_h"]
        parts.append(_shade(x_of(0),  x_of(nd), NIGHT_FILL, NIGHT_OP))
        parts.append(_shade(x_of(nd), x_of(sr), TWI_FILL,   TWI_OP))
        parts.append(_shade(x_of(ss), x_of(nu), TWI_FILL,   TWI_OP))
        parts.append(_shade(x_of(nu), x_of(24), NIGHT_FILL, NIGHT_OP))
    else:
        parts.append(_shade(x_of(0), x_of(HOUR_START), NIGHT_FILL, NIGHT_OP))
        parts.append(_shade(x_of(HOUR_END + 1), x_of(24), NIGHT_FILL, NIGHT_OP))
    # 30-min vertical gridlines (half-hours lighter, hours a touch darker).
    half = 0
    while half <= 48:
        hr = half / 2.0
        cx = x_of(hr)
        if half % 2 == 0:
            parts.append(
                f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                f"stroke='#C8C6C4' stroke-width='1' opacity='0.65'/>"
            )
        else:
            parts.append(
                f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                f"stroke='#E1DFDD' stroke-width='1' opacity='0.55'/>"
            )
        half += 1

    # Tide curve (cosine-interpolated, 15 min steps)
    base = dt.datetime.combine(day_date, dt.time())
    flat_events = [(e[0], e[1]) for e in events_dt]
    tide_pts: list[tuple[float, float]] = []
    for m in range(0, 24 * 60 + 1, 15):
        target = base + dt.timedelta(minutes=m)
        v = _tide_at(flat_events, target)
        if v is not None:
            tide_pts.append((m / 60.0, v))

    if tide_pts:
        area = "M " + f"{x_of(tide_pts[0][0]):.1f},{PT + IH:.1f} "
        area += " ".join(f"L {x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in tide_pts)
        area += f" L {x_of(tide_pts[-1][0]):.1f},{PT + IH:.1f} Z"
        parts.append(f"<path d='{area}' fill='#DEECF9' stroke='none' opacity='0.85'/>")
        line = "M " + " L ".join(f"{x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in tide_pts)
        parts.append(f"<path d='{line}' fill='none' stroke='#005A9E' stroke-width='2'/>")

        # Tier overlay: tide curve repainted with the heatmap palette so the
        # chart's colored sections directly correspond to score tiers \u2014 the
        # whole tide curve becomes the score legend.
        TIER_FILL = {
            "prime":    ("#107C10", 0.45),
            "good":     ("#107C10", 0.18),
            "marginal": ("#FFE08A", 0.85),
            "poor":     ("#FED9B7", 0.85),
            "terrible": ("#A4262C", 0.55),
        }
        TIER_STROKE = {
            "prime":    "#054B05",
            "good":     "#107C10",
            "marginal": "#A8920A",
            "poor":     "#A8330A",
            "terrible": "#A4262C",
        }

        def _tier(score: float) -> Optional[str]:
            if score >= 0.9:
                return "prime"
            if score >= 0.75:
                return "good"
            if score >= 0.5:
                return "marginal"
            if score >= 0.25:
                return "poor"
            return "terrible"

        cells_sorted = sorted(cells, key=lambda c: c["hour"])
        tier_spans: list[tuple[str, float, float]] = []
        cur_tier: Optional[str] = None
        cur_lo: Optional[float] = None
        prev_h: Optional[int] = None
        for c in cells_sorted:
            t = _tier(c["score"])
            h = c["hour"]
            if t != cur_tier:
                if cur_tier and prev_h is not None and cur_lo is not None:
                    tier_spans.append((cur_tier, cur_lo, prev_h + 0.5))
                cur_tier = t
                cur_lo = h - 0.5
            prev_h = h
        if cur_tier and prev_h is not None and cur_lo is not None:
            tier_spans.append((cur_tier, cur_lo, prev_h + 0.5))

        for tier, lo, hi in tier_spans:
            seg = [(hr, v) for hr, v in tide_pts if lo <= hr <= hi]
            if len(seg) < 2:
                continue
            fill_color, fill_op = TIER_FILL[tier]
            stroke_color = TIER_STROKE[tier]
            sw = 3 if tier in ("prime", "good") else 2.2
            fill = "M " + f"{x_of(seg[0][0]):.1f},{PT + IH:.1f} "
            fill += " ".join(f"L {x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in seg)
            fill += f" L {x_of(seg[-1][0]):.1f},{PT + IH:.1f} Z"
            parts.append(
                f"<path d='{fill}' fill='{fill_color}' opacity='{fill_op:.2f}' stroke='none'/>"
            )
            stroke = "M " + " L ".join(
                f"{x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in seg
            )
            parts.append(
                f"<path d='{stroke}' fill='none' stroke='{stroke_color}' "
                f"stroke-width='{sw}' stroke-linecap='round'/>"
            )

        # Tide-change windows = contiguous runs of GREEN (Prime OR Good) cells.
        # Merging the two tiers matters: a slack often sits on the Good side of
        # a Prime->Good boundary (e.g. a 6:42 slack with the 6a cell Prime and
        # the 7a cell Good), and the center-of-mass must be taken over the whole
        # productive run, not a truncated tier slice.
        spans: list[tuple[float, float]] = []
        _run_lo: Optional[float] = None
        _prev_h: Optional[int] = None
        for c in cells_sorted:
            if c["score"] >= 0.75:
                if _run_lo is None:
                    _run_lo = c["hour"] - 0.5
                _prev_h = c["hour"]
            elif _run_lo is not None and _prev_h is not None:
                spans.append((_run_lo, _prev_h + 0.5))
                _run_lo = None
        if _run_lo is not None and _prev_h is not None:
            spans.append((_run_lo, _prev_h + 0.5))

        # BEST-MOMENT marker: each Prime/Good span that contains a predicted
        # slack anchors one pill for that tide-change window. The pill sits on
        # the score-weighted center-of-mass of the window — the heart of the
        # bite — which lands ahead of slack on asymmetric windows (long lead-in,
        # sharp drop), so the eye is drawn to when you should actually be out.
        windows_with_slack: list[tuple[float, float]] = []
        seen_spans: set[tuple[float, float]] = set()
        for t, v, kind in events_dt:
            if t.date() != day_date:
                continue
            hr_f = t.hour + t.minute / 60.0
            span = next(((lo, hi) for lo, hi in spans if lo <= hr_f <= hi), None)
            if span and span not in seen_spans:
                seen_spans.add(span)
                windows_with_slack.append(span)

        for lo, hi in windows_with_slack:
            best = _window_heart(lo, hi, day_date, cells, tide_events)
            if best is None:
                continue
            peak_t, score_val, peak_cell = best
            cx = x_of(peak_t.hour + peak_t.minute / 60.0)
            # Glass-calm flag: heart-of-window hour cell has gust <= 10 AND
            # wind <= 7. Visual only — the badge LABEL is driven by the score
            # tier so it can never contradict the cell color underneath.
            glass = bool(
                peak_cell
                and (peak_cell.get("gust_mph") or 0) <= 10
                and (peak_cell.get("wind_mph") or 0) <= 7
            )
            score_str = (
                f"{score_val:.2f}".lstrip("0")
                if isinstance(score_val, (int, float)) and score_val > 0
                else ""
            )
            tier_name = (
                _tier(score_val)
                if isinstance(score_val, (int, float))
                else None
            )
            tier_label = "PRIME" if tier_name == "prime" else "GOOD"
            # Gold treatment is reserved for the STANDOUT combo: glass-calm
            # AND Prime tier. A glass-calm slack whose nearest hour cell only
            # scores GOOD (e.g. big-swing slack with tight ±45 min window
            # where the cell sits 13 min off slack) gets the normal green
            # badge — gold would over-promise.
            gold = glass and tier_name == "prime"

            if gold:
                # Soft gold vertical band behind the stroke — flags glass-calm Prime.
                band_w = max(8.0, IW / 24.0 * 0.55)
                parts.append(
                    f"<rect x='{cx - band_w/2:.1f}' y='{PT}' width='{band_w:.1f}' "
                    f"height='{IH}' fill='#FFB900' opacity='0.18'/>"
                )
                parts.append(
                    f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                    f"stroke='#D29200' stroke-width='2' opacity='0.95'/>"
                )
                badge_fill = "#FFB900"
                badge_text = "#3B2F00"
                badge_h = 18
                font_sz = 11
            else:
                parts.append(
                    f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                    f"stroke='#107C10' stroke-width='1.4' stroke-dasharray='5,3' opacity='0.9'/>"
                )
                badge_fill = "#107C10" if tier_name == "good" else "#054B05"
                badge_text = "#FFFFFF"
                badge_h = 15
                font_sz = 10

            label = (
                f"\u2605 {tier_label} {score_str} {_fmt_clock(peak_t)}"
                if score_str
                else f"\u2605 {tier_label} {_fmt_clock(peak_t)}"
            )

            # Above the chart frame, on a dedicated shelf between the score
            # strip (y=32) and the chart top (y=PT=78).
            badge_y = 50
            text_w = 8 + len(label) * 6
            # GLASS pill rides with the gold treatment — both flag the same
            # standout combo (glass-calm AND Prime tier).
            pill_text = "GLASS"
            pill_w = 8 + len(pill_text) * 6 if gold else 0
            pill_gap = 4 if gold else 0
            group_w = text_w + pill_gap + pill_w
            gx = max(PL + 2, min(cx - group_w / 2, PL + IW - group_w - 2))
            bx = gx
            parts.append(
                f"<rect x='{bx:.1f}' y='{badge_y:.1f}' width='{text_w}' height='{badge_h}' "
                f"rx='3' fill='{badge_fill}'/>"
            )
            parts.append(
                f"<text x='{bx + text_w/2:.1f}' y='{badge_y + badge_h - 4:.1f}' "
                f"text-anchor='middle' font-size='{font_sz}' font-weight='700' "
                f"fill='{badge_text}'>{label}</text>"
            )
            if gold:
                # Compact gold "GLASS" pill rides alongside the main badge so
                # the wind/gust glass-calm flag is named explicitly.
                px = bx + text_w + pill_gap
                pill_h = badge_h
                parts.append(
                    f"<rect x='{px:.1f}' y='{badge_y:.1f}' width='{pill_w}' "
                    f"height='{pill_h}' rx='{pill_h/2:.1f}' fill='#FFB900' "
                    f"stroke='#D29200' stroke-width='0.8'/>"
                )
                parts.append(
                    f"<text x='{px + pill_w/2:.1f}' y='{badge_y + pill_h - 4:.1f}' "
                    f"text-anchor='middle' font-size='10' font-weight='800' "
                    f"fill='#3B2F00'>{pill_text}</text>"
                )

    # Tide H/L markers for this day. Label position flips above/below the dot
    # when it would otherwise clip the frame edge or collide with the hour axis.
    for t, v, kind in events_dt:
        if t.date() != day_date:
            continue
        hr = t.hour + t.minute / 60
        cx, cy = x_of(hr), y_tide(v)
        parts.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='4.5' fill='#005A9E'/>")
        is_high = kind == "H"
        # Default: highs above the dot, lows below it.
        place_above = is_high
        if place_above and cy - 22 < PT + 2:
            place_above = False     # high tide squeezed against frame top -> flip
        elif (not place_above) and cy + 28 > PT + IH - 2:
            place_above = True      # low tide squeezed against frame bottom -> flip
        if place_above:
            ly_value = cy - 9
            ly_time = cy - 20
        else:
            ly_value = cy + 15
            ly_time = cy + 26
        parts.append(
            f"<text x='{cx:.1f}' y='{ly_value:.1f}' text-anchor='middle' font-size='10' "
            f"font-weight='700' fill='#005A9E'>{kind} {v:.1f}ft</text>"
        )
        parts.append(
            f"<text x='{cx:.1f}' y='{ly_time:.1f}' text-anchor='middle' "
            f"font-size='9' fill='var(--ms-text-secondary)'>"
            f"{_fmt_clock(t)}</text>"
        )

    # Wind + gust
    day_hours = [h for h in hours_raw if h.get("time", "").startswith(day_date.isoformat())]
    if day_hours:
        wind_pts = [(int(h["time"][11:13]), h.get("wind_mph") or 0) for h in day_hours]
        gust_pts = [(int(h["time"][11:13]), h.get("gust_mph") or 0) for h in day_hours]
        gust_d = "M " + " L ".join(f"{x_of(hr + 0.5):.1f},{y_wind(v):.1f}" for hr, v in gust_pts)
        wind_d = "M " + " L ".join(f"{x_of(hr + 0.5):.1f},{y_wind(v):.1f}" for hr, v in wind_pts)
        parts.append(
            f"<path d='{gust_d}' fill='none' stroke='#D83B01' stroke-width='1.5' "
            f"stroke-dasharray='4,3' opacity='0.85'/>"
        )
        parts.append(
            f"<path d='{wind_d}' fill='none' stroke='#D83B01' stroke-width='2.2'/>"
        )

    # Temperature line + min/max markers
    if day_hours:
        temp_pts = [(int(h["time"][11:13]), h.get("temp_f")) for h in day_hours
                    if h.get("temp_f") is not None]
        if temp_pts:
            temp_d = "M " + " L ".join(f"{x_of(hr + 0.5):.1f},{y_temp(v):.1f}" for hr, v in temp_pts)
            parts.append(
                f"<path d='{temp_d}' fill='none' stroke='#5C2D91' stroke-width='1.6' "
                f"stroke-dasharray='1,3' opacity='0.85'/>"
            )
            tmin = min(temp_pts, key=lambda p: p[1])
            tmax = max(temp_pts, key=lambda p: p[1])
            for hr, v in (tmin, tmax):
                parts.append(
                    f"<circle cx='{x_of(hr + 0.5):.1f}' cy='{y_temp(v):.1f}' r='3' "
                    f"fill='#5C2D91'/>"
                )
                anchor = "start" if hr < 18 else "end"
                dx = 6 if hr < 18 else -6
                parts.append(
                    f"<text x='{x_of(hr + 0.5) + dx:.1f}' y='{y_temp(v) - 5:.1f}' "
                    f"text-anchor='{anchor}' font-size='10' font-weight='700' "
                    f"fill='#5C2D91'>{v:.0f}\u00b0F</text>"
                )

    # Reference: +2 ft tide line (approx. minimum-floatable depth at the dock)
    parts.append(
        f"<line x1='{PL}' x2='{W - PR}' y1='{y_tide(2):.1f}' y2='{y_tide(2):.1f}' "
        f"stroke='#A4262C' stroke-dasharray='4,3' opacity='0.75'/>"
    )
    parts.append(
        f"<text x='{PL + 6}' y='{y_tide(2) - 3:.1f}' text-anchor='start' "
        f"font-size='9' font-weight='700' fill='#A4262C'>+2 ft float line</text>"
    )

    # Left axis (tide ft)
    for v in (-4, 0, 2, 4, 8, 12):
        ly = y_tide(v)
        parts.append(
            f"<text x='{PL - 6}' y='{ly + 3:.1f}' text-anchor='end' font-size='9' "
            f"fill='#005A9E'>{v}</text>"
        )
    parts.append(
        f"<text x='{14}' y='{PT + IH/2:.1f}' transform='rotate(-90 14,{PT + IH/2:.1f})' "
        f"font-size='10' font-weight='600' fill='#005A9E' text-anchor='middle'>Tide (ft, MLLW)</text>"
    )

    # Right axis (wind mph)
    for v in (0, 10, 20, 30):
        parts.append(
            f"<text x='{W - PR + 6}' y='{y_wind(v) + 3:.1f}' font-size='9' "
            f"fill='#D83B01'>{v}</text>"
        )
    parts.append(
        f"<text x='{W - 14}' y='{PT + IH/2:.1f}' transform='rotate(90 {W - 14},{PT + IH/2:.1f})' "
        f"font-size='10' font-weight='600' fill='#D83B01' text-anchor='middle'>Wind / Gust (mph)</text>"
    )

    # X-axis hour ticks (every hour, labeled)
    for hr in range(0, 25):
        cx = x_of(hr)
        tick_h = 5 if hr % 3 == 0 else 3
        parts.append(
            f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT + IH}' y2='{PT + IH + tick_h}' "
            f"stroke='#A19F9D'/>"
        )
        weight = "600" if hr % 3 == 0 else "400"
        parts.append(
            f"<text x='{cx:.1f}' y='{PT + IH + 14}' text-anchor='middle' font-size='9' "
            f"font-weight='{weight}' fill='var(--ms-text-secondary)'>{_fmt_hour_label(hr)}</text>"
        )

    # Sun-event edge labels below the hour axis. Outer/inner anchoring so the
    # first-light + sunrise pair spread apart (and sunset + last-light) instead
    # of colliding in early-summer months when they sit only ~1.7 h apart.
    if sun:
        sun_label_y = PT + IH + 25
        sun_tick_top = PT + IH + 1
        sun_tick_bot = PT + IH + 5
        for key, label, anchor, dx in (
            ("nautical_dawn_h", "first",   "end",   -3),
            ("sunrise_h",       "sunrise", "start",  3),
            ("sunset_h",        "sunset",  "end",   -3),
            ("nautical_dusk_h", "last",    "start",  3),
        ):
            h = sun.get(key)
            t = sun.get(key.replace("_h", ""))
            if h is None or t is None:
                continue
            cx = x_of(h)
            parts.append(
                f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{sun_tick_top}' "
                f"y2='{sun_tick_bot}' stroke='#605E5C' stroke-width='1.2'/>"
            )
            parts.append(
                f"<text x='{cx + dx:.1f}' y='{sun_label_y}' text-anchor='{anchor}' "
                f"font-size='9' font-style='italic' fill='#605E5C'>"
                f"{label} {_sun_clock(t)}</text>"
            )

    # Frame
    parts.append(
        f"<rect x='{PL}' y='{PT}' width='{IW}' height='{IH}' "
        f"fill='none' stroke='var(--ms-border)'/>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _render_daily_charts(data: dict) -> str:
    """Section with one SVG per day plus a shared legend."""
    events_dt: list[tuple[dt.datetime, float, str]] = []
    for ev in data["tide_events"]:
        try:
            t = dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M")
            events_dt.append((t, float(ev["v"]), ev.get("type", "")))
        except Exception:
            continue
    events_dt.sort(key=lambda e: e[0])

    legend = (
        "<div class='chart-legend'>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:10px;"
        "background:#DEECF9;border:1px solid #005A9E;vertical-align:middle;margin-right:6px'></span>"
        "Tide (cosine-interpolated)</span>"
        "<span><span class='swatch' style='display:inline-block;width:8px;height:8px;border-radius:50%;"
        "background:#005A9E;vertical-align:middle;margin-right:6px'></span>Predicted H / L</span>"
        "<span><span class='line' style='border-color:#D83B01'></span>Wind (mph)</span>"
        "<span><span class='line dashed' style='border-color:#D83B01'></span>Gust (mph)</span>"
        "<span><span class='line dashed' style='border-color:#A4262C'></span>+2 ft tide (float line)</span>"
        "<span><span class='line' style='border-color:#5C2D91;border-top-style:dotted;border-top-width:3px'></span>Air temp (\u00b0F)</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:10px;"
        "background:#107C10;vertical-align:middle;margin-right:6px'></span>"
        "Tide curve color = score tier (Prime/Good/Marginal/Poor)</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:14px;"
        "border-radius:3px;background:#054B05;color:#fff;text-align:center;font-size:10px;"
        "line-height:14px;vertical-align:middle;margin-right:6px'>\u2605</span>"
        "<strong>PRIME / GOOD</strong> &mdash; heart of the bite (score-weighted center of the window, ahead of slack)</span>"
        "<span><span class='swatch' style='display:inline-block;width:32px;height:14px;"
        "border-radius:7px;background:#FFB900;border:1px solid #D29200;color:#3B2F00;"
        "text-align:center;font-size:10px;line-height:14px;font-weight:800;vertical-align:middle;"
        "margin-right:6px'>GLASS</span>"
        "glass-calm slack at a Prime cell (gust \u226410 mph &amp; wind \u22647 mph &amp; cell score \u22650.9) &mdash; gold treatment flags the standout windows</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:10px;"
        "background:#107C10;vertical-align:middle;margin-right:6px'></span>"
        "Hourly fishability score (above frame)</span>"
        "</div>"
    )

    charts = []
    for row in data["grid"]:
        svg = _render_daily_chart(row["date"], row["cells"], data["hours_raw"],
                                  events_dt, data["tide_events"],
                                  sun=row.get("sun"))
        badge_label, badge_cls = _day_wind_badge(row)
        badge_html = (
            f"<span class='day-badge {badge_cls}'>{badge_label}</span>"
            if badge_label else ""
        )
        charts.append(f"<div class='chart-card'>{badge_html}{svg}</div>")

    return legend + f"<div class='chart-grid'>{''.join(charts)}</div>"


def build_html(start: Optional[dt.date] = None, data: Optional[dict] = None) -> str:
    start = start or dt.date.today()
    if data is None:
        data = _assemble(start)
    w = data["water"]

    tide_station_used = data.get("tide_station_used") or "9445526"
    tide_station_label = "Hansville" if tide_station_used == "9445526" else "Seattle (fallback)"
    sub = (
        f"{_kind_tag(w.kind)} {w.lat:.3f}, {w.lon:.3f} · "
        f"tide station {tide_station_label} ({tide_station_used})"
    )

    # Cards
    cards = []

    # Best windows (surfaced at the top — the most actionable view)
    cards.append(
        "<div class='card' style='grid-column:1/-1'>"
        "<h3>Best windows (next 7 days)</h3>"
        + _render_window_list(data["windows"]) + "</div>"
    )

    # Heatmap card
    cards.append(
        "<div class='card' style='grid-column:1/-1'>"
        "<h3>Fishability Heatmap (tide \u00d7 weather)</h3>"
        + _render_heatmap(data["grid"], data["tide_events"])
        + "</div>"
    )

    # Daily detail charts
    cards.append(
        "<div class='card' style='grid-column:1/-1'>"
        "<h3>Daily Detail \u2014 Tide / Wind / Temperature</h3>"
        + _render_daily_charts(data)
        + "</div>"
    )

    # Tides
    if data["tides_error"]:
        tides_html = f"<p class='dim'>Tides error: {_h(data['tides_error'])}</p>"
    else:
        in_window = {(data["start"] + dt.timedelta(days=i)).isoformat() for i in range(DAYS)}
        window_events = [t for t in data["tide_events"] if (t.get("t") or "")[:10] in in_window]
        tides_html = _render_tides(_group_tides_by_day(window_events))
    cards.append(f"<div class='card'><h3>Tides (MLLW)</h3>{tides_html}</div>")

    # Buoys
    if data["buoys"]:
        cards.append(
            "<div class='card'><h3>Buoy snapshots</h3>"
            + "".join(_render_buoy(b) for b in data["buoys"])
            + "</div>"
        )

    # Marine forecast text
    mf = data["marine"]
    if mf.get("text"):
        cards.append(
            f"<div class='card' style='grid-column:1/-1'>"
            f"<h3>NWS marine zone {_h(mf.get('zone'))}</h3>"
            f"<details><summary>Full text</summary><pre>{_h(mf['text'].strip())}</pre></details>"
            "</div>"
        )

    # Regulations
    cards.append(
        "<div class='card' style='grid-column:1/-1'><h3>Regulations</h3>"
        + _render_rules(data["rules"].get("current", [])[:3],
                        data["rules"].get("proposed", [])[:2])
        + "</div>"
    )

    generated = dt.datetime.now().strftime("%Y-%m-%d %#I:%M %p")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>MA9 Fishability {data['start']} \u2013 {data['end']}</title>"
        f"<style>{CSS}{EXTRA_CSS}{LOADOUT_CSS}</style></head><body>"
        "<header class='page'>"
        "<h1><div class='brand-logo'>"
        "<span></span><span></span><span></span><span></span>"
        "</div>Marine Area 9 \u2014 Fishability Report</h1>"
        f"<div class='meta'>{data['start'].strftime('%A, %B %d')} \u2013 "
        f"{data['end'].strftime('%A, %B %d, %Y')} \u00b7 generated {generated}</div>"
        "</header>"
        f"{render_nav('forecast')}"
        f"<section class='water' id='ma9'>"
        f"<h2>{_h(w.name)}</h2>"
        f"<div class='sub'>{sub}</div>"
        f"{_lingcod_alert(start)}"
        f"{_render_top_kpis(data)}"
        f"<div class='grid'>{''.join(cards)}</div>"
        "</section>"
        "<footer>Scoring: <b>wind_score &times; precip_score &times; (0.4 + 0.6 &times; tide_score)</b>. "
        "Wind and precip are hard multipliers; tide is a soft modifier so a "
        "glass-calm mid-cycle hour earns ~0.4 (Marginal) on big-swing days "
        "instead of being crushed to zero or inflated to Good. tide_score is "
        "1.0 at slack and decays linearly to 0; the half-window is sized per "
        "side by the adjacent swing \u2014 a 13 ft drop into slack gives a tight "
        "\u00b145 min before-window, a 4 ft rise out gives a generous \u00b13 hr "
        "after-window. Thresholds: &lt;3 ft = 6 hr, 3\u20136 = 3 hr, 6\u20139 = 90 min, "
        "\u22659 ft = 45 min. wind_score takes the worse of two tiers \u2014 "
        "sustained &lt;10/&lt;15/&lt;25/\u226525 mph and gust &lt;15/&lt;20/&lt;25/\u226530 mph "
        "\u2014 mapped to 1.0/0.7/0.3/0.0 so a calm-but-gusty hour can't earn "
        "Prime. Slack-tide chart badge label always matches the heatmap tier "
        "(PRIME if cell \u22650.9, else GOOD) so the chart and the cell can't "
        "disagree. Gold badge + GLASS pill = slack with gust \u226410 &amp; "
        "wind \u22647 AND the cell scores Prime \u2014 the standout combo. "
        "Per-day badge: "
        "<b>GLASS</b> (max wind \u22647 &amp; gust \u226410), <b>WINDY</b> (max wind &gt;15 "
        "or gust \u226525), <b>BREEZY</b> in between. "
        "Tide curve color matches the heatmap tier \u2014 "
        "<b>green</b>=Prime, <b>light green</b>=Good, <b>yellow</b>=Marginal, <b>orange</b>=Poor, <b>red</b>=Terrible. "
        "Chart shading: night (dark grey) \u2192 nautical twilight (light grey) \u2192 daylight (clear); "
        "labeled at first light, sunrise, sunset, last light per day. "
        f"Wind blend: {' + '.join(data.get('wind_sources') or ['Open-Meteo'])}. "
        "Other sources: NOAA NWS \u00b7 NOAA CO-OPS \u00b7 NDBC.</footer>"
        "</body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        out_path = Path(argv[0])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        out_path = reports / f"fishing_ma9_{dt.date.today().isoformat()}.html"
    out_path.write_text(build_html(), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
