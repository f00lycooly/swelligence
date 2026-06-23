#!/usr/bin/env python3
"""Pull live Open-Meteo forecasts for the Christchurch spot set and run them
through the deterministic scorer — a standalone sanity-check for the default
sport profiles (no Home Assistant required).

Usage:  python3 scripts/validate_spots.py
"""

from __future__ import annotations

import json
import sys
import types
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Import the pure submodules WITHOUT executing the package __init__ (which pulls
# in Home Assistant). We register a stub 'swelligence' package pointing at the
# source dir; relative imports in the pure modules then resolve against it.
ROOT = Path(__file__).resolve().parent.parent
_PKG_DIR = ROOT / "custom_components" / "swelligence"
_pkg = types.ModuleType("swelligence")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["swelligence"] = _pkg

from swelligence.policy import apply_water_policy, marine_wanted  # noqa: E402
from swelligence.providers.base import ForecastPoint, SpotForecast  # noqa: E402
from swelligence.scoring import best_window, score_point  # noqa: E402
from swelligence.sports import SPORT_PROFILES  # noqa: E402

_MS_TO_KN = 1.943_84
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

SPOTS = [
    {"name": "Christchurch Harbour", "lat": 50.728, "lon": -1.745, "water": "sheltered",
     "sports": ["windsurf", "wingfoil", "sup", "sailing", "seaswim", "wakeboard_sea"]},
    {"name": "Avon Beach", "lat": 50.736, "lon": -1.733, "water": "sea",
     "sports": ["surf", "sup", "kitesurf", "windsurf"]},
    {"name": "Bournemouth Pier", "lat": 50.713, "lon": -1.876, "water": "sea",
     "sports": ["surf"]},
    {"name": "Sandbanks", "lat": 50.687, "lon": -1.943, "water": "sea",
     "sports": ["kitesurf", "windsurf", "wingfoil"]},
    {"name": "New Forest Water Park", "lat": 50.9016, "lon": -1.7801, "water": "inland",
     "sports": ["wakeboard_inland", "sup"]},
    {"name": "Hurst Spit / Keyhaven", "lat": 50.711, "lon": -1.553, "water": "sea",
     "sports": ["kitesurf", "windsurf", "wingfoil"]},
]


def _get(url: str, params: dict) -> dict | None:
    qs = urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(f"{url}?{qs}", timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as err:  # noqa: BLE001
        print(f"  ! fetch failed ({url}): {err}", file=sys.stderr)
        return None


def _at(values, i):
    if i is None or not values or i >= len(values):
        return None
    return values[i]


def fetch_points(lat: float, lon: float, water: str, hours: int = 48) -> list[ForecastPoint]:
    wind = _get(_FORECAST_URL, {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,precipitation,cloud_cover",
        "wind_speed_unit": "ms", "forecast_hours": hours, "timezone": "auto",
    })
    marine = None
    if marine_wanted(water):
        marine = _get(_MARINE_URL, {
            "latitude": lat, "longitude": lon,
            "hourly": "wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,sea_surface_temperature",
            "forecast_hours": hours, "timezone": "auto",
        })
    if not wind or "hourly" not in wind:
        return []
    wh = wind["hourly"]
    times = wh.get("time", [])
    mh = (marine or {}).get("hourly", {}) if marine else {}
    m_index = {t: i for i, t in enumerate(mh.get("time", []))}

    def kn(values, i):
        v = _at(values, i)
        return round(v * _MS_TO_KN, 1) if v is not None else None

    points = []
    for i, iso in enumerate(times):
        mi = m_index.get(iso)
        points.append(ForecastPoint(
            time=datetime.fromisoformat(iso),
            wind_speed_kn=kn(wh.get("wind_speed_10m", []), i),
            wind_gust_kn=kn(wh.get("wind_gusts_10m", []), i),
            wind_dir_deg=_at(wh.get("wind_direction_10m", []), i),
            air_temp_c=_at(wh.get("temperature_2m", []), i),
            precip_mm=_at(wh.get("precipitation", []), i),
            cloud_pct=_at(wh.get("cloud_cover", []), i),
            wave_height_m=_at(mh.get("wave_height", []), mi),
            wave_period_s=_at(mh.get("wave_period", []), mi),
            wave_dir_deg=_at(mh.get("wave_direction", []), mi),
            swell_height_m=_at(mh.get("swell_wave_height", []), mi),
            swell_period_s=_at(mh.get("swell_wave_period", []), mi),
            water_temp_c=_at(mh.get("sea_surface_temperature", []), mi),
        ))
    # Apply the same water-type policy the integration uses.
    forecast = SpotForecast(provider="open_meteo", latitude=lat, longitude=lon, points=points)
    apply_water_policy(forecast, water)
    return forecast.points


def main() -> int:
    for spot in SPOTS:
        points = fetch_points(spot["lat"], spot["lon"], spot["water"])
        if not points:
            print(f"\n### {spot['name']} — no forecast\n")
            continue
        now = points[0]
        note = ""
        if spot["water"] == "inland":
            note = "  [inland → marine suppressed]"
        elif spot["water"] == "sheltered":
            note = "  [sheltered → waves suppressed, temp kept]"
        print(f"\n### {spot['name']} ({spot['water']}){note}")
        print(f"    now: wind {now.wind_speed_kn}kn gust {now.wind_gust_kn}kn "
              f"@{now.wind_dir_deg}°, wave {now.wave_height_m}m, "
              f"water {now.water_temp_c}°C, air {now.air_temp_c}°C")
        print(f"    {'sport':<18}{'now':>5} {'verdict':<10}{'best/24h':>9} {'when':>6}  reasons")
        for sport in spot["sports"]:
            profile = SPORT_PROFILES.get(sport)
            if not profile:
                continue
            res = score_point(now, profile)
            bw = best_window(points, profile, horizon=24)
            best_str = f"{bw[1].score:>5}" if bw else "    -"
            when = f"+{bw[0]}h" if bw else "  -"
            reasons = ", ".join(res.reasons[:3])
            print(f"    {profile.label:<18}{res.score:>5} {res.verdict:<10}"
                  f"{best_str:>9} {when:>6}  {reasons}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
