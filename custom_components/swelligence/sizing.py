"""Rider sizing model — weight + wind -> ideal kite/wing size, and a quiver-aware
kit recommendation.

Pure, calibratable, no I/O. The relationship is the standard inverse model:

    ideal_size_m2 ~= constant * rider_weight_kg / wind_kn

with constants tuned so a typical rider lands on sensible sizes (an 80 kg rider:
~9 m² kite at 20 kn, ~15 m² at 12 kn, ~6 m² at 30 kn; ~5 m² wing at 16 kn). The
constants are defaults — callers may pass overrides once per-rider calibration
exists. Only kitesurf and wing foil are sized in v1; other sports return a
neutral ("n/a") recommendation so they're unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass

# Calibratable model constants (see module docstring for the sanity checks).
KITE_CONSTANT = 2.25
WING_CONSTANT = 1.0

# Sizes within this fractional deviation of ideal are treated as "ideal".
_IDEAL_BAND = 0.12
# Deviation at which the power-match factor reaches 0.
_TOLERANCE = 0.40

# Sports that have a wind/weight size model.
SIZED_SPORTS = {"kitesurf": KITE_CONSTANT, "wingfoil": WING_CONSTANT}

# Power verdicts.
POWER_IDEAL = "ideal"
POWER_UNDER = "underpowered"
POWER_OVER = "overpowered"
POWER_NO_KIT = "no_kit"
POWER_NA = "n/a"


@dataclass(slots=True)
class KitRecommendation:
    """The kit advice for one sized sport at a given wind."""

    sport: str
    ideal_size_m2: float | None
    owned_size_m2: float | None
    power: str
    factor: float  # 0..1 power-match factor (1.0 = perfectly rigged / n/a)
    summary: str


def ideal_size(
    sport: str,
    weight_kg: float,
    wind_kn: float | None,
    *,
    constants: dict[str, float] | None = None,
) -> float | None:
    """Ideal kit size (m²) for the sport, rider weight and wind. None if the
    sport isn't sized or there's no usable wind/weight."""
    const_map = {**SIZED_SPORTS, **(constants or {})}
    c = const_map.get(sport)
    if c is None or not wind_kn or wind_kn <= 0 or weight_kg <= 0:
        return None
    return round(c * weight_kg / wind_kn, 1)


def recommend_kit(
    sport: str,
    weight_kg: float,
    wind_kn: float | None,
    quiver: list[float] | None,
    *,
    constants: dict[str, float] | None = None,
) -> KitRecommendation:
    """Pick the best owned size for the conditions and rate the power match."""
    ideal = ideal_size(sport, weight_kg, wind_kn, constants=constants)
    if ideal is None:
        # Not a sized sport (or no usable wind) -> neutral, no effect on score.
        return KitRecommendation(sport, None, None, POWER_NA, 1.0, "")

    if not quiver:
        return KitRecommendation(
            sport, ideal, None, POWER_NO_KIT, 0.0,
            f"no kit configured (ideal ~{ideal:g}m²)",
        )

    nearest = min(quiver, key=lambda s: abs(s - ideal))
    deviation = abs(nearest / ideal - 1.0)
    factor = round(max(0.0, 1.0 - deviation / _TOLERANCE), 2)

    if deviation <= _IDEAL_BAND:
        power = POWER_IDEAL
        summary = f"rig your {nearest:g}m² (ideal ~{ideal:g}m²)"
    elif nearest > ideal:
        power = POWER_OVER
        summary = f"overpowered on your {nearest:g}m² (ideal ~{ideal:g}m²)"
    else:
        power = POWER_UNDER
        summary = f"underpowered on your {nearest:g}m² (ideal ~{ideal:g}m²)"

    return KitRecommendation(sport, ideal, nearest, power, factor, summary)
