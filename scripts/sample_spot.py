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
from datetime import datetime
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

from swelligence.forecast import _slot, daily_forecast  # noqa: E402
from swelligence.policy import apply_water_policy  # noqa: E402
from swelligence.tide import tide_phase, tide_state  # noqa: E402
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

    forecast = fetch(lat, lon, water, days=7)
    # Anchor "now" at local mid-day (12:00) rather than the series' midnight start
    # — a daytime snapshot reads far more naturally on the card/panel. The emitted
    # series runs from this point forward, so the consumers' "series[0] == now"
    # invariant holds (now / next hours / rest-of-week all flow from here).
    pts = forecast.points
    now_index = next((i for i, p in enumerate(pts) if p.time.hour == 12), 0)
    forward = pts[now_index:]
    now = forward[0]
    # A forecast windowed at "now" so the integration builders (daily outlook,
    # tide state) reflect now → +7d, not this morning's already-past hours.
    fwd = dataclasses.replace(forecast, points=forward)

    sample: dict = {
        "spot": {"name": name, "latitude": lat, "longitude": lon, "water_type": water},
        "now_raw": _point_dict(now),
        # Tide state is a spot-level, integration-provided data point (trend +
        # next high/low); screens render it without deriving anything.
        "tide": tide_state(fwd),
        "scores": {},
        "forecast": {},
    }
    for sport in sports:
        profile = SPORT_PROFILES.get(sport)
        if not profile:
            continue
        res = score_point(now, profile)
        bw = best_window(forward, profile, horizon=24)
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
            # Daytime-only daily peak per day = the weekly outlook. pad_h=0 =
            # strict sunrise..sunset; the default pad (2h) barely filters in a UK
            # summer (~17h days) so a "daytime" peak would otherwise land at 23:00.
            "daily": daily_forecast(fwd, profile, sport, pad_h=0),
        }
        # Annotate each daily peak with the tide phase + height AT that peak hour,
        # so the weekly best-day readout is a true detail view (integration-side).
        for entry in sample["scores"][sport]["daily"]:
            entry["tide"] = tide_phase(fwd, datetime.fromisoformat(entry["datetime"]))
        # Full forward get_forecast-style hourly slots (now → +7d) for this sport;
        # consumers slice the near-term for the timeline and aggregate per-day for
        # the weekly outlook.
        sample["forecast"][sport] = [
            _slot(p, profile, sport, 0, None) for p in forward
        ]

    json.dump(sample, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
