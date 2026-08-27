"""Fetch the current METAR observation for Almargem (Sintra) from Allmetsat.

Allmetsat publishes the METAR/TAF of each ICAO station on a plain HTML page.
The page only answers to a browser-like ``User-Agent`` (anything else gets a
404) and the markup is third-party, so all parsing is centralized here and
treated as fragile.

Only the METAR report is consumed: wind (sustained/gust), temperature/dew
point, QNH and the observation time.  The TAF is ignored.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from app.config import config
from app.data.windguru import CurrentConditions

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

KNOTS_TO_KMH = 1.852

METAR_RE = re.compile(r"<b>\s*METAR\s*:</b>\s*(?P<metar>[^<]+)</p>", re.IGNORECASE)
WIND_RE = re.compile(r"\b(?:(?P<dir>\d{3}|VRB)(?P<spd>\d{2,3})(G(?P<gust>\d{2,3}))?KT)\b")
TEMP_RE = re.compile(r"\b(?P<temp>M?\d{2})/(?P<dew>M?\d{2})\b")
QNH_RE = re.compile(r"\bQ(?P<qnh>\d{4})\b")
OBS_TIME_RE = re.compile(r"^\s*[A-Z]{4}\s+(?P<day>\d{2})(?P<hour>\d{2})(?P<minute>\d{2})Z\b")


class AllmetsatError(RuntimeError):
    """Raised when the Allmetsat page cannot be reached or parsed."""


def _signed(value: str) -> int:
    """METAR temperatures use ``M`` for negative values (e.g. ``M05`` = -5)."""
    if value.startswith("M"):
        return -int(value[1:])
    return int(value)


def _relative_humidity(temperature_c: float, dew_point_c: float) -> float:
    """Approximate relative humidity from temperature and dew point (Magnus)."""
    if temperature_c < dew_point_c:
        return 100.0
    a = 17.62
    b = 243.12
    gamma_d = (a * dew_point_c) / (b + dew_point_c)
    gamma_t = (a * temperature_c) / (b + temperature_c)
    return round(100.0 * math.exp(gamma_d - gamma_t), 1)


def _observed_at(metar: str, now: datetime) -> Optional[datetime]:
    """Parse the ``DDHHMMZ`` observation time into an aware UTC datetime."""
    match = OBS_TIME_RE.match(metar)
    if not match:
        return None
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    utc_now = now.astimezone(timezone.utc)
    try:
        observed = utc_now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if observed > utc_now:
        # METARs are at most a few hours old; a future time means the day
        # belongs to the previous month.
        first_of_month = observed.replace(day=1)
        previous = first_of_month - timedelta(days=1)
        try:
            observed = previous.replace(
                day=day, hour=hour, minute=minute, second=0, microsecond=0
            )
        except ValueError:
            # Day does not exist in the previous month (e.g. Feb 31).
            return None
    return observed


def parse_metar(metar: str, now: Optional[datetime] = None) -> CurrentConditions:
    """Parse a METAR string into :class:`CurrentConditions`.

    Raises :class:`AllmetsatError` when the wind group is missing.
    """
    now = now or datetime.now(timezone.utc)
    metar = " ".join(metar.split())

    wind = WIND_RE.search(metar)
    if not wind:
        raise AllmetsatError(f"no wind group in METAR: {metar!r}")

    direction = None if wind.group("dir") == "VRB" else int(wind.group("dir"))
    sustained_kt = int(wind.group("spd"))
    gust_kt = int(wind.group("gust")) if wind.group("gust") else sustained_kt

    temperature_c = dew_point_c = None
    temp = TEMP_RE.search(metar)
    if temp:
        temperature_c = float(_signed(temp.group("temp")))
        dew_point_c = float(_signed(temp.group("dew")))
    humidity = (
        _relative_humidity(temperature_c, dew_point_c)
        if temperature_c is not None and dew_point_c is not None
        else None
    )

    mslp_hpa = None
    qnh = QNH_RE.search(metar)
    if qnh:
        mslp_hpa = float(int(qnh.group("qnh")))

    return CurrentConditions(
        wind_avg_kmh=round(sustained_kt * KNOTS_TO_KMH, 1),
        wind_max_kmh=round(gust_kt * KNOTS_TO_KMH, 1),
        wind_direction_deg=direction,
        temperature_c=temperature_c,
        relative_humidity_pct=humidity,
        mslp_hpa=mslp_hpa,
        observed_at=_observed_at(metar, now),
    )


class AllmetsatClient:
    """Scraper for the Allmetsat METAR/TAF page of a single ICAO station."""

    def __init__(self, icao: Optional[str] = None, timeout: Optional[int] = None) -> None:
        self.url = config.allmetsat_url.format(icao=icao or config.allmetsat_icao)
        self.timeout = timeout or config.request_timeout

    def get_current(self) -> CurrentConditions:
        """Fetch the page and return the latest METAR as current conditions."""
        response = requests.get(
            self.url,
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
        )
        response.raise_for_status()
        match = METAR_RE.search(response.text)
        if not match:
            raise AllmetsatError("METAR report not found in Allmetsat page")
        return parse_metar(match.group("metar"))
