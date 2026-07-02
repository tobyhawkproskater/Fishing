"""Sun-event calculator: sunrise/sunset + nautical twilight per day.

Pure-Python implementation of the standard "sunrise equation" (NOAA/USNO
low-precision algorithm) — accurate to about a minute in the temperate
latitudes we care about. No third-party dependency required.

`sun_times(date, lat, lon)` returns a dict of naive local-Pacific
datetimes for four events on `date`:

    nautical_dawn  — sun 12° below horizon (morning)  = "first light"
    sunrise        — sun -0.833° (refraction + solar radius)
    sunset         — sun -0.833° (evening)
    nautical_dusk  — sun 12° below horizon (evening)  = "last light"

A key returns None if the sun never reaches that altitude on that date
(polar day/night — not relevant for MA9 but returned safely).
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    _PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    _PT = dt.timezone(dt.timedelta(hours=-8))

# J2000 epoch: 2000-01-01 12:00 UT
_J2000 = dt.datetime(2000, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)


def _julian_day(date: dt.date) -> float:
    """Julian day at 0h UT of the given calendar date."""
    y, m, d = date.year, date.month, date.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def _solar_events(date: dt.date, lat: float, lon: float,
                  altitude_deg: float) -> tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """Return (rising_utc, setting_utc) for the sun crossing `altitude_deg`.

    Altitudes: -0.833° for sunrise/sunset, -12° for nautical twilight.
    Returns (None, None) if the sun never crosses that altitude.
    """
    jd = _julian_day(date) + 0.5  # noon of `date` in UT terms
    n = jd - 2451545.0 + 0.0008
    j_star = n - lon / 360.0
    m = (357.5291 + 0.98560028 * j_star) % 360.0
    mr = math.radians(m)
    c = 1.9148 * math.sin(mr) + 0.0200 * math.sin(2 * mr) + 0.0003 * math.sin(3 * mr)
    lam = (m + c + 180.0 + 102.9372) % 360.0
    lr = math.radians(lam)
    j_transit = 2451545.0 + j_star + 0.0053 * math.sin(mr) - 0.0069 * math.sin(2 * lr)
    sin_decl = math.sin(lr) * math.sin(math.radians(23.44))
    decl = math.asin(sin_decl)
    lat_r = math.radians(lat)
    cos_h = (math.sin(math.radians(altitude_deg)) - math.sin(lat_r) * sin_decl) \
        / (math.cos(lat_r) * math.cos(decl))
    if cos_h > 1 or cos_h < -1:
        return (None, None)
    h_deg = math.degrees(math.acos(cos_h))
    j_set = j_transit + h_deg / 360.0
    j_rise = j_transit - h_deg / 360.0

    def _to_utc(j: float) -> dt.datetime:
        return _J2000 + dt.timedelta(days=j - 2451545.0)

    return (_to_utc(j_rise), _to_utc(j_set))


def _to_local(u: Optional[dt.datetime]) -> Optional[dt.datetime]:
    if u is None:
        return None
    return u.astimezone(_PT).replace(tzinfo=None)


def sun_times(date: dt.date, lat: float, lon: float) -> dict:
    """Return naive local-Pacific datetimes for the four sun events on `date`."""
    naut_rise, naut_set = _solar_events(date, lat, lon, -12.0)
    day_rise, day_set = _solar_events(date, lat, lon, -0.833)
    return {
        "nautical_dawn": _to_local(naut_rise),
        "sunrise":       _to_local(day_rise),
        "sunset":        _to_local(day_set),
        "nautical_dusk": _to_local(naut_set),
    }


def hour_of_day(t: Optional[dt.datetime]) -> Optional[float]:
    """Convert a datetime to its hour-of-day as a float, or None."""
    if t is None:
        return None
    return t.hour + t.minute / 60.0 + t.second / 3600.0


def fmt_clock(t: Optional[dt.datetime]) -> str:
    """Short 12-hour clock formatter, e.g. '5:15a', '9:07p'."""
    if t is None:
        return ""
    h = t.hour % 12 or 12
    suf = "a" if t.hour < 12 else "p"
    return f"{h}:{t.minute:02d}{suf}"
