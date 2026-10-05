# Boat Search — Requirements (Single Source of Truth)

> Canonical working doc for Toby's aluminum-boat search. Lives in OneDrive
> (`OneDrive - Microsoft\MCP Fishing\`) so it can be opened from VS Code and
> referenced from CoWork / Copilot alike. **This file supersedes
> `Revised boat search.md`** — keep everything here.
>
> Last updated: 2026-07-23

---

## 1. Who / where the boat lives

- **Owner:** Toby
- **Home:** 20719 NE 68th St, Redmond WA 98053
- **Cabin:** 7250 Mill Beach Ln, Clinton WA 98236 (Whidbey, Useless Bay)
- **Current boat:** 2006 Boston Whaler 160 Dauntless — "the Barnacle"
  (the boat we're looking to replace / step up from)
- **Primary waters:** Marine Area 9 (Admiralty Inlet), Marine Area 10
  (Seattle/Bremerton), plus the Skykomish / Snohomish / Snoqualmie rivers
  and Lake Sammamish.

Dominant use case: **MA9 salmon** — real chop past 10–12 kt and strong tidal
current — plus the ability to launch and fish comfortably in open water. Whidbey
beaching / solo-launch was an early want but is now **deprioritized** in favor of
rough-water comfort (see §4).

---

## 2. Hard filters (what the scanner enforces)

Locked into the Craigslist scanner (`src/fishing/scan_listings.py`):

| Filter | Value |
|--------|-------|
| Length (LOA) | **18–24 ft** |
| Year | **2000 or newer** |
| Price ceiling | **≤ $80,000** (scanner cap) · realistic target **~$50k** |
| Distance | **≤ 250 mi** from Redmond (47.71, -122.09) |
| Hull material | **Welded aluminum only** |

**Target brands** (aluminum PNW builders):
Duckworth · Alumaweld · North River · Hewescraft · KingFisher ·
Silver Streak · Weldcraft · Wooldridge

**Search regions scanned:** Seattle, Bellingham, Skagit, Olympic, Portland,
Yakima, Wenatchee, Spokane (Craigslist by-owner).

> Facebook Marketplace and Boat Trader / YachtWorld are deliberately excluded
> (login/ToS + Cloudflare walls). Revisit if coverage feels thin.

---

## 3. Core direction (soft cutoffs — general direction, not hard gates)

> **These describe the *shape* of the right boat, not a pass/fail checklist.**
> A boat that misses one line by a hair (e.g. an Intruder 20 at 2,295 lb vs the
> ~2,300 lb line — 5 lb / 0.2% under) is **not** disqualified. Treat these as
> the center of the target; weigh the whole package, and let a strong showing on
> what matters most offset a small miss elsewhere.

### Core direction (aim for these)
- **Deep-vee hull (~18°+ transom deadrise)** — the big one for MA9 chop
- **Heavy hull (~2,300 lb+ dry weight)** — rides through chop, stays planted
- **Bottom gauge ~.190"+**
- **Transom gauge ~.190"+** (`.250"` is the gold standard)
- **Cockpit length ~72"+**
- **Cabin height ~6'2"+**
- **Fuel capacity ~50 gal+** (bigger tank = longer trolling days)
- **Canvas or hybrid top preferred** (rigid removable frame ideal)
- **Documented service history** + low engine hours
- **Modern EFI kicker strongly preferred** (power tilt, electric start > old tiller T8)

### Strong preferences
- Offshore/step-thru bracket (cockpit space + dry ride) over transom-mount
- Suspension seats
- Clean rear-deck ergonomics + good mooching layout
- Aluminum rocket-launcher tubes

### Tie-breakers
- Larger fuel tank (70–90 gal)
- Premium kicker (power tilt, electric start)
- Electronics stack (modern MFD/chartplotter, radar)
- Downriggers included
- Recent trailer service

---

## 4. Key trade-off axis

```
  LIGHT / BEACHABLE / SOLO-LAUNCH  <----------------->  HEAVY / DEEP-VEE / MA9-COMFORT
        Duckworth Sport 20                              Alumaweld Intruder,
        (1,635 lb, 14° transom)                         North River Seahawk,
                                                        Duckworth Pac Nav 22
                                                        (2,300–2,900 lb, 18° vee)
```

The refined criteria in §3 place Toby **firmly on the right side** — the
MA9-comfort side. The old light-and-beachable want (Duckworth Sport 20) is kept
below as a contrast/fallback, not a front-runner.

---

## 5. Candidate models

Model-level comparison (mirrors the `BOATS` list in `html_boats.py`; prices are
model-level ranges, not asking prices). ⭐ = leans into the §3 core direction.

| Brand / Model | LOA | Beam | Deadrise | Bottom / Transom | Dry lb | Fuel | HP | Price (model) | Note |
|---|---|---|---|---|---|---|---|---|---|
| **North River Seahawk OB 21'** ⭐ *Top build* | 23'2" | 8'6" | 18° (42° entry) | .250" / .250" | 2,680 | 70 | 300 | Used ~$55–95k | Best-built hull; **lifetime hull warranty**. Soft top std; add rigid removable top for hardtop. |
| **Alumaweld Intruder 22 (Hardtop)** ⭐ *Best value* | 24'9" | 8'3.5" | 18° | .190" / .250" | 2,475 | 60 | 225 | Used ~$45–70k | Value-line deep-vee. Intruder 20 sibling is 2,295 lb (near-miss on weight — fine per §3). |
| **Duckworth Pacific Navigator 22** ⭐ | 25'0" (w/ bracket) | 8'6" | 18° (28° fwd / 34° bow) | .190" / TBD | 2,783 | 65 | 300 | Used ~$55–80k | Premium Duckworth offshore. Verified specs in §6. Verify transom gauge, cockpit, cabin, top. |
| **North River Coho 21' Hard Top** | 23'2" | 8'6" | 18° | .190" / .190" | 2,800 | 70 | 300 | $79,995 new · used ~$55–75k | Only true ~21' factory hardtop new. Value tier (7-yr warranty). Smaller 66" cockpit. |
| **KingFisher 2325 Coastal Express** | 24' | 8' | 16° (var.) | .190" / — | 2,660 | 85 | 250 | Used ~$65–90k | Biggest tank (85 gal), deep cockpit, pilot house. Flatter 16° + transom-mount fall short of core direction. |
| **Hewescraft 210 Searunner** | 22'6" | 8'0" | 16° | .160" / — | 2,250 | 55 | 150 | Used ~$40–55k | Best-selling WA aluminum / easy resale, but lighter build + 16° = protected-water class, below core direction. |
| **Duckworth Pacific Navigator Sport 20** | 21'11" | 7'9.5" | 14° transom | .190" / — | 1,635 | 42 | 200 | Used ~$40–55k | The light/beachable contrast. Fails the deep-vee + weight direction; kept as fallback. |
| **Silver Streak 21' Hardtop** | 21' (23.5' w/ bracket) | 8'6" | — | 7' reverse chine | — | — | — | Used ~$70–95k (BC premium) | Quality/ride benchmark. Usually over budget — reference point, not a likely buy. |

---

## 6. Verified specs (from spec sheets / builder pages)

### North River Seahawk (spec sheet)
- **42° hull entry / 18° transom deadrise**; **.250" bottom**, 35" sides
- **Cockpit:** 73" (22') · 85" (23')
- **Cabin height:** 74" (6'2")
- **Fuel:** 70–90 gal · **Dry weight:** 2,680–2,860 lb
- Canvas + hybrid rigid-frame top options
- **Price reality:** soft-top 21–22' ~$45–65k · soft-top 23' ~$55–85k · hardtops ~$70–110k. A **22' soft-top** is the best shot at ~$50k.

### Duckworth Pacific Navigator 22 (Duckworth.net)
- **LOA:** 25'0" (incl. bracket) · **Beam:** 8'6"
- **Deadrise:** transom **18°** · forward 28° · bow 34°
- **Bottom:** 0.190" (5086-H116), 7' bottom width
- **Sides:** 0.125" (5052-H32), 39" side height
- **Dry weight:** **2,783 lb** · **Fuel:** 65 USG (diurnal fuel system)
- **Max HP:** 300 · **Capacity:** 8 persons / 1,320 lb
- **Still verify** (not published): transom gauge (~.190"+), cockpit length (~72"+), cabin height (~6'2"+), top style (soft / hybrid / hardtop).

### Alumaweld Intruder (catalog)
- **18° deadrise** · **.190" bottom / .250" transom** · cockpit ≈ 78" · cabin ≈ 6'2" · fuel 60 gal
- **Dry weight:** Intruder 20 = 2,295 lb · Intruder 22 = 2,475 lb
- Canvas / hybrid tops common

---

## 7. Compatibility matrix (vs §3 core direction)

| Boat | Deadrise | Gauges | Cockpit | Cabin | Fuel | Weight | Top | Price fit | Verdict |
|------|----------|--------|---------|--------|-------|--------|------|-----------|---------|
| **North River Seahawk** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ (.250/.250) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | **Best overall; hard to find ≤ $50k** |
| **Alumaweld Intruder** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ (.190/.250) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **Best value; fits the direction well** |
| **Duckworth Pac Navigator 22** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ (.190 bottom; transom TBD) | ❓ verify | ❓ verify | ⭐⭐⭐⭐ (65 gal) | ⭐⭐⭐⭐⭐ (2,783 lb) | ⭐⭐⭐⭐ | ⭐⭐⭐ | **Strong hull fit; verify cockpit/cabin + top** |

---

## 8. Ranked shortlist

1. **Alumaweld Intruder 20/22 (soft or hybrid top)** — best value; fits the
   direction; strong used market close to home.
2. **Duckworth Pacific Navigator 22 (soft or hybrid top)** — strong hull fit
   (2,783 lb, 18° transom, 65 gal); verify cockpit length, cabin height, top style.
3. **North River Seahawk (soft or hybrid top)** — best ride and build; buy
   quickly if one lands at/near ~$50k.

> Ranking is by **attainability at the ~$50k target**, not raw build quality
> (on build alone the Seahawk leads).

---

## 9. Decision guide (holistic, not a checklist)

A **weighted judgment**, not an all-or-nothing gate. A boat that lands *at or
near* the §3 center — and clears what matters most for MA9 — is worth a survey
and an offer, even if it misses a line or two by a small margin.

**Matters most (a real miss here gives real pause):**
- Deep-vee (~18°+ transom) + heavy hull (~2,300 lb+)
- Structurally sound: ~.190"+ bottom & transom, clean survey
- Price in reach (~$50k target; a bit over is fine if the boat is right)

**Matters, but a near-miss is fine:**
- Cockpit ~72"+, cabin ~6'2"+, fuel ~50 gal+ — a couple inches or a few
  gallons short doesn't sink the deal
- Canvas/hybrid top, documented history, modern EFI kicker

**Rule of thumb:** close to center on the must-haves + clean survey →
**schedule survey + make offer.** A single small miss (the 5-lb example) is
noise, not a veto. Reserve a hard "no" for a stack of misses or a failure on
something that matters for open-water safety.

---

## 10. Survey checklist (any candidate)

- **Engine:** confirm model code (4-stroke vs 2-stroke), compression across all
  cylinders, lower-unit oil metal check, hours.
- **Kicker:** model + hours; confirm high-thrust / power-tilt as claimed.
- **Fuel tank:** aluminum diurnal pressure test (mandatory on older hulls).
- **Bracket:** weld dye-penetrant; transom moisture at bracket bolts.
- **Top/cabin:** hardtop-to-cabin and window seal condition.
- **Trailer:** bearings, brake actuator, wiring, tires.
- **Storage history:** inside vs outside (big value delta on aluminum boats).

---

## 11. Open questions / decisions to make

- [x] **Ride vs launch** — resolved: committed to the heavy deep-vee (MA9-comfort)
  direction; beachability deprioritized. *(Confirm if that ever shifts back.)*
- [ ] **Hardtop:** must-have on day one, or accept a soft/hybrid top + later add?
- [ ] **New vs used:** North River Coho at $79,995 new turnkey vs a used deep-vee?
- [ ] **Pacific Navigator 22:** confirm transom gauge, cockpit length, cabin
  height, and top style on any specific unit.
- [ ] **Weight line:** keep ~2,300 lb as the soft center (so an Intruder 20 at
  2,295 stays in), or nudge toward the Intruder 22 to clear it outright?

---

## 12. Provenance legend

- **verified** — from a spec sheet / catalog PDF or builder site.
- **approx** — general/model-family knowledge (values prefixed `~`).

---

## 13. How this doc connects to the tooling

- **Rendered comparison:** `src/fishing/html_boats.py` → `docs/boats.html`
  is a **running comparison of candidate MODELS and their trade-offs** (not
  specific for-sale units). Edit the `BOATS` list and rerun
  `python -m fishing.html_boats boats docs/boats.html`.
- **Live scanner (background only):** `src/fishing/scan_listings.py` still
  runs locally (Task Scheduler "MCP-Fishing-ScanListings") and writes
  `data/listings.json` for reference, but its results are **no longer shown**
  on the boats page.
- **Refresh:** `scan-listings.cmd` at the workspace root runs the scan and
  rebuilds `docs/boats.html`.

---

## 14. Latest requirement set + retrofit-value table (2026-07-23)

Toby's current wish list, scored by **what it costs to add after purchase**.
Use the "Retrofit cost" column as the *dollar weight* to apply when a candidate
boat is missing that feature — i.e. how much to knock off an asking price (or
budget on top) to end up where you want. The "At-purchase priority" column flags
what's effectively **impossible/expensive to change** (must be right on day one)
vs. **cheap bolt-ons** you can defer.

> Costs are PNW installed-price approximations (parts + typical shop labor) for a
> 21–24' welded-aluminum boat, mid-2026. Ranges are wide because it depends on
> the specific boat and whether a fab shop or DIY.

*Sorted by at-purchase priority (highest first), then by approximate retrofit
cost (highest first) within each priority tier.*

| # | Requirement | Retrofittable? | Approx. retrofit cost (installed) | Difficulty / risk | At-purchase priority |
|---|-------------|----------------|-----------------------------------|-------------------|----------------------|
| 1 | **21'+ length, offshore bracket** | ❌ Length: no · Bracket: barely | $4,000–8,000 to fab/weld a bracket (if the transom even suits it); length can't change | High — structural welding, affects flotation/ride | **MUST be right at purchase** — non-negotiable, essentially the hull you buy |
| 2 | **Bright cabin w/ windows + open rear** (walk-through) | ⚠️ Mostly architectural | $1,500–5,000 to add/enlarge windows or open a bulkhead; often not practical | High — cutting cabin structure | **Buy it built this way** — layout is baked into the hull |
| 3 | **Huge back deck** (people space) | ❌ Layout is fixed | n/a (can't grow the cockpit) | — | **Buy it built this way** — cockpit sq-ft is a hull decision |
| 4a | **Yamaha 150–250 main** | ✅ Repower | $18,000–30,000+ for a new main + rigging | High cost, moderate labor | High — repower is the single most expensive add; strongly prefer a good main already on it |
| 4b | **9.9 kicker (high-thrust, EFI)** | ✅ Common add | $3,500–6,000 installed | Moderate — mount, fuel, wiring | Medium — retrofittable, but adds up |
| 5 | **Reactor 40 (or similar) autopilot, easy override** | ✅ Yes | $2,000–4,000 (drive/pump kit + install; less if hydraulic steering already there) | Moderate — needs compatible steering | Medium — deferrable bolt-on |
| 6 | **Rod tower / rocket launcher (also adds strength)** | ✅ Yes | $1,500–4,000 welded aluminum tower/arch | Moderate — fabrication | Medium — deferrable, but priced like a project |
| 4c | **Kicker tie-bar to main + forward controls** | ✅ Yes | $150–500 tie-bar · $300–1,500 to run kicker binnacle/controls up front | Low–moderate | Low–medium — cheap-ish if kicker exists |
| 7 | **Garmin GPS / chartplotter** | ✅ Easy | $1,000–3,500 (MFD + transducer, installed) | Low — standard rig | Low — add anytime; brand-swappable |
| 9 | **Rear (transom) door** — "nice to have" | ⚠️ Yes, invasive | $800–2,500 to cut & frame a transom door | Moderate — structural cut | Low — optional; only if it's a clean add |
| 8 | **Rear storage / bait station with a lip** | ✅ Yes | $400–1,500 fabricated aluminum station | Low–moderate | Low — easy bolt-on/weld |
| 3b | **Indoor/outdoor side chairs** (swappable seating) | ✅ Easy | $200–700 per removable/pedestal seat | Low — bolt-in / slide-mount | Low — add anytime |

### How to read it
- **Buy-it-built (items 1, 2, 3):** hull length, bracket, cabin brightness/open
  rear, and cockpit size are **not realistically retrofittable** — these define
  which boats even make the shortlist. Weight them near-100%.
- **Big-money repower (4a):** a strong Yamaha 150–250 already on the boat is
  worth ~$18k–30k of avoided cost. Treat a tired/small main as a large price
  deduction, not a shrug.
- **Cheap deferrables (3b, 7, 8, and largely 4c/5):** electronics, seating,
  bait station, tie-bar/controls, and autopilot are all **add-later** items.
  Don't overpay for a boat *just* because it has these — they're a few thousand
  dollars you can add on your own schedule.
- **Mid-tier projects (4b, 6):** kicker and tower are retrofittable but each is
  a real several-thousand-dollar job — nice to inherit, not dealbreakers.

**Rule of thumb for offers:** sum the retrofit costs of everything a candidate is
*missing* → that's roughly the discount (or added budget) versus a fully-equipped
boat. Items 1–3 aren't in that math — if they're wrong, walk.
