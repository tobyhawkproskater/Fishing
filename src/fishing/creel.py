"""Fetch, archive, and render WDFW Puget Sound creel trends."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import httpx

from . import ROOT
from .html_loadout import render_nav
from .html_report import CSS, _h


SOURCE_URL = "https://wdfw.wa.gov/fishing/reports/creel/puget"
CACHE_PATH = ROOT / "data" / "creel_history.json"
AREAS = {
    "MA4": ("Area 4,",),
    "MA5": ("Area 5,",),
    "MA6": ("Area 6,", "Area 6-1,", "Area 6-2,"),
    "MA7": ("Area 7,",),
    "MA8-1": ("Area 8-1,",),
    "MA8-2": ("Area 8-2,",),
    "MA9": ("Area 9,",),
    "MA10": ("Area 10,",),
}
# Home water: everything else on this page is context for MA9, so it gets the
# emphasized treatment in the chart, legend, cards, and table.
FOCUS_AREA = "MA9"


class _CreelTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._in_table = False
        self._in_caption = False
        self._in_cell = False
        self._caption: list[str] = []
        self._cell: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._caption = []
        elif self._in_table and tag == "caption":
            self._in_caption = True
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in {"td", "th"}:
            self._in_cell = True
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self._caption.append(data)
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "caption":
            self._in_caption = False
        elif tag in {"td", "th"} and self._in_cell:
            self._row.append(" ".join("".join(self._cell).split()))
            self._in_cell = False
        elif tag == "tr" and len(self._row) == 12 and self._row[0] != "Ramp/site":
            row = _parse_row(" ".join(self._caption).strip(), self._row)
            if row:
                self.rows.append(row)
        elif tag == "table":
            self._in_table = False


def _number(value: str, *, integer: bool = False) -> int | float:
    try:
        return int(value) if integer else float(value)
    except ValueError:
        return 0 if integer else 0.0


def _parse_row(caption: str, cells: list[str]) -> dict | None:
    try:
        day = dt.datetime.strptime(caption, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None
    return {
        "date": day,
        "ramp": cells[0],
        "catch_area": cells[1],
        "interviews": _number(cells[2], integer=True),
        "anglers": _number(cells[3], integer=True),
        "chinook": _number(cells[5], integer=True),
        "coho": _number(cells[6], integer=True),
        "chum": _number(cells[7], integer=True),
        "pink": _number(cells[8], integer=True),
        "sockeye": _number(cells[9], integer=True),
        "source": SOURCE_URL,
    }


def parse_creel_html(html_text: str) -> list[dict]:
    parser = _CreelTableParser()
    parser.feed(html_text)
    return parser.rows


class _PagerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pages = {0}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        for value in parse_qs(urlparse(href).query).get("page", []):
            try:
                self.pages.add(int(value))
            except ValueError:
                pass


def _page_numbers(html_text: str) -> set[int]:
    parser = _PagerParser()
    parser.feed(html_text)
    return parser.pages


def _load_cache(path: Path = CACHE_PATH) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("rows", [])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _fetch_page(page: int = 0) -> str:
    params = {"sample_date": "3"}
    if page:
        params["page"] = str(page)
    try:
        response = httpx.get(
            SOURCE_URL,
            params=params,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": SOURCE_URL,
            },
            follow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise

    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            "30",
            "--user-agent",
            "Mozilla/5.0 (compatible; MCP-Fishing creel trends)",
            f"{SOURCE_URL}?sample_date=3&page={page}",
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _fetch_html() -> str:
    first_page = _fetch_page()
    pages = range(1, max(_page_numbers(first_page)) + 1)
    return "".join([first_page, *(_fetch_page(page) for page in pages)])


def update_history(path: Path = CACHE_PATH) -> tuple[list[dict], str | None]:
    """Merge WDFW's rolling 60-day view into the persistent raw-row cache."""
    cached = _load_cache(path)
    error = None
    try:
        fresh = parse_creel_html(_fetch_html())
        if not fresh:
            raise ValueError("WDFW response contained no creel rows")
    except (httpx.HTTPError, subprocess.SubprocessError, OSError, ValueError) as exc:
        fresh = []
        error = str(exc)

    merged = {
        (row["date"], row["ramp"], row["catch_area"]): row
        for row in [*cached, *fresh]
    }
    rows = sorted(merged.values(), key=lambda row: (row["date"], row["catch_area"], row["ramp"]))
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "updated": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "source": SOURCE_URL,
                    "rows": rows,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    return rows, error


