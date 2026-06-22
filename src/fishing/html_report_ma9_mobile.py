"""Mobile-tuned MA9 fishability report.

Reuses the same data assembly as ``html_report_ma9`` but renders a single-column
layout with larger fonts, portrait-friendly SVG aspect, and tighter cards meant
for an iPhone-sized viewport. Drops the wide heatmap and the long-form
regulations / marine-zone text (still available in the desktop report).

Run:
    python -m fishing.html_report_ma9_mobile
    python -m fishing.html_report_ma9_mobile path\\out.html
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

from . import ROOT
from .html_loadout import LOADOUT_CSS, render_nav
from .html_report import CSS, _h, _kind_tag
from .html_report_ma9 import (
    CAT_GREEN, DAYS, EXTRA_CSS, HOUR_END, HOUR_START,
    _assemble, _day_wind_badge, _fmt_clock, _lingcod_alert, _score_cell_class, _tide_at,
)


# --- mobile-tuned per-day chart ---------------------------------------------

def _render_daily_chart_mobile(day_date: dt.date, cells: list[dict],
                               hours_raw: list[dict],
                               events_dt: list[tuple[dt.datetime, float, str]]) -> str:
    """Portrait-friendly SVG: same data layers as desktop, larger type."""
    W, H = 600, 320
    PL, PR, PT, PB = 40, 40, 78, 40
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
        f"<text x='{PL}' y='22' font-size='17' font-weight='700' "
        f"fill='var(--ms-text)'>{day_date.strftime('%A %b %#d')}</text>"
    )

    # (Score is shown directly via the tide curve color, no separate strip.)

    # Non-daylight shading + hourly vertical gridlines (no half-hours on mobile;
    # too noisy at this width).
    parts.append(
        f"<rect x='{PL}' y='{PT}' width='{x_of(HOUR_START) - PL:.1f}' height='{IH}' "
        f"fill='#D2D0CE' opacity='0.55'/>"
    )
    parts.append(
        f"<rect x='{x_of(HOUR_END + 1):.1f}' y='{PT}' "
        f"width='{(PL + IW) - x_of(HOUR_END + 1):.1f}' height='{IH}' "
        f"fill='#D2D0CE' opacity='0.55'/>"
    )
    for hr in range(0, 25):
        cx = x_of(hr)
        parts.append(
            f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
            f"stroke='#C8C6C4' stroke-width='1' opacity='0.55'/>"
        )

    # Tide curve
    base = dt.datetime.combine(day_date, dt.time())
    flat_events = [(e[0], e[1]) for e in events_dt]
    tide_pts: list[tuple[float, float]] = []
    for m in range(0, 24 * 60 + 1, 15):
        target = base + dt.timedelta(minutes=m)
        v = _tide_at(flat_events, target)
        if v is not None:
            tide_pts.append((m / 60.0, v))

    spans: list[tuple[float, float]] = []
    if tide_pts:
        area = "M " + f"{x_of(tide_pts[0][0]):.1f},{PT + IH:.1f} "
        area += " ".join(f"L {x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in tide_pts)
        area += f" L {x_of(tide_pts[-1][0]):.1f},{PT + IH:.1f} Z"
        parts.append(f"<path d='{area}' fill='#DEECF9' stroke='none' opacity='0.85'/>")
        line = "M " + " L ".join(f"{x_of(hr):.1f},{y_tide(v):.1f}" for hr, v in tide_pts)
        parts.append(f"<path d='{line}' fill='none' stroke='#005A9E' stroke-width='2.5'/>")

        # Tier overlay across the full heatmap palette (Prime/Good/Marginal/Poor/Terrible).
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

        def _tier(score: float):
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
        cur_tier = None
        cur_lo = None
        prev_h = None
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
            sw = 4 if tier in ("prime", "good") else 2.8
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

        spans = [(lo, hi) for tier, lo, hi in tier_spans if tier in ("prime", "good")]

        # Best-moment markers (and PRIME upgrade)
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
            slack_hr = int(round(hr_f))
            slack_cell = next((c for c in cells if c["hour"] == slack_hr), None)
            glass = bool(
                slack_cell
                and (slack_cell.get("gust_mph") or 0) <= 10
                and (slack_cell.get("wind_mph") or 0) <= 7
            )
            score_val = (slack_cell or {}).get("score")
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

            if glass:
                band_w = max(10.0, IW / 24.0 * 0.6)
                parts.append(
                    f"<rect x='{cx - band_w/2:.1f}' y='{PT}' width='{band_w:.1f}' "
                    f"height='{IH}' fill='#FFB900' opacity='0.18'/>"
                )
                parts.append(
                    f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                    f"stroke='#D29200' stroke-width='2.5' opacity='0.95'/>"
                )
                badge_fill, badge_text = "#FFB900", "#3B2F00"
                badge_h, font_sz = 22, 14
            else:
                parts.append(
                    f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT}' y2='{PT + IH}' "
                    f"stroke='#107C10' stroke-width='1.8' stroke-dasharray='6,3' opacity='0.9'/>"
                )
                badge_fill = "#107C10" if tier_name == "good" else "#054B05"
                badge_text = "#FFFFFF"
                badge_h, font_sz = 19, 12

            label = (
                f"\u2605 {tier_label} {score_str} {_fmt_clock(t)}"
                if score_str
                else f"\u2605 {tier_label} {_fmt_clock(t)}"
            )

            badge_y = 54
            text_w = 12 + len(label) * 7
            pill_text = "GLASS"
            pill_w = 12 + len(pill_text) * 7 if glass else 0
            pill_gap = 5 if glass else 0
            group_w = text_w + pill_gap + pill_w
            bx = max(PL + 2, min(cx - group_w / 2, PL + IW - group_w - 2))
            parts.append(
                f"<rect x='{bx:.1f}' y='{badge_y:.1f}' width='{text_w}' height='{badge_h}' "
                f"rx='3' fill='{badge_fill}'/>"
            )
            parts.append(
                f"<text x='{bx + text_w/2:.1f}' y='{badge_y + badge_h - 5:.1f}' "
                f"text-anchor='middle' font-size='{font_sz}' font-weight='700' "
                f"fill='{badge_text}'>{label}</text>"
            )
            if glass:
                px = bx + text_w + pill_gap
                parts.append(
                    f"<rect x='{px:.1f}' y='{badge_y:.1f}' width='{pill_w}' "
                    f"height='{badge_h}' rx='{badge_h/2:.1f}' fill='#FFB900' "
                    f"stroke='#D29200' stroke-width='1'/>"
                )
                parts.append(
                    f"<text x='{px + pill_w/2:.1f}' y='{badge_y + badge_h - 5:.1f}' "
                    f"text-anchor='middle' font-size='12' font-weight='800' "
                    f"fill='#3B2F00'>{pill_text}</text>"
                )

    # Tide H/L markers
    for t, v, kind in events_dt:
        if t.date() != day_date:
            continue
        hr = t.hour + t.minute / 60
        cx, cy = x_of(hr), y_tide(v)
        parts.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='5' fill='#005A9E'/>")
        is_high = kind == "H"
        place_above = is_high
        if place_above and cy - 24 < PT + 2:
            place_above = False
        elif (not place_above) and cy + 30 > PT + IH - 2:
            place_above = True
        if place_above:
            ly_value, ly_time = cy - 11, cy - 24
        else:
            ly_value, ly_time = cy + 18, cy + 31
        parts.append(
            f"<text x='{cx:.1f}' y='{ly_value:.1f}' text-anchor='middle' font-size='12' "
            f"font-weight='700' fill='#005A9E'>{kind} {v:.1f}ft</text>"
        )
        parts.append(
            f"<text x='{cx:.1f}' y='{ly_time:.1f}' text-anchor='middle' "
            f"font-size='11' fill='var(--ms-text-secondary)'>"
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
            f"<path d='{gust_d}' fill='none' stroke='#D83B01' stroke-width='2' "
            f"stroke-dasharray='5,3' opacity='0.85'/>"
        )
        parts.append(
            f"<path d='{wind_d}' fill='none' stroke='#D83B01' stroke-width='2.8'/>"
        )

    # Temperature with min/max
    if day_hours:
        temp_pts = [(int(h["time"][11:13]), h.get("temp_f")) for h in day_hours
                    if h.get("temp_f") is not None]
        if temp_pts:
            temp_d = "M " + " L ".join(f"{x_of(hr + 0.5):.1f},{y_temp(v):.1f}" for hr, v in temp_pts)
            parts.append(
                f"<path d='{temp_d}' fill='none' stroke='#5C2D91' stroke-width='2' "
                f"stroke-dasharray='1,3' opacity='0.85'/>"
            )
            tmin = min(temp_pts, key=lambda p: p[1])
            tmax = max(temp_pts, key=lambda p: p[1])
            for hr, v in (tmin, tmax):
                parts.append(
                    f"<circle cx='{x_of(hr + 0.5):.1f}' cy='{y_temp(v):.1f}' r='4' "
                    f"fill='#5C2D91'/>"
                )
                anchor = "start" if hr < 18 else "end"
                dx = 8 if hr < 18 else -8
                parts.append(
                    f"<text x='{x_of(hr + 0.5) + dx:.1f}' y='{y_temp(v) - 6:.1f}' "
                    f"text-anchor='{anchor}' font-size='12' font-weight='700' "
                    f"fill='#5C2D91'>{v:.0f}\u00b0F</text>"
                )

    # +2 ft float line reference
    parts.append(
        f"<line x1='{PL}' x2='{W - PR}' y1='{y_tide(2):.1f}' y2='{y_tide(2):.1f}' "
        f"stroke='#A4262C' stroke-dasharray='5,3' opacity='0.75'/>"
    )
    parts.append(
        f"<text x='{PL + 6}' y='{y_tide(2) - 4:.1f}' text-anchor='start' "
        f"font-size='11' font-weight='700' fill='#A4262C'>+2 ft float</text>"
    )

    # Left axis (tide ft)
    for v in (0, 2, 5, 10):
        ly = y_tide(v)
        parts.append(
            f"<text x='{PL - 4}' y='{ly + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='#005A9E'>{v}</text>"
        )

    # Right axis (wind mph)
    for v in (0, 10, 20, 30):
        parts.append(
            f"<text x='{W - PR + 4}' y='{y_wind(v) + 4:.1f}' font-size='11' "
            f"fill='#D83B01'>{v}</text>"
        )

    # X-axis: every 3 h labeled, hourly ticks
    for hr in range(0, 25):
        cx = x_of(hr)
        tick_h = 5 if hr % 3 == 0 else 2
        parts.append(
            f"<line x1='{cx:.1f}' x2='{cx:.1f}' y1='{PT + IH}' y2='{PT + IH + tick_h}' "
            f"stroke='#A19F9D'/>"
        )
        if hr % 3 == 0:
            if hr == 0 or hr == 24:
                label = "12a"
            elif hr < 12:
                label = f"{hr}a"
            elif hr == 12:
                label = "12p"
            else:
                label = f"{hr - 12}p"
            parts.append(
                f"<text x='{cx:.1f}' y='{PT + IH + 18}' text-anchor='middle' font-size='11' "
                f"font-weight='600' fill='var(--ms-text-secondary)'>{label}</text>"
            )

    # Frame
    parts.append(
        f"<rect x='{PL}' y='{PT}' width='{IW}' height='{IH}' "
        f"fill='none' stroke='var(--ms-border)'/>"
    )
    parts.append("</svg>")
    return "".join(parts)


# --- mobile renderers --------------------------------------------------------

MOBILE_CSS = """
:root{--m-pad:12px}
body{margin:0;background:var(--ms-bg);font-family:var(--font-base);color:var(--ms-text);
     font-size:15px;line-height:1.4}
