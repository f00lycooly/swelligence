"""Deterministic suitability scoring.

Given a normalised :class:`ForecastPoint` and a :class:`SportProfile`, produce a
0..100 score plus a per-factor breakdown. This runs with no LLM and is the
ground truth the LLM layer is asked to explain / refine, never to override
silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .providers.base import ForecastPoint
from .sports import SportProfile

# Suitability bands for the textual verdict and the binary "suitable" sensor.
SUITABLE_THRESHOLD = 55.0
_BANDS = [
    (85, "epic"),
    (70, "great"),
    (55, "good"),
    (35, "marginal"),
    (0, "poor"),
]

_SECTOR_DEG = 360.0 / 16  # 22.5


@dataclass(slots=True)
class ScoreResult:
    """Outcome of scoring one spot/sport/timestep."""

    score: float
    verdict: str
    suitable: bool
    factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def _band(score: float) -> str:
    for floor, label in _BANDS:
        if score >= floor:
            return label
    return "poor"


def _wind_factor(speed: float | None, p: SportProfile) -> tuple[float | None, str]:
    if speed is None:
        return None, ""
    if speed < p.wind_min_kn:
        # Linear ramp from 0 (dead calm) to ~0.4 at the minimum.
        f = 0.4 * (speed / p.wind_min_kn) if p.wind_min_kn else 0.4
        return max(0.0, f), f"under-powered ({speed:.0f}kn)"
    if speed > p.wind_max_kn:
        return 0.0, f"too strong ({speed:.0f}kn)"
    # Inside the window: peak at ideal, taper to 0.6 at the edges.
    if speed <= p.wind_ideal_kn:
        span = max(p.wind_ideal_kn - p.wind_min_kn, 0.1)
        f = 0.6 + 0.4 * (speed - p.wind_min_kn) / span
    else:
        span = max(p.wind_max_kn - p.wind_ideal_kn, 0.1)
        f = 1.0 - 0.4 * (speed - p.wind_ideal_kn) / span
    return min(1.0, f), f"{speed:.0f}kn"


def _gust_factor(gust: float | None, p: SportProfile) -> tuple[float | None, str]:
    if gust is None:
        return None, ""
    if gust > p.gust_max_kn:
        return 0.0, f"gusting {gust:.0f}kn (over limit)"
    return 1.0, ""


def _dir_factor(deg: float | None, dirs: list[str]) -> tuple[float | None, str]:
    if deg is None or not dirs:
        return None, ""
    from .const import COMPASS_SECTORS

    targets = [COMPASS_SECTORS.index(d) * _SECTOR_DEG for d in dirs if d in COMPASS_SECTORS]
    if not targets:
        return None, ""
    # Smallest angular distance to any preferred sector.
    best = min(abs(((deg - t + 180) % 360) - 180) for t in targets)
    if best <= _SECTOR_DEG:
        return 1.0, ""
    if best >= 90:
        return 0.0, "wrong wind direction"
    return 1.0 - (best - _SECTOR_DEG) / (90 - _SECTOR_DEG), "off-angle wind"


def _wave_factor(h: float | None, p: SportProfile) -> tuple[float | None, str]:
    if h is None or (p.wave_min_m is None and p.wave_max_m is None):
        return None, ""
    lo = p.wave_min_m if p.wave_min_m is not None else 0.0
    hi = p.wave_max_m if p.wave_max_m is not None else (lo + 3.0)
    if h < lo:
        return (0.5 if lo == 0 else 0.3 * (h / lo)), f"flat ({h:.1f}m)"
    if h > hi:
        return 0.0, f"too big ({h:.1f}m)"
    return 1.0, f"{h:.1f}m"


def _temp_factor(t: float | None, p: SportProfile) -> tuple[float | None, str]:
    if t is None or p.water_temp_min_c is None:
        return None, ""
    if t >= p.water_temp_min_c:
        return 1.0, ""
    deficit = p.water_temp_min_c - t
    return max(0.0, 1.0 - deficit / 6.0), f"cold water ({t:.0f}°C)"


def score_point(point: ForecastPoint, profile: SportProfile) -> ScoreResult:
    """Score one forecast timestep for one sport profile."""
    weighted = [
        ("wind", profile.weight_wind, _wind_factor(point.wind_speed_kn, profile)),
        ("gust", profile.weight_gust, _gust_factor(point.wind_gust_kn, profile)),
        ("direction", profile.weight_dir, _dir_factor(point.wind_dir_deg, profile.wind_dirs)),
        ("wave", profile.weight_wave, _wave_factor(point.wave_height_m, profile)),
        ("temp", profile.weight_temp, _temp_factor(point.water_temp_c, profile)),
    ]

    num = 0.0
    den = 0.0
    factors: dict[str, float] = {}
    reasons: list[str] = []
    hard_fail = False
    for name, weight, (factor, note) in weighted:
        if factor is None or weight <= 0:
            continue
        factors[name] = round(factor * 100, 1)
        num += factor * weight
        den += weight
        if note:
            reasons.append(note)
        # A zeroed essential factor caps the whole session.
        if factor == 0.0 and name in ("wind", "gust", "wave"):
            hard_fail = True

    score = 0.0 if den == 0 else round(100 * num / den, 1)
    if hard_fail:
        score = min(score, 30.0)

    return ScoreResult(
        score=score,
        verdict=_band(score),
        suitable=score >= SUITABLE_THRESHOLD,
        factors=factors,
        reasons=reasons,
    )


def best_window(
    points: list[ForecastPoint], profile: SportProfile, *, horizon: int = 24
) -> tuple[int, ScoreResult] | None:
    """Return the (hour-offset, result) of the best timestep within horizon."""
    best: tuple[int, ScoreResult] | None = None
    for i, pt in enumerate(points[:horizon]):
        res = score_point(pt, profile)
        if best is None or res.score > best[1].score:
            best = (i, res)
    return best
