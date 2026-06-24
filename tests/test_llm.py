"""Unit tests for the AI Task prompt builder — confidence/source feed (o07.5).

Only the pure prompt builder is exercised; the ai_task service call itself lives
in the live-HA harness. ``llm.py`` keeps its HomeAssistant import under
TYPE_CHECKING so the builder imports without Home Assistant installed.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from swelligence.llm import _build_prompt
from swelligence.providers.base import ForecastPoint, SpotForecast
from swelligence.providers.domains import WAVE, WIND
from swelligence.sports import SPORT_PROFILES


def _forecast(point: ForecastPoint, **meta) -> SpotForecast:
    return SpotForecast(
        provider="open_meteo",
        latitude=-43.5,
        longitude=172.7,
        points=[point],
        source_meta=meta,
    )


def _result(score=60.0, verdict="good"):
    now = SimpleNamespace(score=score, verdict=verdict, factors={"wave": 80}, reasons=[])
    return SimpleNamespace(now=now, kit=None)


SPOT = {"name": "Sumner", "id": "sumner", "latitude": -43.57, "longitude": 172.76}


def test_prompt_includes_confidence_and_low_agreement():
    point = ForecastPoint(
        time=datetime(2026, 6, 23, 9),
        wind_speed_kn=12.0,
        wave_height_m=1.4,
        swell_period_s=11.0,
        source_confidence={"wave_height_m": 0.95, "swell_period_s": 0.2},
    )
    fc = _forecast(point, sources={WIND: "open_meteo", WAVE: "open_meteo"})
    prompt = _build_prompt(
        SPOT, fc, {"surf": _result()}, {"surf": SPORT_PROFILES["surf"]}
    )
    assert "confidence=" in prompt
    # swell_period_s confidence 0.2 < threshold -> flagged by its friendly label.
    assert "models disagree on" in prompt
    assert "swell period" in prompt
    # The global instruction to voice low confidence is appended.
    assert "wait for the next run" in prompt


def test_prompt_names_data_sources():
    point = ForecastPoint(
        time=datetime(2026, 6, 23, 9),
        wind_speed_kn=12.0,
        wave_height_m=1.4,
        swell_period_s=11.0,
        swell_dir_deg=200.0,
    )
    fc = _forecast(point, sources={WIND: "open_meteo", WAVE: "open_meteo"})
    prompt = _build_prompt(
        SPOT, fc, {"surf": _result()}, {"surf": SPORT_PROFILES["surf"]}
    )
    assert "data:" in prompt
    assert "swell: open_meteo" in prompt  # WAVE source surfaced via data_quality


def test_prompt_omits_confidence_when_no_signal():
    # No source_confidence anywhere -> single-source -> no confidence clause and
    # no low-agreement instruction.
    point = ForecastPoint(
        time=datetime(2026, 6, 23, 9), wind_speed_kn=12.0, wave_height_m=1.4
    )
    fc = _forecast(point, sources={WIND: "open_meteo", WAVE: "open_meteo"})
    prompt = _build_prompt(
        SPOT, fc, {"surf": _result()}, {"surf": SPORT_PROFILES["surf"]}
    )
    assert "confidence=" not in prompt
    assert "models disagree" not in prompt
    assert "wait for the next run" not in prompt
    # Deterministic scaffolding is still present.
    assert "Sumner" in prompt and "surf" in prompt
