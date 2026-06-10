# MCP Fishing

A local **MCP server** that turns the source documents in this folder into a
queryable fishing knowledge base, augmented with live free weather, marine
forecast, tide, and buoy data — so an LLM (Claude Desktop, Claude Code, etc.)
can generate an up-to-the-minute fishing report on demand.

## Source documents (in repo root)
- `Key facts.docx` — home/cabin/boat
- `Salmon Steelhead Trout.xlsx` — species, calendar, gear, 2025 log, state master
- `Washington State Rules.pdf` — WDFW 2025-26 pamphlet (effective 7/1/2025-6/30/2026)
- `Proposed State Plan.pdf` — proposed 2026-27 MA5-13 regs

## Setup
```powershell
cd 'C:\MCP Fishing'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Build the knowledge base (Phase 1)
```powershell
python -m fishing.build_kb
```

Outputs go to `kb/`:
- per-source JSON files
- `kb/fishing.sqlite` — single queryable database

## Inspect
```powershell
python -m fishing.inspect            # high-level summary
python -m fishing.inspect species    # dump species table
python -m fishing.inspect rules MA9  # current + proposed rules for MA9
```

## Run the MCP server (Phase 2)
```powershell
python -m fishing.server
```

The server speaks stdio. Register it in **Claude Desktop** by adding to
`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fishing": {
      "command": "C:\\MCP Fishing\\.venv\\Scripts\\python.exe",
      "args": ["-m", "fishing.server"],
      "cwd": "C:\\MCP Fishing"
    }
  }
}
```

### Available tools
| Tool | Purpose |
|---|---|
| `list_waters`, `list_spots`, `get_places`, `get_boat` | Static reference |
| `get_regulations(water, source?)` | Current + proposed WDFW rules |
| `get_calendar(water?, month?)` | Seasonal calendar |
| `get_species(name?)`, `get_gear(use?)`, `get_log_2025()` | Workbook lookups |
| `get_distance(from, to)` | Great-circle miles between known names |
| `get_forecast(water, hourly?)` | NOAA NWS land forecast |
| `get_marine_forecast(water)` | NWS coastal-waters text for MA9/MA10 |
| `get_tides(water, date?, days?)` | NOAA CO-OPS high/low predictions |
| `get_buoys(water)` | Latest NDBC observations |
| `get_wind(water, hours?)` | Open-Meteo hourly wind/gust/precip |
| `generate_report(water, date?)` | Composite report with everything above |

All weather/marine/tide sources are **free, no API key required**:
NOAA NWS, NOAA CO-OPS, NDBC, Open-Meteo.



## HTML reports & published Pages site

Two report generators are available:

- `python -m fishing.html_report` � 7-day Fluent-themed HTML for all 6 waters
  (MA9, MA10, Skykomish, Snohomish, Snoqualmie, Lake Sammamish).
- `python -m fishing.html_report_ma9` � MA9-only deep-dive with tide-x-weather
  heatmap, per-day SVG (tide curve + wind + temp + score strip + best-moment
  badges + +2 ft float-line reference). **This is the canonical template.**

Both write into `reports/` by default; pass an output path to override.

### Always-fresh report on your phone (GitHub Pages)

The repo ships with `.github/workflows/build-report.yml` which runs hourly
(plus on-demand via *Actions -> Run workflow*) and publishes the MA9 report to
`docs/index.html` on the `main` branch. To enable:

1. Push the repo to GitHub.
2. **Settings -> Pages -> Source: Deploy from a branch -> Branch: `main` /
   `/docs`** -> Save.
3. After ~1 min, the URL `https://<user>.github.io/<repo>/` will serve the
   report.
4. On iPhone: open the URL in Safari -> Share -> **Add to Home Screen** for an
   app-like icon. Tap to reload anytime; the workflow rebuilds the page every
   hour using live NOAA NWS / CO-OPS / NDBC / Open-Meteo data.
