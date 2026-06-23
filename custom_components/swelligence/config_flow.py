"""Config and options flow for swelligence.

Setup is two-phase:

* **Config flow** (once): pick the sports you care about, the default forecast
  provider, and optionally wire up an AI Task entity for semantic verdicts.
* **Options flow** (ongoing): add/remove favourite spots and toggle the LLM
  layer. Each spot stores a name + coordinates + the subset of sports relevant
  there. Geocoding a place name to coordinates is a later enhancement; for now
  coordinates are entered directly (pre-filled from the HA home location).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_DEFAULT_PROVIDER,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SPORTS,
    CONF_SPOT_NAME,
    CONF_SPOT_SPORTS,
    CONF_SPOTS,
    CONF_USE_LLM,
    CONF_WATER_TYPE,
    DOMAIN,
    WATER_TYPE_SEA,
    WATER_TYPES,
)
from .providers import PROVIDERS
from .sports import SPORT_PROFILES

_SPORT_OPTIONS = [
    selector.SelectOptionDict(value=k, label=p.label)
    for k, p in SPORT_PROFILES.items()
]
_PROVIDER_OPTIONS = [
    selector.SelectOptionDict(value=k, label=cls.label) for k, cls in PROVIDERS.items()
]


def _slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower()).strip("_")


class SwelligenceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Swelligence",
                data={},
                options={
                    CONF_SPORTS: user_input[CONF_SPORTS],
                    CONF_DEFAULT_PROVIDER: user_input[CONF_DEFAULT_PROVIDER],
                    CONF_USE_LLM: user_input.get(CONF_USE_LLM, False),
                    CONF_AI_TASK_ENTITY: user_input.get(CONF_AI_TASK_ENTITY),
                    CONF_SPOTS: [],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SPORTS, default=list(SPORT_PROFILES)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_SPORT_OPTIONS, multiple=True
                    )
                ),
                vol.Required(
                    CONF_DEFAULT_PROVIDER, default="open_meteo"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_PROVIDER_OPTIONS)
                ),
                vol.Optional(CONF_USE_LLM, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_AI_TASK_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="ai_task")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SwelligenceOptionsFlow()


class SwelligenceOptionsFlow(OptionsFlow):
    """Manage spots and the LLM toggle after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["add_spot", "settings"]
        )

    async def async_step_add_spot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            spots = list(self.config_entry.options.get(CONF_SPOTS, []))
            spot_id = _slugify(user_input[CONF_SPOT_NAME])
            if any(s["id"] == spot_id for s in spots):
                errors["base"] = "duplicate_spot"
            else:
                spots.append(
                    {
                        "id": spot_id,
                        CONF_SPOT_NAME: user_input[CONF_SPOT_NAME],
                        CONF_LATITUDE: user_input[CONF_LATITUDE],
                        CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                        CONF_WATER_TYPE: user_input[CONF_WATER_TYPE],
                        CONF_SPOT_SPORTS: user_input[CONF_SPOT_SPORTS],
                    }
                )
                return self._save({CONF_SPOTS: spots})

        enabled = self.config_entry.options.get(CONF_SPORTS, list(SPORT_PROFILES))
        spot_sport_options = [
            o for o in _SPORT_OPTIONS if o["value"] in enabled
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_SPOT_NAME): selector.TextSelector(),
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90, max=90, step=0.0001, mode="box"
                    )
                ),
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180, max=180, step=0.0001, mode="box"
                    )
                ),
                vol.Required(
                    CONF_WATER_TYPE, default=WATER_TYPE_SEA
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WATER_TYPES,
                        translation_key="water_type",
                    )
                ),
                vol.Required(
                    CONF_SPOT_SPORTS, default=enabled
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=spot_sport_options, multiple=True
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="add_spot", data_schema=schema, errors=errors
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_USE_LLM, default=opts.get(CONF_USE_LLM, False)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_AI_TASK_ENTITY,
                    description={"suggested_value": opts.get(CONF_AI_TASK_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="ai_task")
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        new_options = {**self.config_entry.options, **changes}
        return self.async_create_entry(title="", data=new_options)
