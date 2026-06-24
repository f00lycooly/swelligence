"""Unit tests for the tide-provider normalisers (no network).

UKHO, NOAA CO-OPS, and the Open-Meteo modeled fallback factor their parsing into
pure static helpers so nearest-station logic and event derivation are testable
without live API calls.
"""

from __future__ import annotations

import pytest

from datetime import timezone

from swelligence.geo import haversine_km as _haversine
from swelligence.providers.noaa_coops import NOAACoopsTideProvider
from swelligence.providers.open_meteo import _derive_tide_extremes
from swelligence.providers.ukho import UKHOTideProvider


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


# --- NOAA CO-OPS ------------------------------------------------------------

COOPS_STATIONS = {
    "stations": [
        {"id": "8443970", "name": "Boston", "lat": 42.354, "lng": -71.050},
        {"id": "9410230", "name": "La Jolla", "lat": 32.867, "lng": -117.257},
    ]
}
COOPS_PREDICTIONS = {
    "predictions": [
        {"t": "2026-06-24 05:30", "v": "1.234", "type": "H"},
        {"t": "2026-06-24 11:45", "v": "-0.150", "type": "L"},
    ]
}


def test_coops_nearest_station():
    # Near San Diego -> La Jolla; near Massachusetts -> Boston.
    assert NOAACoopsTideProvider._nearest_station(COOPS_STATIONS, 32.7, -117.2) == "9410230"
    assert NOAACoopsTideProvider._nearest_station(COOPS_STATIONS, 42.3, -71.0) == "8443970"
    assert NOAACoopsTideProvider._nearest_station({"stations": []}, 0, 0) is None
    assert NOAACoopsTideProvider._nearest_station(None, 0, 0) is None


def test_coops_parse_predictions():
    events = NOAACoopsTideProvider._parse_predictions(COOPS_PREDICTIONS)
    assert [e.kind for e in events] == ["high", "low"]
    assert events[0].height_m == 1.234
    assert events[0].time.hour == 5 and events[0].time.tzinfo == timezone.utc
    assert events[1].height_m == -0.15
    assert NOAACoopsTideProvider._parse_predictions(None) == []
    # An error payload (no 'predictions') yields no events, not a crash.
    assert NOAACoopsTideProvider._parse_predictions({"error": {"message": "x"}}) == []


def test_coops_covers_us_only():
    assert NOAACoopsTideProvider.covers(32.7, -117.2)  # San Diego
    assert NOAACoopsTideProvider.covers(21.3, -157.8)  # Honolulu
    assert NOAACoopsTideProvider.covers(61.2, -149.9)  # Anchorage
    assert not NOAACoopsTideProvider.covers(50.74, -1.78)  # UK
    assert not NOAACoopsTideProvider.covers(-43.5, 172.7)  # NZ


# --- Open-Meteo modeled tide fallback ---------------------------------------

_SEA_LEVEL_TIMES = [
    "2026-06-24T00:00",
    "2026-06-24T01:00",
    "2026-06-24T02:00",
    "2026-06-24T03:00",
    "2026-06-24T04:00",
]


def test_derive_tide_extremes_finds_turning_points():
    # rises to a high at 01:00, falls to a low at 03:00.
    events = _derive_tide_extremes(_SEA_LEVEL_TIMES, [0.1, 0.6, 0.2, -0.4, 0.0])
    assert [e.kind for e in events] == ["high", "low"]
    assert events[0].height_m == 0.6
    assert events[0].time.hour == 1 and events[0].time.tzinfo == timezone.utc
    assert events[1].height_m == -0.4 and events[1].time.hour == 3


def test_derive_tide_extremes_skips_nones_and_endpoints():
    # A None in the series is skipped; endpoints are never turning points.
    events = _derive_tide_extremes(_SEA_LEVEL_TIMES, [0.6, None, 0.2, -0.4, 0.0])
    assert [e.kind for e in events] == ["low"]  # only the 03:00 trough survives
    assert _derive_tide_extremes([], []) == []


def test_haversine_known_distance():
    # London -> Paris ~ 343 km.
    d = _haversine(51.5074, -0.1278, 48.8566, 2.3522)
    assert d == pytest.approx(343, abs=15)
