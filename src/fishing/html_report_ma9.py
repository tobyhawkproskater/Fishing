"""MA9-only 7-day report with a tide x weather fishability heatmap.

Scoring model (per daylight hour, 5 AM - 9 PM PT):
    score = tide_score * wind_score * precip_score
where
    tide_score   = 1.0 at slack (nearest H/L), linearly to 0 at >=60 min away
    wind_score   = 1.0 / 0.7 / 0.3 / 0.0 for gusts <12 / <18 / <25 / >=25 mph
    precip_score = 1.0 if <0.05 in/h, else 0.5

In addition, each hour gets a *category* (used to highlight ideal slack
windows on the per-day tide wave):
    GREEN   slack +/- 1h, wind < 10 mph AND gust < 20 mph
    YELLOW  slack +/- 1h, wind 10-15 mph (gust < 20 mph)
    RED     slack +/- 1h, but wind > 15 mph OR gust >= 20 mph
    OFF     more than 1h from nearest predicted H or L tide

Slack is approximated by the nearest predicted high/low at Port Townsend
(NOAA CO-OPS 9444900). True Admiralty Inlet slack lags the H/L by 15-45 min;
+/- 1 hour around the event is a reasonable all-of-MA9 window.

Run:
    python -m fishing.html_report_ma9
    python -m fishing.html_report_ma9 path\\out.html
"""
from __future__ import annotations

import datetime as dt
import html
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import ROOT, kb
from .distance import haversine_km
from .stations import PLACES, WATERS
from .weather import ndbc_latest, noaa_tides, nws_marine_forecast, open_meteo, wind_blend
from .html_report import (
    CSS, _deg_to_compass, _fmt, _h, _kind_tag, _render_buoy,
    _render_rules, _render_tides, _group_tides_by_day, _wind_cell_class,
)

DAYS = 7
HOUR_START = 5   # 5 AM PT
HOUR_END = 21    # 9 PM PT inclusive label, exclusive end
WATER_KEY = "ma9"


# --- scoring -----------------------------------------------------------------
#
# Two scores per hour:
#   1. Continuous fishability `score` in [0..1] = tide * wind * precip
#      (drives the heatmap colors and KPIs).
#   2. Category in {GREEN, YELLOW, RED, OFF} based on slack +/- 1h and wind/gust
#      thresholds; used only to highlight the ideal slack windows on the
#      per-day tide wave SVG.

CAT_GREEN, CAT_YELLOW, CAT_RED, CAT_OFF = "green", "yellow", "red", "off"


def _nearest_tide(hour_iso: str, tide_events: list[dict]) -> tuple[Optional[float], Optional[dict]]:
    """Return (minutes_to_nearest_event, nearest_event)."""
    if not tide_events:
        return None, None
    h = dt.datetime.fromisoformat(hour_iso)
    best_dt = None
    best_ev = None
    for ev in tide_events:
        try:
            t = dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M")
        except Exception:
            continue
        d = abs((h - t).total_seconds()) / 60.0
        if best_dt is None or d < best_dt:
            best_dt = d
            best_ev = ev
    return best_dt, best_ev


def _tide_score(minutes_to_slack: Optional[float]) -> float:
    if minutes_to_slack is None:
        return 0.0
    if minutes_to_slack >= 60.0:
        return 0.0
    return max(0.0, 1.0 - minutes_to_slack / 60.0)


def _wind_score(gust_mph: Optional[float]) -> float:
    g = gust_mph if gust_mph is not None else 0.0
    if g < 12: return 1.0
    if g < 18: return 0.7
    if g < 25: return 0.3
    return 0.0


def _precip_score(precip_in: Optional[float]) -> float:
    p = precip_in if precip_in is not None else 0.0
    return 1.0 if p < 0.05 else 0.5


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


def _score_cell_class(score: float) -> tuple[str, str]:
    """Continuous score -> (background, foreground) for heatmap cells.
    Tiers: Prime / Good / Marginal / Poor / Terrible."""
    if score >= 0.85: return ("#0078D4", "#FFFFFF")  # Prime     - blue
    if score >= 0.45: return ("#DFF6DD", "#0B6A0B")  # Good      - light green
    if score >= 0.25: return ("#FFF4CE", "#5C4400")  # Marginal  - light yellow
    if score > 0.0:   return ("#FED9B7", "#8A2900")  # Poor      - light orange
    return ("#F3F2F1", "#A19F9D")                    # Terrible  - neutral


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

