"""Unit tests for the free-tier safe-poll interval derivation."""

from __future__ import annotations

from swelligence.providers import (
    OpenMeteoProvider,
    StormglassProvider,
    free_tier_min_interval_minutes,
)


def test_stormglass_single_spot_interval():
    # 10 req/day * 0.8 safety = 8 req; /2 per fetch = 4 fetches/day; 1440/4 = 360.
    assert free_tier_min_interval_minutes(StormglassProvider, 1) == 360


def test_interval_scales_with_spot_count():
    # Two spots share the budget -> each polls half as often (twice the interval).
    one = free_tier_min_interval_minutes(StormglassProvider, 1)
    two = free_tier_min_interval_minutes(StormglassProvider, 2)
    assert two == 2 * one


def test_no_free_tier_returns_none():
    # Open-Meteo is keyless/unmetered -> no free-tier budget -> no throttle.
    assert OpenMeteoProvider.free_tier_daily_requests is None
    assert free_tier_min_interval_minutes(OpenMeteoProvider, 1) is None


def test_zero_spots_treated_as_one():
    assert free_tier_min_interval_minutes(StormglassProvider, 0) == 360
