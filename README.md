# Swelligence 🌊🪁

**Water- & wind-sports intelligence for Home Assistant.**

Track your favourite spots, set per-sport preferences, and get a suitability
score (and an optional AI-written verdict) for *which spots are good for which
sports, right now and in the next 24h*.

> *swell + intelligence* — conditions, scored.

---

## Why

There are good single-purpose pieces on HACS (Surfline surf reports, a Windy
weather/wave bridge, tide integrations) but nothing that does the thing a
multi-discipline rider actually wants: **"given my spots, my sports and my
preferences — where should I go today?"** Swelligence is that layer.

Prior art that inspired / can complement this:

- [victorigualada/surf-forecast-integration](https://github.com/victorigualada/surf-forecast-integration) — the favourite-spots + threshold pattern (Surfline).
- [udjamaflip/windy-home](https://github.com/udjamaflip/windy-home) — Windy wind/wave/swell sensors.
- [ianByrne/HASS-ukho_tides](https://github.com/ianByrne/HASS-ukho_tides) — UK tide data (future provider).
- [timmaurice/lovelace-windy-card](https://github.com/timmaurice/lovelace-windy-card) — embeddable Windy map card.

## Features

- 🗺️ **Favourite spots** — add by place-name search (geocoded) or raw
  coordinates; the provider locks onto the nearest model grid automatically. Edit
  a spot's sports or water type any time.
- 🏄 **Per-sport profiles** — kitesurf, windsurf, wing foil, surf, SUP, sailing,
  sea swim, and wakeboarding (inland *and* sea). Each has a tunable preference
  profile (wind window, gust ceiling, preferred wind directions, wave window,
  water temperature).
- 📊 **Deterministic scoring** — a transparent 0–100 suitability score per
  (spot × sport), with a factor breakdown, that works with **no API key and no
  LLM**.
- 🎯 **Forecast confidence** — the score's blind spot is *"is this forecast even
  trustworthy?"* Swelligence answers it from **model agreement**: tight agreement
  between independent models reads as high confidence, wide divergence as low.
  Stormglass already returns several source models per field, so confidence comes
  **free, with zero extra requests**; configure a second marine source and you
  get **cross-provider** agreement too (with an optional consensus *blend* for
  accuracy). Each sensor exposes a `confidence` value + `high`/`moderate`/`low`
  label.
- 🔎 **Data-quality notes** — a per-sensor `data_quality` summary names the
  source behind each domain and flags what's thin (e.g. *"swell: open_meteo,
  windsea-only, no groundswell direction"*) or a grid cell that snapped far
  offshore.
- 🧭 **Better-source nudges** — a per-spot diagnostic **Source advice** sensor
  spots when a domain is routed to a weaker-than-available source (e.g. swell on
  Open-Meteo while you have Stormglass configured, or UK tides not using UKHO)
  and names the upgrade — only when a better, *configured* source is actually
  going unused.
- 🤖 **Optional AI verdicts** — wire up a Home Assistant **AI Task** entity
  (Claude/OpenAI/local) and Swelligence asks for a *structured* rating + a
  one-line "should I go?" summary, layered on top of the numbers. The verdict is
  fed the model agreement + data sources, so it can hedge in plain language
  (*"models split on swell size — I'd wait for the next run"*).
- 🔌 **Pluggable providers** — Open-Meteo (free, no key) is the default;
  Stormglass (keyed) slots into the same interface, with a UKHO tide overlay
  for UK spots. Per-spot, per-domain source routing and a budget-aware
  cross-provider ensemble layer on top. Add provider API keys from the
  integration's options.
- 🔔 **Automations** — score sensors + `suitable now` binary sensors per
  (spot × sport) drive any notification/automation you like.

## Entities

For every (spot × sport) you enable:

| Entity | Example | Meaning |
| --- | --- | --- |
| `sensor` | `sensor.swelligence_rye_kitesurf_suitability` | 0–100 score now, with `verdict`, `factors`, `best_in_hours`, `data_quality`, `confidence`/`confidence_label` (when model agreement is available), and (if enabled) `ai_rating`/`ai_summary` attributes |
| `binary_sensor` | `binary_sensor.swelligence_rye_kitesurf_suitable_now` | On when the score clears the suitability threshold |

Plus one diagnostic sensor **per spot**:

| Entity | Example | Meaning |
| --- | --- | --- |
| `sensor` (diagnostic) | `sensor.swelligence_rye_source_advice` | Count of "better source available" nudges; `recommendations` attribute carries the detail. `0` = on the best source it can reach |

Each spot is a single HA **device**, so all its sports group together.

The `get_overview` service also returns a top-level `source_advice` array and
per-entry `confidence` for dashboard cards.

## Install

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → add this repo, category **Integration**.
2. Install **Swelligence**, restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Swelligence*.
4. Pick your sports + default provider (Open-Meteo needs no key).
5. Open the integration's options → **Add a favourite spot**.

### AI verdicts (optional)

Set up any **AI Task**-capable conversation agent (e.g. Anthropic/Claude,
OpenAI, or a local model), then in Swelligence options → *AI / general settings*
enable the LLM toggle and select the AI Task entity.

### Cross-provider confidence (optional)

Intra-model confidence from Stormglass needs nothing beyond its API key. To get
**cross-provider** confidence, set a marine source for a spot (options → *edit
spot*) and enable **Cross-provider confidence** on the providers step; tick
**Blend** as well to replace the marine values with the two-source consensus.
Both are budget-throttled by the same free-tier interval as polling.

## Lovelace card

`www/swelligence-card.js` is a dependency-free, theme-aware custom card with four
**modes**, each built around the bespoke sport icon set:

| `mode` | Shows | Data |
| --- | --- | --- |
| `podium` *(default)* | each day's **top-3** opportunities (preference-ranked) | `get_overview` |
| `timeline` | per-spot **opportunity timeline** — only go-worthy windows over 7 days | `get_overview` |
| `heatgrid` | spot × sport **suitability now** (verdict colour + rig size) | live sensor states |
| `medallions` | per-spot **rings now** (gauge fills to score) | live sensor states |

Cells/medallions colour by verdict; kite/wing show the rig size from your quiver;
sports order by your **Sport priority** — drag to reorder in the card's visual
editor (most-wanted first).

A **visual editor** is supported — add the card from the dashboard's card picker
("Swelligence Card", with live preview) and configure mode/title/filters in the
UI; no YAML needed. The YAML below is equivalent.

Install:

1. Copy `www/swelligence-card.js` to your HA `config/www/`.
2. Add a Lovelace resource: URL `/local/swelligence-card.js`, type **JavaScript module**.
3. Add cards (visual editor, or YAML):

   ```yaml
   type: custom:swelligence-card
   mode: podium          # podium | timeline | heatgrid | medallions
   title: Conditions
   # optional:
   # days: 4             # forecast modes: how many days to show (1-7)
   # spots: ["Avon Beach", "Hurst Spit / Keyhaven"]
   # sports: ["kitesurf", "surf"]
   ```

   Filters (`spots`, `sports`, `days`) apply to every mode; for podium/timeline
   they're sent to `get_overview` so the podium is recomputed for the subset.

Hard-refresh the browser after install/upgrade so the new resource loads.

## Development

```bash
pip install -r requirements-test.txt
pytest                              # pure-logic suite (no Home Assistant needed)
python3 scripts/validate_spots.py   # live Open-Meteo scoring sanity-check
python3 scripts/analyze_history.py  # re-score the windiest recent days
```

The unit tests cover the deterministic scorer, profile overrides, the
water-type policy, Open-Meteo normalisation, forecast confidence (intra-model and
cross-provider), data-quality summaries, the provider-authority nudges, and the
AI-Task prompt builder. They import the pure submodules via a stub package
(`tests/conftest.py`) so they run without installing Home Assistant.
Config-flow/coordinator tests that need the HA harness are tracked with the
live-HA smoke test.

## Status

**v0.1 — scaffold / foundation.** Core pipeline (provider → score → entities)
and config/options flow are in place. See [`docs/SCOPE.md`](docs/SCOPE.md) for
the full design and [the milestone list](docs/SCOPE.md#roadmap).

## License

MIT — see [LICENSE](LICENSE).
