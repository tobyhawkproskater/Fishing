"""Build both desktop and mobile MA9 reports from a single weather fetch.

Running the desktop and mobile generators as separate processes makes two
independent calls to ``_assemble``, which means two separate fetches of the
live forecast. When the gust forecast updates between calls, the two reports
can disagree on the gold PRIME marker (e.g., desktop sees gust 11 / GOOD
star, mobile sees gust 10 / PRIME star at the same slack).

This entry point assembles the data once and feeds it to both builders so
they always agree.

Run:
    python -m fishing.build_reports                       # writes both into reports/
    python -m fishing.build_reports docs/index.html docs/mobile.html
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from . import ROOT
from .html_boats import build_boats_html
from .html_loadout import build_gear_html
from .html_report_ma9 import _assemble, build_html as build_desktop
from .html_report_ma9_mobile import build_html as build_mobile


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

    data = _assemble(today)

    # A report with no tide data is worse than a stale one: with tide_score
    # forced to 0, every hour collapses to the mid-cycle floor (a flat ~0.40
    # heatmap with no Prime tiers, no colored tide curves, and no qualifying
    # windows). This happens when NOAA CO-OPS times out (e.g. 504) and the
    # Seattle fallback also fails. Abort WITHOUT writing so the last good
    # report stays published instead of being clobbered by a useless one.
    if not data.get("tide_events"):
        err = data.get("tides_error") or "no tide data"
        print(
            f"ERROR: tide data unavailable ({err}); skipping report write to "
            "preserve the last good report.",
            file=sys.stderr,
        )
        return 1

    # Partial tide data is just as misleading as none: when NOAA's day-by-day
    # fallback drops a day (504), that day's heatmap collapses to the flat
    # ~0.40 floor — no Prime tiers, no colored curve, no pill — while its
    # neighbors look fine, so the gap is easy to miss. Require every forecast
    # day to carry tide events before publishing.
    covered = {ev["t"][:10] for ev in data["tide_events"] if ev.get("t")}
    missing = [
        row["date"].isoformat()
        for row in data.get("grid", [])
        if row["date"].isoformat() not in covered
    ]
    if missing:
        print(
            f"ERROR: tide data missing for {', '.join(missing)}; skipping report "
            "write to preserve the last good report.",
            file=sys.stderr,
        )
        return 1

    desktop_html = build_desktop(today, data=data)
    desktop_path.write_text(desktop_html, encoding="utf-8")
    print(f"Wrote {desktop_path} ({desktop_path.stat().st_size:,} bytes)")

    mobile_html = build_mobile(today, data=data)
    mobile_path.write_text(mobile_html, encoding="utf-8")
    print(f"Wrote {mobile_path} ({mobile_path.stat().st_size:,} bytes)")

    # Static reference tab (fishing gear catalog). Reads the KB only;
    # no live data, so it's cheap to rebuild alongside the forecast.
    gear_path = desktop_path.parent / "gear.html"
    gear_path.write_text(build_gear_html(), encoding="utf-8")
    print(f"Wrote {gear_path} ({gear_path.stat().st_size:,} bytes)")

    # Boat shopping comparison tab. Static shortlist (no live data).
    boats_path = desktop_path.parent / "boats.html"
    boats_path.write_text(build_boats_html(), encoding="utf-8")
    print(f"Wrote {boats_path} ({boats_path.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
