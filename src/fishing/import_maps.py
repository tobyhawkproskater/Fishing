"""Import John's Sporting Goods (and similar) fishing-map PDFs as cross references.

John's publishes dozens of free map PDFs under ``/wp-content/uploads/`` — marine
area charts, crab/shrimp holes, river access, boat launches, etc. This module:

1. Drives a headless Chromium (via Playwright) to crawl a curated set of John's
   map index pages and follow their same-site links one level deep, discovering
   every ``*.pdf`` link. A real browser is required because the site sits behind
   Cloudflare's JS challenge, which plain HTTP clients cannot pass.
2. Downloads each PDF into ``maps/`` (repo root; overridable) using the browser's
   authenticated request context.
3. Extracts any selectable text via the existing ``pdftotext`` wrapper. Many
   maps are raster scans with little/no text — that's fine, they're still
   cataloged and cross-referenced by title/filename.
4. Writes ``kb/maps.json``: one entry per map with title, source URL, local
   path, extracted text, and cross-reference tags (waters / spots / places)
   matched against the station registry.

Setup (one time)::

    pip install -e ".[maps]"        # installs playwright
    python -m playwright install chromium

Run::

    python -m fishing.import_maps            # crawl, download, catalog
    python -m fishing.import_maps --no-download   # refresh catalog only
    python -m fishing.import_maps --limit-pages 40

Nothing here is John's-specific except the seed URLs; point ``--seed`` at any
site to reuse the pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import KB_DIR, MAPS_DIR
from .pdf_text import extract_text
from .stations import SPOTS, WATERS

# --- crawl configuration -----------------------------------------------------

BASE = "https://johnssportinggoods.com"
DEFAULT_SEEDS = [
    f"{BASE}/johns-maps/",
    f"{BASE}/popular-boat-launch-maps/",
    f"{BASE}/river-access-park-maps/",
    f"{BASE}/rigging-tackle/",
    f"{BASE}/",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NAV_TIMEOUT_MS = 60_000
CF_WAIT_SECONDS = 25

# WordPress REST media endpoint. Many location maps live only in the media
# library and are not linked from any browsable page, so page-crawling alone
# misses them. The REST API enumerates them directly (and legitimately).
REST_MEDIA = f"{BASE}/wp-json/wp/v2/media"

_WS = re.compile(r"\s+")
_MAPISH = re.compile(r"map|access|launch|crab|shrimp|reef|hol|chart", re.IGNORECASE)
# Pure non-map documents to skip when enumerating the whole media library.
_NONMAP = re.compile(r"newsletter|coupon|redemption", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_NEWSLETTER = re.compile(r"news?letter", re.IGNORECASE)  # matches typo "newletter"
_COUPON = re.compile(r"coupon|redemption", re.IGNORECASE)
_GUIDE = re.compile(r"rig|rigging|set[ _-]?up|bait|formula|leader|knot", re.IGNORECASE)


def classify(filename: str, title: str) -> str:
    """Bucket a PDF as map / guide / newsletter / coupon by name."""
    s = f"{filename} {title}"
    if _NEWSLETTER.search(s):
        return "newsletter"
    if _COUPON.search(s):
        return "coupon"
    if _GUIDE.search(s):
        return "guide"
    return "map"


# --- cross-reference keyword tables ------------------------------------------

def _water_keywords() -> dict[str, list[str]]:
    """water_key -> lowercase phrases that imply it."""
    kw: dict[str, list[str]] = {}
    for w in WATERS.values():
        phrases = {w.key, w.key.replace("_", " "), w.name.lower(), *w.aliases}
        if w.key == "ma9":
            phrases |= {"marine area 9", "ma 9", "area 9"}
        if w.key == "ma10":
            phrases |= {"marine area 10", "ma 10", "area 10"}
        kw[w.key] = sorted(p for p in phrases if len(p) >= 3)
    return kw


def _spot_keywords() -> dict[str, list[str]]:
    """spot_key -> lowercase phrases that imply it (and its water)."""
    kw: dict[str, list[str]] = {}
    for key, spot in SPOTS.items():
        base = spot.name.split("(")[0].strip().lower()
        kw[key] = sorted({base, key.replace("_", " ")})
    return kw


# Notable Puget Sound / North Sound place names John's maps commonly cover.
# Used only as free-text catalog tags ("cross-reference by place name").
PLACE_KEYWORDS: list[str] = [
    "edmonds", "kingston", "mukilteo", "everett", "possession", "useless bay",
    "mutiny bay", "double bluff", "bush point", "point no point", "pilot point",
    "shilshole", "jefferson head", "kayak point", "camano", "hat island",
    "port ludlow", "hood canal", "admiralty", "deception pass", "anacortes",
    "bellingham", "san juan", "humpy hollow", "pile point", "eagle point",
    "redondo", "des moines", "seattle", "tulalip", "skykomish", "snohomish",
    "snoqualmie", "sammamish", "elliott bay", "elliot bay", "sekiu", "neah bay",
    "westport", "richmond beach", "open bay", "tin shed", "apple cove",
    "possession bar",
]


def cross_reference(text: str) -> dict[str, list[str]]:
    """Match combined map text against waters / spots / places."""
    # Normalise hyphen/underscore separators (common in filenames) to spaces so
    # "Useless-Bay" / "richmond_beach" match multi-word place keywords.
    hay = _WS.sub(" ", re.sub(r"[-_]+", " ", text.lower()))
    waters: set[str] = set()
    spots: set[str] = set()
    places: set[str] = set()

    for spot_key, phrases in _spot_keywords().items():
        if any(p in hay for p in phrases):
            spots.add(spot_key)
            waters.add(SPOTS[spot_key].water_key)

    for water_key, phrases in _water_keywords().items():
        if any(p in hay for p in phrases):
            waters.add(water_key)

    for place in PLACE_KEYWORDS:
        if place in hay:
            places.add(place)

    return {
        "waters": sorted(waters),
        "spots": sorted(spots),
        "places": sorted(places),
    }


# --- helpers -----------------------------------------------------------------

def _same_site(url: str) -> bool:
    return urlparse(url).netloc.endswith("johnssportinggoods.com")


def _title_from_url(url: str) -> str:
    stem = Path(urlparse(url).path).stem
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    stem = re.sub(r"\b(\d{4})\b", "", stem).strip()  # drop stray years
    return _WS.sub(" ", stem).title() or "Untitled Map"


def _safe_name(url: str) -> str:
    name = Path(urlparse(url).path).name or "map.pdf"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _wait_for_cloudflare(page) -> bool:
    """Return True once the CF interstitial clears (or was never present)."""
    for _ in range(CF_WAIT_SECONDS):
        try:
            title = page.title().lower()
        except Exception:  # noqa: BLE001 - navigation in flight
            title = ""
        if "just a moment" not in title and "attention required" not in title:
            return True
        time.sleep(1)
    return False


# --- crawling (Playwright) ---------------------------------------------------

def discover_pdfs(page, seeds: list[str], limit_pages: int, verbose: bool = True) -> dict[str, str]:
    """Crawl seeds + one level of same-site links; return {pdf_url: title}."""
    pdfs: dict[str, str] = {}
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(u, 0) for u in seeds]
    pages = 0

    while queue and pages < limit_pages:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            _wait_for_cloudflare(page)
            if resp is not None and resp.status >= 400:
                if verbose:
                    print(f"  skip {url} (HTTP {resp.status})")
                continue
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"  skip {url} ({type(e).__name__})")
            continue

        pages += 1

        # (href, anchor-text) pairs → best titles.
        try:
            anchors = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => [e.href, (e.textContent || '').trim()])",
            )
        except Exception:  # noqa: BLE001
            anchors = []

        for href, label in anchors:
            absu = urljoin(url, str(href).split("#")[0])
            low = absu.lower()
            if low.endswith(".pdf") or ".pdf?" in low:
                title = _WS.sub(" ", str(label)).strip() or _title_from_url(absu)
                pdfs.setdefault(absu, title)
            elif depth == 0 and _same_site(absu) and absu not in seen and _MAPISH.search(low):
                queue.append((absu, depth + 1))

    if verbose:
        print(f"  crawled {pages} page(s); found {len(pdfs)} PDF link(s)")
    return pdfs


def discover_via_rest(request_ctx, verbose: bool = True, maps_only: bool = False) -> dict[str, str]:
    """Enumerate every PDF in the WordPress media library via the REST API.

    Paginated with ``per_page=100``; honours the ``X-WP-TotalPages`` header.
    When ``maps_only`` is set, newsletters/coupons/redemption forms are skipped;
    otherwise the entire library is returned. Returns ``{pdf_url: title}``.
    """
    pdfs: dict[str, str] = {}
    page_num = 1
    while True:
        url = f"{REST_MEDIA}?media_type=application&per_page=100&page={page_num}"
        try:
            resp = request_ctx.get(url, timeout=NAV_TIMEOUT_MS)
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"  REST page {page_num} failed ({type(e).__name__})")
            break
        if resp.status >= 400:
            if verbose and page_num == 1:
                print(f"  REST API unavailable (HTTP {resp.status})")
            break
        try:
            items = resp.json()
        except Exception:  # noqa: BLE001
            break
        if not isinstance(items, list) or not items:
            break
        for it in items:
            src = str(it.get("source_url") or "")
            low = src.lower()
            if not low.endswith(".pdf"):
                continue
            if maps_only and _NONMAP.search(low):
                continue
            title = ""
            rendered = (it.get("title") or {}).get("rendered", "") if isinstance(it.get("title"), dict) else ""
            if rendered:
                title = _WS.sub(" ", _HTML_TAG.sub("", rendered)).strip()
            pdfs.setdefault(src, title or _title_from_url(src))
        try:
            total_pages = int(resp.headers.get("x-wp-totalpages", "1") or 1)
        except ValueError:
            total_pages = page_num
        if page_num >= total_pages:
            break
        page_num += 1
    if verbose:
        kind = "map/guide" if maps_only else "PDF"
        print(f"  REST API: found {len(pdfs)} {kind}(s)")
    return pdfs


# --- download + extract ------------------------------------------------------

def download(request_ctx, url: str, dest_dir: Path) -> Path | None:
    dest = dest_dir / _safe_name(url)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        resp = request_ctx.get(url, timeout=NAV_TIMEOUT_MS)
        if resp.status >= 400:
            print(f"  download failed {url} (HTTP {resp.status})")
            return None
        data = resp.body()
        if not data or not data[:5].startswith(b"%PDF"):
            print(f"  not a PDF, skipping: {url}")
            return None
        dest.write_bytes(data)
        return dest
    except Exception as e:  # noqa: BLE001
        print(f"  download failed {url} ({type(e).__name__})")
        return None


def _extract_text(path: Path) -> str:
    try:
        return extract_text(path, allow_pypdf=True).strip()
    except FileNotFoundError:
        # pdftotext not installed — catalog without full text.
        return ""
    except Exception as e:  # noqa: BLE001 - never let one bad PDF stop the import
        print(f"  text extract failed for {path.name} ({type(e).__name__})")
        return ""


# --- main --------------------------------------------------------------------

def build_catalog(seeds: list[str], dest_dir: Path, do_download: bool, limit_pages: int,
                  maps_only: bool = False) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is required. Install it with:\n"
            '  pip install -e ".[maps]"\n'
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        raise SystemExit(2)

    dest_dir.mkdir(parents=True, exist_ok=True)
    catalog: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()

        print("Discovering map PDFs...")
        found = discover_pdfs(page, seeds, limit_pages=limit_pages)
        for url, title in discover_via_rest(ctx.request, maps_only=maps_only).items():
            found.setdefault(url, title)
        print(f"  total unique PDF(s): {len(found)}")

        for i, (url, title) in enumerate(sorted(found.items(), key=lambda kv: kv[1].lower()), 1):
            local_path: Path | None = None
            if do_download:
                local_path = download(ctx.request, url, dest_dir)
            else:
                candidate = dest_dir / _safe_name(url)
                local_path = candidate if candidate.exists() else None

            text = _extract_text(local_path) if local_path else ""
            fname = _safe_name(url)
            refs = cross_reference(f"{title} {fname} {text}")
            entry = {
                "title": title,
                "filename": fname,
                "kind": classify(fname, title),
                "source_url": url,
                "local_path": str(local_path.relative_to(MAPS_DIR.parent)) if local_path else None,
                "bytes": local_path.stat().st_size if local_path else 0,
                "has_text": bool(text),
                "text": text,
                **refs,
            }
            catalog.append(entry)
            tag = ",".join(refs["waters"]) or "-"
            print(f"  [{i}/{len(found)}] {entry['kind']:10s} {title[:40]:40s} waters={tag}")

        browser.close()

    return catalog


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Import fishing-map PDFs as cross references.")
    ap.add_argument("--seed", action="append", dest="seeds",
                    help="Seed URL to crawl (repeatable). Defaults to John's map pages.")
    ap.add_argument("--dest", type=Path, default=MAPS_DIR,
                    help=f"Download directory (default: {MAPS_DIR}).")
    ap.add_argument("--no-download", action="store_true",
                    help="Rebuild the catalog from already-downloaded PDFs only.")
    ap.add_argument("--limit-pages", type=int, default=30,
                    help="Max HTML pages to crawl (default: 30).")
    ap.add_argument("--maps-only", action="store_true",
                    help="Skip newsletters/coupons; download maps and guides only.")
    args = ap.parse_args(argv)

    seeds = args.seeds or DEFAULT_SEEDS
    catalog = build_catalog(
        seeds=seeds,
        dest_dir=args.dest,
        do_download=not args.no_download,
        limit_pages=args.limit_pages,
        maps_only=args.maps_only,
    )

    KB_DIR.mkdir(parents=True, exist_ok=True)
    out = KB_DIR / "maps.json"
    out.write_text(
        json.dumps({"source": BASE, "maps": catalog}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    downloaded = sum(1 for m in catalog if m["local_path"])
    with_text = sum(1 for m in catalog if m["has_text"])
    tagged = sum(1 for m in catalog if m["waters"] or m["spots"] or m["places"])
    by_kind: dict[str, int] = {}
    for m in catalog:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
    kinds = "  ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
    print(
        f"\nCatalog written to {out}\n"
        f"  total: {len(catalog)}  downloaded: {downloaded}  "
        f"with-text: {with_text}  cross-referenced: {tagged}\n"
        f"  by kind: {kinds}"
    )
    if not catalog:
        print("  (No maps found — the site may be blocking automated requests.)")
        sys.exit(1)


if __name__ == "__main__":
    main()
