"""Built-in sport definitions and default preference profiles.

Each sport carries a default preference profile. Users override these per-spot
(or globally) via the options flow. Profiles are intentionally conservative
starting points for a UK setup and meant to be tuned.

Units: wind/gust in knots, wave height in metres, water temp in degrees C.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SportProfile:
    """Default suitability preferences for a sport."""

    key: str
    label: str
    icon: str
    water: str  # "sea", "inland", or "any"
    # Wind window (knots)
    wind_min_kn: float
    wind_ideal_kn: float
    wind_max_kn: float
    gust_max_kn: float
    # Preferred wind directions (compass sectors). Empty = direction-agnostic.
    wind_dirs: list[str] = field(default_factory=list)
    # Wave window (metres). None = waves not relevant / not scored.
    # wave_ideal_m sets the sport's intent:
    #   * a positive value  -> "waves desired" (e.g. surf): score peaks at ideal.
    #   * None               -> "flat preferred": flatter water scores higher,
    #                           declining to 0 at wave_max_m.
    wave_min_m: float | None = None
    wave_ideal_m: float | None = None
    wave_max_m: float | None = None
    # Minimum comfortable water temperature (degrees C). None = not scored.
    water_temp_min_c: float | None = None
    # How strongly each factor weighs in the deterministic score (0..1).
    weight_wind: float = 1.0
    weight_dir: float = 0.5
    weight_wave: float = 0.5
    weight_gust: float = 0.3
    weight_temp: float = 0.2


# Default sectors are left empty so the user sets their spot-specific offshore
# directions; these are sensible all-round starting windows otherwise.
SPORT_PROFILES: dict[str, SportProfile] = {
    "kitesurf": SportProfile(
        key="kitesurf", label="Kitesurf", icon="mdi:kitesurfing", water="sea",
        wind_min_kn=12, wind_ideal_kn=20, wind_max_kn=35, gust_max_kn=40,
        wave_min_m=None, wave_max_m=3.0, weight_dir=0.7,
    ),
    "windsurf": SportProfile(
        key="windsurf", label="Windsurf", icon="mdi:windsock", water="sea",
        wind_min_kn=12, wind_ideal_kn=22, wind_max_kn=40, gust_max_kn=45,
        wave_max_m=2.5, weight_dir=0.5,
    ),
    "wingfoil": SportProfile(
        key="wingfoil", label="Wing foil", icon="mdi:wind-power", water="sea",
        wind_min_kn=10, wind_ideal_kn=16, wind_max_kn=33, gust_max_kn=40,
        wave_max_m=2.5, weight_dir=0.6,
    ),
    "surf": SportProfile(
        key="surf", label="Surf", icon="mdi:surfing", water="sea",
        wind_min_kn=0, wind_ideal_kn=5, wind_max_kn=15, gust_max_kn=20,
        wave_min_m=0.6, wave_ideal_m=1.5, wave_max_m=3.5,
        weight_wind=0.6, weight_dir=0.8, weight_wave=1.0,
    ),
    "sup": SportProfile(
        key="sup", label="SUP", icon="mdi:rowing", water="any",
        wind_min_kn=0, wind_ideal_kn=4, wind_max_kn=12, gust_max_kn=15,
        wave_max_m=0.5, weight_wind=0.8, weight_wave=0.8,
    ),
    "sailing": SportProfile(
        key="sailing", label="Sailing", icon="mdi:sail-boat", water="sea",
        wind_min_kn=6, wind_ideal_kn=14, wind_max_kn=25, gust_max_kn=30,
        wave_max_m=2.0, weight_dir=0.3,
    ),
    "seaswim": SportProfile(
        key="seaswim", label="Sea swim", icon="mdi:swim", water="sea",
        wind_min_kn=0, wind_ideal_kn=2, wind_max_kn=12, gust_max_kn=16,
        wave_max_m=0.6, water_temp_min_c=12.0,
        weight_wind=0.7, weight_wave=1.0, weight_temp=1.0, weight_dir=0.1,
    ),
    "wakeboard_inland": SportProfile(
        key="wakeboard_inland", label="Wakeboard (inland)", icon="mdi:ski-water",
        water="inland",
        wind_min_kn=0, wind_ideal_kn=3, wind_max_kn=12, gust_max_kn=16,
        wave_max_m=0.3, weight_wind=1.0, weight_wave=0.9, weight_dir=0.1,
    ),
    "wakeboard_sea": SportProfile(
        key="wakeboard_sea", label="Wakeboard (sea)", icon="mdi:ski-water",
        water="sea",
        wind_min_kn=0, wind_ideal_kn=4, wind_max_kn=14, gust_max_kn=18,
        wave_max_m=0.6, weight_wind=0.9, weight_wave=1.0, weight_dir=0.2,
    ),
}


_OVERRIDABLE = {f.name for f in dataclasses.fields(SportProfile)} - {
    "key",
    "label",
    "icon",
    "water",
}


def sport_keys() -> list[str]:
    """Return all built-in sport keys."""
    return list(SPORT_PROFILES.keys())


def get_profile(key: str) -> SportProfile | None:
    """Return the default profile for a sport key."""
    return SPORT_PROFILES.get(key)


def apply_overrides(profile: SportProfile, overrides: dict | None) -> SportProfile:
    """Return ``profile`` with user overrides applied (defaults preserved).

    Only known, non-None preference fields are applied; identity/weight metadata
    (key/label/icon/water) is never overridable.
    """
    if not overrides:
        return profile
    clean = {
        k: v
        for k, v in overrides.items()
        if k in _OVERRIDABLE and v is not None
    }
    return dataclasses.replace(profile, **clean) if clean else profile
