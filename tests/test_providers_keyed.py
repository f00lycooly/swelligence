"""Unit tests for the keyed-provider normalisers (no network).

Windy, Stormglass, and UKHO all factor their response parsing into pure static
methods so the metres/second -> knots, Kelvin -> Celsius, u/v -> speed/dir, and
nearest-station logic are testable without live (paid) API calls.
"""

from __future__ import annotations

import math

import pytest

from swelligence.geo import haversine_km as _haversine
from swelligence.providers.stormglass import StormglassProvider
from swelligence.providers.ukho import UKHOTideProvider
from swelligence.providers.windy import WindyProvider

# --- Stormglass -------------------------------------------------------------

SG_WEATHER = {
    "hours": [
        {
            "time": "2026-06-23T12:00:00+00:00",
            "windSpeed": {"sg": 5.0, "noaa": 4.0},
            "gust": {"sg": 8.0},
            "windDirection": {"sg": 200.0},
            "waveHeight": {"sg": 0.8},
            "airTemperature": {"noaa": 18.0},  # no 'sg' -> falls back to noaa
            "waterTemperature": {"sg": 17.0},
        },
        {"time": "2026-06-23T13:00:00+00:00", "windSpeed": {"sg": 10.0}},
    ]
}
SG_TIDES = {
    "data": [
        {"time": "2026-06-23T06:30:00+00:00", "type": "high", "height": 1.4},
        {"time": "2026-06-23T12:45:00+00:00", "type": "low", "height": -0.2},
    ]
}


def test_stormglass_wind_ms_to_knots_and_source_pick():
    pts = StormglassProvider._parse_weather(SG_WEATHER)
    assert len(pts) == 2
    assert pts[0].wind_speed_kn == pytest.approx(9.7, abs=0.05)
    assert pts[0].wind_gust_kn == pytest.approx(15.6, abs=0.05)
    # windDirection is not a speed -> not converted.
    assert pts[0].wind_dir_deg == 200.0
    # airTemperature falls back to 'noaa' when 'sg' absent.
    assert pts[0].air_temp_c == 18.0
    assert pts[1].wind_speed_kn == pytest.approx(19.4, abs=0.05)


def test_stormglass_missing_params_left_none():
    pts = StormglassProvider._parse_weather(SG_WEATHER)
    assert pts[1].wave_height_m is None
    assert pts[1].air_temp_c is None


def test_stormglass_tides():
    events = StormglassProvider._parse_tides(SG_TIDES)
    assert [e.kind for e in events] == ["high", "low"]
    assert events[0].height_m == 1.4
    assert events[1].height_m == -0.2


def test_stormglass_empty():
    assert StormglassProvider._parse_weather(None) == []
    assert StormglassProvider._parse_tides({}) == []


# --- Windy ------------------------------------------------------------------

WINDY_WIND = {
    "ts": [1_750_000_000_000, 1_750_003_600_000],
    "wind_u-surface": [3.0, -4.0],
    "wind_v-surface": [4.0, 0.0],
    "gust-surface": [8.0, 9.0],
    "temp-surface": [291.15, 293.15],  # Kelvin
    "past3hprecip-surface": [0.0, 0.5],
    "lclouds-surface": [10, 20],
}
WINDY_WAVE = {
    "ts": [1_750_000_000_000, 1_750_003_600_000],
    "waves_height-surface": [0.8, 1.2],
    "waves_period-surface": [6.0, 7.0],
    "waves_direction-surface": [180, 190],
    "swell1_height-surface": [0.5, 0.7],
    "swell1_period-surface": [9.0, 10.0],
}


def test_windy_uv_to_speed_and_direction():
    pts = WindyProvider._parse(WINDY_WIND, WINDY_WAVE)
    assert len(pts) == 2
    # |(3,4)| = 5 m/s -> 9.7 kn
    assert pts[0].wind_speed_kn == pytest.approx(5 * 1.94384, abs=0.05)
    # from-direction of vector (u=3,v=4): 270 - deg(atan2(4,3))
    expected = (270 - math.degrees(math.atan2(4, 3))) % 360
    assert pts[0].wind_dir_deg == pytest.approx(expected, abs=0.1)
    # Kelvin -> Celsius
    assert pts[0].air_temp_c == pytest.approx(18.0, abs=0.05)
    assert pts[0].cloud_pct == 10


def test_windy_waves_merged_by_timestamp():
    pts = WindyProvider._parse(WINDY_WIND, WINDY_WAVE)
    assert pts[1].wave_height_m == 1.2
    assert pts[1].swell_period_s == 10.0


def test_windy_no_wave_model_leaves_marine_none():
    pts = WindyProvider._parse(WINDY_WIND, None)
    assert pts[0].wave_height_m is None
    assert pts[0].wind_speed_kn is not None


def test_windy_empty():
    assert WindyProvider._parse(None, None) == []
    assert WindyProvider._parse({}, None) == []


# --- UKHO -------------------------------------------------------------------

UKHO_STATIONS = {
    "features": [
        {
            "properties": {"Id": "0001", "Name": "Bournemouth"},
            "geometry": {"coordinates": [-1.876, 50.713]},
        },
        {
            "properties": {"Id": "0002", "Name": "Dover"},
            "geometry": {"coordinates": [1.313, 51.119]},
        },
    ]
}
UKHO_EVENTS = [
    {"EventType": "HighWater", "DateTime": "2026-06-23T06:30:00", "Height": 1.4},
    {"EventType": "LowWater", "DateTime": "2026-06-23T12:45:00", "Height": -0.2},
]


def test_ukho_nearest_station():
    # A coordinate next to Bournemouth must resolve to station 0001.
    assert UKHOTideProvider._nearest_station(UKHO_STATIONS, 50.72, -1.85) == "0001"
    # A coordinate near Dover resolves to 0002.
    assert UKHOTideProvider._nearest_station(UKHO_STATIONS, 51.1, 1.3) == "0002"


def test_ukho_nearest_station_empty():
    assert UKHOTideProvider._nearest_station({"features": []}, 50.0, -1.0) is None
    assert UKHOTideProvider._nearest_station(None, 50.0, -1.0) is None


def test_ukho_parse_events():
    events = UKHOTideProvider._parse_events(UKHO_EVENTS)
    assert [e.kind for e in events] == ["high", "low"]
    assert events[0].height_m == 1.4


def test_haversine_known_distance():
    # London -> Paris ~ 343 km.
    d = _haversine(51.5074, -0.1278, 48.8566, 2.3522)
    assert d == pytest.approx(343, abs=15)
