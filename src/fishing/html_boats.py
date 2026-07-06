"""Boat shopping comparison tab (desktop + mobile).

A static reference tab in the fishing-report site: the boat shortlist lives
in the ``BOATS`` list below, so refreshing the chart is just editing that list
and rerunning the build. No live data, so it rebuilds cheaply alongside the
forecast and gear tabs.

Run:
    python -m fishing.html_boats boats docs/boats.html
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from . import ROOT
from .html_report import CSS, _h
from .html_loadout import render_nav


# --- data: the shortlist ----------------------------------------------------
# Refresh the chart by editing this list, then rerun:
#   python -m fishing.html_boats boats docs/boats.html
# Provenance: "verified" = from a spec sheet / catalog PDF or the builder's
# site; "listing" = pulled from a live for-sale ad; "approx" = general
# knowledge / model-family figure (site was JS-blocked). Values prefixed with
# "~" are approximate. Keep this honest so the sort/compare stays trustworthy.

BOATS = [
    {
        "brand": "Alumaweld", "model": "Intruder 22 (Hardtop)",
        "loa": "24'9\"", "beam": "8'3.5\"", "deadrise": "18\u00b0",
        "bottom": ".190\"", "sides": ".125\"",
        "dry": 2475, "fuel": 60, "hp": 225,
        "bracket": "Yes (Alumadrive)", "warranty": "Limited",
        "price": "New ~$90k+ \u00b7 best used value",
        "price_sort": 90000,
        "provenance": "verified",
        "source": "2026 catalog PDF",
        "tag": "b",
        "fit": "Lightest hull \u2192 best sand-flat draft and beaching. "
               "Tradeoffs: thinnest sides (.125\"), narrower 8'3.5\" beam, and a "
               "225 HP cap. Offered as DuraFrame Sport Top or hardtop \u2014 "
               "matches your open-hardtop want.",
    },
    {
        "brand": "North River", "model": "Coho 21' Hard Top",
        "loa": "23'2\"", "beam": "8'6\"", "deadrise": "18\u00b0",
        "bottom": ".190\"", "sides": ".160\"",
        "dry": 2800, "fuel": 70, "hp": 300,
        "bracket": "Yes (standard)", "warranty": "7-yr hull",
        "price": "$79,995 new (turnkey)",
        "price_sort": 79995,
        "provenance": "verified",
        "source": "dealer PDF",
        "tag": "g",
        "fit": "Your style favorite and an attainable NEW number. Open-bow "
               "hardtop; comes standard with 150 HP + trailer + hydraulic "
               "steering + offshore bracket. Cockpit is smaller (66\") than the "
               "bigger hulls.",
    },
    {
        "brand": "North River", "model": "Seahawk 22' (Hardtop)",
        "loa": "~24'", "beam": "8'6\"", "deadrise": "18\u00b0",
        "bottom": ".250\"", "sides": ".160\"",
        "dry": 2700, "fuel": 80, "hp": 300,
        "bracket": "Yes (standard)", "warranty": "Lifetime hull",
        "price": "Used ~$60\u201398k",
        "price_sort": 75000,
        "provenance": "verified",
        "source": "dealer PDF",
        "tag": "p",
        "fit": "Thickest bottom (.250\") + lifetime warranty = the stoutest, "
               "softest-riding hull on the list. Premium price; the loaded 2019 "
               "listing was $98k. Buy older/plainer to stay in budget.",
    },
    {
        "brand": "KingFisher", "model": "2325 Coastal Express",
        "loa": "~23'", "beam": "8'6\"", "deadrise": "16\u00b0 (var.)",
        "bottom": ".190\"", "sides": ".160\"",
        "dry": "~3,200", "fuel": "~70", "hp": "~300",
        "bracket": "Yes (full-width)", "warranty": "Lifetime hull",
        "price": "~$120k+ new",
        "price_sort": 120000,
        "provenance": "approx",
        "source": "family specs verified; model figures approx",
        "tag": "t",
        "fit": "Value-quality middle ground. Flatter 16\u00b0 hull = slightly "
               "firmer offshore ride but very stable. Helm-side door common "
               "(great for solo docking/buoy pickup).",
    },
    {
        "brand": "Duckworth", "model": "Navigator 21'",
        "loa": "~23' w/ bracket", "beam": "~8'6\"", "deadrise": "High (deep-V)",
        "bottom": "~.190\u2013.250\"", "sides": "~.190\"",
        "dry": "~3,000+", "fuel": 42, "hp": "~115\u2013250",
        "bracket": "Varies", "warranty": "Used",
        "price": "$55k (2015, live)",
        "price_sort": 55000,
        "provenance": "listing",
        "source": "general + live listing (no verified spec sheet)",
        "tag": "o",
        "fit": "Stoutest hull + softest heavy-V ride, but deepest draft = "
               "worst sand-flat beaching (the one unfixable tradeoff). The live "
               "2015 unit nails your dream rig: Yamaha 115 + T9.9 kicker, "
               "~319 hrs, offshore-proven out of Westport.",
        "pick": True,
    },
    {
        "brand": "Silver Streak", "model": "21' Hardtop",
        "loa": "21' (23.5' w/ bracket)", "beam": "8'6\"", "deadrise": "\u2014",
        "bottom": "7' w/ reverse chines", "sides": "\u2014",
        "dry": "\u2014", "fuel": "\u2014", "hp": "\u2014",
        "bracket": "Yes (offshore)", "warranty": "\u2014",
        "price": "$89k firm (2015, live)",
        "price_sort": 89000,
        "url": "https://www.craigslist.org/view/d/anacortes-21-silver-streak-hardtop/nVYzTMLAxDhvdAqTYGQsjo",
        "provenance": "listing",
        "source": "live listing + general",
        "tag": "b",
        "fit": "Premium BC tank. True reverse chines = very stable + dry ride, "
               "7 gph @ 30 mph. Over budget, but a useful quality/ride "
               "benchmark to measure the others against.",
    },
]

# Order columns render in the comparison table: (key, header, numeric?)
COLUMNS = [
    ("model", "Boat", False),
    ("loa", "LOA", False),
    ("beam", "Beam", False),
    ("deadrise", "Deadrise", False),
    ("bottom", "Bottom", False),
    ("sides", "Sides", False),
    ("dry", "Dry (lb)", True),
    ("fuel", "Fuel (gal)", True),
    ("hp", "Max HP", True),
    ("bracket", "Bracket", False),
    ("warranty", "Warranty", False),
    ("price", "Price", False),
]


# --- page-specific CSS ------------------------------------------------------

BOATS_CSS = """
/* Boats-page tweaks (boats.html) */
.hero{padding:28px 32px 8px;background:linear-gradient(135deg,#004578 0%,#005A9E 55%,#0078D4 100%);
      color:#fff}
.hero h1{margin:0;font-size:28px;font-weight:600}
.hero .sub{opacity:.9;margin-top:6px;font-size:14px;max-width:760px}
.hero .pill-row{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px}
.hero .pill{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.35);
            color:#fff;padding:6px 12px;border-radius:999px;font-size:12.5px;font-weight:600;
            letter-spacing:.3px;display:inline-flex;align-items:center;gap:6px}
.hero .pill b{font-weight:700;font-size:13px}
.section-pad{padding:24px 32px}
@media (max-width:640px){.hero{padding:20px 16px 6px} .hero h1{font-size:22px}
  .section-pad{padding:16px}}

.cmp-wrap{overflow-x:auto;border:1px solid var(--ms-border);border-radius:6px;
          box-shadow:var(--shadow-sm);background:#fff;margin-bottom:8px}
table.cmp{width:100%;border-collapse:collapse;font-size:13px;min-width:920px}
table.cmp th,table.cmp td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--ms-divider);
                          white-space:nowrap}
