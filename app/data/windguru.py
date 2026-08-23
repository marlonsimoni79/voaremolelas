"""Fetch live weather for Almargem from a Windguru observation station.

Windguru exposes an internal JSON API (``/int/iapi.php``) that the public map
uses.  The endpoints are unofficial and the markup/parameters can change, so
all parsing is centralized here and treated as fragile.

Verified flow (see /tmp/opencode/test_stations.py):
  1. GET the public map page to populate session cookies.
  2. GET ``q=token_refresh`` and store ``data.token`` in the ``X-WG-Token`` header.
  3. GET station queries with the session + token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from app.config import config

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class WindguruError(RuntimeError):
    """Raised when the Windguru API cannot be reached or returns bad data."""


@dataclass
class CurrentConditions:
    """Current observed conditions at the station."""

    wind_avg_kmh: Optional[float]
    wind_max_kmh: Optional[float]
    wind_direction_deg: Optional[int]
    temperature_c: Optional[float]
    relative_humidity_pct: Optional[float]
    mslp_hpa: Optional[float]
    observed_at: Optional[datetime]


@dataclass
class StationSeries:
    """Time series of observations for the station."""

    points: List[Dict[str, Any]] = field(default_factory=list)
    sunrise: Optional[str] = None
    sunset: Optional[str] = None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    value = _to_float(value)
    if value is None:
        return None
    return int(round(value))


def _unix_to_local(unixtime: Optional[int], tz_offset: int = 3600) -> Optional[datetime]:
    """Convert a unix timestamp to an aware datetime in the station timezone."""
    if not unixtime:
        return None
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime.fromtimestamp(int(unixtime), tz=tz)


class WindguruClient:
    """Minimal client for the Windguru internal station API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_url: Optional[str] = None,
        page_url: Optional[str] = None,
        station_id: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or config.windguru_base).rstrip("/")
        self.api_url = api_url or (self.base_url + "/int/iapi.php")
        self.page_url = page_url or config.windguru_page
        self.station_id = station_id or config.station_id
        self.timeout = timeout or config.request_timeout
        self._session: Optional[requests.Session] = None
        self._token: Optional[str] = None

    # -- session / token ----------------------------------------------------

    def _ensure_session(self) -> requests.Session:
        if self._session is not None:
            return self._session

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9,pt;q=0.8",
                "Referer": self.page_url,
                "Origin": self.base_url,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        # Prime cookies (session/deviceid/langc) from the public page.
        page = session.get(self.page_url, timeout=self.timeout)
        page.raise_for_status()

        # Obtain the API token.
        token_resp = session.get(self.api_url, params={"q": "token_refresh"}, timeout=self.timeout)
        token_resp.raise_for_status()
        token = token_resp.json()["data"]["token"]
        session.headers["X-WG-Token"] = token

        self._session = session
        self._token = token
        return session

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        session = self._ensure_session()
        resp = session.get(self.api_url, params=params, timeout=self.timeout)
        if resp.status_code != 200:
            raise WindguruError(f"Windguru API {params.get('q')} returned HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise WindguruError(f"Windguru API {params.get('q')} returned non-JSON: {exc}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise WindguruError(f"Windguru API {params.get('q')} error: {payload.get('error')}")
        return payload

    # -- data ----------------------------------------------------------------

    def get_current(self) -> CurrentConditions:
        """Fetch the current 10-minute averaged observation."""
        payload = self._get(
            {
                "q": "station_data_current",
                "id_station": self.station_id,
                "avg_min": 10,
                "date_format": "unixtime",
            }
        )
        return CurrentConditions(
            wind_avg_kmh=_to_float(payload.get("wind_avg")),
            wind_max_kmh=_to_float(payload.get("wind_max")),
            wind_direction_deg=_to_int(payload.get("wind_direction")),
            temperature_c=_to_float(payload.get("temperature")),
            relative_humidity_pct=_to_float(payload.get("rh")),
            mslp_hpa=_to_float(payload.get("mslp")),
            observed_at=_unix_to_local(payload.get("unixtime")),
        )

    def get_series(self, hours: int = 6) -> StationSeries:
        """Fetch the trailing ``hours`` of 10-minute observations."""
        now = datetime.now(timezone.utc)
        frm = now - timedelta(hours=hours)
        payload = self._get(
            {
                "q": "station_data",
                "id_station": self.station_id,
                "from": frm.isoformat().replace("+00:00", "Z"),
                "to": now.isoformat().replace("+00:00", "Z"),
                "avg_minutes": 10,
                "graph_info": 1,
            }
        )
        unixtime = payload.get("unixtime") or []
        tz_offset = int(payload.get("tzoffset") or 3600)

        def col(name: str) -> List[Any]:
            value = payload.get(name)
            return value if isinstance(value, list) else []

        wind_avg = col("wind_avg")
        wind_max = col("wind_max")
        wind_dir = col("wind_direction")
        temperature = col("temperature")
        rh = col("rh")
        mslp = col("mslp")
        gustiness = col("gustiness")

        points: List[Dict[str, Any]] = []
        for i, ts in enumerate(unixtime):
            points.append(
                {
                    "time": _unix_to_local(ts, tz_offset),
                    "wind_avg_kmh": _to_float(wind_avg[i]) if i < len(wind_avg) else None,
                    "wind_max_kmh": _to_float(wind_max[i]) if i < len(wind_max) else None,
                    "wind_direction_deg": _to_int(wind_dir[i]) if i < len(wind_dir) else None,
                    "temperature_c": _to_float(temperature[i]) if i < len(temperature) else None,
                    "relative_humidity_pct": _to_float(rh[i]) if i < len(rh) else None,
                    "mslp_hpa": _to_float(mslp[i]) if i < len(mslp) else None,
                    "gustiness": _to_float(gustiness[i]) if i < len(gustiness) else None,
                }
            )

        return StationSeries(points=points, sunrise=payload.get("sunrise"), sunset=payload.get("sunset"))


def fetch_current() -> CurrentConditions:
    """Convenience wrapper used by the API layer."""
    return WindguruClient().get_current()


def fetch_series(hours: int = 6) -> StationSeries:
    """Convenience wrapper used by the API layer."""
    return WindguruClient().get_series(hours=hours)
