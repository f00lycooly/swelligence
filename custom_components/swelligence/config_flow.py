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
    BEAUFORT_SQUALL_OPTIONS,
    COMPASS_SECTORS,
    CONF_AI_TASK_ENTITY,
    CONF_API_KEY,
    CONF_FREE_TIER,
    CONF_DEFAULT_PROVIDER,
    CONF_HAZARD_FOG,
    CONF_HAZARD_HEAVY_RAIN,
    CONF_HAZARD_SQUALL,
    CONF_HAZARD_THUNDERSTORM,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MARINE_BLEND,
    CONF_MARINE_ENSEMBLE,
    CONF_MARINE_PREFER,
    CONF_MARINE_SOURCE,
    CONF_PLACE_QUERY,
    CONF_PROVIDERS,
    CONF_QUIVER,
    CONF_RIDER,
    CONF_RIDER_WEIGHT,
    CONF_SPORTS,
    CONF_SPOT_NAME,
    CONF_SPOT_PREFS,
    CONF_SPOT_PROVIDER,
    CONF_SPOT_SPORTS,
    CONF_SPOTS,
    CONF_SQUALL_BEAUFORT_KN,
    CONF_TIDE_SOURCE,
    CONF_TIDE_STATE,
    CONF_TIDE_WINDOW_H,
    CONF_USE_LLM,
    CONF_WATER_TYPE,
    DEFAULT_SQUALL_BEAUFORT_KN,
    DOMAIN,
    HAZARD_TIERS,
    OVERRIDE_FIELDS,
    PREF_GUST_MAX,
    PREF_SWELL_DIRS,
    PREF_SWELL_PERIOD,
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
from .geocoding import GeocodeResult, async_geocode
from .providers import PROVIDERS, TIDE_PROVIDERS
from .sports import SPORT_PROFILES, apply_overrides
from .tide import TIDE_STATE_ANY, TIDE_STATES

# Keyed providers needing an API key entry in the providers settings step.
_KEYED_PROVIDERS = {k: cls for k, cls in PROVIDERS.items() if cls.requires_api_key}
# Tide overlays needing an API key (e.g. UKHO). Keyless tide sources
# (NOAA CO-OPS, Open-Meteo modeled) need no entry.
_KEYED_TIDE_PROVIDERS = {
    k: cls
    for k, cls in TIDE_PROVIDERS.items()
    if cls.requires_api_key and k not in PROVIDERS
}
_TIDE_STATE_OPTIONS = [
    selector.SelectOptionDict(value=s, label=s) for s in TIDE_STATES
]
_TIDE_SOURCE_OPTIONS = [selector.SelectOptionDict(value="none", label="none")] + [
    selector.SelectOptionDict(value=k, label=cls.label)
    for k, cls in TIDE_PROVIDERS.items()
]
# Keyed marine-capable providers can be layered onto the keyless base.
_MARINE_SOURCE_OPTIONS = [selector.SelectOptionDict(value="none", label="none")] + [
    selector.SelectOptionDict(value=k, label=cls.label)
    for k, cls in PROVIDERS.items()
    if cls.supports_marine and cls.requires_api_key
]
# Per-spot routing variants: an "inherit" option falls back to the global
# setting. _PROVIDER_ROUTE_OPTIONS is built below, once _PROVIDER_OPTIONS exists.
_INHERIT_OPTION = selector.SelectOptionDict(value="inherit", label="(use global)")
_MARINE_ROUTE_OPTIONS = [_INHERIT_OPTION] + _MARINE_SOURCE_OPTIONS
_TIDE_ROUTE_OPTIONS = [_INHERIT_OPTION] + _TIDE_SOURCE_OPTIONS


def _tide_fields(state: str = TIDE_STATE_ANY, window: float | None = None) -> dict:
    """Schema fragment for a spot's tide preference (state + window hours)."""
    return {
        vol.Optional(
            CONF_TIDE_STATE, default=state or TIDE_STATE_ANY
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=_TIDE_STATE_OPTIONS, translation_key="tide_state"
            )
        ),
        vol.Optional(
            CONF_TIDE_WINDOW_H, description={"suggested_value": window}
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.5, max=4, step=0.5, mode="box", unit_of_measurement="h"
            )
        ),
    }

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
# Per-spot primary-provider routing (depends on _PROVIDER_OPTIONS above).
_PROVIDER_ROUTE_OPTIONS = [_INHERIT_OPTION] + _PROVIDER_OPTIONS


