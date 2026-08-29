"""Tests for the Wunderground PWS client and parser."""

from datetime import datetime, timezone

import pytest

from app.data.wunderground import (
    USER_AGENT,
    WundergroundClient,
    WundergroundError,
    _observed_at,
)


def _payload(observations):
    return {"observations": observations}


def _obs():
    return {
        "obsTimeUtc": "2026-08-29T09:00:00Z",
        "epoch": 1756412400,
        "winddirAvg": 270.0,
        "humidityAvg": 55.0,
        "metric": {
            "tempAvg": 21.5,
            "windspeedAvg": 18.4,
            "windspeedHigh": 22.0,
            "windgustHigh": 24.0,
            "pressureMax": 1016.0,
        },
    }


class TestObservedAt:
    def test_prefers_iso_obs_time_utc(self):
        dt = _observed_at({"obsTimeUtc": "2026-08-29T09:00:00Z", "epoch": 1})
        assert dt == datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    def test_falls_back_to_epoch(self):
        dt = _observed_at({"epoch": 1756412400})
        assert dt == datetime.fromtimestamp(1756412400, tz=timezone.utc)

    def test_no_timestamp_returns_none(self):
        assert _observed_at({}) is None


class TestGetCurrent:
    def test_parses_observation_fields(self, monkeypatch):
        class _Resp:
            status_code = 200

            def json(self):
                return _payload([_obs()])

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        c = WundergroundClient().get_current()
        assert c.wind_avg_kmh == pytest.approx(18.4)
        assert c.wind_max_kmh == pytest.approx(24.0)
        assert c.wind_direction_deg == 270
        assert c.temperature_c == pytest.approx(21.5)
        assert c.relative_humidity_pct == pytest.approx(55.0)
        assert c.mslp_hpa == pytest.approx(1016.0)
        assert c.observed_at == datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    def test_uses_last_observation(self, monkeypatch):
        first = dict(_obs(), metric=dict(_obs()["metric"], windspeedAvg=5.0))
        second = dict(_obs(), metric=dict(_obs()["metric"], windspeedAvg=19.0))

        class _Resp:
            status_code = 200

            def json(self):
                return _payload([first, second])

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        c = WundergroundClient().get_current()
        assert c.wind_avg_kmh == pytest.approx(19.0)

    def test_gust_falls_back_to_windspeed_high(self, monkeypatch):
        obs = dict(_obs())
        obs["metric"] = dict(_obs()["metric"], windgustHigh=None)

        class _Resp:
            status_code = 200

            def json(self):
                return _payload([obs])

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        c = WundergroundClient().get_current()
        assert c.wind_max_kmh == pytest.approx(22.0)

    def test_no_observations_raises(self, monkeypatch):
        class _Resp:
            status_code = 200

            def json(self):
                return {"observations": []}

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(WundergroundError):
            WundergroundClient().get_current()

    def test_malformed_observation_raises(self, monkeypatch):
        class _Resp:
            status_code = 200

            def json(self):
                return {"observations": ["not-a-dict"]}

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(WundergroundError):
            WundergroundClient().get_current()

    def test_http_error_raises(self, monkeypatch):
        class _Resp:
            status_code = 500

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(WundergroundError):
            WundergroundClient().get_current()

    def test_non_json_raises(self, monkeypatch):
        class _Resp:
            status_code = 200

            def json(self):
                raise ValueError("bad json")

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(WundergroundError):
            WundergroundClient().get_current()

    def test_request_uses_api_params(self, monkeypatch):
        calls = {}

        class _Resp:
            status_code = 200

            def json(self):
                return _payload([_obs()])

        def fake_get(url, params=None, headers=None, timeout=None):
            calls["url"] = url
            calls["params"] = params
            calls["headers"] = headers
            return _Resp()

        import app.data.wunderground as mod

        monkeypatch.setattr(mod.requests, "get", fake_get)
        WundergroundClient().get_current()
        assert calls["params"]["stationId"] == "IPEROP1"
        assert calls["params"]["units"] == "m"
        assert calls["params"]["apiKey"]
        assert calls["headers"]["User-Agent"] == USER_AGENT
