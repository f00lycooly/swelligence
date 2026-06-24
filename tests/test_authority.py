"""Unit tests for the metadata-derived authority + region/priority resolver.

Post single-source simplification the only multi-source hierarchy is TIDE
(UKHO=UK, NOAA CO-OPS=US, both rank 100, region-gated; Open-Meteo modeled tide
rank 0 global fallback). WAVE has just the keyless Open-Meteo baseline, so it
never produces a "better source" nudge — which these tests pin down.
"""

from __future__ import annotations

from swelligence.authority import (
    advice_message,
    domain_ranking,
    provider_name,
    recommend_sources,
    resolve_overlay,
)
from swelligence.providers.domains import TIDE, WAVE, WIND

# Christchurch NZ (neither), Avon Beach UK, San Diego US — to exercise gating.
NZ = (-43.5, 172.7)
UK = (50.74, -1.78)
US = (32.7, -117.2)


def _recs(sources, *, water_type="sea", coord=NZ, available):
    return recommend_sources(
        sources=sources,
        water_type=water_type,
        latitude=coord[0],
        longitude=coord[1],
        available=available,
    )


# --- "better source" nudges (now a TIDE-only hierarchy) ---------------------


def test_nudge_when_better_tide_source_configured():
    # UK spot on the modeled fallback while UKHO is configured -> nudge to UKHO.
    recs = _recs(
        {TIDE: "open_meteo_tide"}, coord=UK, available={"open_meteo_tide", "ukho"}
    )
    assert len(recs) == 1
    r = recs[0]
    assert r["domain"] == TIDE
    assert r["current"] == "open_meteo_tide" and r["suggested"] == "ukho"
    assert r["reason"]


def test_no_nudge_when_already_on_best():
    recs = _recs({TIDE: "ukho"}, coord=UK, available={"open_meteo_tide", "ukho"})
    assert recs == []


def test_no_nudge_when_better_source_not_available():
    # UKHO would be better in the UK but the user hasn't entered a key.
    recs = _recs({TIDE: "open_meteo_tide"}, coord=UK, available={"open_meteo_tide"})
    assert recs == []


def test_ukho_tide_nudge_only_in_uk():
    avail = {"open_meteo_tide", "ukho"}
    # UK spot on the fallback -> suggest UKHO.
    uk = _recs({TIDE: "open_meteo_tide"}, coord=UK, available=avail)
    assert any(r["domain"] == TIDE and r["suggested"] == "ukho" for r in uk)
    # Outside the UK, UKHO doesn't apply -> no tide nudge.
    nz = _recs({TIDE: "open_meteo_tide"}, coord=NZ, available=avail)
    assert all(r["domain"] != TIDE for r in nz)


def test_wave_has_no_better_source_so_never_nudges():
    # Open-Meteo is the only WAVE source now -> no swell nudge, ever.
    recs = _recs({WAVE: "open_meteo"}, available={"open_meteo"})
    assert all(r["domain"] != WAVE for r in recs)


def test_wind_domain_never_nudges():
    recs = _recs(
        {WIND: "open_meteo", TIDE: "ukho"}, coord=UK, available={"open_meteo", "ukho"}
    )
    assert all(r["domain"] != WIND for r in recs)


def test_unrouted_domain_is_skipped():
    # No tide source routed -> nothing to recommend.
    recs = _recs({WIND: "open_meteo"}, coord=UK, available={"open_meteo", "ukho"})
    assert recs == []


def test_advice_message_is_human_readable():
    rec = {
        "domain": TIDE,
        "current": "open_meteo_tide",
        "suggested": "ukho",
        "reason": "a regional hydrographic authority predicts tides better",
    }
    msg = advice_message(rec)
    assert "Tides" in msg
    assert "Open-Meteo" in msg and "UKHO" in msg


def test_provider_name_falls_back_to_key():
    assert provider_name("ukho") == "UKHO Admiralty"
    assert provider_name("mystery") == "mystery"


# --- resolver (region/priority overlay resolution) --------------------------


def test_domain_ranking_is_priority_ordered_and_region_gated():
    # UK: UKHO (100) > Open-Meteo modeled fallback (0).
    assert domain_ranking(TIDE, *UK) == ["ukho", "open_meteo_tide"]
    # US: NOAA CO-OPS (100) > fallback.
    assert domain_ranking(TIDE, *US) == ["noaa_coops", "open_meteo_tide"]
    # NZ: both regional authorities gated out; only the fallback remains.
    assert domain_ranking(TIDE, *NZ) == ["open_meteo_tide"]
    # WAVE: just the Open-Meteo baseline.
    assert domain_ranking(WAVE, *NZ) == ["open_meteo"]


def test_resolve_overlay_picks_region_authority_then_falls_back():
    avail = {"open_meteo_tide", "ukho", "noaa_coops"}
    assert resolve_overlay(TIDE, *UK, available=avail) == "ukho"
    assert resolve_overlay(TIDE, *US, available=avail) == "noaa_coops"
    # Outside both regions -> the keyless modeled fallback.
    assert resolve_overlay(TIDE, *NZ, available=avail) == "open_meteo_tide"


def test_resolve_overlay_respects_availability():
    # UKHO authoritative in the UK but not configured -> fall to the modeled tide.
    assert resolve_overlay(TIDE, *UK, available={"open_meteo_tide"}) == "open_meteo_tide"
    # Nothing available -> None (no source to attach).
    assert resolve_overlay(TIDE, *UK, available=set()) is None


def test_resolve_overlay_unranked_domain_is_none():
    # No provider declares wind authority -> nothing to resolve.
    assert resolve_overlay(WIND, *UK, available={"open_meteo"}) is None


def test_modeled_tide_is_the_keyless_global_fallback():
    # Nothing keyed available anywhere -> the priority-0 Open-Meteo modeled tide
    # is the resolved source, so every spot gets indicative tides with no config.
    assert resolve_overlay(TIDE, *NZ, available={"open_meteo_tide"}) == "open_meteo_tide"
    assert resolve_overlay(TIDE, *UK, available={"open_meteo_tide"}) == "open_meteo_tide"
    # But a configured regional authority still outranks it.
    assert resolve_overlay(TIDE, *UK, available={"open_meteo_tide", "ukho"}) == "ukho"
