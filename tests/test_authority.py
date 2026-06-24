"""Unit tests for the provider-authority map + nudges (o07.4)."""

from __future__ import annotations

from swelligence.authority import (
    advice_message,
    domain_ranking,
    provider_name,
    recommend_sources,
    resolve_overlay,
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


def test_stormglass_beats_open_meteo_for_waves():
    # Stormglass configured on a sea spot routing waves to Open-Meteo -> suggest it.
    recs = _recs({WAVE: "open_meteo"}, available={"open_meteo", "stormglass"})
    assert recs[0]["suggested"] == "stormglass"


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
        available={"open_meteo", "stormglass"},
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


# --- resolver (region/priority overlay resolution) --------------------------


def test_resolve_overlay_picks_region_authority_then_falls_back():
    avail = {"open_meteo", "stormglass", "ukho"}
    # In the UK, UKHO (rank 100, UK-gated) wins for tides.
    assert resolve_overlay(TIDE, *UK, available=avail) == "ukho"
    # Outside the UK, UKHO doesn't cover -> global Stormglass (rank 50) wins.
    assert resolve_overlay(TIDE, *NZ, available=avail) == "stormglass"


def test_resolve_overlay_respects_availability():
    # UKHO authoritative in the UK but not configured -> fall to Stormglass.
    assert resolve_overlay(TIDE, *UK, available={"stormglass"}) == "stormglass"
    # Nothing available -> None (no source to attach).
    assert resolve_overlay(TIDE, *UK, available=set()) is None


def test_resolve_overlay_unranked_domain_is_none():
    # No provider declares wind authority -> nothing to resolve.
    assert resolve_overlay(WIND, *UK, available={"open_meteo", "stormglass"}) is None


def test_domain_ranking_is_priority_ordered_and_region_gated():
    assert domain_ranking(TIDE, *UK) == ["ukho", "stormglass"]  # UK: both, UKHO first
    assert domain_ranking(TIDE, *NZ) == ["stormglass"]  # NZ: UKHO gated out
    assert domain_ranking(WAVE, *NZ) == ["stormglass", "open_meteo"]  # rank 50 > 0
