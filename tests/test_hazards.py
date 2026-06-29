"""Unit tests for the weather safety-hazard evaluator (pure)."""

from __future__ import annotations

from datetime import datetime

from swelligence.hazards import (
    FOG,
    HEAVY_RAIN,
    SQUALL,
    THUNDERSTORM,
    TIER_HARD,
    TIER_OFF,
    TIER_WARN,
    Hazard,
    HazardConfig,
    evaluate_hazards,
    has_hard,
)
from swelligence.providers.base import ForecastPoint

T = datetime(2026, 6, 29, 12)


def pt(**kw) -> ForecastPoint:
    return ForecastPoint(time=T, **kw)


def test_thunderstorm_from_weather_code():
    hz = evaluate_hazards(pt(weather_code=95), HazardConfig())
    assert [h.kind for h in hz] == [THUNDERSTORM]
    assert hz[0].tier == TIER_HARD


def test_thunderstorm_from_cape():
    hz = evaluate_hazards(pt(cape_jkg=1500), HazardConfig())
    assert any(h.kind == THUNDERSTORM for h in hz)


def test_cape_below_threshold_is_clear():
    assert evaluate_hazards(pt(cape_jkg=500), HazardConfig()) == []


def test_fog_below_visibility_threshold():
    hz = evaluate_hazards(pt(visibility_m=800), HazardConfig())
    assert [h.kind for h in hz] == [FOG]
    assert hz[0].tier == TIER_WARN


def test_squall_at_default_force_8():
    assert evaluate_hazards(pt(wind_gust_kn=34), HazardConfig()) != []
    assert evaluate_hazards(pt(wind_gust_kn=33), HazardConfig()) == []


def test_squall_threshold_is_tunable():
    cfg = HazardConfig(squall_gust_kn=41)  # Force 9
    assert evaluate_hazards(pt(wind_gust_kn=34), cfg) == []
    assert evaluate_hazards(pt(wind_gust_kn=41), cfg) != []


def test_heavy_rain_threshold():
    hz = evaluate_hazards(pt(precip_mm=7.5), HazardConfig())
    assert [h.kind for h in hz] == [HEAVY_RAIN]


def test_off_tier_suppresses_hazard():
    cfg = HazardConfig(thunderstorm=TIER_OFF)
    assert evaluate_hazards(pt(weather_code=99), cfg) == []


def test_none_values_never_trigger():
    assert evaluate_hazards(pt(), HazardConfig()) == []


def test_has_hard():
    assert has_hard([Hazard(THUNDERSTORM, TIER_HARD, "x")]) is True
    assert has_hard([Hazard(FOG, TIER_WARN, "x")]) is False
    assert has_hard([]) is False
