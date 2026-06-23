"""Unit tests for Open-Meteo response normalisation (no network)."""

from __future__ import annotations

import pytest

from swelligence.providers.open_meteo import OpenMeteoProvider

TIMES = ["2026-06-23T12:00", "2026-06-23T13:00"]

WIND = {
    "hourly": {
        "time": TIMES,
        "wind_speed_10m": [5.0, 10.0],      # m/s
        "wind_gusts_10m": [7.0, 12.0],
        "wind_direction_10m": [200, 210],
        "temperature_2m": [18.0, 19.0],
        "precipitation": [0.0, 0.1],
        "cloud_cover": [10, 20],
    }
}

MARINE = {
    "hourly": {
        "time": TIMES,
        "wave_height": [0.8, 0.9],
        "wave_period": [5.0, 6.0],
        "wave_direction": [180, 190],
        "swell_wave_height": [0.6, 0.7],
        "swell_wave_period": [8.0, 9.0],
        "sea_surface_temperature": [18.0, 18.5],
    }
}


def test_ms_to_knots_conversion():
    pts = OpenMeteoProvider._merge(WIND, None)
    assert len(pts) == 2
    # 5 m/s * 1.94384 = 9.7 kn (rounded to 1dp)
    assert pts[0].wind_speed_kn == pytest.approx(9.7, abs=0.05)
    assert pts[1].wind_speed_kn == pytest.approx(19.4, abs=0.05)
    assert pts[0].wind_gust_kn == pytest.approx(13.6, abs=0.05)


def test_no_marine_leaves_wave_fields_none():
    pts = OpenMeteoProvider._merge(WIND, None)
    assert pts[0].wave_height_m is None
    assert pts[0].water_temp_c is None
    # Non-marine fields still populated.
    assert pts[0].air_temp_c == 18.0
    assert pts[0].cloud_pct == 10


def test_marine_merged_by_time():
    pts = OpenMeteoProvider._merge(WIND, MARINE)
    assert pts[0].wave_height_m == 0.8
    assert pts[1].swell_height_m == 0.7
    assert pts[0].water_temp_c == 18.0


def test_marine_time_misalignment_handled():
    # Marine only has the second hour; first point must stay None.
    misaligned = {
        "hourly": {
            "time": [TIMES[1]],
            "wave_height": [1.1],
            "wave_period": [7.0],
            "wave_direction": [200],
            "swell_wave_height": [0.9],
            "swell_wave_period": [10.0],
            "sea_surface_temperature": [17.5],
        }
    }
    pts = OpenMeteoProvider._merge(WIND, misaligned)
    assert pts[0].wave_height_m is None
    assert pts[1].wave_height_m == 1.1


def test_empty_wind_returns_no_points():
    assert OpenMeteoProvider._merge(None, None) == []
    assert OpenMeteoProvider._merge({}, None) == []


def test_grid_distance_from_snapped_coords():
    from swelligence.providers.open_meteo import _grid_distance_km

    # Open-Meteo echoes the resolved grid cell; offset from the request is the
    # data-quality signal.
    snapped = {"latitude": -43.55, "longitude": 172.75}
    d = _grid_distance_km(-43.5, 172.7, snapped)
    assert d is not None and 5.0 < d < 8.0
    # Missing or coord-less payloads yield no signal.
    assert _grid_distance_km(-43.5, 172.7, None) is None
    assert _grid_distance_km(-43.5, 172.7, {"latitude": -43.5}) is None
