"""Unit tests for sport profile overrides."""

from __future__ import annotations

from swelligence.sports import SPORT_PROFILES, apply_overrides


def test_override_replaces_field():
    base = SPORT_PROFILES["surf"]
    out = apply_overrides(base, {"wind_dirs": ["N", "NNW"]})
    assert out.wind_dirs == ["N", "NNW"]
    # Untouched fields preserved.
    assert out.wave_ideal_m == base.wave_ideal_m
    # Original is not mutated (frozen dataclass -> new instance).
    assert base.wind_dirs == []


def test_none_values_ignored():
    base = SPORT_PROFILES["kitesurf"]
    out = apply_overrides(base, {"wind_max_kn": None})
    assert out.wind_max_kn == base.wind_max_kn


def test_unknown_keys_ignored():
    base = SPORT_PROFILES["surf"]
    out = apply_overrides(base, {"not_a_field": 5, "wind_min_kn": 3})
    assert out.wind_min_kn == 3
    assert not hasattr(out, "not_a_field")


def test_identity_fields_not_overridable():
    base = SPORT_PROFILES["surf"]
    out = apply_overrides(base, {"label": "Hacked", "icon": "mdi:evil", "key": "x"})
    assert out.label == base.label
    assert out.icon == base.icon
    assert out.key == base.key


def test_empty_or_none_overrides_return_same_object():
    base = SPORT_PROFILES["sup"]
    assert apply_overrides(base, None) is base
    assert apply_overrides(base, {}) is base


def test_multiple_overrides_applied():
    base = SPORT_PROFILES["windsurf"]
    out = apply_overrides(
        base, {"wind_min_kn": 8, "wind_ideal_kn": 18, "wave_max_m": 3.0}
    )
    assert (out.wind_min_kn, out.wind_ideal_kn, out.wave_max_m) == (8, 18, 3.0)
