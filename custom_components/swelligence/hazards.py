"""Weather safety hazards — pure, config-driven gate signals.

Evaluated per :class:`ForecastPoint` (same granularity as the tide gate). Each
active hazard carries a *tier*: ``hard`` (the scorer caps the slot to "poor" /
not-suitable), ``warn`` (advisory only, surfaced on the card/panel) or ``off``
(never produced). Thresholds are fixed constants except the squall gust, which
the options flow exposes via a Beaufort dropdown.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tiers (string values are what the options flow stores).
TIER_OFF = "off"
TIER_WARN = "warn"
TIER_HARD = "hard"

# Hazard kinds.
THUNDERSTORM = "thunderstorm"
FOG = "fog"
SQUALL = "squall"
HEAVY_RAIN = "heavy_rain"

# Fixed thresholds (v1). Only the squall gust is user-tunable (Beaufort).
THUNDER_WEATHER_CODES = frozenset({95, 96, 99})
THUNDER_CAPE_JKG = 1000.0
FOG_VISIBILITY_M = 1000.0
HEAVY_RAIN_MM = 7.5
DEFAULT_SQUALL_GUST_KN = 34.0  # Beaufort Force 8 (gale)


@dataclass(slots=True)
class Hazard:
    """One active weather hazard at a timestep."""

    kind: str
    tier: str
    reason: str


@dataclass(slots=True)
class HazardConfig:
    """Per-hazard tier + the tunable squall gust threshold (knots)."""

    thunderstorm: str = TIER_HARD
    fog: str = TIER_WARN
    squall: str = TIER_WARN
    heavy_rain: str = TIER_WARN
    squall_gust_kn: float = DEFAULT_SQUALL_GUST_KN


def _is_thunderstorm(point) -> bool:
    code = point.weather_code
    if code is not None and int(code) in THUNDER_WEATHER_CODES:
        return True
    cape = point.cape_jkg
    return cape is not None and cape > THUNDER_CAPE_JKG


def evaluate_hazards(point, config: HazardConfig) -> list[Hazard]:
    """Active hazards for one forecast point under ``config`` (empty if none).

    A ``None`` field never triggers (unknown is not a hazard). ``off``-tier
    hazards are never produced.
    """
    out: list[Hazard] = []
    if config.thunderstorm != TIER_OFF and _is_thunderstorm(point):
        out.append(Hazard(THUNDERSTORM, config.thunderstorm, "thunderstorm risk"))
    if (
        config.fog != TIER_OFF
        and point.visibility_m is not None
        and point.visibility_m < FOG_VISIBILITY_M
    ):
        out.append(Hazard(FOG, config.fog, f"low visibility ({point.visibility_m:.0f}m)"))
    if (
        config.squall != TIER_OFF
        and point.wind_gust_kn is not None
        and point.wind_gust_kn >= config.squall_gust_kn
    ):
        out.append(Hazard(SQUALL, config.squall, f"violent gusts ({point.wind_gust_kn:.0f}kn)"))
    if (
        config.heavy_rain != TIER_OFF
        and point.precip_mm is not None
        and point.precip_mm >= HEAVY_RAIN_MM
    ):
        out.append(Hazard(HEAVY_RAIN, config.heavy_rain, f"heavy rain ({point.precip_mm:.1f}mm)"))
    return out


def has_hard(hazards) -> bool:
    """Whether any hazard in the list is hard-tier."""
    return any(h.tier == TIER_HARD for h in (hazards or []))
