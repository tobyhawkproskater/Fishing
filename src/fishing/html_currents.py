"""Interactive LiveOcean surface-current forecast page."""
from __future__ import annotations

import datetime as dt
import json
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx

from .html_loadout import LOADOUT_CSS, render_nav
from .html_report import CSS
from .weather import noaa_tides


LIVE_OCEAN_VIDEO = "https://s3.kopah.uw.edu/liveocean-web/P1_PS_speed_top.mp4"
LIVE_OCEAN_PAGE = "https://faculty.washington.edu/pmacc/LO/p5_PS_speed_top.html"
PS_CURRENTS_REPO = "https://github.com/salish-sea/ps-currents"
GLENDALE_STATION = "9447814"
PACIFIC = ZoneInfo("America/Los_Angeles")
FRAME_RATE = 8
FORECAST_FRAMES = 73


def load_overlay_data() -> dict:
    """Fetch the model-day anchor and matching Glendale tide predictions."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.head(LIVE_OCEAN_VIDEO)
            response.raise_for_status()
        modified = parsedate_to_datetime(response.headers["last-modified"]).astimezone(dt.UTC)
        forecast_start = modified.replace(hour=0, minute=0, second=0, microsecond=0)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        return {
            "forecast_start": None,
            "tide_events": [],
            "overlay_error": f"LiveOcean model time unavailable: {error}",
        }

    local_start = forecast_start.astimezone(PACIFIC).date()
    tides = noaa_tides(GLENDALE_STATION, date=local_start.isoformat(), days=4)
    tide_events = []
    for event in tides.get("tides", []):
        try:
            event_time = dt.datetime.strptime(event["t"], "%Y-%m-%d %H:%M").replace(
                tzinfo=PACIFIC
            )
            tide_events.append(
                {
                    "time": event_time.isoformat(),
                    "type": event["type"],
                    "height": float(event["v"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    tide_error = tides.get("error")
    return {
        "forecast_start": forecast_start.isoformat(),
        "tide_events": tide_events,
        "overlay_error": f"Glendale tide unavailable: {tide_error}" if tide_error else None,
    }


CURRENT_CSS = """
.currents-hero{padding:24px 32px 20px;background:linear-gradient(135deg,#004578,#0078D4);
               color:#fff}
.currents-hero h1{margin:0 0 6px;font-size:28px;font-weight:600}
.currents-hero p{margin:0;max-width:760px;line-height:1.45;opacity:.94}
.currents-main{max-width:1120px;margin:0 auto;padding:24px 20px 40px}
.focus-bar{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.focus-bar button,.floating-controls button,.floating-controls select{
  appearance:none;border:1px solid #8A8886;border-radius:6px;background:#fff;color:#201F1E;
  padding:8px 12px;font:600 14px/1.2 "Segoe UI",sans-serif;cursor:pointer}
.focus-bar button:hover,.floating-controls button:hover{background:#EFF6FC;border-color:#0078D4}
.focus-bar button.active{background:#0078D4;border-color:#0078D4;color:#fff}
.floating-controls{display:flex;position:fixed;z-index:20;left:50%;bottom:max(12px,env(safe-area-inset-bottom));
                   transform:translateX(-50%);width:min(920px,calc(100vw - 20px));
                   align-items:center;gap:8px;padding:10px 12px;border:1px solid rgba(255,255,255,.35);
                   border-radius:12px;background:rgba(32,31,30,.91);color:#fff;
                   box-shadow:0 5px 24px rgba(0,0,0,.35);backdrop-filter:blur(12px)}
.floating-controls button{border-color:rgba(255,255,255,.55)}
.floating-controls button[aria-pressed=true]{background:#0078D4;border-color:#50E6FF;color:#fff}
.floating-controls label{font-size:12px;font-weight:600}
.floating-controls input[type=range]{flex:1;min-width:100px;accent-color:#50E6FF}
.floating-controls select{padding:7px 8px}
.time-readout{min-width:76px;font-variant-numeric:tabular-nums;font-size:12px;color:#fff}
.dock-time{min-width:150px;font-size:13px;font-weight:700;line-height:1.2}
.detail-control{display:flex;align-items:center;gap:10px;margin:-2px 0 12px;
                font-size:13px;color:#605E5C;font-weight:600}
.detail-control[hidden]{display:none}
.detail-control input{width:min(320px,55vw);accent-color:#0078D4}
.resolution{margin-left:auto;font-weight:400}
.current-stage{position:relative;overflow:hidden;background:#111;border-radius:10px;
               box-shadow:0 3px 12px rgba(0,0,0,.22);transition:aspect-ratio .2s ease}
.current-stage[data-focus=full]{aspect-ratio:13/24}
.current-stage:not([data-focus=full]){aspect-ratio:16/10}
.current-stage video{display:block;width:100%;height:auto}
.current-stage:not([data-focus=full]) video{position:absolute;max-width:none;height:auto}
.forecast-overlay{position:absolute;z-index:4;right:12px;top:12px;max-width:min(390px,calc(100% - 24px));
                  padding:10px 12px;border:1px solid rgba(255,255,255,.45);border-radius:9px;
                  background:rgba(0,69,120,.9);color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.25);
                  backdrop-filter:blur(8px)}
.forecast-overlay[hidden]{display:none}
.forecast-overlay strong,.forecast-overlay span{display:block}
.forecast-overlay strong{font-size:16px;margin-bottom:3px}
.forecast-overlay span{font-size:12px;line-height:1.4}
.place-label{display:none;position:absolute;left:12px;top:12px;padding:6px 10px;border-radius:999px;
             background:rgba(0,69,120,.9);color:#fff;font-size:13px;font-weight:700}
.current-stage:not([data-focus=full]) .place-label{display:block}
.target-marker{display:none;position:absolute;left:50%;top:50%;width:20px;height:20px;
               border:3px solid #fff;border-radius:50%;transform:translate(-50%,-50%);
               box-shadow:0 0 0 2px rgba(0,69,120,.9),0 1px 5px rgba(0,0,0,.8)}
.target-marker::before,.target-marker::after{content:"";position:absolute;background:#fff}
.target-marker::before{width:2px;height:34px;left:6px;top:-10px}
.target-marker::after{height:2px;width:34px;left:-10px;top:6px}
.current-stage:not([data-focus=full]) .target-marker{display:block}
.loading{position:absolute;inset:0;display:grid;place-items:center;color:#fff;background:#111;
         font-size:14px;z-index:2}
.loading[hidden]{display:none}
.source-note,.reading-grid{margin-top:16px}
.source-note{font-size:13px;color:#605E5C;line-height:1.5}
.source-note a{color:#005A9E}
.reading-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.reading-card{background:#fff;border:1px solid #E1DFDD;border-radius:8px;padding:14px}
.reading-card h3{font-size:15px;margin:0 0 6px;color:#004578}
.reading-card p{font-size:13px;line-height:1.45;margin:0;color:#605E5C}
@media(max-width:640px){
  .currents-hero{padding:20px 16px 16px}.currents-hero h1{font-size:22px}
  .currents-main{padding:16px 10px 32px}.reading-grid{grid-template-columns:1fr}
  .focus-bar button{flex:1}.current-stage:not([data-focus=full]){aspect-ratio:4/3}
  .resolution{display:none}
  .floating-controls{flex-wrap:wrap}.floating-controls input[type=range]{order:5;flex-basis:100%}
  .floating-controls label{display:none}.dock-time{margin-left:auto;min-width:125px;font-size:12px}
  .floating-controls select{display:none}
}
"""


CURRENT_SCRIPT = """
(() => {
  const video = document.querySelector("#current-video");
  const config = window.CURRENT_VIEWER_DATA;
  const stage = document.querySelector("#current-stage");
  const loading = document.querySelector("#loading");
  const focusButtons = [...document.querySelectorAll("[data-focus-button]")];
  const placeLabel = document.querySelector("#place-label");
  const playButton = document.querySelector("#play-button");
  const previousButton = document.querySelector("#previous-frame");
  const nextButton = document.querySelector("#next-frame");
  const infoButton = document.querySelector("#info-button");
  const forecastOverlay = document.querySelector("#forecast-overlay");
  const forecastTime = document.querySelector("#forecast-time");
  const frameLabel = document.querySelector("#frame-label");
  const tideStatus = document.querySelector("#tide-status");
  const dockTime = document.querySelector("#dock-time");
  const scrubber = document.querySelector("#scrubber");
  const timeReadout = document.querySelector("#time-readout");
  const speed = document.querySelector("#speed");
  const detailControl = document.querySelector("#detail-control");
  const detailZoom = document.querySelector("#detail-zoom");
  const detailValue = document.querySelector("#detail-value");
  const resolution = document.querySelector("#resolution");
  const focusCenters = {
    useless: {x: .668, y: .446},
    possession: {x: .71, y: .47},
  };
  const forecastStart = config.forecastStart ? new Date(config.forecastStart) : null;
  const tideEvents = config.tideEvents.map(event => ({...event, date: new Date(event.time)}));
  const timeFormat = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
  const eventTimeFormat = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    hour: "numeric",
    minute: "2-digit",
  });

  const frameIndex = () => Math.max(
    0,
    Math.min(config.frameCount - 1, Math.round(video.currentTime * config.frameRate)),
  );

  const tideDescription = modelTime => {
    if (!tideEvents.length) return config.overlayError || "Glendale tide data unavailable";
    const nextIndex = tideEvents.findIndex(event => event.date >= modelTime);
    const next = nextIndex >= 0 ? tideEvents[nextIndex] : null;
    const previous = nextIndex > 0 ? tideEvents[nextIndex - 1] : null;
    if (!next) return "Glendale tide: no later prediction in this forecast window";
    const phase = next.type === "H" ? "rising" : "falling";
    const nextType = next.type === "H" ? "high" : "low";
    const previousText = previous
      ? ` from ${previous.height.toFixed(1)} ft ${previous.type === "H" ? "high" : "low"}`
      : "";
    return `Glendale tide: ${phase}${previousText} · next ${nextType} ` +
      `${next.height.toFixed(1)} ft at ${eventTimeFormat.format(next.date)}`;
  };

  const updateTime = () => {
    const index = frameIndex();
    scrubber.value = index;
    timeReadout.textContent = `${index + 1} / ${config.frameCount}`;
    frameLabel.textContent = `Forecast hour ${index + 1} of ${config.frameCount}`;
    if (forecastStart) {
      const modelTime = new Date(forecastStart.getTime() + index * 60 * 60 * 1000);
      const label = timeFormat.format(modelTime);
      forecastTime.textContent = label;
      dockTime.textContent = label;
      tideStatus.textContent = tideDescription(modelTime);
    } else {
      forecastTime.textContent = "Model time unavailable";
      dockTime.textContent = "Time unavailable";
      tideStatus.textContent = config.overlayError || "Forecast metadata unavailable";
    }
  };

  const positionFocusedView = () => {
    const center = focusCenters[stage.dataset.focus];
    if (!center || !video.videoWidth) {
      video.removeAttribute("style");
      return;
    }
    const zoom = Number(detailZoom.value);
    const width = stage.clientWidth * zoom;
    const height = width * video.videoHeight / video.videoWidth;
    video.style.width = `${width}px`;
    video.style.left = `${stage.clientWidth / 2 - center.x * width}px`;
    video.style.top = `${stage.clientHeight / 2 - center.y * height}px`;
    detailValue.textContent = `${zoom.toFixed(1)}x`;
  };

  focusButtons.forEach(button => button.addEventListener("click", () => {
    const focus = button.dataset.focusButton;
    stage.dataset.focus = focus;
    detailControl.hidden = focus === "full";
    focusButtons.forEach(candidate => {
      const selected = candidate === button;
      candidate.classList.toggle("active", selected);
      candidate.setAttribute("aria-pressed", String(selected));
    });
    placeLabel.textContent = button.dataset.label || "";
    requestAnimationFrame(positionFocusedView);
  }));

  playButton.addEventListener("click", async () => {
    if (video.paused) {
      try {
        await video.play();
      } catch (error) {
        loading.hidden = false;
        loading.textContent = `Unable to play the LiveOcean forecast: ${error.message}`;
      }
    } else {
      video.pause();
    }
  });
  video.addEventListener("play", () => playButton.textContent = "Pause");
  video.addEventListener("pause", () => playButton.textContent = "Play");
  video.addEventListener("loadedmetadata", () => {
    loading.hidden = true;
    resolution.textContent = `Source: ${video.videoWidth} × ${video.videoHeight}`;
    updateTime();
    positionFocusedView();
  });
  video.addEventListener("timeupdate", updateTime);
  video.addEventListener("error", () => {
    loading.hidden = false;
    loading.innerHTML = "The LiveOcean video could not be loaded. " +
      "<a href='https://faculty.washington.edu/pmacc/LO/p5_PS_speed_top.html' " +
      "style='color:#fff'>Open the UW forecast page</a>.";
  });
  const stepFrame = delta => {
    video.pause();
    const target = Math.max(0, Math.min(config.frameCount - 1, frameIndex() + delta));
    video.currentTime = target / config.frameRate + .001;
    updateTime();
  };
  previousButton.addEventListener("click", () => stepFrame(-1));
  nextButton.addEventListener("click", () => stepFrame(1));
  scrubber.addEventListener("input", () => {
    video.pause();
    video.currentTime = Number(scrubber.value) / config.frameRate + .001;
    updateTime();
  });
  speed.addEventListener("change", () => video.playbackRate = Number(speed.value));
  infoButton.addEventListener("click", () => {
    const show = forecastOverlay.hidden;
    forecastOverlay.hidden = !show;
    infoButton.setAttribute("aria-pressed", String(show));
  });
  detailZoom.addEventListener("input", positionFocusedView);
  if ("ResizeObserver" in window) {
    new ResizeObserver(positionFocusedView).observe(stage);
  } else {
    window.addEventListener("resize", positionFocusedView);
  }
})();
"""


def build_html(
    forecast_start: str | None = None,
    tide_events: list[dict] | None = None,
    overlay_error: str | None = None,
) -> str:
    """Return the standalone current-viewer page."""
    generated = dt.datetime.now().astimezone().strftime("%b %d, %Y at %I:%M %p %Z")
    viewer_data = json.dumps(
        {
            "forecastStart": forecast_start,
            "tideEvents": tide_events or [],
            "overlayError": overlay_error,
            "frameRate": FRAME_RATE,
            "frameCount": FORECAST_FRAMES,
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>"
        "<meta name='theme-color' content='#005A9E'>"
        "<title>Useless Bay &amp; Possession Bar Currents</title>"
        f"<style>{CSS}{LOADOUT_CSS}{CURRENT_CSS}</style></head><body>"
        "<header class='currents-hero'><h1>Surface currents</h1>"
        "<p>Explore the University of Washington LiveOcean three-day forecast, with "
        "calibrated views for Useless Bay and Possession Bar.</p></header>"
        f"{render_nav('currents')}"
        "<main class='currents-main'>"
        "<div class='focus-bar' role='group' aria-label='Map focus'>"
        "<button class='active' data-focus-button='full' data-label='' aria-pressed='true'>"
        "Puget Sound</button>"
        "<button data-focus-button='useless' data-label='Useless Bay' aria-pressed='false'>"
        "Useless Bay</button>"
        "<button data-focus-button='possession' data-label='Possession Bar' aria-pressed='false'>"
        "Possession Bar</button></div>"
        "<div class='detail-control' id='detail-control' hidden>"
        "<label for='detail-zoom'>Detail zoom</label>"
        "<input id='detail-zoom' type='range' min='1.4' max='3' value='2' step='.1'>"
        "<output id='detail-value' for='detail-zoom'>2.0x</output>"
        "<span class='resolution' id='resolution'>Source resolution loading...</span></div>"
        "<div class='current-stage' id='current-stage' data-focus='full'>"
        "<div class='loading' id='loading'>Loading the latest LiveOcean forecast...</div>"
        f"<video id='current-video' playsinline loop preload='metadata' "
        f"aria-label='Animated Puget Sound surface-current forecast' src='{LIVE_OCEAN_VIDEO}'>"
        f"<a href='{LIVE_OCEAN_VIDEO}'>Download the LiveOcean current forecast</a></video>"
        "<div class='forecast-overlay' id='forecast-overlay'>"
        "<strong id='forecast-time'>Model time loading...</strong>"
        "<span id='frame-label'>Forecast hour 1 of 73</span>"
        "<span id='tide-status'>Glendale tide loading...</span></div>"
        "<span class='place-label' id='place-label'></span>"
        "<span class='target-marker' aria-hidden='true'></span></div>"
        "<div class='floating-controls' id='floating-controls' aria-label='Animation controls'>"
        "<button id='previous-frame' type='button' title='Previous forecast hour'>−1 hr</button>"
        "<button id='play-button' type='button'>Play</button>"
        "<button id='next-frame' type='button' title='Next forecast hour'>+1 hr</button>"
        "<label for='speed'>Speed</label><select id='speed'>"
        "<option value='.5'>0.5x</option><option value='1' selected>1x</option>"
        "<option value='2'>2x</option><option value='4'>4x</option></select>"
        "<input id='scrubber' type='range' min='0' max='72' value='0' step='1' "
        "aria-label='Forecast hour'>"
        "<span class='time-readout' id='time-readout'>1 / 73</span>"
        "<span class='dock-time' id='dock-time'>Time loading...</span>"
        "<button id='info-button' type='button' aria-pressed='true'>Info</button></div>"
        "<div class='reading-grid'>"
        "<article class='reading-card'><h3>Direction</h3><p>Blue arrows point in the "
        "modeled surface-current direction. Watch how flow wraps around south Whidbey.</p></article>"
        "<article class='reading-card'><h3>Speed</h3><p>Darker orange means faster water. "
        "The legend is in meters per second; 1 m/s is about 1.94 knots.</p></article>"
        "<article class='reading-card'><h3>Timing</h3><p>Use the graph at the bottom in "
        "Puget Sound view to match each frame to Pacific time and the modeled tide cycle.</p></article>"
        "</div>"
        "<p class='source-note'><strong>Image quality:</strong> the UW animation is "
        "650 × 1200 pixels. Lower detail zoom values look sharper and show more context; "
        "higher values enlarge the source pixels but cannot reveal additional model detail.</p>"
        "<p class='source-note'>This is model guidance, not an observation or a substitute "
        "for safe-navigation decisions. Source: University of Washington "
        f"<a href='{LIVE_OCEAN_PAGE}'>LiveOcean</a>. Viewer inspired by the open-source "
        f"<a href='{PS_CURRENTS_REPO}'>ps-currents project</a>. Tide predictions: "
        "<a href='https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id=9447814'>"
        "NOAA Glendale station 9447814</a> (MLLW). "
        f"Page built {generated}.</p></main>"
        f"<script>window.CURRENT_VIEWER_DATA={viewer_data};</script>"
        f"<script>{CURRENT_SCRIPT}</script></body></html>"
    )
