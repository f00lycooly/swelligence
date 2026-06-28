"""Unit tests for forecast confidence from model agreement (o07.2)."""

from __future__ import annotations

from datetime import datetime

from swelligence.confidence import (
    FIELD_UNCERTAINTY_SCALE,
    aggregate_confidence,
    confidence_label,
    field_confidence,
)
from swelligence.providers.base import ForecastPoint
from swelligence.sports import SPORT_PROFILES


# --- field_confidence -------------------------------------------------------

def test_tight_agreement_is_high_confidence():
    # Three models within ~0.1m on wave height -> near-perfect agreement.
    c = field_confidence("wave_height_m", [1.50, 1.55, 1.52])
    assert c is not None and c > 0.85


def test_wide_divergence_is_low_confidence():
    # Spread ~ the full uncertainty scale (0.6m) -> confidence collapses.
    c = field_confidence("wave_height_m", [0.8, 1.6, 2.4])
    assert c is not None and c < 0.2


def test_single_source_has_no_confidence():
    assert field_confidence("wave_height_m", [1.5]) is None
    assert field_confidence("wave_height_m", []) is None


def test_unknown_field_has_no_scale():
    assert field_confidence("not_a_field", [1.0, 2.0]) is None


def test_direction_uses_circular_spread():
    # 355 and 5 degrees are 10 apart, not 350 — circular maths must see tight
    # agreement, so confidence stays high.
    c = field_confidence("wind_dir_deg", [355.0, 5.0])
    assert c is not None and c > 0.7


def test_perfect_agreement_is_full_confidence():
    assert field_confidence("swell_period_s", [11.0, 11.0, 11.0]) == 1.0


def test_confidence_label_bands():
    assert confidence_label(0.9) == "high"
    assert confidence_label(0.5) == "moderate"
    assert confidence_label(0.2) == "low"


# --- aggregate_confidence ---------------------------------------------------

def _point(conf: dict | None) -> ForecastPoint:
    return ForecastPoint(time=datetime(2026, 6, 23, 9), source_confidence=conf)


def test_aggregate_weights_by_sport_factor():
    # Surf leans hardest on wave (1.0) and swell (0.7); wind is lighter (0.6).
    point = _point({
        "wave_height_m": 0.9,
        "swell_period_s": 0.9,
        "wind_speed_kn": 0.2,
    })
    agg = aggregate_confidence(point, SPORT_PROFILES["surf"])
    assert agg is not None
    # Wave/swell dominate, so the blend sits well above the wind value.
    assert agg["value"] > 0.7
    assert agg["label"] == "high"
    assert set(agg["fields"]) == {"wave_height_m", "swell_period_s", "wind_speed_kn"}


def test_aggregate_ignores_fields_the_sport_does_not_score():
    # Kitesurf has weight_swell == 0, so a low swell confidence must not drag it.
    point = _point({"wind_speed_kn": 0.9, "swell_period_s": 0.1})
    agg = aggregate_confidence(point, SPORT_PROFILES["kitesurf"])
    assert agg is not None
    assert "swell_period_s" not in agg["fields"]
    assert agg["value"] == 0.9


def test_aggregate_none_without_signal():
    assert aggregate_confidence(_point(None), SPORT_PROFILES["surf"]) is None
    assert aggregate_confidence(_point({}), SPORT_PROFILES["surf"]) is None


def test_every_scale_field_is_a_known_point_field():
    fields = set(ForecastPoint.__dataclass_fields__)
    assert set(FIELD_UNCERTAINTY_SCALE).issubset(fields)


# --- newly-scored fields (48w.7: surf-quality trio) -------------------------

def test_new_scored_fields_have_uncertainty_scales():
    # Fields wired into scoring by 48w.7 must carry a confidence scale so 48w.1's
    # aggregate sees them.
    for field in ("swell_peak_period_s", "wind_wave_height_m", "secondary_swell_height_m"):
        assert field in FIELD_UNCERTAINTY_SCALE
        assert field_confidence(field, [1.0, 1.0]) == 1.0


def test_aggregate_includes_clean_factor_fields_for_surf():
    # Surf scores cleanliness (wind-wave + secondary swell), so their agreement
    # must feed the aggregate confidence.
    point = _point({
        "wave_height_m": 0.9,
        "swell_peak_period_s": 0.9,
        "wind_wave_height_m": 0.8,
        "secondary_swell_height_m": 0.8,
    })
    agg = aggregate_confidence(point, SPORT_PROFILES["surf"])
    assert agg is not None
    assert "wind_wave_height_m" in agg["fields"]
    assert "swell_peak_period_s" in agg["fields"]


def test_clean_fields_ignored_for_non_surf_sport():
    # Kitesurf doesn't score cleanliness -> wind-wave confidence must not count.
    point = _point({"wind_speed_kn": 0.9, "wind_wave_height_m": 0.1})
    agg = aggregate_confidence(point, SPORT_PROFILES["kitesurf"])
    assert agg is not None
    assert "wind_wave_height_m" not in agg["fields"]
    assert agg["value"] == 0.9