def _area_key(catch_area: str) -> str | None:
    for key, prefixes in AREAS.items():
        if catch_area.startswith(prefixes):
            return key
    return None


def aggregate(rows: Iterable[dict]) -> list[dict]:
    totals: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"anglers": 0, "interviews": 0, "coho": 0, "chinook": 0}
    )
    for row in rows:
        area = _area_key(row["catch_area"])
        if not area:
            continue
        item = totals[(row["date"], area)]
        for field in ("anglers", "interviews", "coho", "chinook"):
            item[field] += row[field]

    result = []
    for (day, area), item in sorted(totals.items()):
        anglers = item["anglers"]
        result.append({
            "date": day,
            "area": area,
            **item,
            "coho_rate": item["coho"] / anglers if anglers else 0.0,
            "chinook_rate": item["chinook"] / anglers if anglers else 0.0,
        })
    return result


def _period_rate(points: list[dict]) -> tuple[float, int, int]:
    anglers = sum(point["anglers"] for point in points)
    fish = sum(point["coho"] for point in points)
    return (fish / anglers if anglers else 0.0, anglers, fish)


def trend_summary(points: list[dict], area: str) -> dict:
    area_points = [point for point in points if point["area"] == area]
    recent = area_points[-3:]
    baseline = area_points[-10:-3]
    recent_rate, recent_anglers, recent_fish = _period_rate(recent)
    baseline_rate, baseline_anglers, baseline_fish = _period_rate(baseline)
    ratio = recent_rate / baseline_rate if baseline_rate > 0 else None
    enough = recent_anglers >= 20 and baseline_anglers >= 30
    if enough and recent_rate >= 0.35 and (baseline_rate < 0.10 or (ratio or 0) >= 2):
        signal = "SURGE"
    elif enough and recent_rate >= 0.15 and (baseline_rate < 0.08 or (ratio or 0) >= 1.35):
        signal = "RISING"
    elif not enough and recent_anglers >= 20 and recent_rate >= 0.35:
        signal = "HOT NOW"
    elif recent_anglers < 20:
        signal = "LOW SAMPLE"
    else:
        signal = "STEADY"
    return {
        "area": area,
        "signal": signal,
        "rate": recent_rate,
        "anglers": recent_anglers,
        "fish": recent_fish,
        "interviews": sum(point["interviews"] for point in recent),
        "recent_days": len(recent),
        "recent_start": recent[0]["date"] if recent else None,
        "recent_end": recent[-1]["date"] if recent else None,
        "baseline": baseline_rate,
        "baseline_anglers": baseline_anglers,
        "baseline_fish": baseline_fish,
        "baseline_days": len(baseline),
        "ratio": ratio,
    }


