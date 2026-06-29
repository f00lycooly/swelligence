"""Safety flags — pure, advisory markers of *why a slot may be unsafe*.

First-class output alongside the score (how good) and confidence (how
trustworthy): ``safety_flags`` answers *why a slot may be unsafe*. Flags are
**advisory** — they never change the numeric score. They are derived from the
factor values and notes the scorer already computes (see ``scoring.score_point``),
so a flag can never disagree with the score it accompanies — the wind/wave
hard-fails that cap the score are the same evaluations that raise the flag
(unify, don't parallel).

Pure logic: no ``homeassistant`` import, no provider/domain import — runs under
the stubbed unit suite. Mirrors ``hazards.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Severity tiers. ``danger`` = conditions that already hard-fail the sport
# (overpowering / oversized / over-choppy); ``caution`` = manageable-but-squally.
DANGER = "danger"
CAUTION = "caution"

# Plain fallbacks when a factor note is somehow empty (defensive only — the
# scorer always supplies a note for these conditions today).
_FALLBACK = {
    "too_strong": "overpowering wind",
    "too_big": "oversized waves",
    "too_choppy": "choppy water",
    "gusty": "strong gusts",
}


@dataclass(slots=True, frozen=True)
class SafetyFlag:
    """One active safety marker at a timestep."""

    kind: str  # "too_strong" | "too_big" | "too_choppy" | "gusty"
    severity: str  # DANGER | CAUTION
    message: str  # conservative human text, reused from the factor note

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "severity": self.severity, "message": self.message}


def _flag(kind: str, severity: str, note: str) -> SafetyFlag:
    return SafetyFlag(kind, severity, note or _FALLBACK[kind])


def derive_safety_flags(profile, factors: dict[str, tuple]) -> list[SafetyFlag]:
    """Advisory safety flags for one scored timestep.

    ``factors`` maps a scored factor name to ``(value, note)`` as produced by the
    scorer, for the factors that can raise a flag (``wind`` / ``wave`` / ``gust``).
    Nothing is re-thresholded here: a ``0.0`` wind/wave value is exactly the
    scorer's hard-fail signal, and a gust value below ``1.0`` is exactly the
    scorer's over-ceiling signal.
    """
    flags: list[SafetyFlag] = []

    wind = factors.get("wind")
    if wind is not None and wind[0] == 0.0:
        # _wind_factor returns 0.0 only for over-max ("too strong"); under-power
        # is always > 0, so this never mistakes a light day for a dangerous one.
        flags.append(_flag("too_strong", DANGER, wind[1]))

    wave = factors.get("wave")
    if wave is not None and wave[0] == 0.0:
        # waves-desired (surf): over-max reads "too big"; flat-preferred (wind
        # sports): over-max reads "too choppy". Same value, profile disambiguates.
        kind = "too_big" if (profile.wave_ideal_m and profile.wave_ideal_m > 0) else "too_choppy"
        flags.append(_flag(kind, DANGER, wave[1]))

    gust = factors.get("gust")
    if gust is not None and gust[0] is not None and gust[0] < 1.0:
        # _gust_factor is exactly 1.0 at/under the ceiling; < 1.0 only once gusts
        # exceed the sport's gust_max_kn.
        flags.append(_flag("gusty", CAUTION, gust[1]))

    return flags
