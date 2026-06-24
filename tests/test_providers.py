"""Unit tests for Open-Meteo response normalisation (no network)."""

from __future__ import annotations

import asyncio

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
        "apparent_temperature": [16.0, 17.0],
        "precipitation": [0.0, 0.1],
        "cloud_cover": [10, 20],
        "uv_index": [3.0, 4.0],
        "visibility": [24000, 20000],
        "weather_code": [1, 3],
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
        "swell_wave_peak_period": [11.0, 12.0],
        "wind_wave_height": [0.3, 0.4],
        "wind_wave_period": [3.0, 3.5],
        "secondary_swell_wave_height": [0.2, 0.25],
        "secondary_swell_wave_period": [14.0, 15.0],
        "secondary_swell_wave_direction": [120, 130],
        "ocean_current_velocity": [1.852, 3.704],  # km/h -> 1.0, 2.0 kn
        "ocean_current_direction": [90, 95],
        "sea_level_height_msl": [0.4, 0.1],
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


def test_additional_detail_fields_captured():
    pts = OpenMeteoProvider._merge(WIND, MARINE)
    p = pts[0]
    # Marine surf-quality detail.
    assert p.swell_peak_period_s == 11.0
    assert p.wind_wave_height_m == 0.3 and p.wind_wave_period_s == 3.0
    assert p.secondary_swell_height_m == 0.2
    assert p.secondary_swell_period_s == 14.0
    assert p.secondary_swell_dir_deg == 120
    # Ocean current: 1.852 km/h -> 1.0 kn; direction passes through.
    assert p.current_speed_kn == pytest.approx(1.0, abs=0.05)
    assert pts[1].current_speed_kn == pytest.approx(2.0, abs=0.05)
    assert p.current_dir_deg == 90
    # Sea level fills the previously-empty WATER field.
    assert p.sea_level_m == 0.4
    # Atmosphere comfort/safety.
    assert p.apparent_temp_c == 16.0
    assert p.uv_index == 3.0 and p.visibility_m == 24000
    assert p.weather_code == 1


def test_additional_fields_none_without_marine():
    p = OpenMeteoProvider._merge(WIND, None)[0]
    # Marine-only detail stays None inland; atmospheric extras still populate.
    assert p.swell_peak_period_s is None and p.current_speed_kn is None
    assert p.sea_level_m is None
    assert p.apparent_temp_c == 16.0 and p.weather_code == 1


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


# --- batched fetch (akc) ----------------------------------------------------


def _wind_payload(speed_ms: float) -> dict:
    return {
        "latitude": 50.0,
        "longitude": -1.0,
        "utc_offset_seconds": 0,
        "timezone_abbreviation": "GMT",
        "hourly": {"time": ["2026-06-23T12:00"], "wind_speed_10m": [speed_ms]},
    }


def _marine_payload(wave_m: float) -> dict:
    return {"hourly": {"time": ["2026-06-23T12:00"], "wave_height": [wave_m]}}


class _StubProvider(OpenMeteoProvider):
    """Open-Meteo provider with canned HTTP responses, recording call URLs."""

    def __init__(self, forecast, marine):
        super().__init__(None)
        self._forecast, self._marine = forecast, marine
        self.calls: list[str] = []

    async def _get(self, url, params, *, optional=False):
        self.calls.append(url)
        return self._marine if "marine" in url else self._forecast


def test_fetch_many_index_matches_and_two_calls():
    # Two coords -> top-level arrays; results matched by index, two calls total.
    p = _StubProvider(
        forecast=[_wind_payload(5.0), _wind_payload(10.0)],
        marine=[_marine_payload(0.8), _marine_payload(1.5)],
    )
    out = asyncio.run(
        p.async_fetch_many([(50.0, -1.0, True), (51.0, -2.0, True)])
    )
    assert len(out) == 2
    assert out[0].points[0].wind_speed_kn == pytest.approx(9.7, abs=0.05)
    assert out[1].points[0].wind_speed_kn == pytest.approx(19.4, abs=0.05)
    assert out[0].points[0].wave_height_m == 0.8
    assert out[1].points[0].wave_height_m == 1.5
    assert p.calls.count("https://api.open-meteo.com/v1/forecast") == 1
    assert p.calls.count("https://marine-api.open-meteo.com/v1/marine") == 1


def test_fetch_many_single_coord_object_response():
    # One coord -> Open-Meteo returns top-level objects, not arrays.
    p = _StubProvider(forecast=_wind_payload(5.0), marine=_marine_payload(0.8))
    out = asyncio.run(p.async_fetch_many([(50.0, -1.0, True)]))
    assert len(out) == 1
    assert out[0].points[0].wave_height_m == 0.8


def test_fetch_many_per_coord_marine_flag():
    # First wants marine, second is inland -> still one marine call, but the
    # inland spot gets no marine data and is marked skipped.
    p = _StubProvider(
        forecast=[_wind_payload(5.0), _wind_payload(6.0)],
        marine=[_marine_payload(0.8), _marine_payload(1.5)],
    )
    out = asyncio.run(
        p.async_fetch_many([(50.0, -1.0, True), (52.0, -1.5, False)])
    )
    assert out[0].points[0].wave_height_m == 0.8
    assert out[1].points[0].wave_height_m is None
    assert out[1].source_meta["marine"] == "skipped (inland spot)"


def test_fetch_many_all_inland_skips_marine_call():
    p = _StubProvider(forecast=[_wind_payload(5.0)], marine=None)
    out = asyncio.run(p.async_fetch_many([(48.0, 2.0, False)]))
    assert out[0].points[0].wind_speed_kn == pytest.approx(9.7, abs=0.05)
    assert "marine-api.open-meteo.com/v1/marine" not in p.calls


def test_fetch_many_empty():
    assert asyncio.run(OpenMeteoProvider(None).async_fetch_many([])) == []


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