CREEL_CSS = """
.creel-hero{padding:26px 32px 20px;background:#003B4F;color:#fff}
.creel-hero h1{margin:0;font-size:26px;font-weight:650}.creel-hero p{margin:6px 0 0;max-width:850px;color:#D6F2F5}
.creel-main{padding:22px 32px 34px;max-width:1240px;margin:auto}.signal-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.signal{background:#fff;border:1px solid var(--ms-border);border-top:5px solid #0078D4;border-radius:6px;padding:14px;box-shadow:var(--shadow-sm)}
.signal.surge,.signal.hot-now{border-top-color:#D83B01}.signal.rising{border-top-color:#107C10}.signal.low-sample{border-top-color:#A19F9D}
.signal .area{font-size:19px;font-weight:700}.signal .state{font-size:11px;font-weight:800;color:var(--ms-text-secondary);letter-spacing:.5px}
.signal .rate{font-size:30px;font-weight:650;margin-top:8px}.signal .unit{font-size:11px;color:var(--ms-text-secondary);margin-bottom:10px}
.signal .detail{font-size:12px;color:var(--ms-text-secondary);line-height:1.5}.signal .comparison{margin-top:8px;padding-top:8px;border-top:1px solid var(--ms-border);color:var(--ms-text)}
.trend-panel{margin-top:18px;background:#fff;border:1px solid var(--ms-border);border-radius:6px;padding:18px;box-shadow:var(--shadow-sm)}
.trend-panel h2{margin:0 0 3px;font-size:18px}.trend-panel .sub{color:var(--ms-text-secondary);font-size:12px;margin-bottom:14px}
.chart-wrap{overflow-x:auto}.creel-chart{display:block;width:100%;min-width:720px;height:auto}.creel-chart text{font-family:'Segoe UI',sans-serif;fill:#605E5C;font-size:11px}
.creel-chart text.focus-label{font-size:14px;font-weight:700}
.signal.focus{box-shadow:0 0 0 3px rgba(0,120,212,.35),var(--shadow-sm)}
.signal .home{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:9px;background:#0078D4;color:#fff;font-size:10px;font-weight:800;letter-spacing:.4px;vertical-align:middle}
.sample-table tr.focus td{background:#EFF6FC;font-weight:600;box-shadow:inset 3px 0 0 #0078D4}
.sample-table{width:100%;border-collapse:collapse;font-size:13px}.sample-table th,.sample-table td{padding:9px 10px;border-bottom:1px solid var(--ms-border);text-align:right;white-space:nowrap}.sample-table th:first-child,.sample-table td:first-child{text-align:left}.sample-table th{color:var(--ms-text-secondary);font-size:11px;text-transform:uppercase}.sample-table tbody tr:last-child td{border-bottom:0}
.method{margin-top:18px;padding:14px 16px;background:#F3F2F1;border-left:4px solid #0078D4;font-size:12px;color:#605E5C}
@media(max-width:760px){.creel-hero{padding:20px 16px}.creel-main{padding:16px}.signal-grid{grid-template-columns:1fr 1fr}.signal .rate{font-size:25px}}
"""


