"""API tests: all external data sources are mocked."""

from datetime import datetime, timezone

import pytest

from app.api import routes
from app.data.ipma import Tephigram
from app.data.openmeteo import RainForecast, RainNow
from app.data.windguru import CurrentConditions, StationSeries
from app.main import create_app


@pytest.fixture()
def client():
    routes.clear_cache()
    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    routes.clear_cache()


def make_current(wind_avg=18.0, wind_dir=290):
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


def make_series():
    return StationSeries(
        points=[
            {
                "time": datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc),
                "wind_avg_kmh": 17.0,
                "wind_max_kmh": 19.0,
                "wind_direction_deg": 285,
                "temperature_c": 19.5,
                "relative_humidity_pct": 55,
                "mslp_hpa": 1014.0,
                "gustiness": 10.0,
            }
        ],
        sunrise="07:01",
        sunset="20:18",
    )


def make_tephigrams():
    return [
        Tephigram(
            station_code="08536",
            station_name="Lisboa",
            kind="observation",
            label="12UTC",
            filename="tef_LISBOA_08536_0_12_00.png",
            url="https://www.ipma.pt/resources.www/transf/sondagem/tef_LISBOA_08536_0_12_00.png",
        )
    ]


def patch_sources(monkeypatch, current=None, series=None, rain_now=None,
                  rain_forecast=None, tephigrams=None):
    monkeypatch.setattr(routes, "_fetch_current", lambda: current)
    monkeypatch.setattr(routes, "_fetch_series", lambda: series)
    monkeypatch.setattr(routes, "_fetch_rain_now", lambda: rain_now)
    monkeypatch.setattr(routes, "_fetch_rain_forecast", lambda: rain_forecast)
    monkeypatch.setattr(routes, "_fetch_tephigrams", lambda: tephigrams)


class TestIndex:
    def test_index_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Voar em Olelas" in resp.data


class TestWeather:
    def test_good_verdict(self, client, monkeypatch):
        patch_sources(
            monkeypatch,
            current=make_current(),
            series=make_series(),
            rain_now=make_rain(),
            tephigrams=make_tephigrams(),
        )
        resp = client.get("/api/weather")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["assessment"]["verdict"] == "GOOD"
        assert data["current"]["wind_avg_kmh"] == 18.0
        assert data["series"]["sunrise"] == "07:01"
        assert data["tephigrams"][0]["kind"] == "observation"
        assert data["rain_now"]["is_raining"] is False
        assert all(c["ok"] for c in data["assessment"]["criteria"])
        assert data["assessment"]["errors"] == []

    def test_bad_verdict_when_windy(self, client, monkeypatch):
        patch_sources(
            monkeypatch,
            current=make_current(wind_avg=30.0),
            series=make_series(),
            rain_now=make_rain(),
        )
        data = client.get("/api/weather").get_json()
        assert data["assessment"]["verdict"] == "BAD"
        wind = next(c for c in data["assessment"]["criteria"] if c["name"] == "wind_speed")
        assert wind["ok"] is False

    def test_bad_verdict_when_raining(self, client, monkeypatch):
        patch_sources(
            monkeypatch,
            current=make_current(),
            rain_now=make_rain(rain_mm=2.5, prob=80),
        )
        data = client.get("/api/weather").get_json()
        assert data["assessment"]["verdict"] == "BAD"
        rain = next(c for c in data["assessment"]["criteria"] if c["name"] == "rain")
        assert rain["ok"] is False

    def test_fetch_failures_reported_as_errors(self, client, monkeypatch):
        def boom():
            raise RuntimeError("source down")

        patch_sources(
            monkeypatch,
            current=make_current(),
            rain_now=make_rain(),
        )
        monkeypatch.setattr(routes, "_fetch_series", boom)
        monkeypatch.setattr(routes, "_fetch_tephigrams", boom)
        data = client.get("/api/weather").get_json()
        assert data["series"] is None
        assert data["tephigrams"] is None
        assert any("series" in e for e in data["assessment"]["errors"])
        assert any("tephigrams" in e for e in data["assessment"]["errors"])

    def test_all_sources_down_still_returns_bad(self, client, monkeypatch):
        patch_sources(monkeypatch)  # everything returns None
        data = client.get("/api/weather").get_json()
        assert data["assessment"]["verdict"] == "BAD"
        assert data["current"] is None
        assert len(data["assessment"]["criteria"]) == 3

    def test_rain_forecast_serialized(self, client, monkeypatch):
        forecast = RainForecast(
            hours=["10:00", "11:00"],
            rain_mm=[0.0, 0.2],
            precipitation_probability_pct=[10, 30],
        )
        patch_sources(
            monkeypatch,
            current=make_current(),
            rain_now=make_rain(),
            rain_forecast=forecast,
        )
        data = client.get("/api/weather").get_json()
        assert data["rain_forecast"]["hours"] == ["10:00", "11:00"]
        assert data["rain_forecast"]["rain_mm"] == [0.0, 0.2]
