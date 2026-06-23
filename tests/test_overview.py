"""Unit tests for overview aggregation (sessions + podium)."""

from __future__ import annotations

from swelligence.overview import build_podium, build_sessions


def slot(dt, score, verdict, kit=None):
    s = {"datetime": dt, "score": score, "verdict": verdict}
    if kit is not None:
        s["kit_rig_m2"] = kit
    return s


def _entry(spot, sport, slots):
    return {"spot": spot, "sport": sport, "slots": slots}


def test_sessions_detect_contiguous_runs():
    # Two good runs separated by a poor hour -> two sessions.
    slots = [
        slot("2026-06-27T09:00", 40, "marg"),
        slot("2026-06-27T10:00", 70, "great"),
        slot("2026-06-27T11:00", 75, "great"),
        slot("2026-06-27T12:00", 30, "poor"),
        slot("2026-06-27T13:00", 60, "good"),
    ]
    s = build_sessions([_entry("Hurst", "kitesurf", slots)])
    assert len(s) == 2
    assert (s[0]["start"], s[0]["end"], s[0]["peak"]) == (10, 12, 75)
    assert s[1]["start"] == 13 and s[1]["end"] == 14


def test_sessions_split_across_days():
    slots = [
        slot("2026-06-27T20:00", 70, "great"),
        slot("2026-06-28T06:00", 72, "great"),
    ]
    s = build_sessions([_entry("Hurst", "kitesurf", slots)])
    assert len(s) == 2  # different days never merge


def test_sessions_threshold():
    slots = [slot("2026-06-27T10:00", 50, "marg")]  # below 55
    assert build_sessions([_entry("X", "surf", slots)]) == []


def test_podium_ranks_top3_by_score():
    day = "2026-06-27"
    entries = [
        _entry("A", "surf", [slot(f"{day}T10:00", 80, "great")]),
        _entry("B", "kitesurf", [slot(f"{day}T11:00", 60, "good")]),
        _entry("C", "sup", [slot(f"{day}T12:00", 90, "epic")]),
        _entry("D", "wingfoil", [slot(f"{day}T13:00", 40, "marg")]),
    ]
    pod = build_podium(entries)
    ranks = pod[0]["ranks"]
    assert [r["score"] for r in ranks] == [90, 80, 60]
    assert [r["place"] for r in ranks] == [1, 2, 3]


def test_podium_preference_reorders_close_scores():
    day = "2026-06-27"
    entries = [
        _entry("Lake", "wakeboard_inland", [slot(f"{day}T10:00", 72, "great")]),
        _entry("Hurst", "wingfoil", [slot(f"{day}T11:00", 70, "great")]),
    ]
    # Without preference: wake first (higher raw).
    assert build_podium(entries)[0]["ranks"][0]["sport"] == "wakeboard_inland"
    # With wing preferred: wing surfaces to 1st despite slightly lower raw.
    pri = ["wingfoil", "kitesurf", "wakeboard_inland"]
    assert build_podium(entries, pri)[0]["ranks"][0]["sport"] == "wingfoil"


def test_podium_per_day():
    entries = [
        _entry("A", "surf", [
            slot("2026-06-27T10:00", 80, "great"),
            slot("2026-06-28T10:00", 40, "marg"),
        ]),
    ]
    pod = build_podium(entries)
    assert [p["day"] for p in pod] == ["2026-06-27", "2026-06-28"]
    assert pod[0]["ranks"][0]["score"] == 80
