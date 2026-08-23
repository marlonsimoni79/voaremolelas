"""Business logic: decide whether conditions are GOOD or BAD for paragliding.

Criteria (from the spec):
  * wind speed between 15 and 22 km/h
  * wind direction between W (270 deg) and NW (315 deg)
  * no rain (not raining now and low rain probability)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import config
from app.data.openmeteo import RainNow
from app.data.windguru import CurrentConditions, StationSeries

COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def direction_to_compass(degrees: Optional[float]) -> Optional[str]:
    """Convert a meteorological from-direction in degrees to a compass label."""
    if degrees is None:
        return None
    index = int((degrees % 360) / 22.5 + 0.5) % 16
    return COMPASS_POINTS[index]


@dataclass
class Criterion:
    """Result of a single flying criterion."""

    name: str
    label: str
    ok: bool
    detail: str


@dataclass
class Assessment:
    """Aggregated flying assessment for the current moment."""

    verdict: str  # "GOOD" or "BAD"
    criteria: List[Criterion] = field(default_factory=list)
    wind_avg_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    wind_compass: Optional[str] = None
    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    mslp_hpa: Optional[float] = None
    rain_mm: Optional[float] = None
    rain_probability_pct: Optional[int] = None
    is_raining: bool = False
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    assessed_at: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "criteria": [
                {"name": c.name, "label": c.label, "ok": c.ok, "detail": c.detail}
                for c in self.criteria
            ],
            "wind_avg_kmh": self.wind_avg_kmh,
            "wind_direction_deg": self.wind_direction_deg,
            "wind_compass": self.wind_compass,
            "temperature_c": self.temperature_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "mslp_hpa": self.mslp_hpa,
            "rain_mm": self.rain_mm,
            "rain_probability_pct": self.rain_probability_pct,
            "is_raining": self.is_raining,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "assessed_at": self.assessed_at.isoformat() if self.assessed_at else None,
            "errors": self.errors,
        }


def _fmt(value: Optional[float], unit: str) -> str:
    if value is None:
        return "no data"
    return f"{value:.1f} {unit}"


def assess_wind_speed(wind_avg_kmh: Optional[float]) -> Criterion:
    label = "Wind speed (15-22 km/h)"
    if wind_avg_kmh is None:
        return Criterion("wind_speed", label, False, "no wind data")
    ok = config.wind_min_kmh <= wind_avg_kmh <= config.wind_max_kmh
    detail = _fmt(wind_avg_kmh, "km/h")
    return Criterion("wind_speed", label, ok, detail)


def assess_wind_direction(wind_direction_deg: Optional[float]) -> Criterion:
    label = "Wind direction (W to NW)"
    if wind_direction_deg is None:
        return Criterion("wind_direction", label, False, "no wind direction data")
    ok = config.wind_dir_min <= wind_direction_deg <= config.wind_dir_max
    detail = f"{wind_direction_deg:.0f} deg ({direction_to_compass(wind_direction_deg)})"
    return Criterion("wind_direction", label, ok, detail)


def assess_rain(rain: Optional[RainNow]) -> Criterion:
    label = "No rain"
    if rain is None:
        return Criterion("rain", label, False, "no rain data")
    if rain.is_raining:
        return Criterion(
            "rain", label, False, f"raining now ({_fmt(rain.rain_mm, 'mm')})"
        )
    if rain.precipitation_probability_pct is not None:
        ok = rain.precipitation_probability_pct < config.rain_probability_threshold
        return Criterion(
            "rain",
            label,
            ok,
            f"rain probability {rain.precipitation_probability_pct}% "
            f"(threshold {config.rain_probability_threshold}%)",
        )
    return Criterion("rain", label, True, "no rain reported")


def analyze(
    current: Optional[CurrentConditions],
    rain: Optional[RainNow],
    series: Optional[StationSeries] = None,
    errors: Optional[List[str]] = None,
) -> Assessment:
    """Combine current conditions and rain into a GOOD/BAD assessment."""
    criteria = []
    wind_avg = current.wind_avg_kmh if current else None
    wind_dir = current.wind_direction_deg if current else None

    criteria.append(assess_wind_speed(wind_avg))
    criteria.append(assess_wind_direction(wind_dir))
    criteria.append(assess_rain(rain))

    verdict = "GOOD" if all(c.ok for c in criteria) else "BAD"

    return Assessment(
        verdict=verdict,
        criteria=criteria,
        wind_avg_kmh=wind_avg,
        wind_direction_deg=wind_dir,
        wind_compass=direction_to_compass(wind_dir),
        temperature_c=current.temperature_c if current else None,
        relative_humidity_pct=current.relative_humidity_pct if current else None,
        mslp_hpa=current.mslp_hpa if current else None,
        rain_mm=rain.rain_mm if rain else None,
        rain_probability_pct=rain.precipitation_probability_pct if rain else None,
        is_raining=rain.is_raining if rain else False,
        sunrise=series.sunrise if series else None,
        sunset=series.sunset if series else None,
        assessed_at=datetime.now().astimezone(),
        errors=errors or [],
    )
