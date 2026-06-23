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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    COMPASS_SECTORS,
    CONF_AI_TASK_ENTITY,
    CONF_API_KEY,
    CONF_DEFAULT_PROVIDER,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PLACE_QUERY,
    CONF_PROVIDERS,
    CONF_QUIVER,
    CONF_RIDER,
    CONF_RIDER_WEIGHT,
    CONF_SPORTS,
    CONF_SPOT_NAME,
    CONF_SPOT_PREFS,
    CONF_SPOT_SPORTS,
    CONF_SPOTS,
    CONF_USE_LLM,
    CONF_WATER_TYPE,
    DOMAIN,
    OVERRIDE_FIELDS,
    PREF_GUST_MAX,
    PREF_WAVE_IDEAL_M,
    PREF_WAVE_MAX_M,
    PREF_WAVE_MIN_M,
    PREF_WIND_DIRS,
    PREF_WIND_IDEAL,
    PREF_WIND_MAX,
    PREF_WIND_MIN,
    WATER_TYPE_SEA,
    WATER_TYPES,
)
from .geocoding import async_geocode
from .providers import PROVIDERS
from .sports import SPORT_PROFILES, apply_overrides

# Keyed providers needing an API key entry in the providers settings step.
_KEYED_PROVIDERS = {k: cls for k, cls in PROVIDERS.items() if cls.requires_api_key}

_DIR_OPTIONS = [selector.SelectOptionDict(value=s, label=s) for s in COMPASS_SECTORS]


def _kn(min_v: float = 0, max_v: float = 60) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_v, max=max_v, step=1, mode="box", unit_of_measurement="kn"
        )
    )


def _metres(max_v: float = 8) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=max_v, step=0.1, mode="box", unit_of_measurement="m"
        )
    )

_SPORT_OPTIONS = [
    selector.SelectOptionDict(value=k, label=p.label)
    for k, p in SPORT_PROFILES.items()
]
_PROVIDER_OPTIONS = [
    selector.SelectOptionDict(value=k, label=cls.label) for k, cls in PROVIDERS.items()
]


def _slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower()).strip("_")


def _parse_sizes(raw: str | None) -> list[float]:
    """Parse a comma/space separated size list ('7, 9, 12') into sorted floats."""
    if not raw:
        return []
    out: list[float] = []
    for token in raw.replace(",", " ").split():
        try:
            out.append(float(token))
        except ValueError:
            continue
    return sorted(set(out))


