"""Unit tests for the pure marine-overlay merge."""

from __future__ import annotations

from datetime import datetime, timezone

from swelligence.overlay import filled_domains, merge_marine, resolve_route
from swelligence.providers.base import ForecastPoint
from swelligence.providers.domains import WATER, WAVE


def base_pt(hour: int, **kw) -> ForecastPoint:
    # Open-Meteo style: naive *local* time.
    return ForecastPoint(time=datetime(2026, 6, 23, hour), **kw)


def ov_pt(hour: int, **kw) -> ForecastPoint:
    # Stormglass style: aware UTC time.
    return ForecastPoint(time=datetime(2026, 6, 23, hour, tzinfo=timezone.utc), **kw)


# Base local 12:00 with UTC+1 offset == overlay 11:00 UTC (same instant).
OFFSET = 3600


def test_gapfill_fills_missing_only():
    base = [base_pt(12, wind_speed_kn=15)]
    ov = [ov_pt(11, wave_height_m=1.2, swell_height_m=0.8, water_temp_c=17.0)]
    filled = merge_marine(base, ov, prefer=False, base_offset_seconds=OFFSET)
    assert base[0].wave_height_m == 1.2
    assert base[0].water_temp_c == 17.0
    assert base[0].wind_speed_kn == 15  # base wind untouched
    assert "wave_height_m" in filled and "water_temp_c" in filled


def test_gapfill_does_not_overwrite_existing():
    base = [base_pt(12, wave_height_m=0.5)]
    ov = [ov_pt(11, wave_height_m=1.2)]
    filled = merge_marine(base, ov, prefer=False, base_offset_seconds=OFFSET)
    assert base[0].wave_height_m == 0.5
    assert "wave_height_m" not in filled


def test_prefer_overwrites_existing():
    base = [base_pt(12, wave_height_m=0.5)]
    ov = [ov_pt(11, wave_height_m=1.2)]
    merge_marine(base, ov, prefer=True, base_offset_seconds=OFFSET)
    assert base[0].wave_height_m == 1.2


def test_unaligned_timestamps_skipped():
    base = [base_pt(12)]
    ov = [ov_pt(20, wave_height_m=1.2)]  # different instant
    filled = merge_marine(base, ov, prefer=True, base_offset_seconds=OFFSET)
    assert base[0].wave_height_m is None
    assert not filled


def test_filled_domains_mapping():
    assert filled_domains({"wave_height_m"}) == {WAVE}
    assert filled_domains({"water_temp_c"}) == {WATER}
    assert filled_domains({"swell_height_m", "water_temp_c"}) == {WAVE, WATER}
    assert filled_domains(set()) == set()


def test_resolve_route_inherits_or_overrides():
    # inherit sentinels fall back to the entry-level value...
    assert resolve_route(None, "stormglass") == "stormglass"
    assert resolve_route("", "stormglass") == "stormglass"
    assert resolve_route("inherit", "stormglass") == "stormglass"
    # ...any real value overrides, including an explicit "none" (off).
    assert resolve_route("windy", "stormglass") == "windy"
    assert resolve_route("none", "stormglass") == "none"
