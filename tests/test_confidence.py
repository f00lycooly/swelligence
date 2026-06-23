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
from swelligence.providers.stormglass import StormglassProvider
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


# --- Stormglass integration -------------------------------------------------

def test_stormglass_spread_excludes_sg_blend():
    # sg is Stormglass's own blend of the others, not an independent model.
    vals = StormglassProvider._spread(
        {"sg": 1.5, "noaa": 1.4, "icon": 1.6}, is_wind=False
    )
    assert sorted(vals) == [1.4, 1.6]


def test_stormglass_spread_converts_wind_to_knots():
    vals = StormglassProvider._spread({"noaa": 10.0, "icon": 10.0}, is_wind=True)
    assert all(v > 18 for v in vals)  # 10 m/s ~ 19.4 kn


def test_stormglass_parse_populates_source_confidence():
    payload = {
        "hours": [
            {
                "time": "2026-06-23T09:00:00+00:00",
                "waveHeight": {"sg": 1.5, "noaa": 1.5, "icon": 1.52},
                "swellPeriod": {"sg": 11.0, "noaa": 7.0, "dwd": 13.0},
            }
        ]
    }
    points = StormglassProvider._parse_weather(payload)
    assert len(points) == 1
    conf = points[0].source_confidence
    assert conf is not None
    # Wave height: tight agreement -> high.
    assert conf["wave_height_m"] > 0.85
    # Swell period: 7..13s spread -> lower confidence than wave height.
    assert conf["swell_period_s"] < conf["wave_height_m"]


def test_stormglass_single_source_field_has_no_confidence():
    payload = {
        "hours": [
            {"time": "2026-06-23T09:00:00+00:00", "waveHeight": {"sg": 1.5}}
        ]
    }
    points = StormglassProvider._parse_weather(payload)
    # Only sg present -> nothing independent to compare -> no confidence at all.
    assert points[0].source_confidence is None
    assert points[0].wave_height_m == 1.5


def test_every_scale_field_is_a_known_point_field():
    fields = set(ForecastPoint.__dataclass_fields__)
    assert set(FIELD_UNCERTAINTY_SCALE).issubset(fields)
