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

# Cap applied when an *essential* factor for a sport has no provider data: even
# perfect known conditions can't read better than "marginal" while a defining
# condition is unverifiable (surf with no swell, sea-swim with no water temp).
# Honest under-statement of an incomplete picture, distinct from the known-bad
# hard-fail cap (30) — unknown is less punitive than known-bad, but still below
# the `SUITABLE_THRESHOLD` so an incomplete forecast never reads "suitable".
INCOMPLETE_CAP = 50.0

# Per-factor completeness states. A factor's ``None`` is no longer a single
# "unknown" — it is one of three distinct things, scored differently:
APPLICABLE = "applicable"  # has a value; contributes to the weighted mean
NOT_APPLICABLE = "not_applicable"  # sport genuinely doesn't score it; free
NOT_CONFIGURED = "not_configured"  # spot metadata missing (e.g. no offshore window); nudge
MISSING_DATA = "missing_data"  # provider returned None for a field the sport scores

_DIR_NUDGE = "set offshore wind directions for sharper scoring"
_SWELL_DIR_NUDGE = "set swell directions for sharper surf scoring"


@dataclass(slots=True)
class FactorEval:
    """One factor's evaluation: its value (if any), completeness state, and notes.

    ``note`` is a condition observation ("12kn", "too big") surfaced in
    ``reasons``; ``nudge`` is a data-quality hint ("set offshore directions")
    surfaced separately so config gaps never masquerade as bad conditions.
    """

    value: float | None
    state: str
    note: str = ""
    nudge: str = ""


@dataclass(slots=True)
class ScoreResult:
    """Outcome of scoring one spot/sport/timestep."""

    score: float
    verdict: str
    suitable: bool
    factors: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    #: Per-factor completeness state for factors that are NOT plainly scorable —
    #: ``not_configured`` (fixable via spot metadata) or ``missing_data``
    #: (provider gap). Applicable factors appear in ``factors``; not-applicable
    #: factors are silent.
    completeness: dict[str, str] = field(default_factory=dict)
    #: Actionable data-quality hints (config gaps), separate from ``reasons``.
    nudges: list[str] = field(default_factory=list)


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
    if gust <= p.gust_max_kn:
        return 1.0, ""
    # Graduated penalty: 1.0 at the ceiling, ramping to 0 once gusts reach 50%
    # over it. A gust slightly over the limit nudges the score, it doesn't kill it.
    over = (gust - p.gust_max_kn) / max(0.5 * p.gust_max_kn, 0.1)
    return max(0.0, 1.0 - over), f"gusting {gust:.0f}kn (over {p.gust_max_kn:.0f})"


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
    if h is None or (
        p.wave_min_m is None and p.wave_ideal_m is None and p.wave_max_m is None
    ):
        return None, ""

    # Waves-desired sport (surf-like): score ramps up to wave_ideal_m, then
    # tapers towards wave_max_m. No more binary "full credit anywhere in range".
    if p.wave_ideal_m and p.wave_ideal_m > 0:
        base = p.wave_min_m if p.wave_min_m is not None else 0.0
        if h < base:
            frac = (h / base) if base else 0.0
            return max(0.0, 0.5 * frac), f"flat ({h:.1f}m)"
        if p.wave_max_m is not None and h > p.wave_max_m:
            return 0.0, f"too big ({h:.1f}m)"
        if h <= p.wave_ideal_m:
            span = max(p.wave_ideal_m - base, 0.1)
            f = 0.6 + 0.4 * (h - base) / span
        else:
            top = p.wave_max_m if p.wave_max_m is not None else p.wave_ideal_m + 2.0
            span = max(top - p.wave_ideal_m, 0.1)
            f = 1.0 - 0.4 * (h - p.wave_ideal_m) / span
        return min(1.0, max(0.0, f)), f"{h:.1f}m"

    # Flat-preferred sport: full credit while chop is comfortable, then declining
    # to 0 at wave_max_m. The comfort plateau stops small, normal sea chop from
    # penalising wind sports (kite/windsurf/wing) where it's neutral-to-fun.
    if p.wave_max_m is not None:
        comfort = 0.4 * p.wave_max_m
        if h <= comfort:
            return 1.0, ""
        if h >= p.wave_max_m:
            return 0.0, f"too choppy ({h:.1f}m)"
        f = 1.0 - (h - comfort) / (p.wave_max_m - comfort)
        note = f"choppy ({h:.1f}m)" if h > 0.7 * p.wave_max_m else ""
        return max(0.0, f), note
    return None, ""


