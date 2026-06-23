"""Unit tests for the water-type forecast policy."""

from __future__ import annotations

from datetime import datetime

from swelligence.policy import apply_water_policy, marine_wanted
from swelligence.providers.base import ForecastPoint, SpotForecast


def _forecast() -> SpotForecast:
    return SpotForecast(
        provider="open_meteo",
        latitude=50.7,
        longitude=-1.7,
        points=[
            ForecastPoint(
                time=datetime(2026, 6, 23, 12),
                wind_speed_kn=15.0,
                wave_height_m=0.8,
                wave_period_s=5.0,
                swell_height_m=0.6,
                water_temp_c=18.0,
            )
        ],
    )


def test_marine_wanted():
    assert marine_wanted("sea") is True
    assert marine_wanted("sheltered") is True
    assert marine_wanted("inland") is False


def test_inland_nulls_waves_and_temp():
    fc = _forecast()
    apply_water_policy(fc, "inland")
    p = fc.points[0]
    assert p.wave_height_m is None
    assert p.swell_height_m is None
    assert p.water_temp_c is None
    # Wind data is untouched.
    assert p.wind_speed_kn == 15.0


def test_sheltered_nulls_waves_keeps_temp():
    fc = _forecast()
    apply_water_policy(fc, "sheltered")
    p = fc.points[0]
    assert p.wave_height_m is None
    assert p.swell_height_m is None
    assert p.water_temp_c == 18.0


def test_sea_unchanged():
    fc = _forecast()
    apply_water_policy(fc, "sea")
    p = fc.points[0]
    assert p.wave_height_m == 0.8
    assert p.water_temp_c == 18.0


def test_policy_records_provenance():
    fc = _forecast()
    apply_water_policy(fc, "inland")
    assert "water_policy" in fc.source_meta
