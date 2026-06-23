"""Guard tests that exercise the integration against real Home Assistant.

These catch the two bug classes that the stubbed ``tests/`` suite is blind to:

1. Wrong ``homeassistant.*`` imports in the platform modules (e.g. importing
   ``DeviceInfo`` from the wrong helper) — caught by ``test_all_modules_import``.
2. Invalid selector/flow schemas (e.g. a ``NumberSelector`` ``step`` Home
   Assistant rejects) — caught by rendering every config- and options-flow step.
"""

from __future__ import annotations

import importlib

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.swelligence.const import (
    CONF_SPORTS,
    CONF_SPOTS,
    DOMAIN,
)

# Every HA-facing module in the package. A wrong import in any of these raises
# at import time against real Home Assistant.
HA_MODULES = [
    "__init__",
    "binary_sensor",
    "config_flow",
    "const",
    "coordinator",
    "entity",
    "forecast",
    "llm",
    "overview",
    "policy",
    "ranking",
    "scoring",
    "sensor",
    "sizing",
    "sports",
    "geocoding",
    "providers",
    "providers.base",
    "providers.open_meteo",
    "providers.windy",
    "providers.stormglass",
    "providers.ukho",
]


@pytest.mark.parametrize("module", HA_MODULES)
def test_all_modules_import(module: str) -> None:
    """Importing each module against real HA must not raise (catches bad imports)."""
    importlib.import_module(f"custom_components.swelligence.{module}")


async def test_config_user_flow_renders(hass) -> None:
    """The initial config-flow step builds its schema without HA rejecting it."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


# A minimal entry whose options carry one spot so spot-scoped steps render.
_OPTIONS = {
    CONF_SPORTS: ["surf", "kitesurf", "windsurf"],
    CONF_SPOTS: [
        {
            "id": "test_spot",
            "name": "Test Spot",
            "latitude": 50.73,
            "longitude": -1.75,
            "water_type": "sea",
            "sports": ["surf", "kitesurf"],
        }
    ],
}

# Options-flow steps reachable straight from the menu; each renders a schema.
_MENU_STEPS = ["add_spot", "edit_spot", "rider", "providers", "settings"]


@pytest.fixture
def options_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_OPTIONS)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("step", _MENU_STEPS)
async def test_options_menu_step_renders(hass, options_entry, step: str) -> None:
    """Each options-flow menu step builds its schema (catches bad selectors)."""
    result = await hass.config_entries.options.async_init(options_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == step


async def test_options_spot_prefs_chain_renders(hass, options_entry) -> None:
    """Walk spot_prefs -> sport -> edit so every per-sport selector is built."""
    result = await hass.config_entries.options.async_init(options_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "spot_prefs"}
    )
    assert result["step_id"] == "spot_prefs"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"spot": "test_spot"}
    )
    assert result["step_id"] == "spot_prefs_sport"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sport": "surf"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "spot_prefs_edit"
