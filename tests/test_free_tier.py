"""Unit tests for the free-tier safe-poll interval derivation.

The throttle is provider-agnostic: it reads ``free_tier_daily_requests`` /
``requests_per_fetch`` off any provider. No current provider sets a free tier
(Open-Meteo is unmetered), so a small synthetic provider stands in for one with a
quota — keeping the generic logic tested without depending on a removed provider.
"""

from __future__ import annotations

from swelligence.providers import OpenMeteoProvider, free_tier_min_interval_minutes
from swelligence.providers.base import ForecastProvider


class _Metered(ForecastProvider):
    """Synthetic provider with a 10/day budget, 2 requests per fetch."""

    key = "metered"
    free_tier_daily_requests = 10
    requests_per_fetch = 2

    async def async_fetch(self, latitude, longitude, *, days=7, marine=True):  # pragma: no cover
        raise NotImplementedError


def test_metered_single_spot_interval():
    # 10 req/day * 0.8 safety = 8 req; /2 per fetch = 4 fetches/day; 1440/4 = 360.
    assert free_tier_min_interval_minutes(_Metered, 1) == 360


def test_interval_scales_with_spot_count():
    # Two spots share the budget -> each polls half as often (twice the interval).
    one = free_tier_min_interval_minutes(_Metered, 1)
    two = free_tier_min_interval_minutes(_Metered, 2)
    assert two == 2 * one


def test_no_free_tier_returns_none():
    # Open-Meteo is keyless/unmetered -> no free-tier budget -> no throttle.
    assert OpenMeteoProvider.free_tier_daily_requests is None
    assert free_tier_min_interval_minutes(OpenMeteoProvider, 1) is None


def test_zero_spots_treated_as_one():
    assert free_tier_min_interval_minutes(_Metered, 0) == 360
