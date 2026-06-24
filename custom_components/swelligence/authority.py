"""Per-domain provider authority and 'better source available' nudges.

The suitability score says how good conditions are; it cannot say whether a spot
is even *listening to the best source* for each domain. Some providers are
authoritative for some data: UKHO Admiralty is the gold standard for UK tides;
keyed marine models (Stormglass) resolve exposed-coast swell better than
Open-Meteo's nearest-coastal grid; for wind, Open-Meteo is perfectly fine.

This module encodes that ranking (some entries region- or water-type-gated),
compares a spot's ACTUAL routing (``source_meta['sources']`` from al8.1/al8.4)
against the best *available* (configured) source, and emits an actionable nudge
only when a strictly better source is sitting unused — never noise when the spot
is already on the best source it can reach.

Pure module (no Home Assistant / I/O) so the coordinator, the diagnostic sensor,
the overview service, and the validation scripts share one implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .providers.domains import TIDE, WAVE

# UK bounding box for region-gated authorities (UKHO is UK-only).
_UK_BBOX = (49.0, 61.0, -8.5, 2.0)  # lat_min, lat_max, lon_min, lon_max


def _in_uk(lat: float, lon: float) -> bool:
    la0, la1, lo0, lo1 = _UK_BBOX
    return la0 <= lat <= la1 and lo0 <= lon <= lo1


def _sea_only(water_type: str, lat: float, lon: float) -> bool:
    # Swell-source quality only matters on the open coast; sheltered/inland
    # spots have marine suppressed, so the routing choice is moot.
    return water_type == "sea"


def _uk_tide(water_type: str, lat: float, lon: float) -> bool:
    return _in_uk(lat, lon)


@dataclass(frozen=True)
class _Authority:
    """One ranked source for a domain, with an applicability predicate."""

    provider: str
    applies: Callable[[str, float, float], bool] = field(
        default=lambda water_type, lat, lon: True
    )


# Best-first authority per domain. Domains absent here (wind, air) have no
# meaningful source hierarchy — Open-Meteo is authoritative enough — so they
# never raise a nudge.
DOMAIN_AUTHORITY: dict[str, tuple[_Authority, ...]] = {
    WAVE: (
        _Authority("stormglass", _sea_only),
        _Authority("open_meteo", _sea_only),
    ),
    TIDE: (
        _Authority("ukho", _uk_tide),
        _Authority("stormglass"),
    ),
}

# Why a domain's nudge fires — surfaced verbatim to the user.
_REASONS: dict[str, str] = {
    WAVE: (
        "keyed marine models resolve exposed-coast swell better than "
        "Open-Meteo's nearest-coastal grid"
    ),
    TIDE: "UKHO Admiralty is the authoritative source for UK tidal predictions",
}


# Short, friendly names for the nudge text (the registry labels are verbose).
_PROVIDER_NAMES: dict[str, str] = {
    "open_meteo": "Open-Meteo",
    "stormglass": "Stormglass",
    "ukho": "UKHO Admiralty",
}
_DOMAIN_LABELS: dict[str, str] = {WAVE: "Swell/waves", TIDE: "Tides"}


def provider_name(key: str) -> str:
    """Short display name for a provider key."""
    return _PROVIDER_NAMES.get(key, key)


def advice_message(rec: dict) -> str:
    """One-line, user-facing 'better source available' nudge for a rec."""
    domain = _DOMAIN_LABELS.get(rec["domain"], rec["domain"])
    current = provider_name(rec["current"])
    suggested = provider_name(rec["suggested"])
    reason = rec.get("reason")
    tail = f" — {reason}" if reason else ""
    return f"{domain}: using {current}; {suggested} is available{tail}."


def recommend_sources(
    *,
    sources: dict[str, str] | None,
    water_type: str,
    latitude: float,
    longitude: float,
    available: set[str],
) -> list[dict]:
    """Nudges where a strictly better, *available* source exists for a domain.

    ``sources`` is the spot's actual per-domain routing. ``available`` is the set
    of provider keys the user has configured (always includes the keyless
    ``open_meteo``). Returns ``[{domain, current, suggested, reason}, ...]`` —
    empty when every routed domain is already on the best source it can reach.
    """
    recs: list[dict] = []
    for domain, ranks in DOMAIN_AUTHORITY.items():
        current = (sources or {}).get(domain)
        if not current:
            continue  # domain not supplied for this spot -> nothing to improve
        order = [
            a.provider for a in ranks if a.applies(water_type, latitude, longitude)
        ]
        if not order:
            continue
        best = next((p for p in order if p in available), None)
        if best is None:
            continue
        best_rank = order.index(best)
        cur_rank = order.index(current) if current in order else len(order)
        if best_rank < cur_rank:
            recs.append(
                {
                    "domain": domain,
                    "current": current,
                    "suggested": best,
                    "reason": _REASONS.get(domain, ""),
                }
            )
    return recs
