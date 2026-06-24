#!/usr/bin/env python3
"""Build the spot-detail mockup's embedded DATA object from the real samples in
mockups/research/sample/ (`*-sensors.json` = authoritative scores/attrs;
`*-forecast.json` = raw current conditions). Emits a compact JSON blob to embed
between the `/*__DATA__*/ ... /*__END__*/` markers in mockups/spot-detail.html.

Usage:  python3 scripts/build_card_data.py            # prints JSON
        python3 scripts/build_card_data.py --inject    # rewrites the mockup in place
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "mockups" / "research" / "sample"
MOCKUP = ROOT / "mockups" / "spot-detail.html"

# Spot order + identity (matches the configured HA spots).
SPOTS = [
    ("Southbourne", "southbourne"),
    ("Mudeford", "mudeford"),
    ("Sandbanks", "sandbanks"),
]
SPORT_ORDER = ["surf", "kitesurf", "wingfoil", "sup", "wakeboard_inland"]


def _sport_key(entity_id: str, slug: str) -> str:
    # sensor.swelligence_<slug>_<sport>_suitability ; sport slug uses wing_foil
    tail = entity_id.split(f"swelligence_{slug}_", 1)[-1]
    return tail.rsplit("_suitability", 1)[0].replace("wing_foil", "wingfoil")


def build() -> dict:
    spots = []
    for name, slug in SPOTS:
        sensors = json.loads((SAMPLE / f"{slug}-sensors.json").read_text())
        fc = json.loads((SAMPLE / f"{slug}-forecast.json").read_text())
        meta = fc["spot"]
        nr = fc["now_raw"]

        # Per-sport from the authoritative recorder attributes.
        sports = {}
        advice = []
        grid = None
        sources: dict = {}
        for eid, rec in sensors.items():
            a = rec.get("attributes", {})
            if eid.endswith("_source_advice"):
                advice = a.get("recommendations", [])
                continue
            if "_suitability" not in eid:
                continue
            sk = _sport_key(eid, slug)
            try:
                score = round(float(rec["state"]), 1)
            except (TypeError, ValueError):
                score = None  # unknown/unavailable (e.g. captured mid-restart)
            dq = a.get("data_quality", {})
            grid = dq.get("grid_distance_km", grid)
            sources = a.get("data_sources", sources) or sources
            sports[sk] = {
                "sport": sk,
                "label": a.get("sport_label", sk),
                "icon": a.get("icon", ""),
                "score": score,
                "verdict": a.get("verdict"),
                "suitable": a.get("suitable"),
                "factors": a.get("factors", {}),
                "reasons": a.get("reasons", []),
                "completeness": a.get("completeness", {}),
                "nudges": a.get("nudges", []),
                "best_score": a.get("best_score"),
                "best_in_h": a.get("best_in_hours"),
                "best_verdict": a.get("best_verdict"),
                "data_quality": dq,
            }
        ordered = [sports[k] for k in SPORT_ORDER if k in sports]
        ordered += [v for k, v in sports.items() if k not in SPORT_ORDER]

        spots.append(
            {
                "name": name,
                "water_type": meta["water_type"],
                "lat": meta["latitude"],
                "lon": meta["longitude"],
                "grid_distance_km": grid,
                "sources": sources,
                "source_advice": advice,
                "sports": ordered,
                "current": {
                    "time": nr.get("time"),
                    "wind_kn": nr.get("wind_speed_kn"),
                    "gust_kn": nr.get("wind_gust_kn"),
                    "wind_dir": nr.get("wind_dir_deg"),
                    "wave_m": nr.get("wave_height_m"),
                    "wave_period_s": nr.get("wave_period_s"),
                    "wave_dir": nr.get("wave_dir_deg"),
                    "swell_m": nr.get("swell_height_m"),
                    "swell_period_s": nr.get("swell_period_s"),
                    "swell_peak_period_s": nr.get("swell_peak_period_s"),
                    "swell_dir": nr.get("swell_dir_deg"),
                    "wind_wave_m": nr.get("wind_wave_height_m"),
                    "current_kn": nr.get("current_speed_kn"),
                    "current_dir": nr.get("current_dir_deg"),
                    "sea_level_m": nr.get("sea_level_m"),
                    "water_temp_c": nr.get("water_temp_c"),
                    "air_temp_c": nr.get("air_temp_c"),
                    "apparent_temp_c": nr.get("apparent_temp_c"),
                    "uv": nr.get("uv_index"),
                    "visibility_m": nr.get("visibility_m"),
                    "weather_code": nr.get("weather_code"),
                },
            }
        )
    return {
        "source": "open_meteo",
        "confidence_dormant": True,
        "spots": spots,
    }


def main() -> int:
    data = build()
    blob = json.dumps(data, separators=(",", ":"))
    if "--inject" in sys.argv:
        html = MOCKUP.read_text()
        new = re.sub(
            r"/\*__DATA__\*/.*?/\*__END__\*/",
            f"/*__DATA__*/{blob}/*__END__*/",
            html,
            flags=re.S,
        )
        MOCKUP.write_text(new)
        print(f"injected {len(blob)} bytes into {MOCKUP.relative_to(ROOT)}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
