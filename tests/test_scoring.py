"""Unit tests for the deterministic scorer."""

from __future__ import annotations

from datetime import datetime

import pytest

from swelligence.providers.base import ForecastPoint
from swelligence.scoring import (
    INCOMPLETE_CAP,
    MISSING_DATA,
    NOT_CONFIGURED,
    SUITABLE_THRESHOLD,
    ScoreResult,
    best_window,
    blend_kit,
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
    # No essential_factors on a synthetic profile -> missing wind is non-essential
    # -> no completeness cap, but the gap is still recorded.
    assert res.completeness.get("wind") == MISSING_DATA


# --- factor completeness semantics (slh.1) -----------------------------------

def _essential(missing_field) -> SportProfile:
    """A waves-desired profile that treats wave + swell as essential."""
    return SportProfile(
        key="e", label="E", icon="mdi:e", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=40, gust_max_kn=50,
        wave_min_m=0.6, wave_ideal_m=1.5, wave_max_m=3.5,
        swell_period_ideal_s=11,
        weight_wind=0.6, weight_dir=0.0, weight_wave=1.0, weight_swell=0.7,
        weight_gust=0.0, weight_temp=0.0,
        essential_factors=frozenset({"wave", "swell"}),
    )


def test_essential_missing_caps_score():
    # Great wave, but the sport treats swell as essential and there's no swell
    # data -> capped, not averaged away to a flattering number.
    res = score_point(pt(wave_height_m=1.5), _essential("swell"))
    assert res.score <= INCOMPLETE_CAP
    assert res.completeness.get("swell") == MISSING_DATA
    assert "swell data unavailable" in " ".join(res.reasons)


def test_essential_present_no_cap():
    # Same profile, full data -> no completeness cap, scores high.
    res = score_point(
        pt(wave_height_m=1.5, swell_period_s=12), _essential("swell")
    )
    assert res.score > INCOMPLETE_CAP
    assert "swell" not in res.completeness


def test_non_essential_missing_is_not_capped():
    # A profile where swell is scored but NOT essential: missing swell drops out
    # of the mean (recorded) but does not cap an otherwise-good wave score.
    p = SportProfile(
        key="n", label="N", icon="mdi:n", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=40, gust_max_kn=50,
        wave_min_m=0.6, wave_ideal_m=1.5, wave_max_m=3.5,
        swell_period_ideal_s=11,
        weight_wind=0.0, weight_dir=0.0, weight_wave=1.0, weight_swell=0.7,
        weight_gust=0.0, weight_temp=0.0,
    )  # essential_factors defaults to empty
    res = score_point(pt(wave_height_m=1.5), p)  # no swell
    assert res.score == 100.0
    assert res.completeness.get("swell") == MISSING_DATA


def test_not_configured_direction_nudges_without_changing_score():
    # weight_dir > 0 and a wind bearing present, but no offshore window set:
    # direction is "not configured" -> excluded from the mean (score unchanged
    # vs wind alone), surfaced as a nudge, never as a condition penalty.
    p = SportProfile(
        key="c", label="C", icon="mdi:c", water="sea",
        wind_min_kn=10, wind_ideal_kn=20, wind_max_kn=30, gust_max_kn=40,
        wind_dirs=[],
        weight_wind=1.0, weight_dir=0.8, weight_wave=0.0,
        weight_gust=0.0, weight_temp=0.0,
    )
    res = score_point(pt(wind_speed_kn=20, wind_dir_deg=180), p)
    assert res.score == 100.0  # wind ideal; direction not counted, not penalised
    assert res.completeness.get("direction") == NOT_CONFIGURED
    assert any("offshore" in n for n in res.nudges)
    assert "direction" not in res.factors


def test_not_applicable_factor_is_silent():
    # Surf-like waves-desired profile doesn't score temp -> temp is neither in
    # completeness (not a gap) nor a nudge, even with no water_temp data.
    res = score_point(pt(wave_height_m=1.5, swell_period_s=12), _essential("x"))
    assert "temp" not in res.completeness
    assert res.nudges == [] or all("temp" not in n for n in res.nudges)


def test_zero_weight_factor_never_flags_completeness():
    # A factor the sport zero-weights must not produce a not_configured nudge
    # nor a missing_data record, even with empty dirs and no bearing.
    res = score_point(pt(wind_speed_kn=20), wind_only())  # weight_dir=0, dirs=[]
    assert "direction" not in res.completeness
    assert res.nudges == []


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


# --- kit blend ----------------------------------------------------------------

def _result(score: float) -> ScoreResult:
    return ScoreResult(score=score, verdict="", suitable=True, factors={}, reasons=[])


def test_blend_kit_perfect_match_unchanged():
    r = score_point(pt(wind_speed_kn=20), wind_only())
    assert blend_kit(r, 1.0) is r


def test_blend_kit_no_kit_caps_to_40_percent():
    out = blend_kit(_result(90.0), 0.0)
    assert out.score == pytest.approx(36.0, abs=0.1)  # 90 * 0.4
    assert out.verdict == "marginal"
    assert out.suitable is False
    assert out.factors["kit"] == 0.0


def test_blend_kit_partial_match_scales():
    out = blend_kit(_result(90.0), 0.5)
    # 90 * (0.4 + 0.6*0.5) = 90 * 0.7 = 63
    assert out.score == pytest.approx(63.0, abs=0.1)
    assert out.suitable is True
