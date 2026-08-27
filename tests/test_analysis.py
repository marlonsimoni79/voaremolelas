"""Unit tests for the analysis logic."""
from datetime import datetime, timezone

import pytest

from app.logic.analysis import (
    Assessment,
    analyze,
    assess_rain,
    assess_wind_direction,
    assess_wind_speed,
    direction_to_compass,
)
from app.data.openmeteo import RainNow


def make_current(wind_avg=18.0, wind_dir=290.0):
    from app.data.windguru import CurrentConditions

    return CurrentConditions(
        wind_avg_kmh=wind_avg,
        wind_max_kmh=20.0,
        wind_direction_deg=wind_dir,
        temperature_c=20.0,
        relative_humidity_pct=50,
        mslp_hpa=1015.0,
        observed_at=datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
    )


def make_rain(rain_mm=0.0, prob=10):
    return RainNow(
        rain_mm=rain_mm,
        precipitation_probability_pct=prob,
        is_raining=rain_mm > 0,
        updated_at=datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
    )


class TestCompass:
    def test_cardinal(self):
        assert direction_to_compass(0) == "N"
        assert direction_to_compass(90) == "E"
        assert direction_to_compass(180) == "S"
        assert direction_to_compass(270) == "W"

    def test_intercardinal(self):
        assert direction_to_compass(315) == "NW"
        assert direction_to_compass(45) == "NE"

    def test_wraparound(self):
        assert direction_to_compass(340) == "NNW"
        assert direction_to_compass(360) == "N"


class TestWindSpeed:
    def test_in_range(self):
        c = assess_wind_speed(18.0)
        assert c.ok is True

    def test_below(self):
        c = assess_wind_speed(10.0)
        assert c.ok is False

    def test_above(self):
        c = assess_wind_speed(25.0)
        assert c.ok is False

    def test_boundaries(self):
        assert assess_wind_speed(15.0).ok is True
        assert assess_wind_speed(22.0).ok is True

    def test_missing(self):
        c = assess_wind_speed(None)
        assert c.ok is False


class TestWindDirection:
    def test_w_to_nw(self):
        assert assess_wind_direction(271).ok is True
        assert assess_wind_direction(290).ok is True
        assert assess_wind_direction(315).ok is True

    def test_w_exclusive(self):
        assert assess_wind_direction(270).ok is False

    def test_nw_inclusive(self):
        assert assess_wind_direction(337.5).ok is True

    def test_outside(self):
        assert assess_wind_direction(269).ok is False
        assert assess_wind_direction(338).ok is False
        assert assess_wind_direction(90).ok is False
        assert assess_wind_direction(0).ok is False

    def test_missing(self):
        assert assess_wind_direction(None).ok is False


class TestRain:
    def test_dry(self):
        c = assess_rain(make_rain())
        assert c.ok is True

    def test_raining(self):
        c = assess_rain(make_rain(rain_mm=2.0, prob=80))
        assert c.ok is False

    def test_high_probability(self):
        c = assess_rain(make_rain(prob=60))
        assert c.ok is False

    def test_missing(self):
        c = assess_rain(None)
        assert c.ok is False


class TestAnalyze:
    def test_good(self):
        a = analyze(make_current(), make_rain())
        assert a.verdict == "GOOD"
        assert all(c.ok for c in a.criteria)

    def test_bad_wind(self):
        a = analyze(make_current(wind_avg=30.0), make_rain())
        assert a.verdict == "BAD"

    def test_bad_rain(self):
        a = analyze(make_current(), make_rain(rain_mm=1.0, prob=90))
        assert a.verdict == "BAD"

    def test_no_data_is_bad(self):
        a = analyze(None, None)
        assert a.verdict == "BAD"
        assert all(not c.ok for c in a.criteria)

    def test_errors_carried(self):
        a = analyze(make_current(), make_rain(), errors=["windguru: timeout"])
        assert a.errors == ["windguru: timeout"]