def _swell_factor(point, p: SportProfile) -> tuple[float | None, str]:
    """Swell *quality* for surf-type sports: period (groundswell) × direction.

    Long-period swell scores higher than short-period windswell; when the spot
    has a swell window (``swell_dirs``) and the provider reports swell direction,
    swell from outside the window is gated down. ``None`` when the sport doesn't
    care about swell or no swell-period data is available.
    """
    if p.swell_period_ideal_s is None or point.swell_period_s is None:
        return None, ""
    period = point.swell_period_s
    lo = 4.0  # below ~4s is wind-chop, not rideable groundswell
    ideal = max(p.swell_period_ideal_s, lo + 1)
    f_period = max(0.0, min(1.0, (period - lo) / (ideal - lo)))

    f_dir, _ = _dir_factor(point.swell_dir_deg, p.swell_dirs)
    factor = f_period if f_dir is None else f_period * f_dir

    if f_dir is not None and f_dir < 0.4:
        note = "swell out of window"
    elif period < 7:
        note = f"short-period swell ({period:.0f}s)"
    elif period >= ideal:
        note = f"clean {period:.0f}s groundswell"
    else:
        note = f"{period:.0f}s swell"
    return round(factor, 3), note


def _temp_factor(t: float | None, p: SportProfile) -> tuple[float | None, str]:
    if t is None or p.water_temp_min_c is None:
        return None, ""
    if t >= p.water_temp_min_c:
        return 1.0, ""
    deficit = p.water_temp_min_c - t
    return max(0.0, 1.0 - deficit / 6.0), f"cold water ({t:.0f}°C)"


# --- completeness-aware wrappers ---------------------------------------------
# Each wraps a numeric core and classifies its ``None`` into a completeness
# state. The numeric cores above are unchanged, so the score math is identical
# whenever the data is present — only the *absence* of data is now typed.


def _wind_eval(speed: float | None, p: SportProfile) -> FactorEval:
    if speed is None:
        return FactorEval(None, MISSING_DATA, "wind data unavailable")
    f, note = _wind_factor(speed, p)
    return FactorEval(f, APPLICABLE, note)


def _gust_eval(gust: float | None, p: SportProfile) -> FactorEval:
    if gust is None:
        return FactorEval(None, MISSING_DATA)  # graduated, never essential
    f, note = _gust_factor(gust, p)
    return FactorEval(f, APPLICABLE, note)


def _wind_dir_eval(deg: float | None, dirs: list[str]) -> FactorEval:
    # No offshore window set is a *spot config* gap, not bad conditions: surface
    # a nudge rather than silently dropping the strictness a tuned spot gets.
    if not dirs:
        return FactorEval(None, NOT_CONFIGURED, nudge=_DIR_NUDGE)
    if deg is None:
        return FactorEval(None, MISSING_DATA, "wind direction unavailable")
    f, note = _dir_factor(deg, dirs)
    if f is None:  # dirs held no valid compass sectors
        return FactorEval(None, NOT_CONFIGURED, nudge=_DIR_NUDGE)
    return FactorEval(f, APPLICABLE, note)


def _wave_eval(h: float | None, p: SportProfile) -> FactorEval:
    if p.wave_min_m is None and p.wave_ideal_m is None and p.wave_max_m is None:
        return FactorEval(None, NOT_APPLICABLE)  # sport doesn't score waves
    if h is None:
        return FactorEval(None, MISSING_DATA, "wave data unavailable")
    f, note = _wave_factor(h, p)
    if f is None:  # degenerate window (e.g. only wave_min set) — not scorable
        return FactorEval(None, NOT_APPLICABLE)
    return FactorEval(f, APPLICABLE, note)


def _swell_eval(point, p: SportProfile) -> FactorEval:
    if p.swell_period_ideal_s is None:
        return FactorEval(None, NOT_APPLICABLE)  # sport doesn't score swell
    if point.swell_period_s is None:
        return FactorEval(None, MISSING_DATA, "swell data unavailable")
    f, note = _swell_factor(point, p)
    # If we have a swell bearing but no window to gate it against, the spot is
    # under-configured for surf quality — nudge, but still score on period.
    nudge = _SWELL_DIR_NUDGE if (point.swell_dir_deg is not None and not p.swell_dirs) else ""
    return FactorEval(f, APPLICABLE, note, nudge)


