#!/usr/bin/env python3
"""Pull the last ~3 weeks of Open-Meteo history for the Christchurch spot set,
find the windy days, and re-score them — a top-of-the-curve stress test for the
kite/wing/surf profiles (complements validate_spots.py which only sees 'now').

Usage:  python3 scripts/analyze_history.py [past_days]
"""

from __future__ import annotations

import sys
import types
import urllib.parse
import urllib.request
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PKG_DIR = ROOT / "custom_components" / "swelligence"
_pkg = types.ModuleType("swelligence")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["swelligence"] = _pkg

from swelligence.policy import apply_water_policy, marine_wanted  # noqa: E402
from swelligence.providers.base import ForecastPoint, SpotForecast  # noqa: E402
from swelligence.scoring import score_point  # noqa: E402
from swelligence.sports import SPORT_PROFILES  # noqa: E402

_MS_TO_KN = 1.943_84
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

SPOTS = [
    {"name": "Christchurch Harbour", "lat": 50.728, "lon": -1.745, "water": "sheltered",
     "sports": ["windsurf", "wingfoil", "sailing"]},
    {"name": "Avon Beach", "lat": 50.736, "lon": -1.733, "water": "sea",
     "sports": ["surf", "kitesurf", "windsurf"]},
    {"name": "Bournemouth Pier", "lat": 50.713, "lon": -1.876, "water": "sea",
     "sports": ["surf"]},
    {"name": "Sandbanks", "lat": 50.687, "lon": -1.943, "water": "sea",
     "sports": ["kitesurf", "windsurf", "wingfoil"]},
    {"name": "Hurst Spit / Keyhaven", "lat": 50.711, "lon": -1.553, "water": "sea",
     "sports": ["kitesurf", "windsurf", "wingfoil"]},
]


def _get(url: str, params: dict) -> dict | None:
    qs = urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(f"{url}?{qs}", timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as err:  # noqa: BLE001
        print(f"  ! fetch failed ({url}): {err}", file=sys.stderr)
        return None


def _at(values, i):
    if i is None or not values or i >= len(values):
        return None
    return values[i]


def fetch_history(lat, lon, water, past_days):
    common = {"latitude": lat, "longitude": lon, "forecast_days": 1,
              "past_days": past_days, "timezone": "auto"}
    wind = _get(_FORECAST_URL, {**common, "wind_speed_unit": "ms",
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m"})
    marine = None
    if marine_wanted(water):
        marine = _get(_MARINE_URL, {**common,
            "hourly": "wave_height,wave_period,wave_direction,sea_surface_temperature"})
    if not wind or "hourly" not in wind:
        return []
    wh = wind["hourly"]
    times = wh.get("time", [])
    mh = (marine or {}).get("hourly", {}) if marine else {}
    m_index = {t: i for i, t in enumerate(mh.get("time", []))}

    def kn(v, i):
        x = _at(v, i)
        return round(x * _MS_TO_KN, 1) if x is not None else None

    pts = []
    for i, iso in enumerate(times):
        mi = m_index.get(iso)
        pts.append(ForecastPoint(
            time=datetime.fromisoformat(iso),
            wind_speed_kn=kn(wh.get("wind_speed_10m", []), i),
            wind_gust_kn=kn(wh.get("wind_gusts_10m", []), i),
            wind_dir_deg=_at(wh.get("wind_direction_10m", []), i),
            air_temp_c=_at(wh.get("temperature_2m", []), i),
            wave_height_m=_at(mh.get("wave_height", []), mi),
            wave_period_s=_at(mh.get("wave_period", []), mi),
            wave_dir_deg=_at(mh.get("wave_direction", []), mi),
            water_temp_c=_at(mh.get("sea_surface_temperature", []), mi),
        ))
    fc = SpotForecast(provider="open_meteo", latitude=lat, longitude=lon, points=pts)
    apply_water_policy(fc, water)
    return fc.points


def _compass(deg):
    if deg is None:
        return "?"
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]


def main():
    past_days = int(sys.argv[1]) if len(sys.argv) > 1 else 21

    # Reference point (Avon Beach) to rank windy days region-wide.
    ref = next(s for s in SPOTS if s["name"] == "Avon Beach")
    ref_pts = fetch_history(ref["lat"], ref["lon"], ref["water"], past_days)
    by_day = defaultdict(list)
    for p in ref_pts:
        if p.wind_speed_kn is not None:
            by_day[p.time.date()].append(p)

    day_peaks = []
    for day, pts in by_day.items():
        peak = max(pts, key=lambda p: (p.wind_gust_kn or 0))
        day_peaks.append((day, peak.wind_speed_kn, peak.wind_gust_kn,
                          _compass(peak.wind_dir_deg), peak.time.hour))
    day_peaks.sort(key=lambda r: (r[2] or 0), reverse=True)

    print(f"\n=== Windiest days in last {past_days}d (ref: Avon Beach) ===")
    print(f"{'date':<12}{'peak wind':>10}{'peak gust':>11}{'dir':>5}{'hr':>4}")
    for day, w, g, d, hr in day_peaks:
        print(f"{str(day):<12}{w:>8}kn{g:>9}kn{d:>5}{hr:>4}")

    # Stress-score the top windy days at each spot's windiest hour.
    top_days = [r[0] for r in day_peaks[:5]]
    spot_pts = {s["name"]: fetch_history(s["lat"], s["lon"], s["water"], past_days)
                for s in SPOTS}

    for day in top_days:
        print(f"\n### {day} — peak-hour scores")
        for spot in SPOTS:
            pts = [p for p in spot_pts[spot["name"]] if p.time.date() == day
                   and p.wind_speed_kn is not None]
            if not pts:
                continue
            peak = max(pts, key=lambda p: (p.wind_gust_kn or 0))
            wave = f"{peak.wave_height_m:.1f}m" if peak.wave_height_m is not None else "—"
            print(f"  {spot['name']:<24} peak {peak.wind_speed_kn:>4}kn "
                  f"g{peak.wind_gust_kn:>4}kn {_compass(peak.wind_dir_deg):<3} wave {wave}")
            for sport in spot["sports"]:
                prof = SPORT_PROFILES.get(sport)
                if not prof:
                    continue
                res = score_point(peak, prof)
                print(f"      {prof.label:<16}{res.score:>5} {res.verdict:<10}"
                      f"  {', '.join(res.reasons[:3])}")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
