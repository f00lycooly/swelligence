"""Per-spot now/week detail payloads.

Two consumers share the same source of truth so the panel and the Lovelace card
never drift:

* ``spot_detail`` — rich nested payload for the ``get_spot_detail`` service (the
  spot-detail Lovelace card renders it directly; the screen derives nothing).
* ``spot_panel_payload`` — the *same* data flattened into HA-attribute-friendly
  scalars + delimited arrays. An ESPHome LVGL panel binds entity attributes and
  has no on-device JSON parser, so nested structures are reshaped into flat
  scalars and CSV/pipe-delimited strings it can split in a lambda.
"""

from __future__ import annotations

from datetime import datetime

from .forecast import daylight_remaining
from .sizing import kit_payload
from .sports import SPORT_PROFILES
from .tide import tide_phase, tide_state

# Raw now-conditions surfaced verbatim to the spot-detail card (normalised units).
NOW_FIELDS = (
    "wind_speed_kn", "wind_gust_kn", "wind_dir_deg", "wave_height_m", "wave_period_s",
    "wave_dir_deg", "swell_height_m", "swell_period_s", "swell_peak_period_s",
    "swell_dir_deg", "wind_wave_height_m", "current_speed_kn", "current_dir_deg",
    "sea_level_m", "water_temp_c", "air_temp_c", "apparent_temp_c", "uv_index",
    "visibility_m", "weather_code", "precip_mm", "precip_prob_pct", "cloud_pct",
)

# Verdict -> 1-char code: keeps the per-hour / per-day verdict CSVs tiny so the
# whole panel payload stays well under HA's attribute-size budget.
VERDICT_CODE = {"epic": "e", "great": "g", "good": "o", "marginal": "m", "poor": "p"}

# Array-valued (high-churn) panel attributes kept OUT of the recorder DB. Built
# from the bounded sport set so every per-sport timeline/week CSV is covered.
_ARRAY_SUFFIXES = (
    "factors",
    "hourly_scores", "hourly_verdicts",
    "week_scores", "week_times", "week_verdicts",
    "week_wind", "week_gust", "week_dir", "week_wave", "week_swell",
    "week_per", "week_water", "week_tide_state", "week_tide_h",
    "week_rain", "week_rain_prob", "week_air",
)
# Spot-level (non-per-sport) high-churn arrays.
_SPOT_ARRAYS = ("tide_levels", "hours", "week_days", "week_dates")
PANEL_UNRECORDED = frozenset(
    set(_SPOT_ARRAYS)
    | {f"{sport}_{suf}" for sport in SPORT_PROFILES for suf in _ARRAY_SUFFIXES}
)


def best_clock(forecast, best_offset_h) -> str | None:
    """Local ``HH:MM`` of the best-window slot, from the now-anchored forecast.

    ``best_offset_h`` indexes ``forecast.points`` (it's the index ``best_window``
    returned), so the slot time is ``points[offset].time`` — the authoritative
    source. Shared by the per-sport :class:`SuitabilitySensor` and the panel
    detail sensor so both render the same clock for the same offset. ``None`` when
    there is no best slot or the offset falls outside the available points.
    """
    if best_offset_h is None:
        return None
    points = forecast.points
    if 0 <= best_offset_h < len(points):
        return points[best_offset_h].time.strftime("%H:%M")
    return None


def spot_detail(coordinator, data, sports_f: set) -> dict:
    """One spot's full now/week detail — every time-varying value ready to render
    (the screen derives nothing). Live forecast is now-anchored (points[0] == now),
    so hourly[0]/daily[0]/tide all align without slicing."""
    forecast = data.forecast
    now_pt = forecast.current()
    sports: list[dict] = []
    for sport, res in data.results.items():
        if sports_f and sport not in sports_f:
            continue
        profile = coordinator.profile(sport)
        # Continuous next-24h hourly (keep every hour; large pad disables the
        # daylight filter) + the daytime-only daily peak (strict sunrise..sunset).
        hourly = coordinator.build_forecast(sport, "hourly", pad_h=999, horizon=24)
        daily = coordinator.build_forecast(sport, "daily", pad_h=0)
        for entry in daily:
            entry["tide"] = tide_phase(forecast, datetime.fromisoformat(entry["datetime"]))
        best = None
        if res.best is not None:
            best = {
                "score": round(res.best.score),
                "in_hours": res.best_offset_h,
                "verdict": res.best.verdict,
                "time": best_clock(forecast, res.best_offset_h),
            }
        sports.append({
            "sport": sport,
            "label": profile.label if profile else sport,
            "now": {
                "score": round(res.now.score), "verdict": res.now.verdict,
                "suitable": res.now.suitable, "factors": res.now.factors,
                "reasons": res.now.reasons, "completeness": res.now.completeness,
                "nudges": res.now.nudges,
                "kit": kit_payload(res.kit),
            },
            "best": best,
            "hourly": hourly,
            "daily": daily,
        })
    return {
        "name": coordinator.spot["name"],
        "water_type": coordinator.spot.get("water_type", "sea"),
        "latitude": coordinator.spot["latitude"],
        "longitude": coordinator.spot["longitude"],
        "now_time": now_pt.time.strftime("%H:%M") if now_pt else None,
        "daylight": daylight_remaining(forecast),
        "tide": tide_state(forecast),
        "current": {f: getattr(now_pt, f, None) for f in NOW_FIELDS} if now_pt else {},
        "sports": sports,
    }


