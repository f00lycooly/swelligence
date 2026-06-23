"""Unit tests for the per-(spot, sport) data-quality summary (o07.1)."""

from __future__ import annotations

from datetime import datetime

from swelligence.providers.base import ForecastPoint, SpotForecast
from swelligence.providers.domains import WATER, WAVE, WIND
from swelligence.quality import COARSE_GRID_KM, data_quality
from swelligence.sports import SPORT_PROFILES


def _forecast(point: ForecastPoint | None = None, **meta) -> SpotForecast:
    return SpotForecast(
        provider="open_meteo",
        latitude=-43.5,
        longitude=172.7,
        points=[point] if point else [],
        source_meta=meta,
    )


def _point(**kw) -> ForecastPoint:
    base = dict(time=datetime(2026, 6, 23, 9), wind_speed_kn=14.0, wind_dir_deg=200.0)
    base.update(kw)
    return ForecastPoint(**base)


def test_surf_windsea_only_names_swell_gaps():
    # Open-Meteo gave wave height but no swell partition or direction.
    fc = _forecast(
        _point(wave_height_m=1.4, swell_period_s=None, swell_dir_deg=None),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
    )
    q = data_quality(fc, SPORT_PROFILES["surf"])
    assert "windsea-only" in q["summary"]
    assert "no groundswell direction" in q["summary"]
    assert "no groundswell period" in q["issues"]
    assert "no swell direction" in q["issues"]
    assert q["summary"].startswith("wind: open_meteo")


def test_surf_clean_groundswell_has_no_swell_issues():
    fc = _forecast(
        _point(wave_height_m=1.4, swell_period_s=12.0, swell_dir_deg=210.0),
        sources={WIND: "open_meteo", WAVE: "stormglass"},
    )
    q = data_quality(fc, SPORT_PROFILES["surf"])
    assert q["issues"] == []
    assert "swell: stormglass" in q["summary"]


def test_marine_unavailable_flags_missing_waves():
    fc = _forecast(
        _point(wave_height_m=None),
        sources={WIND: "open_meteo"},
        marine="unavailable (unsupported grid)",
    )
    q = data_quality(fc, SPORT_PROFILES["surf"])
    assert "no wave data" in q["issues"]
    assert "unavailable (unsupported grid)" in q["summary"]


def test_wind_sport_ignores_swell():
    # Kitesurf scores no swell, so missing swell must not appear as an issue.
    fc = _forecast(
        _point(wave_height_m=0.8, swell_period_s=None),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
    )
    q = data_quality(fc, SPORT_PROFILES["kitesurf"])
    assert q["issues"] == []
    assert "swell" not in q["summary"]
    assert "waves: open_meteo" in q["summary"]


def test_missing_wind_direction_for_dir_scored_sport():
    fc = _forecast(
        _point(wind_dir_deg=None, wave_height_m=0.5),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
    )
    q = data_quality(fc, SPORT_PROFILES["kitesurf"])
    assert "no wind direction" in q["issues"]


def test_seaswim_flags_missing_water_temp():
    fc = _forecast(
        _point(wave_height_m=0.3, water_temp_c=None),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
    )
    q = data_quality(fc, SPORT_PROFILES["seaswim"])
    assert "no water temperature" in q["issues"]
    assert "water temp: missing" in q["summary"]


def test_seaswim_names_water_source_when_present():
    fc = _forecast(
        _point(wave_height_m=0.3, water_temp_c=15.0),
        sources={WIND: "open_meteo", WAVE: "open_meteo", WATER: "stormglass"},
    )
    q = data_quality(fc, SPORT_PROFILES["seaswim"])
    assert "water temp: stormglass" in q["summary"]
    assert "no water temperature" not in q["issues"]


def test_grid_distance_surfaced_and_flagged_when_coarse():
    near = _forecast(
        _point(wave_height_m=1.0, swell_period_s=10.0, swell_dir_deg=200.0),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
        grid_distance_km=2.0,
    )
    q_near = data_quality(near, SPORT_PROFILES["surf"])
    assert q_near["grid_distance_km"] == 2.0
    assert not any("grid cell" in i for i in q_near["issues"])

    far = _forecast(
        _point(wave_height_m=1.0, swell_period_s=10.0, swell_dir_deg=200.0),
        sources={WIND: "open_meteo", WAVE: "open_meteo"},
        grid_distance_km=COARSE_GRID_KM + 5,
    )
    q_far = data_quality(far, SPORT_PROFILES["surf"])
    assert any("grid cell" in i for i in q_far["issues"])