table.cmp th{background:#F3F2F1;color:var(--ms-text-secondary);font-weight:600;font-size:12px;
             text-transform:uppercase;letter-spacing:.4px;position:sticky;top:0;cursor:pointer;
             user-select:none}
table.cmp th:hover{color:var(--ms-blue)}
table.cmp th .arrow{color:var(--ms-blue);font-size:10px;margin-left:4px;opacity:.5}
table.cmp th.sorted .arrow{opacity:1}
table.cmp td.num,table.cmp th.num{text-align:right;font-variant-numeric:tabular-nums}
table.cmp tr:hover td{background:#F8F7F6}
table.cmp tr.pick td{background:#DFF6DD}
table.cmp tr.pick:hover td{background:#D2F0CE}
table.cmp td.boat{font-weight:600;color:var(--ms-text)}
table.cmp td.boat .brand{display:block;font-size:11px;color:var(--ms-text-secondary);
                         text-transform:uppercase;letter-spacing:.4px;font-weight:600}
table.cmp td a{color:var(--ms-blue-darker);text-decoration:none;font-weight:600;white-space:nowrap}
table.cmp td a:hover{text-decoration:underline}

.scroll-hint{display:none;font-size:12px;color:var(--ms-text-secondary);margin:0 0 8px;
             font-style:italic}

.prov{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;
      text-transform:uppercase;letter-spacing:.3px;margin-left:6px;vertical-align:middle}
.prov.verified{background:#DFF6DD;color:#0B6A0B}
.prov.approx{background:#FFF4CE;color:#796300}
.prov.listing{background:#DEECF9;color:var(--ms-blue-darker)}

.legend{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0 22px;font-size:12px;
        color:var(--ms-text-secondary)}
.legend span{display:inline-flex;align-items:center;gap:6px}

.detail-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.bcard{background:#fff;border:1px solid var(--ms-border);border-radius:10px;padding:16px 18px;
       box-shadow:var(--shadow-sm);position:relative;overflow:hidden}
.bcard::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:var(--ms-blue)}
.bcard.pick::before{background:var(--ms-green)}
.bcard .brand{font-size:11px;color:var(--ms-text-secondary);text-transform:uppercase;
              letter-spacing:.5px;font-weight:600}
.bcard .model{font-size:17px;font-weight:600;color:var(--ms-text);margin:2px 0 0;line-height:1.2}
.bcard .price{font-size:13px;font-weight:600;color:var(--ms-blue-darker);margin-top:6px}
.bcard .fit{margin-top:10px;font-size:12.5px;color:var(--ms-text);line-height:1.5}
.bcard .src{margin-top:10px;font-size:11px;color:var(--ms-text-secondary);font-style:italic}
.bcard .picklabel{position:absolute;top:12px;right:14px;background:var(--ms-green);color:#fff;
                  font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
                  padding:2px 9px;border-radius:10px}
.bcard .listing{margin-top:12px}
.bcard .listing a{display:inline-block;background:var(--ms-blue);color:#fff;font-size:12px;
                  font-weight:600;padding:6px 14px;border-radius:4px;text-decoration:none}
.bcard .listing a:hover{background:var(--ms-blue-darker)}

footer.fun{padding:18px 32px;color:var(--ms-text-secondary);font-size:12px;
           border-top:1px solid var(--ms-border);background:#fff;text-align:center}

/* --- Mobile --- */
@media (max-width:640px){
  header.page{padding:16px 18px}
  header.page h1{font-size:19px}
  nav.tabs{padding:0 12px}
  .section-pad{padding:14px 16px}
  .scroll-hint{display:block}
  .cmp-wrap{-webkit-overflow-scrolling:touch}
  table.cmp{min-width:720px;font-size:12px}
  table.cmp th,table.cmp td{padding:7px 9px}
  .legend{gap:10px;margin:12px 0 18px}
  .detail-grid{grid-template-columns:1fr;gap:12px}
  footer.fun{padding:16px 18px}
}
"""


# --- helpers ----------------------------------------------------------------

def _num(v) -> str:
    """Format a numeric-or-string cell value for display."""
    if isinstance(v, (int, float)):
        return f"{v:,}"
    return _h(str(v))


def _sort_val(v) -> str:
    """Best-effort numeric sort key stashed in data-sort."""
    if isinstance(v, (int, float)):
        return str(v)
    # pull the first number out of strings like "~3,200" or "8'6\""
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits or "0"


def _row(b: dict) -> str:
    cells = []
    for key, _hdr, numeric in COLUMNS:
        val = b.get(key, "\u2014")
        if key == "model":
            prov = b.get("provenance", "")
            prov_badge = (
                f"<span class='prov {prov}'>{prov}</span>" if prov else ""
            )
            cells.append(
                f"<td class='boat' data-sort='{_h(b.get('model',''))}'>"
                f"<span class='brand'>{_h(b.get('brand',''))}</span>"
                f"{_h(b.get('model',''))}{prov_badge}</td>"
            )
        elif numeric:
            cells.append(
                f"<td class='num' data-sort='{_sort_val(val)}'>{_num(val)}</td>"
            )
        elif key == "price":
            url = b.get("url")
            price_html = _h(str(val))
            if url:
                price_html = (
                    f"<a href='{_h(url)}' target='_blank' rel='noopener noreferrer'>"
                    f"{price_html}&nbsp;\u2197</a>"
                )
            cells.append(
                f"<td data-sort='{b.get('price_sort', 0)}'>{price_html}</td>"
            )
        else:
            cells.append(f"<td data-sort='{_h(str(val))}'>{_h(str(val))}</td>")
    cls = " class='pick'" if b.get("pick") else ""
    return f"<tr{cls}>{''.join(cells)}</tr>"


def _header_row() -> str:
    ths = []
    for i, (_key, hdr, numeric) in enumerate(COLUMNS):
        cls = "num" if numeric else ""
        ths.append(
            f"<th class='{cls}' data-col='{i}' data-numeric='{int(numeric)}'>"
            f"{_h(hdr)}<span class='arrow'>\u25b4\u25be</span></th>"
        )
    return f"<tr>{''.join(ths)}</tr>"


def _detail_card(b: dict) -> str:
    pick = b.get("pick")
    picklabel = "<div class='picklabel'>Top value</div>" if pick else ""
    url = b.get("url")
    listing = (
        f"<div class='listing'><a href='{_h(url)}' target='_blank' "
        f"rel='noopener noreferrer'>View live listing \u2197</a></div>"
        if url else ""
    )
    return (
        f"<div class='bcard{' pick' if pick else ''}'>"
        f"{picklabel}"
        f"<div class='brand'>{_h(b.get('brand',''))}</div>"
        f"<div class='model'>{_h(b.get('model',''))}</div>"
        f"<div class='price'>{_h(b.get('price',''))}</div>"
        f"<div class='fit'>{_h(b.get('fit',''))}</div>"
        f"<div class='src'>Data: {_h(b.get('source',''))}</div>"
        f"{listing}"
        "</div>"
    )


_SORT_JS = """
<script>
(function(){
  var table=document.getElementById('cmp');
  if(!table) return;
  var tbody=table.tBodies[0];
  var ths=table.tHead.rows[0].cells;
  var state={col:-1,dir:1};
  function val(row,col,numeric){
    var td=row.cells[col];
    var s=td.getAttribute('data-sort');
    if(numeric) return parseFloat(s)||0;
    return (s||td.textContent).toLowerCase();
  }
  function sortBy(col){
    var numeric=ths[col].getAttribute('data-numeric')==='1';
    if(state.col===col){state.dir*=-1;}else{state.col=col;state.dir=1;}
    var rows=Array.prototype.slice.call(tbody.rows);
    rows.sort(function(a,b){
      var x=val(a,col,numeric), y=val(b,col,numeric);
      if(x<y) return -1*state.dir;
      if(x>y) return 1*state.dir;
      return 0;
    });
    rows.forEach(function(r){tbody.appendChild(r);});
    for(var i=0;i<ths.length;i++){ths[i].classList.toggle('sorted',i===col);}
  }
  for(var i=0;i<ths.length;i++){
    (function(idx){ths[idx].addEventListener('click',function(){sortBy(idx);});})(i);
  }
})();
</script>
"""


def build_boats_html() -> str:
    rows = "".join(_row(b) for b in BOATS)
    cards = "".join(_detail_card(b) for b in BOATS)
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    n = len(BOATS)
    verified = sum(1 for b in BOATS if b.get("provenance") == "verified")

    pills = [
        f"<span class='pill'>Boats&nbsp;<b>{n}</b></span>",
        "<span class='pill'>Target&nbsp;<b>20\u201322' aluminum hardtop</b></span>",
        "<span class='pill'>Budget&nbsp;<b>$40\u201355k</b></span>",
        f"<span class='pill'>Verified specs&nbsp;<b>{verified}/{n}</b></span>",
    ]

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Boat Comparison</title>"
        f"<style>{CSS}{BOATS_CSS}</style></head><body>"
        "<header class='page'>"
        "<h1><div class='brand-logo'>"
        "<span></span><span></span><span></span><span></span>"
        "</div>Boat Comparison</h1>"
        f"<div class='meta'>{n} shortlist boats \u00b7 updated {generated}</div>"
        "</header>"
        f"{render_nav('boats')}"
        "<section class='hero'>"
        "<h1>Boat Shortlist \u2693</h1>"
        "<div class='sub'>The 20\u201322' welded-aluminum hardtop-cabin boats in the running \u2014 "
        "click any column header to sort. Deciding specs for your use: shallow draft (dry "
        "weight), ride quality (deadrise + weight), and beam/stability.</div>"
        f"<div class='pill-row'>{''.join(pills)}</div>"
        "</section>"
        "<section class='section-pad'>"
        "<div class='scroll-hint'>\u2190 swipe the table sideways to compare specs \u2192</div>"
        "<div class='cmp-wrap'>"
        f"<table class='cmp' id='cmp'><thead>{_header_row()}</thead>"
        f"<tbody>{rows}</tbody></table>"
        "</div>"
        "<div class='legend'>"
        "<span><span class='prov verified'>verified</span> spec sheet / catalog / builder site</span>"
        "<span><span class='prov listing'>listing</span> from a live for-sale ad</span>"
        "<span><span class='prov approx'>approx</span> model-family figure (site JS-blocked); \u201c~\u201d = approximate</span>"
        "</div>"
        f"<div class='detail-grid'>{cards}</div>"
        "</section>"
        "<footer class='fun'>Refresh this chart by editing the <code>BOATS</code> list in "
        "<code>src/fishing/html_boats.py</code> and rerunning "
        "<code>python -m fishing.html_boats boats docs/boats.html</code>.</footer>"
        f"{_SORT_JS}"
        "</body></html>"
    )


# --- CLI --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv and argv[0].lower() != "boats":
        print(f"Unknown target: {argv[0]}")
        print("Usage: python -m fishing.html_boats boats [out.html]")
        return 2

    html_text = build_boats_html()
    if len(argv) >= 2:
        out = Path(argv[1])
    else:
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        out = reports / "boats.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
