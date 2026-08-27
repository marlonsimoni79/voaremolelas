"""Tests for the Open-Meteo rain client."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.data.openmeteo import OpenMeteoClient, OpenMeteoError


def _payload(rain=0.0, time="2026-08-27T18:00", hourly=None):
    payload = {"current": {"time": time, "rain": rain}}
    if hourly is not None:
        payload["hourly"] = hourly
    return payload


HOURLY = {
    "time": [
        "2026-08-27T17:00",
        "2026-08-27T18:00",
        "2026-08-27T19:00",
    ],
    "precipitation_probability": [5, 12, 40],
}


def _install(monkeypatch, payload=None, json_error=False, http_error=False):
    class _Resp:
        def raise_for_status(self):
            if http_error:
                raise RuntimeError("500 Server Error")

        def json(self):
            if json_error:
                raise ValueError("no json")
            return payload if payload is not None else _payload()

    calls = {}

    def fake_get(url, params=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        calls["timeout"] = timeout
        return _Resp()

    import app.data.openmeteo as mod

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return calls


class TestGetRainNow:
    def test_current_rain_and_local_timezone(self, monkeypatch):
        calls = _install(monkeypatch, _payload(rain=0.0, hourly=HOURLY))
        rain = OpenMeteoClient().get_rain_now()
        assert rain.rain_mm == 0.0
        assert rain.is_raining is False
        assert rain.updated_at == datetime(2026, 8, 27, 18, 0).replace(
            tzinfo=ZoneInfo("Europe/Lisbon")
        )
        assert calls["params"]["current"] == "rain"
        assert calls["params"]["hourly"] == "precipitation_probability"
        assert calls["params"]["timezone"] == "Europe/Lisbon"

    def test_probability_from_matching_hour(self, monkeypatch):
        _install(monkeypatch, _payload(hourly=HOURLY))
        rain = OpenMeteoClient().get_rain_now()
        assert rain.precipitation_probability_pct == 12

    def test_raining_when_rain_positive(self, monkeypatch):
        _install(monkeypatch, _payload(rain=0.5, hourly=HOURLY))
        rain = OpenMeteoClient().get_rain_now()
        assert rain.rain_mm == 0.5
        assert rain.is_raining is True

    def test_missing_hourly_probability(self, monkeypatch):
        _install(monkeypatch, _payload())
        rain = OpenMeteoClient().get_rain_now()
        assert rain.precipitation_probability_pct is None

    def test_invalid_current_time(self, monkeypatch):
        _install(monkeypatch, _payload(time="garbage", hourly=HOURLY))
        rain = OpenMeteoClient().get_rain_now()
        assert rain.updated_at is None
        assert rain.precipitation_probability_pct is None

    def test_probability_rounded_to_int(self, monkeypatch):
        hourly = {
            "time": ["2026-08-27T18:00"],
            "precipitation_probability": [55.4],
        }
        _install(monkeypatch, _payload(hourly=hourly))
        rain = OpenMeteoClient().get_rain_now()
        assert rain.precipitation_probability_pct == 55

    def test_missing_rain_value(self, monkeypatch):
        _install(monkeypatch, {"current": {"time": "2026-08-27T18:00"}})
        rain = OpenMeteoClient().get_rain_now()
        assert rain.rain_mm is None
        assert rain.is_raining is False


class TestGetRainForecast:
    def test_parses_hourly(self, monkeypatch):
        payload = {
            "hourly": {
                "time": ["2026-08-27T18:00", "2026-08-27T19:00", "2026-08-27T20:00"],
                "rain": [0.0, None, 0.2],
                "precipitation_probability": [10, None, 55.4],
            }
        }
        calls = _install(monkeypatch, payload)
        forecast = OpenMeteoClient().get_rain_forecast()
        assert forecast.hours == [
            "2026-08-27T18:00",
            "2026-08-27T19:00",
            "2026-08-27T20:00",
        ]
        assert forecast.rain_mm == [0.0, None, 0.2]
        assert forecast.precipitation_probability_pct == [10, None, 55]
        assert calls["params"]["hourly"] == "rain,precipitation_probability"

    def test_missing_hourly(self, monkeypatch):
        _install(monkeypatch, {})
        forecast = OpenMeteoClient().get_rain_forecast()
        assert forecast.hours == []
        assert forecast.rain_mm == []
        assert forecast.precipitation_probability_pct == []


class TestErrors:
    def test_api_error_payload_raises(self, monkeypatch):
        _install(monkeypatch, {"error": True, "reason": "bad lat"})
        with pytest.raises(OpenMeteoError, match="bad lat"):
            OpenMeteoClient().get_rain_now()

    def test_non_json_raises(self, monkeypatch):
        _install(monkeypatch, json_error=True)
        with pytest.raises(OpenMeteoError, match="non-JSON"):
            OpenMeteoClient().get_rain_forecast()

    def test_http_error_propagates(self, monkeypatch):
        _install(monkeypatch, http_error=True)
        with pytest.raises(RuntimeError, match="500"):
            OpenMeteoClient().get_rain_now()


class TestProbabilityForHour:
    def test_no_matching_hour(self):
        payload = _payload(hourly=HOURLY)
        updated = datetime(2026, 8, 27, 20, 0).replace(tzinfo=ZoneInfo("Europe/Lisbon"))
        assert OpenMeteoClient._probability_for_hour(payload, updated) is None

    def test_none_updated(self):
        payload = _payload(hourly=HOURLY)
        assert OpenMeteoClient._probability_for_hour(payload, None) is None
