"""Unit tests for the rider sizing model.

The model constants are calibrated against published manufacturer wind-range
charts (see ``mockups/research/kit-sizing-manufacturers.md``). The
``test_*_within_manufacturer_range`` fixtures below regression-lock that
calibration: for each charted (size, weight, wind-range) row the model's
recommended size must fall inside the manufacturer's published wind window, so a
future change to ``KITE_CONSTANT`` / ``WING_CONSTANT`` that drifts away from the
real charts fails the suite.
"""

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
        # KITE_CONSTANT = 2.6 (calibrated): 2.6 * weight / wind
        ("kitesurf", 80, 20, 10.4),  # 2.6 * 80 / 20
        ("kitesurf", 80, 12, 17.3),  # light wind -> bigger kite
        ("kitesurf", 80, 30, 6.9),   # strong wind -> smaller kite
        # WING_CONSTANT = 1.1 (calibrated): 1.1 * weight / wind
        ("wingfoil", 80, 16, 5.5),   # 1.1 * 80 / 16
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
    bigger = ideal_size("kitesurf", 80, 20, constants={"kitesurf": 5.2})
    assert bigger == pytest.approx(2 * base, abs=0.05)


# --- manufacturer-chart calibration ------------------------------------------
# Each row is (size_m2, reference_weight_kg, wind_lo_kn, wind_hi_kn) straight
# from the published chart. The model recommends a *size* for a given wind; the
# calibration is sound when the size the manufacturer rates for [lo, hi] is one
# the model would recommend somewhere inside that wind window — i.e.
#   size@hi  <=  charted_size  <=  size@lo
# (lighter wind -> bigger recommended size, hence the bracket order). Ranges are
# wide, so this is a meaningful-but-robust check rather than a point fit.
#
# Rows are restricted to each chart's normal riding band. The textbook 1/wind^2
# curvature shows up only at the small-wing / very-high-wind extreme (Cabrinha's
# 1-2 m wings need far more wind than a linear law predicts); those rows are out
# of the linear model's intended scope and deliberately omitted — documented in
# mockups/research/kit-sizing-manufacturers.md.

# Cabrinha Moto X Lite kite chart, 75 kg rider.
_CABRINHA_KITE_75 = [
    (6, 75, 21, 40),
    (7, 75, 19, 38),
    (8, 75, 17, 36),
    (9, 75, 15, 34),
    (10, 75, 13, 32),
    (11, 75, 11, 30),
    (12, 75, 9, 25),
]

# Cabrinha wing chart, 75 kg rider (3-5 m riding band).
_CABRINHA_WING_75 = [
    (3, 75, 18, 32),
    (4, 75, 13, 27),
    (5, 75, 11, 26),
]

# Duotone Unit 2025 wing chart (~78 kg typical).
_DUOTONE_WING_78 = [
    (2.0, 78, 27, 45),
    (3.0, 78, 19, 37),
    (4.0, 78, 14, 30),
    (5.0, 78, 10, 25),
    (6.0, 78, 8, 20),
    (6.5, 78, 7, 18),
]


@pytest.mark.parametrize(
    "sport,rows",
    [
        ("kitesurf", _CABRINHA_KITE_75),
        ("wingfoil", _CABRINHA_WING_75),
        ("wingfoil", _DUOTONE_WING_78),
    ],
)
def test_size_within_manufacturer_range(sport, rows):
    for size, weight, lo, hi in rows:
        size_at_lo = ideal_size(sport, weight, lo)
        size_at_hi = ideal_size(sport, weight, hi)
        assert size_at_hi <= size <= size_at_lo, (
            f"{sport} {size}m2 @ {weight}kg: charted range {lo}-{hi}kn maps to "
            f"model sizes {size_at_hi}-{size_at_lo}m2, which does not bracket "
            f"{size}m2 — constant drifted from the manufacturer chart"
        )


# --- recommend_kit ------------------------------------------------------------

def test_unsized_sport_is_neutral():
    rec = recommend_kit("surf", 80, 15, [])
    assert rec.power == POWER_NA
    assert rec.factor == 1.0  # no effect on score


def test_no_kit_caps_factor_to_zero():
    rec = recommend_kit("kitesurf", 80, 20, [])
    assert rec.power == POWER_NO_KIT
    assert rec.factor == 0.0
    assert rec.ideal_size_m2 == 10.4  # 2.6 * 80 / 20
    assert "no kit" in rec.summary


def test_perfect_match_is_ideal():
    # ideal 8.0m² at 26kn (2.6*80/26); owning an 8 is a perfect rig.
    rec = recommend_kit("kitesurf", 80, 26, [6, 8, 10])
    assert rec.owned_size_m2 == 8
    assert rec.power == POWER_IDEAL
    assert rec.factor == 1.0
    assert "rig your 8" in rec.summary


def test_underpowered_when_nearest_is_smaller():
    # ideal 17.3m² at 12kn; biggest owned is 12 -> underpowered.
    rec = recommend_kit("kitesurf", 80, 12, [7, 9, 12])
    assert rec.owned_size_m2 == 12
    assert rec.power == POWER_UNDER
    assert 0 < rec.factor < 1


def test_overpowered_when_nearest_is_bigger():
    # ideal ~5.9m² at 35kn; smallest owned is 7 -> overpowered.
    rec = recommend_kit("kitesurf", 80, 35, [7, 9, 12])
    assert rec.owned_size_m2 == 7
    assert rec.power == POWER_OVER
    assert 0 < rec.factor < 1


def test_factor_decreases_with_deviation():
    near = recommend_kit("kitesurf", 80, 20, [10])      # ideal ~10.4, close
    far = recommend_kit("kitesurf", 80, 20, [5])        # way too small
    assert near.factor > far.factor


def test_wing_sizing():
    # ideal 5.5m² at 16kn (1.1*80/16); owning a 5 is within the ideal band.
    rec = recommend_kit("wingfoil", 80, 16, [3, 4, 5])
    assert rec.ideal_size_m2 == 5.5
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
