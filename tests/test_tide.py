"""Unit tests for tide-aware scoring (pure)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from swelligence.providers.base import ForecastPoint, TideEvent
from swelligence.scoring import score_point
from swelligence.sports import SPORT_PROFILES
from swelligence.tide import (
    TIDE_FLOOR,
    TIDE_STATE_ANY,
    tide_factor,
    to_utc_naive,
)

# high water at 12:00 UTC, low at 18:00 UTC.
EVENTS = [
    TideEvent(time=datetime(2026, 6, 23, 12), kind="high", height_m=1.4),
    TideEvent(time=datetime(2026, 6, 23, 18), kind="low", height_m=-0.2),
]


def test_to_utc_naive_from_aware():
    aware = datetime(2026, 6, 23, 12, tzinfo=timezone.utc)
    assert to_utc_naive(aware) == datetime(2026, 6, 23, 12)
    plus1 = datetime(2026, 6, 23, 12, tzinfo=timezone(timedelta(hours=1)))
    assert to_utc_naive(plus1) == datetime(2026, 6, 23, 11)


def test_to_utc_naive_from_naive_local():
    # naive local (UTC+1) -> shift back to UTC.
    local = datetime(2026, 6, 23, 12)
    assert to_utc_naive(local, local_offset_seconds=3600) == datetime(2026, 6, 23, 11)


def test_high_pref_peaks_at_high_water():
    f, note = tide_factor(EVENTS, datetime(2026, 6, 23, 12), "high", 2.0)
    assert f == 1.0 and "high" in note


def test_high_pref_decays_within_window():
    # 2h after high, window 2h -> 1 - 0.3*1 = 0.7.
    f, _ = tide_factor(EVENTS, datetime(2026, 6, 23, 14), "high", 2.0)
    assert f == pytest.approx(0.7, abs=0.001)


def test_far_from_state_hits_floor():
    f, _ = tide_factor(EVENTS, datetime(2026, 6, 23, 18), "high", 2.0)
    assert f == TIDE_FLOOR


def test_low_pref_peaks_at_low_water():
    f, _ = tide_factor(EVENTS, datetime(2026, 6, 23, 18), "low", 2.0)
    assert f == 1.0


def test_mid_pref_peaks_between_extremes():
    # max flow ~ 15:00 (midway high 12:00 -> low 18:00).
    f, _ = tide_factor(EVENTS, datetime(2026, 6, 23, 15), "mid", 2.0)
    assert f == 1.0


def test_any_and_no_events_return_none():
    assert tide_factor(EVENTS, datetime(2026, 6, 23, 12), TIDE_STATE_ANY, 2.0) == (None, "")
    assert tide_factor([], datetime(2026, 6, 23, 12), "high", 2.0) == (None, "")


def test_score_point_folds_tide_factor():
    profile = SPORT_PROFILES["kitesurf"]
    base = ForecastPoint(time=datetime(2026, 6, 23, 12), wind_speed_kn=18, wind_gust_kn=22)
    gated = ForecastPoint(
        time=datetime(2026, 6, 23, 12), wind_speed_kn=18, wind_gust_kn=22, tide_factor=0.5
    )
    s_base = score_point(base, profile)
    s_gated = score_point(gated, profile)
    assert s_gated.score == pytest.approx(s_base.score * 0.5, abs=0.1)
    assert s_gated.factors["tide"] == 50.0


# --- tide_state (ready-to-render trend + next high/low) ---------------------

from datetime import datetime as _dt, timedelta as _td  # noqa: E402

from swelligence.providers.base import ForecastPoint, SpotForecast, TideEvent  # noqa: E402
from swelligence.tide import tide_state  # noqa: E402


def _fc_from_levels(levels):
    base = _dt(2026, 6, 25, 12, 0)
    pts = [ForecastPoint(time=base + _td(hours=i), sea_level_m=l) for i, l in enumerate(levels)]
    return SpotForecast(provider="t", latitude=50.7, longitude=-1.7, points=pts)


def test_tide_state_modelled_rising_finds_next_high():
    # Rising into a peak at index 3, then falling.
    fc = _fc_from_levels([-0.6, -0.4, -0.1, 0.2, 0.1, -0.2, -0.5])
    st = tide_state(fc)
    assert st["source"] == "modelled"
    assert st["state"] == "rising"
    assert st["next"]["type"] == "high"
    assert st["next"]["in_h"] == 3
    assert st["min"] == -0.6 and st["max"] == 0.2


def test_tide_state_modelled_falling_finds_next_low():
    fc = _fc_from_levels([0.3, 0.1, -0.2, -0.5, -0.3, 0.0])
    st = tide_state(fc)
    assert st["state"] == "falling"
    assert st["next"]["type"] == "low"
    assert st["next"]["in_h"] == 3


def test_tide_state_prefers_overlay_events():
    fc = _fc_from_levels([-0.6, -0.4, -0.1, 0.2])
    base = _dt(2026, 6, 25, 12, 0)
    fc.tide_events = [TideEvent(time=base + _td(hours=2), kind="high", height_m=1.8)]
    st = tide_state(fc)
    assert st["source"] == "overlay"
    assert st["state"] == "rising"
    assert st["next"] == {"type": "high", "time": "14:00", "in_h": 2, "level": 1.8}
