"""Unit tests for the data-domain taxonomy and per-domain source provenance."""

from __future__ import annotations

from datetime import datetime

import pytest

from swelligence.providers import PROVIDERS, TIDE_PROVIDERS
from swelligence.providers.base import SpotForecast, TideEvent
from swelligence.providers.domains import (
    AIR,
    DOMAIN_FIELDS,
    DOMAINS,
    TIDE,
    WATER,
    WAVE,
    WIND,
    assert_legal_domains,
    stamp_sources,
)
from swelligence.providers.open_meteo import OpenMeteoProvider


def _forecast(**kw) -> SpotForecast:
    return SpotForecast(provider="x", latitude=0.0, longitude=0.0, **kw)


def test_stamp_sources_writes_per_domain():
    fc = _forecast()
    stamp_sources(fc, "open_meteo", {WIND, AIR})
    assert fc.source_meta["sources"] == {"wind": "open_meteo", "air": "open_meteo"}


def test_stamp_sources_overwrites_for_overlay():
    fc = _forecast()
    stamp_sources(fc, "open_meteo", {WIND, WAVE})
    stamp_sources(fc, "overlay", {WAVE})  # an overlay re-stamps just waves
    assert fc.source_meta["sources"] == {"wind": "open_meteo", "wave": "overlay"}


def test_assert_legal_domains_accepts_legal_and_rejects_illegal():
    assert_legal_domains([WIND, TIDE])  # no raise
    assert_legal_domains({WAVE: 1, WATER: 2})  # dict keys are iterated
    with pytest.raises(ValueError, match="tides"):  # bare-string typo for TIDE
        assert_legal_domains(["wind", "tides"], where="oops")


def test_every_registered_provider_declares_only_legal_domains():
    # The legality gate enforced at the registry — assert it holds for all
    # providers so a bad domain key on any provider fails this test, not prod.
    for key, cls in {**PROVIDERS, **TIDE_PROVIDERS}.items():
        assert_legal_domains(
            getattr(cls, "provides_domains", frozenset()), where=f"{key}.provides_domains"
        )
        assert_legal_domains(cls.authority_rank, where=f"{key}.authority_rank")


def test_domain_fields_cover_known_point_fields():
    flat = [f for fields in DOMAIN_FIELDS.values() for f in fields]
    assert "wind_speed_kn" in flat and "swell_height_m" in flat
    assert len(flat) == len(set(flat))  # no field claimed by two domains
    assert TIDE in DOMAINS and TIDE not in DOMAIN_FIELDS  # tide has no point fields


def test_open_meteo_marine_stamps_all_non_tide():
    p = OpenMeteoProvider(None)
    fc = _forecast()
    p._stamp_sources(fc, marine=True)
    assert set(fc.source_meta["sources"]) == {WIND, AIR, WAVE, WATER}


def test_open_meteo_inland_only_wind_air():
    p = OpenMeteoProvider(None)
    fc = _forecast()
    p._stamp_sources(fc, marine=False)
    assert set(fc.source_meta["sources"]) == {WIND, AIR}


def test_stamp_sources_discards_tide_without_events():
    # _stamp_sources drops a claimed TIDE domain unless tide events exist.
    class _TideyForecaster(OpenMeteoProvider):
        provides_domains = frozenset({WIND, AIR, WAVE, WATER, TIDE})

    p = _TideyForecaster(None)
    no_tide = _forecast()
    p._stamp_sources(no_tide, marine=True)
    assert TIDE not in no_tide.source_meta["sources"]

    with_tide = _forecast(
        tide_events=[TideEvent(time=datetime(2026, 6, 23, 6), kind="high", height_m=1.2)]
    )
    p._stamp_sources(with_tide, marine=True)
    assert set(with_tide.source_meta["sources"]) == {WIND, AIR, WAVE, WATER, TIDE}
