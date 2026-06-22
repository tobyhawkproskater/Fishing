"""7-day HTML fishing conditions report covering all home waters.

Run:
    python -m fishing.html_report                       # → reports/fishing_7day_YYYY-MM-DD.html
    python -m fishing.html_report path\\to\\out.html      # explicit output path
"""
from __future__ import annotations

import datetime as dt
import html
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import ROOT, kb
from .distance import haversine_km
from .stations import PLACES, WATERS, Water
from .weather import (
    ndbc_latest,
    noaa_tides,
    nws_forecast,
    nws_marine_forecast,
    open_meteo,
)

DAYS = 7
CARDINALS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def _deg_to_compass(deg: Optional[float]) -> str:
    if deg is None:
        return "—"
    return CARDINALS[int((deg % 360) / 22.5 + 0.5) % 16]


def _aggregate_daily(hours: list[dict]) -> list[dict]:
    """Roll hourly Open-Meteo rows up to per-day summaries."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for h in hours:
        day = h["time"][:10]
        by_day[day].append(h)
    out = []
    for day in sorted(by_day):
        rows = by_day[day]
        temps = [r["temp_f"] for r in rows if r.get("temp_f") is not None]
        winds = [r["wind_mph"] for r in rows if r.get("wind_mph") is not None]
        gusts = [r["gust_mph"] for r in rows if r.get("gust_mph") is not None]
        precs = [r["precip_in"] for r in rows if r.get("precip_in") is not None]
        # Pick dominant wind direction from daytime hours (8a–8p) by gust weight
        day_rows = [r for r in rows if 8 <= int(r["time"][11:13]) <= 20]
        weighted = day_rows or rows
        if weighted:
            # vector-average using gust weight
            import math
            x = y = 0.0
            for r in weighted:
                d = r.get("wind_dir_deg")
                w = r.get("gust_mph") or r.get("wind_mph") or 1.0
                if d is None:
                    continue
                rad = math.radians(d)
                x += w * math.sin(rad)
                y += w * math.cos(rad)
            avg_dir = (math.degrees(math.atan2(x, y)) + 360) % 360 if (x or y) else None
        else:
            avg_dir = None
        out.append({
            "date": day,
            "temp_min_f": min(temps) if temps else None,
            "temp_max_f": max(temps) if temps else None,
            "wind_avg_mph": round(sum(winds) / len(winds), 1) if winds else None,
            "wind_max_mph": max(winds) if winds else None,
            "gust_max_mph": max(gusts) if gusts else None,
            "precip_in": round(sum(precs), 2) if precs else 0.0,
            "wind_dir_deg": avg_dir,
        })
    return out[:DAYS]


def _group_tides_by_day(tides: list[dict]) -> dict[str, list[dict]]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in tides:
        # 't' is "YYYY-MM-DD HH:MM"
        day = (t.get("t") or "")[:10]
        if day:
            by_day[day].append(t)
    return by_day


def _gather_water(w: Water, start: dt.date) -> dict:
    """Pull all data for one water for the 7-day window."""
    out: dict = {
        "water": w,
        "distance_home_mi": round(haversine_km(*PLACES["home"], w.lat, w.lon) * 0.621371, 1),
        "distance_cabin_mi": round(haversine_km(*PLACES["cabin"], w.lat, w.lon) * 0.621371, 1),
    }

    om = open_meteo(w.lat, w.lon, hours=DAYS * 24)
    out["open_meteo_error"] = om.get("error")
    out["daily"] = _aggregate_daily(om.get("hours", []))

    if w.kind == "marine":
        if w.nws_zone:
            out["marine"] = nws_marine_forecast(w.nws_zone)
        if w.tide_station:
            out["tides"] = noaa_tides(w.tide_station, date=start.isoformat(), days=DAYS)
        out["buoys"] = [ndbc_latest(b) for b in w.ndbc_buoys]
    else:
        out["nws"] = nws_forecast(w.lat, w.lon, hourly=False)

    # KB context
    base_name = w.name.split(" (")[0]
    regs = kb.regulations(base_name)
    out["rules_current"] = regs.get("current", [])[:3]
    out["rules_proposed"] = regs.get("proposed", [])[:2]

    return out


# --- HTML rendering (Microsoft Fluent theme) --------------------------------

CSS = """
:root{
  /* Brand blues */
  --ms-blue:#0078D4; --ms-blue-dark:#106EBE; --ms-blue-darker:#005A9E;
  --ms-cyan:#00BCF2; --ms-teal:#008272; --ms-purple:#5C2D91;
  /* Neutrals */
  --ms-bg:#FAF9F8; --ms-card:#FFFFFF; --ms-border:#E1DFDD; --ms-divider:#EDEBE9;
  --ms-text:#201F1E; --ms-text-secondary:#605E5C; --ms-text-disabled:#A19F9D;
  /* Status */
  --ms-green:#107C10; --ms-yellow:#F2C811; --ms-orange:#D83B01; --ms-red:#A4262C;
  /* Elevation */
  --shadow-sm:0 1px 2px rgba(0,0,0,0.08);
  --shadow-md:0 3px 8px rgba(0,0,0,0.12);
  --shadow-lg:0 6.4px 14.4px rgba(0,0,0,0.13), 0 1.2px 3.6px rgba(0,0,0,0.10);
}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI','Segoe UI Web','Segoe WP',-apple-system,BlinkMacSystemFont,Roboto,Helvetica,Arial,sans-serif;
     font-size:14px;line-height:1.45;color:var(--ms-text);background:var(--ms-bg)}

