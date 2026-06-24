"""Unit tests for geocoding normalisation + query routing (no network)."""

from __future__ import annotations

from swelligence.geocoding import (
    _UK_OUTCODE,
    _UK_POSTCODE,
    GeocodeResult,
    _parse,
    _parse_postcode,
)

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


# --- UK postcode routing + parsing -------------------------------------------

def test_uk_postcode_and_outcode_patterns():
    # Full postcodes (with/without the inner space) -> postcode regex.
    for pc in ("BH23 4AA", "BH234AA", "SW1A 1AA", "M1 1AE"):
        assert _UK_POSTCODE.match(pc), pc
    # Outcodes -> outcode regex but NOT the full-postcode regex.
    for oc in ("BH6", "SW1A", "M1"):
        assert _UK_OUTCODE.match(oc) and not _UK_POSTCODE.match(oc), oc
    # Plain place names match neither (route to Open-Meteo).
    for name in ("Mudeford", "Avon Beach", "Christchurch Dorset"):
        assert not _UK_POSTCODE.match(name) and not _UK_OUTCODE.match(name), name


def test_parse_postcode_full():
    # postcodes.io /postcodes/{pc} shape: string admin_district/country.
    payload = {
        "result": {
            "postcode": "BH6 4AA",
            "latitude": 50.72,
            "longitude": -1.83,
            "admin_district": "Bournemouth, Christchurch and Poole",
            "country": "England",
        }
    }
    [r] = _parse_postcode(payload)
    assert r.name == "BH6 4AA"
    assert (r.latitude, r.longitude) == (50.72, -1.83)
    assert r.admin1 == "Bournemouth, Christchurch and Poole"
    assert r.country == "England"


def test_parse_postcode_outcode_list_fields():
    # /outcodes/{oc} shape: admin_district/country are LISTS.
    payload = {
        "result": {
            "outcode": "BH6",
            "latitude": 50.7276,
            "longitude": -1.802,
            "admin_district": ["Bournemouth, Christchurch and Poole"],
            "country": ["England"],
        }
    }
    [r] = _parse_postcode(payload)
    assert r.name == "BH6"
    assert r.admin1 == "Bournemouth, Christchurch and Poole"
    assert r.country == "England"


def test_parse_postcode_empty_or_404():
    assert _parse_postcode(None) == []
    assert _parse_postcode({}) == []
    assert _parse_postcode({"result": None}) == []
    assert _parse_postcode({"result": {"postcode": "X"}}) == []  # no coords
