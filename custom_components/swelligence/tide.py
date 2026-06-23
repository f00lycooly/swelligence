"""Tide-aware scoring (pure, no Home Assistant / I/O).

A tide-dependent spot only works well around a particular tidal state — surf
breaks that need water over the reef (high), estuary launches that dry out
(low), or spots that fire on the run of the tide (mid / max flow). This module
turns a spot's tide preference + the forecast's high/low water events into a
0..1 suitability multiplier per timestep, which the scorer folds into the score.

Timezone note: Open-Meteo point times are naive *local* wall-clock, while tide
events (Stormglass/UKHO) are UTC. :func:`to_utc_naive` collapses both to a
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
