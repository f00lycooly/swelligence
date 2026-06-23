"""Unit tests for Open-Meteo geocoding normalisation (no network)."""

from __future__ import annotations

from swelligence.geocoding import GeocodeResult, _parse

PAYLOAD = {
    "results": [
        {
            "name": "Christchurch",
            "latitude": 50.73583,
            "longitude": -1.78972,
            "country": "United Kingdom",
            "admin1": "England",
        },
        {
            "name": "Christchurch",
            "latitude": -43.53333,
            "longitude": 172.63333,
            "country": "New Zealand",
            "admin1": "Canterbury",
        },
        {"name": "NoCoords"},  # dropped: missing lat/lon
    ]
}


def test_parse_drops_results_without_coordinates():
    results = _parse(PAYLOAD)
    assert len(results) == 2
    assert all(isinstance(r, GeocodeResult) for r in results)
    assert results[0].latitude == 50.73583
    assert results[1].country == "New Zealand"


def test_parse_handles_empty_or_missing():
    assert _parse(None) == []
    assert _parse({}) == []
    assert _parse({"results": None}) == []


def test_label_disambiguates():
    r = _parse(PAYLOAD)[0]
    assert r.label == "Christchurch, England, United Kingdom"


def test_label_skips_redundant_admin1():
    r = GeocodeResult(name="Dorset", latitude=1.0, longitude=2.0, admin1="Dorset")
    assert r.label == "Dorset"
