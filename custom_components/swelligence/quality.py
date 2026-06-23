"""Per-(spot, sport) data-quality summary.

The scorer treats any missing :class:`ForecastPoint` field as "unknown" and
silently drops that factor from the weighted mean — so a great-looking score can
rest on thin data (no swell period, the marine grid unavailable, a coarse cell
far offshore). This module turns the provenance already carried on a
``SpotForecast`` — ``source_meta['sources']`` (al8.1 per-domain attribution), the
marine/water-policy notes, the grid-cell offset, and per-point field presence —
into a compact, *sport-aware* quality note. Each suitability sensor can then say
what is thin or missing for that exact (spot, sport), rather than burying it.

Pure module (no Home Assistant imports) so the sensor layer, the overview
aggregation, and the standalone validation scripts share one implementation.
"""

from __future__ import annotations

from .providers.domains import WATER, WAVE, WIND
from .sports import SportProfile

#: A grid cell at least this far from the spot is flagged as a quality concern
#: (Open-Meteo's marine grid can snap several km offshore).
COARSE_GRID_KM = 8.0


def _source_of(forecast, domain: str) -> str | None:
    """The provider attributed to ``domain`` in al8.1 provenance, if any."""
    return (forecast.source_meta.get("sources") or {}).get(domain)


def data_quality(forecast, profile: SportProfile) -> dict:
    """Summarise data availability/quality for one sport at a spot.

    Returns ``{"summary": str, "issues": [str, ...]}`` and, where the provider
    reported it, ``"grid_distance_km": float``. ``summary`` is a one-line,
    human-readable note naming the source and any gaps for each domain the sport
    actually scores on; ``issues`` is the machine-readable list of concerns
    (empty when the data backing this score is complete).
    """
    point = forecast.current()
    meta = forecast.source_meta
    parts: list[str] = []
    issues: list[str] = []

    # WIND — every scored sport leans on it (speed, and optionally gust/dir).
    if profile.weight_wind or profile.weight_gust or profile.weight_dir:
        src = _source_of(forecast, WIND) or meta.get("model") or forecast.provider
        if point is None or point.wind_speed_kn is None:
            parts.append(f"wind: {src}, missing")
            issues.append("no wind data")
        elif profile.weight_dir and point.wind_dir_deg is None:
            parts.append(f"wind: {src}, no direction")
            issues.append("no wind direction")
        else:
            parts.append(f"wind: {src}")

    # WAVE / swell — only sports that score them. wave_max_m alone (flat-water
    # sports) still wants the wave field; wave_ideal_m / swell add more.
    wants_wave = bool(profile.weight_wave) and (
        profile.wave_ideal_m is not None or profile.wave_max_m is not None
    )
    wants_swell = bool(profile.weight_swell) and profile.swell_period_ideal_s is not None
    if wants_wave or wants_swell:
        src = _source_of(forecast, WAVE)
        if src is None or point is None or point.wave_height_m is None:
            note = meta.get("marine") or meta.get("water_policy") or "unavailable"
            parts.append(f"waves: {note}")
            issues.append("no wave data")
        else:
            sub = [src]
            if wants_swell:
                if point.swell_period_s is None:
                    sub.append("windsea-only")
                    issues.append("no groundswell period")
                if point.swell_dir_deg is None:
                    sub.append("no groundswell direction")
                    issues.append("no swell direction")
            label = "swell" if wants_swell else "waves"
            parts.append(f"{label}: {', '.join(sub)}")

    # WATER temperature — only temp-scored sports (e.g. sea swim).
    if profile.weight_temp and profile.water_temp_min_c is not None:
        if point is None or point.water_temp_c is None:
            parts.append("water temp: missing")
            issues.append("no water temperature")
        else:
            src = _source_of(forecast, WATER) or forecast.provider
            parts.append(f"water temp: {src}")

    out: dict = {"summary": "; ".join(parts), "issues": issues}

    dist = meta.get("grid_distance_km")
    if dist is not None:
        out["grid_distance_km"] = dist
        if dist >= COARSE_GRID_KM:
            issues.append(f"grid cell ~{dist:.0f}km from spot")

    return out
