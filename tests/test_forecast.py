"""Unit tests for the forecast builders."""

from __future__ import annotations

from datetime import datetime, timedelta

from swelligence.forecast import daily_forecast, hourly_forecast
from swelligence.providers.base import ForecastPoint, SpotForecast
from swelligence.sports import SPORT_PROFILES


def _forecast_two_days() -> SpotForecast:
    """Two days, hourly 00:00–23:00, with sun 06:00–20:00 each day."""
    base = datetime(2026, 6, 27, 0, 0)
    points = []
    for h in range(48):
        t = base + timedelta(hours=h)
        # Wind ramps 8→24kn across each day so scores vary.
        points.append(ForecastPoint(time=t, wind_speed_kn=8 + (h % 24) * 0.7,
                                    wind_gust_kn=14 + (h % 24) * 0.8,
                                    wind_dir_deg=220, wave_height_m=0.8))
    sun = {}
    for d in ("2026-06-27", "2026-06-28"):
        sun[d] = {"sunrise": datetime.fromisoformat(d + "T06:00"),
                  "sunset": datetime.fromisoformat(d + "T20:00")}
    return SpotForecast(provider="t", latitude=50.7, longitude=-1.7,
                        points=points, daily_sun=sun)


def test_hourly_restricted_to_padded_daylight():
    fc = _forecast_two_days()
    prof = SPORT_PROFILES["windsurf"]
    slots = hourly_forecast(fc, prof, "windsurf", pad_h=2)
    hours = {s["datetime"][11:16] for s in slots}
    # window = sunrise-2 (04:00) .. sunset+2 (22:00); 03:00 and 23:00 excluded.
    assert "04:00" in hours
    assert "22:00" in hours
    assert "03:00" not in hours
    assert "23:00" not in hours


def test_hourly_no_sun_data_keeps_all():
    fc = _forecast_two_days()
    fc.daily_sun = {}
    slots = hourly_forecast(fc, SPORT_PROFILES["windsurf"], "windsurf")
    assert len(slots) == 48


def test_daily_one_entry_per_day_with_best():
    fc = _forecast_two_days()
    prof = SPORT_PROFILES["windsurf"]
    days = daily_forecast(fc, prof, "windsurf")
    assert [d["date"] for d in days] == ["2026-06-27", "2026-06-28"]
    # Each daily entry's score is the max of that day's hourly slots.
    hourly = hourly_forecast(fc, prof, "windsurf")
    for d in days:
        same_day = [s["score"] for s in hourly if s["datetime"][:10] == d["date"]]
        assert d["score"] == max(same_day)


def test_kit_fields_present_for_kite_with_rider():
    fc = _forecast_two_days()
    prof = SPORT_PROFILES["kitesurf"]
    slots = hourly_forecast(fc, prof, "kitesurf", weight=80, quiver_sizes=[9, 12])
    assert all("kit_power" in s for s in slots)
    assert slots[0]["kit_ideal_m2"] is not None


def test_no_kit_fields_without_rider():
    fc = _forecast_two_days()
    slots = hourly_forecast(fc, SPORT_PROFILES["kitesurf"], "kitesurf", weight=0)
    assert all("kit_power" not in s for s in slots)


def test_unsized_sport_has_no_kit_even_with_rider():
    fc = _forecast_two_days()
    slots = hourly_forecast(fc, SPORT_PROFILES["surf"], "surf", weight=80,
                            quiver_sizes=[9])
    assert all("kit_power" not in s for s in slots)
