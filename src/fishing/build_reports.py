"""Build desktop MA9 plus mobile MA9 and Area 8-2 reports.

Running the desktop and mobile generators as separate processes makes two
independent calls to ``_assemble``, which means two separate fetches of the
live forecast. When the gust forecast updates between calls, the two reports
can disagree on the gold PRIME marker (e.g., desktop sees gust 11 / GOOD
star, mobile sees gust 10 / PRIME star at the same slack).

This entry point assembles the data once and feeds it to both builders so
they always agree.

Run:
    python -m fishing.build_reports                       # writes all reports into reports/
    python -m fishing.build_reports docs/index.html docs/mobile.html
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from . import ROOT
from .creel import build_html as build_creel_html, update_history
from .html_boats import build_boats_html
from .html_loadout import build_gear_html
from .html_report_ma9 import _assemble, build_html as build_desktop
from .html_report_ma9_mobile import build_html as build_mobile


def _report_data_error(data: dict) -> str | None:
    if not data.get("tide_events"):
        return data.get("tides_error") or "no tide data"

    covered = {ev["t"][:10] for ev in data["tide_events"] if ev.get("t")}
    missing = [
        row["date"].isoformat()
        for row in data.get("grid", [])
        if row["date"].isoformat() not in covered
    ]
    if missing:
        return f"tide data missing for {', '.join(missing)}"
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    today = dt.date.today()

    if len(argv) >= 2:
        desktop_path = Path(argv[0])
        mobile_path = Path(argv[1])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        desktop_path = reports / f"fishing_ma9_{today.isoformat()}.html"
        mobile_path = reports / f"fishing_ma9_mobile_{today.isoformat()}.html"

    big_jake_path = (
        desktop_path.parent / "big-jake.html"
        if len(argv) >= 2
        else desktop_path.parent / f"fishing_ma8_2_big_jake_{today.isoformat()}.html"
    )

    data = _assemble(today)
    big_jake_data = _assemble(today, water_key="ma8_2", rules_name="Marine Area 8-2")

    # A report with no tide data is worse than a stale one: with tide_score
    # forced to 0, every hour collapses to the mid-cycle floor (a flat ~0.40
    # heatmap with no Prime tiers, no colored tide curves, and no qualifying
    # windows). This happens when NOAA CO-OPS times out (e.g. 504) and the
    # Seattle fallback also fails. Abort WITHOUT writing so the last good
    # report stays published instead of being clobbered by a useless one.
    for report_name, report_data in (("MA9", data), ("Big Jake", big_jake_data)):
        error = _report_data_error(report_data)
        if not error:
            continue
        print(
            f"ERROR: {report_name} tide data unavailable ({error}); skipping report "
            "writes to preserve the last good pages.",
            file=sys.stderr,
        )
        return 1

    desktop_html = build_desktop(today, data=data)
    desktop_path.write_text(desktop_html, encoding="utf-8")
    print(f"Wrote {desktop_path} ({desktop_path.stat().st_size:,} bytes)")

    mobile_html = build_mobile(today, data=data)
    mobile_path.write_text(mobile_html, encoding="utf-8")
    print(f"Wrote {mobile_path} ({mobile_path.stat().st_size:,} bytes)")

    big_jake_data["tide_station_label"] = (
        "Everett (9447659)" if big_jake_data.get("tide_station_used") == "9447659"
        else "Seattle fallback (9447130)"
    )
    big_jake_html = build_mobile(
        today,
        data=big_jake_data,
        nav_active="big-jake",
        page_name="Big Jake",
        location_note="Sandy Point \u00b7 Marine Area 8-2",
        tide_reference_ft=0.0,
        tide_reference_label="0 ft dock elevator",
        show_lingcod_alert=False,
    )
    big_jake_path.write_text(big_jake_html, encoding="utf-8")
    print(f"Wrote {big_jake_path} ({big_jake_path.stat().st_size:,} bytes)")

    # Static reference tab (fishing gear catalog). Reads the KB only;
    # no live data, so it's cheap to rebuild alongside the forecast.
    gear_path = desktop_path.parent / "gear.html"
    gear_path.write_text(build_gear_html(), encoding="utf-8")
    print(f"Wrote {gear_path} ({gear_path.stat().st_size:,} bytes)")

    # Boat shopping comparison tab. Static shortlist (no live data).
    boats_path = desktop_path.parent / "boats.html"
    boats_path.write_text(build_boats_html(), encoding="utf-8")
    print(f"Wrote {boats_path} ({boats_path.stat().st_size:,} bytes)")

    # WDFW's live page only exposes a rolling window. Merge it into the
    # persistent cache before rendering so seasonal trends accumulate.
    creel_path = desktop_path.parent / "creel.html"
    creel_rows, creel_error = update_history()
    if creel_rows:
        creel_path.write_text(build_creel_html(creel_rows, creel_error), encoding="utf-8")
        print(f"Wrote {creel_path} ({creel_path.stat().st_size:,} bytes)")
    else:
        print(
            f"WARNING: creel data unavailable ({creel_error or 'empty cache'}); "
            "preserving the last creel page.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
