"""Fetch the current observation for Almargem from a Wunderground PWS.

The public PWS dashboard (``https://www.wunderground.com/dashboard/pws/...``)
is rendered client-side, but the underlying ``api.weather.com`` JSON API works
directly and returns fresh observations that are already metric when requested
with ``units=m``.  The endpoints and field names are unofficial, so all parsing
is centralized here and treated as fragile.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from app.config import config
from app.data.windguru import CurrentConditions

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class WundergroundError(RuntimeError):
    """Raised when the Wunderground API cannot be reached or returns bad data."""


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


def _observed_at(obs: Dict[str, Any]) -> Optional[datetime]:
    """Prefer the ISO ``obsTimeUtc``; fall back to the numeric ``epoch``."""
    iso = obs.get("obsTimeUtc")
    if iso:
        try:
            return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    epoch = _to_float(obs.get("epoch"))
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return None


class WundergroundClient:
    """Minimal client for the Wunderground PWS observations JSON API."""

    def __init__(
        self,
        station_id: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.api_base = (api_base or config.wunderground_api).rstrip("/")
        self.api_key = api_key or config.wunderground_api_key
        self.station_id = station_id or config.wunderground_station_id
        self.timeout = timeout or config.request_timeout

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.get(
            f"{self.api_base}{path}",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise WundergroundError(f"Wunderground API {path} returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise WundergroundError(f"Wunderground API {path} returned non-JSON: {exc}") from exc
        return payload

    def get_current(self) -> CurrentConditions:
        """Fetch the latest PWS observation as current conditions."""
        payload = self._get(
            "/v2/pws/observations/all/1day",
            {
                "apiKey": self.api_key,
                "stationId": self.station_id,
                "numericPrecision": "decimal",
                "format": "json",
                "units": "m",
            },
        )
        observations = payload.get("observations")
        if not isinstance(observations, list) or not observations:
            raise WundergroundError(f"Wunderground API returned no observations for {self.station_id}")
        # The most recent observation is the last entry in the list.
        obs = observations[-1]
        if not isinstance(obs, dict):
            raise WundergroundError(f"Wunderground API returned a malformed observation for {self.station_id}")

        metric = obs.get("metric") or {}

        wind_speed = _to_float(metric.get("windspeedAvg"))
        gust = _to_float(metric.get("windgustHigh"))
        if gust is None:
            gust = _to_float(metric.get("windspeedHigh"))

        return CurrentConditions(
            wind_avg_kmh=wind_speed,
            wind_max_kmh=gust,
            wind_direction_deg=_to_int(obs.get("winddirAvg")),
            temperature_c=_to_float(metric.get("tempAvg")),
            relative_humidity_pct=_to_float(obs.get("humidityAvg")),
            mslp_hpa=_to_float(metric.get("pressureMax")),
            observed_at=_observed_at(obs),
            source="wunderground",
        )


def fetch_current() -> CurrentConditions:
    """Convenience wrapper used by the API layer."""
    return WundergroundClient().get_current()
