"""Forecast confidence from model agreement.

Confidence == agreement. When several independent forecast models agree closely
on a field, trust it; when they diverge, hedge. This module owns two pure,
provider-agnostic pieces:

* :func:`field_confidence` — map the *spread* of a field's per-model source
  values to a 0..1 confidence, using a per-field physical uncertainty scale.
  Providers that retain a multi-source spread for a field (e.g. Open-Meteo's
  multi-model ``models=`` request) call this once per field and stash the result
  in ``ForecastPoint.source_confidence``.
* :func:`aggregate_confidence` — collapse those per-field confidences into a
  single, *sport-aware* signal for one timestep, weighting each field by how
  much that sport's score leans on it.

No Home Assistant / I/O, so the providers, the sensor layer, and the standalone
validation scripts share one implementation.
"""

from __future__ import annotations

import math

from .sports import SportProfile

# Spread (std-dev, in each field's native unit) at which agreement is considered
# fully lost — confidence reaches 0. Tuned to the physical scale of each field:
# a 6kn disagreement on wind, or 0.6m on wave height, is a coin-flip's worth of
# uncertainty. Direction fields use circular std-dev in degrees. Tunable.
FIELD_UNCERTAINTY_SCALE: dict[str, float] = {
    "wind_speed_kn": 6.0,
    "wind_gust_kn": 8.0,
    "wind_dir_deg": 45.0,
    "wave_height_m": 0.6,
    "wave_period_s": 3.0,
    "wave_dir_deg": 45.0,
    "swell_height_m": 0.5,
    "swell_period_s": 3.0,
    "swell_dir_deg": 45.0,
    "water_temp_c": 2.0,
    "air_temp_c": 3.0,
}

#: Fields scored on a compass bearing — spread is angular, not linear.
DIRECTION_FIELDS: frozenset[str] = frozenset(
    {"wind_dir_deg", "wave_dir_deg", "swell_dir_deg"}
)

# Confidence -> word. Bands chosen so "high" means models are within roughly a
# third of the uncertainty scale of each other.
_LABELS = ((0.7, "high"), (0.45, "moderate"), (0.0, "low"))


def confidence_label(value: float) -> str:
    """Map a 0..1 confidence to ``high`` / ``moderate`` / ``low``."""
    for floor, label in _LABELS:
        if value >= floor:
            return label
    return "low"


def _pstdev(values: list[float]) -> float:
    n = len(values)
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def _circular_std_deg(values: list[float]) -> float:
    """Circular standard deviation (degrees) of a set of compass bearings."""
    n = len(values)
    s = sum(math.sin(math.radians(v)) for v in values) / n
    c = sum(math.cos(math.radians(v)) for v in values) / n
    r = math.hypot(s, c)
    if r <= 1e-9:
        return 180.0  # maximally dispersed
    return math.degrees(math.sqrt(-2.0 * math.log(r)))


def _circular_mean_deg(values: list[float]) -> float:
    """Mean compass bearing (degrees, 0..360) of a set of directions."""
    n = len(values)
    s = sum(math.sin(math.radians(v)) for v in values) / n
    c = sum(math.cos(math.radians(v)) for v in values) / n
    return math.degrees(math.atan2(s, c)) % 360.0


def blend_values(field: str, values) -> float | None:
    """Consensus value for a field across models — the mean for accuracy.

    Uses a circular mean for compass-bearing fields (so 350° and 10° average to
    0°, not 180°) and an arithmetic mean otherwise. ``None`` when no numeric
    values are given.
    """
    nums = [float(v) for v in (values or []) if isinstance(v, (int, float))]
    if not nums:
        return None
    if field in DIRECTION_FIELDS:
        # %360 folds a rounded 360.0 back to 0.0 (atan2 can land just below 0).
        return round(_circular_mean_deg(nums), 1) % 360.0
    return round(sum(nums) / len(nums), 2)


def field_confidence(field: str, values) -> float | None:
    """Confidence (0..1) that ``field`` is well-determined, from model spread.

    ``values`` is the set of per-model source values for one field at one
    timestep (already in the field's stored unit — knots for wind, etc.).
    Returns ``None`` when fewer than two numeric sources exist (no spread to
    measure) or the field has no defined uncertainty scale.
    """
    nums = [float(v) for v in (values or []) if isinstance(v, (int, float))]
    if len(nums) < 2:
        return None
    scale = FIELD_UNCERTAINTY_SCALE.get(field)
    if not scale:
        return None
    spread = _circular_std_deg(nums) if field in DIRECTION_FIELDS else _pstdev(nums)
    return round(max(0.0, min(1.0, 1.0 - spread / scale)), 3)


# Each scored factor -> the representative ForecastPoint field whose agreement
# stands in for that factor's confidence, paired with the profile weight to read.
_FACTOR_FIELDS: tuple[tuple[str, str], ...] = (
    ("wind_speed_kn", "weight_wind"),
    ("wind_gust_kn", "weight_gust"),
    ("wind_dir_deg", "weight_dir"),
    ("wave_height_m", "weight_wave"),
    ("swell_period_s", "weight_swell"),
    ("swell_dir_deg", "weight_swell"),
    ("water_temp_c", "weight_temp"),
)


def aggregate_confidence(point, profile: SportProfile) -> dict | None:
    """Sport-weighted overall confidence for one timestep.

    Reads ``point.source_confidence`` (per-field 0..1, populated by the provider)
    and collapses it into one number, weighting each field by how strongly the
    sport's score depends on it. Returns ``{"value", "label", "fields"}`` or
    ``None`` when no scored field carries an agreement signal (e.g. a
    single-source provider).
    """
    per_field = getattr(point, "source_confidence", None)
    if not per_field:
        return None
    num = den = 0.0
    used: dict[str, float] = {}
    for field, weight_attr in _FACTOR_FIELDS:
        conf = per_field.get(field)
        weight = getattr(profile, weight_attr, 0.0) or 0.0
        if conf is None or weight <= 0:
            continue
        num += conf * weight
        den += weight
        used[field] = conf
    if den == 0:
        return None
    value = round(num / den, 3)
    return {"value": value, "label": confidence_label(value), "fields": used}
