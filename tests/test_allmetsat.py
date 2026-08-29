"""Tests for the Allmetsat METAR parser and client."""

import pytest
from datetime import datetime, timezone

from app.data.allmetsat import (
    AllmetsatClient,
    AllmetsatError,
    KNOTS_TO_KMH,
    USER_AGENT,
    parse_metar,
)


class TestParseMetar:
    def test_full_sample(self):
        now = datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)
        c = parse_metar("LPST 271800Z 28013KT 9999 FEW020 20/13 Q1017", now=now)
        assert c.wind_avg_kmh == pytest.approx(13 * KNOTS_TO_KMH, abs=0.05)
        assert c.wind_max_kmh == c.wind_avg_kmh
        assert c.wind_direction_deg == 280
        assert c.temperature_c == 20.0
        assert c.relative_humidity_pct == pytest.approx(64.1, abs=0.5)
        assert c.mslp_hpa == 1017.0
        assert c.observed_at == datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)

    def test_gust(self):
        c = parse_metar("LPST 271800Z 28013G20KT 9999 20/13 Q1017")
        assert c.wind_avg_kmh == pytest.approx(13 * KNOTS_TO_KMH, abs=0.05)
        assert c.wind_max_kmh == pytest.approx(20 * KNOTS_TO_KMH, abs=0.05)

    def test_vrb_direction(self):
        c = parse_metar("LPST 271800Z VRB03KT 9999 20/13 Q1017")
        assert c.wind_direction_deg is None
        assert c.wind_avg_kmh == pytest.approx(3 * KNOTS_TO_KMH, abs=0.05)

    def test_negative_temperatures(self):
        c = parse_metar("LPST 271800Z 28013KT 9999 M05/M08 Q1017")
        assert c.temperature_c == -5.0
        assert c.relative_humidity_pct == pytest.approx(79.5, abs=0.5)

    def test_missing_wind_raises(self):
        with pytest.raises(AllmetsatError):
            parse_metar("LPST 271800Z 9999 20/13 Q1017")

    def test_missing_optional_groups(self):
        c = parse_metar("LPST 271800Z 28013KT 9999")
        assert c.temperature_c is None
        assert c.relative_humidity_pct is None
        assert c.mslp_hpa is None

    def test_whitespace_normalized(self):
        c = parse_metar("LPST  271800Z  28013KT  9999\n20/13 Q1017")
        assert c.wind_direction_deg == 280
        assert c.temperature_c == 20.0


class TestObservedAt:
    def test_same_day(self):
        now = datetime(2026, 8, 27, 19, 0, tzinfo=timezone.utc)
        c = parse_metar("LPST 271800Z 28013KT 9999", now=now)
        assert c.observed_at == datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)

    def test_previous_month_fallback(self):
        now = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
        c = parse_metar("LPST 271800Z 28013KT 9999", now=now)
        assert c.observed_at == datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc)

    def test_impossible_day_returns_none(self):
        now = datetime(2026, 3, 1, 0, 30, tzinfo=timezone.utc)
        c = parse_metar("LPST 311800Z 28013KT 9999", now=now)
        assert c.observed_at is None


class TestClient:
    def test_url_uses_config_icao(self):
        client = AllmetsatClient()
        assert "icao=LPST" in client.url

    def test_url_custom_icao(self):
        client = AllmetsatClient(icao="LPPR")
        assert "icao=LPPR" in client.url

    def test_get_current_parses_page(self, monkeypatch):
        page = (
            "<html><body><div class=\"c1b\">"
            "<p><b>METAR:</b> LPST 271800Z 28013KT 9999 FEW020 20/13 Q1017</p>"
            "</div></body></html>"
        )

        class _Resp:
            text = page

            def raise_for_status(self):
                return None

        calls = {}

        def fake_get(url, headers=None, timeout=None):
            calls["url"] = url
            calls["headers"] = headers
            calls["timeout"] = timeout
            return _Resp()

        import app.data.allmetsat as mod

        monkeypatch.setattr(mod.requests, "get", fake_get)
        c = AllmetsatClient().get_current()
        assert c.wind_direction_deg == 280
        assert calls["headers"]["User-Agent"] == USER_AGENT
        assert calls["timeout"] == 30
        assert "icao=LPST" in calls["url"]

    def test_get_current_no_metar_raises(self, monkeypatch):
        class _Resp:
            text = "<html><body>no report</body></html>"

            def raise_for_status(self):
                return None

        import app.data.allmetsat as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(AllmetsatError):
            AllmetsatClient().get_current()

    def test_get_current_http_error_raises(self, monkeypatch):
        class _HttpError(Exception):
            pass

        class _Resp:
            text = ""

            def raise_for_status(self):
                raise _HttpError("500")

        import app.data.allmetsat as mod

        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _Resp())
        with pytest.raises(_HttpError):
            AllmetsatClient().get_current()