/* Header */
header.page{background:linear-gradient(135deg,var(--ms-blue-darker) 0%,var(--ms-blue) 60%,var(--ms-cyan) 110%);
            color:#fff;padding:20px 32px;box-shadow:var(--shadow-md);
            position:sticky;top:0;z-index:50}
header.page h1{margin:0;font-size:22px;font-weight:600;display:flex;align-items:center}
header.page .meta{margin-top:4px;font-size:13px;opacity:.92}
.brand-logo{display:inline-grid;grid-template-columns:repeat(2,10px);gap:2px;margin-right:10px;vertical-align:middle}
.brand-logo span{width:10px;height:10px;display:block}
.brand-logo span:nth-child(1){background:#F25022}
.brand-logo span:nth-child(2){background:#7FBA00}
.brand-logo span:nth-child(3){background:#00A4EF}
.brand-logo span:nth-child(4){background:#FFB900}

/* Tab nav */
nav.tabs{background:#fff;border-bottom:1px solid var(--ms-border);padding:0 32px;
         position:sticky;top:64px;z-index:40;display:flex;gap:4px;overflow-x:auto;
         box-shadow:var(--shadow-sm)}
nav.tabs a{color:var(--ms-text-secondary);text-decoration:none;font-weight:600;font-size:13px;
           padding:12px 14px;border-bottom:2px solid transparent;white-space:nowrap}
nav.tabs a:hover{color:var(--ms-blue)}
nav.tabs a.active{color:var(--ms-blue);border-bottom-color:var(--ms-blue)}

/* Water section */
.water{padding:24px 32px;border-bottom:1px solid var(--ms-divider)}
.water h2{margin:0 0 4px;font-size:20px;font-weight:600;color:var(--ms-blue);
          border-bottom:2px solid var(--ms-blue);padding-bottom:6px;display:inline-block}
.water .sub{color:var(--ms-text-secondary);font-size:13px;margin:4px 0 16px}

/* KPI strip */
.kpi-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--ms-card);border:1px solid var(--ms-border);border-radius:6px;
     padding:14px 16px;position:relative;box-shadow:var(--shadow-sm);overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--ms-blue)}
.kpi.green::before{background:var(--ms-green)}
.kpi.yellow::before{background:var(--ms-yellow)}
.kpi.orange::before{background:var(--ms-orange)}
.kpi.red::before{background:var(--ms-red)}
.kpi.purple::before{background:var(--ms-purple)}
.kpi.teal::before{background:var(--ms-teal)}
.kpi .lbl{font-size:11px;color:var(--ms-text-secondary);text-transform:uppercase;
          letter-spacing:.5px;font-weight:600;margin-bottom:4px}
.kpi .val{font-size:28px;font-weight:600;color:var(--ms-text);line-height:1.1}
.kpi .sub{font-size:12px;color:var(--ms-text-secondary);margin-top:4px}

/* Grid of detail cards */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:1000px){.grid{grid-template-columns:1fr}}
.card{background:var(--ms-card);border:1px solid var(--ms-border);border-radius:6px;
      padding:16px 18px;box-shadow:var(--shadow-sm)}
