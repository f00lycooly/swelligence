"""Unit tests for swell-quality scoring (period + direction) for surf."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from swelligence.providers.base import ForecastPoint
from swelligence.scoring import _swell_factor, score_point
from swelligence.sports import SPORT_PROFILES

SURF = SPORT_PROFILES["surf"]
T = datetime(2026, 6, 23, 9)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


def test_no_swell_data_returns_none():
    assert _swell_factor(pt(), SURF) == (None, "")


def test_sport_without_swell_pref_returns_none():
    flat = SPORT_PROFILES["kitesurf"]  # swell_period_ideal_s is None
    assert _swell_factor(pt(swell_period_s=12), flat) == (None, "")


def test_long_period_beats_short_period():
    f_short, _ = _swell_factor(pt(swell_period_s=5), SURF)
    f_long, note = _swell_factor(pt(swell_period_s=11), SURF)
    assert f_long == 1.0 and "groundswell" in note
    assert f_short < 0.2  # windswell scores poorly


def test_swell_direction_window_gates():
    spot_surf = dataclasses.replace(SURF, swell_dirs=["SW"])
    in_window, _ = _swell_factor(pt(swell_period_s=12, swell_dir_deg=225), spot_surf)
    out_window, note = _swell_factor(pt(swell_period_s=12, swell_dir_deg=45), spot_surf)
    assert in_window == 1.0
    assert out_window == 0.0 and note == "swell out of window"


def test_direction_ignored_when_no_window_or_no_data():
    # No swell_dirs -> direction not gated, period only.
    f, _ = _swell_factor(pt(swell_period_s=11), SURF)
    assert f == 1.0
    # swell_dirs set but provider gave no direction -> period only.
    spot_surf = dataclasses.replace(SURF, swell_dirs=["SW"])
    f2, _ = _swell_factor(pt(swell_period_s=11), spot_surf)
    assert f2 == 1.0


def test_score_point_rewards_clean_groundswell():
    clean = pt(wind_speed_kn=4, wave_height_m=1.4, swell_period_s=13)
    windswell = pt(wind_speed_kn=4, wave_height_m=1.4, swell_period_s=5)
    s_clean = score_point(clean, SURF)
    s_wind = score_point(windswell, SURF)
    assert s_clean.score > s_wind.score
    assert "swell" in s_clean.factors


def test_peak_period_preferred_over_mean_period():
    # Peak period is the better surf-power proxy: a long peak with a short mean
    # (mixed sea) should still read as powerful groundswell.
    f_peak, note = _swell_factor(pt(swell_period_s=6, swell_peak_period_s=13), SURF)
    assert f_peak == 1.0 and "groundswell" in note
    # Mean only, short -> windswell.
    f_mean, _ = _swell_factor(pt(swell_period_s=6), SURF)
    assert f_mean < f_peak


def test_peak_period_alone_is_scorable():
    # Provider may give peak period without mean — still scorable, not missing.
    f, _ = _swell_factor(pt(swell_peak_period_s=12), SURF)
    assert f == 1.0
    res = score_point(pt(wind_speed_kn=4, wave_height_m=1.4, swell_peak_period_s=12), SURF)
    assert "swell" in res.factors
    assert "swell" not in res.completeness  # not flagged missing
