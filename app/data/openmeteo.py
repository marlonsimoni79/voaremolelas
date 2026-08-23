"""Fetch rain data for Almargem from the public Open-Meteo API.

Open-Meteo is a free public weather API that requires no key.  We use it only
for the rain signal (rain amount + precipitation probability) because neither
Windguru station data nor the IPMA tephigram PNGs expose structured rain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.config import config

logger = logging.getLogger(__name__)


class OpenMeteoError(RuntimeError):
    """Raised when the Open-Meteo API cannot be reached or returns bad data."""


@dataclass
class RainNow:
    """Current rain situation."""

    rain_mm: Optional[float]
    precipitation_probability_pct: Optional[int]
    is_raining: bool
    updated_at: Optional[datetime]


@dataclass
class RainForecast:
    """Hourly rain forecast for the day."""

    hours: List[str]
    rain_mm: List[Optional[float]]
    precipitation_probability_pct: List[Optional[int]]


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


class OpenMeteoClient:
    """Minimal client for the Open-Meteo forecast API."""

    def __init__(
        self,
        url: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.url = url or config.openmeteo_url
        self.lat = lat or config.almargem_lat
        self.lon = lon or config.almargem_lon
        self.timeout = timeout or config.request_timeout

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.get(self.url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            raise OpenMeteoError(f"Open-Meteo returned non-JSON: {exc}") from exc
        if "error" in payload:
            raise OpenMeteoError(f"Open-Meteo error: {payload.get('error')}")
        return payload

    def get_rain_now(self) -> RainNow:
        """Fetch the current rain amount and precipitation probability."""
        payload = self._get(
            {
                "latitude": self.lat,
                "longitude": self.lon,
                "current": "rain,precipitation_probability",
                "timezone": config.timezone,
            }
        )
        current = payload.get("current", {})
        rain = _to_float(current.get("rain"))
        probability = _to_int(current.get("precipitation_probability"))
        updated = None
        if current.get("time"):
            try:
                updated = datetime.fromisoformat(current["time"]).replace(tzinfo=timezone.utc)
            except ValueError:
                updated = None
        return RainNow(
            rain_mm=rain,
            precipitation_probability_pct=probability,
            is_raining=(rain or 0) > 0,
            updated_at=updated,
        )

    def get_rain_forecast(self) -> RainForecast:
        """Fetch today's hourly rain forecast."""
        payload = self._get(
            {
                "latitude": self.lat,
                "longitude": self.lon,
                "hourly": "rain,precipitation_probability",
                "forecast_days": 1,
                "timezone": config.timezone,
            }
        )
        hourly = payload.get("hourly", {})
        hours = hourly.get("time") or []
        rain = hourly.get("rain") or []
        probability = hourly.get("precipitation_probability") or []
        return RainForecast(
            hours=hours,
            rain_mm=[_to_float(v) for v in rain],
            precipitation_probability_pct=[_to_int(v) for v in probability],
        )


def fetch_rain_now() -> RainNow:
    """Convenience wrapper used by the API layer."""
    return OpenMeteoClient().get_rain_now()


def fetch_rain_forecast() -> RainForecast:
    """Convenience wrapper used by the API layer."""
    return OpenMeteoClient().get_rain_forecast()
