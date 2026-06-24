"""Unit tests for cross-provider confidence + consensus blend (o07.3)."""

from __future__ import annotations

from datetime import datetime

from swelligence.confidence import blend_values
from swelligence.overlay import ensemble_marine
from swelligence.providers.base import ForecastPoint


def _pt(t: datetime, **kw) -> ForecastPoint:
    return ForecastPoint(time=t, **kw)


T0 = datetime(2026, 6, 23, 9)
T1 = datetime(2026, 6, 23, 10)


# --- blend_values -----------------------------------------------------------

def test_blend_magnitude_is_arithmetic_mean():
    assert blend_values("wave_height_m", [1.0, 2.0]) == 1.5


def test_blend_direction_is_circular_mean():
    # 350 and 10 should average to 0, not 180.
    assert blend_values("swell_dir_deg", [350.0, 10.0]) == 0.0


def test_blend_none_without_values():
    assert blend_values("wave_height_m", []) is None


# --- ensemble_marine --------------------------------------------------------

def test_confidence_stamped_from_agreement():
    base = [_pt(T0, wave_height_m=1.5, swell_period_s=11.0)]
    overlay = [_pt(T0, wave_height_m=1.52, swell_period_s=7.0)]
    scored = ensemble_marine(base, overlay)
    assert scored == {"wave_height_m", "swell_period_s"}
    conf = base[0].source_confidence
    # Wave heights agree tightly; swell periods (11 vs 7) diverge.
    assert conf["wave_height_m"] > 0.9
    assert conf["swell_period_s"] < conf["wave_height_m"]


def test_no_blend_leaves_base_values_untouched():
    base = [_pt(T0, wave_height_m=1.5)]
    overlay = [_pt(T0, wave_height_m=2.5)]
    ensemble_marine(base, overlay, blend=False)
    assert base[0].wave_height_m == 1.5  # base value preserved


def test_blend_replaces_with_consensus():
    base = [_pt(T0, wave_height_m=1.5)]
    overlay = [_pt(T0, wave_height_m=2.5)]
    ensemble_marine(base, overlay, blend=True)
    assert base[0].wave_height_m == 2.0  # mean of the two sources


def test_confidence_from_original_pair_not_post_blend():
    # Even with blend on, confidence must reflect the 1.5 vs 2.5 disagreement,
    # not the collapsed 2.0/2.0 it would look like after blending.
    base = [_pt(T0, wave_height_m=1.5)]
    overlay = [_pt(T0, wave_height_m=2.5)]
    ensemble_marine(base, overlay, blend=True)
    # |spread| = 0.5 against a 0.6 scale -> low-ish confidence, not ~1.0.
    assert base[0].source_confidence["wave_height_m"] < 0.4


def test_only_fields_present_in_both_are_scored():
    base = [_pt(T0, wave_height_m=1.5)]  # no swell on base
    overlay = [_pt(T0, wave_height_m=1.5, swell_period_s=10.0)]
    scored = ensemble_marine(base, overlay)
    assert scored == {"wave_height_m"}


def test_alignment_by_timestamp():
    base = [_pt(T0, wave_height_m=1.0), _pt(T1, wave_height_m=2.0)]
    overlay = [_pt(T1, wave_height_m=2.05)]  # only the second hour overlaps
    scored = ensemble_marine(base, overlay)
    assert scored == {"wave_height_m"}
    assert base[0].source_confidence is None  # T0 had no overlay partner
    assert base[1].source_confidence is not None


def test_merges_with_existing_confidence():
    # A provider's own intra-model confidence (e.g. multi-model spread) survives.
    base = [_pt(T0, wave_height_m=1.5, swell_period_s=11.0,
                source_confidence={"swell_period_s": 0.9})]
    overlay = [_pt(T0, wave_height_m=1.5)]
    ensemble_marine(base, overlay)
    conf = base[0].source_confidence
    assert conf["swell_period_s"] == 0.9  # preserved
    assert "wave_height_m" in conf        # added by the ensemble


def test_no_overlap_returns_empty():
    base = [_pt(T0, wave_height_m=1.0)]
    overlay = [_pt(T1, wave_height_m=1.0)]
    assert ensemble_marine(base, overlay) == set()
    assert base[0].source_confidence is None
