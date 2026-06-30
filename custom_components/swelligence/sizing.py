"""Rider sizing model — weight + wind -> ideal kite/wing size, and a quiver-aware
kit recommendation.

Pure, calibratable, no I/O. The relationship is the standard inverse model:

    ideal_size_m2 ~= constant * rider_weight_kg / wind_kn

The constants are calibrated against published manufacturer wind-range charts
(Cabrinha Moto X Lite + Cabrinha/Duotone wings) cross-checked with industry size
grids (kitesurftheworld, windance) — see
``mockups/research/kit-sizing-manufacturers.md`` for the data and the per-chart
implied-constant fit. Real charts are ~linear in 1/wind across the riding band
(n≈1–1.3); the textbook 1/wind² law over-corrects vs. what brands actually print
(depower range + kite efficiency flatten the theoretical curve), so the model
stays linear and the constant carries the calibration. The constants are
defaults — callers may pass overrides once per-rider calibration exists. Only
kitesurf and wing foil are sized in v1; other sports return a neutral ("n/a")
recommendation so they're unaffected.

Sanity checks at the calibrated constants (80 kg rider): kite ~10.4 m² @ 20 kn,
~6.9 m² @ 30 kn; wing ~5.5 m² @ 16 kn.
"""

from __future__ import annotations

from dataclasses import dataclass

# Calibratable model constants. Fit to manufacturer + industry charts (see module
# docstring + mockups/research/kit-sizing-manufacturers.md): kite charts cluster
# at c≈2.5–2.8 (central 2.6), wings at c≈1.1 in the 3–5 m / 12–22 kn band.
KITE_CONSTANT = 2.6
WING_CONSTANT = 1.1

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


def kit_payload(kit: KitRecommendation | None) -> dict | None:
    """Serialise a kit recommendation for the spot-detail card's ``now`` block.

    Returns ``{"rig_m2", "ideal_m2", "power"}`` for a sized sport, or ``None``
    when there is no recommendation or the sport has no size model (``POWER_NA``)
    — so non-rig sports (swim/SUP/surf) render no kit gauge, while a rig sport
    with an empty quiver still surfaces its ``no_kit`` state.
    """
    if kit is None or kit.power == POWER_NA:
        return None
    return {
        "rig_m2": kit.owned_size_m2,
        "ideal_m2": kit.ideal_size_m2,
        "power": kit.power,
    }
