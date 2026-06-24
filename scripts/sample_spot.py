#!/usr/bin/env python3
"""Produce a real data sample for one spot — the raw normalised ForecastPoint
fields, the deterministic score per sport, and a get_forecast-style hourly
timeline — using the integration's *own* Open-Meteo provider + scorer against
live data. No Home Assistant required.

Usage:  python3 scripts/sample_spot.py [name lat lon water sport,sport,...]
Writes JSON to stdout; pipe to a file. Feeds the spot-detail card design.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import types
import urllib.parse
import urllib.request
from pathlib import Path

# Import the pure + provider submodules without executing the HA-pulling package
# __init__ (stub the package, point it at the source dir).
ROOT = Path(__file__).resolve().parent.parent
_PKG_DIR = ROOT / "custom_components" / "swelligence"
_pkg = types.ModuleType("swelligence")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["swelligence"] = _pkg

from swelligence.forecast import _slot  # noqa: E402
from swelligence.policy import apply_water_policy  # noqa: E402
from swelligence.providers.open_meteo import (  # noqa: E402
    _FORECAST_HOURLY,
    _MARINE_HOURLY,
    _FORECAST_URL,
    _MARINE_URL,
    OpenMeteoProvider,
)
from swelligence.scoring import best_window, score_point  # noqa: E402
from swelligence.sports import SPORT_PROFILES  # noqa: E402


def _get(url: str, params: dict) -> dict | None:
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{qs}", timeout=40) as resp:
        return json.loads(resp.read().decode())


def fetch(lat: float, lon: float, water: str, days: int = 3):
    """Live fetch + the provider's exact normalisation + water policy."""
    wind = _get(
        _FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_FORECAST_HOURLY),
            "daily": "sunrise,sunset",
            "wind_speed_unit": "ms",
            "forecast_days": days,
            "timezone": "auto",
        },
    )
    marine = _get(
        _MARINE_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_MARINE_HOURLY),
            "forecast_days": days,
            "timezone": "auto",
        },
    )
    # _build_forecast is pure normalisation; the session isn't used by it.
    forecast = OpenMeteoProvider(None)._build_forecast(lat, lon, wind, marine, True)
    apply_water_policy(forecast, water)
    return forecast


def _point_dict(p) -> dict:
    d = dataclasses.asdict(p)
    d["time"] = p.time.isoformat()
    return {k: v for k, v in d.items() if v is not None}


def main() -> int:
    if len(sys.argv) >= 5:
        name, lat, lon, water = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
        sports = sys.argv[5].split(",") if len(sys.argv) > 5 else list(SPORT_PROFILES)
    else:  # default: Southbourne (a configured spot)
        name, lat, lon, water = "Southbourne", 50.718, -1.7825, "sea"
        sports = ["surf", "kitesurf", "wingfoil", "sup"]

    forecast = fetch(lat, lon, water)
    now = forecast.points[0]

    sample: dict = {
        "spot": {"name": name, "latitude": lat, "longitude": lon, "water_type": water},
        "now_raw": _point_dict(now),
        "scores": {},
        "forecast": {},
    }
    for sport in sports:
        profile = SPORT_PROFILES.get(sport)
        if not profile:
            continue
        res = score_point(now, profile)
        bw = best_window(forecast.points, profile, horizon=24)
        sample["scores"][sport] = {
            "score": res.score,
            "verdict": res.verdict,
            "suitable": res.suitable,
            "factors": res.factors,
            "reasons": res.reasons,
            "completeness": res.completeness,
            "nudges": res.nudges,
            "best": {"score": bw[1].score, "in_hours": bw[0], "verdict": bw[1].verdict}
            if bw
            else None,
        }
        # 24h get_forecast-style hourly slots for this sport.
        sample["forecast"][sport] = [
            _slot(p, profile, sport, 0, None) for p in forecast.points[:24]
        ]

    json.dump(sample, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