def _temp_eval(t: float | None, p: SportProfile) -> FactorEval:
    if p.water_temp_min_c is None:
        return FactorEval(None, NOT_APPLICABLE)  # sport doesn't score water temp
    if t is None:
        return FactorEval(None, MISSING_DATA, "water temp unavailable")
    f, note = _temp_factor(t, p)
    return FactorEval(f, APPLICABLE, note)


def score_point(point: ForecastPoint, profile: SportProfile) -> ScoreResult:
    """Score one forecast timestep for one sport profile."""
    evals = [
        ("wind", profile.weight_wind, _wind_eval(point.wind_speed_kn, profile)),
        ("gust", profile.weight_gust, _gust_eval(point.wind_gust_kn, profile)),
        ("direction", profile.weight_dir, _wind_dir_eval(point.wind_dir_deg, profile.wind_dirs)),
        ("wave", profile.weight_wave, _wave_eval(point.wave_height_m, profile)),
        ("swell", profile.weight_swell, _swell_eval(point, profile)),
        ("temp", profile.weight_temp, _temp_eval(point.water_temp_c, profile)),
    ]

    num = 0.0
    den = 0.0
    factors: dict[str, float] = {}
    reasons: list[str] = []
    completeness: dict[str, str] = {}
    nudges: list[str] = []
    essential_missing: list[str] = []
    hard_fail = False
    for name, weight, ev in evals:
        # weight <= 0 means the sport genuinely doesn't score this factor at all;
        # its absence is never a completeness gap (not_applicable, silent).
        if weight <= 0:
            continue
        if ev.nudge:
            nudges.append(ev.nudge)
        if ev.state == APPLICABLE:
            factors[name] = round(ev.value * 100, 1)
            num += ev.value * weight
            den += weight
            if ev.note:
                reasons.append(ev.note)
            # A zeroed essential factor caps the whole session. Gusts are excluded:
            # they apply a graduated penalty rather than a hard cap.
            if ev.value == 0.0 and name in ("wind", "wave"):
                hard_fail = True
        elif ev.state == NOT_CONFIGURED:
            completeness[name] = NOT_CONFIGURED
        elif ev.state == MISSING_DATA:
            completeness[name] = MISSING_DATA
            # An essential field with no data means a defining condition is
            # unverifiable — cap rather than averaging the gap away (which would
            # inflate the score and let untuned/under-fed spots escape scrutiny).
            if name in profile.essential_factors:
                essential_missing.append(name)
                if ev.note:
                    reasons.append(ev.note)
        # NOT_APPLICABLE: silent, contributes nothing.

    score = 0.0 if den == 0 else round(100 * num / den, 1)
    if hard_fail:
        score = min(score, 30.0)
    if essential_missing:
        score = min(score, INCOMPLETE_CAP)

    # Tide gate: a tide-dependent spot at the wrong state caps the score (the
    # multiplier is precomputed per point by the coordinator; see tide.py).
    if point.tide_factor is not None:
        factors["tide"] = round(point.tide_factor * 100, 1)
        score = round(score * point.tide_factor, 1)
        if point.tide_factor < 0.95:
            reasons.append("tide off")

    return ScoreResult(
        score=score,
        verdict=_band(score),
        suitable=score >= SUITABLE_THRESHOLD,
        factors=factors,
        reasons=reasons,
        completeness=completeness,
        nudges=nudges,
    )


def blend_kit(result: ScoreResult, kit_factor: float) -> ScoreResult:
    """Fold a quiver power-match factor into a conditions score.

    kit_factor 1.0 leaves the score untouched; a poor match scales it down to a
    floor of 40% (so a great-wind day you can't rig for reads "marginal/poor"
    with the kit advice, rather than vanishing to zero). The factor is recorded
    in ``factors['kit']`` for transparency.
    """
    if kit_factor >= 1.0:
        return result
    adjusted = round(result.score * (0.4 + 0.6 * kit_factor), 1)
    return ScoreResult(
        score=adjusted,
        verdict=_band(adjusted),
        suitable=adjusted >= SUITABLE_THRESHOLD,
        factors={**result.factors, "kit": round(kit_factor * 100, 1)},
        reasons=list(result.reasons),
        completeness=dict(result.completeness),
        nudges=list(result.nudges),
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
