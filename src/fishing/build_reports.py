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
from .html_loadout import build_boat_html, build_tackle_html
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

    desktop_html = build_desktop(today, data=data)
    desktop_path.write_text(desktop_html, encoding="utf-8")
    print(f"Wrote {desktop_path} ({desktop_path.stat().st_size:,} bytes)")

    mobile_html = build_mobile(today, data=data)
    mobile_path.write_text(mobile_html, encoding="utf-8")
    print(f"Wrote {mobile_path} ({mobile_path.stat().st_size:,} bytes)")

    # Static reference tabs (boat loadout + tackle catalog). Read the KB only;
    # no live data, so they're cheap to rebuild alongside the forecast.
    out_dir = desktop_path.parent
    for name, fn in (("boat.html", build_boat_html), ("tackle.html", build_tackle_html)):
        p = out_dir / name
        p.write_text(fn(), encoding="utf-8")
        print(f"Wrote {p} ({p.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
