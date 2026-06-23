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

- 🗺️ **Favourite spots** — add by name + coordinates; the provider locks onto the
  nearest model grid automatically.
- 🏄 **Per-sport profiles** — kitesurf, windsurf, wing foil, surf, SUP, sailing,
  sea swim, and wakeboarding (inland *and* sea). Each has a tunable preference
  profile (wind window, gust ceiling, preferred wind directions, wave window,
  water temperature).
- 📊 **Deterministic scoring** — a transparent 0–100 suitability score per
  (spot × sport), with a factor breakdown, that works with **no API key and no
  LLM**.
- 🤖 **Optional AI verdicts** — wire up a Home Assistant **AI Task** entity
  (Claude/OpenAI/local) and Swelligence asks for a *structured* rating + a
  one-line "should I go?" summary, layered on top of the numbers.
- 🔌 **Pluggable providers** — Open-Meteo (free, no key) ships first; Windy and
  Stormglass slot into the same interface.
- 🔔 **Automations** — score sensors + `suitable now` binary sensors per
  (spot × sport) drive any notification/automation you like.

## Entities

For every (spot × sport) you enable:

| Entity | Example | Meaning |
| --- | --- | --- |
| `sensor` | `sensor.swelligence_rye_kitesurf_suitability` | 0–100 score now, with `verdict`, `factors`, `best_in_hours`, and (if enabled) `ai_rating`/`ai_summary` attributes |
| `binary_sensor` | `binary_sensor.swelligence_rye_kitesurf_suitable_now` | On when the score clears the suitability threshold |

Each spot is a single HA **device**, so all its sports group together.

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

## Development

```bash
pip install -r requirements-test.txt
pytest                              # pure-logic suite (no Home Assistant needed)
python3 scripts/validate_spots.py   # live Open-Meteo scoring sanity-check
python3 scripts/analyze_history.py  # re-score the windiest recent days
```

The unit tests cover the deterministic scorer, profile overrides, the
water-type policy, and Open-Meteo normalisation. They import the pure submodules
via a stub package (`tests/conftest.py`) so they run without installing Home
Assistant. Config-flow/coordinator tests that need the HA harness are tracked
with the live-HA smoke test.

## Status

**v0.1 — scaffold / foundation.** Core pipeline (provider → score → entities)
and config/options flow are in place. See [`docs/SCOPE.md`](docs/SCOPE.md) for
the full design and [the milestone list](docs/SCOPE.md#roadmap).

## License

MIT — see [LICENSE](LICENSE).