def _assemble(start: dt.date) -> dict:
    w = WATERS[WATER_KEY]
    om = wind_blend(w.lat, w.lon, hours=DAYS * 24)
    if "error" in om or not om.get("hours"):
        # Last-ditch fallback to single-source Open-Meteo if the blend failed.
        om = open_meteo(w.lat, w.lon, hours=DAYS * 24)
    hours = {h["time"]: h for h in om.get("hours", [])}

    # Pad ±1 day so cosine tide interpolation has bracketing events at the edges.
    tide_begin = (start - dt.timedelta(days=1)).isoformat()
    tides = noaa_tides(w.tide_station, date=tide_begin, days=DAYS + 2)
    tide_events = tides.get("tides", []) or []

    grid: list[dict] = []
    all_windows: list[dict] = []

    for di in range(DAYS):
        day = start + dt.timedelta(days=di)
        row = {"date": day, "cells": []}
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
            in_slack = mins is not None and mins <= 60.0
            ts = _tide_score(mins)
            ws = _wind_score(gust)
            ps = _precip_score(precip)
            score = ts * ws * ps
            category = _classify(in_slack, wind, gust)

            cell = {
                "time": key, "hour": hr, "score": score,
                "tide_score": ts, "wind_score": ws, "precip_score": ps,
                "category": category,
                "in_slack": in_slack, "minutes_to_slack": mins,
                "nearest_tide": t_ev,
                "wind_mph": wind, "gust_mph": gust, "wind_dir_deg": wdir,
                "temp_f": temp, "precip_in": precip,
            }
            row["cells"].append(cell)

            # Best-windows leaderboard = runs of hours with usable score.
            if score >= 0.45:
                run.append(cell)
            else:
                if run:
                    all_windows.append(_summarize_run(run))
                    run = []
        if run:
            all_windows.append(_summarize_run(run))
        grid.append(row)

    all_windows.sort(key=lambda r: (-r["peak_score"], -r["hours"]))

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
            padding:8px 12px;box-shadow:var(--shadow-sm)}
