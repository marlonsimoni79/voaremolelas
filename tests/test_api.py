"""API tests: all external data sources are mocked."""

from datetime import datetime, timedelta, timezone

import pytest

from app.api import routes
from app.logic import analysis
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
    """Return a current-conditions object with a fresh (now) timestamp."""
    return CurrentConditions(
        wind_avg_kmh=wind_avg,
        wind_max_kmh=20.0,
        wind_direction_deg=wind_dir,
        temperature_c=20.0,
        relative_humidity_pct=50,
        mslp_hpa=1015.0,
        observed_at=datetime.now(timezone.utc),
    )


def make_stale_current(wind_avg=18.0, wind_dir=290):
    """Return a current-conditions object whose METAR is older than the max age."""
    return CurrentConditions(
        wind_avg_kmh=wind_avg,
        wind_max_kmh=20.0,
        wind_direction_deg=wind_dir,
        temperature_c=20.0,
        relative_humidity_pct=50,
        mslp_hpa=1015.0,
        observed_at=datetime.now(timezone.utc) - timedelta(hours=2),
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


class _FakeClient:
    """Client stand-in exposing only the methods the routes call."""

    def __init__(self, current=None, series=None):
        self._current = current
        self._series = series

    def get_current(self):
        return self._current

    def get_series(self, hours=6):
        return self._series


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
        # Freeze the clock at 10:00 UTC = 12:00 Lisbon (daylight) so the
        # daylight criterion is deterministic regardless of test run time.
        monkeypatch.setattr(
            analysis, "_utcnow",
            lambda: datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
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
        assert len(data["assessment"]["criteria"]) == 4

    def test_current_from_allmetsat(self, client, monkeypatch):
        allmetsat = make_current(wind_avg=24.1, wind_dir=280)
        monkeypatch.setattr(routes, "AllmetsatClient", lambda: _FakeClient(allmetsat))
        monkeypatch.setattr(routes, "_fetch_series", lambda: make_series())
        monkeypatch.setattr(routes, "_fetch_rain_now", lambda: make_rain())
        data = client.get("/api/weather").get_json()
        assert data["current"]["wind_avg_kmh"] == 24.1
        assert data["current"]["wind_direction_deg"] == 280

    def test_is_stale(self):
        assert routes._is_stale(make_stale_current()) is True
        assert routes._is_stale(make_current()) is False
        assert routes._is_stale(None) is False

    def test_falls_back_to_wunderground_when_metar_stale(self, client, monkeypatch):
        # Allmetsat returns a stale METAR; Wunderground is the fresh fallback.
        monkeypatch.setattr(routes, "AllmetsatClient",
                             lambda: _FakeClient(make_stale_current(wind_avg=24.1, wind_dir=280)))
        wunderground = make_current(wind_avg=19.5, wind_dir=270)
        monkeypatch.setattr(routes, "WundergroundClient", lambda: _FakeClient(wunderground))
        monkeypatch.setattr(routes, "_fetch_series", lambda: make_series())
        monkeypatch.setattr(routes, "_fetch_rain_now", lambda: make_rain())
        data = client.get("/api/weather").get_json()
        assert data["current"]["wind_avg_kmh"] == 19.5
        assert data["current"]["wind_direction_deg"] == 270
        assert data["assessment"]["errors"] == []

    def test_fresh_metar_stays_with_allmetsat(self, client, monkeypatch):
        # A fresh METAR must NOT trigger the Wunderground fallback.
        monkeypatch.setattr(routes, "AllmetsatClient",
                             lambda: _FakeClient(make_current(wind_avg=24.1, wind_dir=280)))
        monkeypatch.setattr(routes, "WundergroundClient",
                             lambda: _FakeClient(make_current(wind_avg=10.0)))
        monkeypatch.setattr(routes, "_fetch_series", lambda: make_series())
        monkeypatch.setattr(routes, "_fetch_rain_now", lambda: make_rain())
        data = client.get("/api/weather").get_json()
        assert data["current"]["wind_avg_kmh"] == 24.1
        assert data["current"]["wind_direction_deg"] == 280

    def test_falls_back_to_windguru_when_allmetsat_fails(self, client, monkeypatch):
        def boom_allmetsat():
            raise RuntimeError("allmetsat down")

        windguru = make_current(wind_avg=18.0, wind_dir=290)
        monkeypatch.setattr(routes, "AllmetsatClient", boom_allmetsat)
        monkeypatch.setattr(routes, "WindguruClient", lambda: _FakeClient(windguru))
        monkeypatch.setattr(routes, "_fetch_series", lambda: make_series())
        monkeypatch.setattr(routes, "_fetch_rain_now", lambda: make_rain())
        data = client.get("/api/weather").get_json()
        assert data["current"]["wind_avg_kmh"] == 18.0
        assert data["current"]["wind_direction_deg"] == 290
        assert data["assessment"]["errors"] == []

    def test_current_none_when_both_sources_fail(self, client, monkeypatch):
        def boom():
            raise RuntimeError("down")

        monkeypatch.setattr(routes, "AllmetsatClient", boom)
        monkeypatch.setattr(routes, "WindguruClient", boom)
        monkeypatch.setattr(routes, "_fetch_series", lambda: make_series())
        monkeypatch.setattr(routes, "_fetch_rain_now", lambda: make_rain())
        data = client.get("/api/weather").get_json()
        assert data["current"] is None
        assert any("current" in e for e in data["assessment"]["errors"])

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
