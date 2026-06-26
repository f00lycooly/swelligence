"""Panel transport encoding — the flat/delimited contract the ESPHome panel
binds. The full spot_panel_payload (needs a live coordinator) is exercised in the
live-HA harness; here we lock the pure encoding helpers so the panel-side lambda
parsing never silently drifts."""

from __future__ import annotations

from types import SimpleNamespace

from swelligence.detail import (
    PANEL_UNRECORDED,
    VERDICT_CODE,
    _csv,
    _verdict_csv,
    panel_headline,
)
from swelligence.sports import SPORT_PROFILES


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
        for suffix in ("hourly_scores", "hourly_verdicts",
                       "week_scores", "week_times", "week_verdicts"):
            assert f"{sport}_{suffix}" in PANEL_UNRECORDED
    assert "tide_levels" in PANEL_UNRECORDED
