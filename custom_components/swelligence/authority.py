"""Provider authority resolution + 'better source available' nudges.

The suitability score says how good conditions are; it cannot say whether a spot
is even *listening to the best source* for each domain. Some providers are
authoritative for some data: UKHO Admiralty (UK) and NOAA CO-OPS (US) give
harmonic tides where the modeled fallback is only indicative; for wind/waves,
Open-Meteo is the source.

That ranking is **not** hardcoded here. Each provider *declares* the domains it
is an authority for (``authority_rank``) and the region it covers (``covers``);
this module just scans the registries and ranks. So adding a provider — UKHO,
NOAA CO-OPS, WorldTides, a future swell service — is a declaration on the
provider class plus a registry entry, never an edit to a table in this file.

Two consumers share the derived ranking:

* :func:`resolve_overlay` — pick the single best *available* source for a domain
  at a coordinate (used by the coordinator to auto-attach the right tide source
  by region, with no manual per-spot selection).
* :func:`recommend_sources` — emit an actionable nudge when a strictly better,
  configured source is sitting unused for a domain the spot already routes.

Pure module (no Home Assistant / I/O) so the coordinator, the diagnostic sensor,
the overview service, and the validation scripts share one implementation.
"""

from __future__ import annotations

from .providers import PROVIDERS, TIDE_PROVIDERS
from .providers.domains import DOMAINS, TIDE, WATER, WAVE, assert_legal_domains

# Domains whose source only matters on the open coast — sheltered/inland spots
# have marine suppressed, so a swell/sea-temp source choice is moot there.
_SEA_ONLY_DOMAINS = frozenset({WAVE, WATER})

# Why a domain's nudge fires — surfaced verbatim to the user. Keyed by domain
# (not provider), so it needs no edit when providers are added.
_REASONS: dict[str, str] = {
    WAVE: (
        "keyed marine models resolve exposed-coast swell better than "
        "Open-Meteo's nearest-coastal grid"
    ),
    TIDE: "a regional hydrographic authority predicts tides better than a model",
}

# Short, friendly names for the nudge text. Optional: a provider absent here
# falls back to its registry key, so this never blocks adding a provider.
_PROVIDER_NAMES: dict[str, str] = {
    "open_meteo": "Open-Meteo",
    "open_meteo_tide": "Open-Meteo (modeled)",
    "ukho": "UKHO Admiralty",
    "noaa_coops": "NOAA CO-OPS",
    "worldtides": "WorldTides",
}
_DOMAIN_LABELS: dict[str, str] = {WAVE: "Swell/waves", TIDE: "Tides"}

# Legality guard for the domain-keyed maps in this module (catches bare-string
# domain keys at import, the very mistake the constants exist to prevent).
assert_legal_domains(_REASONS, where="authority._REASONS")
assert_legal_domains(_DOMAIN_LABELS, where="authority._DOMAIN_LABELS")


def _all_providers() -> dict[str, type]:
    """Every registered provider class, keyed by registry key (deduped).

    A class registered in both the forecast and tide registries appears once.
    Reading from the live registries is what makes authority self-updating as
    providers are registered or removed.
    """
    merged: dict[str, type] = {}
    merged.update(TIDE_PROVIDERS)
    merged.update(PROVIDERS)
    return merged


def domain_ranking(domain: str, latitude: float, longitude: float) -> list[str]:
    """Provider keys that are an authority for ``domain`` at a coordinate.

    Best-first by declared ``authority_rank[domain]``; region-gated by each
    provider's ``covers``. Empty when no provider claims authority for the domain
    there (e.g. wind/air, or tides outside any covered region).
    """
    cands: list[tuple[int, str]] = []
    for key, cls in _all_providers().items():
        rank = cls.authority_rank.get(domain)
        if rank is None:
            continue
        if not cls.covers(latitude, longitude):
            continue
        cands.append((rank, key))
    # rank desc; key as a stable tiebreak so output is deterministic.
    cands.sort(key=lambda rk: (-rk[0], rk[1]))
    return [key for _, key in cands]


def resolve_overlay(
    domain: str,
    latitude: float,
    longitude: float,
    *,
    available: set[str],
) -> str | None:
    """Best *available* source for a domain at a coordinate, or ``None``.

    ``available`` is the set of provider keys usable here (keyless providers
    always; keyed ones only when configured). This is the wiring point: the
    coordinator calls it to attach the right tide source by region without any
    hardcoded provider choice.
    """
    for key in domain_ranking(domain, latitude, longitude):
        if key in available:
            return key
    return None


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
    for domain in DOMAINS:
        current = (sources or {}).get(domain)
        if not current:
            continue  # domain not supplied for this spot -> nothing to improve
        if domain in _SEA_ONLY_DOMAINS and water_type != "sea":
            continue  # swell/sea-temp source is moot off the open coast
        order = domain_ranking(domain, latitude, longitude)
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
