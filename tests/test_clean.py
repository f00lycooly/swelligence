"""Unit tests for sea-cleanliness scoring (wind-wave dominance + crossed swell).

The 'clean' factor captures sea *organisation* for surf-type sports — distinct
from the 'swell' factor (period/direction quality). A clean groundswell with
little local windsea surfs well; the same swell under a big short-period wind
wave is messy/blown-out, and a strong crossing secondary swell makes a confused,
lumpy sea.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from swelligence.providers.base import ForecastPoint
from swelligence.scoring import _clean_factor, score_point
from swelligence.sports import SPORT_PROFILES

SURF = SPORT_PROFILES["surf"]
T = datetime(2026, 6, 23, 9)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


def test_clean_none_when_no_windwave_data():
    # No wind-wave height -> cleanliness not measurable.
    assert _clean_factor(pt(swell_height_m=1.2), SURF) == (None, "")


def test_clean_none_when_flat():
    # Negligible total sea -> cleanliness irrelevant (flat handled by wave factor).
    assert _clean_factor(pt(swell_height_m=0.02, wind_wave_height_m=0.02), SURF) == (
        None,
        "",
    )


def test_clean_groundswell_scores_high():
    f, note = _clean_factor(pt(swell_height_m=1.4, wind_wave_height_m=0.2), SURF)
    assert f > 0.8 and note == ""


def test_windsea_dominated_scores_low():
    f, note = _clean_factor(pt(swell_height_m=0.3, wind_wave_height_m=1.3), SURF)
    assert f < 0.4 and "messy" in note


def test_crossed_secondary_swell_penalised():
    clean = _clean_factor(pt(swell_height_m=1.4, wind_wave_height_m=0.2), SURF)[0]
    crossed_f, note = _clean_factor(
        pt(swell_height_m=1.4, wind_wave_height_m=0.2, secondary_swell_height_m=1.1),
        SURF,
    )
    assert crossed_f < clean
    assert "confused" in note or "crossed" in note


def test_small_secondary_swell_not_penalised():
    base = _clean_factor(pt(swell_height_m=1.4, wind_wave_height_m=0.2), SURF)[0]
    f = _clean_factor(
        pt(swell_height_m=1.4, wind_wave_height_m=0.2, secondary_swell_height_m=0.2),
        SURF,
    )[0]
    assert f == base


def test_clean_not_applicable_for_non_surf_sport():
    kite = SPORT_PROFILES["kitesurf"]  # weight_clean == 0
    res = score_point(pt(swell_height_m=0.3, wind_wave_height_m=1.3), kite)
    assert "clean" not in res.factors
    assert "clean" not in res.completeness


def test_clean_feeds_surf_score():
    clean = pt(wind_speed_kn=4, wave_height_m=1.4, swell_peak_period_s=12,
               swell_height_m=1.3, wind_wave_height_m=0.2)
    messy = pt(wind_speed_kn=4, wave_height_m=1.4, swell_peak_period_s=12,
               swell_height_m=0.3, wind_wave_height_m=1.3)
    s_clean = score_point(clean, SURF)
    s_messy = score_point(messy, SURF)
    assert "clean" in s_clean.factors
    assert s_clean.score > s_messy.score