.chart-card svg{display:block;width:100%;height:auto}
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
        for c in row["cells"]:
            bg, fg = _score_cell_class(c["score"])
            cls = "tide-marker" if c["hour"] in tide_hours_by_day.get(day.isoformat(), set()) else ""
            tip = _cell_tooltip(c)
            display = f"{c['score']:.2f}".lstrip("0") if c["score"] > 0 else ""
            cells.append(
                f"<td class='{cls}' style='background:{bg};color:{fg}' "
                f"title=\"{html.escape(tip)}\">{display}</td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    header = "<tr><th class='label'>Day</th>" + hour_headers + "</tr>"
    legend = (
        "<div class='legend'>"
        "<span><span class='sw' style='background:#0078D4'></span>Prime (\u22650.85)</span>"
        "<span><span class='sw' style='background:#DFF6DD'></span>Good</span>"
        "<span><span class='sw' style='background:#FFF4CE'></span>Marginal</span>"
        "<span><span class='sw' style='background:#FED9B7'></span>Poor</span>"
        "<span><span class='sw' style='background:#F3F2F1'></span>Terrible</span>"
        "<span style='margin-left:14px'>"
        "<span class='sw' style='background:#fff;outline:2px solid #005A9E;outline-offset:-2px'></span>"
        "tide event hour</span>"
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
                     key=lambda w: w["peak_score"], default=None)
    best_overall = windows[0] if windows else None

    ideal_hours = sum(1 for row in data["grid"] for c in row["cells"] if c["score"] >= 0.85)
    blown = sum(1 for row in data["grid"] for c in row["cells"]
                if c.get("wind_score", 1.0) == 0 and c["in_slack"])

    def _fmt_window(w: Optional[dict]) -> tuple[str, str]:
        if not w:
            return ("\u2014", "")
        date = w["date"].strftime("%a")
        start = f"{w['start_hour'] % 12 or 12}{'a' if w['start_hour'] < 12 else 'p'}"
        end = f"{(w['end_hour']+1) % 12 or 12}{'a' if (w['end_hour']+1) < 12 else 'p'}"
        return (f"{date} {start}\u2013{end}", f"score {w['peak_score']:.2f}")

    today_val, today_sub = _fmt_window(best_today)
    overall_val, overall_sub = _fmt_window(best_overall)

    kpis = [
        ("",       "From Cabin",       f"{data['distance_cabin_mi']} mi", "great-circle"),
        ("teal",   "From Home",        f"{data['distance_home_mi']} mi",  "great-circle"),
        ("green",  "Best Today",       today_val,   today_sub),
        ("",       "Best This Week",   overall_val, overall_sub),
        ("purple", "Ideal Hours (7d)", str(ideal_hours), "score \u2265 0.85"),
        ("red" if blown else "",
                   "Blown-Out Hours",  str(blown), "gust \u2265 25 mph in slack"),
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
                        events_dt: list[tuple[dt.datetime, float, str]]) -> str:
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

    # Non-daylight shading (before HOUR_START, after HOUR_END+1) + 30-min gridlines.
    # Drawn before the tide curve so everything else paints on top.
    parts.append(
        f"<rect x='{PL}' y='{PT}' width='{x_of(HOUR_START) - PL:.1f}' height='{IH}' "
        f"fill='#D2D0CE' opacity='0.55'/>"
    )
    parts.append(
        f"<rect x='{x_of(HOUR_END + 1):.1f}' y='{PT}' "
        f"width='{(PL + IW) - x_of(HOUR_END + 1):.1f}' height='{IH}' "
        f"fill='#D2D0CE' opacity='0.55'/>"
    )
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
            "prime":    ("#0078D4", 0.30),
            "good":     ("#107C10", 0.20),
            "marginal": ("#FFF4CE", 0.85),
            "poor":     ("#FED9B7", 0.85),
        }
        TIER_STROKE = {
            "prime":    "#0078D4",
            "good":     "#107C10",
            "marginal": "#B07900",
            "poor":     "#D04A0A",
        }

        def _tier(score: float) -> Optional[str]:
            if score >= 0.85:
                return "prime"
            if score >= 0.45:
                return "good"
            if score >= 0.25:
                return "marginal"
            if score > 0.0:
                return "poor"
            return None  # Terrible \u2014 leave default tide color

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

        # Slack-moment marker spans = Prime or Good spans only.
        spans: list[tuple[float, float]] = [
            (lo, hi) for tier, lo, hi in tier_spans if tier in ("prime", "good")
        ]

        # BEST-MOMENT marker: any predicted H/L on this day that falls inside a
        # GREEN span is the literal peak of the fishability score. Mark the exact
        # minute with a vertical green line + star + time across the top.
        best_moments: list[tuple[dt.datetime, float, str]] = []
        for t, v, kind in events_dt:
            if t.date() != day_date:
                continue
            hr_f = t.hour + t.minute / 60.0
            if any(lo <= hr_f <= hi for lo, hi in spans):
                best_moments.append((t, v, kind))
        for t, v, kind in best_moments:
            hr_f = t.hour + t.minute / 60.0
            cx = x_of(hr_f)
            # PRIME upgrade: glass-calm slack (gust <= 10 AND wind <= 7 at the
            # nearest hour). Paint the marker in Microsoft gold with a halo so
            # the truly stand-out windows leap off the page.
            slack_hr = int(round(hr_f))
            slack_cell = next(
                (c for c in cells if c["hour"] == slack_hr), None
            )
            prime = bool(
                slack_cell
                and (slack_cell.get("gust_mph") or 0) <= 10
                and (slack_cell.get("wind_mph") or 0) <= 7
            )

            if prime:
                # Soft gold vertical band behind the green stroke.
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
                label = f"\u2605 PRIME {_fmt_clock(t)}"
                badge_h = 18
                font_sz = 11
            else:
                parts.append(
                    f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                    f"stroke='#107C10' stroke-width='1.4' stroke-dasharray='5,3' opacity='0.9'/>"
                )
                badge_fill = "#107C10"
                badge_text = "#FFFFFF"
                label = f"\u2605 GOOD {_fmt_clock(t)}"
                badge_h = 15
                font_sz = 10

            # Above the chart frame, on a dedicated shelf between the score
            # strip (y=32) and the chart top (y=PT=78).
            badge_y = 50
            text_w = 8 + len(label) * 6
            bx = max(PL + 2, min(cx - text_w / 2, PL + IW - text_w - 2))
            parts.append(
                f"<rect x='{bx:.1f}' y='{badge_y:.1f}' width='{text_w}' height='{badge_h}' "
                f"rx='3' fill='{badge_fill}'/>"
            )
            parts.append(
                f"<text x='{bx + text_w/2:.1f}' y='{badge_y + badge_h - 4:.1f}' "
                f"text-anchor='middle' font-size='{font_sz}' font-weight='700' "
                f"fill='{badge_text}'>{label}</text>"
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
        "background:#0078D4;vertical-align:middle;margin-right:6px'></span>"
        "Tide curve color = score tier (Prime/Good/Marginal/Poor)</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:14px;"
        "border-radius:3px;background:#107C10;color:#fff;text-align:center;font-size:10px;"
        "line-height:14px;vertical-align:middle;margin-right:6px'>\u2605</span>"
        "<strong>GOOD</strong> &mdash; slack tide inside a Good span</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:14px;"
        "border-radius:3px;background:#FFB900;color:#3B2F00;text-align:center;font-size:11px;"
        "line-height:14px;font-weight:700;vertical-align:middle;margin-right:6px'>\u2605</span>"
        "<strong>PRIME</strong> &mdash; glass-calm slack (gust \u226410 mph &amp; wind \u22647 mph)</span>"
        "<span><span class='swatch' style='display:inline-block;width:14px;height:10px;"
        "background:#0078D4;vertical-align:middle;margin-right:6px'></span>"
        "Hourly fishability score (above frame)</span>"
        "</div>"
    )

    charts = []
    for row in data["grid"]:
        svg = _render_daily_chart(row["date"], row["cells"], data["hours_raw"], events_dt)
        charts.append(f"<div class='chart-card'>{svg}</div>")

    return legend + f"<div class='chart-grid'>{''.join(charts)}</div>"


