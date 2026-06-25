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
# Every mockup that embeds the shared DATA blob between the /*__DATA__*/ markers.
MOCKUPS = [
    ROOT / "mockups" / "spot-detail.html",
    ROOT / "mockups" / "wall-panel-720.html",
]

# Spot order + identity (matches the configured HA spots).
SPOTS = [
    ("Southbourne", "southbourne"),
    ("Mudeford", "mudeford"),
    ("Sandbanks", "sandbanks"),
]
SPORT_ORDER = ["surf", "kitesurf", "wingfoil", "sup", "wakeboard_inland"]

# Fallback labels when the recorder capture doesn't carry sport_label.
_SPORT_META = {
    "surf": ("Surf",), "kitesurf": ("Kitesurf",), "wingfoil": ("Wingfoil",),
    "sup": ("SUP",), "wakeboard_inland": ("Wake",), "windsurf": ("Windsurf",),
    "sailing": ("Sailing",), "seaswim": ("Sea swim",),
}


def _sport_key(entity_id: str, slug: str) -> str:
    # sensor.swelligence_<slug>_<sport>_suitability ; sport slug uses wing_foil
    tail = entity_id.split(f"swelligence_{slug}_", 1)[-1]
    return tail.rsplit("_suitability", 1)[0].replace("wing_foil", "wingfoil")


# Verdict → compact code for the hourly timeline (keeps DATA small).
_VCODE = {"poor": 0, "marginal": 1, "good": 2, "great": 3, "epic": 4}
# Near-term hourly horizon embedded for the suitability timeline + tide curve
# (the full multi-day series is aggregated to daily peaks for the weekly strip).
_NEAR_H = 24


def _daily(pts: list, today: str) -> list:
    """Aggregate a sport's full forward hourly series into one entry per calendar
    day: the day's PEAK suitability + the hour it occurs. Feeds the weekly strip."""
    from datetime import date as _date

    days: dict[str, dict] = {}
    order: list[str] = []
    for p in pts:
        d = p["datetime"][:10]
        sc = p.get("score")
        if sc is None:
            continue
        if d not in days:
            days[d] = {"date": d, "s": sc, "v": p.get("verdict"), "t": p["datetime"][11:16]}
            order.append(d)
        elif sc > days[d]["s"]:
            days[d].update(s=sc, v=p.get("verdict"), t=p["datetime"][11:16])
    out = []
    for d in order:
        e = days[d]
        out.append({
            "d": "Today" if d == today else _date.fromisoformat(d).strftime("%a"),
            "date": d,
            "s": round(e["s"]),
            "v": _VCODE.get(e["v"], 1),
            "t": e["t"],
        })
    return out


def _derive_tide(hours: list, levels: list) -> dict | None:
    """Tide state from the modelled sea-level trajectory (Open-Meteo sea_level_m).
    Honest: this is the MODELLED tidal datum, not a station tide table — labelled
    as such in the UI. Real overlay (UKHO/NOAA) supplies true high/low events.
    'now' is hours[0] (the series starts at the captured time)."""
    valid = [l for l in levels if l is not None]
    if len(valid) < 3:
        return None
    now_l = levels[0]
    # Tides move slowly — judge the slope over the next ~3h, not one noisy hour.
    fut = [l for l in levels[1:4] if l is not None]
    ahead = sum(fut) / len(fut) if fut else now_l
    if ahead > now_l + 0.02:
        state, want = "rising", "high"
    elif ahead < now_l - 0.02:
        state, want = "falling", "low"
    else:
        state, want = "slack", None
    nxt = None
    for i in range(1, len(levels) - 1):
        a, b, c = levels[i - 1], levels[i], levels[i + 1]
        if None in (a, b, c):
            continue
        is_max, is_min = b >= a and b >= c, b <= a and b <= c
        if (want == "high" and is_max) or (want == "low" and is_min):
            nxt = (want, i, b)
            break
        if want is None and (is_max or is_min):
            nxt = ("high" if is_max else "low", i, b)
            break
    tide = {
        "now": round(now_l, 2),
        "state": state,
        "min": round(min(valid), 2),
        "max": round(max(valid), 2),
        "levels": [round(l, 2) if l is not None else None for l in levels],
    }
    if nxt:
        tide["next"] = {"type": nxt[0], "time": hours[nxt[1]], "in_h": nxt[1], "level": round(nxt[2], 2)}
    return tide


