"""Compose a fishing report for a given water by stitching KB + live data."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from . import kb
from .distance import distance, haversine_km
from .stations import PLACES, WATERS, resolve_water
from .weather import (
    ndbc_latest,
    noaa_tides,
    nws_forecast,
    nws_marine_forecast,
    open_meteo,
)


def _month_name(d: dt.date) -> str:
    return d.strftime("%B")


def generate_report(water: str, date: Optional[str] = None, from_place: str = "home") -> dict:
    """Build a fishing-report dict for `water` on `date` (default: today)."""
    w = resolve_water(water)
    if not w:
        return {"error": f"Unknown water: {water!r}"}

    d = dt.date.fromisoformat(date) if date else dt.date.today()
    month = _month_name(d)

    report: dict = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "water": {"key": w.key, "name": w.name, "kind": w.kind,
                  "lat": w.lat, "lon": w.lon},
        "date": d.isoformat(),
        "month": month,
    }

    # Distance from home/cabin
    if from_place in PLACES:
        flat, flon = PLACES[from_place]
        report["distance_from"] = {
            "place": from_place,
            "miles": round(haversine_km(flat, flon, w.lat, w.lon) * 0.621371, 1),
        }
    # Always include both for marine outings from cabin
    report["distance_home_miles"] = round(
        haversine_km(*PLACES["home"], w.lat, w.lon) * 0.621371, 1)
    report["distance_cabin_miles"] = round(
        haversine_km(*PLACES["cabin"], w.lat, w.lon) * 0.621371, 1)

    # Regulations
    regs = kb.regulations(w.name.split(" (")[0])  # e.g. "Marine Area 9"
    # narrow current results
    report["regulations"] = {
        "current": [
            {"heading": r["heading"], "page": r["page"],
             "snippet": (r["text"][:600] + "…") if len(r["text"]) > 600 else r["text"]}
            for r in regs["current"][:4]
        ],
        "proposed": [
            {"area": r["area"],
             "snippet": (r["text"][:600] + "…") if len(r["text"]) > 600 else r["text"]}
            for r in regs["proposed"][:2]
        ],
    }

    # Seasonal calendar row for this month
    cal_rows = kb.calendar(month=month)
    report["calendar"] = cal_rows[:1] if cal_rows else []

    # Weather (NWS land forecast only for non-marine; marine waters use the zone text)
    if w.kind != "marine":
        report["forecast"] = nws_forecast(w.lat, w.lon, hourly=False)
    report["wind_hourly"] = open_meteo(w.lat, w.lon, hours=48)

    # Marine extras
    if w.kind == "marine":
        if w.nws_zone:
            report["marine_forecast"] = nws_marine_forecast(w.nws_zone)
        if w.tide_station:
            report["tides"] = noaa_tides(w.tide_station, date=d.isoformat(), days=2)
        report["buoys"] = [ndbc_latest(b) for b in w.ndbc_buoys]

    return report


def format_report_markdown(rep: dict) -> str:
    """Human-readable Markdown render of a report dict."""
    if "error" in rep:
        return f"**Error:** {rep['error']}"

    w = rep["water"]
    lines = [
        f"# Fishing Report — {w['name']}",
        f"_Generated {rep['generated_at']} for {rep['date']} ({rep['month']})_",
        "",
        f"- From home: {rep.get('distance_home_miles')} mi  ·  "
        f"From cabin: {rep.get('distance_cabin_miles')} mi",
    ]

    # Calendar
    if rep.get("calendar"):
        c = rep["calendar"][0]
        key = w["key"]
        target_col = key if key in c else None
        if not target_col:
            for k in ("ma9", "ma10", "skykomish", "snohomish",
                      "snoqualmie", "lake_sammamish"):
                if k in c and c[k]:
                    target_col = k; break
        lines.append("")
        lines.append("## Seasonal calendar")
        lines.append(f"- **{c.get('month')}** — {c.get(target_col) or '(no entry)'}")
        if c.get("notes"):
            lines.append(f"- Notes: {c['notes']}")

    # Regulations
    lines.append("")
    lines.append("## Regulations")
    if rep["regulations"]["current"]:
        for r in rep["regulations"]["current"]:
            lines.append(f"- **{r['heading']}** (p.{r['page']})")
            lines.append(f"  > {r['snippet']}")
    else:
        lines.append("- _No current rule sections found._")
    if rep["regulations"]["proposed"]:
        lines.append("")
        lines.append("### Proposed 2026-27")
        for r in rep["regulations"]["proposed"]:
            lines.append(f"- **{r['area']}**: {r['snippet']}")

    # Forecast (land NWS only included for non-marine waters)
    fc = rep.get("forecast")
    if fc:
        lines.append("")
        lines.append("## NWS forecast")
        if "error" in fc:
            lines.append(f"- Error: {fc['error']}")
        else:
            for p in fc.get("periods", [])[:4]:
                lines.append(f"- **{p.get('name')}**: {p.get('detailedForecast')}")

    # Marine zone text
    mf = rep.get("marine_forecast")
    if mf and "text" in mf:
        lines.append("")
        lines.append(f"## Marine forecast ({mf.get('zone')})")
        lines.append("```")
        lines.append(mf["text"].strip())
        lines.append("```")

    # Wind
    wh = rep.get("wind_hourly", {})
    if wh.get("hours"):
        peak = max(wh["hours"], key=lambda h: (h.get("gust_mph") or h.get("wind_mph") or 0))
        lines.append("")
        lines.append("## Wind (next 48 h, Open-Meteo)")
        lines.append(
            f"- Peak gust: {peak.get('gust_mph')} mph at {peak.get('time')} "
            f"(wind {peak.get('wind_mph')} mph @ {peak.get('wind_dir_deg')}°)"
        )

    # Marine
    if w["kind"] == "marine":
        tides = rep.get("tides", {})
        if tides.get("tides"):
            lines.append("")
            lines.append("## Tides")
            for t in tides["tides"][:8]:
                lines.append(f"- {t.get('t')}  {t.get('type')}  {t.get('v')} ft")
        for b in rep.get("buoys", []):
            if "error" not in b:
                lines.append("")
                lines.append(f"## Buoy {b['station']} ({b.get('observed_utc')})")
                lines.append(
                    f"- Wind: {b.get('wind_speed_mps')} m/s @ {b.get('wind_dir_deg')}°  "
                    f"gust {b.get('wind_gust_mps')} m/s"
                )
                if b.get("water_temp_c") is not None:
                    lines.append(f"- Water temp: {b['water_temp_c']} °C")

    return "\n".join(lines)
