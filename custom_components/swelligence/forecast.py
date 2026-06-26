"""Pure forecast builders — turn scored points into hourly/daily timelines.

Used by the ``swelligence.get_forecast`` service (HA weather best-practice:
forecasts are served by a service, not entity state/attributes). No I/O; the
SpotForecast is already fetched by the coordinator.

Slots are restricted to a padded daylight window (sunrise − pad .. sunset + pad)
so dawn-patrol / evening sessions are kept but the dead of night is dropped.
Kit recommendations are computed per timestep, since wind varies through the day.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .providers.base import ForecastPoint, SpotForecast
from .scoring import blend_kit, score_point
from .sizing import POWER_NA, recommend_kit
from .sports import SportProfile

DEFAULT_DAYLIGHT_PAD_H = 2


def _naive(t: datetime) -> datetime:
    """Drop tz info so naive-local point times compare cleanly."""
    return t.replace(tzinfo=None) if t.tzinfo is not None else t


def anchor_to_now(forecast: SpotForecast, *, now: datetime | None = None) -> SpotForecast:
    """Trim leading past hours so ``points[0]`` is the current hour.

    Open-Meteo returns hourly data from local midnight, so the raw series starts
    at 00:00. The coordinator anchors it once per refresh so every consumer
    (sensors, services, the card) sees a now-forward series and
    ``forecast.current()`` genuinely means "now". Point times are naive *local*;
    the provider's ``utc_offset_seconds`` converts UTC now into that frame.

    Returns a shallow copy with a sliced point list (the source forecast — e.g.
    the batch-loader cache — keeps its full series for the next refresh). A
    no-op when nothing precedes the current hour, or when the whole series is in
    the past (keeps the final point so ``current()`` still returns something).
    """
    pts = forecast.points
    if not pts:
        return forecast
    offset = (forecast.source_meta or {}).get("utc_offset_seconds", 0) or 0
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    now_local = (base.astimezone(timezone.utc) + timedelta(seconds=offset)).replace(tzinfo=None)
    cur_hour = now_local.replace(minute=0, second=0, microsecond=0)
    idx = next((i for i, p in enumerate(pts) if _naive(p.time) >= cur_hour), len(pts) - 1)
    return forecast if idx <= 0 else replace(forecast, points=pts[idx:])


def _in_daylight(point_time, daily_sun: dict, pad_h: int) -> bool:
    info = daily_sun.get(point_time.date().isoformat())
    if not info or not info.get("sunrise") or not info.get("sunset"):
        return True  # no sun data -> don't filter
    return (
        info["sunrise"] - timedelta(hours=pad_h)
        <= point_time
        <= info["sunset"] + timedelta(hours=pad_h)
    )


def _slot(
    point: ForecastPoint,
    profile: SportProfile,
    sport: str,
    weight: float,
    quiver_sizes: list[float] | None,
) -> dict:
    res = score_point(point, profile)
    kit = None
    if weight:
        rec = recommend_kit(sport, weight, point.wind_speed_kn, quiver_sizes)
        if rec.power != POWER_NA:
            res = blend_kit(res, rec.factor)
            kit = rec
    slot = {
        "datetime": point.time.isoformat(),
        "score": res.score,
        "verdict": res.verdict,
        "suitable": res.suitable,
        "wind_speed_kn": point.wind_speed_kn,
        "wind_gust_kn": point.wind_gust_kn,
        "wind_bearing": point.wind_dir_deg,
        "wave_height_m": point.wave_height_m,
        "swell_height_m": point.swell_height_m,
        "swell_period_s": point.swell_period_s,
        "swell_peak_period_s": point.swell_peak_period_s,
        "wind_wave_height_m": point.wind_wave_height_m,
        "current_speed_kn": point.current_speed_kn,
        "sea_level_m": point.sea_level_m,
        "water_temp_c": point.water_temp_c,
        "apparent_temp_c": point.apparent_temp_c,
        "weather_code": point.weather_code,
    }
    if kit is not None:
        slot["kit_ideal_m2"] = kit.ideal_size_m2
        slot["kit_rig_m2"] = kit.owned_size_m2
        slot["kit_power"] = kit.power
    return slot


def hourly_forecast(
    forecast: SpotForecast,
    profile: SportProfile,
    sport: str,
    weight: float = 0,
    quiver_sizes: list[float] | None = None,
    *,
    pad_h: int = DEFAULT_DAYLIGHT_PAD_H,
) -> list[dict]:
    """Hourly suitability slots within the padded daylight window."""
    return [
        _slot(p, profile, sport, weight, quiver_sizes)
        for p in forecast.points
        if _in_daylight(p.time, forecast.daily_sun, pad_h)
    ]


def daily_forecast(
    forecast: SpotForecast,
    profile: SportProfile,
    sport: str,
    weight: float = 0,
    quiver_sizes: list[float] | None = None,
    *,
    pad_h: int = DEFAULT_DAYLIGHT_PAD_H,
) -> list[dict]:
    """One entry per day = that day's best slot."""
    best_by_day: dict[str, dict] = {}
    for slot in hourly_forecast(
        forecast, profile, sport, weight, quiver_sizes, pad_h=pad_h
    ):
        day = slot["datetime"][:10]
        if day not in best_by_day or slot["score"] > best_by_day[day]["score"]:
            best_by_day[day] = slot
    out: list[dict] = []
    for day in sorted(best_by_day):
        entry = dict(best_by_day[day])
        entry["date"] = day
        out.append(entry)
    return out
