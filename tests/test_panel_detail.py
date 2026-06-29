"""Panel transport encoding — the flat/delimited contract the ESPHome panel
binds. The full spot_panel_payload (needs a live coordinator) is exercised in the
live-HA harness; here we lock the pure encoding helpers so the panel-side lambda
parsing never silently drifts."""

from __future__ import annotations

from types import SimpleNamespace

from datetime import datetime

from swelligence.detail import (
    PANEL_UNRECORDED,
    VERDICT_CODE,
    _csv,
    _factor_csv,
    _rcsv,
    _verdict_csv,
    best_clock,
    flatten_detail,
    panel_headline,
)
from swelligence.sports import SPORT_PROFILES


# --- best_clock (shared best-slot HH:MM helper, d1r.1) ----------------------

def _fc(*hours):
    """A now-anchored forecast: points[i].time at the given local hours."""
    pts = [SimpleNamespace(time=datetime(2026, 6, 25, h, 0)) for h in hours]
    return SimpleNamespace(points=pts)


def test_best_clock_returns_local_hhmm_at_offset():
    fc = _fc(12, 13, 14, 15)
    assert best_clock(fc, 0) == "12:00"
    assert best_clock(fc, 3) == "15:00"


def test_best_clock_none_when_no_best():
    assert best_clock(_fc(12, 13), None) is None


def test_best_clock_none_when_offset_out_of_range():
    fc = _fc(12, 13)
    assert best_clock(fc, 5) is None
    assert best_clock(fc, -1) is None


def test_best_clock_none_when_no_points():
    assert best_clock(SimpleNamespace(points=[]), 0) is None


def test_csv_renders_none_as_empty_field_keeping_positions():
    # Positional CSV: a missing hour must hold its slot, not collapse the series.
    assert _csv([3, None, 7]) == "3,,7"
    assert _csv([]) == ""


def test_verdict_csv_uses_one_char_codes():
    slots = [{"verdict": "epic"}, {"verdict": "poor"}, {"verdict": None}, {}]
    # epic->e, poor->p, missing->empty; positions preserved.
    assert _verdict_csv(slots) == "e,p,,"


def test_verdict_code_covers_the_semantic_palette():
    assert set(VERDICT_CODE) == {"epic", "great", "good", "marginal", "poor"}
    # Codes are unique (the panel maps code->colour 1:1).
    assert len(set(VERDICT_CODE.values())) == len(VERDICT_CODE)


def test_panel_headline_is_best_current_score():
    data = SimpleNamespace(results={
        "kitesurf": SimpleNamespace(now=SimpleNamespace(score=14.2)),
        "wing_foil": SimpleNamespace(now=SimpleNamespace(score=58.6)),
        "sup": SimpleNamespace(now=None),
    })
    assert panel_headline(data) == 59  # max, rounded


def test_panel_headline_handles_no_data():
    assert panel_headline(None) is None
    assert panel_headline(SimpleNamespace(results={})) is None


def test_unrecorded_set_covers_every_sport_array_attribute():
    # Every per-sport timeline/week CSV must be excluded from the recorder.
    for sport in SPORT_PROFILES:
        for suffix in ("factors", "hourly_scores", "hourly_verdicts",
                       "week_scores", "week_times", "week_verdicts",
                       "week_wind", "week_gust", "week_dir", "week_wave",
                       "week_swell", "week_per", "week_water",
                       "week_tide_state", "week_tide_h"):
            assert f"{sport}_{suffix}" in PANEL_UNRECORDED
    for spot_array in ("tide_levels", "hours", "week_days", "week_dates"):
        assert spot_array in PANEL_UNRECORDED


def test_rcsv_rounds_and_holds_none():
    assert _rcsv([10.46, None, 7.0]) == "10.5,,7.0"
    assert _rcsv([95.4, None], 0) == "95,"          # n=0 -> int
    assert _rcsv([-0.634, 0.1], 2) == "-0.63,0.1"


def test_factor_csv_pairs_in_scorer_order_dropping_none():
    # key:score pairs, rounded int, scorer's own order; None factors dropped.
    assert _factor_csv({"wind": 67.2, "gust": 40.0, "wave": None}) == "wind:67,gust:40"
    assert _factor_csv(None) == ""
    assert _factor_csv({}) == ""


def _slot(dt, score, verdict, **cond):
    return {"datetime": dt, "score": score, "verdict": verdict, **cond}