.m-header{background:linear-gradient(135deg,var(--ms-blue-darker) 0%,var(--ms-blue) 60%,var(--ms-cyan) 110%);
          color:#fff;padding:18px var(--m-pad) 14px}
.m-header h1{font-size:22px;margin:0 0 4px;font-weight:700;letter-spacing:.2px}
.m-header .meta{font-size:12px;opacity:.92}
.m-header a.desktop-link{display:inline-block;margin-top:8px;color:#fff;text-decoration:underline;
                         font-size:12px;opacity:.9}
.m-section{padding:0 var(--m-pad) 14px}
.m-card{background:var(--ms-card);border:1px solid var(--ms-border);border-radius:8px;
        padding:12px;margin-top:12px;box-shadow:var(--shadow-sm)}
.m-card h3{margin:0 0 10px;font-size:15px;font-weight:700;color:var(--ms-blue-darker)}
.m-card svg{display:block;width:100%;height:auto}

.m-kpi-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.m-kpi{background:var(--ms-card);border:1px solid var(--ms-border);border-radius:6px;padding:10px}
.m-kpi .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--ms-text-secondary)}
.m-kpi .val{font-size:18px;font-weight:700;color:var(--ms-text);margin-top:2px}
.m-kpi .sub{font-size:11px;color:var(--ms-text-secondary);margin-top:1px}
.m-kpi.prime{background:linear-gradient(135deg,#FFF7DA 0%,#FFE8A3 100%);border-color:#D29200}
.m-kpi.prime .lbl{color:#8A6D00}
.m-kpi.prime .val{color:#3B2F00}
.m-kpi.good{background:#DFF6DD;border-color:#107C10}
.m-kpi.good .val{color:#0B6A0B}
.m-kpi.alert{background:#FED9B7;border-color:#D83B01}
.m-kpi.alert .val{color:#8A2900}

.m-window{display:flex;justify-content:space-between;align-items:center;
          padding:8px 0;border-bottom:1px solid var(--ms-divider);gap:10px}
.m-window:last-child{border-bottom:none}
.m-window .when{font-weight:700;color:var(--ms-text);font-size:14px}
.m-window .why{font-size:12px;color:var(--ms-text-secondary);margin-top:2px}
.m-window .score{font-weight:700;color:var(--ms-blue-darker);font-size:14px;
                 padding:4px 8px;background:#DEECF9;border-radius:12px;white-space:nowrap}
.m-window.prime .score{background:#FFB900;color:#3B2F00}

.m-tide-row{display:flex;justify-content:space-between;padding:4px 0;font-size:13px;
            font-variant-numeric:tabular-nums;border-bottom:1px solid var(--ms-divider)}
.m-tide-row:last-child{border-bottom:none}
.m-tide-row .kind{font-weight:700;color:var(--ms-blue-darker);width:24px}
.m-tide-row .time{flex:1;color:var(--ms-text-secondary)}
.m-tide-row .ht{font-weight:700}

.m-alert{padding:10px 12px;border-radius:6px;margin-top:12px;font-size:13px;
         border-left:4px solid var(--ms-green);background:#DFF6DD;color:#0B6A0B}
.m-day-hd{display:flex;justify-content:space-between;align-items:center;
          gap:6px;margin-bottom:6px;flex-wrap:wrap}
.m-day-hd .pills{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.m-day-hd .pill{font-size:11px;padding:3px 8px;border-radius:10px;font-weight:700;
                letter-spacing:0.04em}
.m-day-hd .pill.green{background:#DFF6DD;color:#0B6A0B}
.m-day-hd .pill.prime{background:#FFB900;color:#3B2F00}
.m-day-hd .pill.dim{background:#F3F2F1;color:#605E5C}
.m-day-hd .pill.glass{background:#DFF6DD;color:#0B6A0B;border:1px solid #92C593}
.m-day-hd .pill.breezy{background:#FFF4CE;color:#5C4400;border:1px solid #E8C77A}
.m-day-hd .pill.windy{background:#FED9B7;color:#8A2900;border:1px solid #E89F70}

footer{padding:18px var(--m-pad) 28px;font-size:11px;color:var(--ms-text-secondary);
       text-align:center}
"""


def _peak_hour_summary(row: dict) -> tuple[str, str]:
    """Return ('great'/'prime'/'good'/'meh'/'off', '<peak description>') for a day row."""
    cells = row["cells"]
    if not cells:
        return ("off", "no data")
    peak = max(cells, key=lambda c: c["score"])
    prime = (peak["category"] == CAT_GREEN
             and (peak.get("gust_mph") or 0) <= 10
             and (peak.get("wind_mph") or 0) <= 7)
    if prime and peak["score"] >= 0.9:
        tier = "prime"
    elif peak["score"] >= 0.9:
        tier = "great"
    elif peak["score"] >= 0.75:
        tier = "good"
    elif peak["score"] > 0:
        tier = "meh"
    else:
        tier = "off"
    return tier, f"peak {peak['score']:.2f}"


def _render_mobile_kpis(data: dict) -> str:
    windows = data["windows"]
    today = data["start"]
    best_today = max((w for w in windows if w["date"] == today),
                     key=lambda w: w["quality"], default=None)
    best_overall = windows[0] if windows else None

    ideal_hours = sum(1 for row in data["grid"] for c in row["cells"] if c["score"] >= 0.9)
    prime_count = 0
    for row in data["grid"]:
        for c in row["cells"]:
            if (c["category"] == CAT_GREEN and (c.get("gust_mph") or 0) <= 10
                    and (c.get("wind_mph") or 0) <= 7 and c["score"] >= 0.9):
                prime_count += 1
                break  # one per day max

    def _fmt_window(w: Optional[dict]) -> tuple[str, str]:
        if not w:
            return ("\u2014", "")
        date = w["date"].strftime("%a")
        start_h, end_h = w["start_hour"], w["end_hour"] + 1
        s_hh = start_h % 12 or 12
        e_hh = end_h % 12 or 12
        s_ap = "a" if start_h < 12 else "p"
        e_ap = "a" if end_h < 12 else "p"
        hrs = w["hours"]
        hr_lbl = "hr" if hrs == 1 else "hrs"
        return (f"{date} {s_hh}{s_ap}\u2013{e_hh}{e_ap}",
                f"peak {w['peak_score']:.2f} \u00b7 {hrs} {hr_lbl}")

    today_val, today_sub = _fmt_window(best_today)
    overall_val, overall_sub = _fmt_window(best_overall)

    today_cls = "good" if best_today and best_today["peak_score"] >= 0.75 else ""
    overall_cls = ("prime" if prime_count > 0 and best_overall and best_overall["peak_score"] >= 0.9
                   else ("good" if best_overall and best_overall["peak_score"] >= 0.75 else ""))

    kpis = [
        (today_cls,   "Best Today",      today_val,   today_sub),
        (overall_cls, "Best 7 Days",     overall_val, overall_sub),
        ("good" if ideal_hours else "",  "Ideal Hrs",   str(ideal_hours), "score \u22650.9"),
        ("prime" if prime_count else "", "PRIME days",  str(prime_count), "glass-calm slack"),
    ]
    cells = []
    for cls, lbl, val, sub in kpis:
        cells.append(
            f"<div class='m-kpi {cls}'><div class='lbl'>{_h(lbl)}</div>"
            f"<div class='val'>{_h(val)}</div>"
            + (f"<div class='sub'>{_h(sub)}</div>" if sub else "")
            + "</div>"
        )
    return f"<div class='m-kpi-grid'>{''.join(cells)}</div>"


def _render_mobile_windows(windows: list[dict], limit: int = 6) -> str:
    if not windows:
        return "<p style='color:var(--ms-text-secondary);font-size:13px'>No qualifying windows in the next 7 days.</p>"
    items = []
    for w in windows[:limit]:
        date = w["date"].strftime("%a %b %#d")
        start_h, end_h = w["start_hour"], w["end_hour"] + 1
        s = f"{start_h % 12 or 12}{'a' if start_h < 12 else 'p'}"
        e = f"{end_h % 12 or 12}{'a' if end_h < 12 else 'p'}"
        tide_str = (f"near {w['tide_kind']} {w['tide_time']}"
                    if w.get("tide_kind") else "")
        why = f"{tide_str} \u00b7 gust {w['max_gust']:.0f} mph \u00b7 {w['avg_temp']:.0f}\u00b0F"
        cls = "prime" if w["peak_score"] >= 0.9 and w.get("max_gust", 99) <= 10 else ""
        items.append(
            f"<div class='m-window {cls}'><div>"
            f"<div class='when'>{date} \u00b7 {s}\u2013{e}</div>"
            f"<div class='why'>{why}</div></div>"
            f"<span class='score'>{w['peak_score']:.2f}</span></div>"
        )
    return "".join(items)


def _render_mobile_tides_day(day: dt.date, events: list[dict]) -> str:
    day_events = [e for e in events if (e.get("t") or "")[:10] == day.isoformat()]
    rows = []
    for e in day_events:
        t = e.get("t", "")
        try:
            ts = dt.datetime.strptime(t, "%Y-%m-%d %H:%M")
            time_str = _fmt_clock(ts)
        except Exception:
            time_str = t[11:16]
        rows.append(
            f"<div class='m-tide-row'>"
            f"<span class='kind'>{e.get('type','')}</span>"
            f"<span class='time'>{time_str}</span>"
            f"<span class='ht'>{e.get('v','')} ft</span>"
            f"</div>"
        )
    return "".join(rows)


def _lingcod_alert_mobile(start: dt.date) -> str:
    season_end = dt.date(start.year, 6, 15)
    if start > season_end:
        return ""
    days_left = (season_end - start).days
    return (f"<div class='m-alert'><strong>Lingcod open</strong> through Jun 15 "
            f"(26\u2033\u201336\u2033 slot, 1/day, descender required). "
            f"{days_left} day(s) left.</div>")


# --- page assembly -----------------------------------------------------------

def build_html(start: Optional[dt.date] = None, data: Optional[dict] = None) -> str:
    start = start or dt.date.today()
    if data is None:
        data = _assemble(start)
    w = data["water"]
    generated = dt.datetime.now().strftime("%b %d, %#I:%M %p")

    # Pre-parse tide events into datetimes for the SVG renderer.
    events_dt: list[tuple[dt.datetime, float, str]] = []
    for ev in data["tide_events"]:
        try:
            t = dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M")
            events_dt.append((t, float(ev["v"]), ev.get("type", "")))
        except Exception:
            continue
    events_dt.sort(key=lambda e: e[0])

    # Per-day cards
    day_cards = []
    for row in data["grid"]:
        day = row["date"]
        tier, peak_desc = _peak_hour_summary(row)
        pill_cls = {"prime": "prime", "great": "green", "good": "green",
                    "meh": "dim", "off": "dim"}[tier]
        pill_label = {"prime": "PRIME", "great": "GREAT", "good": "GOOD",
                      "meh": "fair", "off": "off"}[tier]
        wind_label, wind_cls = _day_wind_badge(row)
        wind_pill = (
            f"<span class='pill {wind_cls}'>{wind_label}</span>"
            if wind_label else ""
        )
        tide_rows = _render_mobile_tides_day(day, data["tide_events"])
        svg = _render_daily_chart_mobile(day, row["cells"], data["hours_raw"], events_dt)
        day_cards.append(
            f"<div class='m-card'>"
            f"<div class='m-day-hd'>"
            f"<h3 style='margin:0'>{day.strftime('%A %b %#d')}</h3>"
            f"<span class='pills'>{wind_pill}"
            f"<span class='pill {pill_cls}'>{pill_label} \u00b7 {peak_desc}</span>"
            f"</span>"
            f"</div>"
            f"{svg}"
            + (f"<div style='margin-top:8px'>{tide_rows}</div>" if tide_rows else "")
            + "</div>"
        )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>"
        "<meta name='apple-mobile-web-app-capable' content='yes'>"
        "<meta name='apple-mobile-web-app-status-bar-style' content='black-translucent'>"
        "<meta name='apple-mobile-web-app-title' content='MA9 Fishing'>"
        "<meta name='theme-color' content='#005A9E'>"
        f"<title>MA9 \u00b7 {data['start'].strftime('%b %#d')}</title>"
        f"<style>{CSS}{EXTRA_CSS}{MOBILE_CSS}{LOADOUT_CSS}</style></head><body>"
        "<header class='m-header'>"
        "<h1>MA9 Fishing</h1>"
        f"<div class='meta'>{data['start'].strftime('%a %b %#d')} \u2013 "
        f"{data['end'].strftime('%a %b %#d')} \u00b7 updated {generated}</div>"
        "<a class='desktop-link' href='index.html'>Full desktop view \u2192</a>"
        "</header>"
        f"{render_nav('mobile')}"
        "<section class='m-section'>"
        + _lingcod_alert_mobile(start)
        + _render_mobile_kpis(data)
        + "<div class='m-card'><h3>Best windows (7 days)</h3>"
        + _render_mobile_windows(data["windows"]) + "</div>"
        + "".join(day_cards)
        + "</section>"
        "<footer>"
        f"<div>{_h(w.name)} \u00b7 tide station Hansville (9445526)</div>"
        "<div>Score = wind \u00d7 precip \u00d7 (0.4 + 0.6 \u00d7 tide). Wind/precip are hard "
        "multipliers; tide is a soft modifier so flat-calm mid-cycle hours "
        "land at ~0.4 (Marginal). Tide half-window scales with the adjacent "
        "swing per side (\u22659 ft = 45 min, &lt;3 ft = 6 hr). Wind score = "
        "worse of two tiers \u2014 sustained &lt;10/&lt;15/&lt;25/\u226525 mph and gust "
        "&lt;15/&lt;20/&lt;25/\u226530 mph \u2014 mapped to 1.0/0.7/0.3/0.0. "
        "Day badge: <b>GLASS</b> (max wind \u22647, "
        "gust \u226410), <b>WINDY</b> (wind &gt;15 or gust \u226525), <b>BREEZY</b> in "
        "between.</div>"
        "<div>Tide curve color matches the heatmap tier: "
        "<b>green</b>=Prime, <b>light green</b>=Good, <b>yellow</b>=Marginal, "
        "<b>orange</b>=Poor, <b>red</b>=Terrible.</div>"
        f"<div>Wind blend: {' + '.join(data.get('wind_sources') or ['Open-Meteo'])} \u00b7 "
        "NOAA NWS \u00b7 NOAA CO-OPS \u00b7 NDBC</div>"
        "</footer>"
        "</body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        out_path = Path(argv[0])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        out_path = reports / f"fishing_ma9_mobile_{dt.date.today().isoformat()}.html"
    out_path.write_text(build_html(), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
