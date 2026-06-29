"""The coordinator's HazardConfig is built from option keys with safe defaults."""

from __future__ import annotations

from swelligence.const import (
    CONF_HAZARD_FOG,
    CONF_HAZARD_HEAVY_RAIN,
    CONF_HAZARD_SQUALL,
    CONF_HAZARD_THUNDERSTORM,
    CONF_SQUALL_BEAUFORT_KN,
    DEFAULT_SQUALL_BEAUFORT_KN,
    HAZARD_TIERS,
)
from swelligence.hazards import TIER_HARD, TIER_OFF, TIER_WARN


def test_tier_values_are_known():
    assert set(HAZARD_TIERS) == {TIER_OFF, TIER_WARN, TIER_HARD}


def test_default_squall_is_force_8():
    assert DEFAULT_SQUALL_BEAUFORT_KN == 34


def test_conf_keys_are_distinct_strings():
    keys = {
        CONF_HAZARD_THUNDERSTORM, CONF_HAZARD_FOG, CONF_HAZARD_SQUALL,
        CONF_HAZARD_HEAVY_RAIN, CONF_SQUALL_BEAUFORT_KN,
    }
    assert len(keys) == 5
