"""Boat shopping comparison tab (desktop + mobile).

A static reference tab in the fishing-report site: the boat shortlist lives
in the ``BOATS`` list below, so refreshing the chart is just editing that list
and rerunning the build. No live data, so it rebuilds cheaply alongside the
forecast and gear tabs.

The list is a running comparison of candidate MODELS and their tradeoffs, not
specific for-sale units.

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
        "brand": "North River", "model": "Seahawk Outboard 21'",
        "loa": "23'2\"", "beam": "8'6\"", "deadrise": "18\u00b0 (42\u00b0 entry)",
        "bottom": ".250\"", "sides": ".160\"", "transom_thk": ".250\"",
        "dry": 2680, "fuel": 70, "hp": 300,
        "bracket": "Yes (offshore, std)", "warranty": "Lifetime hull",
        "price": "Used ~$55\u201395k \u00b7 new ~$110k+",
        "price_sort": 72000,
        "provenance": "verified",
        "source": "2025 Seahawk spec sheet",
        "tag": "p",
        "fit": "The strongest hull in the running and my benchmark for MA9 "
               "rough water. .250\" bottom + .250\" transom + towering 35\" "
               "sides + North River's LIFETIME (transferable) hull warranty "
               "\u2014 vs the Coho's .190\" / 7-yr, same brand's value tier. "
               "42\u00b0 entry / 18\u00b0 transom = the softest, driest ride here, and "
               "it stays stuck-down in a chop. TRADEOFFS: heavy (2,680 lb) so "
               "it's a harder solo-launch/tow than the Duckworth Sport, and it "
               "ships with a deluxe FOLDING soft top standard \u2014 add the rigid "
               "removable top for a pop-off hardtop; a true enclosed factory "
               "hardtop means stepping up to the 23' Hard Top (25'2\" LOA, "
               "~3,060 lb). Premium price \u2014 buy older/plainer to stay in "
               "budget. Best fit if ride quality and build are the priority.",
        "pick": True,
        "picklabel": "Top build",
    },
    {
        "brand": "Alumaweld", "model": "Intruder 22 (Hardtop)",
        "loa": "24'9\"", "beam": "8'3.5\"", "deadrise": "18\u00b0",
        "bottom": ".190\"", "sides": ".125\"", "transom_thk": ".250\"",
        "dry": 2475, "fuel": 60, "hp": 225,
        "bracket": "Yes (Alumadrive)", "warranty": "Limited",
        "price": "Used ~$45\u201370k \u00b7 new ~$90k+",
        "price_sort": 60000,
        "provenance": "verified",
        "source": "2026 catalog PDF",
        "tag": "b",
        "fit": "Alumaweld's value OFFSHORE boat \u2014 not the entry line. Full "
               "18\u00b0 vee, .190\" bottom + heavy .250\" transom, Alumadrive "
               "bracket standard \u2014 one of the deepest-vee hulls in the "
               "shortlist at the 20-22' size. Heavier (2,475 lb) than the "
               "Duckworth Sport, so it rides softer and stays stuck-down in "
               "MA9 chop past 10-12 kt. Offered as DuraFrame Sport Top or full "
               "hardtop. TRADEOFFS vs the Seahawk: thinner .190\" bottom and "
               "limited (not lifetime) warranty, but typically a lower buy-in "
               "\u2014 the value-priced way into a real deep-vee. TRADEOFFS vs "
               "lighter boats: more trailer weight, worse solo-launch, 225 HP "
               "ceiling.",
    },
    {
        "brand": "Duckworth", "model": "Pacific Navigator 22",
        "loa": "25'0\" (incl. bracket)", "beam": "8'6\"",
        "deadrise": "18\u00b0 transom (28\u00b0 fwd / 34\u00b0 bow)",
        "bottom": ".190\" (5086-H116)", "sides": ".125\" (5052-H32)",
        "transom_thk": "\u2014",
        "dry": 2783, "fuel": 65, "hp": 300,
        "bracket": "Yes (offshore, std)", "warranty": "\u2014",
        "price": "Used ~$55\u201380k \u00b7 new ~$120k+",
        "price_sort": 68000,
        "provenance": "verified",
        "source": "Duckworth.net spec page (Pacific Navigator 22)",
        "tag": "o",
        "fit": "The premium-Duckworth offshore model \u2014 a completely different "
               "boat from the value Sport 20. Published specs: 18\u00b0 transom "
               "(28\u00b0 forward / 34\u00b0 bow entry), .190\" bottom (5086-H116) + "
               ".125\" sides, 39\" side height, 7' bottom width, 8'6\" beam, "
               "2,783 lb dry, 65-gal diurnal fuel system, 300 HP rating. "
               "MEETS the refined non-negotiables: \u226518\u00b0 deadrise, \u2265.190\" "
               "bottom, \u22652,300 lb dry, \u226550 gal fuel. TRADEOFFS: one of the "
               "biggest hulls here (25'0\" incl. bracket), so the most boat to "
               "tow/launch/store. STILL VERIFY (not on the spec page): transom "
               "gauge, cockpit length (\u226572\" target), cabin height (\u22656'2\" "
               "target), and whether the unit has a soft/hybrid or full "
               "hardtop.",
    },
    {
        "brand": "North River", "model": "Coho 21' Hard Top",
        "loa": "23'2\"", "beam": "8'6\"", "deadrise": "18\u00b0",
        "bottom": ".190\"", "sides": ".160\"", "transom_thk": ".190\"",
        "dry": 2800, "fuel": 70, "hp": 300,
        "bracket": "Yes (standard)", "warranty": "7-yr hull",
        "price": "$79,995 new (turnkey) \u00b7 used ~$55\u201375k",
        "price_sort": 79995,
        "provenance": "verified",
        "source": "dealer PDF",
        "tag": "g",
        "fit": "The only true ~21' FACTORY hardtop at an attainable NEW "
               "number, and turnkey (150 HP + trailer + hydraulic steering + "
               "offshore bracket standard). TRADEOFFS: it's North River's "
               "VALUE tier \u2014 .190\" bottom + 7-yr warranty vs the Seahawk's "
               ".250\" + lifetime (same brand, lighter build). Cockpit is "
               "smaller (66\") than the bigger hulls. Best fit if you want a "
               "brand-new enclosed hardtop without stepping up to the 23' "
               "Seahawk Hard Top's price.",
    },
    {
        "brand": "KingFisher", "model": "2325 Coastal Express",
        "loa": "24'", "beam": "8'", "deadrise": "16\u00b0 (var.)",
        "bottom": ".190\"", "sides": ".125\"",
        "dry": 2660, "fuel": 85, "hp": 250,
        "bracket": "No (transom)", "warranty": "Lifetime hull",
        "price": "Used ~$65\u201390k \u00b7 new ~$120k+",
        "price_sort": 78000,
        "provenance": "verified",
        "source": "2026 KingFisher boat guide PDF",
        "tag": "t",
        "fit": "Value-quality middle ground. Flatter 16\u00b0 variable-deadrise "
               "hull = slightly firmer offshore ride but very stable, and "
               "lifetime hull warranty. Biggest tank here (85 gal \u2014 longest "
               "trolling range) and a deep 6'2\" cockpit; pilot-house cabin "
               "(7'2\", 6'1\" headroom). TRADEOFFS: it's TRANSOM-mounted (25\", "
               "step-thru) rather than bracketed like the Duckworth/Alumaweld, "
               "the flatter hull gives up some big-chop cushion vs the 18\u00b0 "
               "vees, and it's capped at 250 HP.",
    },
    {
        "brand": "Hewescraft", "model": "210 Searunner",
        "loa": "22'6\" (incl. bracket)", "beam": "8'0\"",
        "deadrise": "16\u00b0",
        "bottom": ".160\"", "sides": ".100\"", "transom_thk": "\u2014",
        "dry": 2250, "fuel": 55, "hp": 150,
        "bracket": "Yes (offshore, std)", "warranty": "Limited",
        "price": "Used ~$40\u201355k \u00b7 new ~$90k+",
        "price_sort": 47000,
        "provenance": "verified",
        "source": "Hewescraft model guide",
        "tag": "b",
        "fit": "The value-tier PNW workhorse. Hewescraft is the best-selling "
               "aluminum boat in WA \u2014 legendary resale, easy to fix, "
               "everyone knows what it is. The Searunner is the SEMI-cabin "
               "line (small cuddy + open helm) between the open Sportsman and "
               "the full-pilothouse Ocean Pro. IMPORTANT class distinction: "
               "this is NOT the same class of offshore boat as the Seahawk / "
               "Intruder / Duckworth 235 \u2014 lighter build (.160\" bottom, "
               ".100\" sides, thinnest here), 150 HP ceiling caps a repower. "
               "Rides firmer in real MA9 chop; competent for Saratoga / Skagit "
               "Bay / Possession Bar fair-weather, marginal for Deception Pass "
               "/ open Strait on a 3-4' day. No hardtop in this trim. Best fit "
               "as the affordable, protected-water, easy-resale option.",
    },
    {
        "brand": "Duckworth", "model": "Pacific Navigator Sport 20",
        "loa": "21'11\" (incl. bracket)", "beam": "7'9.5\"",
        "deadrise": "14\u00b0 transom (24\u00b0 fwd / 30\u00b0 bow)",
        "bottom": ".190\"", "sides": ".125\"",
        "dry": 1635, "fuel": 42, "hp": 200,
        "bracket": "Yes (25\" offshore, std)", "warranty": "\u2014",
        "price": "Used ~$40\u201355k",
        "price_sort": 48000,
        "provenance": "verified",
        "source": "Duckworth model guide PDF",
        "tag": "o",
        "fit": "The LIGHT / BEACHABLE end of the shortlist \u2014 Duckworth's "
               "value SPORT trim (not the upscale 215 SE). At ~1,635 lb dry "
               "it's by far the lightest hull here: easiest to solo-launch, "
               "beach at Useless Bay, and tow behind anything. Full "
               "reverse-chine bottom + 30\u00b0 bow entry keep the ride soft; the "
               "flatter 14\u00b0 transom trades some big-water cushion for "
               "stability at rest \u2014 nice for mooching. Standard 25\" offshore "
               "bracket. TRADEOFFS vs the bigger hulls: 7'9.5\" beam is the "
               "NARROWEST here (vs 8'-8'6\"), the 42-gal tank caps range "
               "(~7-8 hrs trolling), 200 HP ceiling, and it ships with a soft "
               "convertible top \u2014 NOT a hardtop, so it doesn't satisfy that "
               "want on its own (removable hardtop add ~$3-5k later). Best fit "
               "if beach/solo-launch flexibility matters more than a big-chop "
               "MA9 hull.",
        "pick": True,
        "picklabel": "Lightest / beachable",
    },
    {
        "brand": "Silver Streak", "model": "21' Hardtop",
        "loa": "21' (23.5' w/ bracket)", "beam": "8'6\"", "deadrise": "\u2014",
        "bottom": "7' w/ reverse chines", "sides": "\u2014",
        "dry": "\u2014", "fuel": "\u2014", "hp": "\u2014",
        "bracket": "Yes (offshore)", "warranty": "\u2014",
        "price": "Used ~$70\u201395k (BC premium)",
        "price_sort": 85000,
        "provenance": "approx",
        "source": "builder site + general",
        "tag": "b",
        "fit": "Premium BC tank and the quality/ride benchmark I measure the "
               "others against. True reverse chines = very stable + dry ride, "
               "~7 gph @ 30 mph. Factory hardtop. TRADEOFF: typically over "
               "budget and the priciest to buy in, so it's more a reference "
               "point than a likely purchase.",
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
    ("transom_thk", "Transom", False),
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
    picklabel = (
        f"<div class='picklabel'>{_h(b.get('picklabel', 'Top value'))}</div>"
        if pick else ""
    )
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
  function attach(tableId){
    var table=document.getElementById(tableId);
    if(!table||!table.tHead) return;
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
  }
  attach('cmp');
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
        f"<span class='pill'>Models&nbsp;<b>{n}</b></span>",
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
        "<div class='sub'>A running comparison of the 20\u201322' welded-aluminum "
        "hardtop-cabin MODELS in the running \u2014 not specific for-sale units. "
        "Click any column header to sort. Deciding specs for your use: shallow "
        "draft (dry weight), ride quality (deadrise + weight), and "
        "beam/stability.</div>"
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
        "<span><span class='prov approx'>approx</span> model-family figure; \u201c~\u201d = approximate</span>"
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
