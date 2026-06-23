"""Pure marine-overlay merge — coalesce one provider's marine fields onto another.

Lets a keyless base (Open-Meteo) keep wind/air while a keyed source (Stormglass)
supplies waves/swell/sea-temperature where the base has none ("gap-fill") or
always ("prefer", for quality). The merge aligns by timestamp across the two
providers' different timezone conventions (base naive-local vs overlay UTC) via
:func:`to_utc_naive`, and returns which fields it filled so the caller can stamp
per-domain provenance (epic al8). No Home Assistant / I/O.
"""

from __future__ import annotations

from .providers.domains import DOMAIN_FIELDS, WATER, WAVE
from .tide import to_utc_naive

# Marine fields the overlay may supply. sea_level_m (also under WATER) is left to
# the tide layer, so only wave/swell + sea-surface temperature are merged here.
MARINE_FIELDS: tuple[str, ...] = (*DOMAIN_FIELDS[WAVE], "water_temp_c")


def merge_marine(
    base_points,
    overlay_points,
    *,
    prefer: bool = False,
    base_offset_seconds: int = 0,
) -> set[str]:
    """Merge overlay marine fields onto ``base_points`` in place, by timestamp.

    ``prefer`` replaces existing base values; otherwise only ``None`` (missing)
    base fields are filled. Returns the set of field names actually written.
    """
    index = {to_utc_naive(p.time): p for p in overlay_points}
    filled: set[str] = set()
    for bp in base_points:
        op = index.get(to_utc_naive(bp.time, local_offset_seconds=base_offset_seconds))
        if op is None:
            continue
        for field in MARINE_FIELDS:
            value = getattr(op, field, None)
            if value is None:
                continue
            if prefer or getattr(bp, field, None) is None:
                setattr(bp, field, value)
                filled.add(field)
    return filled


def resolve_route(spot_value, entry_value):
    """Resolve a per-spot source override against the entry-level default.

    A spot value of ``None``/``""``/``"inherit"`` falls through to the
    entry-level (global) setting; any other value (a provider key or ``"none"``)
    overrides it. This is how per-spot, per-domain source routing composes on top
    of the global overlay configuration.
    """
    if spot_value in (None, "", "inherit"):
        return entry_value
    return spot_value


def filled_domains(filled: set[str]) -> set[str]:
    """Map merged field names back to their provenance domains."""
    domains: set[str] = set()
    if any(f in DOMAIN_FIELDS[WAVE] for f in filled):
        domains.add(WAVE)
    if "water_temp_c" in filled:
        domains.add(WATER)
    return domains