def _detail():
    """A two-sport spot_detail dict (the shape spot_detail() emits): one sea spot
    with a sheltered-style None wave on day 2, exercising alignment + None holes."""
    return {
        "name": "Avon", "water_type": "sea", "latitude": 50.7, "longitude": -1.7,
        "now_time": "12:00",
        "daylight": {"sunrise": "05:00", "sunset": "21:30",
                     "remaining_min": 570, "progress": 0.42},
        "tide": {"state": "rising", "source": "modelled", "now": -0.6,
                 "levels": [-0.6, -0.4, None, 0.1],
                 "next": {"type": "high", "time": "18:00", "in_h": 6, "level": 0.1}},
        "current": {"wind_speed_kn": 13.2, "wind_gust_kn": 26.0, "wind_dir_deg": 94,
                    "wave_height_m": 0.66, "wind_wave_height_m": 0.6,
                    "swell_height_m": 0.2, "swell_period_s": 4.3, "water_temp_c": 19.6},
        "sports": [
            {
                "sport": "kitesurf", "label": "Kitesurf",
                "now": {"score": 81, "verdict": "great", "suitable": True,
                        "factors": {"wind": 66.0, "gust": 100.0, "wave": 100.0},
                        "kit": {"power": "powered", "rig_m2": 9.0, "ideal_m2": 8.4}},
                "best": {"score": 83, "in_hours": 1, "verdict": "great", "time": "13:00"},
                "hourly": [_slot("2026-06-25T12:00:00", 81, "great"),
                           _slot("2026-06-25T13:00:00", 83, "great")],
                "daily": [
                    _slot("2026-06-25T13:00:00", 83, "great", date="2026-06-25",
                          wind_speed_kn=14.0, wind_gust_kn=27.8, wind_bearing=96.4,
                          wave_height_m=0.7, swell_height_m=0.2, swell_period_s=4.5,
                          water_temp_c=19.7, tide={"state": "low", "height": -0.64}),
                    _slot("2026-06-26T16:00:00", 79, "great", date="2026-06-26",
                          wind_speed_kn=12.4, wind_gust_kn=23.9, wind_bearing=234.0,
                          wave_height_m=None, swell_height_m=0.3, swell_period_s=3.7,
                          water_temp_c=20.3, tide={"state": "rising", "height": -0.45}),
                ],
            },
            {
                "sport": "sup", "label": "SUP",
                "now": {"score": 0, "verdict": "poor", "suitable": False,
                        "factors": {"wind": 0.0, "gust": 0.0}, "kit": {}},
                "best": {"score": 76, "in_hours": 19, "verdict": "great", "time": "07:00"},
                "hourly": [_slot("2026-06-25T12:00:00", 0, "poor"),
                           _slot("2026-06-25T13:00:00", 0, "poor")],
                "daily": [
                    _slot("2026-06-25T19:00:00", 30, "poor", date="2026-06-25",
                          wind_speed_kn=10.5, wind_gust_kn=20.6, wind_bearing=94.0,
                          wave_height_m=0.8, swell_height_m=0.3, swell_period_s=4.4,
                          water_temp_c=19.9, tide={"state": "falling", "height": -0.09}),
                    _slot("2026-06-26T07:00:00", 76, "great", date="2026-06-26",
                          wind_speed_kn=6.0, wind_gust_kn=11.5, wind_bearing=282.0,
                          wave_height_m=0.3, swell_height_m=0.3, swell_period_s=3.1,
                          water_temp_c=19.7, tide={"state": "falling", "height": -0.19}),
                ],
            },
        ],
    }


def test_flatten_exposes_now_strip_with_wind_wave_fallback_field():
    a = flatten_detail(_detail())
    assert a["wind_kn"] == 13.2 and a["gust_kn"] == 26.0 and a["wind_dir_deg"] == 94
    assert a["wave_m"] == 0.66 and a["swell_m"] == 0.2
    # wind_wave_m carried so the panel's Wave cell can fall back when wave is None.
    assert a["wind_wave_m"] == 0.6


def test_flatten_carries_tide_and_daylight_scalars():
    a = flatten_detail(_detail())
    assert a["tide_state"] == "rising" and a["tide_source"] == "modelled"
    assert a["tide_next_type"] == "high" and a["tide_next_in_h"] == 6
    assert a["tide_levels"] == "-0.6,-0.4,,0.1"      # None held as empty field
    assert a["daylight_remaining_min"] == 570


