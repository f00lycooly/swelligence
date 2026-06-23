"""Unit tests for the deterministic scorer."""

from __future__ import annotations

from datetime import datetime

import pytest

from swelligence.providers.base import ForecastPoint
from swelligence.scoring import (
    SUITABLE_THRESHOLD,
    best_window,
    score_point,
)
from swelligence.sports import SportProfile

T = datetime(2026, 6, 23, 12)


def wind_only(**kw) -> SportProfile:
    """A profile that scores wind alone (all other weights zeroed)."""
    base = dict(
        key="t", label="T", icon="mdi:test", water="sea",
        wind_min_kn=10, wind_ideal_kn=20, wind_max_kn=30, gust_max_kn=40,
        weight_wind=1.0, weight_dir=0.0, weight_wave=0.0,
        weight_gust=0.0, weight_temp=0.0,
    )
    base.update(kw)
    return SportProfile(**base)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


# --- wind window --------------------------------------------------------------

def test_wind_at_ideal_scores_full():
    res = score_point(pt(wind_speed_kn=20), wind_only())
    assert res.score == 100.0
    assert res.verdict == "epic"
    assert res.suitable is True


def test_wind_over_max_hard_fails():
    res = score_point(pt(wind_speed_kn=40), wind_only())
    assert res.score <= 30.0
    assert res.verdict == "poor"
    assert "too strong" in " ".join(res.reasons)


def test_wind_under_min_is_underpowered_not_zero():
    res = score_point(pt(wind_speed_kn=5), wind_only())
    assert 0 < res.score < 55
    assert "under-powered" in " ".join(res.reasons)


def test_band_thresholds():
    # Edge of window tapers to 0.6 -> 60 -> "good".
    res = score_point(pt(wind_speed_kn=10), wind_only())
    assert res.verdict == "good"
    assert res.suitable is (res.score >= SUITABLE_THRESHOLD)


# --- gust (graduated, not a hard fail) ---------------------------------------

def test_gust_over_ceiling_penalises_but_does_not_cap_to_30():
    p = wind_only(weight_gust=1.0, gust_max_kn=20)
    # Wind ideal (full), gust 30 = 50% over ceiling -> gust factor 0.
    res = score_point(pt(wind_speed_kn=20, wind_gust_kn=30), p)
    # (wind 1.0 + gust 0.0) / 2 = 50 -> NOT capped to 30 (gust isn't a hard fail).
    assert res.score == pytest.approx(50.0, abs=0.1)
    assert "gusting" in " ".join(res.reasons)


def test_gust_within_ceiling_no_penalty():
    p = wind_only(weight_gust=1.0, gust_max_kn=40)
    res = score_point(pt(wind_speed_kn=20, wind_gust_kn=35), p)
    assert res.score == 100.0


# --- wave: waves-desired (surf-like) -----------------------------------------

def waves_desired() -> SportProfile:
    return SportProfile(
        key="s", label="S", icon="mdi:s", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=40, gust_max_kn=50,
        wave_min_m=0.6, wave_ideal_m=1.5, wave_max_m=3.5,
        weight_wind=0.0, weight_dir=0.0, weight_wave=1.0,
        weight_gust=0.0, weight_temp=0.0,
    )


def test_small_wave_is_not_epic_for_surf():
    # 0.6m just clears the minimum -> ~0.6 factor, NOT full credit.
    res = score_point(pt(wave_height_m=0.6), waves_desired())
    assert res.score == pytest.approx(60.0, abs=1.0)
    assert res.verdict == "good"


def test_ideal_wave_peaks():
    res = score_point(pt(wave_height_m=1.5), waves_desired())
    assert res.score == 100.0


def test_oversized_wave_hard_fails():
    res = score_point(pt(wave_height_m=5.0), waves_desired())
    assert res.score <= 30.0
    assert "too big" in " ".join(res.reasons)


# --- wave: flat-preferred (comfort plateau) ----------------------------------

def flat_preferred() -> SportProfile:
    return SportProfile(
        key="f", label="F", icon="mdi:f", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=40, gust_max_kn=50,
        wave_max_m=2.0,
        weight_wind=0.0, weight_dir=0.0, weight_wave=1.0,
        weight_gust=0.0, weight_temp=0.0,
    )


def test_small_chop_within_comfort_plateau_full_credit():
    # comfort = 0.4 * 2.0 = 0.8m; 0.6m is comfortable -> full credit.
    res = score_point(pt(wave_height_m=0.6), flat_preferred())
    assert res.score == 100.0


def test_chop_above_comfort_declines():
    res = score_point(pt(wave_height_m=1.4), flat_preferred())
    assert 0 < res.score < 100


def test_chop_at_max_hard_fails():
    res = score_point(pt(wave_height_m=2.0), flat_preferred())
    assert res.score <= 30.0
    assert "too choppy" in " ".join(res.reasons)


# --- direction (offshore matching, wrap-around) ------------------------------

def with_dirs(dirs) -> SportProfile:
    return SportProfile(
        key="d", label="D", icon="mdi:d", water="sea",
        wind_min_kn=0, wind_ideal_kn=10, wind_max_kn=40, gust_max_kn=50,
        wind_dirs=dirs,
        weight_wind=0.0, weight_dir=1.0, weight_wave=0.0,
        weight_gust=0.0, weight_temp=0.0,
    )


def test_direction_match_full():
    res = score_point(pt(wind_speed_kn=10, wind_dir_deg=10), with_dirs(["N"]))
    assert res.score == 100.0


def test_direction_wraparound_350_matches_north():
    res = score_point(pt(wind_speed_kn=10, wind_dir_deg=350), with_dirs(["N"]))
    assert res.score == 100.0


def test_opposite_direction_zero():
    res = score_point(pt(wind_speed_kn=10, wind_dir_deg=180), with_dirs(["N"]))
    assert res.score == 0.0
    assert "wrong wind direction" in " ".join(res.reasons)


def test_no_dirs_means_direction_unscored():
    # With no preferred dirs and only direction weighted, nothing is scorable.
    res = score_point(pt(wind_speed_kn=10, wind_dir_deg=180), with_dirs([]))
    assert res.score == 0.0  # den == 0 -> 0.0


# --- missing fields -----------------------------------------------------------

def test_missing_wind_skips_factor():
    # Wind unknown -> wind factor None -> skipped; wave carries the score.
    p = SportProfile(
        key="m", label="M", icon="mdi:m", water="sea",
        wind_min_kn=10, wind_ideal_kn=20, wind_max_kn=30, gust_max_kn=40,
        wave_max_m=2.0,
        weight_wind=1.0, weight_wave=1.0, weight_dir=0.0,
        weight_gust=0.0, weight_temp=0.0,
    )
    res = score_point(pt(wave_height_m=0.5), p)  # no wind
    assert res.score == 100.0  # only wave scored, comfortable
    assert "wind" not in res.factors


# --- best window --------------------------------------------------------------

def test_best_window_picks_highest_within_horizon():
    pts = [
        pt(wind_speed_kn=5),   # +0 underpowered
        pt(wind_speed_kn=20),  # +1 ideal
        pt(wind_speed_kn=40),  # +2 too strong
    ]
    bw = best_window(pts, wind_only(), horizon=24)
    assert bw is not None
    offset, res = bw
    assert offset == 1
    assert res.score == 100.0


def test_best_window_respects_horizon():
    pts = [pt(wind_speed_kn=5)] * 3 + [pt(wind_speed_kn=20)]
    bw = best_window(pts, wind_only(), horizon=3)  # excludes the ideal at +3
    assert bw[0] != 3
