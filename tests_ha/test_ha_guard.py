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
    "tide",
    "batch",
    "overlay",
    "geocoding",
    "providers",
    "providers.base",
    "providers.domains",
    "providers.open_meteo",
    "providers.ukho",
    "providers.noaa_coops",
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


async def test_options_edit_spot_chain_renders(hass, options_entry) -> None:
    """Walk edit_spot -> edit_spot_fields so the routing/tide selectors build."""
    result = await hass.config_entries.options.async_init(options_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_spot"}
    )
    assert result["step_id"] == "edit_spot"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"spot": "test_spot"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_spot_fields"


async def test_options_add_spot_search_then_map(hass, options_entry) -> None:
    """Search -> disambiguation pick (centres map) -> map -> save.

    Geocoding is mocked (no network). The chosen match centres the map and
    defaults the name; the pin placed on the map sets the final coordinates.
    """
    from unittest.mock import AsyncMock, patch

    from custom_components.swelligence.geocoding import GeocodeResult

    matches = [
        GeocodeResult("Christchurch", 50.73, -1.78, "United Kingdom", "England"),
        GeocodeResult("Christchurch", -43.53, 172.63, "New Zealand", "Canterbury"),
    ]
    result = await hass.config_entries.options.async_init(options_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_spot"}
    )
    assert result["step_id"] == "add_spot"
    with patch(
        "custom_components.swelligence.config_flow.async_geocode",
        AsyncMock(return_value=matches),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"place_query": "Christchurch", "water_type": "sea", "sports": ["surf"]},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_spot_pick"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"match": "0"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_spot_location"
    # Drop the pin slightly off the town centre (the actual break).
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": "Avon Beach", "location": {"latitude": 50.735, "longitude": -1.755}},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    new = [s for s in result["data"][CONF_SPOTS] if s["id"] == "avon_beach"]
    assert new and new[0]["latitude"] == 50.735 and new[0]["longitude"] == -1.755


async def test_options_add_spot_no_search_map(hass, options_entry) -> None:
    """No search term -> map opens on the home location -> pin -> save."""
    result = await hass.config_entries.options.async_init(options_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_spot"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"water_type": "sea", "sports": ["surf"]}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_spot_location"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": "Secret Reef", "location": {"latitude": 50.5, "longitude": -1.9}},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert any(s["id"] == "secret_reef" for s in result["data"][CONF_SPOTS])


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
