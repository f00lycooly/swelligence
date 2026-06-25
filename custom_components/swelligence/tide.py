"""Tide-aware scoring (pure, no Home Assistant / I/O).

A tide-dependent spot only works well around a particular tidal state — surf
breaks that need water over the reef (high), estuary launches that dry out
(low), or spots that fire on the run of the tide (mid / max flow). This module
turns a spot's tide preference + the forecast's high/low water events into a
0..1 suitability multiplier per timestep, which the scorer folds into the score.

Timezone note: Open-Meteo point times are naive *local* wall-clock, while tide
events (UKHO/CO-OPS/modeled) are UTC. :func:`to_utc_naive` collapses both to a
single UTC-naive basis so the hour arithmetic is correct — callers must convert
both sides before calling :func:`tide_factor`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

TIDE_STATE_ANY = "any"
TIDE_STATE_HIGH = "high"
TIDE_STATE_LOW = "low"
TIDE_STATE_MID = "mid"
TIDE_STATES: tuple[str, ...] = (
    TIDE_STATE_ANY,
    TIDE_STATE_HIGH,
    TIDE_STATE_LOW,
    TIDE_STATE_MID,
)

DEFAULT_TIDE_WINDOW_H = 2.0
# Wrong-tide floor: a tide-dependent spot at the wrong state still scores this
# fraction of its conditions score (a gate, not a hard zero).
TIDE_FLOOR = 0.3


def to_utc_naive(dt: datetime, *, local_offset_seconds: int = 0) -> datetime:
    """Collapse a datetime to a UTC-naive basis.

    Aware datetimes are converted to UTC and stripped. Naive datetimes are
    assumed to be *local* wall-clock and shifted to UTC by ``local_offset_seconds``
    (the forecast's UTC offset), then used as-is.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt - timedelta(seconds=local_offset_seconds)


def _hours_between(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds()) / 3600.0


def _target_time(events, when: datetime, state: str) -> datetime | None:
    """The reference time the spot wants to be near, in the events' basis."""
    if state in (TIDE_STATE_HIGH, TIDE_STATE_LOW):
        cands = [e for e in events if e.kind == state]
        if not cands:
            return None
        return min(cands, key=lambda e: _hours_between(e.time, when)).time
    if state == TIDE_STATE_MID:
        # Max flow ≈ midway in time between each consecutive pair of extremes.
        evs = sorted(events, key=lambda e: e.time)
        mids = [a.time + (b.time - a.time) / 2 for a, b in zip(evs, evs[1:])]
        if not mids:
            return None
        return min(mids, key=lambda m: _hours_between(m, when))
    return None


def tide_factor(
    events,
    when: datetime,
    state: str | None,
    window_h: float = DEFAULT_TIDE_WINDOW_H,
) -> tuple[float | None, str]:
    """Suitability multiplier in ``[TIDE_FLOOR, 1.0]`` for a tide preference.

    Returns ``(None, "")`` when tide scoring doesn't apply (state ``any``/unset or
    no events). ``events`` times and ``when`` must already share a basis (see
    :func:`to_utc_naive`). The factor is 1.0 at the preferred state, easing down
    to ``TIDE_FLOOR`` as the timestep moves away from it.
    """
    if state in (None, "", TIDE_STATE_ANY) or not events:
        return None, ""
    window_h = window_h or DEFAULT_TIDE_WINDOW_H
    target = _target_time(events, when, state)
    if target is None:
        return None, ""
    dt = _hours_between(when, target)
    factor = max(TIDE_FLOOR, 1.0 - 0.3 * (dt / window_h))
    note = f"near {state} tide" if dt <= window_h else f"{dt:.1f}h off {state} tide"
    return round(factor, 3), note


# ---------------------------------------------------------------------------
# Tide STATE — a ready-to-render data point for the cards/panel (not scoring).
#
# Honesty: the real high/low events come from a tide overlay (UKHO / NOAA /
# Open-Meteo modeled) when one covers the spot; only when no events exist do we
# fall back to the MODELLED sea-level trajectory and label it as such. Trend and
# next extreme are surfaced so the screens render without deriving anything.
# ---------------------------------------------------------------------------

#: Below this metre delta over ~3h the tide reads as standing (slack water).
_TIDE_SLACK_DELTA_M = 0.02


def _modelled_tide_state(points, levels):
    """(state, next-extreme) from the modelled sea-level trajectory. Tides move
    slowly, so judge the trend over the next ~3h rather than one noisy hour."""
    valid = [l for l in levels if l is not None]
    if len(valid) < 3:
        return "slack", None
    now_l = levels[0]
    fut = [l for l in levels[1:4] if l is not None]
    ahead = sum(fut) / len(fut) if fut else now_l
    if ahead > now_l + _TIDE_SLACK_DELTA_M:
        state, want = "rising", "high"
    elif ahead < now_l - _TIDE_SLACK_DELTA_M:
        state, want = "falling", "low"
    else:
        state, want = "slack", None
    for i in range(1, len(levels) - 1):
        a, b, c = levels[i - 1], levels[i], levels[i + 1]
        if None in (a, b, c):
            continue
        is_max, is_min = b >= a and b >= c, b <= a and b <= c
        match = (want == "high" and is_max) or (want == "low" and is_min) or (
            want is None and (is_max or is_min)
        )
        if match:
            kind = want or ("high" if is_max else "low")
            return state, {"type": kind, "time": points[i].time.strftime("%H:%M"),
                           "in_h": i, "level": round(b, 2)}
    return state, None


def _phase_from_levels(levels, i) -> str:
    """high/low (local extreme) else rising/falling/slack at index ``i``."""
    cur = levels[i] if 0 <= i < len(levels) else None
    if cur is None:
        return "slack"
    prv = next((levels[j] for j in range(i - 1, -1, -1) if levels[j] is not None), None)
    nxt = next((levels[j] for j in range(i + 1, len(levels)) if levels[j] is not None), None)
    if prv is not None and nxt is not None:
        if cur >= prv and cur >= nxt:
            return "high"
        if cur <= prv and cur <= nxt:
            return "low"
    ref = nxt if nxt is not None else cur
    if ref > cur + _TIDE_SLACK_DELTA_M:
        return "rising"
    if ref < cur - _TIDE_SLACK_DELTA_M:
        return "falling"
    return "slack"


def tide_phase(forecast, when, *, near_min: int = 45) -> dict | None:
    """Tide phase + height AT a given time — a ready-to-render data point for the
    weekly best-day readout. ``state`` ∈ {high, low, rising, falling, slack};
    ``height`` is metres (provider datum). Prefers the tide_events overlay;
    falls back to the modelled sea_level_m trajectory (``source`` says which)."""
    pts = forecast.points
    if not pts:
        return None
    i = min(range(len(pts)), key=lambda k: abs((pts[k].time - when).total_seconds()))
    height = pts[i].sea_level_m
    out: dict = {"height": round(height, 2) if height is not None else None}

    events = sorted(forecast.tide_events or [], key=lambda e: e.time)
    if events:
        out["source"] = "overlay"
        nearest = min(events, key=lambda e: abs((e.time - when).total_seconds()))
        if abs((nearest.time - when).total_seconds()) <= near_min * 60:
            out["state"] = nearest.kind  # "high" / "low"
            if out["height"] is None and nearest.height_m is not None:
                out["height"] = round(nearest.height_m, 2)
        else:
            nxt = next((e for e in events if e.time >= when), None)
            out["state"] = ("rising" if nxt and nxt.kind == "high"
                            else "falling" if nxt and nxt.kind == "low" else "slack")
        return out

    out["source"] = "modelled"
    out["state"] = _phase_from_levels([p.sea_level_m for p in pts], i)
    return out


def tide_state(forecast, *, now=None, horizon: int = 24) -> dict | None:
    """Current tide trend + the next high/low, as a ready-to-render data point.

    Prefers the real ``forecast.tide_events`` overlay; falls back to the modelled
    ``sea_level_m`` trajectory when no events exist (``source`` says which).
    ``levels`` is the near-term sea-level series (``horizon`` points) for a
    sparkline; ``next`` is ``{type, time, in_h, level}`` or absent.
    """
    points = forecast.points
    if not points:
        return None
    now = now or points[0].time
    near = [p.sea_level_m for p in points[:horizon]]
    valid = [l for l in near if l is not None]
    out: dict = {"levels": [round(l, 2) if l is not None else None for l in near]}
    if valid:
        out["now"] = round(near[0], 2) if near and near[0] is not None else None
        out["min"], out["max"] = round(min(valid), 2), round(max(valid), 2)

    upcoming = sorted((e for e in (forecast.tide_events or []) if e.time >= now),
                      key=lambda e: e.time)
    if upcoming:
        nxt = upcoming[0]
        out["source"] = "overlay"
        out["state"] = "rising" if nxt.kind == "high" else "falling"
        out["next"] = {
            "type": nxt.kind,
            "time": nxt.time.strftime("%H:%M"),
            "in_h": round((nxt.time - now).total_seconds() / 3600),
            "level": round(nxt.height_m, 2) if nxt.height_m is not None else None,
        }
        return out

    state, nxt = _modelled_tide_state(points, [p.sea_level_m for p in points])
    out["source"] = "modelled"
    out["state"] = state
    if nxt:
        out["next"] = nxt
    return out
