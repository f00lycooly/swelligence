"""Unit tests for safety-flag derivation (bd swelligence-slh.2).

Flags are advisory markers ("why a slot may be unsafe"), separate from score.
They are derived from the factor values + notes the scorer already computes, so
a flag can never disagree with the score it accompanies. Restraint is a
first-class requirement: benign conditions must produce no flags.
"""

from __future__ import annotations

from datetime import datetime

from swelligence.providers.base import ForecastPoint
from swelligence.safety import (
    CAUTION,
    DANGER,
    SafetyFlag,
    derive_safety_flags,
)
from swelligence.scoring import score_point
from swelligence.sports import SportProfile

T = datetime(2026, 6, 23, 12)


def waves_desired(**kw) -> SportProfile:
    """Surf-like profile: wave_ideal_m set => over-max waves are 'too big'."""
    base = dict(
        key="t", label="T", icon="mdi:test", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=15, gust_max_kn=20,
        wave_min_m=0.6, wave_ideal_m=1.5, wave_max_m=3.5,
        weight_wind=0.6, weight_wave=1.0, weight_dir=0.0, weight_gust=0.0,
        weight_temp=0.0,
    )
    base.update(kw)
    return SportProfile(**base)


def flat_preferred(**kw) -> SportProfile:
    """Wind-sport-like profile: no wave_ideal_m => over-max waves are 'too choppy'."""
    base = dict(
        key="t", label="T", icon="mdi:test", water="sea",
        wind_min_kn=12, wind_ideal_kn=20, wind_max_kn=30, gust_max_kn=40,
        wave_max_m=2.5,
        weight_wind=1.0, weight_wave=0.5, weight_dir=0.0, weight_gust=0.3,
        weight_temp=0.0,
    )
    base.update(kw)
    return SportProfile(**base)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


# --- derive_safety_flags (pure) ----------------------------------------------

def test_over_max_wind_flags_too_strong_danger():
    flags = derive_safety_flags(flat_preferred(), {"wind": (0.0, "too strong (40kn)")})
    assert flags == [SafetyFlag("too_strong", DANGER, "too strong (40kn)")]


def test_zeroed_waves_on_surf_flag_too_big():
    flags = derive_safety_flags(waves_desired(), {"wave": (0.0, "too big (4.0m)")})
    assert flags == [SafetyFlag("too_big", DANGER, "too big (4.0m)")]


def test_zeroed_waves_on_wind_sport_flag_too_choppy():
    flags = derive_safety_flags(flat_preferred(), {"wave": (0.0, "too choppy (3.0m)")})
    assert flags == [SafetyFlag("too_choppy", DANGER, "too choppy (3.0m)")]


def test_gust_over_ceiling_flags_gusty_caution():
    flags = derive_safety_flags(flat_preferred(), {"gust": (0.5, "gusting 50kn (over 40)")})
    assert flags == [SafetyFlag("gusty", CAUTION, "gusting 50kn (over 40)")]


def test_empty_note_falls_back_to_plain_message():
    flags = derive_safety_flags(flat_preferred(), {"wind": (0.0, "")})
    assert flags[0].kind == "too_strong"
    assert flags[0].message  # non-empty fallback


def test_as_dict_shape():
    f = SafetyFlag("too_strong", DANGER, "too strong (40kn)")
    assert f.as_dict() == {"kind": "too_strong", "severity": DANGER, "message": "too strong (40kn)"}


# --- restraint: benign conditions produce NO flags ---------------------------

def test_under_powered_wind_is_not_flagged():
    # under-power yields a positive factor, never 0.0 -> no danger flag.
    flags = derive_safety_flags(flat_preferred(), {"wind": (0.4, "under-powered (5kn)")})
    assert flags == []


def test_comfortable_chop_is_not_flagged():
    flags = derive_safety_flags(flat_preferred(), {"wave": (1.0, "")})
    assert flags == []


def test_gust_at_ceiling_is_not_flagged():
    # _gust_factor returns exactly 1.0 at/under the ceiling -> no gusty flag.
    flags = derive_safety_flags(flat_preferred(), {"gust": (1.0, "")})
    assert flags == []


def test_no_factors_no_flags():
    assert derive_safety_flags(flat_preferred(), {}) == []


# --- integration via score_point ---------------------------------------------

def test_score_point_exposes_safety_flags_field():
    res = score_point(pt(wind_speed_kn=10), flat_preferred())
    assert isinstance(res.safety_flags, list)


def test_hard_fail_flag_and_cap_co_occur():
    # Unification: the same over-max wind that caps the score also raises the flag.
    res = score_point(pt(wind_speed_kn=40), flat_preferred())
    assert res.score <= 30.0
    kinds = [f.kind for f in res.safety_flags]
    assert "too_strong" in kinds
    assert all(f.severity == DANGER for f in res.safety_flags if f.kind == "too_strong")


def test_benign_score_point_has_no_safety_flags():
    res = score_point(pt(wind_speed_kn=20, wind_gust_kn=22, wave_height_m=0.3), flat_preferred())
    assert res.safety_flags == []