def _render_chart(points: list[dict]) -> str:
    days = sorted({point["date"] for point in points})[-30:]
    by_key = {(point["date"], point["area"]): point for point in points}
    width, height, left, top, right, bottom = 1000, 330, 52, 20, 18, 44
    chart_w, chart_h = width - left - right, height - top - bottom
    max_rate = max((point["coho_rate"] for point in points if point["date"] in days), default=1)
    ceiling = max(0.5, min(2.0, (int(max_rate * 4) + 1) / 4))
    parts = [f"<svg class='creel-chart' viewBox='0 0 {width} {height}' role='img' aria-label='Reported coho per interviewed angler by marine area'>"]
    for tick in range(5):
        rate = ceiling * tick / 4
        y = top + chart_h - chart_h * tick / 4
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{width-right}' y2='{y:.1f}' stroke='#E1DFDD'/><text x='{left-7}' y='{y+4:.1f}' text-anchor='end'>{rate:.2f}</text>")
    colors = {
        "MA4": "#C19C00",
        "MA5": "#5C2D91",
        "MA6": "#D83B01",
        "MA7": "#008272",
        "MA8-1": "#498205",
        "MA8-2": "#C239B3",
        "MA9": "#0078D4",
        "MA10": "#8764B8",
    }
    # MA9 is the home area, so it is drawn last (on top of every other line),
    # twice as thick, with larger markers and an inline end-of-line label. The
    # other areas drop to a thinner, semi-transparent stroke so they read as
    # context rather than competing for attention on a phone screen.
    for area in sorted(AREAS, key=lambda a: a == FOCUS_AREA):
        focus = area == FOCUS_AREA
        coords = []
        for index, day in enumerate(days):
            point = by_key.get((day, area))
            if point is None:
                continue
            x = left + (chart_w * index / max(1, len(days) - 1))
            y = top + chart_h * (1 - min(point["coho_rate"], ceiling) / ceiling)
            coords.append((x, y, point))
        if coords:
            path = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y, _) in enumerate(coords))
            stroke_w = 6 if focus else 2
            opacity = 1 if focus else 0.45
            if focus:
                # Halo underneath keeps the MA9 line legible where it crosses
                # a same-hued context line.
                parts.append(f"<path d='{path}' fill='none' stroke='#FFFFFF' stroke-width='{stroke_w+4}'"
                             " stroke-linecap='round' stroke-linejoin='round'/>")
            parts.append(f"<path d='{path}' fill='none' stroke='{colors[area]}' stroke-width='{stroke_w}'"
                         f" stroke-opacity='{opacity}' stroke-linecap='round' stroke-linejoin='round'/>")
            for x, y, point in coords:
                title = f"{area} {point['date']}: {point['coho']} coho / {point['anglers']} anglers ({point['coho_rate']:.2f})"
                if focus:
                    parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='7' fill='{colors[area]}'"
                                 f" stroke='#FFFFFF' stroke-width='2'><title>{_h(title)}</title></circle>")
                else:
                    parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{colors[area]}'"
                                 f" fill-opacity='{opacity}'><title>{_h(title)}</title></circle>")
            if focus:
                end_x, end_y, _ = coords[-1]
                anchor = "end" if end_x > width - right - 60 else "start"
                label_x = end_x - 12 if anchor == "end" else end_x + 12
                parts.append(f"<text class='focus-label' x='{label_x:.1f}' y='{end_y-13:.1f}'"
                             f" text-anchor='{anchor}' fill='{colors[area]}'>{FOCUS_AREA}</text>")
    label_step = max(1, len(days) // 6)
    for index, day in enumerate(days):
        if index % label_step == 0 or index == len(days) - 1:
            x = left + chart_w * index / max(1, len(days) - 1)
            parts.append(f"<text x='{x:.1f}' y='{height-18}' text-anchor='middle'>{day[5:]}</text>")
    legend_x = left
    for area in AREAS:
        focus = area == FOCUS_AREA
        text_attrs = f" class='focus-label' fill='{colors[area]}'" if focus else ""
        parts.append(
            f"<line x1='{legend_x}' y1='{height-9}' x2='{legend_x+20}' y2='{height-9}'"
            f" stroke='{colors[area]}' stroke-width='{6 if focus else 2}'"
            f" stroke-opacity='{1 if focus else 0.45}' stroke-linecap='round'/>"
            f"<text{text_attrs} x='{legend_x+25}' y='{height-5}'>{area}</text>"
        )
        legend_x += 82
    parts.append("</svg>")
    return "".join(parts)


def _comparison_text(item: dict) -> str:
    if not item["baseline_days"]:
        return "Prior trend window: not enough sampled days yet"
    if not item["baseline_anglers"]:
        return f"Prior {item['baseline_days']} days: no anglers sampled"
    prior = (
        f"Prior {item['baseline_days']} days: {item['baseline']:.2f} "
        f"({item['baseline_fish']} coho / {item['baseline_anglers']} anglers)"
    )
    if item["baseline"] == 0:
        return prior
    change = (item["rate"] / item["baseline"] - 1) * 100
    return f"{prior} · Change {change:+.0f}%"


def _render_latest_table(points: list[dict]) -> str:
    rows = []
    for area in AREAS:
        area_points = [point for point in points if point["area"] == area]
        if not area_points:
            continue
        point = area_points[-1]
        tr = "<tr class='focus'>" if area == FOCUS_AREA else "<tr>"
        rows.append(
            f"{tr}<td><b>{area}</b></td><td>{point['date'][5:]}</td>"
            f"<td>{point['coho']}</td><td>{point['chinook']}</td>"
            f"<td>{point['anglers']}</td><td>{point['interviews']}</td>"
            f"<td>{point['coho_rate']:.2f}</td></tr>"
        )
    return (
        "<div class='chart-wrap'><table class='sample-table'><thead><tr><th>Area</th>"
        "<th>Date</th><th>Coho</th><th>Chinook</th><th>Anglers</th>"
        "<th>Interviews</th><th>Coho / angler</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def build_html(rows: list[dict], error: str | None = None) -> str:
    points = aggregate(rows)
    summaries = [trend_summary(points, area) for area in AREAS]
    cards = []
    for item in summaries:
        css_class = item["signal"].lower().replace(" ", "-")
        focus = item["area"] == FOCUS_AREA
        if focus:
            css_class += " focus"
        badge = "<span class='home'>HOME</span>" if focus else ""
        period = (
            f"{item['recent_start'][5:]} to {item['recent_end'][5:]}"
            if item["recent_start"] != item["recent_end"]
            else item["recent_end"][5:]
        )
        cards.append(
            f"<article class='signal {css_class}'><div class='area'>{item['area']}{badge}</div>"
            f"<div class='state'>{item['signal']}</div><div class='rate'>{item['rate']:.2f}</div>"
            f"<div class='unit'>coho per angler</div><div class='detail'>"
            f"Recent {item['recent_days']} days ({period})<br>"
            f"{item['fish']} coho · {item['anglers']} anglers · {item['interviews']} interviews"
            f"<div class='comparison'>{_comparison_text(item)}</div></div></article>"
        )
    latest = max((row["date"] for row in rows), default="no data")
    warning = f"<div class='alert'>WDFW refresh failed; showing cached history. {_h(error)}</div>" if error else ""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Puget Sound Salmon Pulse</title><style>{CSS}{CREEL_CSS}</style></head><body>"
        "<header class='creel-hero'><h1>Puget Sound Salmon Pulse</h1>"
        f"<p>Dock-sample catch rates from the ocean entrance toward Admiralty Inlet. Latest WDFW sample: {_h(latest)}.</p></header>"
        f"{render_nav('creel')}<main class='creel-main'>{warning}<section class='signal-grid'>{''.join(cards)}</section>"
        "<section class='trend-panel'><h2>Coho movement</h2><div class='sub'>Daily reported coho per interviewed angler. MA9 (home water) is drawn bold; the other areas are context. Hover a point for fish and sample counts.</div>"
        f"<div class='chart-wrap'>{_render_chart(points)}</div></section>"
        "<section class='trend-panel'><h2>Latest samples by area</h2><div class='sub'>Most recent sampled day available for each tracked marine area.</div>"
        f"{_render_latest_table(points)}</section>"
        "<div class='method'><b>How to read this:</b> MA4 is the earliest ocean-side signal; MA5/MA6 rising can confirm fish moving into the Strait. MA7 and MA8-1/MA8-2 show movement toward Admiralty Inlet, while MA9 is the local don't-miss alert and MA10 carries the watch after MA9 closes. "
        "Rates are fish divided by interviewed anglers, aggregated by catch area, not ramp. HOT NOW marks at least 0.35 coho per angler on a 20-angler sample before enough history exists. SURGE compares the latest 3 sampled days with the prior 7 and requires at least 20 recent and 30 baseline anglers. "
        "Small samples are labeled LOW SAMPLE. WDFW calls these raw data subject to QA/QC; catch rate is not total run size or a forecast.</div></main>"
        f"<footer>Source: <a href='{SOURCE_URL}'>WDFW Puget Sound creel reports</a>. Raw rows are archived on each report build.</footer></body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    output = Path(argv[0]) if argv else ROOT / "reports" / "creel.html"
    rows, error = update_history()
    if not rows:
        print(f"ERROR: no creel data available ({error or 'empty cache'})", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(rows, error), encoding="utf-8")
    print(f"Wrote {output} ({len(rows):,} archived WDFW rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())