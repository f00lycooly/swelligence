"""Unit tests for the forecast builders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _hourly_from_midnight(offset_seconds: int = 0) -> SpotForecast:
    """A 48h series from local midnight, naive-local times, with utc offset meta."""
    base = datetime(2026, 6, 27, 0, 0)
    pts = [ForecastPoint(time=base + timedelta(hours=h), wind_speed_kn=10) for h in range(48)]
    return SpotForecast(provider="t", latitude=50.7, longitude=-1.7, points=pts,
                        source_meta={"utc_offset_seconds": offset_seconds})


def test_anchor_to_now_trims_leading_past_hours():
    from datetime import timezone

    from swelligence.forecast import anchor_to_now
    fc = _hourly_from_midnight()
    # 14:37 UTC, zero offset -> current hour is 14:00 local.
    now = datetime(2026, 6, 27, 14, 37, tzinfo=timezone.utc)
    out = anchor_to_now(fc, now=now)
    assert out.current().time == datetime(2026, 6, 27, 14, 0)
    assert len(out.points) == 48 - 14
    # source forecast keeps its full series (anchoring returns a copy).
    assert len(fc.points) == 48


def test_anchor_to_now_respects_utc_offset():
    from datetime import timezone

    from swelligence.forecast import anchor_to_now
    # BST: +3600s. 11:30 UTC -> 12:30 local -> current hour 12:00 local.
    fc = _hourly_from_midnight(offset_seconds=3600)
    now = datetime(2026, 6, 27, 11, 30, tzinfo=timezone.utc)
    out = anchor_to_now(fc, now=now)
    assert out.current().time == datetime(2026, 6, 27, 12, 0)


def test_anchor_to_now_noop_when_first_point_is_future():
    from datetime import timezone

    from swelligence.forecast import anchor_to_now
    fc = _hourly_from_midnight()
    now = datetime(2026, 6, 26, 23, 30, tzinfo=timezone.utc)  # before the series starts
    out = anchor_to_now(fc, now=now)
    assert out is fc  # nothing trimmed


def test_anchor_to_now_all_past_keeps_last_point():
    from swelligence.forecast import anchor_to_now
    fc = _hourly_from_midnight()
    now = datetime(2026, 6, 30, 9, 0, tzinfo=timezone.utc)  # after the series ends
    out = anchor_to_now(fc, now=now)
    assert len(out.points) == 1
    assert out.current().time == datetime(2026, 6, 28, 23, 0)


# ---------------------------------------------------------------------------
# daylight_remaining tests
# ---------------------------------------------------------------------------

from swelligence.forecast import daylight_remaining  # noqa: E402


def _sun_forecast():
    # Naive-local points starting "now" (07:00 local); +1h utc offset.
    pts = [ForecastPoint(time=datetime(2026, 6, 26, 7, 0)),
           ForecastPoint(time=datetime(2026, 6, 26, 8, 0))]
    return SpotForecast(
        provider="t",
        latitude=50.7,
        longitude=-1.7,
        points=pts,
        daily_sun={"2026-06-26": {"sunrise": datetime(2026, 6, 26, 5, 0),
                                  "sunset": datetime(2026, 6, 26, 21, 18)}},
        source_meta={"utc_offset_seconds": 3600},
    )


def test_daylight_remaining_counts_minutes_to_sunset():
    fc = _sun_forecast()
    # Real UTC now = 16:06Z -> +1h offset -> 17:06 local; sunset 21:18 -> 4h12m = 252 min.
    now = datetime(2026, 6, 26, 16, 6, tzinfo=timezone.utc)
    out = daylight_remaining(fc, now=now)
    assert out == {"sunrise": "05:00", "sunset": "21:18", "remaining_min": 252}


def test_daylight_remaining_clamps_after_sunset():
    fc = _sun_forecast()
    now = datetime(2026, 6, 26, 22, 0, tzinfo=timezone.utc)  # 23:00 local, past sunset
    assert daylight_remaining(fc, now=now)["remaining_min"] == 0


def test_daylight_remaining_none_without_sun_data():
    fc = SpotForecast(provider="t", latitude=50.7, longitude=-1.7,
                      points=[ForecastPoint(time=datetime(2026, 6, 26, 7, 0))],
                      daily_sun={}, source_meta={})
    assert daylight_remaining(fc, now=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)) is None
