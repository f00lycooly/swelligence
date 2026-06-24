"""Forecast data domains — the unit of source provenance and (later) merging.

A *domain* is a group of related :class:`ForecastPoint` fields that a single
provider typically supplies together (wind, waves, etc.). Provenance records
which provider supplied each domain in ``SpotForecast.source_meta['sources']``;
the composite-merge layer (epic al8) routes and coalesces per domain using this
same taxonomy, so the field grouping lives in exactly one place.

Pure module (no Home Assistant imports) so providers, the coordinator, and the
standalone validation scripts share it.
"""

from __future__ import annotations

WIND = "wind"
WAVE = "wave"
WATER = "water"  # sea-surface temperature / sea level
AIR = "air"  # air temp, precipitation, cloud
TIDE = "tide"  # high/low water events (SpotForecast.tide_events)

DOMAINS: tuple[str, ...] = (WIND, WAVE, WATER, AIR, TIDE)

# Domain -> the ForecastPoint fields it covers. TIDE has no point fields; it
# lives on SpotForecast.tide_events (and sea_level_m, grouped under WATER).
DOMAIN_FIELDS: dict[str, tuple[str, ...]] = {
    WIND: ("wind_speed_kn", "wind_gust_kn", "wind_dir_deg"),
    WAVE: (
        "wave_height_m",
        "wave_period_s",
        "wave_dir_deg",
        "swell_height_m",
        "swell_period_s",
        "swell_dir_deg",
        "swell_peak_period_s",
        "wind_wave_height_m",
        "wind_wave_period_s",
        "secondary_swell_height_m",
        "secondary_swell_period_s",
        "secondary_swell_dir_deg",
    ),
    WATER: ("water_temp_c", "sea_level_m", "current_speed_kn", "current_dir_deg"),
    AIR: (
        "air_temp_c",
        "apparent_temp_c",
        "precip_mm",
        "cloud_pct",
        "uv_index",
        "visibility_m",
        "weather_code",
    ),
}

# Marine-only domains — skipped for inland / no-marine spots.
MARINE_DOMAINS: frozenset[str] = frozenset({WAVE, WATER, TIDE})


def assert_legal_domains(keys, *, where: str = "") -> None:
    """Raise if any of ``keys`` is not a legal domain.

    The single legality checker for anything keyed by domain — provider
    ``provides_domains`` / ``authority_rank``, the authority reason/label maps,
    etc. Use the module constants (:data:`WIND`, :data:`TIDE`, …) rather than
    bare strings; this guard exists to catch the times that doesn't happen.
    """
    illegal = sorted(k for k in keys if k not in DOMAINS)
    if illegal:
        ctx = f" in {where}" if where else ""
        raise ValueError(
            f"Illegal domain(s){ctx}: {illegal!r}. Legal domains: {list(DOMAINS)!r}"
        )


def stamp_sources(forecast, provider_key: str, domains) -> None:
    """Record ``provider_key`` as the source of each given domain.

    Writes into ``forecast.source_meta['sources']`` (creating it if absent),
    overwriting any prior attribution for those domains — so the merge layer can
    re-stamp a domain when a later overlay supplies it.
    """
    sources = forecast.source_meta.setdefault("sources", {})
    for domain in domains:
        sources[domain] = provider_key
