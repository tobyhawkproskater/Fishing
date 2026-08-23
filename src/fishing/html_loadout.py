"""Fishing gear catalog page (responsive, desktop + mobile).

A static reference tab in the fishing-report site: reads from the SQLite
KB only and doesn't fetch any live data, so it's cheap to rebuild on every
CI run alongside the forecast.

Run:
    python -m fishing.html_loadout gear docs/gear.html
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Optional

from . import ROOT, kb
from .html_report import CSS, _h


# --- shared nav -------------------------------------------------------------

NAV_LINKS = [
    ("Forecast",     "index.html",  "forecast"),
    ("Mobile",       "mobile.html", "mobile"),
    ("Big Jake",     "big-jake.html", "big-jake"),
    ("Creel Trends", "creel.html",  "creel"),
    ("Fishing Gear", "gear.html",   "gear"),
    ("Boats",        "boats.html",  "boats"),
]


def render_nav(active: str) -> str:
    """Top tab nav shared by every page in docs/. `active` matches the slug."""
    items = []
    for label, href, slug in NAV_LINKS:
        cls = "active" if slug == active else ""
        items.append(f"<a class='{cls}' href='{href}'>{label}</a>")
    return f"<nav class='tabs'>{''.join(items)}</nav>"


# --- gear-page CSS (extends CSS from html_report.py) ----------------------

LOADOUT_CSS = """
/* Gear-page tweaks (gear.html) */
.hero{padding:28px 32px 8px;background:linear-gradient(135deg,#004578 0%,#005A9E 55%,#0078D4 100%);
      color:#fff}
.hero h1{margin:0;font-size:28px;font-weight:600}
.hero .sub{opacity:.9;margin-top:6px;font-size:14px}
.hero .pill-row{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px}
.hero .pill{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.35);
            color:#fff;padding:6px 12px;border-radius:999px;font-size:12.5px;font-weight:600;
            letter-spacing:.3px;display:inline-flex;align-items:center;gap:6px}
.hero .pill b{font-weight:700;font-size:13px}

.section-pad{padding:24px 32px}
@media (max-width:640px){.hero{padding:20px 16px 6px} .hero h1{font-size:22px}
  .section-pad{padding:16px}}

.use-filter{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 16px;padding:0;list-style:none}
.use-filter li{background:#F3F2F1;color:var(--ms-text);padding:6px 12px;border-radius:999px;
               font-size:12px;font-weight:600;border:1px solid var(--ms-border);
               display:inline-flex;align-items:center;gap:6px}
.use-filter li b{color:var(--ms-blue);font-weight:700}

.use-section{margin-bottom:28px}
.use-section h3{margin:0 0 12px;font-size:16px;color:var(--ms-text);font-weight:600;
                display:flex;align-items:center;gap:10px;padding-bottom:6px;
                border-bottom:2px solid var(--ms-blue)}
.use-section h3 .count{font-size:12px;color:var(--ms-text-secondary);font-weight:500;
                       background:#EFF6FC;color:var(--ms-blue-darker);padding:2px 10px;
                       border-radius:999px;letter-spacing:.3px}

.rod-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.rod{background:#fff;border:1px solid var(--ms-border);border-radius:10px;
     padding:16px 18px;box-shadow:var(--shadow-sm);position:relative;overflow:hidden;
     transition:box-shadow .15s ease, transform .15s ease}
.rod:hover{box-shadow:var(--shadow-md);transform:translateY(-1px)}
.rod::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:var(--ms-blue)}
.rod[data-use="Salmon"]::before{background:#D83B01}
.rod[data-use="Trout"]::before{background:#107C10}
.rod[data-use="Steelhead"]::before{background:#5C2D91}
.rod[data-use="Bottomfishing"]::before{background:#FFB900}
.rod[data-use="All Purpose"]::before{background:#008080}
.rod .head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.rod .brand{font-size:11px;color:var(--ms-text-secondary);text-transform:uppercase;
            letter-spacing:.5px;font-weight:600}
.rod .model{font-size:17px;font-weight:600;color:var(--ms-text);margin:2px 0 0;line-height:1.2}
.rod .meta-row{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.rod .chip{background:#F3F2F1;color:var(--ms-text);padding:3px 9px;border-radius:4px;
           font-size:11px;font-weight:600;letter-spacing:.2px}
.rod .chip.type{background:#DEECF9;color:var(--ms-blue-darker)}
.rod .chip.loc{background:#FFF4CE;color:#796300}
.rod .chip.guest{background:#DFF6DD;color:#0B6A0B}
.rod .chip.solo{background:#FDE7E9;color:#8E1F25}
.rod .power-bar{margin:12px 0 8px;display:flex;align-items:center;gap:8px}
.rod .power-bar .scale{flex:1;display:grid;grid-template-columns:repeat(5,1fr);gap:2px;height:6px}
.rod .power-bar .scale span{background:#EDEBE9;border-radius:2px}
.rod .power-bar .scale span.on{background:var(--ms-blue)}
.rod .power-bar .label{font-size:11px;color:var(--ms-text-secondary);min-width:80px;text-align:right;
                       font-weight:600}
.rod .reel{font-size:12.5px;color:var(--ms-text-secondary);margin-top:2px}
.rod .reel b{color:var(--ms-text);font-weight:600}
.rod .notes{margin-top:8px;font-size:12px;color:var(--ms-text-secondary);font-style:italic}

footer.fun{padding:18px 32px;color:var(--ms-text-secondary);font-size:12px;
           border-top:1px solid var(--ms-border);background:#fff;text-align:center}
"""


# --- helpers ---------------------------------------------------------------

_POWER_RANK_RE = re.compile(r"^\s*(\d)")
_POWER_LABELS = {
    1: "Ultralight", 2: "Medium-Light", 3: "Medium",
    4: "Medium-Heavy", 5: "Heavy",
}


def _power_rank(power: Optional[str]) -> tuple[int, str]:
    """Return (1..5 rank, friendly label) from a raw 'power' string."""
    if not power:
        return (0, "")
    m = _POWER_RANK_RE.match(power)
    rank = int(m.group(1)) if m else 0
    rest = power.strip().split(" ", 1)
    label = rest[1].strip() if len(rest) > 1 else _POWER_LABELS.get(rank, "")
    if rank == 4 and label.lower() == "heavy":
        # Worksheet has "4 Heavy" vs "4 Medium Heavy"; coerce to 5 if Heavy.
        rank = 5
        label = "Heavy"
    return (max(0, min(rank, 5)), label or _POWER_LABELS.get(rank, ""))


def _power_bar(rank: int, label: str) -> str:
    cells = "".join(
        f"<span class='{'on' if i < rank else ''}'></span>" for i in range(5)
    )
    return (
        "<div class='power-bar'>"
        f"<div class='scale'>{cells}</div>"
        f"<div class='label'>{_h(label or '\u2014')}</div>"
        "</div>"
    )


# --- Gear page -------------------------------------------------------------

# Order of Use categories on the page (others fall through alphabetical).
_USE_ORDER = ["Salmon", "Steelhead", "Trout", "Bottomfishing", "All Purpose"]
_USE_ICONS = {
    "Salmon": "&#127907;",       # fishing pole
    "Steelhead": "&#127754;",    # water wave
    "Trout": "&#128031;",        # fish
    "Bottomfishing": "&#9875;",  # anchor
    "All Purpose": "&#11088;",   # star
}


def _rod_card(r: dict) -> str:
    rank, plabel = _power_rank(r.get("power"))
    chips = []
    if r.get("type"):
        chips.append(f"<span class='chip type'>{_h(r['type'])}</span>")
    if r.get("length"):
        chips.append(f"<span class='chip'>{_h(r['length'])}</span>")
    if r.get("line_rating"):
        chips.append(f"<span class='chip'>{_h(r['line_rating'])}</span>")
    if r.get("lure_rating"):
        chips.append(f"<span class='chip'>{_h(r['lure_rating'])}</span>")
    if r.get("location"):
        chips.append(f"<span class='chip loc'>{_h(r['location'])}</span>")
    if r.get("guests"):
        g = (r["guests"] or "").strip().lower()
        if g.startswith("y"):
            chips.append("<span class='chip guest'>Guest-friendly</span>")
        elif g.startswith("n"):
            chips.append("<span class='chip solo'>Personal</span>")

    reel_line = ""
    if r.get("reel") or r.get("line"):
        reel = _h(r.get("reel") or "\u2014")
        line = _h(r.get("line") or "\u2014")
        reel_line = f"<div class='reel'>Reel: <b>{reel}</b> \u00b7 Line: <b>{line}</b></div>"

    notes = ""
    if r.get("notes"):
        notes = f"<div class='notes'>\u201c{_h(r['notes'])}\u201d</div>"

    purpose = _h(r.get("purpose") or r.get("use") or "")
    brand = _h(r.get("brand") or "")
    model = _h(r.get("model") or "")
    number = _h(r.get("number") or "")
    head = (
        "<div class='head'>"
        f"<div><div class='brand'>{brand}</div>"
        f"<div class='model'>{model}</div></div>"
        f"<div class='brand' style='text-align:right'>{purpose}</div>"
        "</div>"
    )
    code = f"<div class='brand' style='margin-top:2px'>{number}</div>" if number else ""

    return (
        f"<div class='rod' data-use='{_h(r.get('use') or '')}'>"
        f"{head}{code}"
        f"<div class='meta-row'>{''.join(chips)}</div>"
        f"{_power_bar(rank, plabel)}"
        f"{reel_line}{notes}"
        "</div>"
    )


def build_gear_html() -> str:
    rods = kb.gear() or []
    # Filter out the trailing totals row if it slipped through (no brand/model).
    rods = [r for r in rods if (r.get("brand") or r.get("model"))]

    by_use: "OrderedDict[str, list[dict]]" = OrderedDict()
    for u in _USE_ORDER:
        by_use[u] = []
    for r in rods:
        u = r.get("use") or "Other"
        by_use.setdefault(u, []).append(r)

    by_loc = defaultdict(int)
    for r in rods:
        by_loc[r.get("location") or "Other"] += 1

    pill = lambda lbl, val: f"<span class='pill'>{lbl}&nbsp;<b>{_h(val)}</b></span>"
    pills = [
        pill("Rods", str(len(rods))),
    ] + [pill(loc, str(n)) for loc, n in sorted(by_loc.items(), key=lambda x: -x[1])]

    filter_items = "".join(
        f"<li>{_USE_ICONS.get(u, '&#127907;')} {_h(u)} <b>{len(rs)}</b></li>"
        for u, rs in by_use.items() if rs
    )

    sections = []
    for use, rs in by_use.items():
        if not rs:
            continue
        rs_sorted = sorted(rs, key=lambda x: (_power_rank(x.get("power"))[0],
                                              x.get("brand") or "",
                                              x.get("model") or ""))
        cards = "".join(_rod_card(r) for r in rs_sorted)
        sections.append(
            f"<div class='use-section'>"
            f"<h3>{_USE_ICONS.get(use, '&#127907;')} {_h(use)} "
            f"<span class='count'>{len(rs)} rod{'s' if len(rs) != 1 else ''}</span></h3>"
            f"<div class='rod-grid'>{cards}</div>"
            "</div>"
        )

    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Fishing Gear</title>"
        f"<style>{CSS}{LOADOUT_CSS}</style></head><body>"
        "<header class='page'>"
        "<h1><div class='brand-logo'>"
        "<span></span><span></span><span></span><span></span>"
        "</div>Fishing Gear</h1>"
        f"<div class='meta'>{len(rods)} rod &amp; reel combos \u00b7 updated {generated}</div>"
        "</header>"
        f"{render_nav('gear')}"
        "<section class='hero'>"
        "<h1>Fishing Gear &#127907;</h1>"
        "<div class='sub'>Every rod, reel, and line in the rotation \u2014 organized by what we fish for.</div>"
        f"<div class='pill-row'>{''.join(pills)}</div>"
        "</section>"
        "<section class='section-pad'>"
        f"<ul class='use-filter'>{filter_items}</ul>"
        f"{''.join(sections)}"
        "</section>"
        "<footer class='fun'>Pulled from Fishing Gear.xlsx \u00b7 edit that file and rerun "
        "<code>python -m fishing.build_kb</code> to update.</footer>"
        "</body></html>"
    )


# --- CLI -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv and argv[0].lower() != "gear":
        print(f"Unknown target: {argv[0]}")
        print("Usage: python -m fishing.html_loadout gear [out.html]")
        return 2

    html_text = build_gear_html()
    if len(argv) >= 2:
        out = Path(argv[1])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        out = reports / "gear.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