.card h3{margin:0 0 10px;font-size:14px;font-weight:600;color:var(--ms-purple);
         text-transform:uppercase;letter-spacing:.5px}

/* Tables */
table.dt{width:100%;border-collapse:collapse;font-size:13px}
table.dt th,table.dt td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--ms-divider)}
table.dt th{background:#F3F2F1;color:var(--ms-text-secondary);font-weight:600;font-size:12px;
            text-transform:uppercase;letter-spacing:.4px;position:sticky;top:0}
table.dt tr:hover td{background:#F3F2F1}
table.dt td.num,table.dt th.num{text-align:right;font-variant-numeric:tabular-nums}
table.dt tr:last-child td{border-bottom:none}

/* Wind heatmap cells */
.wind-cell-low{background:#DFF6DD;color:#0B6A0B;font-weight:600}
.wind-cell-mod{background:#FFF4CE;color:#796300;font-weight:600}
.wind-cell-high{background:#FED9B7;color:#8A2900;font-weight:600}
.wind-cell-xhigh{background:#FDE7E9;color:#8E1F25;font-weight:700}

/* Badges & tags */
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;
       font-weight:600;text-transform:uppercase;letter-spacing:.4px;color:#fff;margin-right:6px}
.badge.b{background:var(--ms-blue)} .badge.g{background:var(--ms-green)}
.badge.o{background:var(--ms-orange)} .badge.r{background:var(--ms-red)}
.badge.p{background:var(--ms-purple)} .badge.t{background:var(--ms-teal)}
.badge.y{background:var(--ms-yellow);color:#3B2F00}

.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;
     letter-spacing:.3px;margin-right:6px}
.tag.b{background:#DEECF9;color:var(--ms-blue-darker)}
.tag.g{background:#DFF6DD;color:#0B6A0B}
.tag.r{background:#FDE7E9;color:#8E1F25}
.tag.o{background:#FED9B7;color:#8A2900}
.tag.y{background:#FFF4CE;color:#796300}
.tag.p{background:#E8D6F2;color:#3B1854}

/* Tides */
.tide-up{color:var(--ms-blue-darker);font-weight:600}
.tide-dn{color:var(--ms-orange);font-weight:600}

/* Misc */
.dim{color:var(--ms-text-secondary)}
pre{background:#F3F2F1;color:var(--ms-text);padding:10px 12px;border-radius:4px;
    overflow:auto;font-size:12px;max-height:280px;border:1px solid var(--ms-border)}
details{margin-top:8px}
details summary{cursor:pointer;color:var(--ms-blue);font-size:13px;font-weight:600}
ul{margin:6px 0;padding-left:20px}
li{margin:4px 0}
footer{padding:18px 32px;color:var(--ms-text-secondary);font-size:12px;
       border-top:1px solid var(--ms-border);background:#fff}
"""


def _wind_cell_class(mph: Optional[float]) -> str:
    """Heatmap tint for a wind/gust speed."""
    if mph is None:
        return ""
    if mph >= 25:
        return "wind-cell-xhigh"
    if mph >= 18:
        return "wind-cell-high"
    if mph >= 12:
        return "wind-cell-mod"
    return "wind-cell-low"


def _kind_tag(kind: str) -> str:
    cls = {"marine": "tag b", "river": "tag g", "lake": "tag p"}.get(kind, "tag")
    return f"<span class='{cls}'>{kind.upper()}</span>"


def _fmt(v, suffix="", n=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{n}f}{suffix}"
    return f"{v}{suffix}"


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def _render_daily_table(daily: list[dict]) -> str:
    rows = []
    for d in daily:
        date = dt.date.fromisoformat(d["date"])
        dlabel = date.strftime("%a %b %#d")
        avg_cls = _wind_cell_class(d.get("wind_avg_mph"))
        gust_cls = _wind_cell_class(d.get("gust_max_mph"))
        rows.append(
            "<tr>"
            f"<td><strong>{dlabel}</strong></td>"
            f"<td class='num'>{_fmt(d.get('temp_min_f'),'°',0)} / {_fmt(d.get('temp_max_f'),'°',0)}</td>"
            f"<td class='num {avg_cls}'>{_fmt(d.get('wind_avg_mph'),' mph',0)}</td>"
            f"<td class='num {gust_cls}'>{_fmt(d.get('gust_max_mph'),' mph',0)}</td>"
            f"<td>{_deg_to_compass(d.get('wind_dir_deg'))}</td>"
            f"<td class='num'>{_fmt(d.get('precip_in'),'″',2)}</td>"
            "</tr>"
        )
    return (
        "<table class='dt'><thead><tr>"
        "<th>Day</th><th class='num'>Temp lo/hi</th><th class='num'>Wind avg</th>"
        "<th class='num'>Gust max</th><th>Dir</th><th class='num'>Precip</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _render_tides(tides_by_day: dict[str, list[dict]]) -> str:
    if not tides_by_day:
        return "<p class='dim'>No tide data.</p>"

    def _fmt12(iso_hhmm: str) -> str:
        # Convert "HH:MM" (24-hour) to a 12-hour label like "5:24p".
        try:
            hh, mm = iso_hhmm.split(":", 1)
            h, m = int(hh), int(mm)
            h12 = h % 12 or 12
            suffix = "a" if h < 12 else "p"
            return f"{h12}:{m:02d}{suffix}"
        except (ValueError, IndexError):
            return iso_hhmm

    rows = []
    for day in sorted(tides_by_day)[:DAYS]:
        cells = []
        for t in tides_by_day[day]:
            time = _fmt12((t.get("t") or "")[11:16])
            kind = t.get("type")
            v = t.get("v")
            cls = "tide-up" if kind == "H" else "tide-dn"
            cells.append(f"<span class='{cls}'>{kind} {time} ({v} ft)</span>")
        date = dt.date.fromisoformat(day)
        dlabel = date.strftime("%a %b %#d")
        rows.append(f"<tr><td>{dlabel}</td><td>{' &nbsp; '.join(cells)}</td></tr>")
    return (
        "<table class='dt'><thead><tr><th>Day</th><th>Tides (MLLW)</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _render_buoy(b: dict) -> str:
    if "error" in b:
        return f"<p class='dim'>Buoy {_h(b.get('station'))}: {_h(b['error'])}</p>"
    ws = b.get("wind_speed_mps")
    gs = b.get("wind_gust_mps")
    ws_mph = round(ws * 2.23694, 1) if ws is not None else None
    gs_mph = round(gs * 2.23694, 1) if gs is not None else None
    parts = [
        f"<strong>{_h(b['station'])}</strong>",
        f"<span class='dim'>{_h(b.get('observed_utc'))}</span>",
        f"Wind {_fmt(ws_mph,' mph')} {_deg_to_compass(b.get('wind_dir_deg'))} · gust {_fmt(gs_mph,' mph')}",
    ]
    if b.get("water_temp_c") is not None:
        wf = b["water_temp_c"] * 9 / 5 + 32
        parts.append(f"Water {wf:.1f}°F")
    if b.get("wave_height_m") is not None:
        parts.append(f"Waves {b['wave_height_m']:.1f} m")
    return "<div>" + " · ".join(parts) + "</div>"


def _render_nws(fc: dict) -> str:
    if not fc or fc.get("error"):
        return f"<p class='dim'>NWS forecast unavailable{': ' + _h(fc.get('error')) if fc else ''}.</p>"
    periods = fc.get("periods", [])[:8]
    rows = []
    for p in periods:
        rows.append(
            f"<tr><td><strong>{_h(p.get('name'))}</strong></td>"
            f"<td>{_h(p.get('shortForecast'))}</td>"
            f"<td class='num'>{_h(p.get('temperature'))}°{_h(p.get('temperatureUnit'))}</td>"
            f"<td>{_h(p.get('windSpeed'))} {_h(p.get('windDirection'))}</td></tr>"
        )
    return (
        "<table class='dt'><thead><tr><th>Period</th><th>Outlook</th>"
        "<th class='num'>Temp</th><th>Wind</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _render_rules(current: list[dict], proposed: list[dict]) -> str:
    out = []
    if current:
        out.append("<div><span class='tag b'>CURRENT 2025-26</span><ul>")
        for r in current:
            snippet = (r.get("text") or "")[:280].replace("\n", " ")
            out.append(
                f"<li><strong>{_h(r.get('heading'))}</strong> "
                f"<span class='dim'>p.{_h(r.get('page'))}</span><br>"
                f"<span class='dim'>{_h(snippet)}…</span></li>"
            )
        out.append("</ul></div>")
    if proposed:
        out.append("<div style='margin-top:10px'><span class='tag p'>PROPOSED 2026-27</span><ul>")
        for r in proposed:
            snippet = (r.get("text") or "")[:280].replace("\n", " ")
            out.append(f"<li><strong>{_h(r.get('area'))}</strong> — <span class='dim'>{_h(snippet)}…</span></li>")
        out.append("</ul></div>")
    return "".join(out) if out else "<p class='dim'>No matching regulations.</p>"


def _render_kpi_strip(data: dict) -> str:
    w: Water = data["water"]
    daily = data.get("daily", [])
    peak_gust = max((d.get("gust_max_mph") or 0) for d in daily) if daily else None
    max_temp = max((d.get("temp_max_f") or -999) for d in daily) if daily else None
    total_precip = round(sum((d.get("precip_in") or 0) for d in daily), 2) if daily else 0
    if peak_gust is None:
        gust_kpi_cls = ""
    elif peak_gust >= 25:
        gust_kpi_cls = "red"
    elif peak_gust >= 18:
        gust_kpi_cls = "orange"
    elif peak_gust >= 12:
        gust_kpi_cls = "yellow"
    else:
        gust_kpi_cls = "green"
    precip_cls = "green" if total_precip < 0.1 else ("yellow" if total_precip < 0.5 else "orange")
    kpis = [
        ("", "From Home", f"{data['distance_home_mi']} mi", "great-circle"),
        ("teal", "From Cabin", f"{data['distance_cabin_mi']} mi", "great-circle"),
        (gust_kpi_cls, "Peak Gust (7d)", f"{int(peak_gust)} mph" if peak_gust else "—", "Open-Meteo"),
        ("orange" if (max_temp or 0) >= 85 else "yellow" if (max_temp or 0) >= 75 else "",
         "Max Temp (7d)", f"{int(max_temp)}°F" if max_temp and max_temp > -999 else "—", ""),
        (precip_cls, "Total Precip (7d)", f"{total_precip:.2f}″", ""),
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


def _render_water(data: dict) -> str:
    w: Water = data["water"]
    sub = f"{w.lat:.3f}, {w.lon:.3f}"

    cards = []
    # Daily summary card (always first)
    daily_html = _render_daily_table(data["daily"]) if data.get("daily") else (
        f"<p class='dim'>Open-Meteo error: {_h(data.get('open_meteo_error'))}</p>"
    )
    cards.append(f"<div class='card'><h3>7-Day Wind &amp; Weather (Open-Meteo)</h3>{daily_html}</div>")

    # Marine vs land
    if w.kind == "marine":
        tides = data.get("tides", {})
        if tides.get("error"):
            tides_html = f"<p class='dim'>Tides error: {_h(tides['error'])}</p>"
        else:
            tides_html = _render_tides(_group_tides_by_day(tides.get("tides", [])))
        cards.append(f"<div class='card'><h3>Tides (next {DAYS} days)</h3>{tides_html}</div>")

        buoys = data.get("buoys", [])
        if buoys:
            cards.append(
                "<div class='card'><h3>Buoy snapshots</h3>"
                + "".join(_render_buoy(b) for b in buoys)
                + "</div>"
            )
        mf = data.get("marine") or {}
        if mf.get("text"):
            cards.append(
                f"<div class='card'><h3>NWS marine zone {_h(mf.get('zone'))}</h3>"
                f"<details><summary>Full text</summary><pre>{_h(mf['text'].strip())}</pre></details>"
                "</div>"
            )
        elif mf.get("error"):
            cards.append(
                f"<div class='card'><h3>NWS marine zone</h3>"
                f"<p class='dim'>{_h(mf['error'])}</p></div>"
            )
    else:
        cards.append(
            f"<div class='card'><h3>NWS forecast</h3>{_render_nws(data.get('nws', {}))}</div>"
        )

    cards.append(
        "<div class='card'><h3>Regulations</h3>"
        f"{_render_rules(data.get('rules_current', []), data.get('rules_proposed', []))}"
        "</div>"
    )

    return (
        f"<section class='water' id='{w.key}'>"
        f"<h2>{_h(w.name)}</h2>"
        f"<div class='sub'>{_kind_tag(w.kind)} {sub}</div>"
        f"{_render_kpi_strip(data)}"
        f"<div class='grid'>{''.join(cards)}</div>"
        "</section>"
    )


def build_html(start: Optional[dt.date] = None,
               water_keys: Optional[list[str]] = None) -> str:
    """Generate the full 7-day HTML report as a string."""
    start = start or dt.date.today()
    keys = water_keys or list(WATERS.keys())
    waters = [WATERS[k] for k in keys if k in WATERS]

    sections: list[str] = []
    for w in waters:
        data = _gather_water(w, start)
        sections.append(_render_water(data))

    nav = "".join(
        f"<a href='#{w.key}'>{_h(w.name.split(' (')[0])}</a>" for w in waters
    )
    end = start + dt.timedelta(days=DAYS - 1)
    generated = dt.datetime.now().strftime("%Y-%m-%d %#I:%M %p %Z").strip()

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Fishing Conditions {start} – {end}</title>"
        f"<style>{CSS}</style></head><body>"
        "<header class='page'>"
        "<h1><div class='brand-logo'>"
        "<span></span><span></span><span></span><span></span>"
        "</div>Fishing Conditions Report</h1>"
        f"<div class='meta'>{start.strftime('%A, %B %d')} – {end.strftime('%A, %B %d, %Y')} "
        f"· generated {generated}</div>"
        "</header>"
        f"<nav class='tabs'>{nav}</nav>"
        + "".join(sections)
        + "<footer>Sources: NOAA NWS · NOAA CO-OPS tides · NDBC buoys · Open-Meteo. "
          "Regs from WDFW 2025-26 pamphlet + 2026-27 proposed plan KB.</footer>"
        "</body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        out_path = Path(argv[0])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        out_path = reports / f"fishing_7day_{dt.date.today().isoformat()}.html"

    html_text = build_html()
    out_path.write_text(html_text, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html_text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
