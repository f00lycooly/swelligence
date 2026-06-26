"""Unit tests for the rider sizing model."""

from __future__ import annotations

import pytest

from swelligence.sizing import (
    POWER_IDEAL,
    POWER_NA,
    POWER_NO_KIT,
    POWER_OVER,
    POWER_UNDER,
    KitRecommendation,
    ideal_size,
    kit_payload,
    recommend_kit,
)


# --- ideal_size ---------------------------------------------------------------

@pytest.mark.parametrize(
    "sport,weight,wind,expected",
    [
        ("kitesurf", 80, 20, 9.0),   # 2.25 * 80 / 20
        ("kitesurf", 80, 12, 15.0),  # light wind -> bigger kite
        ("kitesurf", 80, 30, 6.0),   # strong wind -> smaller kite
        ("wingfoil", 80, 16, 5.0),   # 1.0 * 80 / 16
    ],
)
def test_ideal_size_known_points(sport, weight, wind, expected):
    assert ideal_size(sport, weight, wind) == pytest.approx(expected, abs=0.05)


def test_ideal_size_scales_with_weight():
    light = ideal_size("kitesurf", 60, 20)
    heavy = ideal_size("kitesurf", 100, 20)
    assert heavy > light


def test_unsized_sport_returns_none():
    assert ideal_size("surf", 80, 15) is None
    assert ideal_size("sup", 80, 10) is None


def test_no_wind_returns_none():
    assert ideal_size("kitesurf", 80, 0) is None
    assert ideal_size("kitesurf", 80, None) is None


def test_constants_override():
    base = ideal_size("kitesurf", 80, 20)
    bigger = ideal_size("kitesurf", 80, 20, constants={"kitesurf": 4.5})
    assert bigger == pytest.approx(2 * base, abs=0.05)


# --- recommend_kit ------------------------------------------------------------

def test_unsized_sport_is_neutral():
    rec = recommend_kit("surf", 80, 15, [])
    assert rec.power == POWER_NA
    assert rec.factor == 1.0  # no effect on score


def test_no_kit_caps_factor_to_zero():
    rec = recommend_kit("kitesurf", 80, 20, [])
    assert rec.power == POWER_NO_KIT
    assert rec.factor == 0.0
    assert rec.ideal_size_m2 == 9.0
    assert "no kit" in rec.summary


def test_perfect_match_is_ideal():
    rec = recommend_kit("kitesurf", 80, 20, [7, 9, 12])
    assert rec.owned_size_m2 == 9
    assert rec.power == POWER_IDEAL
    assert rec.factor == 1.0
    assert "rig your 9" in rec.summary


def test_underpowered_when_nearest_is_smaller():
    # ideal 15m² at 12kn; biggest owned is 12 -> underpowered.
    rec = recommend_kit("kitesurf", 80, 12, [7, 9, 12])
    assert rec.owned_size_m2 == 12
    assert rec.power == POWER_UNDER
    assert 0 < rec.factor < 1


def test_overpowered_when_nearest_is_bigger():
    # ideal 6m² at 30kn; smallest owned is 7 -> overpowered.
    rec = recommend_kit("kitesurf", 80, 30, [7, 9, 12])
    assert rec.owned_size_m2 == 7
    assert rec.power == POWER_OVER
    assert 0 < rec.factor < 1


def test_factor_decreases_with_deviation():
    near = recommend_kit("kitesurf", 80, 20, [9])      # exact
    far = recommend_kit("kitesurf", 80, 20, [5])       # way too small
    assert near.factor > far.factor


def test_wing_sizing():
    rec = recommend_kit("wingfoil", 80, 16, [3, 4, 5])
    assert rec.ideal_size_m2 == 5.0
    assert rec.power == POWER_IDEAL


def test_kit_payload_serialises_sized_recommendation():
    rec = KitRecommendation("wingfoil", 5.2, 5.0, POWER_IDEAL, 0.95, "rig your 5m²")
    assert kit_payload(rec) == {"rig_m2": 5.0, "ideal_m2": 5.2, "power": POWER_IDEAL}


def test_kit_payload_none_for_na_sport():
    # n/a sport (no size model) -> no kit gauge on the card.
    rec = KitRecommendation("sup", None, None, POWER_NA, 1.0, "")
    assert kit_payload(rec) is None


def test_kit_payload_none_when_no_recommendation():
    assert kit_payload(None) is None


def test_kit_payload_keeps_no_kit_state():
    # rig sport with empty quiver still surfaces its no_kit state.
    rec = KitRecommendation("kitesurf", 9.0, None, POWER_NO_KIT, 0.0, "no kit configured")
    assert kit_payload(rec) == {"rig_m2": None, "ideal_m2": 9.0, "power": POWER_NO_KIT}