def _csv(values) -> str:
    """Comma-join, rendering None as an empty field so positions stay aligned."""
    return ",".join("" if v is None else str(v) for v in values)


def _verdict_csv(slots) -> str:
    return ",".join(VERDICT_CODE.get(s.get("verdict"), "") for s in slots)


def _i(v):
    return None if v is None else round(v)


def _rcsv(values, n: int = 1) -> str:
    """CSV of values rounded to ``n`` dp (0 → int), None held as an empty field."""
    return _csv(None if v is None else (round(v, n) if n else round(v)) for v in values)


def _factor_csv(factors: dict | None) -> str:
    """Per-sport factor breakdown as ``key:score`` pairs (rounded int), in the
    scorer's own factor order, so the panel can render the breakdown bars without
    a fixed key list (factor sets differ by sport — e.g. surf has swell, SUP
    doesn't)."""
    return ",".join(f"{k}:{round(v)}" for k, v in (factors or {}).items() if v is not None)


def spot_panel_payload(coordinator, data) -> dict:
    """``spot_detail`` flattened for an ESPHome panel — see ``flatten_detail``."""
    return flatten_detail(spot_detail(coordinator, data, set()))


def flatten_detail(d: dict) -> dict:
    """``spot_detail`` flattened for an ESPHome panel: flat scalars + delimited
    arrays only (no nested dicts/lists), so the panel can bind each value and
    split the CSV/pipe strings in a lambda. Pure (dict in, dict out) so the whole
    encoding is unit-testable without a live coordinator."""
    tide = d.get("tide") or {}
    nxt = tide.get("next") or {}
    cur = d.get("current") or {}
    day = d.get("daylight") or {}

    attrs: dict = {
        "name": d["name"],
        "water_type": d["water_type"],
        "now_time": d["now_time"],
        "lat": d["latitude"],
        "lon": d["longitude"],
        # Daylight: sunrise/sunset clock + minutes left + elapsed fraction
        # (lets the panel place a sun marker / show a sunset countdown).
        "sunrise": day.get("sunrise"),
        "sunset": day.get("sunset"),
        "daylight_remaining_min": day.get("remaining_min"),
        "daylight_progress": day.get("progress"),
        # Now conditions (raw units, verbatim from the scorer's inputs).
        "wind_kn": cur.get("wind_speed_kn"),
        "gust_kn": cur.get("wind_gust_kn"),
        "wind_dir_deg": cur.get("wind_dir_deg"),
        "wave_m": cur.get("wave_height_m"),
        # wind-wave fallback for the now-strip Wave cell when total wave is
        # unknown (sheltered spots often have wave_m None but a wind_wave value).
        "wind_wave_m": cur.get("wind_wave_height_m"),
        "swell_m": cur.get("swell_height_m"),
        "swell_period_s": cur.get("swell_period_s"),
        # Comfort/safety weather (now).
        "precip_mm": cur.get("precip_mm"),
        "precip_prob_pct": cur.get("precip_prob_pct"),
        "air_temp_c": cur.get("air_temp_c"),
        "apparent_temp_c": cur.get("apparent_temp_c"),
        "uv_index": cur.get("uv_index"),
        "visibility_m": cur.get("visibility_m"),
        "cloud_pct": cur.get("cloud_pct"),
        "weather_code": cur.get("weather_code"),
        # Marine quality (now).
        "wave_period_s": cur.get("wave_period_s"),
        "wave_dir_deg": cur.get("wave_dir_deg"),
        "swell_dir_deg": cur.get("swell_dir_deg"),
        "current_speed_kn": cur.get("current_speed_kn"),
        "current_dir_deg": cur.get("current_dir_deg"),
        "water_temp_c": cur.get("water_temp_c"),
        # Tide — honesty label carried verbatim (modelled vs overlay).
        "tide_state": tide.get("state"),
        "tide_source": tide.get("source"),
        "tide_now_m": tide.get("now"),
        "tide_levels": _csv(tide.get("levels") or []),
        "tide_next_type": nxt.get("type"),
        "tide_next_time": nxt.get("time"),
        "tide_next_in_h": nxt.get("in_h"),
        "tide_next_level_m": nxt.get("level"),
    }

    sports = d.get("sports") or []
    # Fixed sport order drives the panel's selector pills + per-sport lookups.
    attrs["sports"] = "|".join(s["sport"] for s in sports)
    attrs["sport_labels"] = "|".join(s["label"] for s in sports)
    # Spot-level time axes — identical across sports (shared daylight window), so
    # carried once. `hours` labels the 24h timeline x-axis; `week_days`/
    # `week_dates` label the weekly day rows (index 0 is always "Today", matching
    # the card's daily[0]==today convention) and the header date range.
    ref = sports[0] if sports else {}
    attrs["hours"] = ",".join(h["datetime"][11:16] for h in ref.get("hourly") or [])
    week = ref.get("daily") or []
    attrs["week_days"] = ",".join(
        "Today" if i == 0 else datetime.fromisoformat(e["datetime"]).strftime("%a")
        for i, e in enumerate(week)
    )
    attrs["week_dates"] = ",".join(e["date"] for e in week)
    # Spot-level headline = the best-scoring sport right now. Statically named so
    # the panel's NOW gauge/verdict bind without knowing each spot's sport list
    # (per-sport attribute names like `kitesurf_now_score` vary by spot).
    headline = max(
        sports,
        key=lambda s: (s.get("now") or {}).get("score") or -1,
        default=None,
    )
    if headline:
        hnow = headline.get("now") or {}
        attrs["headline_sport"] = headline["sport"]
        attrs["headline_label"] = headline["label"]
        attrs["headline_score"] = hnow.get("score")
        attrs["headline_verdict"] = hnow.get("verdict")
        attrs["headline_suitable"] = hnow.get("suitable")
    for s in sports:
        k = s["sport"]
        now = s.get("now") or {}
        best = s.get("best") or {}
        hourly = s.get("hourly") or []
        daily = s.get("daily") or []
        attrs[f"{k}_now_score"] = now.get("score")
        attrs[f"{k}_now_verdict"] = now.get("verdict")
        attrs[f"{k}_now_suitable"] = now.get("suitable")
        attrs[f"{k}_best_score"] = best.get("score")
        attrs[f"{k}_best_in_h"] = best.get("in_hours")
        attrs[f"{k}_best_verdict"] = best.get("verdict")
        attrs[f"{k}_best_time"] = best.get("time")
        # Kit sizing (rig sports only; None for swim/SUP/surf -> empty fields).
        kit = now.get("kit") or {}
        attrs[f"{k}_kit_power"] = kit.get("power")
        attrs[f"{k}_kit_rig_m2"] = kit.get("rig_m2")
        attrs[f"{k}_kit_ideal_m2"] = kit.get("ideal_m2")
        # Optional factor-breakdown bars (key:score pairs, scorer's own order).
        attrs[f"{k}_factors"] = _factor_csv(now.get("factors"))
        # Next-24h timeline (lv_chart) + per-bar verdict colour codes.
        attrs[f"{k}_hourly_scores"] = _csv(_i(h.get("score")) for h in hourly)
        attrs[f"{k}_hourly_verdicts"] = _verdict_csv(hourly)
        # 7-day daytime-peak rows: score, best-time, verdict colour.
        attrs[f"{k}_week_scores"] = _csv(_i(e.get("score")) for e in daily)
        attrs[f"{k}_week_times"] = ",".join(e["datetime"][11:16] for e in daily)
        attrs[f"{k}_week_verdicts"] = _verdict_csv(daily)
        # Peak-hour conditions per day (the best-day pane's detail readout —
        # wind/gust/dir/wave/swell/period/water + tide phase/height annotated
        # server-side). Aligned position-for-position with week_days/_scores.
        attrs[f"{k}_week_wind"] = _rcsv(e.get("wind_speed_kn") for e in daily)
        attrs[f"{k}_week_gust"] = _rcsv(e.get("wind_gust_kn") for e in daily)
        attrs[f"{k}_week_dir"] = _csv(_i(e.get("wind_bearing")) for e in daily)
        attrs[f"{k}_week_wave"] = _rcsv(e.get("wave_height_m") for e in daily)
        attrs[f"{k}_week_swell"] = _rcsv(e.get("swell_height_m") for e in daily)
        attrs[f"{k}_week_per"] = _rcsv(e.get("swell_period_s") for e in daily)
        attrs[f"{k}_week_water"] = _rcsv(e.get("water_temp_c") for e in daily)
        attrs[f"{k}_week_rain"] = _rcsv(e.get("precip_mm") for e in daily)
        attrs[f"{k}_week_rain_prob"] = _csv(_i(e.get("precip_prob_pct")) for e in daily)
        attrs[f"{k}_week_air"] = _rcsv(e.get("air_temp_c") for e in daily)
        attrs[f"{k}_week_tide_state"] = _csv(
            (e.get("tide") or {}).get("state") for e in daily
        )
        attrs[f"{k}_week_tide_h"] = _rcsv(
            ((e.get("tide") or {}).get("height") for e in daily), 2
        )
        # Index of the peak (max-score) day so the panel anchors the best-day
        # pane without an argmax in a lambda (thin renderer).
        scores = [e.get("score") for e in daily]
        attrs[f"{k}_week_peak_idx"] = (
            max(range(len(scores)), key=lambda i: scores[i] if scores[i] is not None else -1)
            if scores else None
        )
    return attrs


def panel_headline(data) -> int | None:
    """Best current sport score at the spot — the detail sensor's state / the
    spot-tab headline number."""
    results = getattr(data, "results", None) or {}
    scores = [
        round(res.now.score)
        for res in results.values()
        if res and res.now is not None
    ]
    return max(scores) if scores else None