def build() -> dict:
    spots = []
    for name, slug in SPOTS:
        sensors = json.loads((SAMPLE / f"{slug}-sensors.json").read_text())
        fc = json.loads((SAMPLE / f"{slug}-forecast.json").read_text())
        meta = fc["spot"]
        nr = fc["now_raw"]

        # Hourly forecast series → the time story (now / next hours / today).
        # Environmental series (time, sea level) is spot-level; take it from any
        # sport's series. Per-sport score series feeds the suitability timeline.
        fseries = fc.get("forecast", {})
        env = next((v for v in fseries.values() if isinstance(v, list) and v), [])
        near = env[:_NEAR_H]
        hours = [p["datetime"][11:16] for p in near]
        now_iso = nr.get("time") or (env[0]["datetime"] if env else "")
        now_time = now_iso.replace("T", " ")[11:16]
        today = now_iso[:10]
        tide = _derive_tide(hours, [p.get("sea_level_m") for p in near]) if near else None
        # Compact per-sport near-term hourly [score, vcode] (timeline) + daily peaks (week).
        series_by_sport, daily_by_sport = {}, {}
        for sk, pts in fseries.items():
            if isinstance(pts, list):
                series_by_sport[sk] = [
                    [round(p["score"]) if p.get("score") is not None else None,
                     _VCODE.get(p.get("verdict"), 1)]
                    for p in pts[:_NEAR_H]
                ]
                daily_by_sport[sk] = _daily(pts, today)

        # Time-invariant presentation/quality metadata from the recorder capture
        # (sport label/icon, model grid distance, per-domain sources, advice).
        # These don't change with time of day, so a prior capture is fine.
        meta_by_sport, advice, grid = {}, [], None
        sources: dict = {}
        for eid, rec in sensors.items():
            a = rec.get("attributes", {})
            if eid.endswith("_source_advice"):
                advice = a.get("recommendations", [])
                continue
            if "_suitability" not in eid:
                continue
            sk = _sport_key(eid, slug)
            meta_by_sport[sk] = {"label": a.get("sport_label"), "icon": a.get("icon", "")}
            grid = a.get("data_quality", {}).get("grid_distance_km", grid)
            sources = a.get("data_sources", sources) or sources

        # SCORING is single-sourced from the freshly-fetched midday forecast so the
        # "now" gauge, the timeline (series[0]) and the weekly peaks all agree.
        # (The recorder sensors.json was a midnight capture; using it for scores
        # here would make now ≠ series[0]. See mockups/research/sample/README.)
        sports = {}
        for sk, sc in (fc.get("scores") or {}).items():
            best = sc.get("best") or {}
            bih = best.get("in_hours")
            lab = (meta_by_sport.get(sk) or {}).get("label") or _SPORT_META.get(sk, (sk.title(),))[0]
            sports[sk] = {
                "sport": sk,
                "label": lab,
                "icon": (meta_by_sport.get(sk) or {}).get("icon", ""),
                "score": round(sc["score"], 1) if sc.get("score") is not None else None,
                "verdict": sc.get("verdict"),
                "suitable": sc.get("suitable"),
                "factors": sc.get("factors", {}),
                "reasons": sc.get("reasons", []),
                "completeness": sc.get("completeness", {}),
                "nudges": sc.get("nudges", []),
                "best_score": best.get("score"),
                "best_in_h": bih,
                "best_verdict": best.get("verdict"),
                "best_time": hours[bih] if bih is not None and bih < len(hours) else None,
                "series": series_by_sport.get(sk),
                "daily": daily_by_sport.get(sk),
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
                "now_time": now_time,
                "hours": hours,
                "horizon_h": len(hours),
                "tide": tide,
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
        for mockup in MOCKUPS:
            if not mockup.exists():
                continue
            html = mockup.read_text()
            new = re.sub(
                r"/\*__DATA__\*/.*?/\*__END__\*/",
                f"/*__DATA__*/{blob}/*__END__*/",
                html,
                flags=re.S,
            )
            mockup.write_text(new)
            print(f"injected {len(blob)} bytes into {mockup.relative_to(ROOT)}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