def test_flatten_spot_level_time_axes():
    a = flatten_detail(_detail())
    assert a["hours"] == "12:00,13:00"
    # index 0 is "Today"; the rest are weekday abbreviations of their date.
    assert a["week_days"] == "Today,Fri"            # 2026-06-26 is a Friday
    assert a["week_dates"] == "2026-06-25,2026-06-26"


def test_flatten_per_sport_week_conditions_align_and_hold_none():
    a = flatten_detail(_detail())
    assert a["kitesurf_week_scores"] == "83,79"
    assert a["kitesurf_week_times"] == "13:00,16:00"
    assert a["kitesurf_week_verdicts"] == "g,g"
    assert a["kitesurf_week_wind"] == "14.0,12.4"
    assert a["kitesurf_week_gust"] == "27.8,23.9"
    assert a["kitesurf_week_dir"] == "96,234"       # rounded to int
    assert a["kitesurf_week_wave"] == "0.7,"        # day-2 wave None -> empty slot
    assert a["kitesurf_week_per"] == "4.5,3.7"
    assert a["kitesurf_week_water"] == "19.7,20.3"
    assert a["kitesurf_week_tide_state"] == "low,rising"
    assert a["kitesurf_week_tide_h"] == "-0.64,-0.45"


def test_flatten_week_peak_idx_points_to_max_score_day():
    a = flatten_detail(_detail())
    assert a["kitesurf_week_peak_idx"] == 0          # 83 > 79
    assert a["sup_week_peak_idx"] == 1               # 76 > 30


def test_flatten_factors_and_headline():
    a = flatten_detail(_detail())
    assert a["kitesurf_factors"] == "wind:66,gust:100,wave:100"
    assert a["sports"] == "kitesurf|sup" and a["sport_labels"] == "Kitesurf|SUP"
    # Headline = best-scoring sport right now (kitesurf 81 > sup 0).
    assert a["headline_sport"] == "kitesurf" and a["headline_score"] == 81


def test_flatten_handles_no_sports():
    d = {"name": "X", "water_type": "sea", "latitude": 0, "longitude": 0,
         "now_time": None, "daylight": {}, "tide": {}, "current": {}, "sports": []}
    a = flatten_detail(d)
    assert a["sports"] == "" and a["hours"] == "" and a["week_days"] == ""


def test_flatten_surfaces_comfort_and_marine_now_fields():
    from swelligence.detail import flatten_detail

    d = {
        "name": "X", "water_type": "sea", "now_time": "12:00",
        "latitude": 1.0, "longitude": 2.0,
        "current": {
            "precip_mm": 2.1, "precip_prob_pct": 70, "air_temp_c": 14.0,
            "apparent_temp_c": 11.0, "uv_index": 3, "visibility_m": 8000,
            "cloud_pct": 40, "weather_code": 61, "wave_period_s": 7.0,
            "wave_dir_deg": 220, "swell_dir_deg": 230, "current_speed_kn": 0.5,
            "current_dir_deg": 180,
        },
        "sports": [],
    }
    a = flatten_detail(d)
    assert a["precip_mm"] == 2.1
    assert a["precip_prob_pct"] == 70
    assert a["apparent_temp_c"] == 11.0
    assert a["visibility_m"] == 8000
    assert a["wave_period_s"] == 7.0
    assert a["current_speed_kn"] == 0.5


def test_flatten_emits_weekly_weather_csvs():
    from swelligence.detail import flatten_detail

    daily = [
        {"date": "2026-06-29", "datetime": "2026-06-29T12:00", "score": 60,
         "verdict": "good", "precip_mm": 0.0, "precip_prob_pct": 10, "air_temp_c": 15.0},
        {"date": "2026-06-30", "datetime": "2026-06-30T12:00", "score": 40,
         "verdict": "marginal", "precip_mm": 3.4, "precip_prob_pct": 80, "air_temp_c": 12.0},
    ]
    d = {
        "name": "X", "water_type": "sea", "now_time": "12:00",
        "latitude": 1.0, "longitude": 2.0, "current": {},
        "sports": [{"sport": "surf", "label": "Surf", "now": {}, "best": {},
                    "hourly": [], "daily": daily}],
    }
    a = flatten_detail(d)
    assert a["surf_week_rain"] == "0.0,3.4"
    assert a["surf_week_rain_prob"] == "10,80"
    assert a["surf_week_air"] == "15.0,12.0"
