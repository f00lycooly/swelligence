"""Unit tests for the provider-authority map + nudges (o07.4)."""

from __future__ import annotations

from swelligence.authority import (
    advice_message,
    provider_name,
    recommend_sources,
)
from swelligence.providers.domains import TIDE, WAVE, WIND

# Christchurch, NZ (not UK) and Avon Beach, UK — to exercise region gating.
NZ = (-43.5, 172.7)
UK = (50.74, -1.78)


def _recs(sources, *, water_type="sea", coord=NZ, available):
    return recommend_sources(
        sources=sources,
        water_type=water_type,
        latitude=coord[0],
        longitude=coord[1],
        available=available,
    )


def test_nudge_when_better_marine_source_configured():
    # Swell on Open-Meteo while Stormglass is configured -> nudge.
    recs = _recs({WAVE: "open_meteo"}, available={"open_meteo", "stormglass"})
    assert len(recs) == 1
    r = recs[0]
    assert r["domain"] == WAVE
    assert r["current"] == "open_meteo" and r["suggested"] == "stormglass"
    assert r["reason"]


def test_no_nudge_when_already_on_best():
    recs = _recs({WAVE: "stormglass"}, available={"open_meteo", "stormglass"})
    assert recs == []


def test_no_nudge_when_better_source_not_available():
    # Stormglass would be better but the user hasn't configured it.
    recs = _recs({WAVE: "open_meteo"}, available={"open_meteo"})
    assert recs == []


def test_wave_nudge_suppressed_for_non_sea_spot():
    recs = _recs(
        {WAVE: "open_meteo"},
        water_type="inland",
        available={"open_meteo", "stormglass"},
    )
    assert recs == []


def test_windy_beats_open_meteo_but_loses_to_stormglass():
    # Only Windy configured -> suggest Windy.
    recs = _recs({WAVE: "open_meteo"}, available={"open_meteo", "windy"})
    assert recs[0]["suggested"] == "windy"
    # Both keyed configured -> Stormglass wins (higher authority).
    recs2 = _recs(
        {WAVE: "open_meteo"}, available={"open_meteo", "windy", "stormglass"}
    )
    assert recs2[0]["suggested"] == "stormglass"


def test_ukho_tide_nudge_only_in_uk():
    avail = {"open_meteo", "stormglass", "ukho"}
    # UK spot routing tide to Stormglass -> suggest UKHO.
    uk = _recs({TIDE: "stormglass"}, coord=UK, available=avail)
    assert any(r["domain"] == TIDE and r["suggested"] == "ukho" for r in uk)
    # Same routing outside the UK -> UKHO doesn't apply, no tide nudge.
    nz = _recs({TIDE: "stormglass"}, coord=NZ, available=avail)
    assert all(r["domain"] != TIDE for r in nz)


def test_wind_domain_never_nudges():
    recs = _recs(
        {WIND: "open_meteo", WAVE: "stormglass"},
        available={"open_meteo", "stormglass", "windy"},
    )
    assert all(r["domain"] != WIND for r in recs)


def test_unrouted_domain_is_skipped():
    # No wave source at all (e.g. marine unavailable) -> nothing to recommend.
    recs = _recs({WIND: "open_meteo"}, available={"open_meteo", "stormglass"})
    assert recs == []


def test_advice_message_is_human_readable():
    rec = {
        "domain": WAVE,
        "current": "open_meteo",
        "suggested": "stormglass",
        "reason": "keyed marine models resolve exposed-coast swell better",
    }
    msg = advice_message(rec)
    assert "Swell/waves" in msg
    assert "Open-Meteo" in msg and "Stormglass" in msg


def test_provider_name_falls_back_to_key():
    assert provider_name("stormglass") == "Stormglass"
    assert provider_name("mystery") == "mystery"
