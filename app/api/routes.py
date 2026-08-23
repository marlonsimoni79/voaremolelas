"""Flask API routes for the voaremolelas web app."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from flask import Blueprint, jsonify, render_template

from app.config import config
from app.data.ipma import IpmmaClient
from app.data.openmeteo import OpenMeteoClient
from app.data.windguru import WindguruClient
from app.logic.analysis import analyze

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)

# Simple in-memory cache: key -> (expires_monotonic, value)
_cache: Dict[str, Tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, ttl: int, fetch: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]
    value = fetch()
    with _cache_lock:
        _cache[key] = (now + ttl, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# Data access functions (module-level so tests can monkeypatch them).

def _fetch_current():
    return WindguruClient().get_current()


def _fetch_series():
    return WindguruClient().get_series(hours=6)


def _fetch_rain_now():
    return OpenMeteoClient().get_rain_now()


def _fetch_rain_forecast():
    return OpenMeteoClient().get_rain_forecast()


def _fetch_tephigrams():
    return IpmmaClient().for_station(config.ipma_station)


# Serialization helpers.

def _current_json(current) -> Optional[Dict[str, Any]]:
    if current is None:
        return None
    return {
        "wind_avg_kmh": current.wind_avg_kmh,
        "wind_max_kmh": current.wind_max_kmh,
        "wind_direction_deg": current.wind_direction_deg,
        "temperature_c": current.temperature_c,
        "relative_humidity_pct": current.relative_humidity_pct,
        "mslp_hpa": current.mslp_hpa,
        "observed_at": current.observed_at.isoformat() if current.observed_at else None,
    }


def _series_json(series) -> Optional[Dict[str, Any]]:
    if series is None:
        return None
    return {
        "points": [
            {
                "time": p["time"].isoformat() if p["time"] else None,
                "wind_avg_kmh": p["wind_avg_kmh"],
                "wind_max_kmh": p["wind_max_kmh"],
                "wind_direction_deg": p["wind_direction_deg"],
                "temperature_c": p["temperature_c"],
                "relative_humidity_pct": p["relative_humidity_pct"],
                "mslp_hpa": p["mslp_hpa"],
                "gustiness": p["gustiness"],
            }
            for p in series.points
        ],
        "sunrise": series.sunrise,
        "sunset": series.sunset,
    }


def _tephigrams_json(tephigrams) -> Optional[list]:
    if tephigrams is None:
        return None
    return [
        {
            "station_code": t.station_code,
            "station_name": t.station_name,
            "kind": t.kind,
            "label": t.label,
            "filename": t.filename,
            "url": t.url,
        }
        for t in tephigrams
    ]


# Routes.

@api.route("/")
def index():
    return render_template("index.html")


@api.route("/api/weather")
def weather():
    """Combined payload: current conditions, series, rain, tephigrams, assessment."""
    errors: list = []

    def guarded(key: str, fetch: Callable[[], Any]):
        try:
            return _cached(key, config.cache_ttl, fetch)
        except Exception as exc:  # noqa: BLE001 - report and degrade gracefully
            logger.warning("Fetch %s failed: %s", key, exc)
            errors.append(f"{key}: {exc}")
            return None

    current = guarded("current", _fetch_current)
    series = guarded("series", _fetch_series)
    rain_now = guarded("rain_now", _fetch_rain_now)
    rain_forecast = guarded("rain_forecast", _fetch_rain_forecast)
    tephigrams = guarded("tephigrams", _fetch_tephigrams)

    assessment = analyze(current, rain_now, series, errors)

    return jsonify(
        {
            "station": config.station_name,
            "current": _current_json(current),
            "series": _series_json(series),
            "rain_now": (
                {
                    "rain_mm": rain_now.rain_mm,
                    "precipitation_probability_pct": rain_now.precipitation_probability_pct,
                    "is_raining": rain_now.is_raining,
                    "updated_at": rain_now.updated_at.isoformat() if rain_now.updated_at else None,
                }
                if rain_now
                else None
            ),
            "rain_forecast": (
                {
                    "hours": rain_forecast.hours,
                    "rain_mm": rain_forecast.rain_mm,
                    "precipitation_probability_pct": rain_forecast.precipitation_probability_pct,
                }
                if rain_forecast
                else None
            ),
            "tephigrams": _tephigrams_json(tephigrams),
            "assessment": assessment.to_dict(),
        }
    )