def build_html(start: Optional[dt.date] = None) -> str:
    start = start or dt.date.today()
    data = _assemble(start)
    w = data["water"]

    sub = f"{_kind_tag(w.kind)} {w.lat:.3f}, {w.lon:.3f} · tide station Port Townsend (9444900)"

    # Cards
    cards = []

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

    # Best windows
    cards.append(
        "<div class='card'><h3>Best windows (next 7 days)</h3>"
        + _render_window_list(data["windows"]) + "</div>"
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

    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>MA9 Fishability {data['start']} \u2013 {data['end']}</title>"
        f"<style>{CSS}{EXTRA_CSS}</style></head><body>"
        "<header class='page'>"
        "<h1><div class='brand-logo'>"
        "<span></span><span></span><span></span><span></span>"
        "</div>Marine Area 9 \u2014 Fishability Report</h1>"
        f"<div class='meta'>{data['start'].strftime('%A, %B %d')} \u2013 "
        f"{data['end'].strftime('%A, %B %d, %Y')} \u00b7 generated {generated} "
        f"\u00b7 <a href='mobile.html' style='color:#fff;text-decoration:underline'>"
        f"Mobile view \u2192</a></div>"
        "</header>"
        f"<section class='water' id='ma9'>"
        f"<h2>{_h(w.name)}</h2>"
        f"<div class='sub'>{sub}</div>"
        f"{_lingcod_alert(start)}"
        f"{_render_top_kpis(data)}"
        f"<div class='grid'>{''.join(cards)}</div>"
        "</section>"
        "<footer>Scoring: tide_score (1.0 at slack \u2192 0 at \u00b160 min) "
        "\u00d7 wind_score (1.0/0.7/0.3/0.0 for gusts &lt;12 / &lt;18 / &lt;25 / \u226525 mph) "
        "\u00d7 precip_score. Tide curve color matches the heatmap tier \u2014 "
        "<b>blue</b>=Prime, <b>green</b>=Good, <b>yellow</b>=Marginal, <b>orange</b>=Poor, "
        "plain blue = Terrible. Daylight only (5 AM \u2013 9 PM PT). "
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
