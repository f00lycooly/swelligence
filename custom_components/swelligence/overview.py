"""Pure aggregation for the overview cards.

Turns per-(spot, sport) hourly forecasts into:
  * sessions — contiguous runs of go-worthy hours (score >= threshold), for the
    Opportunity Timeline (and a Session Agenda).
  * podium — each day's top-N opportunities, preference-ranked, for the Top-3
    podium card.

No Home Assistant / I/O. Input is a list of entries, each:
    {"spot": str, "sport": str, "slots": [forecast-slot dicts]}
where a slot has at least: datetime (ISO), score (float|None), verdict (str),
and optionally kit_rig_m2.
"""

from __future__ import annotations

from .ranking import rank_score
from .scoring import SUITABLE_THRESHOLD


def _kit(slot: dict) -> str:
    v = slot.get("kit_rig_m2")
    return f"{v:g}m²" if v else ""


def _flush(out: list, entry: dict, run: list) -> None:
    if not run:
        return
    peak = max(run, key=lambda s: s["score"])
    out.append({
        "spot": entry["spot"],
        "sport": entry["sport"],
        "day": run[0]["datetime"][:10],
        "start": int(run[0]["datetime"][11:13]),
        "end": int(run[-1]["datetime"][11:13]) + 1,
        "peak": round(peak["score"]),
        "verdict": peak["verdict"],
        "kit": _kit(peak),
        "time": peak["datetime"][11:16],
    })


def build_sessions(entries: list[dict], good: float = SUITABLE_THRESHOLD) -> list[dict]:
    """Contiguous runs (per spot×sport) where score >= ``good``, sorted by time."""
    out: list[dict] = []
    for entry in entries:
        slots = sorted(entry["slots"], key=lambda s: s["datetime"])
        run: list[dict] = []
        prev_h = prev_d = None
        for s in slots:
            if s["score"] is None:
                continue
            h, d = int(s["datetime"][11:13]), s["datetime"][:10]
            if s["score"] >= good:
                if run and (h != prev_h + 1 or d != prev_d):
                    _flush(out, entry, run)
                    run = []
                run.append(s)
                prev_h, prev_d = h, d
            else:
                _flush(out, entry, run)
                run = []
                prev_h = prev_d = None
        _flush(out, entry, run)
    out.sort(key=lambda s: (s["day"], s["start"], -s["peak"]))
    return out


def build_podium(
    entries: list[dict], priority: list[str] | None = None, *, top: int = 3
) -> list[dict]:
    """Per-day top-N opportunities (sport @ spot), preference-ranked."""
    days = sorted({s["datetime"][:10] for e in entries for s in e["slots"]})
    result: list[dict] = []
    for day in days:
        cands: list[dict] = []
        for entry in entries:
            day_slots = [
                s for s in entry["slots"]
                if s["datetime"][:10] == day and s["score"] is not None
            ]
            if not day_slots:
                continue
            peak = max(day_slots, key=lambda s: s["score"])
            cands.append({
                "sport": entry["sport"],
                "spot": entry["spot"],
                "score": round(peak["score"]),
                "verdict": peak["verdict"],
                "kit": _kit(peak),
                "time": peak["datetime"][11:16],
                "_rank": rank_score(peak["score"], entry["sport"], priority),
            })
        cands.sort(key=lambda c: -c["_rank"])
        ranks = []
        for i, c in enumerate(cands[:top]):
            c.pop("_rank", None)
            ranks.append({"place": i + 1, **c})
        result.append({"day": day, "ranks": ranks})
    return result