def _format_sizes(sizes: list[float] | None) -> str:
    return ", ".join(f"{s:g}" for s in sizes) if sizes else ""


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
    """Manage spots, per-spot preferences, and the LLM toggle after setup."""

    _pref_spot_id: str | None = None
    _pref_sport: str | None = None
    _edit_spot_id: str | None = None
    _pending_spot: dict | None = None
    _geocode_choices: list | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_spot",
                "edit_spot",
                "spot_prefs",
                "rider",
                "providers",
                "settings",
            ],
        )

    async def async_step_rider(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the single local rider's weight and quiver (kite/wing sizes)."""
        if user_input is not None:
            rider = {
                CONF_RIDER_WEIGHT: user_input.get(CONF_RIDER_WEIGHT),
                CONF_QUIVER: {
                    "kitesurf": _parse_sizes(user_input.get("kite_sizes")),
                    "wingfoil": _parse_sizes(user_input.get("wing_sizes")),
                },
            }
            return self._save({CONF_RIDER: rider})

        rider = self.config_entry.options.get(CONF_RIDER, {})
        quiver = rider.get(CONF_QUIVER, {})
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RIDER_WEIGHT,
                    description={"suggested_value": rider.get(CONF_RIDER_WEIGHT)},
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=20, max=150, step=1, mode="box",
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(
                    "kite_sizes",
                    description={"suggested_value": _format_sizes(quiver.get("kitesurf"))},
                ): selector.TextSelector(),
                vol.Optional(
                    "wing_sizes",
                    description={"suggested_value": _format_sizes(quiver.get("wingfoil"))},
                ): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="rider", data_schema=schema)

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
                # Carry the spot's metadata while we resolve coordinates.
                self._pending_spot = {
                    "id": spot_id,
                    CONF_SPOT_NAME: user_input[CONF_SPOT_NAME],
                    CONF_WATER_TYPE: user_input[CONF_WATER_TYPE],
                    CONF_SPOT_SPORTS: user_input[CONF_SPOT_SPORTS],
                }
                query = (user_input.get(CONF_PLACE_QUERY) or "").strip()
                if query:
                    session = async_get_clientsession(self.hass)
                    results = await async_geocode(session, query)
                    if not results:
                        errors["base"] = "geocode_no_results"
                    elif len(results) == 1:
                        return self._finish_add_spot(
                            results[0].latitude, results[0].longitude
                        )
                    else:
                        self._geocode_choices = results
                        return await self.async_step_add_spot_pick()
                else:
                    return self._finish_add_spot(
                        user_input[CONF_LATITUDE], user_input[CONF_LONGITUDE]
                    )

        enabled = self.config_entry.options.get(CONF_SPORTS, list(SPORT_PROFILES))
        spot_sport_options = [
            o for o in _SPORT_OPTIONS if o["value"] in enabled
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_SPOT_NAME): selector.TextSelector(),
                vol.Optional(CONF_PLACE_QUERY): selector.TextSelector(),
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90, max=90, step="any", mode="box"
                    )
                ),
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180, max=180, step="any", mode="box"
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

    async def async_step_add_spot_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Disambiguate a place-name search that returned several matches."""
        choices = self._geocode_choices or []
        if not choices or self._pending_spot is None:
            return await self.async_step_add_spot()
        if user_input is not None:
            choice = choices[int(user_input["match"])]
            return self._finish_add_spot(choice.latitude, choice.longitude)

        options = [
            selector.SelectOptionDict(value=str(i), label=r.label)
            for i, r in enumerate(choices)
        ]
        schema = vol.Schema(
            {
                vol.Required("match", default="0"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(
            step_id="add_spot_pick",
            data_schema=schema,
            description_placeholders={"name": self._pending_spot[CONF_SPOT_NAME]},
        )

    def _finish_add_spot(self, lat: float, lon: float) -> ConfigFlowResult:
        """Append the pending spot with resolved coordinates and save."""
        spot = {**self._pending_spot, CONF_LATITUDE: lat, CONF_LONGITUDE: lon}
        spots = list(self.config_entry.options.get(CONF_SPOTS, []))
        spots.append(spot)
        self._pending_spot = None
        self._geocode_choices = None
        return self._save({CONF_SPOTS: spots})

    async def async_step_edit_spot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: pick which existing spot to edit (sports / water type)."""
        spots = self.config_entry.options.get(CONF_SPOTS, [])
        if not spots:
            return self.async_abort(reason="no_spots")
        if user_input is not None:
            self._edit_spot_id = user_input["spot"]
            return await self.async_step_edit_spot_fields()

        options = [
            selector.SelectOptionDict(value=s["id"], label=s[CONF_SPOT_NAME])
            for s in spots
        ]
        schema = vol.Schema(
            {
                vol.Required("spot"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="edit_spot", data_schema=schema)

    async def async_step_edit_spot_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: add/remove sports and change the water type for the spot."""
        spot = self._get_spot(self._edit_spot_id)
        if spot is None:
            return self.async_abort(reason="no_spots")
        enabled = self.config_entry.options.get(CONF_SPORTS, list(SPORT_PROFILES))

        if user_input is not None:
            new_sports = user_input[CONF_SPOT_SPORTS]
            new_spots = []
            for s in self.config_entry.options.get(CONF_SPOTS, []):
                if s["id"] != self._edit_spot_id:
                    new_spots.append(s)
                    continue
                # Drop per-sport overrides for sports no longer relevant here.
                prefs = {
                    k: v
                    for k, v in (s.get(CONF_SPOT_PREFS, {}) or {}).items()
                    if k in new_sports
                }
                updated = {
                    **s,
                    CONF_WATER_TYPE: user_input[CONF_WATER_TYPE],
                    CONF_SPOT_SPORTS: new_sports,
                    CONF_SPOT_PREFS: prefs,
                }
                new_spots.append(updated)
            return self._save({CONF_SPOTS: new_spots})

        spot_sport_options = [o for o in _SPORT_OPTIONS if o["value"] in enabled]
        current_sports = [
            s for s in (spot.get(CONF_SPOT_SPORTS) or enabled) if s in enabled
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WATER_TYPE,
                    default=spot.get(CONF_WATER_TYPE, WATER_TYPE_SEA),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WATER_TYPES, translation_key="water_type"
                    )
                ),
                vol.Required(
                    CONF_SPOT_SPORTS, default=current_sports
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=spot_sport_options, multiple=True
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="edit_spot_fields",
            data_schema=schema,
            description_placeholders={"spot": spot[CONF_SPOT_NAME]},
        )

    async def async_step_providers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter API keys for keyed forecast providers (Windy, Stormglass)."""
        if not _KEYED_PROVIDERS:
            return self.async_abort(reason="no_keyed_providers")
        stored = dict(self.config_entry.options.get(CONF_PROVIDERS, {}) or {})
        if user_input is not None:
            for key in _KEYED_PROVIDERS:
                value = (user_input.get(key) or "").strip()
                if value:
                    stored[key] = {**stored.get(key, {}), CONF_API_KEY: value}
                else:
                    stored.pop(key, None)
            return self._save({CONF_PROVIDERS: stored})

        fields: dict = {}
        for key, cls in _KEYED_PROVIDERS.items():
            current = (stored.get(key, {}) or {}).get(CONF_API_KEY)
            fields[
                vol.Optional(
                    key, description={"suggested_value": current}
                )
            ] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        return self.async_show_form(
            step_id="providers", data_schema=vol.Schema(fields)
        )

    async def async_step_spot_prefs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: choose which spot to tune."""
        spots = self.config_entry.options.get(CONF_SPOTS, [])
        if not spots:
            return self.async_abort(reason="no_spots")
        if user_input is not None:
            self._pref_spot_id = user_input["spot"]
            return await self.async_step_spot_prefs_sport()

        options = [
            selector.SelectOptionDict(value=s["id"], label=s[CONF_SPOT_NAME])
            for s in spots
        ]
        schema = vol.Schema(
            {
                vol.Required("spot"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="spot_prefs", data_schema=schema)

    async def async_step_spot_prefs_sport(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: choose which sport at that spot to tune."""
        spot = self._get_spot(self._pref_spot_id)
        if spot is None:
            return self.async_abort(reason="no_spots")
        if user_input is not None:
            self._pref_sport = user_input["sport"]
            return await self.async_step_spot_prefs_edit()

        sports = spot.get(CONF_SPOT_SPORTS) or list(SPORT_PROFILES)
        options = [
            selector.SelectOptionDict(
                value=k, label=SPORT_PROFILES[k].label if k in SPORT_PROFILES else k
            )
            for k in sports
        ]
        schema = vol.Schema(
            {
                vol.Required("sport"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(
            step_id="spot_prefs_sport",
            data_schema=schema,
            description_placeholders={"spot": spot[CONF_SPOT_NAME]},
        )

    async def async_step_spot_prefs_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: edit the preference overrides for (spot, sport)."""
        spot = self._get_spot(self._pref_spot_id)
        if spot is None:
            return self.async_abort(reason="no_spots")
        sport = self._pref_sport

        if user_input is not None:
            overrides = {
                k: user_input[k]
                for k in OVERRIDE_FIELDS
                if k in user_input and user_input[k] not in (None, "")
            }
            new_spots = []
            for s in self.config_entry.options.get(CONF_SPOTS, []):
                if s["id"] == self._pref_spot_id:
                    prefs = {**s.get(CONF_SPOT_PREFS, {}), sport: overrides}
                    new_spots.append({**s, CONF_SPOT_PREFS: prefs})
                else:
                    new_spots.append(s)
            return self._save({CONF_SPOTS: new_spots})

        # Pre-fill from the effective profile (default + any existing override).
        base = SPORT_PROFILES.get(sport)
        eff = apply_overrides(base, spot.get(CONF_SPOT_PREFS, {}).get(sport))

        def opt(key: str, value: Any, sel: selector.Selector):
            marker = vol.Optional(
                key,
                description={"suggested_value": value} if value is not None else None,
            )
            return marker, sel

        fields: dict = {}
        m, s = opt(PREF_WIND_DIRS, eff.wind_dirs or None, selector.SelectSelector(
            selector.SelectSelectorConfig(options=_DIR_OPTIONS, multiple=True)
        ))
        fields[m] = s
        for key, value in (
            (PREF_WIND_MIN, eff.wind_min_kn),
            (PREF_WIND_IDEAL, eff.wind_ideal_kn),
            (PREF_WIND_MAX, eff.wind_max_kn),
            (PREF_GUST_MAX, eff.gust_max_kn),
        ):
            m, s = opt(key, value, _kn())
            fields[m] = s
        for key, value in (
            (PREF_WAVE_MIN_M, eff.wave_min_m),
            (PREF_WAVE_IDEAL_M, eff.wave_ideal_m),
            (PREF_WAVE_MAX_M, eff.wave_max_m),
        ):
            m, s = opt(key, value, _metres())
            fields[m] = s

        return self.async_show_form(
            step_id="spot_prefs_edit",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "spot": spot[CONF_SPOT_NAME],
                "sport": base.label if base else sport,
            },
        )

    def _get_spot(self, spot_id: str | None) -> dict | None:
        for s in self.config_entry.options.get(CONF_SPOTS, []):
            if s["id"] == spot_id:
                return s
        return None

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