# add_spot form keys that aren't persisted spot fields: the "enter coordinates
# manually" escape hatch and the in-flight custom-name override carried between
# the search step and location resolution.
# add_spot form key for the map picker, and in-flight state carried between the
# search step and the map: the name override, the raw query, and the (lat, lon)
# the map should centre on (from a geocode match; absent => centre on HA home).
_LOCATION = "location"
_NAME_OVERRIDE = "_name_override"
_QUERY = "_query"
_CENTRE = "_centre"


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
        """Add a spot: capture its config + an optional search, then pick on a map.

        The search (place name *or* UK postcode/outcode) only **centres** the map
        — the exact location is always placed on the map in
        ``add_spot_location``. So a spot the geocoder can't resolve (a surf break,
        a postcode it misses) still works: the map just opens on the home location.
        """
        if user_input is not None:
            # Carry the spot's config while we resolve its location on the map.
            self._pending_spot = {
                CONF_WATER_TYPE: user_input[CONF_WATER_TYPE],
                CONF_SPOT_SPORTS: user_input[CONF_SPOT_SPORTS],
                CONF_TIDE_STATE: user_input.get(CONF_TIDE_STATE, TIDE_STATE_ANY),
                CONF_TIDE_WINDOW_H: user_input.get(CONF_TIDE_WINDOW_H),
                _NAME_OVERRIDE: (user_input.get(CONF_SPOT_NAME) or "").strip(),
            }
            query = (user_input.get(CONF_PLACE_QUERY) or "").strip()
            self._pending_spot[_QUERY] = query
            if query:
                session = async_get_clientsession(self.hass)
                results = await async_geocode(session, query)
                if len(results) > 1:
                    self._geocode_choices = results
                    return await self.async_step_add_spot_pick()
                if len(results) == 1:
                    self._set_centre(results[0])
            return await self.async_step_add_spot_location()

        enabled = self.config_entry.options.get(CONF_SPORTS, list(SPORT_PROFILES))
        spot_sport_options = [
            o for o in _SPORT_OPTIONS if o["value"] in enabled
        ]
        schema = vol.Schema(
            {
                vol.Optional(CONF_PLACE_QUERY): selector.TextSelector(),
                vol.Optional(CONF_SPOT_NAME): selector.TextSelector(),
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
                **_tide_fields(),
            }
        )
        return self.async_show_form(step_id="add_spot", data_schema=schema)

    async def async_step_add_spot_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Disambiguate a search that matched several places. The choice just
        centres the map; the pin is still placed in ``add_spot_location``."""
        choices = self._geocode_choices or []
        if not choices or self._pending_spot is None:
            return await self.async_step_add_spot()
        if user_input is not None:
            self._set_centre(choices[int(user_input["match"])])
            return await self.async_step_add_spot_location()

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
            description_placeholders={
                "name": self._pending_spot.get(_QUERY) or "your search"
            },
        )

    async def async_step_add_spot_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Place the spot precisely on a map — centred on the search match when
        there was one, otherwise on the Home Assistant location."""
        if self._pending_spot is None:
            return await self.async_step_add_spot()
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[_LOCATION]
            result, err = self._commit_spot(
                user_input[CONF_SPOT_NAME], loc["latitude"], loc["longitude"]
            )
            if err:
                errors["base"] = err
            else:
                return result

        centre = self._pending_spot.get(_CENTRE) or (
            self.hass.config.latitude,
            self.hass.config.longitude,
        )
        override = self._pending_spot.get(_NAME_OVERRIDE)
        name_key = (
            vol.Required(CONF_SPOT_NAME, default=override)
            if override
            else vol.Required(CONF_SPOT_NAME)
        )
        schema = vol.Schema(
            {
                name_key: selector.TextSelector(),
                vol.Required(
                    _LOCATION,
                    default={"latitude": centre[0], "longitude": centre[1]},
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=False)
                ),
            }
        )
        return self.async_show_form(
            step_id="add_spot_location",
            data_schema=schema,
            errors=errors,
            description_placeholders={"query": self._pending_spot.get(_QUERY) or ""},
        )

    def _set_centre(self, result: GeocodeResult) -> None:
        """Record a geocode match as the map centre + default spot name."""
        self._pending_spot[_CENTRE] = (result.latitude, result.longitude)
        if not self._pending_spot.get(_NAME_OVERRIDE):
            self._pending_spot[_NAME_OVERRIDE] = result.name

    def _commit_spot(
        self, name: str, lat: float, lon: float
    ) -> tuple[ConfigFlowResult | None, str | None]:
        """Append the pending spot with a resolved name + coordinates and save.

        Returns ``(result, None)`` on success, or ``(None, error_key)`` when the
        name collides with an existing spot so the caller re-shows the form.
        """
        name = (name or "").strip() or "Spot"
        spot_id = _slugify(name)
        spots = list(self.config_entry.options.get(CONF_SPOTS, []))
        if any(s["id"] == spot_id for s in spots):
            return None, "duplicate_spot"
        spot = {
            "id": spot_id,
            CONF_SPOT_NAME: name,
            CONF_WATER_TYPE: self._pending_spot[CONF_WATER_TYPE],
            CONF_SPOT_SPORTS: self._pending_spot[CONF_SPOT_SPORTS],
            CONF_TIDE_STATE: self._pending_spot[CONF_TIDE_STATE],
            CONF_TIDE_WINDOW_H: self._pending_spot[CONF_TIDE_WINDOW_H],
            CONF_LATITUDE: lat,
            CONF_LONGITUDE: lon,
        }
        spots.append(spot)
        self._pending_spot = None
        self._geocode_choices = None
        return self._save({CONF_SPOTS: spots}), None

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
                    CONF_TIDE_STATE: user_input.get(CONF_TIDE_STATE, TIDE_STATE_ANY),
                    CONF_TIDE_WINDOW_H: user_input.get(CONF_TIDE_WINDOW_H),
                }
                # Per-spot source routing: store an override, or drop the key so
                # it inherits the entry-level (global) source.
                for route_key in (
                    CONF_SPOT_PROVIDER,
                    CONF_MARINE_SOURCE,
                    CONF_TIDE_SOURCE,
                ):
                    value = user_input.get(route_key)
                    if value in (None, "inherit"):
                        updated.pop(route_key, None)
                    else:
                        updated[route_key] = value
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
                **_tide_fields(
                    spot.get(CONF_TIDE_STATE, TIDE_STATE_ANY),
                    spot.get(CONF_TIDE_WINDOW_H),
                ),
                vol.Optional(
                    CONF_SPOT_PROVIDER,
                    default=spot.get(CONF_SPOT_PROVIDER, "inherit"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_PROVIDER_ROUTE_OPTIONS)
                ),
                vol.Optional(
                    CONF_MARINE_SOURCE,
                    default=spot.get(CONF_MARINE_SOURCE, "inherit"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_MARINE_ROUTE_OPTIONS)
                ),
                vol.Optional(
                    CONF_TIDE_SOURCE,
                    default=spot.get(CONF_TIDE_SOURCE, "inherit"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_TIDE_ROUTE_OPTIONS)
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
        """Enter API keys for keyed providers (e.g. UKHO tides)."""
        if not _KEYED_PROVIDERS and not _KEYED_TIDE_PROVIDERS:
            return self.async_abort(reason="no_keyed_providers")
        stored = dict(self.config_entry.options.get(CONF_PROVIDERS, {}) or {})
        if user_input is not None:
            for key, cls in _KEYED_PROVIDERS.items():
                value = (user_input.get(key) or "").strip()
                if not value:
                    stored.pop(key, None)
                    continue
                cfg = {**stored.get(key, {}), CONF_API_KEY: value}
                if cls.free_tier_daily_requests:
                    cfg[CONF_FREE_TIER] = bool(user_input.get(f"{key}_{CONF_FREE_TIER}"))
                stored[key] = cfg
            for key in _KEYED_TIDE_PROVIDERS:
                value = (user_input.get(key) or "").strip()
                if value:
                    stored[key] = {**stored.get(key, {}), CONF_API_KEY: value}
                else:
                    stored.pop(key, None)
            return self._save(
                {
                    CONF_PROVIDERS: stored,
                    CONF_TIDE_SOURCE: user_input.get(CONF_TIDE_SOURCE, "none"),
                    CONF_MARINE_SOURCE: user_input.get(CONF_MARINE_SOURCE, "none"),
                    CONF_MARINE_PREFER: bool(user_input.get(CONF_MARINE_PREFER)),
                    CONF_MARINE_ENSEMBLE: bool(user_input.get(CONF_MARINE_ENSEMBLE)),
                    CONF_MARINE_BLEND: bool(user_input.get(CONF_MARINE_BLEND)),
                }
            )

        fields: dict = {}
        for key, cls in _KEYED_PROVIDERS.items():
            saved = stored.get(key, {}) or {}
            fields[
                vol.Optional(key, description={"suggested_value": saved.get(CONF_API_KEY)})
            ] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
            # Free-tier safe-poll toggle, only for providers with a known quota.
            if cls.free_tier_daily_requests:
                fields[
                    vol.Optional(
                        f"{key}_{CONF_FREE_TIER}",
                        default=bool(saved.get(CONF_FREE_TIER)),
                    )
                ] = selector.BooleanSelector()
        for key in _KEYED_TIDE_PROVIDERS:
            saved = stored.get(key, {}) or {}
            fields[
                vol.Optional(key, description={"suggested_value": saved.get(CONF_API_KEY)})
            ] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        # Tide overlay source — supplies tides for tide-dependent spots. Usually
        # left unset: the region resolver auto-picks (UKHO/CO-OPS/modeled).
        opts = self.config_entry.options
        fields[
            vol.Optional(
                CONF_TIDE_SOURCE, default=opts.get(CONF_TIDE_SOURCE, "none")
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=_TIDE_SOURCE_OPTIONS)
        )
        # Marine overlay — layer a keyed source's waves/swell onto the base.
        if len(_MARINE_SOURCE_OPTIONS) > 1:
            fields[
                vol.Optional(
                    CONF_MARINE_SOURCE, default=opts.get(CONF_MARINE_SOURCE, "none")
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=_MARINE_SOURCE_OPTIONS)
            )
            fields[
                vol.Optional(
                    CONF_MARINE_PREFER, default=bool(opts.get(CONF_MARINE_PREFER))
                )
            ] = selector.BooleanSelector()
            # Cross-provider ensemble: confidence from base-vs-overlay agreement,
            # and an optional consensus blend (o07.3). Costs the overlay fetch
            # even when the base has waves, so it's opt-in and budget-throttled.
            fields[
                vol.Optional(
                    CONF_MARINE_ENSEMBLE,
                    default=bool(opts.get(CONF_MARINE_ENSEMBLE)),
                )
            ] = selector.BooleanSelector()
            fields[
                vol.Optional(
                    CONF_MARINE_BLEND, default=bool(opts.get(CONF_MARINE_BLEND))
                )
            ] = selector.BooleanSelector()
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
        # Swell quality (surf-type sports only — others leave these unset).
        if eff.swell_period_ideal_s is not None:
            m, s = opt(
                PREF_SWELL_DIRS,
                eff.swell_dirs or None,
                selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_DIR_OPTIONS, multiple=True)
                ),
            )
            fields[m] = s
            m, s = opt(
                PREF_SWELL_PERIOD,
                eff.swell_period_ideal_s,
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=4, max=20, step=1, mode="box", unit_of_measurement="s"
                    )
                ),
            )
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
        tier_opts = [selector.SelectOptionDict(value=t, label=t) for t in HAZARD_TIERS]
        beaufort_opts = [
            selector.SelectOptionDict(value=v, label=lbl)
            for v, lbl in BEAUFORT_SQUALL_OPTIONS
        ]

        def tier(key, default):
            return (
                vol.Optional(key, default=opts.get(key, default)),
                selector.SelectSelector(selector.SelectSelectorConfig(options=tier_opts)),
            )

        fields = {
            vol.Optional(
                CONF_USE_LLM, default=opts.get(CONF_USE_LLM, False)
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_AI_TASK_ENTITY,
                description={"suggested_value": opts.get(CONF_AI_TASK_ENTITY)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task")),
        }
        for key, default in (
            (CONF_HAZARD_THUNDERSTORM, "hard"),
            (CONF_HAZARD_FOG, "warn"),
            (CONF_HAZARD_SQUALL, "warn"),
            (CONF_HAZARD_HEAVY_RAIN, "warn"),
        ):
            m, s = tier(key, default)
            fields[m] = s
        fields[
            vol.Optional(
                CONF_SQUALL_BEAUFORT_KN,
                default=str(opts.get(CONF_SQUALL_BEAUFORT_KN, DEFAULT_SQUALL_BEAUFORT_KN)),
            )
        ] = selector.SelectSelector(selector.SelectSelectorConfig(options=beaufort_opts))
        schema = vol.Schema(fields)
        return self.async_show_form(step_id="settings", data_schema=schema)

    def _save(self, changes: dict[str, Any]) -> ConfigFlowResult:
        new_options = {**self.config_entry.options, **changes}
        return self.async_create_entry(title="", data=new_options)
